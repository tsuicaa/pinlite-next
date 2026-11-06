(() => {
    const pinSize = document.getElementById("pin-size");
    const pinSizeKey = "pinlite-next.pin-size";
    const sizes = ["default", "compact", "large"];

    try {
    const saved = localStorage.getItem(pinSizeKey);
    if (sizes.includes(saved)) pinSize.value = saved;
    } catch {}

    function applyPinSize() {
    document.documentElement.dataset.pinSize = pinSize.value;
    document.dispatchEvent(new Event("pin-size-change"));
    }

    applyPinSize();

    pinSize.addEventListener("change", () => {
    applyPinSize();

    try {
        localStorage.setItem(pinSizeKey, pinSize.value);
    } catch {}
    });

    document.getElementById("settings").addEventListener("click", () => {
        document.getElementById("settings-dialog").showModal();
    });
})();