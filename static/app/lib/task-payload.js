export function normalizeTaskPayload(taskPayload) {
    if (!taskPayload) return taskPayload;
    const normalized = { ...taskPayload };
    if (normalized.assets?.results?.length) {
        normalized.assets.results = normalized.assets.results.map((item, index) => ({ ...item, frame_number: item.frame_number ?? index }));
    }
    return normalized;
}

export function resolveActiveAsset(taskPayload, activeAssetIndex = 0) {
    const assetList = taskPayload?.assets?.results || [];
    if (assetList.length) {
        return assetList[Math.min(activeAssetIndex, assetList.length - 1)];
    }
    return taskPayload?.assets || null;
}

export function getBrowserWebcamSessionStats(session) {
    const duration = session?.startedAt ? (Date.now() - session.startedAt) / 1000 : 0;
    const processedFrames = session?.processedFrames || 0;
    const totalDetections = session?.totalDetections || 0;
    return {
        duration,
        processedFrames,
        totalDetections,
        averageConfidence: totalDetections ? (session?.confidenceSum || 0) / totalDetections : 0,
        fps: duration > 0 ? processedFrames / duration : 0,
    };
}

export function buildBrowserWebcamTaskPayload(session, stats = getBrowserWebcamSessionStats(session)) {
    return {
        task_id: session?.taskId,
        task_type: "webcam",
        status: "processing",
        file_name: "browser_camera",
        total_detections: stats.totalDetections,
        average_confidence: stats.averageConfidence,
        duration: stats.duration,
        student_behavior_stats: { ...(session?.studentCounts || {}) },
        teacher_behavior_stats: { ...(session?.teacherCounts || {}) },
        assets: {
            original: session?.latestOriginalImage || null,
            result: session?.latestAnnotatedImage || null,
            report: `/api/tasks/${session?.taskId}/report`,
            results: [],
        },
    };
}
