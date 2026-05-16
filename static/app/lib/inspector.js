export async function buildInspectorPayload({
    task,
    taskPayload,
    mode,
    browserWebcamActive,
    browserWebcamOriginalImage,
    browserWebcamDetections,
    activeAssetIndex,
    resolveActiveAsset,
    request,
    formatTaskType,
    formatFileLabel,
}) {
    if (browserWebcamActive && mode === "webcam") {
        if (!browserWebcamOriginalImage) throw new Error("浏览器摄像头还没有生成可细看的帧");
        return {
            imageUrl: browserWebcamOriginalImage,
            detections: browserWebcamDetections,
            title: "实时摄像头 · 当前帧细看",
        };
    }
    if (mode === "image" || mode === "batch") {
        const asset = resolveActiveAsset(taskPayload, activeAssetIndex);
        if (!asset?.original) throw new Error("当前任务没有原始图像");
        const frameNumber = asset.frame_number ?? (mode === "image" ? 0 : activeAssetIndex);
        const response = await request(`/api/tasks/${task.task_id}/detections?frame_number=${frameNumber}`);
        const detections = mergeDetections(response.data);
        return {
            imageUrl: asset.original,
            detections,
            title: `${formatTaskType(mode)} · ${formatFileLabel(asset.filename || taskPayload?.file_name)}`,
        };
    }
    const frameData = await getRealtimeFrameAnalysis({ task, mode, request });
    return { imageUrl: frameData.image, detections: mergeDetections(frameData), title: `${formatTaskType(mode)} · 当前帧细看` };
}

export async function getRandomCallPayload({
    task,
    taskPayload,
    mode,
    browserWebcamActive,
    browserWebcamOriginalImage,
    browserWebcamDetections,
    activeAssetIndex,
    resolveActiveAsset,
    request,
    formatTaskType,
}) {
    if (browserWebcamActive && mode === "webcam") {
        return {
            image: browserWebcamOriginalImage,
            detections: browserWebcamDetections,
            label: "浏览器摄像头当前帧",
        };
    }
    if (mode === "image" || mode === "batch") {
        const asset = resolveActiveAsset(taskPayload, activeAssetIndex);
        if (!asset?.original) throw new Error("当前任务没有原始图像");
        const response = await request(`/api/tasks/${task.task_id}/detections?frame_number=${asset.frame_number ?? activeAssetIndex}`);
        return { image: asset.original, detections: mergeDetections(response.data), label: `${formatTaskType(mode)} 当前图像` };
    }
    const realtime = await getRealtimeFrameAnalysis({ task, mode, request });
    return { image: realtime.image, detections: mergeDetections(realtime), label: mode === "webcam" ? "实时摄像头当前帧" : "视频首帧复检" };
}

export async function getRealtimeFrameAnalysis({ task, mode, request }) {
    const frameEndpoint = mode === "webcam" ? "/api/streams/webcam/original-frame" : `/api/streams/video/${task.task_id}/original-frame`;
    const frameResponse = await request(frameEndpoint);
    const frameImage = frameResponse.data.image;
    const detectResponse = await request("/api/detect/frame", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image: frameImage }),
    });
    return { image: frameImage, ...detectResponse.data };
}

export function mergeDetections(payload = {}) {
    return [
        ...(payload.student_detections || []).map((item) => ({ ...item, source: "student" })),
        ...(payload.teacher_detections || []).map((item) => ({ ...item, source: "teacher" })),
    ];
}

export function mergeDetectionsFromTaskPayload(taskPayload) {
    return [
        ...Object.entries(taskPayload?.student_behavior_stats || {})
            .filter(([, count]) => Number(count) > 0)
            .map(([behavior]) => ({ behavior, confidence: 1, source: "student" })),
        ...Object.entries(taskPayload?.teacher_behavior_stats || {})
            .filter(([, count]) => Number(count) > 0)
            .map(([behavior]) => ({ behavior, confidence: 1, source: "teacher" })),
    ];
}

export function isHeadCandidate(label) {
    return /head|teacher|人头|教师|讲课|巡视|观察/.test(String(label || "").toLowerCase()) || /人头|教师|讲课|巡视|观察/.test(String(label || ""));
}

export function pickRandomHeadCandidate(detections = [], matcher = isHeadCandidate) {
    const headCandidates = detections.filter((item) => matcher(item?.behavior));
    if (!headCandidates.length) {
        throw new Error("未检测到可点名目标");
    }
    return headCandidates[Math.floor(Math.random() * headCandidates.length)];
}
