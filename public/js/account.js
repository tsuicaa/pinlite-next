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
    const settings = get("account-settings-dialog");
    const settingsStatus = get("account-settings-status");
    const profileForm = get("account-profile-form");
    const passwordForm = get("account-password-form");
    const profileName = get("profile-display-name");


    let registering = false;

    let usageVersion = 0;

    async function loadUsage() {
        if (get("account-actions").hidden) return;

        const version = ++usageVersion;
        const display = get("account-usage");
        const status = get("account-usage-status");

        display.hidden = true;
        status.textContent = "Loading usage…";

        try {
            const usage = await api("me/usage");
            if (version !== usageVersion) return;

            const pins = get("account-pin-progress");
            pins.max = Math.max(1, usage.pin_limit);
            pins.value = usage.pins;
            get("account-pin-usage").textContent =
                `${usage.pins} / ${usage.pin_limit} pins (${usage.pins_remaining} remaining)`;

            const storage = get("account-storage-progress");
            storage.max = Math.max(1, usage.upload_limit_bytes);
            storage.value = usage.upload_bytes;

            const mib = bytes => (bytes / 1024 ** 2).toFixed(1);
            get("account-storage-usage").textContent =
                `${mib(usage.upload_bytes)} / ${mib(usage.upload_limit_bytes)} MiB`;

            status.textContent = "";
            display.hidden = false;
        } catch {
            if (version === usageVersion) {
                status.textContent = "Could not load usage.";
            }
        }
    }

    function showUser(user) {
        const loggedIn = Boolean(user);

        usageVersion++;
        get("account-usage").hidden = true;
        get("account-usage-status").textContent = "";

        form.hidden = loggedIn;
        get("account-actions").hidden = !loggedIn;
        get("account-display-name").textContent = user?.display_name || "";
        password.value = "";

        document.dispatchEvent(new CustomEvent("account-change", {
            detail: user,
        }));

    }

    async function api(path, data, method = "POST") {
        const response = await fetch(`/api/${path}`, data === undefined ? {} : {
            method,
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

    get("account-settings-open").addEventListener("click", () => {
        profileName.value = get("account-display-name").textContent;
        passwordForm.reset();
        settingsStatus.textContent = "";
        settings.showModal();
        loadUsage();
    });

    settings.addEventListener("close", () => passwordForm.reset());

    profileForm.addEventListener("submit", async event => {
        event.preventDefault();
        const button = profileForm.querySelector("button");
        button.disabled = true;
        settingsStatus.textContent = "";

        try {
            const { user } = await api("me/profile", {
                display_name: profileName.value.trim(),
            }, "PATCH");

            get("account-display-name").textContent = user.display_name;
            profileName.value = user.display_name;
            settingsStatus.textContent = "Display name saved";
        } catch (error) {
            settingsStatus.textContent = error.message;
        } finally {
            button.disabled = false;
        }
    });

    passwordForm.addEventListener("submit", async event => {
        event.preventDefault();

        const newPassword = get("settings-new-password").value;

        if (newPassword !== get("settings-confirm-password").value) {
            settingsStatus.textContent = "New passwords don't match";
            return;
        }

        const button = passwordForm.querySelector("button");
        button.disabled = true;
        settingsStatus.textContent = "";

        try {
            await api("me/password", {
                current_password: get("settings-current-password").value,
                new_password: newPassword,
            });

            passwordForm.reset();
            settingsStatus.textContent = "Password changed";
        } catch (error) {
            settingsStatus.textContent = error.message;
        } finally {
            button.disabled = false;
        }
    });

    api("me")
        .then(result => showUser(result.user))
        .catch(() => {
            status.textContent = "Could not check sign-in status";
        });

})();