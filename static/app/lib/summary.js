export function getTopBehaviors(summary, limit = 3, formatBehaviorLabel) {
    if (!summary) return [];
    return [
        ...Object.entries(summary.student_behavior_stats || {}),
        ...Object.entries(summary.teacher_behavior_stats || {}),
    ]
        .map(([key, value]) => ({ label: formatBehaviorLabel(key), value: Number(value || 0) }))
        .filter((item) => item.value > 0)
        .sort((a, b) => b.value - a.value)
        .slice(0, limit);
}

export function renderBehaviorTags(items, formatNumber) {
    if (!items.length) return `<span class="mini-tag muted">暂无行为标签</span>`;
    return items.map((item, index) => `<span class="mini-tag tone-${(index % 4) + 1}"><strong>${item.label}</strong><small>${formatNumber(item.value)}</small></span>`).join("");
}

export function buildTaskHighlight(task, summary, getTopBehaviors, formatNumber) {
    if (task.status === "processing") return "任务处理中，等待结果摘要生成";
    if (task.status === "failed") return "任务失败或被中止，可点击回看已生成内容";
    const topEntry = getTopBehaviors(summary, 1)[0];
    if (topEntry) return `亮点：${topEntry.label} ${formatNumber(topEntry.value)} 次`;
    if (summary?.total_detections) return `亮点：共识别 ${formatNumber(summary.total_detections)} 个目标`;
    return "亮点：当前任务暂无统计摘要";
}

export function getModeNarrativeLead(mode, total, confidence, duration, formatNumber) {
    const intro = {
        image: "这是一张单图检测结果，系统会在单帧画面里定位课堂目标并输出行为标签。",
        batch: "这里展示的是一组批量检测结果，系统会对多张课堂图片做统一识别和汇总。",
        video: "这里展示的是视频检测结果，系统会在连续画面里持续跟踪课堂行为变化。",
        webcam: "这里展示的是实时巡检结果，系统会边采集边输出课堂行为识别反馈。",
    }[mode] || "这里展示的是当前检测结果。";
    return `${intro} 本次任务共识别 ${formatNumber(total)} 个目标，平均置信度 ${formatNumber(confidence * 100, 1)}%，处理时长 ${formatNumber(duration, 1)} 秒。`;
}

export function buildBehaviorNarrative(mode, topBehaviors, total, formatNumber) {
    if (!topBehaviors.length) return total > 0 ? "当前已有目标识别结果，但行为分布还不够集中。" : "当前结果较少，适合结合原始画面说明场景。";
    const behaviorLine = topBehaviors.map((item) => `${item.label}${formatNumber(item.value)}次`).join("、");
    const modeTip = {
        image: "适合强调检测框、标签和单帧识别精度。",
        batch: "适合强调同一套参数下的多图一致性和切换效率。",
        video: "适合强调连续画面处理过程和行为变化捕捉能力。",
        webcam: "适合强调现场反馈速度和实时巡检的可视化节奏。",
    }[mode] || "";
    return `主要行为包括 ${behaviorLine}。${modeTip}`;
}
