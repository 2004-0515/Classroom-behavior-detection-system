export function renderInspectorPanel({
    state,
    canvas,
    summaryNode,
    listNode,
    uiSettings,
    drawCanvasWithDetections,
    formatBehaviorLabel,
    formatNumber,
    onSelectDetection,
    onToggleDetection,
}) {
    renderInspectorCanvas({ state, canvas, uiSettings, drawCanvasWithDetections });
    renderInspectorSummary({ state, summaryNode, uiSettings });
    renderInspectorList({
        state,
        listNode,
        formatBehaviorLabel,
        formatNumber,
        onSelectDetection,
        onToggleDetection,
    });
}

function renderInspectorCanvas({ state, canvas, uiSettings, drawCanvasWithDetections }) {
    const { image, detections, visibility, activeIndex } = state;
    if (!image || !canvas) return;
    drawCanvasWithDetections(canvas, image, detections, visibility, activeIndex, uiSettings);
}

function renderInspectorSummary({ state, summaryNode, uiSettings }) {
    if (!summaryNode) return;
    const visibleCount = state.visibility.filter(Boolean).length;
    const total = state.detections.length;
    summaryNode.innerHTML = `
        <div><strong>${state.title}</strong><span>共 ${total} 个检测框，当前显示 ${visibleCount} 个</span></div>
        <div><strong>标签显示</strong><span>${(uiSettings?.show_bbox_labels ?? true) ? "开启" : "关闭"} / 置信度 ${(uiSettings?.show_confidence ?? true) ? "开启" : "关闭"}</span></div>
    `;
}

function renderInspectorList({
    state,
    listNode,
    formatBehaviorLabel,
    formatNumber,
    onSelectDetection,
    onToggleDetection,
}) {
    if (!listNode) return;
    if (!state.detections.length) {
        listNode.innerHTML = `<div class="detail-detection-item">当前没有可展示的检测框</div>`;
        return;
    }
    listNode.innerHTML = state.detections.map((item, index) => `
        <div class="detail-detection-item ${index === state.activeIndex ? "active" : ""}" data-index="${index}">
            <div class="detail-detection-head">
                <strong>${formatBehaviorLabel(item.behavior)}</strong>
                <label class="history-toggle detail-visibility-toggle">
                    <input type="checkbox" data-toggle-index="${index}" ${state.visibility[index] ? "checked" : ""}>
                    <span>${state.visibility[index] ? "显示" : "隐藏"}</span>
                </label>
            </div>
            <small>${item.source === "teacher" ? "教师/人头模型" : "学生行为模型"}${item.track_id != null ? ` · 轨迹 #${item.track_id}` : ""}${item.track_hits ? ` · 命中 ${item.track_hits} 帧` : ""}</small>
            <span>${formatNumber(item.confidence * 100, 1)}%</span>
        </div>
    `).join("");

    [...listNode.querySelectorAll(".detail-detection-item[data-index]")].forEach((node) => {
        node.addEventListener("click", () => onSelectDetection?.(Number(node.dataset.index)));
    });
    [...listNode.querySelectorAll("input[data-toggle-index]")].forEach((input) => {
        input.addEventListener("click", (event) => event.stopPropagation());
        input.addEventListener("change", (event) => {
            onToggleDetection?.(Number(event.target.dataset.toggleIndex), event.target.checked);
        });
    });
}
