export function createActionRegistry(onBusy) {
    const active = new Map();
    const notified = new Set();

    function notifyBusy(key, message) {
        if (!message || notified.has(key)) return;
        notified.add(key);
        if (typeof onBusy === "function") {
            onBusy(message);
        }
    }

    return {
        acquire(key, busyMessage = "") {
            if (active.has(key)) {
                notifyBusy(key, busyMessage);
                return null;
            }
            const token = Symbol(key);
            active.set(key, token);
            notified.delete(key);
            return token;
        },
        release(key, token) {
            if (active.get(key) !== token) return false;
            active.delete(key);
            notified.delete(key);
            return true;
        },
        isActive(key) {
            return active.has(key);
        },
        clear(key) {
            active.delete(key);
            notified.delete(key);
        },
        clearAll() {
            active.clear();
            notified.clear();
        },
    };
}

export function createVersionRegistry(keys = []) {
    const versions = new Map(keys.map((key) => [key, 0]));

    function ensureKey(key) {
        if (!versions.has(key)) {
            versions.set(key, 0);
        }
    }

    return {
        bump(key) {
            ensureKey(key);
            const next = (versions.get(key) || 0) + 1;
            versions.set(key, next);
            return next;
        },
        capture(key) {
            ensureKey(key);
            return versions.get(key) || 0;
        },
        isCurrent(key, token) {
            ensureKey(key);
            return (versions.get(key) || 0) === token;
        },
    };
}
