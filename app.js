const grid = document.getElementById('grid');
const response = await fetch('catalog.json');
if (!response.ok) {
  grid.textContent = `catalog.json could not be loaded (HTTP ${response.status}). Run build.py first.`;
  throw new Error(`catalog.json: HTTP ${response.status}`);
}
const catalog = await response.json();
const dialog = document.getElementById('detail');
const state = { group: 'showcase', topic: '', query: '' };
let shown = [];
let current = -1;

const FLAGS = { partial: 'Weaker result', fails: 'Miss' };
const SETTINGS = [
  ['negative', 'Negative prompt'], ['size', 'Size'], ['seed', 'Seed'], ['steps', 'Steps'],
  ['guidance', 'Guidance'], ['cfg', 'Guidance'], ['strength', 'Strength'], ['resolution', 'Output size'],
  ['seconds', 'Time'],
];

const setup = catalog.setup;
document.getElementById('setup').innerHTML =
  `Made with <a href="${setup.app_url}">${setup.app}</a> and the ${setup.model} model on ${setup.machine}. ` +
  'The same settings give the same image on the same setup; other hardware can differ.';

const byId = new Map(catalog.items.map(item => [item.id, item]));
document.getElementById('stats').textContent =
  `${catalog.items.length} images, each with its prompt and settings.`;
document.getElementById('featured').innerHTML = (catalog.featured || []).map(id =>
  `<button data-id="${escape(id)}"><img src="thumb/${escape(id)}.webp" alt="${escape(byId.get(id).title)}"></button>`
).join('');
document.getElementById('featured').addEventListener('click', event => {
  const button = event.target.closest('button');
  if (!button) return;
  const item = byId.get(button.dataset.id);
  Object.assign(state, { group: item.group, topic: '', query: '' });
  document.getElementById('search').value = '';
  renderTabs();
  renderTopics();
  renderGrid();
  open(shown.indexOf(item));
});

if (!catalog.items.some(item => item.group === 'showcase')) {
  state.group = 'make';
  document.querySelector('[data-group="showcase"]').hidden = true;
}

function escape(text) {
  return String(text).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

function title(item) {
  return item.title;
}

function flag(item) {
  return FLAGS[item.verdict] ? `<span class="flag ${item.verdict}">${FLAGS[item.verdict]}</span>` : '';
}

function visible(item) {
  if (item.group !== state.group) return false;
  if (state.topic && item.topic !== state.topic) return false;
  if (!state.query) return true;
  const text = `${item.prompt} ${item.title} ${item.topic}`.toLowerCase();
  return state.query.split(/\s+/).every(word => text.includes(word));
}

function renderTabs() {
  for (const tab of document.querySelectorAll('#tabs button')) {
    tab.setAttribute('aria-pressed', tab.dataset.group === state.group);
  }
}

function renderTopics() {
  const order = catalog.topics;
  const topics = [...new Set(catalog.items.filter(i => i.group === state.group).map(i => i.topic))]
    .sort((a, b) => order.indexOf(a) - order.indexOf(b));
  document.getElementById('topics').innerHTML = (topics.length > 1 ? ['', ...topics] : []).map(topic =>
    `<button data-topic="${escape(topic)}" aria-pressed="${topic === state.topic}">${topic ? escape(topic) : 'All'}</button>`
  ).join('');
}

function renderGrid() {
  shown = catalog.items.filter(visible);
  grid.innerHTML = shown.map((item, index) => {
    const [width, height] = item.size.split(' x ').map(Number);
    return `<button class="card" data-index="${index}">` +
      `<img src="thumb/${item.id}.webp" width="${width}" height="${height}" loading="lazy" alt="${escape(item.prompt.slice(0, 140))}">` +
      `<span class="caption">${flag(item)}${escape(title(item))}</span></button>`;
  }).join('');
  document.getElementById('count').textContent = `${shown.length} images`;
}

function setting(key, item) {
  if (key === 'seconds') return item.seconds ? `${Math.round(item.seconds)} seconds` : '';
  if (key === 'resolution' && item.resolution === 'match') return 'same as the reference';
  return item[key] ?? '';
}

function open(index) {
  current = (index + shown.length) % shown.length;
  const item = shown[current];
  const img = document.getElementById('detail-img');
  img.src = `img/${item.id}.webp`;
  img.alt = item.prompt.slice(0, 200);
  const rows = SETTINGS.filter(([key]) => setting(key, item) !== '').map(([key, label]) =>
    `<dt>${label}</dt><dd>${escape(setting(key, item))}</dd>`);
  rows.unshift(`<dt>Model</dt><dd>${escape(item.model || setup.model)}</dd>`);
  if (item.refs.length) {
    rows.splice(1, 0, `<dt>Edited from</dt><dd class="refs">` +
      item.refs.map((ref, i) => `<a href="img/${ref}.webp" target="_blank"><img src="thumb/${ref}.webp" alt="Reference image ${i + 1}"></a>`).join('') +
      '</dd>');
  }
  const lines = [item.topic, item.watch, item.note].filter(Boolean);
  document.getElementById('detail-text').innerHTML =
    `<h2>${flag(item)}${escape(title(item))}</h2>` +
    (lines.length ? `<p class="note">${lines.map(escape).join('. ')}</p>` : '') +
    `<div class="prompt-box"><button class="copy">Copy</button>${escape(item.prompt)}</div>` +
    `<dl>${rows.join('')}</dl>`;
  if (!dialog.open) dialog.showModal();
}

document.getElementById('tabs').addEventListener('click', event => {
  const button = event.target.closest('button');
  if (!button) return;
  state.group = button.dataset.group;
  state.topic = '';
  renderTabs();
  renderTopics();
  renderGrid();
});
document.getElementById('topics').addEventListener('click', event => {
  const button = event.target.closest('button');
  if (!button) return;
  state.topic = button.dataset.topic;
  renderTopics();
  renderGrid();
});
document.getElementById('search').addEventListener('input', event => {
  state.query = event.target.value.trim().toLowerCase();
  renderGrid();
});
grid.addEventListener('click', event => {
  const card = event.target.closest('.card');
  if (card) open(Number(card.dataset.index));
});
document.getElementById('detail-text').addEventListener('click', async event => {
  const button = event.target.closest('.copy');
  if (!button) return;
  try {
    await navigator.clipboard.writeText(shown[current].prompt);
    button.textContent = 'Copied';
  } catch (error) {
    button.textContent = 'Select the text to copy';
    console.error('Clipboard write failed', error);
  }
});
document.getElementById('close').addEventListener('click', () => dialog.close());
document.getElementById('prev').addEventListener('click', () => open(current - 1));
document.getElementById('next').addEventListener('click', () => open(current + 1));
dialog.addEventListener('keydown', event => {
  if (event.key === 'ArrowLeft') open(current - 1);
  if (event.key === 'ArrowRight') open(current + 1);
});

renderTabs();
renderTopics();
renderGrid();
