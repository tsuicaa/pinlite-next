(() => {
    const get = id => document.getElementById(id);

    const form = get("create-pin-form");
    const status = get("create-pin-status");
    const submit = form.querySelector("button");
    const dialog = get("create-pin-dialog");
    const open = get("create-pin-open");
    const close = get("create-pin-close");
    const mode = get("new-pin-mode");
    const file = get("new-pin-file");
    const imageUrl = get("new-pin-image");

    function updateMode() {
        const uploading = mode.value === "upload";
        get("new-pin-upload-field").hidden = !uploading;
        get("new-pin-url-field").hidden = uploading;

        file.disabled = !uploading;
        file.required = uploading;
        imageUrl.disabled = uploading;
        imageUrl.required = !uploading;
    }

    mode.addEventListener("change", updateMode);
    updateMode();

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
        updateMode();
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

        const uploading = mode.value === "upload";
        const selectedFile = file.files[0];

        if (uploading && (!selectedFile || selectedFile.size > 10 * 1024 * 1024)) {
            status.textContent = "Maximum image size is 10 MB";
            return;
        }

        const version = accountVersion;
        const title = get("new-pin-title").value.trim();
        const visibility = get("new-pin-visibility").value;

        let endpoint;
        let options;

        if (uploading) {
            const body = new FormData();
            body.append("image", selectedFile);
            body.append("title", title);
            body.append("visibility", visibility);

            endpoint = "/api/uploads";
            options = { method: "POST", body };
        } else {
            endpoint = "/api/pins";
            options = {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                title,
                image_url: imageUrl.value.trim(),
                visibility,
            }),
            };
        }

        submit.disabled = true;
        status.textContent = uploading ? "Reticulating Splines..." : "Creating...";

        try {
            const response = await fetch(endpoint, options);

            if (response.status === 413) {
            throw new Error("Upload is too large.");
            }

            if (!response.ok && !response.headers.get("Content-Type")?.includes("application/json")) {
            throw new Error("Can't create pin. Try again.");
            }

            const result = await response.json();

            if (!response.ok) {
            throw new Error(result.error || "Can't create pin.");
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