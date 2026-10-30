(() => {
  const get = id => document.getElementById(id);

  const form = get("collection-form");
  const input = get("collection-name");
  const list = get("collections-list");
  const status = get("collections-status");
  const submit = form.querySelector("button");

  let accountVersion = 0;

  function renderCollection(collection) {
    const item = document.createElement("li");
    item.textContent = collection.name;
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

    list.replaceChildren();
    input.value = "";
    form.hidden = !event.detail;
    submit.disabled = false;

    if (!event.detail) {
      status.textContent = "Sign in to manage your collections";
      return;
    }

    status.textContent = "Loading…";

    try {
      const result = await api();

      if (version !== accountVersion) return;

      list.replaceChildren(...result.collections.map(renderCollection));
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
    status.textContent = "Creating…";

    try {
      const result = await api({ name });

      if (version !== accountVersion) return;

      list.prepend(renderCollection(result.collection));
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
})();