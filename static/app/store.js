const state = {
    mode: "image",
    confidence: 0.25,
    iou: 0.45,
    frameSkip: 2,
    cameraIndex: 0,
    selectedFiles: [],
    currentTask: null,
    activeTaskPayload: null,
    activeImageType: "annotated",
    activeAssetIndex: 0,
    models: [],
    modelInfo: null,
    overview: null,
    uiSettings: null,
    configBundle: null,
    recentTasks: [],
    taskPayloads: {},
    selectedHistoryIds: [],
    exportingHistoryReports: false,
    webcamDiagnostics: null,
    webcamStarting: false,
    notifications: [],
};

const listeners = new Set();

export function getState() {
    return state;
}

export function setState(patch) {
    Object.assign(state, patch);
    listeners.forEach((listener) => listener(state));
}

export function subscribe(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
}

export function pushNotification(message, tone = "info") {
    state.notifications.unshift({
        id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        message,
        tone,
        createdAt: new Date().toLocaleTimeString(),
    });
    state.notifications = state.notifications.slice(0, 8);
    listeners.forEach((listener) => listener(state));
}
