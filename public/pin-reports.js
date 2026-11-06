(() => {
  const get = id => document.getElementById(id);
  const button = get("report-pin");
  const dialog = get("report-dialog");
  const form = get("report-form");
  const submit = form.querySelector('button[type="submit"]');
  const status = get("report-status");
  const error = get("report-error");

  let signedIn = false;
  let pin = null;

  function updateButton() {
    button.hidden = !signedIn || pin?.visibility !== "public";
  }

  document.addEventListener("account-change", event => {
    signedIn = Boolean(event.detail);
    if (!signedIn) dialog.close();
    updateButton();
  });

  document.addEventListener("pin-change", () => {
    pin = null;
    dialog.close();
    status.textContent = "";
    updateButton();
  });

  document.addEventListener("pin-detail", event => {
    pin = event.detail;
    updateButton();
  });

  button.addEventListener("click", () => {
    if (!signedIn || pin?.visibility !== "public") return;

    form.reset();
    error.textContent = "";
    dialog.showModal();
  });

  get("report-cancel").addEventListener("click", () => dialog.close());

  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (!signedIn || pin?.visibility !== "public" || submit.disabled) return;

    const target = pin;
    submit.disabled = true;
    error.textContent = "Sending report...";

    try {
      const response = await fetch(`/api/pins/${encodeURIComponent(target.id)}/report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reason: get("report-reason").value,
          note: get("report-note").value.trim(),
        }),
      });

      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Can't send report");

      if (pin !== target || !signedIn) return;

      dialog.close();
      status.textContent = result.already_reported
        ? "You've already reported this pin"
        : "Report sent for review";
    } catch (problem) {
      if (pin === target && dialog.open) error.textContent = problem.message;
    } finally {
      submit.disabled = false;
    }
  });
})();