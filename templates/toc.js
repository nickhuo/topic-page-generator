(() => {
  const items = document.querySelectorAll('.page-toc__item');
  if (!items.length || !('IntersectionObserver' in window)) return;
  const map = new Map();
  items.forEach((li) => map.set(li.dataset.target, li));
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((e) => {
        const li = map.get(e.target.id);
        if (!li) return;
        if (e.isIntersecting) {
          items.forEach((x) => x.classList.remove('is-active'));
          li.classList.add('is-active');
        }
        if (e.boundingClientRect.top < 0) li.classList.add('is-visited');
      });
    },
    { rootMargin: '-40% 0px -55% 0px' }
  );
  document.querySelectorAll('main .need-section').forEach((s) => observer.observe(s));
})();
