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
    save.disabled = saving || checkingSaved || !currentPin || saved;
    save.textContent = checkingSaved ? "Checking..." : saved ? "Saved" : "Save";  
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
    const link = document.createElement("a");

    link.href = `/?collection=${encodeURIComponent(collection.id)}`;
    link.textContent = collection.name;
    item.append(link);
    
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
    if (!currentPin || !folders.value || saving || checkingSaved
      || savedCollections.has(folders.value)
    ) return;

    const pinId = currentPin;
    const collectionId = folders.value;
    const version = accountVersion;

    saving = true;
    updateSaveControls();
    saveStatus.textContent = "Saving...";

    try {
      const response = await fetch (
        `/api/collections/${collectionId}/pins/${pinId}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        }
      );

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.error || "Could not save pin");
      }

      if (version === accountVersion && currentPin === pinId) {
        savedCollections.add(collectionId);
        saveStatus.textContent = "Saved";
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