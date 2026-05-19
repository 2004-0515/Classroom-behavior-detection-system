import test from "node:test";
import assert from "node:assert/strict";

import { closeDialogById, getDialogFocusableElements, openDialogById, trapDialogFocus } from "./dialogs.js";


function makeClassList(...initialValues) {
    const values = new Set(initialValues);
    return {
        add(value) {
            values.add(value);
        },
        remove(value) {
            values.delete(value);
        },
        contains(value) {
            return values.has(value);
        },
    };
}


function makeFocusable(name, setActiveElement, options = {}) {
    return {
        name,
        classList: makeClassList(...(options.hidden ? ["hidden"] : [])),
        focus() {
            setActiveElement(this);
        },
        hasAttribute(attribute) {
            return attribute === "disabled" ? Boolean(options.disabled) : false;
        },
        getAttribute(attribute) {
            if (attribute === "aria-hidden") {
                return options.ariaHidden ? "true" : null;
            }
            return null;
        },
    };
}


function makeDialogHarness() {
    let activeElement = null;
    const setActiveElement = (node) => {
        activeElement = node;
    };
    const opener = makeFocusable("opener", setActiveElement);
    const closeButton = makeFocusable("close", setActiveElement);
    const hiddenButton = makeFocusable("hidden", setActiveElement, { hidden: true });
    const disabledButton = makeFocusable("disabled", setActiveElement, { disabled: true });
    const dialog = {
        classList: makeClassList(),
        querySelectorAll() {
            return [closeButton, hiddenButton, disabledButton];
        },
        contains(node) {
            return node === closeButton || node === hiddenButton || node === disabledButton || node === dialog;
        },
        focus() {
            setActiveElement(dialog);
        },
    };
    const backdrop = {
        classList: makeClassList("hidden"),
        attributes: { "aria-hidden": "true" },
        querySelector(selector) {
            return selector === ".dialog-card" ? dialog : null;
        },
        setAttribute(name, value) {
            this.attributes[name] = value;
        },
    };
    const els = { modelDetailsModal: backdrop };
    return {
        els,
        opener,
        closeButton,
        dialog,
        backdrop,
        getActiveElement: () => activeElement,
        setActiveElement,
    };
}


test("getDialogFocusableElements filters hidden and disabled nodes", () => {
    const harness = makeDialogHarness();

    const focusable = getDialogFocusableElements(harness.dialog);

    assert.deepEqual(focusable, [harness.closeButton]);
});


test("openDialogById moves focus into the dialog immediately and on the next frame", () => {
    const harness = makeDialogHarness();
    const dialogOpeners = new Map();
    const frameCallbacks = [];
    let activeDialogId = null;
    harness.setActiveElement(harness.opener);

    openDialogById({
        els: harness.els,
        id: "modelDetailsModal",
        dialogOpeners,
        getActiveElement: harness.getActiveElement,
        setActiveDialogId: (value) => {
            activeDialogId = value;
        },
        requestAnimationFrame: (callback) => {
            frameCallbacks.push(callback);
        },
    });

    assert.equal(activeDialogId, "modelDetailsModal");
    assert.equal(harness.backdrop.classList.contains("hidden"), false);
    assert.equal(harness.backdrop.attributes["aria-hidden"], "false");
    assert.equal(harness.getActiveElement(), harness.closeButton);
    assert.equal(dialogOpeners.get("modelDetailsModal"), harness.opener);

    harness.setActiveElement(harness.opener);
    assert.equal(frameCallbacks.length, 1);
    frameCallbacks[0]();
    assert.equal(harness.getActiveElement(), harness.closeButton);
});


test("closeDialogById hides the dialog and returns focus to the opener", () => {
    const harness = makeDialogHarness();
    const dialogOpeners = new Map([["modelDetailsModal", harness.opener]]);
    let activeDialogId = "modelDetailsModal";
    harness.setActiveElement(harness.closeButton);

    closeDialogById({
        els: harness.els,
        id: "modelDetailsModal",
        dialogOpeners,
        getActiveDialogId: () => activeDialogId,
        setActiveDialogId: (value) => {
            activeDialogId = value;
        },
    });

    assert.equal(activeDialogId, null);
    assert.equal(harness.backdrop.classList.contains("hidden"), true);
    assert.equal(harness.backdrop.attributes["aria-hidden"], "true");
    assert.equal(harness.getActiveElement(), harness.opener);
    assert.equal(dialogOpeners.has("modelDetailsModal"), false);
});


test("trapDialogFocus wraps focus back into the dialog", () => {
    const harness = makeDialogHarness();
    const prevented = [];
    const event = {
        shiftKey: false,
        preventDefault() {
            prevented.push(true);
        },
    };

    trapDialogFocus(event, harness.dialog, () => harness.opener);

    assert.equal(prevented.length, 1);
    assert.equal(harness.getActiveElement(), harness.closeButton);
});
