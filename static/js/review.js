// 复盘模块：手写复盘 + AI 评价建议 + 次日计划采纳
let currentReview = null;

function reviewDateStr() {
  return $('reviewDate').value || localDateStr();
}

async function loadReview() {
  const date = reviewDateStr();
  try {
    const data = await apiFetch(`/api/reviews?date=${date}`);
    currentReview = data.review;
    renderReview(data.review);
    renderHistory(data.history);
  } catch (e) {
    showToast(e.message || '加载复盘失败');
  }
}

function renderReview(review) {
  $('reviewManual').value = review ? review.manual_text : '';
  if (!review || (!review.ai_review && !review.ai_advice && !(review.ai_suggestions || []).length)) {
    $('reviewResult').classList.add('hidden');
    return;
  }
  $('aiReview').textContent = review.ai_review || '（无评价）';
  $('aiAdvice').textContent = review.ai_advice || '（无建议）';
  renderSuggestions(review.ai_suggestions || []);
  $('reviewResult').classList.remove('hidden');
}

function renderSuggestions(suggestions) {
  const box = $('aiSuggestions');
  if (!suggestions.length) {
    box.innerHTML = '<div class="empty">AI 暂未给出次日任务建议</div>';
    return;
  }
  box.innerHTML = suggestions
    .map((s) => `
      <div class="suggest-row">
        <span class="suggest-time">${escapeHtml(s.start_time)} → ${escapeHtml(s.end_time)}</span>
        <span class="suggest-desc">${escapeHtml(s.description)}</span>
      </div>`)
    .join('');
}

function renderHistory(history) {
  const box = $('reviewHistory');
  if (!history || !history.length) {
    box.innerHTML = '<div class="empty">还没有历史复盘记录</div>';
    return;
  }
  box.innerHTML = history
    .map((h) => {
      const manual = h.manual_text ? escapeHtml(h.manual_text.slice(0, 80)) : '<span class="hint">未写手写复盘</span>';
      const ai = h.ai_review ? `<div class="history-ai">🤖 ${escapeHtml(h.ai_review.slice(0, 100))}</div>` : '';
      return `
        <div class="history-row">
          <div class="history-date">${h.review_date}</div>
          <div class="history-body">
            <div class="history-manual">✍️ ${manual}</div>
            ${ai}
          </div>
        </div>`;
    })
    .join('');
}

async function saveReview() {
  const err = $('reviewError');
  err.textContent = '';
  try {
    await apiFetch('/api/reviews', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: reviewDateStr(), manual_text: $('reviewManual').value.trim() }),
    });
    showToast('✅ 复盘已保存');
    await loadReview();
  } catch (e) {
    err.textContent = e.message || '保存失败';
  }
}

async function aiReview() {
  const err = $('reviewError');
  err.textContent = '';
  $('reviewAiBtn').disabled = true;
  try {
    const data = await apiFetch('/api/reviews/ai-review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: reviewDateStr() }),
    });
    renderReview({
      manual_text: $('reviewManual').value.trim(),
      ai_review: data.review,
      ai_advice: data.advice,
      ai_suggestions: data.suggestions,
    });
    showToast('🤖 AI 复盘完成');
  } catch (e) {
    err.textContent = e.message || 'AI 复盘失败';
  } finally {
    $('reviewAiBtn').disabled = false;
  }
}

async function applySuggestions() {
  try {
    const data = await apiFetch('/api/reviews/apply-suggestions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: reviewDateStr() }),
    });
    if (data.inserted > 0) {
      showToast(`✅ 已把 ${data.inserted} 条建议加入 ${data.next_date} 的计划`);
    } else {
      showToast(`没有新建议被采纳（${data.skipped} 条被跳过）`);
    }
  } catch (e) {
    showToast(e.message || '采纳失败');
  }
}

function initReview() {
  $('reviewDate').value = localDateStr();
  $('reviewDate').addEventListener('change', loadReview);
  $('reviewSaveBtn').addEventListener('click', saveReview);
  $('reviewAiBtn').addEventListener('click', aiReview);
  $('applySuggestBtn').addEventListener('click', applySuggestions);
  loadReview();
}

document.addEventListener('DOMContentLoaded', initReview);
