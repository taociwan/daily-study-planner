// 设置模块：AI 模型配置 + 账号信息
async function loadAiConfig() {
  try {
    const cfg = await apiFetch('/api/ai/config');
    $('aiBaseUrl').value = cfg.base_url || '';
    $('aiModel').value = cfg.model || '';
    $('aiSystem').value = cfg.system_prompt || '';
    $('aiKey').placeholder = cfg.has_key ? '已保存，留空表示不修改' : '请输入 API Key';
  } catch (e) {}
}

async function saveAiConfig() {
  const err = $('aiConfigError');
  err.textContent = '';
  const payload = {
    base_url: $('aiBaseUrl').value.trim(),
    model: $('aiModel').value.trim(),
    system_prompt: $('aiSystem').value.trim(),
    api_key: $('aiKey').value,
  };
  try {
    await apiFetch('/api/ai/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    $('aiKey').value = '';
    showToast('✅ AI 配置已保存');
    await loadAiConfig();
  } catch (e) {
    err.textContent = e.message || '保存失败';
  }
}

async function testAi() {
  const err = $('aiConfigError');
  err.textContent = '';
  $('aiTestBtn').disabled = true;
  try {
    const data = await apiFetch('/api/ai/test', { method: 'POST' });
    showToast('✅ 连接成功：' + (data.reply || 'OK'));
  } catch (e) {
    err.textContent = e.message || '连接失败';
  } finally {
    $('aiTestBtn').disabled = false;
  }
}

function renderAccount() {
  const me = App.me;
  if (!me) return;
  const genderText = me.gender === 'male' ? '男' : '女';
  $('accountInfo').innerHTML = `
    <div class="account-row"><span>用户名</span><b>${escapeHtml(me.username)}</b></div>
    <div class="account-row"><span>昵称</span><b>${escapeHtml(me.name)}</b></div>
    <div class="account-row"><span>年龄</span><b>${me.age || '—'}</b></div>
    <div class="account-row"><span>性别</span><b>${genderText}</b></div>
  `;
}

function initSettings() {
  $('aiSaveBtn').addEventListener('click', saveAiConfig);
  $('aiTestBtn').addEventListener('click', testAi);
  loadAiConfig();
  renderAccount();
}

document.addEventListener('DOMContentLoaded', initSettings);
