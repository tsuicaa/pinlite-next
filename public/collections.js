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
    save.textContent = checkingSaved ? "Checking..." : saved ? "Remove" : "Save";  
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
    const link = document.createElement("a");
    const preview = document.createElement("div");
    const title = document.createElement("h2");
    const controls = document.createElement("div");
    const rename = document.createElement("button");
    const remove = document.createElement("button");

    link.href = `/?collection=${encodeURIComponent(collection.id)}`;
    preview.className = "collection-preview";
    preview.setAttribute("aria-hidden", "true");
 
    if (collection.previews.length >= 4) {
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

    title.textContent = collection.name;
    link.append(preview, title);

    rename.type = "button";
    rename.textContent = "Rename";

    remove.type = "button";
    remove.textContent = "Delete";
    remove.className = "red";

    controls.className = "collection-controls";
    controls.append(rename, " ", remove);
    item.append(link, controls);

    async function update(method, data) {
      const version = accountVersion;
      rename.disabled = true;
      remove.disabled = true;
      status.textContent = method === "DELETE" ? "Deleting..." : "Renaming...";

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
          item.remove();
          option?.remove();
          savedCollections.delete(collection.id);
        } else {
          collection.name = result.collection.name;
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
    if (confirm(`Delete "${collection.name}"? This does not delete the pins.`)) {
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

      list.replaceChildren(...result.collections.map(renderCollection));
      folders.replaceChildren(...result.collections.map(collection =>
        new Option(collection.name, collection.id)
      ));
      updateSaveControls();

      status.textContent = result.collections.length
        ? ""
        : "No collections yet";
    } catch (error) {
      if (version === accountVersion) {
        status.textContent = error.message;
      }
    }
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