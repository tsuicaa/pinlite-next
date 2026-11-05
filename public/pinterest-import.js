(() => {
    const get = id => document.getElementById(id);
    const form = get("pinterest-preview-form");
    const input = get("pinterest-board-url");
    const submit = form.querySelector("button");
    const status = get("pinterest-preview-status");
    const result = get("pinterest-preview-result");

    let request = null;

    document.addEventListener("account-change", event => {
        request?.abort();
        request = null;
        form.hidden = !event.detail;
        result.hidden = true;
        submit.disabled = false;
        status.textContent = "";    
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
            if (controller.signal.aborted) return;
            if (!response.ok) {
                throw new Error(board.error || "Couldn't preview the board");
            }

            get("pinterest-preview-name").textContent = board.name;
            get("pinterest-preview-count").textContent =
                `Pinterest reports ${board.reported_pin_count ?? "an unknown number of"} pins. `
                + `First page: ${board.first_page_pin_count} found`;
            
            const sections = board.sections.map(section => {
                const item = document.createElement("li");
                item.textContent = section.name;
                return item;
            });

            get("pinterest-preview-sections").replaceChildren(...sections);

            status.textContent = board.has_more_sections
                ? "Showing the first page of section"
                : sections.length ? "" : "Pinterest returned no sections"
            
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
})();