(() => {
  /* ── Horizontal nav scroll spy ── */
  const navItems = document.querySelectorAll('.nav__item[data-section]');
  const sections = [...document.querySelectorAll('.need-section[data-need]')];

  if (navItems.length && sections.length && 'IntersectionObserver' in window) {
    const obs = new IntersectionObserver((entries) => {
      entries.forEach(e => {
        if (e.isIntersecting) {
          navItems.forEach(i => i.classList.remove('is-active'));
          const active = document.querySelector(`.nav__item[data-section="${e.target.dataset.need}"]`);
          if (active) active.classList.add('is-active');
        }
      });
    }, { rootMargin: '-15% 0px -75% 0px' });

    sections.forEach(s => obs.observe(s));
  }

  /* ── Newsfeed prev/next buttons ── */
  const NF_ARROW_L = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>';
  const NF_ARROW_R = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>';
  document.querySelectorAll('.block--newsfeed').forEach(block => {
    const scroller = block.querySelector('.newsfeed-scroller');
    if (!scroller) return;

    const prev = document.createElement('button');
    prev.type = 'button';
    prev.className = 'newsfeed-nav newsfeed-nav--prev';
    prev.setAttribute('aria-label', 'Previous');
    prev.innerHTML = NF_ARROW_L;

    const next = document.createElement('button');
    next.type = 'button';
    next.className = 'newsfeed-nav newsfeed-nav--next';
    next.setAttribute('aria-label', 'Next');
    next.innerHTML = NF_ARROW_R;

    block.appendChild(prev);
    block.appendChild(next);

    const pageStep = () => {
      const card = scroller.querySelector('.news-card');
      const cardW = card ? card.getBoundingClientRect().width : scroller.clientWidth * 0.8;
      const cs = getComputedStyle(scroller);
      const gap = parseFloat(cs.columnGap || cs.gap) || 0;
      return cardW + gap;
    };

    const updateState = () => {
      const max = scroller.scrollWidth - scroller.clientWidth - 1;
      prev.disabled = scroller.scrollLeft <= 0;
      next.disabled = scroller.scrollLeft >= max;
    };

    prev.addEventListener('click', () => scroller.scrollBy({ left: -pageStep(), behavior: 'smooth' }));
    next.addEventListener('click', () => scroller.scrollBy({ left:  pageStep(), behavior: 'smooth' }));
    scroller.addEventListener('scroll', updateState, { passive: true });
    window.addEventListener('resize', updateState);
    updateState();
  });

  /* ── Latest news "Load more" ── */
  document.querySelectorAll('.block--latest-news').forEach(block => {
    const btn = block.querySelector('.latest-news__more');
    if (!btn) return;
    const step = parseInt(block.dataset.step, 10) || 5;
    btn.addEventListener('click', () => {
      const collapsed = block.querySelectorAll('.ln-card--collapsed');
      const reveal = Array.from(collapsed).slice(0, step);
      reveal.forEach(c => c.classList.remove('ln-card--collapsed'));
      const remaining = collapsed.length - reveal.length;
      if (remaining <= 0) {
        btn.hidden = true;
      } else {
        btn.dataset.remaining = String(remaining);
        const label = btn.querySelector('.latest-news__more-label');
        if (label) label.textContent = `Load ${Math.min(step, remaining)} more`;
      }
    });
  });

  /* ── Opinions tabs ── */
  document.querySelectorAll('.opinions').forEach(root => {
    const tabs   = root.querySelectorAll('.opinions__tab');
    const panels = root.querySelectorAll('.opinions__panel');
    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        const tier = tab.dataset.tier;
        tabs.forEach(t => t.classList.toggle('is-active', t === tab));
        panels.forEach(p => p.classList.toggle('is-active', p.dataset.tier === tier));
      });
    });
  });
})();
