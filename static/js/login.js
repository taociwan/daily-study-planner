document.getElementById('loginForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const name = document.getElementById('name').value.trim();
  const age = document.getElementById('age').value.trim();
  const gender = document.querySelector('input[name="gender"]:checked').value;
  const errorEl = document.getElementById('error');
  errorEl.textContent = '';

  if (!name || !age) {
    errorEl.textContent = '请填写姓名和年龄';
    return;
  }

  try {
    const res = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, age: Number(age), gender }),
    });
    const data = await res.json();
    if (!res.ok) {
      errorEl.textContent = data.error || '登录失败';
      return;
    }
    localStorage.setItem('user', JSON.stringify(data));
    window.location.href = '/schedule';
  } catch (err) {
    errorEl.textContent = '网络错误，请重试';
  }
});
