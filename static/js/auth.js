let mode = 'login';

const $ = (id) => document.getElementById(id);
const errorEl = $('error');

function switchMode(next) {
  mode = next;
  document.querySelectorAll('.auth-tab').forEach((t) => {
    t.classList.toggle('active', t.dataset.mode === mode);
  });
  $('registerFields').classList.toggle('hidden', mode !== 'register');
  $('submitBtn').textContent = mode === 'login' ? '登 录' : '注 册';
  $('password').autocomplete = mode === 'login' ? 'current-password' : 'new-password';
  errorEl.textContent = '';
}

document.querySelectorAll('.auth-tab').forEach((t) => {
  t.addEventListener('click', () => switchMode(t.dataset.mode));
});

$('authForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  errorEl.textContent = '';

  const username = $('username').value.trim();
  const password = $('password').value;
  if (!username || !password) {
    errorEl.textContent = '请输入用户名和密码';
    return;
  }

  let payload = { username, password };
  if (mode === 'register') {
    const confirm = $('confirmPassword').value;
    const name = $('name').value.trim();
    const age = $('age').value.trim();
    const gender = document.querySelector('input[name="gender"]:checked').value;
    if (password.length < 6) {
      errorEl.textContent = '密码至少 6 位';
      return;
    }
    if (password !== confirm) {
      errorEl.textContent = '两次输入的密码不一致';
      return;
    }
    if (!name) {
      errorEl.textContent = '请填写昵称';
      return;
    }
    if (!age) {
      errorEl.textContent = '请填写年龄';
      return;
    }
    payload = { username, password, name, age: Number(age), gender };
  }

  try {
    const res = await fetch(mode === 'login' ? '/api/login' : '/api/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) {
      errorEl.textContent = data.error || '操作失败';
      return;
    }
    window.location.href = '/app';
  } catch (err) {
    errorEl.textContent = '网络错误，请重试';
  }
});
