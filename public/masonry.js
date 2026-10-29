function setupMasonry(grid) {
  const gapX = 12, gapY = 16;
  let previous = [], heights = [], lastWidth = -1, lastColumns = 0;
  let frame = 0;
  const watched = new Set();

  function schedule() {
    if (!frame) frame = requestAnimationFrame(layout);
  }

  function layout() {
    frame = 0;
    const width = grid.clientWidth;
    if (!width) return;

    const pins = [...grid.children].filter(node => node.matches('.pin'));
    const columns = matchMedia('(max-width: 500px)').matches
      ? 2
      : Math.max(1, Math.floor((width + gapX) / (200 + gapX)));
    const cardWidth = Math.max(
      1, (width - gapX * (columns - 1)) / columns
    );

    for (const pin of pins) {
      pin.style.width = cardWidth + 'px';
    }

    const sizes = pins.map(pin => pin.getBoundingClientRect().height);
    const rebuild = width !== lastWidth
      || columns !== lastColumns
      || pins.length < previous.length
      || previous.some((item, i) =>
        pins[i] !== item.pin
        || Math.abs(sizes[i] - item.height) > 0.5
      );

    if (rebuild) {
      previous = [];
      heights = Array(columns).fill(0);
    }

    for (let i = previous.length; i < pins.length; i++) {
      const pin = pins[i];
      const column = heights.indexOf(Math.min(...heights));

      pin.style.left = column * (cardWidth + gapX) + 'px';
      pin.style.top = heights[column] + 'px';
      heights[column] += sizes[i] + gapY;
      previous.push({ pin, height: sizes[i] });
    }

    grid.style.height = pins.length
      ? Math.max(...heights) - gapY + 'px'
      : '0px';

    lastWidth = width;
    lastColumns = columns;
  }

  const resize = new ResizeObserver(schedule);
  resize.observe(grid);

  function syncPins() {
    for (const pin of watched) {
      if (pin.parentElement !== grid) {
        resize.unobserve(pin);
        watched.delete(pin);
      }
    }

    for (const pin of grid.children) {
      if (pin.matches('.pin') && !watched.has(pin)) {
        resize.observe(pin);
        watched.add(pin);
      }
    }

    schedule();
  }

  new MutationObserver(syncPins).observe(grid, { childList: true });
  window.addEventListener('resize', schedule);
  syncPins();
}
