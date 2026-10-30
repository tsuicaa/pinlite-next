const $ = (id) => document.getElementById(id);

const grid = document.getElementById("grid");
const status = document.getElementById("status");
const loadMore = document.getElementById("load-more");

const cards = new Map();

let cursor = null;

function renderPin(pin) {
  cards.set(pin.id, pin);


  const button = document.createElement('a');
  button.className = 'pin';
  button.href = `/?pin=${encodeURIComponent(pin.id)}`;
  button.dataset.pinId = pin.id;
  button.setAttribute('aria-label', `Open pin: ${pin.title}`);
  const image = document.createElement('img');
  image.alt = pin.title;
  image.loading = 'lazy';
  image.decoding = 'async';
  image.referrerPolicy = 'no-referrer';
  image.src = pin.thumbnail || pin.image;
  image.addEventListener('error', () => { image.classList.add('failed'); image.alt = 'Image unavailable'; });
  const title = document.createElement('p');
    title.textContent = pin.title;
  button.append(image, title);
  button.addEventListener('click', event => {
    if (
      event.defaultPrevented
      || event.button !== 0
      || event.ctrlKey
      || event.metaKey
      || event.shiftKey
      || event.altKey
    ) return;

    event.preventDefault();
    history.pushState(null, "", button.href);
    showRoute();
  });
  return button;
}

async function loadPins() {
  loadMore.disabled = true;
  status.textContent = "Loading...";

  try {
    const url = new URL("/api/pins", location.origin);

    if (cursor) {
      url.searchParams.set("before", cursor);
    }

    const response = await fetch(url);

    if (!response.ok) {
      throw new Error("Cant load pins");
    }

    const data = await response.json();

    grid.append(...data.pins.map(renderPin));
    cursor = data.next_cursor;

    loadMore.hidden = !cursor;
    status.textContent = grid.childElementCount ? "" : "No pins";
  } catch (error) {
    status.textContent = error.message;
  } finally {
    loadMore.disabled = false;
  }
}

let detailController = null;
let feedScroll = 0;

async function showRoute() {
    detailController?.abort();

    const params = new URLSearchParams(location.search);
    const pinId = params.get("pin");
    const showingDetail = pinId !== null;
    const showingCollections = !showingDetail
        && params.get("view") === "collections";
    const showingHome = !showingDetail && !showingCollections;

    if (!grid.hidden && !showingHome) {
        feedScroll = window.scrollY;
    }

    $("detail").hidden = !showingDetail;
    $("collections-panel").hidden = !showingCollections;
    grid.hidden = !showingHome;
    $("sentinel").hidden = !showingHome;

    if (!showingDetail) {
        requestAnimationFrame(() => {
            window.scrollTo(0, showingHome ? feedScroll : 0);
        });
        return;
    }

    window.scrollTo(0, 0);
    $("detail-title").textContent = "";
    $("detail-description").textContent = "";
    $("detail-image").hidden = true;
    $("detail-image").removeAttribute("src");
    $("source-link").hidden = true;
    $("detail-status").textContent = "Loading…";

    detailController = new AbortController();
    const controller = detailController;

    try {
        const response = await fetch(
        `/api/pins/${encodeURIComponent(pinId)}`,
        { signal: controller.signal }
        );

        if (!response.ok) {
        throw new Error(
            response.status === 404 ? "Pin not found" : "Could not load pin."
        );
        }

        const pin = await response.json();
        if (controller.signal.aborted) return;

        $("detail-title").textContent = pin.title;
        $("detail-description").textContent = pin.description;
        $("detail-image").src = pin.image;
        $("detail-image").alt = pin.title;
        $("detail-image").hidden = false;
        $("detail-status").textContent = "";

        if (pin.source_url) {
        const source = new URL(pin.source_url);

        if (["http:", "https:"].includes(source.protocol)) {
            $("source-link").href = source.href;
            $("source-link").hidden = false;
        }
        }
    } catch (error) {
        if (error.name !== "AbortError") {
        $("detail-status").textContent = error.message;
        }
    }
}

loadMore.addEventListener("click", loadPins);

$("back").addEventListener("click", () => {
  history.pushState(null, "", "/");
  showRoute();
});

$("saved-pins").addEventListener("click", () => {
    history.pushState(null, "", "/?view=collections");
    showRoute();
})

window.addEventListener("popstate", showRoute);

setupMasonry(grid);
showRoute();
loadPins();