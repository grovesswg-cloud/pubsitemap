/* LORD — Main JavaScript */

const ARTICLES_API = 'api/articles.json';

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

function imagePlaceholder(label = 'LORD') {
  return `<div class="card-image-placeholder"><span>${label}</span></div>`;
}

function renderArticleCard(a, featured = false) {
  const img = a.image
    ? `<div class="article-card-image-wrap"><img src="${a.image}" alt="${escapeHtml(a.title)}" loading="lazy"></div>`
    : imagePlaceholder('LORD');

  const genre = a.genre ? `<span class="card-genre">${escapeHtml(a.genre)}</span>` : '';

  return `
    <a href="${a.url}" class="article-card${featured ? ' featured' : ''}">
      ${img}
      <div class="card-eyebrow ${a.type === 'bulletin' ? 'bulletin' : ''}">${typeLabel(a.type)}</div>
      ${genre}
      <div class="card-title">${escapeHtml(a.title)}</div>
      <div class="card-deck">${escapeHtml(a.deck || '')}</div>
      <div class="card-meta">${formatDate(a.date)}</div>
    </a>
  `;
}

function renderBulletinItem(a, index) {
  return `
    <a href="${a.url}" class="bulletin-item">
      <div class="bulletin-num">${String(index + 1).padStart(2, '0')}</div>
      <div class="bulletin-content">
        <div class="bulletin-eyebrow">The Bulletin</div>
        <div class="bulletin-title">${escapeHtml(a.title)}</div>
        <div class="bulletin-deck">${escapeHtml(a.deck || '')}</div>
      </div>
      <div class="bulletin-meta">${formatDate(a.date)}</div>
    </a>
  `;
}

function escapeHtml(str) {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function renderHero(a) {
  if (!a) return;
  const hero = document.getElementById('hero');
  if (!hero) return;

  if (a.image) {
    const img = Object.assign(document.createElement('img'), {
      className: 'hero-image',
      src: a.image,
      alt: a.title,
    });
    hero.insertBefore(img, hero.firstChild);
  }

  const setEl = (id, html) => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
  };

  setEl('hero-eyebrow', typeLabel(a.type));
  setEl('hero-title', escapeHtml(a.title));
  setEl('hero-deck', escapeHtml(a.deck || ''));
  setEl('hero-date', formatDate(a.date));
  setEl('hero-link', `<a href="${a.url}" class="hero-read-link">Read &rarr;</a>`);
}

function getGridColumns() {
  // Match CSS breakpoints
  if (window.innerWidth <= 768) return 1;
  if (window.innerWidth <= 1100) return 2;
  return 3;
}

function populateGrid(id, articles, targetRows = 2) {
  const el = document.getElementById(id);
  if (!el) return;

  const cols = getGridColumns();
  // Show exactly targetRows complete rows, or all articles if fewer than target
  const targetCount = targetRows * cols;
  const count = articles.length >= targetCount ? targetCount : articles.length;
  const slice = articles.slice(0, count);

  if (!slice.length) {
    el.innerHTML = '<div class="empty-state"><div class="empty-state-title">Coming soon.</div></div>';
    return;
  }
  el.innerHTML = slice.map((a, i) => renderArticleCard(a, i === 0 && slice.length >= 3)).join('');
}

function populateBulletins(id, articles, max = 5) {
  const el = document.getElementById(id);
  if (!el) return;
  if (!articles.length) {
    el.innerHTML = '<div class="empty-state"><div class="empty-state-text">No bulletins yet. Check back soon.</div></div>';
    return;
  }
  el.innerHTML = articles.slice(0, max).map(renderBulletinItem).join('');
}

function todayStr() {
  return new Date().toISOString().split('T')[0];
}

function addScrollArrow() {
  const hero = document.getElementById('hero');
  if (!hero) return;

  const arrow = document.createElement('button');
  arrow.className = 'hero-scroll-arrow';
  arrow.innerHTML = '↓';
  arrow.setAttribute('aria-label', 'Scroll to articles');
  arrow.addEventListener('click', () => {
    const main = document.querySelector('main');
    if (main) {
      main.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
  hero.appendChild(arrow);
}

async function init() {
  const all = await loadArticles();

  const bulletins  = all.filter(a => a.type === 'bulletin');
  const reviews    = all.filter(a => a.type === 'review');
  const features   = all.filter(a => a.type === 'feature');

  // Hero: latest article of any type
  renderHero(all[0]);
  addScrollArrow();

  // Today's bulletins (fall back to most recent 3)
  const today = todayStr();
  const todayBulletins = bulletins.filter(a => a.date === today);
  populateBulletins('bulletins-container', todayBulletins.length ? todayBulletins : bulletins);

  // Reviews
  populateGrid('reviews-container', reviews);

  // Features
  populateGrid('features-container', features);

  // Mark active nav link
  document.querySelectorAll('.site-nav a').forEach(link => {
    if (link.getAttribute('href') === 'index.html' || link.getAttribute('href') === '/') {
      link.classList.add('active');
    }
  });
}

document.addEventListener('DOMContentLoaded', init);
