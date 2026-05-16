export function renderRandomCallResult({
    canvas,
    metaNode,
    image,
    target,
    label,
    drawCanvasWithDetections,
    formatBehaviorLabel,
    formatNumber,
}) {
    drawCanvasWithDetections(
        canvas,
        image,
        [target],
        [true],
        0,
        { show_bbox_labels: true, show_confidence: true },
        "#d97706",
    );
    metaNode.innerHTML = `
        <div><strong>命中目标</strong><span>${formatBehaviorLabel(target.behavior)}</span></div>
        <div><strong>置信度</strong><span>${formatNumber(target.confidence * 100, 1)}%</span></div>
        <div><strong>来源</strong><span>${label}</span></div>
    `;
}
