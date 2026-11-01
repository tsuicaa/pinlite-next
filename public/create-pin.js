(() => {
    const get = id => document.getElementById(id);

    const form = get("create-pin-form");
    const status = get("create-pin-status");
    const submit = form.querySelector("button");
    const dialog = get("create-pin-dialog");
    const open = get("create-pin-open");
    const close = get("create-pin-close");

    open.addEventListener("click", () => {
    status.textContent = "";
    dialog.showModal();
    });

    close.addEventListener("click", () => {
    dialog.close();
    });

    let accountVersion = 0;

    document.addEventListener("account-change", event => {
        accountVersion++;
        form.reset();
        form.hidden = !event.detail;
        submit.disabled = false;
        status.textContent = event.detail ? "" : "Sign in to create a pin";
        open.hidden = !event.detail;

        if (!event.detail) {
            dialog.close();
        }
    });

    form.addEventListener("submit", async event => {
        event.preventDefault();

        const version = accountVersion;
        submit.disabled = true;
        status.textContent = "Creating…";

        try {
        const response = await fetch("/api/pins", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
            title: get("new-pin-title").value.trim(),
            image_url: get("new-pin-image").value.trim(),
            visibility: get("new-pin-visibility").value,
            }),
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || "Could not create pin");
        }

        if (version !== accountVersion) return;

        location.href = `/?view=my-pins&pin=${encodeURIComponent(result.pin.id)}`;
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