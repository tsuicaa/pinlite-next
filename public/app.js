const $ = (id) => document.getElementById(id);

const grid = document.getElementById("grid");
const status = document.getElementById("status");
const loadMore = document.getElementById("load-more");

const cards = new Map();

let cursor = null;

let feedPath = null;
let feedController = null;

function resetFeed() {
    feedController?.abort();
    feedController = null;
    feedPath = null;
    cursor = null;
    cards.clear();
    grid.replaceChildren();
    $("heading").textContent = "";
    status.textContent = "";
    loadMore.hidden = true;
    document.dispatchEvent(new CustomEvent("collection-feed", { detail: null }));
}

function renderPin(pin) {
    cards.set(pin.id, pin);
    const button = document.createElement('a');
    button.className = 'pin';

    const pinUrl = new URL("/", location.origin);
    pinUrl.searchParams.set("pin", pin.id);

    const params = new URLSearchParams(location.search);
    const collectionId = params.get("collection")
    if (collectionId !== null) {
        pinUrl.searchParams.set("collection", collectionId);
    } else if (params.get("view") === "my-pins") {
        pinUrl.searchParams.set("view", "my-pins");
    } else {
        for (const key of ["q", "tag"]) {
            if (params.get(key)) {
                pinUrl.searchParams.set(key, params.get(key));
            }
        }
    }

    button.href = pinUrl.pathname + pinUrl.search;

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
    if (feedController || !feedPath) return;

    const controller = new AbortController();
    feedController = controller;
    loadMore.disabled = true;
    status.textContent = "Loading...";

    try {
        const url = new URL(feedPath, location.origin);

        if (cursor) {
            url.searchParams.set("before", cursor);
        }

        const response = await fetch(url, {
            signal: controller.signal,
        });
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || "Cant load pins");
        }

        if (controller.signal.aborted) return;
        if (data.collection) {
            $("heading").textContent = data.collection.name;
        }
        if (data.children) {
            document.dispatchEvent(new CustomEvent("collection-feed", { detail: data }));
        }

        grid.append(...data.pins.map(renderPin));
        cursor = data.next_cursor;

        loadMore.hidden = !cursor;
        status.textContent = grid.childElementCount ? "" : "No pins yet";
    } catch (error) {
        if (!controller.signal.aborted) {
            status.textContent = error.message;
            loadMore.hidden = false;
        }
    } finally {
        if (feedController === controller) {
            feedController = null;
            loadMore.disabled = false;
        }
    }
}

let detailController = null;
let feedScroll = 0;

async function showRoute() {
    detailController?.abort();

    document.dispatchEvent(new CustomEvent("pin-change", {
        detail: null,
    }));


    const params = new URLSearchParams(location.search);
    const pinId = params.get("pin");
    const collectionId = params.get("collection");
    const myPins = collectionId === null
        && params.get("view") === "my-pins"

    const search = collectionId === null && !myPins
        ? (params.get("q") || "").trim()
        : "";
    $("query").value = search;

    const tag = collectionId === null && !myPins
        ? (params.get("tag") || "").trim()
        : "";

    const showingDetail = pinId !== null;
    const showingCollections = !showingDetail
        && params.get("view") === "collections";
    const showingFeed = !showingDetail && !showingCollections;

    if (!grid.hidden && !showingFeed) {
        feedScroll = window.scrollY;
    }

    $("detail").hidden = !showingDetail;
    $("collections-panel").hidden = !showingCollections;
    $("feed-heading").hidden = !showingFeed || (collectionId === null && !myPins && !search && !tag);
    grid.hidden = !showingFeed;
    $("sentinel").hidden = !showingFeed;

    if (showingFeed) {
        const url = new URL(
            collectionId !== null
                ? `/api/collections/${encodeURIComponent(collectionId)}/pins`
                : myPins
                    ? "/api/me/pins"
                    : "/api/pins",
            location.origin
        );

        if (collectionId === null && !myPins) {
            if (search) url.searchParams.set("q", search);
            if (tag) url.searchParams.set("tag", tag);
        }

        const path = url.pathname + url.search;

        if (feedPath !== path) {
            resetFeed();
            feedPath = path;
            feedScroll = 0;
            loadPins();
        }

        if (collectionId === null) {
            $("heading").textContent = myPins
                ? "My pins"
                : [
                    search ? `Search: ${search}` : "",
                    tag ? `Tag: ${tag}` : "",
                ].filter(Boolean).join(" | ");
        }

        requestAnimationFrame(() => window.scrollTo(0, feedScroll));
        return;
    }

    if (!showingDetail) {
        window.scrollTo(0, 0);
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

        document.dispatchEvent(new CustomEvent("pin-change", {
            detail: pin.id,
        }));

        document.dispatchEvent(new CustomEvent("pin-detail", {
            detail: pin,
        }));


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
    const params = new URLSearchParams(location.search);
    params.delete("pin");

    const query = params.toString();
    history.pushState(null, "", query ? `/?${query}` : "/");
    showRoute();
});

$("saved-pins").addEventListener("click", () => {
    history.pushState(null, "", "/?view=collections");
    showRoute();
})

$("search").addEventListener("submit", event => {
    event.preventDefault();
    const search = $("query").value.trim();
    const url = new URL("/", location.origin);
    const params = new URLSearchParams(location.search);

    if (!params.has("collection") && !params.has("view") && params.get("tag")) {
        url.searchParams.set("tag", params.get("tag"));
    }

    if (search) {
        url.searchParams.set("q", search);
    }

    history.pushState(null, "", url.pathname + url.search);
    showRoute();
});

document.addEventListener("account-change", () => {
    const params = new URLSearchParams(location.search);

    if (params.has("collection") || params.has("pin") || params.get("view") === "my-pins") {
        resetFeed();
        showRoute();
    }
});

document.addEventListener("collection-updated", event => {
    const params = new URLSearchParams(location.search);

    if (params.get("collection") === event.detail) {
        resetFeed();

        if (!params.has("pin")) {
            showRoute();
        }
    }
});

document.addEventListener("pin-updated", resetFeed);

window.addEventListener("popstate", showRoute);

const relatedSection = $("related-pins");
const relatedGrid = $("related-grid");
const relatedMore = $("related-more");
const relatedStatus = $("related-status");

let relatedController = null;
let relatedCursor = null;

function resetRelated() {
    relatedController?.abort();
    relatedController = null;
    relatedCursor = null;
    relatedGrid.replaceChildren();
    relatedSection.hidden = true;
    relatedMore.hidden = true;
    relatedMore.disabled = true;
    relatedStatus.textContent = "";
}

async function loadRelated(pinId) {
    if (relatedController) return;

    const controller = new AbortController();
    relatedController = controller;
    relatedMore.disabled = true;
    relatedStatus.textContent = "";

    try {
        const url = new URL(
            `/api/pins/${encodeURIComponent(pinId)}/related`,
            location.origin
        );

        if (relatedCursor) url.searchParams.set("before", relatedCursor);
        const response = await fetch(url, {signal: controller.signal});
        if (!response.ok) throw new Error("Can't load related pins");

        const result = await response.json();
        if (controller.signal.aborted) return;

        relatedGrid.append(...result.pins.map(renderPin));
        relatedcursor = result.next_cursor;
        relatedSection.hidden = !relatedGrid.childElementCount;
        relatedMore.hidden = !relatedCursor;
    } catch {
        if (!controller.signal.aborted){
            relatedSection.hidden = false;
            relatedStatus.textContent = "Can't load related pins";
            relatedMore.hidden = false;
        }
    } finally {
        if (relatedController === controller) {
            relatedController = null;
            relatedMore.disabled = false;
        }
    }
}

document.addEventListener("pin-change", resetRelated);

document.addEventListener("pin-detail", event => {
    if (event.detail.tags?.length) loadRelated(event.detail.id);
});

relatedMore.addEventListener("click", () => {
    const pinId = new URLSearchParams(location.search).get("pin");
    if (pinId) loadRelated(pinId);
});

setupMasonry(relatedGrid);
setupMasonry(grid);
showRoute();