export function renderTaskSummaryCards({
    node,
    summary,
    currentMode,
    formatTaskType,
}) {
    if (!summary) {
        node.innerHTML = `
            <div class="summary-card accent"><span>总检测数</span><strong>--</strong></div>
            <div class="summary-card"><span>平均置信度</span><strong>--</strong></div>
            <div class="summary-card"><span>处理时长</span><strong>--</strong></div>
            <div class="summary-card"><span>任务类型</span><strong>${formatTaskType(currentMode)}</strong></div>
        `;
        return;
    }
    const cards = summary.display_metrics?.cards;
    if (cards?.length) {
        node.innerHTML = cards.slice(0, 4).map((item, index) => `
            <div class="summary-card ${item.accent || index === 0 ? "accent" : ""}">
                <span>${item.label}</span>
                <strong>${item.formatted || "--"}</strong>
            </div>
        `).join("");
        return;
    }
    node.innerHTML = `
        <div class="summary-card accent"><span>总检测数</span><strong>${summary.total_detections || 0}</strong></div>
        <div class="summary-card"><span>平均置信度</span><strong>${((summary.average_confidence || 0) * 100).toFixed(1)}%</strong></div>
        <div class="summary-card"><span>处理时长</span><strong>${(summary.duration || 0).toFixed(1)} 秒</strong></div>
        <div class="summary-card"><span>任务类型</span><strong>${formatTaskType(summary.task_type || currentMode)}</strong></div>
    `;
}

export function renderTaskVideoMeta({
    node,
    summary,
    formatStatus,
    truncate,
    formatFileLabel,
    formatSummaryTone,
}) {
    node.innerHTML = `
        <span class="pill ${summary.status || ""}">${formatStatus(summary.status || "completed")}</span>
        <span class="pill">文件：${truncate(formatFileLabel(summary.file_name), 16)}</span>
        <span class="pill info">${summary.display_metrics?.highlight?.tone_label || formatSummaryTone(summary.total_detections)}</span>
    `;
}

export function renderAnalysisNarrativeBlock({
    node,
    summary,
    task,
    currentMode,
    formatTaskType,
    getTopBehaviors,
    formatNumber,
    buildBehaviorNarrative,
    getModeNarrativeLead,
    renderBehaviorTags,
}) {
    if (task?.status === "processing") {
        node.innerHTML = `
            <article class="narrative-card accent">
                <span>结论摘要</span>
                <strong>当前任务正在处理中</strong>
                <small>${formatTaskType(task.task_type || currentMode)} 正在持续生成结果，适合现场说明处理流程与预览反馈。</small>
            </article>
            <article class="narrative-card">
                <span>展示建议</span>
                <strong>优先讲解主预览区与实时状态</strong>
                <small>待任务完成后，这里会自动切换为结果总结和行为分布解读。</small>
            </article>
        `;
        return;
    }
    if (!summary) {
        node.innerHTML = `
            <article class="narrative-card">
                <span>结论摘要</span>
                <strong>等待检测结果</strong>
                <small>任务完成后，这里会自动提炼总量、置信度与适合答辩陈述的摘要。</small>
            </article>
            <article class="narrative-card">
                <span>展示建议</span>
                <strong>可先介绍模式和输入流程</strong>
                <small>当前适合讲解任务入口、参数设置和主预览区布局，等待结果生成后再切到行为总结。</small>
            </article>
        `;
        return;
    }
    const narrative = summary.display_metrics?.narrative || {};
    const highlight = summary.display_metrics?.highlight || {};
    const topBehaviors = getTopBehaviors(summary, 3);
    const behaviorTags = renderBehaviorTags(topBehaviors);
    node.innerHTML = `
        <article class="narrative-card accent">
            <span>结论摘要</span>
            <strong>${highlight.title || "检测摘要"}</strong>
            <small>${narrative.lead || getModeNarrativeLead(summary.task_type || currentMode, Number(summary.total_detections || 0), Number(summary.average_confidence || 0), Number(summary.duration || 0))}</small>
            <div class="tag-row">${behaviorTags}</div>
        </article>
        <article class="narrative-card">
            <span>展示建议</span>
            <strong>${narrative.recommendation_title || "结果可用于展示"}</strong>
            <small>${narrative.recommendation_text || buildBehaviorNarrative(summary.task_type || currentMode, topBehaviors, Number(summary.total_detections || 0))}</small>
        </article>
    `;
}

export function renderCurrentResultTagsBlock({
    node,
    summary,
    getTopBehaviors,
    renderBehaviorTags,
}) {
    if (!summary) {
        node.innerHTML = `<span class="mini-tag muted">等待结果标签生成</span>`;
        return;
    }
    node.innerHTML = renderBehaviorTags(getTopBehaviors(summary, 4));
}

export function renderSpeechTemplateBlock({
    node,
    summary,
    currentMode,
    getTopBehaviors,
    formatNumber,
    getModeNarrativeLead,
    buildBehaviorNarrative,
}) {
    if (!summary) {
        node.innerHTML = `
            <div class="speech-grid">
                <article class="speech-card"><span>30 秒版</span><p>结果生成后会自动整理一段简短讲解稿，适合快速说明模式、结果和主要行为。</p></article>
                <article class="speech-card"><span>90 秒版</span><p>结果生成后会自动整理一段更完整的答辩口播，适合展开讲解流程、统计结果和模型表现。</p></article>
            </div>
        `;
        return;
    }
    const narrative = summary.display_metrics?.narrative || {};
    const mode = summary.task_type || currentMode;
    const total = Number(summary.total_detections || 0);
    const confidence = Number(summary.average_confidence || 0);
    const duration = Number(summary.duration || 0);
    const topBehaviors = getTopBehaviors(summary, 3);
    const behaviorLine = topBehaviors.length ? `其中最主要的是 ${topBehaviors.map((item) => item.formatted ? `${item.label}${item.formatted}` : `${item.label}${formatNumber(item.value)}次`).join("、")}。` : "当前行为分布还不够集中。";
    const shortSpeech = narrative.short_speech || `${getModeNarrativeLead(mode, total, confidence, duration)} ${behaviorLine}`;
    const longSpeech = narrative.long_speech || `${getModeNarrativeLead(mode, total, confidence, duration)} ${behaviorLine} ${buildBehaviorNarrative(mode, topBehaviors, total)}`;
    node.innerHTML = `
        <div class="speech-grid">
            <article class="speech-card"><span>30 秒版</span><p>${shortSpeech}</p></article>
            <article class="speech-card"><span>90 秒版</span><p>${longSpeech}</p></article>
        </div>
    `;
}
