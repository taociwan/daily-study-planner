// AI 助手聊天窗口
let chatSending = false;

function appendMessage(role, content) {
  const box = $('chatMessages');
  const row = document.createElement('div');
  row.className = `chat-row ${role === 'assistant' ? 'assistant' : 'user'}`;
  row.innerHTML = `<div class="chat-bubble">${escapeHtml(content)}</div>`;
  box.appendChild(row);
  box.scrollTop = box.scrollHeight;
}

async function loadHistory() {
  try {
    const history = await apiFetch('/api/ai/history');
    history.forEach((m) => appendMessage(m.role, m.content));
  } catch (e) {}
}

async function sendMessage() {
  const input = $('chatInput');
  const message = input.value.trim();
  if (!message || chatSending) return;

  appendMessage('user', message);
  input.value = '';
  chatSending = true;
  $('chatSendBtn').disabled = true;

  try {
    const data = await apiFetch('/api/ai/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    });
    appendMessage('assistant', data.reply);
  } catch (e) {
    appendMessage('assistant', `⚠️ ${e.message}`);
  } finally {
    chatSending = false;
    $('chatSendBtn').disabled = false;
    input.focus();
  }
}

async function clearChat() {
  if (!confirm('清空全部对话记录？')) return;
  try {
    await apiFetch('/api/ai/clear', { method: 'POST' });
    $('chatMessages').innerHTML = '';
    showToast('对话已清空');
  } catch (e) {
    showToast(e.message || '清空失败');
  }
}

function initChat() {
  $('chatSendBtn').addEventListener('click', sendMessage);
  $('chatClearBtn').addEventListener('click', clearChat);
  $('chatInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendMessage();
  });
  loadHistory();
}

document.addEventListener('DOMContentLoaded', initChat);
