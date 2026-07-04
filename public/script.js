const form = document.getElementById('ideaForm');
const ideaInput = document.getElementById('ideaInput');
const submitBtn = document.getElementById('submitBtn');
const resultSection = document.getElementById('resultSection');
const loadingState = document.getElementById('loadingState');
const loadingTicker = document.getElementById('loadingTicker');
const verdictBlock = document.getElementById('verdictBlock');
const themesBlock = document.getElementById('themesBlock');
const citationsBlock = document.getElementById('citationsBlock');
const recBlock = document.getElementById('recBlock');
const errorBlock = document.getElementById('errorBlock');
const errorText = document.getElementById('errorText');
const caseNumber = document.getElementById('caseNumber');

caseNumber.textContent = String(Math.floor(1000 + Math.random() * 8999));

const tickerMessages = [
  'Pulling matching testimony…',
  'Cross-referencing subreddit threads…',
  'Weighing sentiment across sources…',
  'Drafting the verdict…',
];

let tickerInterval;

function startTicker() {
  let i = 0;
  loadingTicker.textContent = tickerMessages[0];
  tickerInterval = setInterval(() => {
    i = (i + 1) % tickerMessages.length;
    loadingTicker.textContent = tickerMessages[i];
  }, 900);
}

function stopTicker() {
  clearInterval(tickerInterval);
}

function resetPanels() {
  [verdictBlock, themesBlock, citationsBlock, recBlock, errorBlock].forEach(el => {
    el.hidden = true;
  });
}

function stampClassFor(label) {
  const l = (label || '').toLowerCase();
  if (l.includes('strong')) return '';
  if (l.includes('mixed')) return 'stamp--mixed';
  if (l.includes('insufficient')) return 'stamp--insufficient';
  return 'stamp--weak';
}

function renderResult(data) {
  resetPanels();

  // Verdict
  document.getElementById('verdictScore').innerHTML =
    `${data.verdict_score}<span>/10</span>`;
  document.getElementById('verdictLine').textContent = data.one_line_verdict || '';
  const stamp = document.getElementById('stamp');
  stamp.className = 'stamp ' + stampClassFor(data.verdict_label);
  document.getElementById('stampLabel').textContent = (data.verdict_label || 'REVIEWED').toUpperCase();

  const s = data.sentiment || { positive: 0, neutral: 0, negative: 0 };
  document.getElementById('segPos').style.width = s.positive + '%';
  document.getElementById('segNeu').style.width = s.neutral + '%';
  document.getElementById('segNeg').style.width = s.negative + '%';
  document.getElementById('pctPos').textContent = s.positive + '%';
  document.getElementById('pctNeu').textContent = s.neutral + '%';
  document.getElementById('pctNeg').textContent = s.negative + '%';
  verdictBlock.hidden = false;

  // Themes
  const themeList = document.getElementById('themeList');
  themeList.innerHTML = '';
  (data.themes || []).forEach(theme => {
    const card = document.createElement('div');
    card.className = 'theme-card';
    card.innerHTML = `
      <p class="theme-card__name">${escapeHtml(theme.theme)}</p>
      <p class="theme-card__summary">${escapeHtml(theme.summary)}</p>
      <p class="theme-card__refs">Refs: ${(theme.post_ids || []).join(', ')}</p>
    `;
    themeList.appendChild(card);
  });
  themesBlock.hidden = (data.themes || []).length === 0;

  // Citations
  const evidenceById = {};
  (data.evidence || []).forEach(p => { evidenceById[p.id] = p; });

  const citationList = document.getElementById('citationList');
  citationList.innerHTML = '';
  (data.citations || []).forEach(c => {
    const post = evidenceById[c.post_id];
    const row = document.createElement('div');
    row.className = 'citation';
    const idLink = post
      ? `<a href="${post.url}" target="_blank" rel="noopener">${c.post_id}</a>`
      : c.post_id;
    row.innerHTML = `
      <div class="citation__id">${idLink}</div>
      <div class="citation__body">
        <p>${escapeHtml(c.paraphrase)}</p>
        <p class="citation__source">${post ? escapeHtml(post.subreddit) + ' · ' + post.score + ' upvotes' : ''}</p>
      </div>
    `;
    citationList.appendChild(row);
  });
  citationsBlock.hidden = (data.citations || []).length === 0;

  // Recommendation
  document.getElementById('recText').textContent = data.recommendation || '';
  recBlock.hidden = !data.recommendation;
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str || '';
  return div.innerHTML;
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const idea = ideaInput.value.trim();
  if (!idea) return;

  resultSection.hidden = false;
  resetPanels();
  loadingState.hidden = false;
  submitBtn.disabled = true;
  submitBtn.textContent = 'Reviewing…';
  startTicker();
  resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

  try {
    const res = await fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ idea }),
    });
    const data = await res.json();

    stopTicker();
    loadingState.hidden = true;

    if (!res.ok || data.error) {
      errorText.textContent = data.error || 'Something went wrong opening the file.';
      errorBlock.hidden = false;
      return;
    }

    renderResult(data);
  } catch (err) {
    stopTicker();
    loadingState.hidden = true;
    errorText.textContent = 'Could not reach the analysis engine. Check your connection and try again.';
    errorBlock.hidden = false;
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Open the file';
  }
});
