// 周课表模块：增删改查 + 按星期分列展示
const TT_WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
let ttItems = [];
let ttEditingId = null;

async function loadTimetable() {
  try {
    ttItems = await apiFetch('/api/timetable');
  } catch (e) {
    ttItems = [];
  }
  renderTimetable();
}

function renderTimetable() {
  const grid = $('ttGrid');
  const cols = TT_WEEKDAYS.map((label, w) => {
    const items = ttItems.filter((x) => x.weekday === w);
    const cards = items
      .map((x) => `
        <div class="tt-card">
          <div class="tt-card-time">${escapeHtml(x.start_time)} - ${escapeHtml(x.end_time)}</div>
          <div class="tt-card-name">${escapeHtml(x.course_name)}</div>
          ${x.location ? `<div class="tt-card-loc">📍 ${escapeHtml(x.location)}</div>` : ''}
          ${x.note ? `<div class="tt-card-note">${escapeHtml(x.note)}</div>` : ''}
          <div class="tt-card-actions">
            <button class="btn btn-icon" onclick="editTt(${x.id})" title="编辑">✎</button>
            <button class="btn btn-icon" onclick="deleteTt(${x.id})" title="删除">✕</button>
          </div>
        </div>`)
      .join('');
    return `
      <div class="tt-col">
        <div class="tt-col-head">${label}</div>
        ${cards || '<div class="tt-col-empty">无课程</div>'}
      </div>`;
  }).join('');
  grid.innerHTML = `<div class="tt-cols">${cols}</div>`;
}

function resetTtForm() {
  ttEditingId = null;
  $('ttName').value = '';
  $('ttLocation').value = '';
  $('ttStart').value = '';
  $('ttEnd').value = '';
  $('ttAddBtn').textContent = '添加课程';
  $('ttError').textContent = '';
}

function editTt(id) {
  const item = ttItems.find((x) => x.id === id);
  if (!item) return;
  ttEditingId = id;
  $('ttWeekday').value = String(item.weekday);
  $('ttStart').value = item.start_time;
  $('ttEnd').value = item.end_time;
  $('ttName').value = item.course_name;
  $('ttLocation').value = item.location;
  $('ttAddBtn').textContent = '保存修改';
  document.querySelector('.tt-form').scrollIntoView({ behavior: 'smooth', block: 'center' });
}

async function deleteTt(id) {
  if (!confirm('确定删除这门课程吗？')) return;
  try {
    await apiFetch(`/api/timetable/${id}`, { method: 'DELETE' });
    showToast('已删除课程');
    await loadTimetable();
  } catch (e) {
    showToast(e.message || '删除失败');
  }
}

async function submitTt() {
  const err = $('ttError');
  err.textContent = '';
  const payload = {
    weekday: Number($('ttWeekday').value),
    start_time: $('ttStart').value,
    end_time: $('ttEnd').value,
    course_name: $('ttName').value.trim(),
    location: $('ttLocation').value.trim(),
  };
  if (!payload.course_name) { err.textContent = '请填写课程名称'; return; }
  if (!payload.start_time || !payload.end_time) { err.textContent = '请填写上课和下课时间'; return; }
  if (payload.end_time <= payload.start_time) { err.textContent = '下课时间必须晚于上课时间'; return; }

  try {
    if (ttEditingId) {
      await apiFetch(`/api/timetable/${ttEditingId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      showToast('✅ 已保存修改');
    } else {
      await apiFetch('/api/timetable', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      showToast('✅ 已添加课程');
    }
    resetTtForm();
    await loadTimetable();
  } catch (e) {
    err.textContent = e.message || '保存失败';
  }
}

function initTimetable() {
  $('ttAddBtn').addEventListener('click', submitTt);
  $('ttName').addEventListener('keydown', (e) => { if (e.key === 'Enter') submitTt(); });
  loadTimetable();
}

document.addEventListener('DOMContentLoaded', initTimetable);
