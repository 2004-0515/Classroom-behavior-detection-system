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
    const summaryLike = stats || {};
    return {
        task_id: summaryLike.task_id || session?.taskId,
        task_type: summaryLike.task_type || "webcam",
        status: summaryLike.status || "processing",
        file_name: summaryLike.file_name || "browser_camera",
        total_detections: summaryLike.total_detections ?? summaryLike.totalDetections ?? 0,
        average_confidence: summaryLike.average_confidence ?? summaryLike.averageConfidence ?? 0,
        duration: summaryLike.duration ?? 0,
        processed_frames: summaryLike.processed_frames ?? summaryLike.processedFrames ?? session?.processedFrames ?? 0,
        total_frames: summaryLike.total_frames ?? summaryLike.totalFrames ?? session?.processedFrames ?? 0,
        student_behavior_stats: { ...(summaryLike.student_behavior_stats || session?.studentCounts || {}) },
        teacher_behavior_stats: { ...(summaryLike.teacher_behavior_stats || session?.teacherCounts || {}) },
        display_metrics: { ...(summaryLike.display_metrics || {}) },
        derived_metrics: { ...(summaryLike.derived_metrics || {}) },
        assets: {
            original: session?.latestOriginalImage || null,
            result: session?.latestAnnotatedImage || null,
            report: `/api/tasks/${session?.taskId}/report`,
            results: [],
        },
    };
}
