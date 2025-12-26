(() => {
  const reduceMotion =
    window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduceMotion) return;

  const canvas = document.getElementById('bgBrainsCanvas');
  if (!canvas) return;

  const ctx = canvas.getContext('2d', { alpha: true });
  if (!ctx) return;

  const img = new Image();
  img.src = '/static/images/brains.png';

  const state = {
    dpr: 1,
    w: 0,
    h: 0,
    items: [],
    running: true,
    lastT: 0,
  };

  function resize() {
    const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
    const w = Math.floor(window.innerWidth);
    const h = Math.floor(window.innerHeight);

    state.dpr = dpr;
    state.w = w;
    state.h = h;

    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function rand(min, max) {
    return min + Math.random() * (max - min);
  }

  function initItems() {
    const area = state.w * state.h;
    const target = Math.max(10, Math.min(28, Math.floor(area / 55000)));
    const items = [];

    for (let i = 0; i < target; i++) {
      const size = rand(22, 48);
      const r = size * 0.5;
      const speed = rand(12, 42);
      const angle = rand(0, Math.PI * 2);
      items.push({
        x: rand(r, state.w - r),
        y: rand(r, state.h - r),
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed,
        r,
        size,
        rot: rand(0, Math.PI * 2),
        vr: rand(-0.5, 0.5),
        alpha: rand(0.10, 0.22),
      });
    }

    state.items = items;
  }

  function resolveEdge(it) {
    if (it.x - it.r < 0) {
      it.x = it.r;
      it.vx *= -1;
    } else if (it.x + it.r > state.w) {
      it.x = state.w - it.r;
      it.vx *= -1;
    }

    if (it.y - it.r < 0) {
      it.y = it.r;
      it.vy *= -1;
    } else if (it.y + it.r > state.h) {
      it.y = state.h - it.r;
      it.vy *= -1;
    }
  }

  function resolveCollisions() {
    const a = state.items;
    for (let i = 0; i < a.length; i++) {
      for (let j = i + 1; j < a.length; j++) {
        const p = a[i];
        const q = a[j];
        const dx = q.x - p.x;
        const dy = q.y - p.y;
        const dist2 = dx * dx + dy * dy;
        const minD = p.r + q.r;
        if (dist2 >= minD * minD) continue;

        const dist = Math.sqrt(dist2) || 0.0001;
        const nx = dx / dist;
        const ny = dy / dist;
        const overlap = minD - dist;

        // separate
        p.x -= nx * (overlap * 0.5);
        p.y -= ny * (overlap * 0.5);
        q.x += nx * (overlap * 0.5);
        q.y += ny * (overlap * 0.5);

        // velocity impulse (swap along normal)
        const pv = p.vx * nx + p.vy * ny;
        const qv = q.vx * nx + q.vy * ny;
        const diff = qv - pv;
        p.vx += nx * diff;
        p.vy += ny * diff;
        q.vx -= nx * diff;
        q.vy -= ny * diff;
      }
    }
  }

  function step(t) {
    if (!state.running) return;
    if (!state.lastT) state.lastT = t;
    const dt = Math.min(0.032, Math.max(0.001, (t - state.lastT) / 1000));
    state.lastT = t;

    ctx.clearRect(0, 0, state.w, state.h);

    // move
    for (const it of state.items) {
      it.x += it.vx * dt;
      it.y += it.vy * dt;
      it.rot += it.vr * dt;
      resolveEdge(it);
    }

    resolveCollisions();

    // draw
    for (const it of state.items) {
      ctx.save();
      ctx.globalAlpha = it.alpha;
      ctx.translate(it.x, it.y);
      ctx.rotate(it.rot);
      ctx.drawImage(img, -it.size / 2, -it.size / 2, it.size, it.size);
      ctx.restore();
    }

    requestAnimationFrame(step);
  }

  function onVisibility() {
    state.running = !document.hidden;
    if (state.running) {
      state.lastT = 0;
      requestAnimationFrame(step);
    }
  }

  window.addEventListener('resize', () => {
    resize();
    initItems();
  });
  document.addEventListener('visibilitychange', onVisibility);

  img.onload = () => {
    resize();
    initItems();
    requestAnimationFrame(step);
  };
})();


