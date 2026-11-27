// 今日计划模块：每日计划、计时器、提醒、长期目标
const COMPLETE_RATIO = 0.80; // 完成计划时长的 80% 即认定完成

let selectedDate = localDateStr();
let plans = [];
let goals = [];
let editingPlanId = null;
let editingGoalId = null;
const WEEKDAY_CN = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
const activeTimers = new Map();
const planStartTs = new Map();
const marked80 = new Set();
const reminded = new Set();
let reminderQueue = [];
let reminderOpen = false;
let currentReminderPlan = null;

const STATUS = {
  planned:       { text: '待开始', cls: 'planned' },
  in_progress:   { text: '进行中', cls: 'in-progress' },
  completed:     { text: '已完成', cls: 'completed' },
  not_completed: { text: '未完成', cls: 'not-completed' },
};

// ---------------- 工具函数 ----------------
function sourceBadge(plan) {
  if (plan.source === 'goal') return '<span class="badge badge-goal" title="来自长期目标">目标</span>';
  if (plan.source === 'history') return '<span class="badge badge-auto" title="根据历史习惯自动生成">习惯</span>';
  if (plan.source === 'ai') return '<span class="badge badge-ai" title="来自 AI 复盘建议">AI</span>';
  return '';
}

function formatUsed(s) {
  if (s == null) return '—';
  s = Math.max(0, Math.floor(s));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}小时${m}分${sec}秒`;
  if (m > 0) return `${m}分${sec}秒`;
  return `${sec}秒`;
}

function planMinutes(t) {
  const [h, m] = t.split(':').map(Number);
  return h * 60 + m;
}

function durationSeconds(plan) {
  return (planMinutes(plan.end_time) - planMinutes(plan.start_time)) * 60;
}

function startedAtTs(plan) {
  if (!plan.started_at) return null;
  const m = plan.started_at.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/);
  if (!m) return null;
  const d = new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]);
  return isNaN(d.getTime()) ? null : d.getTime();
}

// ---------------- 声音 ----------------
let audioCtx = null;
function playSound() {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!audioCtx) audioCtx = new Ctx();
    if (audioCtx.state === 'suspended') audioCtx.resume();
    const t0 = audioCtx.currentTime;
    const tone = (freq, start, dur) => {
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = 'sine';
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0, t0 + start);
      gain.gain.linearRampToValueAtTime(0.4, t0 + start + 0.02);
      gain.gain.linearRampToValueAtTime(0, t0 + start + dur);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start(t0 + start);
      osc.stop(t0 + start + dur);
    };
    tone(880, 0, 0.3);
    tone(1108.73, 0.35, 0.45);
  } catch (e) {}
}

// ---------------- 数据加载 ----------------
async function loadPlans() {
  try {
    plans = await apiFetch(`/api/plans?date=${selectedDate}`);
  } catch (e) {
    plans = [];
  }
  renderSummary();
  renderTimeline();
  renderList();
  syncTimers();
  checkReminders();
  checkDayCelebration();
}

// ---------------- 渲染：统计 ----------------
function renderSummary() {
  const total = plans.length;
  const completed = plans.filter((p) => p.status === 'completed').length;
  const inProgress = plans.filter((p) => p.status === 'in_progress').length;
  const notCompleted = plans.filter((p) => p.status === 'not_completed').length;
  const pct = total ? Math.round((completed / total) * 100) : 0;

  $('summary').innerHTML = `
    <div class="stat"><div class="stat-num">${total}</div><div class="stat-label">总计划</div></div>
    <div class="stat stat-green"><div class="stat-num">${completed}</div><div class="stat-label">已完成</div></div>
    <div class="stat stat-amber"><div class="stat-num">${inProgress}</div><div class="stat-label">进行中</div></div>
    <div class="stat stat-red"><div class="stat-num">${notCompleted}</div><div class="stat-label">未完成</div></div>
    <div class="summary-progress">
      <div class="progress-track">
        <div class="progress-fill" style="width:${pct}%"></div>
      </div>
      <div class="progress-text">完成率 ${pct}%</div>
    </div>
  `;
}

// ---------------- 渲染：24 小时时间轴 ----------------
function renderTimeline() {
  const blocks = plans
    .map((plan) => {
      const startMin = planMinutes(plan.start_time);
      const endMin = planMinutes(plan.end_time);
      const left = ((startMin / 1440) * 100).toFixed(3);
      const width = Math.max(0.4, ((endMin - startMin) / 1440) * 100).toFixed(3);
      const st = STATUS[plan.status] || STATUS.planned;
      return `<div class="tl-block tl-${st.cls}" style="left:${left}%;width:${width}%"
        title="${escapeHtml(plan.description)} ${plan.start_time}-${plan.end_time}">${escapeHtml(plan.description)}</div>`;
    })
    .join('');

  $('timeline').innerHTML = `
    <div class="tl-labels">
      <span>0:00</span><span>6:00</span><span>12:00</span><span>18:00</span><span>24:00</span>
    </div>
    <div class="tl-track">${blocks || '<div class="tl-empty">暂无计划</div>'}</div>
  `;
}

// ---------------- 渲染：计划列表 ----------------
function renderList() {
  const list = $('planList');
  if (!plans.length) {
    list.innerHTML = '<div class="empty">📭 还没有计划，先在上面添加一个时间段吧</div>';
    return;
  }
  const isToday = selectedDate === localDateStr();

  list.innerHTML = plans
    .map((plan) => {
      const st = STATUS[plan.status] || STATUS.planned;
      const expired = plan.status === 'not_completed' && !plan.closed_at;
      let right = '';

      if (plan.status === 'planned') {
        right = `<div class="plan-status"><span class="badge badge-planned">${st.text}</span></div>`;
        if (isToday && currentTimeStr() < plan.end_time) {
          right += `<button class="btn btn-start" onclick="startPlan(${plan.id})">▶ 开始</button>`;
        }
        right += `<button class="btn btn-icon" onclick="editPlan(${plan.id})" title="编辑">✎</button>`;
      } else if (plan.status === 'in_progress') {
        right = `
          <div class="plan-status">
            <span class="badge badge-in-progress">${st.text}</span>
            <span class="elapsed" data-elapsed="${plan.id}"></span>
            <span class="countdown" data-countdown="${plan.id}"></span>
          </div>`;
      } else if (plan.status === 'completed') {
        const stillRunning = plan.plan_date === localDateStr() && plan.end_time > currentTimeStr();
        if (stillRunning) {
          right = `
            <div class="plan-status">
              <span class="badge badge-completed">${st.text}</span>
              <span class="elapsed" data-elapsed="${plan.id}"></span>
              <span class="countdown" data-countdown="${plan.id}"></span>
            </div>`;
        } else {
          right = `
            <div class="plan-status">
              <span class="badge badge-completed">${st.text}</span>
              <span class="used-time">用时 ${formatUsed(plan.elapsed_seconds)}</span>
            </div>`;
        }
      } else if (expired) {
        right = `
          <div class="plan-status">
            <span class="badge badge-not-completed">${st.text}</span>
            <button class="btn btn-ghost btn-sm" onclick="closePlan(${plan.id})">结束任务</button>
            <button class="btn btn-primary btn-sm" onclick="openPostpone(${plan.id})">延顺任务</button>
          </div>`;
      } else {
        right = `<div class="plan-status"><span class="badge badge-${st.cls}">${st.text}</span></div>`;
      }

      const progress = plan.status === 'in_progress'
        ? `<div class="progress-track"><div class="progress-fill" data-progress="${plan.id}"></div></div>`
        : '';
      const expiredHint = expired
        ? '<div class="expired-hint">⏰ 计划时间已过，你并没有完成该计划</div>'
        : '';

      return `
        <div class="plan-row${expired ? ' plan-expired' : ''}">
          <div class="plan-time">${plan.start_time}<span class="sep">→</span>${plan.end_time}</div>
          <div class="plan-desc">${escapeHtml(plan.description)}${sourceBadge(plan)}${expiredHint}</div>
          <div class="plan-right">
            ${right}
            <button class="btn btn-icon" onclick="deletePlan(${plan.id})" title="删除">✕</button>
          </div>
        </div>
        ${progress}`;
    })
    .join('');
}

// ---------------- 计时器 ----------------
function startCountdown(plan) {
  if (activeTimers.has(plan.id)) return;
  if (plan.status === 'completed') marked80.add(plan.id);

  const startTs = planStartTs.get(plan.id) || startedAtTs(plan) || Date.now();
  planStartTs.set(plan.id, startTs);
  const total = durationSeconds(plan);
  const threshold = total * COMPLETE_RATIO;

  const update = () => {
    const elapsed = (Date.now() - startTs) / 1000;
    const remaining = total - elapsed;

    const countEl = document.querySelector(`[data-countdown="${plan.id}"]`);
    const barEl = document.querySelector(`[data-progress="${plan.id}"]`);
    const elapsedEl = document.querySelector(`[data-elapsed="${plan.id}"]`);
    if (elapsedEl) elapsedEl.textContent = '已用 ' + formatUsed(elapsed);
    if (countEl) countEl.textContent = remaining > 0 ? '剩余 ' + formatUsed(remaining) : '完成';
    if (barEl) barEl.style.width = Math.min(100, (elapsed / total) * 100) + '%';

    if (elapsed >= threshold && !marked80.has(plan.id)) {
      marked80.add(plan.id);
      markCompleted(plan.id);
    }
    if (elapsed >= total) {
      stopCountdown(plan.id);
      finalizePlan(plan.id);
    }
  };

  update();
  activeTimers.set(plan.id, { interval: setInterval(update, 1000), update });
}

function stopCountdown(id) {
  const t = activeTimers.get(id);
  if (t) {
    clearInterval(t.interval);
    activeTimers.delete(id);
  }
}

function tickActiveTimers() {
  activeTimers.forEach((t) => t.update());
}

function syncTimers() {
  const now = currentTimeStr();
  const keepIds = new Set(
    plans.filter((p) => p.status === 'in_progress' || p.status === 'completed').map((p) => p.id)
  );
  for (const id of [...activeTimers.keys()]) {
    if (!keepIds.has(id)) stopCountdown(id);
  }
  plans.filter((p) => p.status === 'in_progress').forEach((p) => {
    if (!activeTimers.has(p.id)) startCountdown(p);
  });
  plans
    .filter((p) => p.status === 'completed' && p.plan_date === localDateStr() && p.end_time > now)
    .forEach((p) => {
      if (!activeTimers.has(p.id)) startCountdown(p);
    });
  tickActiveTimers();
}

// ---------------- 庆祝：单任务 / 全天 ----------------
function celebratePlan(plan) {
  if (App.celebratedPlans.has(plan.id)) return;
  App.celebratedPlans.add(plan.id);
  showCelebration({
    icon: '🎉',
    title: '恭喜完成该计划！',
    text: `「${plan.description}」已完成，继续保持这个节奏！`,
  });
}

function checkDayCelebration() {
  if (selectedDate !== localDateStr()) return;
  const total = plans.length;
  const completed = plans.filter((p) => p.status === 'completed').length;
  if (total > 0 && completed === total && !App.celebratedDay) {
    App.celebratedDay = true;
    setTimeout(() => {
      showCelebration({
        icon: '🏆',
        title: '恭喜完成今天的全部任务！',
        text: `今天 ${total} 项计划全部搞定，你太棒了，好好奖励自己一下吧！`,
      });
    }, 600);
  }
}

// ---------------- 交互 ----------------
async function startPlan(id) {
  let data = {};
  try {
    data = await apiFetch(`/api/plans/${id}/start`, { method: 'POST' });
  } catch (e) {
    showToast(e.message || '无法开始计划');
    await loadPlans();
    return;
  }
  planStartTs.set(id, Date.now());
  await loadPlans();
  showToast(data.early ? '▶ 已提前开始，计时中…' : '▶ 计划已开始，计时中…');
}

async function markCompleted(id) {
  try {
    const res = await fetch(`/api/plans/${id}/complete`, { method: 'POST' });
    const data = await res.json();
    const plan = plans.find((p) => p.id === id);
    if (plan) {
      plan.status = 'completed';
      plan.completed_at = data.completed_at;
      plan.elapsed_seconds = data.elapsed_seconds;
      celebratePlan(plan);
    }
  } catch (e) {}
  renderList();
  showToast('✅ 已认定完成（达到 80%）');
}

async function finalizePlan(id) {
  try {
    const res = await fetch(`/api/plans/${id}/complete`, { method: 'POST' });
    const data = await res.json();
    const plan = plans.find((p) => p.id === id);
    if (plan) plan.elapsed_seconds = data.elapsed_seconds;
  } catch (e) {}
  await loadPlans();
}

async function deletePlan(id) {
  if (!confirm('确定删除这个计划吗？')) return;
  if (editingPlanId === id) resetAddForm();
  stopCountdown(id);
  try {
    await apiFetch(`/api/plans/${id}`, { method: 'DELETE' });
  } catch (e) {}
  await loadPlans();
}

async function closePlan(id) {
  if (!confirm('结束该任务？将标记为未完成并保留记录。')) return;
  stopCountdown(id);
  try {
    await apiFetch(`/api/plans/${id}/close`, { method: 'POST' });
  } catch (e) {
    showToast(e.message || '操作失败');
    return;
  }
  await loadPlans();
  await loadGoals();
  showToast('任务已结束');
}

// ---------------- 延顺任务 ----------------
let postponingPlanId = null;

function openPostpone(id) {
  const plan = plans.find((p) => p.id === id);
  if (!plan) return;
  postponingPlanId = id;
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  $('postponeDate').value = localDateStr(tomorrow);
  $('postponeStart').value = plan.start_time;
  $('postponeEnd').value = plan.end_time;
  $('postponeText').textContent =
    `「${plan.description}」原时段：${plan.plan_date} ${plan.start_time}-${plan.end_time}`;
  $('postponeError').textContent = '';
  $('postponeModal').classList.remove('hidden');
}

function closePostpone() {
  $('postponeModal').classList.add('hidden');
  postponingPlanId = null;
}

async function submitPostpone() {
  const id = postponingPlanId;
  if (!id) return;
  const err = $('postponeError');
  err.textContent = '';

  const planDate = $('postponeDate').value;
  const startTime = $('postponeStart').value;
  const endTime = $('postponeEnd').value;
  if (!planDate || !startTime || !endTime) {
    err.textContent = '请填写新日期和时段';
    return;
  }
  if (endTime <= startTime) {
    err.textContent = '结束时间必须晚于开始时间';
    return;
  }

  try {
    await apiFetch(`/api/plans/${id}/postpone`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: planDate, start_time: startTime, end_time: endTime }),
    });
  } catch (e) {
    err.textContent = e.message || '延顺失败';
    return;
  }

  closePostpone();
  await loadPlans();
  await loadGoals();
  showToast('✅ 任务已延顺');
}

// ---------------- 提醒弹窗 ----------------
function checkReminders() {
  if (selectedDate !== localDateStr()) return;
  const now = currentTimeStr();
  plans
    .filter((p) => p.status === 'planned' && p.end_time > now && !reminded.has(p.id) && p.start_time <= now)
    .forEach((p) => {
      reminded.add(p.id);
      enqueueReminder(p);
    });
}

function enqueueReminder(plan) {
  reminderQueue.push(plan);
  processReminderQueue();
}

function processReminderQueue() {
  if (reminderOpen || reminderQueue.length === 0) return;
  reminderOpen = true;
  const plan = reminderQueue.shift();
  currentReminderPlan = plan;
  $('reminderText').textContent = `「${plan.description}」 ${plan.start_time} - ${plan.end_time}`;
  $('reminderModal').classList.remove('hidden');
  playSound();
}

function closeReminder() {
  $('reminderModal').classList.add('hidden');
  reminderOpen = false;
  currentReminderPlan = null;
  processReminderQueue();
}

// ---------------- 添加 / 编辑计划 ----------------
function resetAddForm() {
  editingPlanId = null;
  $('description').value = '';
  $('startTime').value = '';
  $('endTime').value = '';
  $('addBtn').textContent = '添加';
  $('addFormTitle').textContent = '＋ 添加时间段计划';
  $('editHint').classList.add('hidden');
}

function editPlan(id) {
  const plan = plans.find((p) => p.id === id);
  if (!plan) return;
  editingPlanId = id;
  $('startTime').value = plan.start_time;
  $('endTime').value = plan.end_time;
  $('description').value = plan.description;
  $('addBtn').textContent = '保存修改';
  $('addFormTitle').textContent = '✎ 修改时间段计划';
  $('editHintText').textContent = `正在编辑「${plan.description}」${plan.start_time} - ${plan.end_time}`;
  $('editHint').classList.remove('hidden');
  $('formError').textContent = '';
  document.querySelector('.add-plan').scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function cancelEdit() {
  resetAddForm();
  $('formError').textContent = '';
}

async function addPlan() {
  const startTime = $('startTime').value;
  const endTime = $('endTime').value;
  const description = $('description').value.trim();
  const err = $('formError');
  err.textContent = '';

  if (!startTime || !endTime || !description) {
    err.textContent = '请填写开始时间、结束时间和计划内容';
    return;
  }
  if (endTime <= startTime) {
    err.textContent = '结束时间必须晚于开始时间';
    return;
  }

  const payload = { date: selectedDate, start_time: startTime, end_time: endTime, description };
  const editing = editingPlanId;
  if (editing) {
    const clash = plans.find((p) => p.id !== editing && p.start_time === startTime);
    if (clash) {
      err.textContent = '该开始时间已有其他计划，请调整时间';
      return;
    }
  }

  try {
    await apiFetch(editing ? `/api/plans/${editing}` : '/api/plans', {
      method: editing ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    resetAddForm();
    await loadPlans();
    showToast(editing ? '✅ 已保存修改' : '✅ 已添加计划');
  } catch (e) {
    err.textContent = e.message || '保存失败';
  }
}

// ---------------- 长期目标 ----------------
const GOAL_STATUS = {
  active:   { text: '进行中', cls: 'badge-completed' },
  upcoming: { text: '未开始', cls: 'badge-planned' },
  ended:    { text: '已结束', cls: 'badge-ended' },
};

async function loadGoals() {
  try {
    goals = await apiFetch('/api/goals');
  } catch (e) {
    goals = [];
  }
  renderGoals();
}

function goalWeekdayText(g) {
  if (g.weekdays.length >= 7) return '每天';
  return g.weekdays.map((d) => WEEKDAY_CN[d]).join('、');
}

function renderGoals() {
  const box = $('goalList');
  if (!goals.length) {
    box.innerHTML = '<div class="empty">还没有长期目标。设定后，系统会自动为范围内每天生成学习计划。</div>';
    return;
  }
  box.innerHTML = goals
    .map((g) => {
      const st = GOAL_STATUS[g.status] || GOAL_STATUS.upcoming;
      const task = g.daily_task && g.daily_task !== g.title
        ? `<div class="goal-task">每日：${escapeHtml(g.daily_task)}</div>`
        : '';
      return `
        <div class="goal-row">
          <span class="badge ${st.cls}">${st.text}</span>
          <div class="goal-main">
            <div class="goal-title">${escapeHtml(g.title)}</div>
            <div class="goal-meta">${g.start_date} 至 ${g.end_date} · ${goalWeekdayText(g)} · ${g.start_time}-${g.end_time}</div>
            ${task}
            <div class="goal-progress">已安排 ${g.scheduled_count} 天 · 已完成 ${g.completed_count} 天</div>
          </div>
          <div class="goal-actions">
            <button class="btn btn-icon" onclick="editGoal(${g.id})" title="编辑">✎</button>
            <button class="btn btn-icon" onclick="deleteGoal(${g.id})" title="删除">✕</button>
          </div>
        </div>`;
    })
    .join('');
}

function resetGoalForm() {
  editingGoalId = null;
  const end = new Date();
  end.setDate(end.getDate() + 30);
  $('goalTitle').value = '';
  $('goalDailyTask').value = '';
  $('goalStartDate').value = localDateStr();
  $('goalEndDate').value = localDateStr(end);
  $('goalStartTime').value = '';
  $('goalEndTime').value = '';
  document.querySelectorAll('#goalWeekdayChips input').forEach((x) => { x.checked = true; });
  $('goalAddBtn').textContent = '添加长期目标';
  $('goalFormTitle').textContent = '＋ 新建长期目标';
  $('goalEditHint').classList.add('hidden');
  $('goalError').textContent = '';
}

function editGoal(id) {
  const g = goals.find((x) => x.id === id);
  if (!g) return;
  editingGoalId = id;
  $('goalTitle').value = g.title;
  $('goalDailyTask').value = g.daily_task || '';
  $('goalStartDate').value = g.start_date;
  $('goalEndDate').value = g.end_date;
  $('goalStartTime').value = g.start_time;
  $('goalEndTime').value = g.end_time;
  const chosen = new Set(g.weekdays);
  document.querySelectorAll('#goalWeekdayChips input').forEach((x) => {
    x.checked = chosen.has(Number(x.value));
  });
  $('goalAddBtn').textContent = '保存修改';
  $('goalFormTitle').textContent = '✎ 修改长期目标';
  $('goalEditHintText').textContent = `正在编辑「${g.title}」`;
  $('goalEditHint').classList.remove('hidden');
  $('goalError').textContent = '';
  document.querySelector('.goal-form').scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function cancelGoalEdit() {
  resetGoalForm();
}

async function addGoal() {
  const err = $('goalError');
  err.textContent = '';

  const title = $('goalTitle').value.trim();
  const daily_task = $('goalDailyTask').value.trim();
  const start_date = $('goalStartDate').value;
  const end_date = $('goalEndDate').value;
  const start_time = $('goalStartTime').value;
  const end_time = $('goalEndTime').value;
  const weekdays = [...document.querySelectorAll('#goalWeekdayChips input:checked')].map((x) => Number(x.value));

  if (!title) { err.textContent = '请填写目标名称'; return; }
  if (!start_date || !end_date) { err.textContent = '请选择开始日期和结束日期'; return; }
  if (end_date < start_date) { err.textContent = '结束日期不能早于开始日期'; return; }
  if (!start_time || !end_time) { err.textContent = '请填写每日开始和结束时间'; return; }
  if (end_time <= start_time) { err.textContent = '结束时间必须晚于开始时间'; return; }
  if (!weekdays.length) { err.textContent = '请至少选择一个执行日'; return; }

  const editing = editingGoalId;
  try {
    await apiFetch(editing ? `/api/goals/${editing}` : '/api/goals', {
      method: editing ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, daily_task, start_date, end_date, start_time, end_time, weekdays }),
    });
    resetGoalForm();
    await loadGoals();
    await loadPlans();
    showToast(editing ? '✅ 已保存目标，未来计划重新安排' : '✅ 已添加长期目标，每日计划已生成');
  } catch (e) {
    err.textContent = e.message || '保存失败';
  }
}

async function deleteGoal(id) {
  if (!confirm('删除这个长期目标吗？今天起未开始的目标计划会一并删除，已完成记录保留。')) return;
  if (editingGoalId === id) resetGoalForm();
  try {
    await apiFetch(`/api/goals/${id}`, { method: 'DELETE' });
  } catch (e) {}
  await loadGoals();
  await loadPlans();
  showToast('已删除长期目标');
}

function updateRegenButton() {
  $('regenBtn').disabled = selectedDate < localDateStr();
}

async function regeneratePlans() {
  if (selectedDate < localDateStr()) {
    showToast('只能重新生成今天或未来的计划');
    return;
  }
  if (!confirm('将重新生成这一天的自动计划；手动修改、进行中、已完成的计划会保留。继续？')) return;
  try {
    await apiFetch('/api/plans/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: selectedDate }),
    });
  } catch (e) {
    showToast(e.message || '生成失败');
    return;
  }
  await loadGoals();
  await loadPlans();
  showToast('⟳ 已重新生成当天计划');
}

// ---------------- 初始化 ----------------
function initPlans() {
  $('datePicker').value = selectedDate;
  updateRegenButton();

  $('datePicker').addEventListener('change', (e) => {
    selectedDate = e.target.value || localDateStr();
    resetAddForm();
    updateRegenButton();
    loadPlans();
  });
  $('addBtn').addEventListener('click', addPlan);
  $('cancelEdit').addEventListener('click', cancelEdit);
  $('description').addEventListener('keydown', (e) => { if (e.key === 'Enter') addPlan(); });
  $('regenBtn').addEventListener('click', regeneratePlans);

  $('goalAddBtn').addEventListener('click', addGoal);
  $('goalCancelEdit').addEventListener('click', cancelGoalEdit);
  $('goalTitle').addEventListener('keydown', (e) => { if (e.key === 'Enter') addGoal(); });

  $('postponeCancel').addEventListener('click', closePostpone);
  $('postponeConfirm').addEventListener('click', submitPostpone);

  $('reminderDismiss').addEventListener('click', closeReminder);
  $('reminderStart').addEventListener('click', () => {
    const plan = currentReminderPlan;
    closeReminder();
    if (plan) startPlan(plan.id);
  });

  document.addEventListener('pointerdown', () => {
    if (audioCtx && audioCtx.state === 'suspended') audioCtx.resume();
  }, { once: true });

  resetGoalForm();
  loadGoals();
  loadPlans();
  setInterval(() => { loadPlans(); loadGoals(); }, 10000);
}

document.addEventListener('DOMContentLoaded', initPlans);
