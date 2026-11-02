(() => {
    const get = id => document.getElementById(id);

    const form = get("create-pin-form");
    const status = get("create-pin-status");
    const submit = form.querySelector('button[type="submit"]');
    const dialog = get("create-pin-dialog");
    const open = get("create-pin-open");
    const close = get("create-pin-close");
    const mode = get("new-pin-mode");
    const file = get("new-pin-file");
    const imageUrl = get("new-pin-image");
    const collection = get("new-pin-collection");
    const progress = get("create-pin-progress");
    const dropZone = get("drop-zone");
    const preview = get("preview");
    const clear = get("clear-btn");

    let creating = false;    

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

    function clearPreview() {
        for (const image of preview.querySelectorAll("img")) {
            URL.revokeObjectURL(image.src);
        }
        preview.replaceChildren();
    }

    function showSelectedFile() {
        clearPreview();

        const selected = file.files[0];
        if (!selected) return;

        const image = document.createElement("img");
        const filename = document.createElement("span");
        image.src = URL.createObjectURL(selected);
        image.alt = selected.name;
        filename.textContent = selected.name;

        preview.append(image, filename);
    }

    dropZone.addEventListener("dragover", event => {
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
    });

    dropZone.addEventListener("drop", event => {
        event.preventDefault();

        const files = event.dataTransfer.files;

        if (files.length !== 1) {
            status.textContent = "Only one image accepted";
            return;
        }

        const selected = files[0];

        if (!["image/jpeg", "image/png", "image/webp"].includes(selected.type)) {
            status.textContent = "Accepted formats are JPEG, PNG, WebP";
            return;
        }

        if (selected.size > 10 * 1024 * 1024) {
            status.textContent = "Maximum image size is 10 MB";
            return;
        }

        const transfer = new DataTransfer();
        transfer.items.add(selected);
        file.files = transfer.files;

        status.textContent = "";
        showSelectedFile();
    });

    file.addEventListener("change", showSelectedFile);

    clear.addEventListener("click", () => {
        file.value = "";
        clearPreview();
        status.textContent = "";
    });

    open.addEventListener("click", () => {
        collection.replaceChildren(
            new Option("No collection", ""),
            ...[...get("pin-folder").options].map(option =>
            new Option(option.textContent, option.value)
            )
        );

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
        clearPreview();
        updateMode();
        form.hidden = !event.detail;
        submit.disabled = false;
        status.textContent = event.detail ? "" : "Sign in to create a pin";
        open.hidden = !event.detail;
        progress.hidden = true;

        if (!event.detail) {
            dialog.close();
        }
    });

    async function convertImage(file) {
        if (
            file.type === "image/webp"
            || typeof createImageBitmap !== "function"
        ) {
            return file;
        }

        const bitmap = await createImageBitmap(file);
        const canvas = document.createElement("canvas");

        try {
            if (bitmap.width * bitmap.height > 20_000_000) {
            throw new Error("Image must be at most 20 megapixels");
            }

            canvas.width = bitmap.width;
            canvas.height = bitmap.height;

            const context = canvas.getContext("2d");
            if (!context) return file;

            context.drawImage(bitmap, 0, 0);

            const blob = await new Promise(resolve => {
            canvas.toBlob(resolve, "image/webp", 0.85);
            });

            if (!blob || blob.type !== "image/webp") return file;

            return new File([blob], "image.webp", { type: "image/webp" });
        } finally {
            bitmap.close();
            canvas.width = canvas.height = 0;
        }
        }

        function uploadImage(body, onProgress, onFinishing) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();

            xhr.upload.onprogress = event => {
            onProgress(event.lengthComputable
                ? Math.round(event.loaded / event.total * 100)
                : null);
            };

            xhr.upload.onload = onFinishing;

            xhr.onload = () => {
            if (xhr.status === 413) {
                reject(new Error("Upload is too large."));
                return;
            }

            const result = xhr.response;

            if (xhr.status < 200 || xhr.status >= 300 || !result) {
                reject(new Error(result?.error || "Can't upload image"));
                return;
            }

            resolve(result);
            };

            xhr.onerror = () => reject(new Error("Upload connection failed"));
            xhr.onabort = () => reject(new Error("Upload cancelled"));

            xhr.open("POST", "/api/uploads");
            xhr.responseType = "json";
            xhr.send(body);
        });
        }

    form.addEventListener("submit", async event => {
        event.preventDefault();
        if (creating) return;

        const uploading = mode.value === "upload";
        const selectedFile = file.files[0];

        if (uploading && (!selectedFile || selectedFile.size > 10 * 1024 * 1024)) {
            status.textContent = "Maximum image size is 10 MB";
            return;
        }

        const version = accountVersion;
        const title = get("new-pin-title").value.trim();
        const visibility = get("new-pin-visibility").value;
        const collectionId = collection.value;
        const externalUrl = imageUrl.value.trim();

        creating = true;
        submit.disabled = true;
        progress.hidden = false;
        progress.removeAttribute("value");

        try {
            let result;

            if (uploading) {
            status.textContent = "Reticulating Splines...";

            const prepared = await convertImage(selectedFile);
            if (version !== accountVersion) return;

            if (prepared.size > 10 * 1024 * 1024) {
                throw new Error("Maximum image size is 10 MB");
            }

            const body = new FormData();
            body.append("image", prepared);
            body.append("title", title);
            body.append("visibility", visibility);
            body.append("collection_id", collectionId);

            status.textContent = "Uploading...";

            result = await uploadImage(
                body,
                percent => {
                if (version !== accountVersion) return;

                if (percent === null) {
                    progress.removeAttribute("value");
                    status.textContent = "Uploading...";
                } else {
                    progress.value = percent;
                    status.textContent = `Uploading: ${percent}%`;
                }
                },
                () => {
                if (version !== accountVersion) return;

                progress.removeAttribute("value");
                status.textContent = "Finishing...";
                }
            );
            } else {
            status.textContent = "Creating...";

            const response = await fetch("/api/pins", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                title,
                image_url: externalUrl,
                visibility,
                collection_id: collectionId,
                }),
            });

            if (!response.headers.get("Content-Type")?.includes("application/json")) {
                throw new Error("Can't create pin");
            }

            result = await response.json();

            if (!response.ok) {
                throw new Error(result.error || "Can't create pin");
            }
            }

            if (version !== accountVersion) return;

            location.href = `/?view=my-pins&pin=${encodeURIComponent(result.pin.id)}`;
        } catch (error) {
            if (version === accountVersion) {
            status.textContent = error.message;
            }
        } finally {
            creating = false;

            if (version === accountVersion) {
            submit.disabled = false;
            progress.hidden = true;
            }
        }
        });
})();