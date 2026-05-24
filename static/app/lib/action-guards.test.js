import test from "node:test";
import assert from "node:assert/strict";

import { createActionRegistry, createVersionRegistry } from "./action-guards.js";

test("createActionRegistry blocks duplicate actions and only notifies busy once", () => {
    const notifications = [];
    const registry = createActionRegistry((message) => notifications.push(message));

    const token = registry.acquire("history-export", "正在导出...");
    assert.equal(typeof token, "symbol");
    assert.equal(registry.isActive("history-export"), true);

    assert.equal(registry.acquire("history-export", "正在导出..."), null);
    assert.equal(registry.acquire("history-export", "正在导出..."), null);
    assert.deepEqual(notifications, ["正在导出..."]);

    assert.equal(registry.release("history-export", token), true);
    assert.equal(registry.isActive("history-export"), false);

    const nextToken = registry.acquire("history-export", "正在导出...");
    assert.equal(typeof nextToken, "symbol");
    assert.notEqual(nextToken, token);
});

test("createActionRegistry ignores mismatched release tokens", () => {
    const registry = createActionRegistry();
    const token = registry.acquire("detect-submit");

    assert.equal(registry.release("detect-submit", Symbol("other")), false);
    assert.equal(registry.isActive("detect-submit"), true);
    assert.equal(registry.release("detect-submit", token), true);
    assert.equal(registry.isActive("detect-submit"), false);
});

test("createActionRegistry clears a single action without touching others", () => {
    const registry = createActionRegistry();
    const detectToken = registry.acquire("detect-submit");
    const exportToken = registry.acquire("history-export");

    registry.clear("detect-submit");

    assert.equal(registry.isActive("detect-submit"), false);
    assert.equal(registry.isActive("history-export"), true);
    assert.equal(registry.release("history-export", exportToken), true);
    assert.equal(registry.release("detect-submit", detectToken), false);
});

test("createVersionRegistry tracks per-key staleness", () => {
    const registry = createVersionRegistry(["task", "history"]);

    assert.equal(registry.capture("task"), 0);
    const taskToken = registry.bump("task");
    assert.equal(taskToken, 1);
    assert.equal(registry.isCurrent("task", taskToken), true);

    registry.bump("task");
    assert.equal(registry.isCurrent("task", taskToken), false);
    assert.equal(registry.capture("task"), 2);

    assert.equal(registry.capture("history"), 0);
    const historyToken = registry.bump("history");
    assert.equal(registry.isCurrent("history", historyToken), true);
});
