export function drawCanvasWithDetections(
    canvas,
    image,
    detections,
    visibility,
    activeIndex,
    uiSettings,
    activeColor,
    formatBehaviorLabel,
    formatNumber,
) {
    const ctx = canvas.getContext("2d");
    canvas.width = image.naturalWidth || image.width;
    canvas.height = image.naturalHeight || image.height;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
    detections.forEach((item, index) => {
        if (!visibility[index]) return;
        const [x1, y1, x2, y2] = item.bbox || [0, 0, 0, 0];
        ctx.lineWidth = index === activeIndex ? 4 : 2;
        ctx.strokeStyle = index === activeIndex ? activeColor : item.source === "teacher" ? "#10b981" : "#2563eb";
        ctx.fillStyle = index === activeIndex ? activeColor : item.source === "teacher" ? "#10b981" : "#2563eb";
        ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
        if (uiSettings.show_bbox_labels) {
            const label = [formatBehaviorLabel(item.behavior), uiSettings.show_confidence ? `${formatNumber((item.confidence || 0) * 100, 1)}%` : ""].filter(Boolean).join(" ");
            const textWidth = Math.max(72, ctx.measureText(label).width + 14);
            ctx.fillRect(x1, Math.max(0, y1 - 24), textWidth, 22);
            ctx.fillStyle = "#ffffff";
            ctx.font = "14px Segoe UI";
            ctx.fillText(label, x1 + 6, Math.max(16, y1 - 8));
        }
    });
}
