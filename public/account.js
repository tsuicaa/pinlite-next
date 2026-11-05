(() => {
    const get = id => document.getElementById(id);

    const form = get("account-form");
    const password = get("account-password");
    const name = get("account-name");
    const accountButton = get("account-button");
    const submit = get("account-submit");
    const toggle = get("account-switch");
    const logout = get("account-logout");
    const status = get("account-status");

    let registering = false;

    let usageVersion = 0;

    async function loadUsage() {
        if (get("account-actions").hidden) return;

        const version = ++usageVersion;
        const display = get("account-usage");
        display.textContent = "Loading usage...";

        try {
            const usage = await api("me/usage");
            if (version !== usageVersion) return;

            const used = (usage.upload_bytes / 1024 / 1024).toFixed(1);
            const limit = (usage.upload_limit_bytes / 1024 / 1024).toFixed(0);

            display.textContent =
                `${usage.pins} / ${usage.pin_limit} pins created`
                + ` (${usage.pins_remaining} remaining)\n`
                + `${used} / ${limit} MB uploaded`;
        } catch (error) {
            if (version === usageVersion) {
                display.textContent = "Can't load usage";
            }
        }
    }

    function showUser(user) {
        const loggedIn = Boolean(user);

        usageVersion++;
        get("account-usage").textContent = "";

        form.hidden = loggedIn;
        get("account-actions").hidden = !loggedIn;
        get("account-display-name").textContent = user?.display_name || "";
        password.value = "";

        document.dispatchEvent(new CustomEvent("account-change", {
            detail: user,
        }));

        if (!get("account").hidden) {
            loadUsage();
        }
    }

    async function api(path, data) {
        const response = await fetch(`/api/${path}`, data === undefined ? {} : {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || "Request failed");
        }

        return result;
    }

    accountButton.addEventListener("click", () => {
        const panel = get("account");
        panel.hidden = !panel.hidden;

        if (!panel.hidden) {
            loadUsage();
        }
    });

    toggle.addEventListener("click", () => {
        registering = !registering;

        get("account-name").hidden = !registering;
        name.required = registering;
        password.autocomplete = registering
            ? "new-password"
            : "current-password";

        submit.textContent = registering ? "Create account" : "Sign in";
        toggle.textContent = registering
            ? "Use existing account"
            : "Create account";

        status.textContent = "";
    });

    form.addEventListener("submit", async event => {
        event.preventDefault();
        submit.disabled = true;
        toggle.disabled = true;
        status.textContent = registering ? "Creating account..." : "Signing in...";

        const data = {
            email: get("account-email").value,
            password: password.value,
        };

        if (registering) {
            data.display_name = name.value;
        }

        try {
            const result = await api(registering ? "register" : "login", data);
            showUser(result.user);
            status.textContent = "";
        } catch (error) {
            status.textContent = error.message;
        } finally {
            submit.disabled = false;
            toggle.disabled = false;
        }
    });

    logout.addEventListener("click", async () => {
        logout.disabled = true;

        try {
            await api("logout", {});
            showUser(null);
            status.textContent = "";
        } catch (error) {
            status.textContent = error.message;
        } finally {
            logout.disabled = false;
        }
    });

    api("me")
        .then(result => showUser(result.user))
        .catch(() => {
            status.textContent = "Could not check sign-in status";
        });

})();