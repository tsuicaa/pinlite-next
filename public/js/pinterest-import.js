(() => {
    const get = id => document.getElementById(id);
    const form = get("pinterest-preview-form");
    const input = get("pinterest-board-url");
    const submit = form.querySelector("button");
    const status = get("pinterest-preview-status");
    const result = get("pinterest-preview-result");
    let request = null;
    const start = get("pinterest-import-start");
    const stop = get("pinterest-import-stop");
    let preview = null;
    let stopping = false;
    const dialog = get("pinterest-import-dialog");
    const open = get("pinterest-import-open");
    const close = get("pinterest-import-close");
    open.addEventListener("click", () => dialog.showModal());
    close.addEventListener("click", () => {
        if (stop.hidden) dialog.close();
    });

    dialog.addEventListener("cancel", event => {
        if (!stop.hidden) event.preventDefault();
    });

    const progress = get("pinterest-import-progress");

    function resetImportDialog() {
        request?.abort();
        request = null;
        preview = null;
        stopping = false;

        form.reset();
        status.textContent = "";
        result.hidden = true;
        get("pinterest-preview-name").textContent = "";
        get("pinterest-preview-count").textContent = "";
        get("pinterest-preview-sections").replaceChildren();

        submit.disabled = false;
        start.disabled = false;
        stop.disabled = false;
        stop.hidden = true;
        progress.hidden = true;
        progress.removeAttribute("value");
    }

    dialog.addEventListener("close", resetImportDialog);

    document.addEventListener("account-change", event => {
        resetImportDialog();
        form.hidden = !event.detail;
        open.hidden = !event.detail;

        if (!event.detail) dialog.close();
    });

    async function readImportResult(response, onProgress) {
        if (!response.headers.get("Content-Type")?.includes("application/x-ndjson")) {
            return response.json();
        }

        const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
        let buffer = "";

        try {
            while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += value;
            const lines = buffer.split("\n");
            buffer = lines.pop();

            for (const line of lines) {
                if (!line) continue;
                const message = JSON.parse(line);

                if (message.error) throw new Error(message.error);
                if (message.result) return message.result;
                if (typeof message.uploaded === "number") onProgress(message.uploaded);
            }
            }

            throw new Error("The import ended before the server confirmed the save");
        } finally {
            reader.releaseLock();
        }
    }

    form.addEventListener("submit", async event => {
        event.preventDefault();
        if (request) return;

        const controller = new AbortController();
        request = controller;
        progress.removeAttribute("value");
        progress.hidden = false;
        submit.disabled = true;
        result.hidden = true;
        status.textContent = "Checking Pinterest...";

        try {
            const response = await fetch("/api/import/pinterest/preview", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url: input.value.trim() }),
                signal: controller.signal,
            });

            const board = await response.json();
            if (controller.signal.aborted) return;
            preview = null;
            if (!response.ok) {
                throw new Error(board.error || "Couldn't preview the board");
            }

            get("pinterest-preview-name").textContent = board.name;
            get("pinterest-preview-count").textContent =
                `${board.reported_pin_count ?? "uknown"} pins. `
                + `(first page: ${board.first_page_pin_count} pins)`;

            const sections = board.sections.map(section => {
                const item = document.createElement("li");
                const label = document.createElement("label");
                const checkbox = document.createElement("input");

                checkbox.type = "checkbox";
                checkbox.value = section.id;
                checkbox.checked = true;

                label.append(checkbox, ` ${section.name} (${section.pin_count ?? "unknown"})`);
                item.append(label);
                return item;
            });

            get("pinterest-preview-sections").replaceChildren(...sections);

            status.textContent = board.has_more_sections
                ? "Showing the first page of section"
                : sections.length ? "" : "Pinterest returned no sections"

            preview = board;
            result.hidden = false;
        } catch (error) {
            if (!controller.signal.aborted) {
                status.textContent = error.message;
            }
        } finally {
            if (request === controller) {
                request = null;
                submit.disabled = false;
                progress.hidden = true;
            }
        }
    });

    stop.addEventListener("click", () => {
        stopping = true;
        stop.disabled = true;
        status.textContent = "Stopping after the current page...";
    });

    start.addEventListener("click", async () => {
        if (!preview || request) return;

        const board = preview;


        function updateProgress(count) {
            if (hasTotal) progress.value = Math.min(count, total);
        }

        const selectedIds = new Set(
            [...get("pinterest-preview-sections").querySelectorAll("input:checked")]
                .map(checkbox => checkbox.value)
        );
        const selectedSections = board.sections.filter(section => selectedIds.has(section.id));

        const options = {
            url: board.url,
            pin_visibility: get("pinterest-publish-pins").checked
                ? "public"
                : "private",
            use_section_tags: get("pinterest-use-section-tags").checked,
        };

        if (board.sections.length && selectedSections.length === 0) {
            status.textContent = "Select at least one section to import";
            return;
        }

        const controller = new AbortController();
        request = controller;
        progress.hidden = false;
        stopping = false;

        const feeds = [...selectedSections];
        if (selectedSections.length === board.sections.length) {
            feeds.push({ id: null, name: "Main board" });
        }

        const fullBoard = selectedSections.length === board.sections.length;
        const sectionCounts = selectedSections.map(section => section.pin_count);
        const total = fullBoard
            ? Number(board.reported_pin_count)
            : sectionCounts.every(count =>
                count != null && Number.isSafeInteger(Number(count)) && Number(count) >= 0
            )
                ? sectionCounts.reduce((sum, count) => sum + Number(count), 0)
                : 0;
        const hasTotal = Number.isSafeInteger(total) && total > 0;

        if (hasTotal) {
            progress.max = total;
            progress.value = 0;
        } else {
            progress.removeAttribute("value");
        }

        let added = 0;
        let linked = 0;
        let failedImages = 0;
        let fetched = 0;
        let reason = "Import pass finished";

        submit.disabled = true;
        start.disabled = true;
        stop.disabled = false;
        stop.hidden = false;

        try {
            importFeeds:
            for (const feed of feeds) {
                let cursor = null;
                const seen = new Set();

                while (true) {
                    if (stopping || controller.signal.aborted) break importFeeds;

                    seen.add(cursor);
                    status.textContent = `Importing ${feed.name}... ${added} pins saved`;

                    const response = await fetch("/api/import/pinterest/page", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            ...options,
                            section_id: feed.id,
                            cursor,
                        }),
                        signal: controller.signal,
                    });

                    if (response.status === 429) {
                        const seconds = Number(response.headers.get("Retry-After")) || 60;
                        status.textContent = `Waiting ${seconds} seconds before the next page...`;

                        await new Promise(resolve => setTimeout(resolve, (seconds + 1) * 1000));
                        seen.delete(cursor);
                        continue;
                    }

                    const page = await readImportResult(response, uploaded => {
                    if (request !== controller || stopping) return;

                    updateProgress(fetched + uploaded);

                    status.textContent =
                        `Importing ${feed.name}... ${added} pins saved | ${uploaded} images uploaded`;
                    });

                    if (!response.ok) {
                        throw new Error(page.error || "Could not import this page");
                    }

                    added += page.added;
                    fetched += page.fetched ?? 0;
                    updateProgress(fetched);
                    linked += page.linked;
                    failedImages += page.failed_images ?? 0;

                    if (page.quota_reached) {
                        reason = "Pin or storage allowance reached";
                        break importFeeds;
                    }

                    cursor = page.next_cursor;
                    if (!cursor) break;
                    
                    if (seen.has(cursor)) {
                        reason = `Pinterest repeated a page in ${feed.name}`;
                        break importFeeds;
                    }
                } 
            }

            if (stopping) reason = "Import stopped";
        } catch (error) {
            reason = error.message;
        } finally {
            if (request === controller) {
                const sectionNote = board.has_more_sections
                    ? " Only the previewed sections were processed"
                    : "";


                const reported = board.reported_pin_count;
                const shortFeed = reason === "Import pass finished"
                    && board.sections.length === 0
                    && !board.has_more_sections
                    && reported != null
                    && fetched < Number(reported);

                if (shortFeed) reason = "Partial import";

                status.innerHTML =
                    `<p><b>${reason}</b></p>`
                    + `<p>Created <b>${added} pins</b> and added <b>${linked} collection memberships</b></p>`
                    + `<p><small>${sectionNote} (Pinterest may return only part of a board. Refresh to see your collections)</small></p>`
                    + `<p>Received ${fetched} supported pin entries. Pinterest reports ${reported ?? "an unknown number of"} pins.</p>`
                    + `<p>${failedImages} images could not be saved</p>`;

                request = null;
                submit.disabled = false;
                start.disabled = false;
                stop.hidden = true;
                progress.hidden = true;
            }
        }
    });
})();