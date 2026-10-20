'use strict';
(() => {
  const search = document.getElementById('search');
  const filters = [...document.querySelectorAll('[data-category].filter')];
  const cards = [...document.querySelectorAll('.article-card')];
  const status = document.getElementById('result-status');
  const emptyState = document.getElementById('empty-state');
  const reset = document.getElementById('reset-filters');
  let category = 'all';
  const normalize = value => value.normalize('NFKC').toLowerCase().trim();
  const searchable = new Map(cards.map(card => [card, normalize(card.dataset.search + ' ' + card.textContent)]));

  function update() {
    const terms = normalize(search.value).split(/\s+/u).filter(Boolean);
    let visible = 0;
    for (const card of cards) {
      const categoryMatches = category === 'all' || card.dataset.category === category;
      const queryMatches = terms.every(term => searchable.get(card).includes(term));
      card.hidden = !(categoryMatches && queryMatches);
      if (!card.hidden) visible++;
    }
    status.textContent = (category === 'all' && !terms.length) ? `共 ${visible} 篇手册` : `找到 ${visible} 篇手册 / 共 ${cards.length} 篇`;
    emptyState.hidden = visible !== 0;
    for (const filter of filters) {
      const active = filter.dataset.category === category;
      filter.classList.toggle('is-active', active);
      filter.setAttribute('aria-pressed', String(active));
    }
  }
  filters.forEach(filter => filter.addEventListener('click', () => {
    category = filter.dataset.category;
    update();
  }));
  search.addEventListener('input', update);
  search.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      search.value = '';
      update();
    }
  });
  reset.addEventListener('click', () => {
    search.value = '';
    category = 'all';
    update();
    search.focus();
  });
  update();
})();
