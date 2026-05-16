export async function request(url, options = {}) {
    const { timeoutMs, ...fetchOptions } = options;
    const controller = timeoutMs ? new AbortController() : null;
    const timer = controller ? window.setTimeout(() => controller.abort(), timeoutMs) : null;
    let response;
    try {
        response = await fetch(url, {
            credentials: "same-origin",
            ...fetchOptions,
            signal: controller?.signal,
        });
    } catch (error) {
        if (error?.name === "AbortError") {
            throw new Error("请求超时");
        }
        throw error;
    } finally {
        if (timer) {
            window.clearTimeout(timer);
        }
    }

    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json")
        ? await response.json()
        : await response.text();

    if (!response.ok) {
        const message = payload?.message || payload?.error?.message || response.statusText;
        throw new Error(message);
    }
    return payload;
}

export function createFormData(state, files) {
    const form = new FormData();
    const key = state.mode === "batch" ? "files" : "file";
    for (const file of files) {
        form.append(key, file);
    }
    form.append("confidence", state.confidence);
    form.append("iou", state.iou);
    form.append("frame_skip", state.frameSkip);
    return form;
}
