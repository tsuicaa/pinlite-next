(() => {
  const get = id => document.getElementById(id);

  const form = get("collection-form");
  const input = get("collection-name");
  const list = get("collections-list");
  const status = get("collections-status");
  const submit = form.querySelector("button");

  let accountVersion = 0;

  const save = get("save-pin");
  const folders = get("pin-folder");
  const saveStatus = get("pin-save-status");

  const subcollections = get("subcollections-list");
  const breadcrumb = get("collection-breadcrumb");
  let ownedCollections = [];


  let currentPin = null;
  let saving = false;

  let savedCollections = new Set();
  let checkingSaved = false;
  let membershipVersion = 0;

  async function loadSavedCollections() {
    const version = ++membershipVersion;
    savedCollections.clear();
    checkingSaved = Boolean(currentPin && !form.hidden);
    updateSaveControls();

    if (!checkingSaved) return;

    try {
      const response = await fetch(
        `/api/pins/${encodeURIComponent(currentPin)}/collections`
      );
      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.error || "Could notcheck saved status");
      }

      if (version !== membershipVersion) return;

      savedCollections = new Set(result.collection_ids);
    } catch (error) {
      if (version === membershipVersion) {
        saveStatus.textContent = error.message;
      }
    } finally {
      if (version === membershipVersion) {
        checkingSaved = false;
        updateSaveControls();
      }
    }

  }

  function updateSaveControls() {
    const available = folders.options.length > 0;
    const saved = savedCollections.has(folders.value);

    save.hidden = !available;
    get("pin-folder-control").hidden = !available;
    save.disabled = saving || checkingSaved || !currentPin;
    save.innerHTML = checkingSaved 
      ? "<i class='icon save'></i> Checking..." 
      : saved 
        ? "<i class='icon save'></i> Remove from" 
        : "<i class='icon save'></i> Save to";  
    save.className = checkingSaved ? "" : saved ? "red" : "green";
    folders.disabled = saving;
  }

  document.addEventListener("pin-change", event => {
    currentPin = event.detail;
    saveStatus.textContent = "";
    loadSavedCollections();
  });

  folders.addEventListener("change", () => {
    saveStatus.textContent = "";
    updateSaveControls();
  })

  function renderCollection(collection) {
    const item = document.createElement("li");
    item.className = "pin collection-card";
    item.dataset.parentId = collection.parent_id ?? "";
    const link = document.createElement("a");
    const preview = document.createElement("div");
    const title = document.createElement("h2");
    const controls = document.createElement("div");
    const rename = document.createElement("button");
    const remove = document.createElement("button");
    const sharing = document.createElement("button");
    sharing.type = "button";
    const share = document.createElement("button");
    share.type = "button";
    share.title = "Share";
    share.innerHTML= "<i class='icon share'></i>";
    const visibilityIcon = document.createElement("div");
    visibilityIcon.className = "panel inset visibility-icon";

    link.href = `/?collection=${encodeURIComponent(collection.id)}`;
    preview.className = "collection-preview";
 
    if (collection.previews?.length >= 4) {
      for (let index = 0; index < 4; index++) {
        const cell = document.createElement("div");
        const url = collection.previews?.[index];

        if (url) {
          const image = document.createElement("img");
          image.src = url;
          image.alt = "";
          image.loading = "lazy";
          image.decoding = "async";
          image.referrerPolicy = "no-referrer";
          cell.append(image);
        }

        preview.append(cell);
      }
    } else {
      const empty = document.createElement("div");
      empty.className = "empty-collection";
      preview.append(empty);
      preview.classList.add("empty");
    }

    share.addEventListener("click", async () => {
      if (collection.visibility !== "public") return;

      try {
        await navigator.clipboard.writeText(link.href);
        status.textContent = "Collection link copied";
      } catch {
        window.prompt("Copy this collection link:", link.href);
      }
    });

    function renderSharing() {
      sharing.innerHTML = collection.visibility === "public"
        ? "<i class='icon private'></i>"
        : "<i class='icon public'></i>";
      sharing.title = collection.visibility === "public"
        ? "Make private"
        : "Make public";
      share.hidden = collection.visibility !== "public";
      visibilityIcon.innerHTML = collection.visibility == "public"
        ? "<i class='icon public'></i>"
        : "<i class='icon private'></i>";
    }
  
    renderSharing();

    sharing.addEventListener("click", () => {
      const makingPublic = collection.visibility !== "public";

      if (makingPublic && !confirm(
        "Make this collection public? Anyone can view its public pins"
      )) return;

      update("PATCH", {
        visibility: makingPublic ? "public" : "private",
      });
    });

    title.textContent = collection.name;
    const hr = document.createElement("hr");
    link.append(preview, hr, title);

    rename.type = "button";
    rename.innerHTML = "<i class='icon rename'></i>";
    rename.title = "Rename"

    remove.type = "button";
    remove.innerHTML = "<i class='icon delete'></i>";
    remove.title = "Delete"
    remove.className = "red";

    controls.className = "collection-controls";
    controls.append(rename, " ", sharing, " ", share, " ", remove);
    item.append(visibilityIcon, link);

    if (collection.can_manage === false) return item;

    item.append(controls);

    async function update(method, data) {
      const version = accountVersion;
      rename.disabled = true;
      remove.disabled = true;
      status.textContent = method === "DELETE" ? "Deleting..." : "Updating...";

      try {
        const response = await fetch(`/api/collections/${collection.id}`, {
          method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        });
        const result = await response.json();

        if (!response.ok) {
          throw new Error(result.error || "Could not update collection");
        }

        if (version !== accountVersion) return;

        const option = [...folders.options].find(
          option => option.value === collection.id
        );

        if (method === "DELETE") {
          location.reload();
          return;
        } else {
          collection.name = result.collection.name;
          collection.visibility = result.collection.visibility;
          renderSharing();
          title.textContent = collection.name;

          if (option) {
            option.textContent = collection.name;
        }
      }

      updateSaveControls();
      status.textContent = list.children.length ? "" : "No collections yet";

      document.dispatchEvent(new CustomEvent("collection-updated", {
        detail: collection.id,
      }));
    } catch (error) {
      if (version === accountVersion) {
        status.textContent = error.message;
      }
    } finally {
      rename.disabled = false;
      remove.disabled = false;
    }
  }
    
  rename.addEventListener("click", () => {
    const entered = prompt("Collection name:", collection.name);
    if (entered === null) return;

    const name = entered.trim();

    if (!name || name.length > 200) {
      status.textContent = "Name must have 1-200 characters";
      return;
    }

    if (name !== collection.name) {
      update("PATCH", { name });
    }
  });

  remove.addEventListener("click", () => {
    const childCount = ownedCollections
      .filter(child => child.parent_id === collection.id).length;

    const children = childCount
      ? ` and ${childCount} sub-collection${childCount === 1 ? "" : "s"}`
      : "";

    if (confirm(
      `Delete "${collection.name}"${children}? The pins will be kept.`
    )) {
      update("DELETE", {});
    }
  });

  return item;
  }

  async function api(data) {
    const response = await fetch("/api/collections", data === undefined ? {} : {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });

    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.error || "Could not load collections");
    }

    return result;
  }

  document.addEventListener("account-change", async event => {
    const version = ++accountVersion;

    ownedCollections = [];
    folders.replaceChildren();
    saveStatus.textContent = "";
    updateSaveControls();

    list.replaceChildren();
    input.value = "";
    form.hidden = !event.detail;
    loadSavedCollections();
    submit.disabled = false;

    if (!event.detail) {
      status.textContent = "Sign in to manage your collections";
      return;
    }

    status.textContent = "Loading...";

    try {
      const result = await api();
      if (version !== accountVersion) return;

      ownedCollections = result.collections;

      const roots = ownedCollections.filter(
        collection => collection.parent_id === null
      );
      list.replaceChildren(...roots.map(renderCollection));

      const byId = new Map(
        ownedCollections.map(collection => [collection.id, collection])
      );
      folders.replaceChildren(...ownedCollections.map(collection => {
        const parent = byId.get(collection.parent_id);
        const label = parent ? `${parent.name} / ${collection.name}` : collection.name;
        return new Option(label, collection.id);
      }));

      updateSaveControls();
      status.textContent = roots.length ? "" : "No collections yet";
    } catch (error) {
      if (version === accountVersion) {
        status.textContent = error.message;
      }
    }
  });

  document.addEventListener("collection-feed", event => {
    const data = event.detail;

    subcollections.replaceChildren();
    breadcrumb.replaceChildren();
    subcollections.hidden = !data?.children.length;
    breadcrumb.hidden = !data;
    if (!data) return;

    function addLink(label, href) {
      const link = document.createElement("a");
      link.textContent = label;
      link.href = href;
      breadcrumb.append(link, " / ");
    }

    if (data.collection.can_manage) {
      addLink("Your collections", "/?view=collections");
    } else {
      addLink("Home", "/");
    }

    if (data.parent) {
      addLink(data.parent.name, `/?collection=${encodeURIComponent(data.parent.id)}`);
    }

    breadcrumb.append(data.collection.name);
    subcollections.append(...data.children.map(renderCollection));
  });

  form.addEventListener("submit", async event => {
    event.preventDefault();

    const name = input.value.trim();
    if (!name) return;

    const version = accountVersion;
    submit.disabled = true;
    status.textContent = "Creating...";

    try {
      const result = await api({ name });

      if (version !== accountVersion) return;

      list.prepend(renderCollection(result.collection));
      folders.prepend(new Option(result.collection.name, result.collection.id));
      folders.value = result.collection.id;
      updateSaveControls();
      input.value = "";
      status.textContent = "";
    } catch (error) {
      if (version === accountVersion) {
        status.textContent = error.message;
      }
    } finally {
      if (version === accountVersion) {
        submit.disabled = false;
      }
    }
  });

  save.addEventListener("click", async () => {
    if (!currentPin || !folders.value || saving || checkingSaved) return;

    const pinId = currentPin;
    const collectionId = folders.value;
    const version = accountVersion;
    const removing = savedCollections.has(collectionId);

    saving = true;
    updateSaveControls();
    saveStatus.textContent = removing ? "Removing..." : "Saving...";

    try {
      const response = await fetch (
        `/api/collections/${collectionId}/pins/${pinId}`,
        {
          method: removing ? "DELETE" : "PUT",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        }
      );

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.error || "Could not update collection");
      }

      if (version !== accountVersion) return;

      document.dispatchEvent(new CustomEvent("collection-updated", {
        detail: collectionId,
      }));

      if (currentPin === pinId) {
        if (removing) {
          savedCollections.delete(collectionId);
        } else {
          savedCollections.add(collectionId);
        }
        saveStatus.textContent = removing ? "Removed" : "Saved";
      }
    } catch (error) {
      if (version === accountVersion && currentPin === pinId) {
        saveStatus.textContent = error.message;
      }
    } finally {
      saving = false;
      updateSaveControls();
    }
  });
})();