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
    close.addEventListener("click", () => dialog.close());

    dialog.addEventListener("cancel", event => {
        if (!stop.hidden) event.preventDefault();
    });

    document.addEventListener("account-change", event => {
        request?.abort();
        request = null;
        form.hidden = !event.detail;
        result.hidden = true;
        submit.disabled = false;
        status.textContent = "";
        preview = null;
        stopping = false;
        start.disabled = false;
        stop.hidden = true;
        open.hidden = !event.detail;    
        close.disabled = false;

        if (!event.detail) dialog.close();
    });

    form.addEventListener("submit", async event => {
        event.preventDefault();
        if (request) return;

        const controller = new AbortController();
        request = controller;
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
            preview = null;
            if (controller.signal.aborted) return;
            if (!response.ok) {
                throw new Error(board.error || "Couldn't preview the board");
            }

            get("pinterest-preview-name").textContent = board.name;
            get("pinterest-preview-count").textContent =
                `${board.reported_pin_count ?? "uknown"} pins. `
                + `(first page: ${board.first_page_pin_count} pins)`;

            const sections = board.sections.map(section => {
                const item = document.createElement("li");
                item.textContent = section.name;
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
        const controller = new AbortController();
        request = controller;
        stopping = false;

        const options = {
            url: board.url,
            pin_visibility: get("pinterest-publish-pins").checked
                ? "public"
                : "private",
            use_section_tags: get("pinterest-use-section-tags").checked,
        };

        const feeds = [
            ...board.sections,
            { id: null, name: "Main board" },
        ];

        let added = 0;
        let linked = 0;
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
                    status.textContent = `Importing ${feed.name}… ${added} new pins so far.`;

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

                    const page = await response.json();

                    if (!response.ok) {
                        throw new Error(page.error || "Could not import this page");
                    }

                    added += page.added;
                    linked += page.linked;

                    if (page.quota_reached) {
                        reason = "Pin allowance reached.";
                        break importFeeds;
                    }

                    cursor = page.next_cursor;
                    if (!cursor) break;
                    
                    if (seen.has(cursor)) {
                        reason = `Pinterest repeated a page in ${feed.name}.`;
                        break importFeeds;
                    }
                } 
            }

            if (stopping) reason = "Import stopped.";
        } catch (error) {
            reason = error.message;
        } finally {
            if (request === controller) {
                const sectionNote = board.has_more_sections
                    ? " Only the previewed sections were processed"
                    : "";

                status.textContent =
                    `${reason} Created ${added} pins and added ${linked} collection memberships`
                    + sectionNote
                    + " Pinterest may return only part of a board. Refresh to see your collections.";

                request = null;
                submit.disabled = false;
                start.disabled = false;
                stop.hidden = true;
            }
        }
    });
})();