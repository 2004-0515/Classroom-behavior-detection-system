export const DIALOG_FOCUSABLE_SELECTOR = [
    "button:not([disabled])",
    "[href]",
    "input:not([disabled])",
    "select:not([disabled])",
    "textarea:not([disabled])",
    "[tabindex]:not([tabindex='-1'])",
].join(",");


export function getDialogCard(els, id) {
    return els[id]?.querySelector(".dialog-card") || null;
}


export function getDialogFocusableElements(dialog) {
    if (!dialog) return [];
    return [...dialog.querySelectorAll(DIALOG_FOCUSABLE_SELECTOR)].filter(
        (node) => !node.hasAttribute("disabled") && !node.getAttribute("aria-hidden") && !node.classList.contains("hidden"),
    );
}


export function focusDialogById(els, id) {
    const dialog = getDialogCard(els, id);
    if (!dialog) return;
    const [firstFocusable] = getDialogFocusableElements(dialog);
    (firstFocusable || dialog).focus();
}


export function trapDialogFocus(event, dialog, getActiveElement = () => document.activeElement) {
    const focusable = getDialogFocusableElements(dialog);
    if (!focusable.length) {
        event.preventDefault();
        dialog.focus();
        return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const activeElement = getActiveElement();
    if (!dialog.contains(activeElement)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
        return;
    }
    if (!event.shiftKey && activeElement === last) {
        event.preventDefault();
        first.focus();
    } else if (event.shiftKey && activeElement === first) {
        event.preventDefault();
        last.focus();
    }
}


export function openDialogById({
    els,
    id,
    dialogOpeners,
    getActiveElement,
    setActiveDialogId,
    requestAnimationFrame,
}) {
    const node = els[id];
    const dialog = getDialogCard(els, id);
    if (!node || !dialog) return;
    const opener = getActiveElement();
    dialogOpeners.set(id, opener);
    node.classList.remove("hidden");
    node.setAttribute("aria-hidden", "false");
    setActiveDialogId(id);
    focusDialogById(els, id);
    requestAnimationFrame(() => focusDialogById(els, id));
}


export function closeDialogById({
    els,
    id,
    dialogOpeners,
    getActiveDialogId,
    setActiveDialogId,
}) {
    const node = els[id];
    if (!node) return;
    node.classList.add("hidden");
    node.setAttribute("aria-hidden", "true");
    if (getActiveDialogId() === id) {
        setActiveDialogId(null);
    }
    const opener = dialogOpeners.get(id);
    dialogOpeners.delete(id);
    if (opener && typeof opener.focus === "function") {
        opener.focus();
    }
}
