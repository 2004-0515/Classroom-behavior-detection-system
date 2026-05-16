export function renderTaskStatePanel({
    node,
    task,
    currentMode,
    metrics = {},
    statusPill,
    formatTaskType,
    formatStatus,
    formatNumber,
}) {
    if (!task) {
        node.innerHTML = `
            <div class="pill">待启动</div>
            <div>当前没有进行中的任务</div>
            <div>选择模式并导入素材后，可在这里查看处理进度。</div>
        `;
        return;
    }
    const status = task.status || "processing";
    const processed = metrics.processed_frames ?? task.processed_frames ?? 0;
    const totalFrames = metrics.total_frames ?? task.total_frames ?? 0;
    node.innerHTML = `
        <div>${statusPill(status)}</div>
        <div>任务类型：${formatTaskType(task.task_type || currentMode)}</div>
        <div>当前状态：${formatStatus(status)}</div>
        <div>已处理：${formatNumber(processed)}${totalFrames ? ` / ${formatNumber(totalFrames)}` : ""}</div>
        <div>FPS: ${formatNumber(metrics.fps, 2)}</div>
        <div>预计剩余：${metrics.eta_seconds === null || metrics.eta_seconds === undefined ? "--" : `${formatNumber(metrics.eta_seconds, 1)} 秒`}</div>
    `;
}

export function renderSystemStatsPanel({
    node,
    task,
    currentMode,
    metrics = {},
    confidence,
    iou,
    cameraIndex,
    formatTaskType,
    formatNumber,
    formatStatus,
}) {
    node.innerHTML = `
        <div class="stat-item"><strong>模式</strong><div>${formatTaskType(currentMode)}</div></div>
        <div class="stat-item"><strong>FPS</strong><div>${formatNumber(metrics.fps, 2)}</div></div>
        <div class="stat-item"><strong>检测数</strong><div>${formatNumber(metrics.total_detections)}</div></div>
        <div class="stat-item"><strong>阈值</strong><div>${formatNumber(confidence, 2)} / ${formatNumber(iou, 2)}</div></div>
        <div class="stat-item"><strong>任务状态</strong><div>${task ? formatStatus(task.status || "processing") : "待启动"}</div></div>
        <div class="stat-item"><strong>机位</strong><div>${metrics.camera_index ?? cameraIndex} ${metrics.backend ? `/ ${metrics.backend}` : ""}</div></div>
    `;
}

export function renderLiveBannerPanel({
    bannerNode,
    statusNode,
    statsNode,
    isWebcam,
    task,
    metrics = {},
    cameraIndex,
    formatStatus,
    formatNumber,
}) {
    bannerNode.classList.toggle("hidden", !isWebcam);
    if (!isWebcam) return;
    const status = task ? formatStatus(task.status || "processing") : "待启动";
    statusNode.className = `pill ${task?.status || ""}`.trim();
    statusNode.textContent = status;
    statsNode.innerHTML = `
        <div class="live-stat"><span>机位</span><strong>${metrics.camera_index ?? cameraIndex}</strong><small>${metrics.backend || "等待诊断后端"}</small></div>
        <div class="live-stat"><span>实时 FPS</span><strong>${formatNumber(metrics.fps ?? 0, 2)}</strong><small>用于说明当前处理节奏</small></div>
        <div class="live-stat"><span>累计检测</span><strong>${formatNumber(metrics.total_detections ?? 0)}</strong><small>当前巡检已识别目标数</small></div>
        <div class="live-stat"><span>处理进度</span><strong>${formatNumber(metrics.processed_frames ?? task?.processed_frames ?? 0)}</strong><small>${metrics.eta_seconds === null || metrics.eta_seconds === undefined ? "实时模式持续运行中" : `预计剩余 ${formatNumber(metrics.eta_seconds, 1)} 秒`}</small></div>
    `;
}

export function renderWebcamDiagnosticsPanel({
    node,
    mode,
    diagnostics,
}) {
    if (mode !== "webcam") {
        node.innerHTML = "";
        return;
    }
    if (!diagnostics) {
        node.innerHTML = `<div><strong>尚未诊断</strong><span>点击“诊断摄像头”后会展示服务端机位信息；如果服务端取流失败，会自动尝试浏览器直连。</span></div>`;
        return;
    }
    const selected = diagnostics.selected;
    const attempts = diagnostics.attempts || [];
    node.innerHTML = `
        <div><strong>${selected ? `已选机位 ${selected.index}` : "未找到可用机位"}</strong><span>${selected ? `${selected.backend} · 分辨率 ${selected.shape?.join("x") || "--"}` : "请检查摄像头权限或索引"}</span></div>
        ${attempts.slice(0, 3).map((item) => `<div><strong>${item.index} / ${item.backend}</strong><span>${item.success ? "可读取画面" : item.error}</span></div>`).join("")}
    `;
}
