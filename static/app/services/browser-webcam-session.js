function stopStreamTracks(stream) {
    stream?.getTracks?.().forEach((track) => track.stop());
}

export async function startBrowserWebcamSession({
    session,
    request,
    createVideoElement,
    createCanvasElement,
}) {
    let stream = null;
    try {
        stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        const sessionRes = await request("/api/streams/webcam/browser-session/start", { method: "POST" });
        session.stream = stream;
        session.taskId = sessionRes.data.task_id;
        session.video = createVideoElement();
        session.video.autoplay = true;
        session.video.playsInline = true;
        session.video.muted = true;
        session.video.srcObject = stream;
        session.canvas = createCanvasElement();
        await session.video.play();
        session.active = true;
        session.startedAt = Date.now();
        return { taskId: session.taskId };
    } catch (error) {
        stopStreamTracks(stream);
        if (session.video) {
            session.video.srcObject = null;
        }
        throw error;
    }
}

export async function captureBrowserWebcamSessionFrame({
    session,
    request,
    mergeDetections,
    getBrowserWebcamSessionStats,
    buildBrowserWebcamTaskPayload,
}) {
    if (!session.active || !session.video || !session.canvas) return null;
    const video = session.video;
    if (!video.videoWidth || !video.videoHeight) return null;
    const canvas = session.canvas;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const originalImage = canvas.toDataURL("image/jpeg", 0.88);
    const detectResponse = await request("/api/detect/frame", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image: originalImage }),
    });
    const data = detectResponse.data;
    const detections = mergeDetections(data);
    session.latestOriginalImage = originalImage;
    session.latestAnnotatedImage = data.annotated_image;
    session.latestDetections = detections;
    session.processedFrames += 1;
    session.totalDetections += detections.length;
    detections.forEach((item) => {
        session.confidenceSum += Number(item.confidence || 0);
        const bucket = item.source === "teacher" ? session.teacherCounts : session.studentCounts;
        bucket[item.behavior] = (bucket[item.behavior] || 0) + 1;
    });

    const stats = getBrowserWebcamSessionStats(session);
    const taskPayload = buildBrowserWebcamTaskPayload(session, stats);
    return {
        stats,
        taskPayload,
        annotatedImage: data.annotated_image,
        processedFrames: session.processedFrames,
        taskId: session.taskId,
    };
}

export async function stopBrowserWebcamSession({
    session,
    request,
    getBrowserWebcamSessionStats,
    failureReason = "",
}) {
    const stats = getBrowserWebcamSessionStats(session);
    const taskId = session.taskId;
    if (!taskId) {
        return { stats, taskId: null };
    }
    await request("/api/streams/webcam/browser-session/stop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            task_id: taskId,
            student_behavior_stats: { ...session.studentCounts },
            teacher_behavior_stats: { ...session.teacherCounts },
            total_detections: stats.totalDetections,
            average_confidence: stats.averageConfidence,
            duration: stats.duration,
            processed_frames: stats.processedFrames,
            total_frames: stats.processedFrames,
            original_image: session.latestOriginalImage,
            annotated_image: session.latestAnnotatedImage,
            failure_reason: failureReason || undefined,
        }),
    });
    return { stats, taskId };
}

export function resetBrowserWebcamSessionState(session) {
    if (session.timer) {
        clearInterval(session.timer);
    }
    stopStreamTracks(session.stream);
    Object.assign(session, {
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
}
