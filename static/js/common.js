// 公共工具：会话、导航、Toast、庆祝弹窗、请求封装
const $ = (id) => document.getElementById(id);

const App = {
  me: null,
  celebratedPlans: new Set(),
  celebratedDay: false,
};

function escapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function localDateStr(d = new Date()) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function currentTimeStr() {
  return new Date().toTimeString().slice(0, 5);
}

async function apiFetch(url, opts = {}) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (res.status === 401) {
    window.location.href = '/';
    throw new Error('未登录');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || '请求失败');
  return data;
}

function showToast(msg) {
  const el = $('toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove('show'), 2500);
}

// ---------------- 导航 ----------------
function switchTab(tab) {
  document.querySelectorAll('.nav-item').forEach((b) => b.classList.toggle('active', b.dataset.tab === tab));
  document.querySelectorAll('.tab-panel').forEach((p) => p.classList.toggle('active', p.id === `tab-${tab}`));
}

document.querySelectorAll('.nav-item').forEach((btn) => {
  btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

// ---------------- 庆祝弹窗 ----------------
const CELEBRATE_ICONS = ['🎉', '🌟', '🎊', '🏆', '✨', '🥳'];

function _confetti(box) {
  box.innerHTML = '';
  const colors = ['#b3472b', '#2f6b46', '#8f5c12', '#e0a83c', '#76578a', '#4a6b85'];
  for (let i = 0; i < 36; i++) {
    const piece = document.createElement('span');
    piece.className = 'confetti-piece';
    piece.style.left = Math.random() * 100 + '%';
    piece.style.background = colors[Math.floor(Math.random() * colors.length)];
    piece.style.animationDelay = Math.random() * 0.4 + 's';
    piece.style.animationDuration = 1.2 + Math.random() * 0.8 + 's';
    piece.style.transform = `rotate(${Math.random() * 360}deg)`;
    box.appendChild(piece);
  }
}

function showCelebration({ icon, title, text }) {
  $('celebrateIcon').textContent = icon || CELEBRATE_ICONS[Math.floor(Math.random() * CELEBRATE_ICONS.length)];
  $('celebrateTitle').textContent = title || '恭喜完成！';
  $('celebrateText').textContent = text || '';
  _confetti($('confettiBox'));
  $('celebrateModal').classList.remove('hidden');
  if (window.playSound) playSound();
}

function closeCelebration() {
  $('celebrateModal').classList.add('hidden');
}

$('celebrateOk').addEventListener('click', closeCelebration);

// ---------------- 初始化：校验登录 ----------------
async function initApp() {
  try {
    App.me = await apiFetch('/api/me');
    $('userName').textContent = App.me.name;
    const genderText = App.me.gender === 'male' ? '男' : '女';
    $('userMeta').textContent = `${App.me.username} · ${App.me.age || ''} 岁 · ${genderText}`;
    if (typeof window.renderAccount === 'function') window.renderAccount();
  } catch (e) {
    // apiFetch 已在 401 时跳转
  }
}

$('logout').addEventListener('click', async () => {
  try {
    await apiFetch('/api/logout', { method: 'POST' });
  } catch (e) {}
  window.location.href = '/';
});

initApp();
