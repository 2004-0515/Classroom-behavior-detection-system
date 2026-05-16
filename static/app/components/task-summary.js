export function renderTaskSummaryCards({
    node,
    summary,
    currentMode,
    formatNumber,
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
    node.innerHTML = `
        <div class="summary-card accent"><span>总检测数</span><strong>${formatNumber(summary.total_detections)}</strong></div>
        <div class="summary-card"><span>平均置信度</span><strong>${formatNumber((summary.average_confidence || 0) * 100, 1)}%</strong></div>
        <div class="summary-card"><span>处理时长</span><strong>${formatNumber(summary.duration || 0, 1)} 秒</strong></div>
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
        <span class="pill info">${formatSummaryTone(summary.total_detections)}</span>
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
    const total = Number(summary.total_detections || 0);
    const confidence = Number(summary.average_confidence || 0);
    const duration = Number(summary.duration || 0);
    const mode = summary.task_type || currentMode;
    const topBehaviors = getTopBehaviors(summary, 3);
    const tone = total >= 20 ? "检测覆盖较高" : total >= 1 ? "已识别到有效目标" : "当前结果较少";
    const confidenceTone = confidence >= 0.7 ? "结果稳定度较高" : confidence >= 0.4 ? "结果可用于展示" : "建议结合原图说明";
    const durationTone = duration >= 60 ? "处理时长偏长，适合说明完整流程" : duration > 0 ? "处理节奏适合现场演示" : "等待任务完成后生成节奏信息";
    const behaviorSentence = buildBehaviorNarrative(mode, topBehaviors, total);
    const modeLead = getModeNarrativeLead(mode, total, confidence, duration);
    node.innerHTML = `
        <article class="narrative-card accent">
            <span>结论摘要</span>
            <strong>${tone}</strong>
            <small>${modeLead}</small>
            <div class="tag-row">${renderBehaviorTags(topBehaviors)}</div>
        </article>
        <article class="narrative-card">
            <span>展示建议</span>
            <strong>${confidenceTone}</strong>
            <small>${behaviorSentence} ${durationTone}</small>
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
    const mode = summary.task_type || currentMode;
    const total = Number(summary.total_detections || 0);
    const confidence = Number(summary.average_confidence || 0);
    const duration = Number(summary.duration || 0);
    const topBehaviors = getTopBehaviors(summary, 3);
    const behaviorLine = topBehaviors.length ? `其中最主要的是 ${topBehaviors.map((item) => `${item.label}${formatNumber(item.value)}次`).join("、")}。` : "当前行为分布还不够集中。";
    const shortSpeech = `${getModeNarrativeLead(mode, total, confidence, duration)} ${behaviorLine}`;
    const longSpeech = `${getModeNarrativeLead(mode, total, confidence, duration)} ${behaviorLine} ${buildBehaviorNarrative(mode, topBehaviors, total)}`;
    node.innerHTML = `
        <div class="speech-grid">
            <article class="speech-card"><span>30 秒版</span><p>${shortSpeech}</p></article>
            <article class="speech-card"><span>90 秒版</span><p>${longSpeech}</p></article>
        </div>
    `;
}
