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
