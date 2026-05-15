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

  /* ── Timeline expander ── */
  document.querySelectorAll('.timeline__expand').forEach((btn, i) => {
    const wrap = btn.parentElement;
    const panel = wrap && wrap.querySelector(':scope > .timeline__earlier');
    if (!panel) return;

    const id = panel.id || `tl-earlier-${i}`;
    panel.id = id;
    btn.setAttribute('aria-controls', id);

    const label = btn.querySelector('.timeline__expand-label');
    const collapsedLabel = btn.dataset.collapsedLabel || (label && label.textContent) || 'Show earlier';
    const expandedLabel = btn.dataset.expandedLabel || 'Hide earlier';

    btn.addEventListener('click', () => {
      const isOpen = panel.dataset.open === 'true';
      panel.dataset.open = isOpen ? 'false' : 'true';
      btn.setAttribute('aria-expanded', isOpen ? 'false' : 'true');
      if (label) label.textContent = isOpen ? collapsedLabel : expandedLabel;
    });
  });

  /* ── Perspectives tabs ── */
  document.querySelectorAll('.pv-tabs').forEach(tabBar => {
    const block = tabBar.closest('.block--reactions');
    if (!block) return;
    const tabs   = tabBar.querySelectorAll('.pv-tab');
    const panels = block.querySelectorAll('.pv-panel');

    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        const target = tab.dataset.tab;
        tabs.forEach(t => t.classList.remove('active'));
        panels.forEach(p => p.classList.remove('active'));
        tab.classList.add('active');
        const panel = block.querySelector(`#${target}`);
        if (panel) panel.classList.add('active');
      });
    });
  });
})();
