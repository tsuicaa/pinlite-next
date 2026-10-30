(() => {
    const get = id => document.getElementById(id);

    const form = get("account-form");
    const password = get("account-password");
    const name = get("account-name");
    const submit = get("account-submit");
    const toggle = get("account-switch");
    const logout = get("account-logout");
    const status = get("account-status");

    let registering = false;

    function showUser(user) {
        form.hidden = Boolean(user);
        get("account-user").hidden = !user;
        get("account-display-name").textContent = user?.display_name || "";
        password.value = "";
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

    toggle.addEventListener("click", () => {
        registering = !registering;

        get("account-name-field").hidden = !registering;
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