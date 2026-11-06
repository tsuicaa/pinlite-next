(() => {
  const get = id => document.getElementById(id);

  const actions = get("pin-actions");
  const form = get("pin-edit-form");
  const title = get("pin-edit-title");
  const description = get("pin-edit-description");
  const visibility = get("pin-edit-visibility");
  const status = get("pin-actions-status");
  const tags = get("pin-edit-tags");

  let pin = null;
  let busy = false;

  function setEditing(editing) {
    get("detail-title").hidden = editing;
    get("detail-description").hidden = editing;
    get("pin-visibility").hidden = editing;

    title.hidden = !editing;
    description.hidden = !editing;
    visibility.hidden = !editing;

    get("pin-edit").hidden = editing;
    get("pin-delete").hidden = editing;
    get("pin-edit-save").hidden = !editing;
    get("pin-edit-cancel").hidden = !editing;
    get("detail-tags").hidden = editing;
    get("pin-edit-tags-field").hidden = !editing;
  }

  function render() {
    const names = pin.tags || [];
    get("detail-title").textContent = pin.title;
    get("detail-description").textContent = pin.description;
    get("pin-visibility").classList.add(pin.moderation_hold
      ? "delete"
      : pin.visibility);
    get("pin-visibility").title = pin.moderation_hold
      ? "Private - moderation hold"
      : pin.visibility;

    visibility.querySelector('option[value="public"]').disabled =
      Boolean(pin.moderation_hold);

    get("detail-tags").replaceChildren(
      ...names.map(name => {
        const link = document.createElement("a");
        link.href = `/?tag=${encodeURIComponent(name)}`;
        link.textContent = name;
        return link;
      })
    );

    title.value = pin.title;
    description.value = pin.description;
    visibility.value = pin.visibility;
    tags.value = names.join(", ");
  }

  document.addEventListener("pin-change", () => {
    pin = null;
    actions.hidden = true;
    get("pin-visibility-row").hidden = true;
    setEditing(false);
    status.textContent = "";
    get("detail-tags").textContent = "";
  });

  document.addEventListener("pin-detail", event => {
    pin = event.detail;
    actions.hidden = !pin.can_edit;
    get("pin-visibility-row").hidden = !pin.can_edit;
    render();
    setEditing(false);
  });

  get("pin-edit").addEventListener("click", () => {
    render();
    status.textContent = "";
    setEditing(true);
    title.focus();
  });

  get("pin-edit-cancel").addEventListener("click", () => {
    render();
    setEditing(false);
    status.textContent = "";
    get("pin-edit").focus();
  });

  async function update(method, data) {
    if (!pin?.can_edit || busy) return;

    const current = pin;
    busy = true;
    actions.querySelectorAll("button").forEach(button => {
      button.disabled = true;
    });
    status.textContent = method === "DELETE" ? "Deleting..." : "Saving...";

    try {
      const response = await fetch(`/api/pins/${current.id}`, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.error || "Could not update pin");
      }

      if (pin !== current) return;

      if (method === "DELETE") {
        location.href = "/?view=my-pins";
        return;
      }

      Object.assign(pin, result.pin);
      render();
      setEditing(false);
      status.textContent = "Saved";

      document.dispatchEvent(new Event("pin-updated"));
      get("pin-edit").focus();
    } catch (error) {
      if (pin === current) {
        status.textContent = error.message;
      }
    } finally {
      busy = false;
      actions.querySelectorAll("button").forEach(button => {
        button.disabled = false;
      });
    }
  }

  form.addEventListener("submit", event => {
    event.preventDefault();
    update("PATCH", {
      title: title.value.trim(),
      description: description.value,
      visibility: visibility.value,
      tags: tags.value.split(",").map(tag => tag.trim()).filter(Boolean),
    });
  });

  get("pin-delete").addEventListener("click", () => {
    if (pin && confirm(`Delete "${pin.title}" from PinLite and all collections?`)) {
      update("DELETE", {});
    }
  });
})();