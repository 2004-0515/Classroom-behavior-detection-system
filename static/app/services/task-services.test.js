import test from "node:test";
import assert from "node:assert/strict";

import {
    buildAppliedTaskState,
    loadTaskById,
    resolveHistoryTaskFollowup,
    resolveVideoPollingSnapshot,
    resolveWebcamPollingSnapshot,
} from "./task-results.js";
import {
    captureBrowserWebcamSessionFrame,
    resetBrowserWebcamSessionState,
    startBrowserWebcamSession,
    stopBrowserWebcamSession,
} from "./browser-webcam-session.js";

test("loadTaskById requests the expected task path", async () => {
    const calls = [];
    const task = { task_id: "t-1", status: "done" };
    const request = async (url) => {
        calls.push(url);
        return { data: task };
    };

    const result = await loadTaskById("t-1", request);

    assert.deepEqual(calls, ["/api/tasks/t-1"]);
    assert.equal(result, task);
});

test("buildAppliedTaskState normalizes payload and resets preview selectors", () => {
    const normalized = { assets: { results: [] } };
    const task = { task_id: "t-2" };
    const rawPayload = { task_id: "t-2", extra: true };

    const result = buildAppliedTaskState({
        task,
        taskPayload: rawPayload,
        normalizeTaskPayload: (payload) => {
            assert.equal(payload, rawPayload);
            return normalized;
        },
    });

    assert.deepEqual(result, {
        currentTask: task,
        activeTaskPayload: normalized,
        activeImageType: "annotated",
        activeAssetIndex: 0,
    });
});

test("resolveVideoPollingSnapshot keeps processing tasks lightweight", () => {
    const task = { task_id: "video-1", status: "processing" };
    const metrics = { fps: 12.3 };
    let normalizedCalled = false;

    const result = resolveVideoPollingSnapshot({
        task,
        metrics,
        normalizeTaskPayload: () => {
            normalizedCalled = true;
            return {};
        },
    });

    assert.equal(result.processing, true);
    assert.equal(result.taskPayload, null);
    assert.deepEqual(result.statePatch, { currentTask: task });
    assert.equal(normalizedCalled, false);
});

test("resolveVideoPollingSnapshot materializes payload when processing is finished", () => {
    const task = { task_id: "video-2", status: "finished" };
    const metrics = { fps: 0 };
    const normalized = { assets: { results: [{ filename: "a.jpg" }] } };

    const result = resolveVideoPollingSnapshot({
        task,
        metrics,
        normalizeTaskPayload: () => normalized,
    });

    assert.equal(result.processing, false);
    assert.equal(result.taskPayload, normalized);
    assert.deepEqual(result.statePatch, {
        currentTask: task,
        activeTaskPayload: normalized,
        activeAssetIndex: 0,
    });
});

test("resolveWebcamPollingSnapshot preserves current payload while processing", () => {
    const task = { task_id: "webcam-1", status: "processing" };
    const metrics = { fps: 20 };
    const currentPayload = { live: true };

    const result = resolveWebcamPollingSnapshot({
        task,
        metrics,
        normalizeTaskPayload: () => ({ shouldNotBeUsed: true }),
        currentActiveTaskPayload: currentPayload,
    });

    assert.equal(result.processing, true);
    assert.equal(result.taskPayload, currentPayload);
    assert.deepEqual(result.statePatch, { currentTask: task });
});

test("resolveWebcamPollingSnapshot falls back to current payload when normalization is empty", () => {
    const task = { task_id: "webcam-2", status: "finished" };
    const metrics = { fps: 0 };
    const currentPayload = { keep: true };

    const result = resolveWebcamPollingSnapshot({
        task,
        metrics,
        normalizeTaskPayload: () => null,
        currentActiveTaskPayload: currentPayload,
    });

    assert.equal(result.processing, false);
    assert.equal(result.taskPayload, currentPayload);
    assert.deepEqual(result.statePatch, {
        currentTask: task,
        activeTaskPayload: currentPayload,
    });
});

test("resolveHistoryTaskFollowup picks the correct poller", () => {
    assert.deepEqual(resolveHistoryTaskFollowup({ task_id: "1", task_type: "video", status: "processing" }), { poller: "video", taskId: "1" });
    assert.deepEqual(resolveHistoryTaskFollowup({ task_id: "2", task_type: "webcam", status: "processing" }), { poller: "webcam", taskId: "2" });
    assert.equal(resolveHistoryTaskFollowup({ task_id: "3", task_type: "image", status: "finished" }), null);
    assert.equal(resolveHistoryTaskFollowup(null), null);
});

test("startBrowserWebcamSession configures media elements and server session", async () => {
    const stream = { id: "stream-1" };
    const session = {};
    const video = {
        autoplay: false,
        playsInline: false,
        muted: false,
        srcObject: null,
        playCalls: 0,
        async play() {
            this.playCalls += 1;
        },
    };
    const canvas = { kind: "canvas" };
    const requestCalls = [];
    const request = async (url, options) => {
        requestCalls.push({ url, options });
        return { data: { task_id: "browser-1" } };
    };
    const previousNavigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, "navigator");
    Object.defineProperty(globalThis, "navigator", {
        configurable: true,
        writable: true,
        value: {
        mediaDevices: {
            getUserMedia: async (constraints) => {
                assert.deepEqual(constraints, { video: true, audio: false });
                return stream;
            },
        },
        },
    });

    try {
        const result = await startBrowserWebcamSession({
            session,
            request,
            createVideoElement: () => video,
            createCanvasElement: () => canvas,
        });

        assert.deepEqual(requestCalls, [
            {
                url: "/api/streams/webcam/browser-session/start",
                options: { method: "POST" },
            },
        ]);
        assert.deepEqual(result, { taskId: "browser-1" });
        assert.equal(session.active, true);
        assert.equal(session.stream, stream);
        assert.equal(session.taskId, "browser-1");
        assert.equal(session.video, video);
        assert.equal(session.canvas, canvas);
        assert.equal(video.autoplay, true);
        assert.equal(video.playsInline, true);
        assert.equal(video.muted, true);
        assert.equal(video.srcObject, stream);
        assert.equal(video.playCalls, 1);
        assert.equal(typeof session.startedAt, "number");
    } finally {
        if (previousNavigatorDescriptor) {
            Object.defineProperty(globalThis, "navigator", previousNavigatorDescriptor);
        } else {
            delete globalThis.navigator;
        }
    }
});

test("startBrowserWebcamSession stops tracks when startup fails after media access", async () => {
    const trackStops = [];
    const stream = {
        getTracks: () => [{ stop: () => trackStops.push("track-1") }, { stop: () => trackStops.push("track-2") }],
    };
    const session = {};
    const previousNavigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, "navigator");
    Object.defineProperty(globalThis, "navigator", {
        configurable: true,
        writable: true,
        value: {
            mediaDevices: {
                getUserMedia: async () => stream,
            },
        },
    });

    try {
        await assert.rejects(
            startBrowserWebcamSession({
                session,
                request: async () => {
                    throw new Error("session failed");
                },
                createVideoElement: () => ({ play: async () => {} }),
                createCanvasElement: () => ({}),
            }),
            /session failed/,
        );
        assert.deepEqual(trackStops, ["track-1", "track-2"]);
    } finally {
        if (previousNavigatorDescriptor) {
            Object.defineProperty(globalThis, "navigator", previousNavigatorDescriptor);
        } else {
            delete globalThis.navigator;
        }
    }
});

test("captureBrowserWebcamSessionFrame aggregates detections and returns snapshot", async () => {
    const drawCalls = [];
    const session = {
        active: true,
        taskId: "browser-2",
        video: { videoWidth: 640, videoHeight: 360 },
        canvas: {
            width: 0,
            height: 0,
            getContext() {
                return {
                    drawImage: (...args) => drawCalls.push(args),
                };
            },
            toDataURL(type, quality) {
                assert.equal(type, "image/jpeg");
                assert.equal(quality, 0.88);
                return "data:image/jpeg;base64,raw";
            },
        },
        processedFrames: 0,
        totalDetections: 0,
        confidenceSum: 0,
        studentCounts: {},
        teacherCounts: {},
        latestOriginalImage: null,
        latestAnnotatedImage: null,
        latestDetections: [],
    };
    const detections = [
        { source: "student", behavior: "reading", confidence: 0.8 },
        { source: "teacher", behavior: "lecture", confidence: 0.6 },
    ];
    const request = async (url, options) => {
        assert.equal(url, "/api/detect/frame");
        assert.equal(options.method, "POST");
        return { data: { annotated_image: "annotated-data" } };
    };
    const stats = { fps: 9.8, totalDetections: 2, averageConfidence: 0.7, duration: 1.2, processedFrames: 1 };
    const payload = { assets: { results: [] } };

    const result = await captureBrowserWebcamSessionFrame({
        session,
        request,
        mergeDetections: () => detections,
        getBrowserWebcamSessionStats: (currentSession) => {
            assert.equal(currentSession, session);
            return stats;
        },
        buildBrowserWebcamTaskPayload: (currentSession, currentStats) => {
            assert.equal(currentSession, session);
            assert.equal(currentStats, stats);
            return payload;
        },
    });

    assert.equal(session.canvas.width, 640);
    assert.equal(session.canvas.height, 360);
    assert.equal(drawCalls.length, 1);
    assert.equal(session.latestOriginalImage, "data:image/jpeg;base64,raw");
    assert.equal(session.latestAnnotatedImage, "annotated-data");
    assert.equal(session.latestDetections, detections);
    assert.equal(session.processedFrames, 1);
    assert.equal(session.totalDetections, 2);
    assert.equal(session.confidenceSum, 1.4);
    assert.deepEqual(session.studentCounts, { reading: 1 });
    assert.deepEqual(session.teacherCounts, { lecture: 1 });
    assert.deepEqual(result, {
        stats,
        taskPayload: payload,
        annotatedImage: "annotated-data",
        processedFrames: 1,
        taskId: "browser-2",
    });
});

test("captureBrowserWebcamSessionFrame short-circuits inactive or unready sessions", async () => {
    assert.equal(await captureBrowserWebcamSessionFrame({
        session: { active: false },
        request: async () => {
            throw new Error("should not run");
        },
        mergeDetections: () => [],
        getBrowserWebcamSessionStats: () => ({}),
        buildBrowserWebcamTaskPayload: () => ({}),
    }), null);

    assert.equal(await captureBrowserWebcamSessionFrame({
        session: { active: true, video: { videoWidth: 0, videoHeight: 0 }, canvas: {} },
        request: async () => {
            throw new Error("should not run");
        },
        mergeDetections: () => [],
        getBrowserWebcamSessionStats: () => ({}),
        buildBrowserWebcamTaskPayload: () => ({}),
    }), null);
});

test("stopBrowserWebcamSession sends aggregated summary payload", async () => {
    const session = {
        taskId: "browser-3",
        studentCounts: { reading: 2 },
        teacherCounts: { lecture: 1 },
        latestOriginalImage: "orig",
        latestAnnotatedImage: "anno",
    };
    const stats = {
        totalDetections: 3,
        averageConfidence: 0.75,
        duration: 8.4,
        processedFrames: 5,
    };
    const calls = [];

    const result = await stopBrowserWebcamSession({
        session,
        request: async (url, options) => {
            calls.push({ url, options });
            return { data: { ok: true } };
        },
        getBrowserWebcamSessionStats: () => stats,
        failureReason: "capture failed",
    });

    assert.deepEqual(result, { stats, taskId: "browser-3" });
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, "/api/streams/webcam/browser-session/stop");
    assert.equal(calls[0].options.method, "POST");
    const payload = JSON.parse(calls[0].options.body);
    assert.deepEqual(payload, {
        task_id: "browser-3",
        student_behavior_stats: { reading: 2 },
        teacher_behavior_stats: { lecture: 1 },
        total_detections: 3,
        average_confidence: 0.75,
        duration: 8.4,
        processed_frames: 5,
        total_frames: 5,
        original_image: "orig",
        annotated_image: "anno",
        failure_reason: "capture failed",
    });
});

test("stopBrowserWebcamSession returns early when task id is missing", async () => {
    const stats = { totalDetections: 0, averageConfidence: 0, duration: 0, processedFrames: 0 };
    let called = false;

    const result = await stopBrowserWebcamSession({
        session: { taskId: null },
        request: async () => {
            called = true;
        },
        getBrowserWebcamSessionStats: () => stats,
    });

    assert.equal(called, false);
    assert.deepEqual(result, { stats, taskId: null });
});

test("resetBrowserWebcamSessionState stops timer and tracks before clearing session", () => {
    const originalClearInterval = globalThis.clearInterval;
    const clearCalls = [];
    globalThis.clearInterval = (timer) => {
        clearCalls.push(timer);
    };
    const trackStops = [];
    const trackA = { stop: () => trackStops.push("a") };
    const trackB = { stop: () => trackStops.push("b") };
    const timer = { id: 1 };
    const session = {
        active: true,
        stream: { getTracks: () => [trackA, trackB] },
        taskId: "browser-4",
        startedAt: 123,
        processedFrames: 8,
        totalDetections: 13,
        confidenceSum: 4.2,
        studentCounts: { reading: 3 },
        teacherCounts: { lecture: 2 },
        latestOriginalImage: "orig",
        latestAnnotatedImage: "anno",
        latestDetections: [{ id: 1 }],
        timer,
        video: { id: "video" },
        canvas: { id: "canvas" },
    };

    try {
        resetBrowserWebcamSessionState(session);
    } finally {
        globalThis.clearInterval = originalClearInterval;
    }

    assert.deepEqual(clearCalls, [timer]);
    assert.deepEqual(trackStops, ["a", "b"]);
    assert.deepEqual(session, {
        active: false,
        stream: null,
        taskId: null,
        startedAt: 0,
        processedFrames: 0,
        totalDetections: 0,
        confidenceSum: 0,
        studentCounts: {},
        teacherCounts: {},
        latestOriginalImage: null,
        latestAnnotatedImage: null,
        latestDetections: [],
        timer: null,
        video: null,
        canvas: null,
    });
});
