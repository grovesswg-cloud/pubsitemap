/* LORD — Section Page JavaScript
   Reads data-section attribute from <main> to filter articles. */

const ARTICLES_API = '../api/articles.json';

async function loadArticles() {
  try {
    const res = await fetch(ARTICLES_API);
    if (!res.ok) return [];
    const data = await res.json();
    return data.articles || [];
  } catch {
    return [];
  }
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
}

function typeLabel(type) {
  const map = {
    bulletin:  'The Bulletin',
    review:    'The Review',
    feature:   'The Feature',
    sermon:    'The Sermon',
    archive:   'The Archive',
    interview: 'The Interview',
    culture:   'Culture',
  };
  return map[type] || type.charAt(0).toUpperCase() + type.slice(1);
}

function escapeHtml(str) {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function renderCard(a) {
  const img = a.image
    ? `<div class="article-card-image-wrap"><img src="../${a.url.replace('articles/', '')}" alt="${escapeHtml(a.title)}" loading="lazy" onerror="this.parentElement.outerHTML='<div class=card-image-placeholder><span>LORD</span></div>'"></div>`
    : '<div class="card-image-placeholder"><span>LORD</span></div>';

  // Fix image path — url is relative to site root, section pages are one level up
  const imgFixed = a.image
    ? `<div class="article-card-image-wrap"><img src="${a.image}" alt="${escapeHtml(a.title)}" loading="lazy"></div>`
    : '<div class="card-image-placeholder"><span>LORD</span></div>';

  const genre = a.genre ? `<span class="card-genre">${escapeHtml(a.genre)}</span>` : '';

  return `
    <a href="../${a.url}" class="article-card">
      ${imgFixed}
      <div class="card-eyebrow ${a.type === 'bulletin' ? 'bulletin' : ''}">${typeLabel(a.type)}</div>
      ${genre}
      <div class="card-title">${escapeHtml(a.title)}</div>
      <div class="card-deck">${escapeHtml(a.deck || '')}</div>
      <div class="card-meta">${formatDate(a.date)}</div>
    </a>
  `;
}

function renderBulletinList(articles) {
  return articles.map((a, i) => `
    <a href="../${a.url}" class="bulletin-item">
      <div class="bulletin-num">${String(i + 1).padStart(2, '0')}</div>
      <div class="bulletin-content">
        <div class="bulletin-eyebrow">The Bulletin</div>
        <div class="bulletin-title">${escapeHtml(a.title)}</div>
        <div class="bulletin-deck">${escapeHtml(a.deck || '')}</div>
      </div>
      <div class="bulletin-meta">${formatDate(a.date)}</div>
    </a>
  `).join('');
}

async function init() {
  const main = document.querySelector('main[data-section]');
  if (!main) return;

  const section = main.dataset.section;
  const container = document.getElementById('section-content');
  if (!container) return;

  const all = await loadArticles();
  const filtered = section === 'all' ? all : all.filter(a => a.type === section);

  if (!filtered.length) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-title">Nothing here yet.</div>
        <div class="empty-state-text">The first dispatch is coming. Check back soon.</div>
      </div>`;
    return;
  }

  if (section === 'bulletin') {
    container.innerHTML = `<div class="bulletin-list">${renderBulletinList(filtered)}</div>`;
  } else {
    container.innerHTML = `<div class="articles-grid">${filtered.map(renderCard).join('')}</div>`;
  }

  // Mark active nav
  document.querySelectorAll('.site-nav a').forEach(link => {
    const href = link.getAttribute('href') || '';
    if (href.includes(section) || (section === 'bulletin' && href.includes('bulletin'))) {
      link.classList.add('active');
    }
  });
}

document.addEventListener('DOMContentLoaded', init);
