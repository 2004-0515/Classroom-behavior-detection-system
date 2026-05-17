import { request, createFormData } from "./api.js";

// Components
import { drawCanvasWithDetections as drawCanvasWithDetectionsComponent } from "./components/canvas-overlay.js";
import { renderCharts } from "./components/charts.js";
import { renderHistoryList, renderHistorySelectionMeta } from "./components/history.js";
import { renderInspectorPanel } from "./components/inspector.js";
import { renderRandomCallResult } from "./components/random-call.js";
import {
    renderLiveBannerPanel,
    renderSystemStatsPanel,
    renderTaskStatePanel,
    renderWebcamDiagnosticsPanel,
} from "./components/status-panels.js";
import {
    renderAnalysisNarrativeBlock,
    renderCurrentResultTagsBlock,
    renderSpeechTemplateBlock,
    renderTaskSummaryCards,
    renderTaskVideoMeta,
} from "./components/task-summary.js";

// Libs
import {
    formatBehaviorLabel,
    formatFileLabel,
    formatModeBadge,
    formatModelDetail,
    formatModelName,
    formatNumber,
    formatRelativeTimeLabel,
    formatStatus,
    formatSummaryTone,
    formatTaskType,
    statusPill,
    truncate,
} from "./lib/format.js";
import {
    compareHistoryTasks as compareHistoryTasksHelper,
    getFilteredHistoryTasks as getFilteredHistoryTasksHelper,
    getHistorySelectionMeta,
    getSpecialHistoryTask,
    getVisibleShowcaseTaskIds,
    isShowcaseTask as isShowcaseTaskHelper,
    toggleHistorySelectionIds,
} from "./lib/history.js";
import {
    buildBrowserWebcamTaskPayload,
    getBrowserWebcamSessionStats,
    normalizeTaskPayload,
    resolveActiveAsset,
} from "./lib/task-payload.js";
import {
    buildInspectorPayload,
    getRandomCallPayload,
    isHeadCandidate,
    mergeDetections,
    mergeDetectionsFromTaskPayload,
    pickRandomHeadCandidate,
} from "./lib/inspector.js";
import {
    buildBehaviorNarrative as buildBehaviorNarrativeHelper,
    buildTaskHighlight as buildTaskHighlightHelper,
    getModeNarrativeLead as getModeNarrativeLeadHelper,
    getTopBehaviors as getTopBehaviorsHelper,
    renderBehaviorTags as renderBehaviorTagsHelper,
} from "./lib/summary.js";

// Services
import {
    captureBrowserWebcamSessionFrame,
    resetBrowserWebcamSessionState,
    startBrowserWebcamSession,
    stopBrowserWebcamSession,
} from "./services/browser-webcam-session.js";
import {
    buildAppliedTaskState,
    loadTaskById,
    loadVideoPollingSnapshot,
    resolveHistoryTaskFollowup,
    resolveWebcamPollingSnapshot,
} from "./services/task-results.js";
import { restoreStoppedTaskState, stopVideoTask } from "./services/task-runtime.js";

// Store
import { getState, pushNotification, setState, subscribe } from "./store.js";

const WEBCAM_DIAGNOSTICS_TIMEOUT_MS = 16000;
const BROWSER_WEBCAM_FIRST_FRAME_TIMEOUT_MS = 4500;
const WEBCAM_SERVER_START_RETRY_DELAY_MS = 600;
const VALID_MODES = new Set(["image", "batch", "video", "webcam"]);

const MODE_CONTENT = {
    image: {
        title: "单图检测工作台",
        intro: "围绕单张图片的快速检测与结果回看，适合展示识别效果。",
        hint: "导入一张图片后直接开始检测，主预览区会优先展示识别结果。",
        dropTitle: "拖入单张课堂图片",
        runLabel: "开始单图检测",
        emptyTitle: "等待单图检测开始",
        emptyCopy: "选择一张课堂图片后，这里会显示标注结果与关键统计。",
    },
    batch: {
        title: "批量图片检测工作台",
        intro: "适合演示多张课堂素材的统一处理、对比和批量导出。",
        hint: "一次导入多张图片后执行批量检测，并在结果画廊中切换查看。",
        dropTitle: "拖入多张课堂图片",
        runLabel: "开始批量检测",
        emptyTitle: "等待批量检测开始",
        emptyCopy: "导入多张素材后，这里会展示首张结果并支持批量切换。",
    },
    video: {
        title: "视频检测工作台",
        intro: "面向课堂视频片段的连续分析，适合展示处理过程、暂停控制和结果输出。",
        hint: "上传视频后启动检测，处理中可轮询预览并支持中止任务。",
        dropTitle: "拖入课堂视频片段",
        runLabel: "开始视频检测",
        emptyTitle: "等待视频检测开始",
        emptyCopy: "上传课堂视频后，这里会展示处理流、结果预览和任务节奏。",
    },
    webcam: {
        title: "实时巡检工作台",
        intro: "围绕实时机位巡检展开，适合演示摄像头诊断、启动与实时分析。",
        hint: "先诊断机位，再启动摄像头。实时模式不需要上传素材。",
        dropTitle: "实时模式无需上传",
        runLabel: "开始检测",
        emptyTitle: "等待实时巡检开始",
        emptyCopy: "完成机位诊断并启动摄像头后，这里会显示实时巡检结果。",
    },
};

const DEFAULT_UI_SETTINGS = {
    auto_scan_models: true,
    show_confidence: true,
    show_bbox_labels: true,
    default_mode: "image",
};

const els = {};
const inspectorState = {
    image: null,
    detections: [],
    visibility: [],
    activeIndex: -1,
    title: "",
};
let taskPoller = null;
let historyPoller = null;
let webcamPoller = null;
let historyRefreshInFlight = false;
let browserWebcamFailureInFlight = false;
const browserWebcamSession = {
    active: false,
    stream: null,
    taskId: null,
    startedAt: 0,
    processedFrames: 0,
    totalDetections: 0,
    confidenceSum: 0,
    studentCounts: {},
    teacherCounts: {},
    latestOriginalImage: null,
    latestAnnotatedImage: null,
    latestDetections: [],
    timer: null,
    video: null,
    canvas: null,
};
const DIALOG_FOCUSABLE_SELECTOR = [
    "button:not([disabled])",
    "[href]",
    "input:not([disabled])",
    "select:not([disabled])",
    "textarea:not([disabled])",
    "[tabindex]:not([tabindex='-1'])",
].join(", " );
let activeDialogId = null;
const dialogOpeners = new Map();

document.addEventListener("DOMContentLoaded", async () => {
    bindElements();
    bindEvents();
    subscribe(render);
    render(getState());
    await bootstrap();
});

function bindElements() {
    [
        "app", "fileInput", "pickFileBtn", "dropzone", "selectedFiles", "runBtn", "workspaceTitle",
        "modeBadge", "confidenceInput", "confidenceLabel", "iouInput", "iouLabel", "frameSkipInput",
        "cameraIndexInput", "studentModelSelect", "teacherModelSelect", "scanModelsBtn", "applyModelsBtn",
        "modelMeta", "historyList", "summaryCards", "resultImage", "resultVideo", "emptyState", "videoMeta",
        "systemStats", "taskState", "notifications", "showOriginalBtn", "showAnnotatedBtn", "reportLink",
        "saveParamsBtn", "refreshHistoryBtn", "historyFilter", "startWebcamBtn", "stopWebcamBtn",
        "probeWebcamBtn", "webcamControls", "logoutBtn", "resultGallery", "webcamDiagnostics",
        "overviewHighlights", "modeIntro", "dropzoneHint", "dropzoneTitle", "analysisNarrative",
        "webcamLiveBanner", "liveBannerStats", "liveBannerStatus", "currentResultTags", "speechTemplate",
        "historyModeFilter", "historySort", "historyLatestBtn", "historyTopBtn", "historyShowcaseOnly",
        "historyExportSelectedBtn", "historySelectionMeta", "historySelectShowcaseBtn",
        "historyClearSelectedBtn", "previewSurface", "settingsBtn", "settingsModal", "settingDefaultMode",
        "settingAutoScan", "settingShowConfidence", "settingShowLabels", "saveSettingsBtn",
        "resetSettingsBtn", "settingsFeedback", "currentModelDetailsBtn", "modelLibraryBtn",
        "modelDetailsModal", "modelDetailsContent", "modelLibraryModal", "modelLibraryContent",
        "openDetailBtn", "downloadAssetBtn", "detailModal", "detailCanvas", "detailSummary",
        "detailDetectionList", "detailShowAllBtn", "detailHideAllBtn", "downloadDetailBtn",
        "detailModalTitle", "randomCallBtn", "randomCallModal", "randomCallCanvas", "randomCallMeta",
        "stopTaskBtn",
    ].forEach((id) => {
        els[id] = document.getElementById(id);
    });
    els.navItems = [...document.querySelectorAll(".nav-item")];
    els.dialogBackdrops = [...document.querySelectorAll(".dialog-backdrop")];
    els.dialogClosers = [...document.querySelectorAll("[data-close-dialog]")];
    els.previewSurface = document.querySelector(".preview-surface");
}

function bindEvents() {
    els.navItems.forEach((item) => item.addEventListener("click", () => switchMode(item.dataset.mode)));
    els.pickFileBtn.addEventListener("click", triggerFileSelect);
    els.fileInput.addEventListener("change", (event) => setSelectedFiles([...event.target.files]));
    els.dropzone.addEventListener("dragover", (event) => {
        if (getState().mode === "webcam") return;
        event.preventDefault();
        els.dropzone.classList.add("dragover");
    });
    els.dropzone.addEventListener("dragleave", () => els.dropzone.classList.remove("dragover"));
    els.dropzone.addEventListener("drop", (event) => {
        if (getState().mode === "webcam") return;
        event.preventDefault();
        els.dropzone.classList.remove("dragover");
        setSelectedFiles([...event.dataTransfer.files]);
    });
    els.runBtn.addEventListener("click", runDetection);
    els.stopTaskBtn.addEventListener("click", stopCurrentVideoTask);
    els.randomCallBtn.addEventListener("click", randomCallCurrentFrame);
    els.confidenceInput.addEventListener("input", () => setState({ confidence: Number(els.confidenceInput.value) }));
    els.iouInput.addEventListener("input", () => setState({ iou: Number(els.iouInput.value) }));
    els.frameSkipInput.addEventListener("change", () => setState({ frameSkip: Number(els.frameSkipInput.value) }));
    els.cameraIndexInput.addEventListener("change", () => setState({ cameraIndex: Number(els.cameraIndexInput.value) }));
    els.scanModelsBtn.addEventListener("click", () => loadModels(true));
    els.applyModelsBtn.addEventListener("click", applyModels);
    els.saveParamsBtn.addEventListener("click", saveParams);
    els.refreshHistoryBtn.addEventListener("click", loadHistory);
    els.historyFilter.addEventListener("input", renderHistory);
    els.historyModeFilter.addEventListener("change", renderHistory);
    els.historySort.addEventListener("change", renderHistory);
    els.historyShowcaseOnly.addEventListener("change", renderHistory);
    els.historySelectShowcaseBtn.addEventListener("click", selectVisibleShowcaseTasks);
    els.historyClearSelectedBtn.addEventListener("click", clearHistorySelection);
    els.historyExportSelectedBtn.addEventListener("click", exportSelectedReports);
    els.historyLatestBtn.addEventListener("click", () => focusSpecialHistoryTask("recent"));
    els.historyTopBtn.addEventListener("click", () => focusSpecialHistoryTask("detections"));
    els.showOriginalBtn.addEventListener("click", () => toggleImageType("original"));
    els.showAnnotatedBtn.addEventListener("click", () => toggleImageType("annotated"));
    els.reportLink.addEventListener("click", openReport);
    els.startWebcamBtn.addEventListener("click", startWebcam);
    els.stopWebcamBtn.addEventListener("click", stopWebcam);
    els.probeWebcamBtn.addEventListener("click", probeWebcam);
    els.logoutBtn.addEventListener("click", logout);
    els.settingsBtn.addEventListener("click", openSettingsDialog);
    els.saveSettingsBtn.addEventListener("click", saveSettings);
    els.resetSettingsBtn.addEventListener("click", resetSettings);
    els.currentModelDetailsBtn.addEventListener("click", openCurrentModelDialog);
    els.modelLibraryBtn.addEventListener("click", openModelLibraryDialog);
    els.openDetailBtn.addEventListener("click", openDetailViewer);
    els.downloadAssetBtn.addEventListener("click", downloadCurrentAsset);
    els.detailShowAllBtn.addEventListener("click", () => setInspectorVisibility(true));
    els.detailHideAllBtn.addEventListener("click", () => setInspectorVisibility(false));
    els.downloadDetailBtn.addEventListener("click", () => downloadCanvas(els.detailCanvas, "inspection-view"));
    els.dialogClosers.forEach((node) => node.addEventListener("click", () => closeDialog(node.dataset.closeDialog)));
    els.dialogBackdrops.forEach((backdrop) => {
        backdrop.addEventListener("click", (event) => {
            if (event.target === backdrop) {
                closeDialog(backdrop.id);
            }
        });
    });
    document.addEventListener("keydown", handleDialogKeydown);
}

async function bootstrap() {
    await loadConfig();
    await Promise.all([loadOverview(), loadHistory()]);
    if (getState().uiSettings?.auto_scan_models ?? true) {
        await loadModels(false);
    }
    historyPoller = setInterval(loadHistory, getHistoryPollMs());
}

async function loadOverview() {
    try {
        const response = await request("/api/dashboard/overview");
        setState({ overview: response.data });
    } catch (error) {
        pushNotification(error.message, "danger");
    }
}

async function loadConfig() {
    try {
        const [paramsRes, settingsRes, configRes, modelsInfoRes] = await Promise.all([
            request("/api/user/config/detection-params"),
            request("/api/user/settings"),
            request("/api/config"),
            request("/api/models/info"),
        ]);
        const params = paramsRes.data.params || {};
        const uiSettings = { ...DEFAULT_UI_SETTINGS, ...(settingsRes.data.settings || {}) };
        setState({
            confidence: Number(params.confidence ?? 0.25),
            iou: Number(params.iou ?? 0.45),
            frameSkip: Number(params.frame_skip ?? 2),
            cameraIndex: 0,
            modelInfo: modelsInfoRes.data,
            uiSettings,
            configBundle: configRes.data,
        });
        syncSettingsForm();
        switchMode(getInitialMode(uiSettings.default_mode));
    } catch (error) {
        pushNotification(`加载配置失败: ${error.message}`, "danger");
    }
}

async function loadModels(forceScan = false) {
    try {
        const response = await request(`/api/models/scan${forceScan ? "?force=1" : ""}`);
        setState({ models: response.data.models || [] });
        populateModelSelects();
        if (forceScan) {
            pushNotification(`已扫描 ${response.data.total || 0} 个候选模型`, "success");
        }
    } catch (error) {
        pushNotification(`模型扫描失败: ${error.message}`, "danger");
    }
}

async function applyModels() {
    const student = els.studentModelSelect.value;
    const teacher = els.teacherModelSelect.value;
    const modelInfo = getState().modelInfo || {};
    const lockedRoles = [];
    try {
        if (student && !modelInfo.student?.selection_locked) {
            await request("/api/models/load", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ type: "student", model: student }),
            });
        } else if (student && modelInfo.student?.selection_locked) {
            lockedRoles.push("学生");
        }
        if (teacher && !modelInfo.teacher?.selection_locked) {
            await request("/api/models/load", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ type: "teacher", model: teacher }),
            });
        } else if (teacher && modelInfo.teacher?.selection_locked) {
            lockedRoles.push("教师");
        }
        if (!student && !teacher) {
            pushNotification("请先选择模型", "danger");
            return;
        }
        const info = await request("/api/models/info");
        setState({ modelInfo: info.data });
        populateModelSelects();
        if (lockedRoles.length) {
            pushNotification(`${lockedRoles.join("、")}模型已由当前启动入口固定`, "info");
        } else {
            pushNotification("模型配置已更新", "success");
        }
    } catch (error) {
        pushNotification(`模型应用失败: ${error.message}`, "danger");
    }
}

async function saveParams() {
    try {
        await request("/api/user/config/detection-params", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                confidence: getState().confidence,
                iou: getState().iou,
                frame_skip: getState().frameSkip,
            }),
        });
        pushNotification("检测参数已保存", "success");
    } catch (error) {
        pushNotification(`保存失败: ${error.message}`, "danger");
    }
}

async function loadHistory() {
    if (historyRefreshInFlight) return;
    historyRefreshInFlight = true;
    try {
        const response = await request(`/api/tasks/recent?limit=${getHistoryRecentLimit()}`);
        const tasks = response.data.tasks || [];
        const taskPayloads = Object.fromEntries(
            tasks.map((task) => [task.task_id, normalizeTaskPayload(task)])
        );
        setState({
            recentTasks: tasks,
            taskPayloads,
            selectedHistoryIds: (getState().selectedHistoryIds || []).filter((taskId) => tasks.some((task) => String(task.task_id) === String(taskId))),
        });
        renderHistory();
    } catch (error) {
        pushNotification(`历史记录加载失败: ${error.message}`, "danger");
    } finally {
        historyRefreshInFlight = false;
    }
}

function switchMode(mode) {
    const modeContent = MODE_CONTENT[mode] || MODE_CONTENT.image;
    stopPolling();
    setState({
        mode,
        selectedFiles: [],
        currentTask: null,
        activeTaskPayload: null,
        activeAssetIndex: 0,
        activeImageType: "annotated",
        webcamDiagnostics: null,
    });
    els.fileInput.value = "";
    els.app.dataset.mode = mode;
    els.navItems.forEach((item) => item.classList.toggle("active", item.dataset.mode === mode));
    els.workspaceTitle.textContent = modeContent.title;
    els.modeBadge.textContent = formatModeBadge(mode);
    els.modeIntro.textContent = modeContent.intro;
    els.dropzoneHint.textContent = modeContent.hint;
    els.dropzoneTitle.textContent = modeContent.dropTitle;
    els.runBtn.textContent = modeContent.runLabel;
    els.pickFileBtn.textContent = mode === "video" ? "选择视频" : "选择文件";
    els.pickFileBtn.classList.toggle("hidden", mode === "webcam");
    els.webcamControls.classList.toggle("hidden", mode !== "webcam");
    els.webcamDiagnostics.classList.toggle("hidden", mode !== "webcam");
    els.runBtn.classList.toggle("hidden", mode === "webcam");
    renderSelectedFiles();
    clearPreview(modeContent.emptyTitle, modeContent.emptyCopy);
    renderTaskPayload(null);
    renderTaskState(null);
    renderWebcamDiagnostics();
    renderActionButtons();
}

function getInitialMode(defaultMode) {
    const auditMode = new URLSearchParams(window.location.search).get("audit_mode");
    if (VALID_MODES.has(auditMode)) return auditMode;
    if (VALID_MODES.has(defaultMode)) return defaultMode;
    return "image";
}

function stopPolling() {
    clearInterval(taskPoller);
    clearInterval(webcamPoller);
}

function getHistoryPollMs() {
    return Number(getState().configBundle?.history_poll_interval_ms || 10000);
}

function getTaskPollMs() {
    return Number(getState().configBundle?.task_poll_interval_ms || 2500);
}

function getHistoryRecentLimit() {
    return Number(getState().configBundle?.history_recent_limit || 18);
}

function triggerFileSelect() {
    const mode = getState().mode;
    els.fileInput.multiple = mode === "batch";
    els.fileInput.accept = mode === "video" ? "video/*" : "image/*";
    els.fileInput.click();
}

function setSelectedFiles(files) {
    if (getState().mode === "image" || getState().mode === "video") {
        files = files.slice(0, 1);
    }
    setState({ selectedFiles: files });
    renderSelectedFiles();
}

function renderSelectedFiles() {
    const { selectedFiles, mode } = getState();
    if (mode === "webcam") {
        els.selectedFiles.innerHTML = "";
        return;
    }
    const emptyText = {
        image: "当前还没有待检测图片",
        batch: "当前还没有批量任务素材",
        video: "当前还没有待检测视频",
    }[mode] || "当前还没有待检测文件";
    els.selectedFiles.innerHTML = selectedFiles.length
        ? selectedFiles.map((file) => `
            <div class="file-chip">
                <strong>${truncate(formatFileLabel(file.name, "待检测文件"), 24)}</strong>
                <small>已加入当前任务</small>
                <span>${Math.round(file.size / 1024)} KB</span>
            </div>
        `).join("")
        : `<div class="file-chip empty">${emptyText}</div>`;
}

async function runDetection() {
    const { mode, selectedFiles } = getState();
    if (mode !== "webcam" && !selectedFiles.length) {
        pushNotification("请先选择文件", "danger");
        return;
    }

    try {
        let response;
        const formData = createFormData(getState(), selectedFiles);
        if (mode === "image") {
            response = await request("/api/detect/image", { method: "POST", body: formData });
            applyResult(await loadTaskPayload(response.data.task_id));
        } else if (mode === "batch") {
            response = await request("/api/detect/batch", { method: "POST", body: formData });
            applyResult(await loadTaskPayload(response.data.task_id));
        } else if (mode === "video") {
            response = await request("/api/detect/video", { method: "POST", body: formData });
            setState({
                currentTask: { task_id: response.data.task_id, status: "processing", task_type: "video", file_name: selectedFiles[0]?.name },
                activeTaskPayload: null,
                activeAssetIndex: 0,
                activeImageType: "annotated",
            });
            clearPreview("视频任务处理中", "正在轮询生成中的检测流，可随时停止任务。");
            startVideoPolling(response.data.task_id);
        }
        await loadHistory();
        pushNotification("任务已提交", "success");
    } catch (error) {
        pushNotification(`检测失败: ${error.message}`, "danger");
    }
}

async function loadTaskPayload(taskId) {
    return loadTaskById(taskId, request);
}

function startVideoPolling(taskId) {
    clearInterval(taskPoller);
    const refresh = async () => {
        try {
            const snapshot = await loadVideoPollingSnapshot({
                taskId,
                request,
                normalizeTaskPayload,
            });
            setState(snapshot.statePatch);
            if (snapshot.processing) {
                showMedia("image", `/api/streams/video/${taskId}/feed`);
                renderTaskState(snapshot.metrics);
                renderActionButtons();
            } else {
                if (snapshot.taskPayload) {
                    updatePreview(snapshot.taskPayload);
                    renderTaskPayload(snapshot.taskPayload);
                }
                renderTaskState(snapshot.metrics);
                renderActionButtons();
                clearInterval(taskPoller);
                await loadHistory();
            }
        } catch (error) {
            clearInterval(taskPoller);
            pushNotification(`视频轮询失败: ${error.message}`, "danger");
        }
    };
    refresh();
    taskPoller = setInterval(refresh, getTaskPollMs());
}

async function stopCurrentVideoTask() {
    const taskId = getState().currentTask?.task_id;
    if (!taskId) return;
    try {
        await stopVideoTask(taskId, request);
        pushNotification("已请求停止视频检测", "info");
        window.setTimeout(() => startVideoPolling(taskId), 300);
    } catch (error) {
        pushNotification(`停止失败: ${error.message}`, "danger");
    }
}

async function probeWebcam() {
    try {
        pushNotification("正在诊断服务端摄像头，这一步可能需要几秒", "info");
        const response = await request(
            `/api/streams/webcam/diagnostics?camera_index=${encodeURIComponent(getState().cameraIndex)}`,
            { timeoutMs: WEBCAM_DIAGNOSTICS_TIMEOUT_MS }
        );
        setState({ webcamDiagnostics: response.data });
        renderWebcamDiagnostics();
        const selected = response.data?.selected;
        if (selected) {
            setState({ cameraIndex: Number(selected.index) });
            pushNotification(`找到可用摄像头：索引 ${selected.index}，后端 ${selected.backend}`, "success");
        } else {
            pushNotification("未找到可读取画面的摄像头组合", "danger");
        }
    } catch (error) {
        pushNotification(`摄像头诊断失败: ${error.message}`, "danger");
    }
}

function findPreferredWebcamAttempt(diagnostics, cameraIndex) {
    const attempts = diagnostics?.attempts || [];
    return attempts.find((item) => Number(item.index) === Number(cameraIndex))
        || attempts.find((item) => item.success)
        || attempts[0]
        || null;
}

function buildServerWebcamStartRequestOptions() {
    return {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            camera_index: getState().cameraIndex,
            confidence: getState().confidence,
            iou: getState().iou,
        }),
    };
}

async function requestServerWebcamStart() {
    return request("/api/streams/webcam/start", buildServerWebcamStartRequestOptions());
}

async function requestServerWebcamStartWithRetry() {
    try {
        return await requestServerWebcamStart();
    } catch (error) {
        pushNotification(`服务端摄像头启动未完成，正在重试: ${error.message}`, "info");
        await request("/api/streams/webcam/stop", { method: "POST" }).catch(() => ({}));
        await waitMs(WEBCAM_SERVER_START_RETRY_DELAY_MS);
        return requestServerWebcamStart();
    }
}

async function startWebcam() {
    setState({ webcamStarting: true });
    renderActionButtons();
    try {
        pushNotification("正在准备摄像头，服务端诊断超时后会自动切到浏览器直连", "info");
        const diagnostics = getState().webcamDiagnostics || await request(
            `/api/streams/webcam/diagnostics?camera_index=${encodeURIComponent(getState().cameraIndex)}`,
            { timeoutMs: WEBCAM_DIAGNOSTICS_TIMEOUT_MS }
        ).then((response) => response.data);
        setState({ webcamDiagnostics: diagnostics });
        renderWebcamDiagnostics();
        const preferredAttempt = findPreferredWebcamAttempt(diagnostics, getState().cameraIndex);
        if (preferredAttempt && !preferredAttempt.success) {
            pushNotification(
                `服务端摄像头不可用，直接切换浏览器直连: ${preferredAttempt.error || "无法读取画面"}`,
                "info"
            );
            await startBrowserWebcamFallback(preferredAttempt.error || "服务端无法读取摄像头画面");
            return;
        }
        const response = await requestServerWebcamStartWithRetry();
        setState({ currentTask: { task_id: response.data.task_id, status: "processing", task_type: "webcam", file_name: `camera_${response.data.camera_index}` }, activeTaskPayload: null });
        showMedia("image", "/api/streams/webcam/feed");
        els.videoMeta.innerHTML = `<span class="pill processing">实时巡检中</span><span class="pill">机位 ${response.data.camera_index} / ${response.data.backend}</span>`;
        startWebcamPolling(response.data.task_id);
        pushNotification("摄像头已启动", "success");
    } catch (error) {
        pushNotification(`服务端摄像头启动未完成，尝试浏览器直连: ${error.message}`, "info");
        await startBrowserWebcamFallback(error.message);
    } finally {
        setState({ webcamStarting: false });
        renderActionButtons();
    }
}

async function stopWebcam() {
    try {
        if (!browserWebcamSession.active && getState().currentTask?.task_type !== "webcam") {
            pushNotification("当前没有正在运行的摄像头任务", "info");
            return;
        }
        if (browserWebcamSession.active) {
            await stopBrowserWebcamFallback();
            return;
        }
        const response = await request("/api/streams/webcam/stop", { method: "POST" });
        clearInterval(webcamPoller);
        await restoreStoppedTask(response.data?.task_id, "巡检已停止", "可以重新启动摄像头，或从历史记录回看检测结果。");
        pushNotification("摄像头已停止", "success");
        await loadHistory();
    } catch (error) {
        pushNotification(`摄像头停止失败: ${error.message}`, "danger");
    }
}

function startWebcamPolling(taskId) {
    clearInterval(webcamPoller);
    const refresh = async () => {
        try {
            const [statsRes, taskRes] = await Promise.all([
                request("/api/streams/webcam/metrics"),
                request(`/api/tasks/${taskId}`),
            ]);
            const snapshot = resolveWebcamPollingSnapshot({
                task: taskRes.data,
                metrics: statsRes.data,
                normalizeTaskPayload,
                currentActiveTaskPayload: getState().activeTaskPayload,
            });
            setState(snapshot.statePatch);
            if (!snapshot.processing) {
                clearInterval(webcamPoller);
                await loadHistory();
            }
            renderTaskState(snapshot.metrics);
            renderTaskPayload(getState().activeTaskPayload);
            renderActionButtons();
        } catch (error) {
            clearInterval(webcamPoller);
            pushNotification(`实时巡检轮询失败: ${error.message}`, "danger");
        }
    };
    refresh();
    webcamPoller = setInterval(refresh, getTaskPollMs());
}

async function openHistoryTask(taskId) {
    try {
        setPreviewLoading(true);
        const task = await loadTaskPayload(taskId);
        applyResult(task);
        focusHistoryTask(taskId);
        const followup = resolveHistoryTaskFollowup(task);
        if (followup?.poller === "video") {
            startVideoPolling(followup.taskId);
        } else if (followup?.poller === "webcam") {
            startWebcamPolling(followup.taskId);
        }
    } catch (error) {
        pushNotification(`加载任务详情失败: ${error.message}`, "danger");
    } finally {
        setPreviewLoading(false);
    }
}

function applyResult(task, taskPayload = task) {
    setState(buildAppliedTaskState({
        task,
        taskPayload,
        normalizeTaskPayload,
    }));
    renderTaskPayload(getState().activeTaskPayload);
    renderTaskState(task);
    updatePreview(getState().activeTaskPayload);
    renderHistory();
    renderActionButtons();
}

function updatePreview(summary) {
    const asset = resolveActiveAsset(summary, getState().activeAssetIndex);
    const source = getState().activeImageType === "original" ? asset?.original : asset?.result;
    if (!source) {
        clearPreview("当前没有可显示的资源", "请切换资源类型或查看其他任务。");
    } else {
        showMedia(detectMediaType(source), source);
    }
    els.reportLink.href = summary?.assets?.report || "#";
    renderResultGallery(summary);
    updatePreviewActions(asset);
    renderActionButtons();
}

function renderResultGallery(summary) {
    const items = summary?.assets?.results || [];
    if (!items.length) {
        els.resultGallery.innerHTML = "";
        els.resultGallery.classList.add("hidden");
        return;
    }
    els.resultGallery.classList.remove("hidden");
    els.resultGallery.innerHTML = items.map((item, index) => `
        <div class="gallery-item ${index === getState().activeAssetIndex ? "active" : ""}" data-index="${index}">
            <strong>${truncate(formatFileLabel(item.filename, `结果 ${index + 1}`), 18)}</strong>
            <small>切换查看第 ${index + 1} 项结果</small>
        </div>
    `).join("");
    [...els.resultGallery.querySelectorAll(".gallery-item")].forEach((node) => {
        node.addEventListener("click", () => {
            setPreviewLoading(true);
            setState({ activeAssetIndex: Number(node.dataset.index) });
            updatePreview(getState().activeTaskPayload);
            window.setTimeout(() => setPreviewLoading(false), 180);
        });
    });
}

function toggleImageType(type) {
    setPreviewLoading(true);
    setState({ activeImageType: type });
    els.showOriginalBtn.classList.toggle("active", type === "original");
    els.showAnnotatedBtn.classList.toggle("active", type === "annotated");
    updatePreview(getState().activeTaskPayload);
    window.setTimeout(() => setPreviewLoading(false), 180);
}

function detectMediaType(source) {
    return /\.(mp4|avi|mov|mkv)$/i.test(source || "") ? "video" : "image";
}

function showMedia(type, src) {
    els.emptyState.style.display = "none";
    if (type === "video") {
        els.resultImage.style.display = "none";
        els.resultImage.removeAttribute("src");
        els.resultVideo.classList.remove("hidden");
        els.resultVideo.src = src;
        els.resultVideo.load();
        els.resultVideo.onloadeddata = () => setPreviewLoading(false);
        return;
    }
    els.resultVideo.pause();
    els.resultVideo.removeAttribute("src");
    els.resultVideo.classList.add("hidden");
    els.resultImage.style.display = "block";
    els.resultImage.src = src;
    if (els.resultImage.complete) {
        setPreviewLoading(false);
    } else {
        els.resultImage.onload = () => setPreviewLoading(false);
    }
}

function clearPreview(title, copy) {
    els.resultImage.style.display = "none";
    els.resultImage.removeAttribute("src");
    els.resultVideo.pause();
    els.resultVideo.removeAttribute("src");
    els.resultVideo.classList.add("hidden");
    els.emptyState.style.display = "grid";
    els.emptyState.querySelector("h3").textContent = title;
    els.emptyState.querySelector("p").textContent = copy;
    els.videoMeta.innerHTML = "";
    els.resultGallery.innerHTML = "";
    els.resultGallery.classList.add("hidden");
    updatePreviewActions(null);
    setPreviewLoading(false);
}

function updatePreviewActions(asset) {
    els.showOriginalBtn.disabled = !asset?.original;
    els.showAnnotatedBtn.disabled = !asset?.result;
}

function canOpenReportForTask(task, summary) {
    if (!task) return false;
    if (task.status === "processing") return false;
    return Boolean(summary?.task_id || task.task_id);
}

function canDownloadCurrentAsset(task, summary) {
    if (!task) return false;
    const asset = resolveActiveAsset(summary, getState().activeAssetIndex);
    return Boolean(asset?.original || asset?.result);
}

function historyCapabilityBadge(task, summary) {
    if (!task) return "任务";
    if (task.status === "processing") return "处理中";
    if (task.status === "failed") return summary?.task_id ? "部分结果" : "失败";
    return canOpenReportForTask(task, summary) ? "可导出" : "已完成";
}

async function logout() {
    await request("/api/auth/logout", { method: "POST" });
    window.location.href = "/login";
}

async function openReport(event) {
    event.preventDefault();
    const taskId = getState().currentTask?.task_id;
    const task = getState().currentTask;
    const summary = getState().activeTaskPayload;
    if (!taskId || !canOpenReportForTask(task, summary)) {
        pushNotification("当前没有可生成报告的任务", "danger");
        return;
    }
    try {
        const response = await request(`/api/tasks/${taskId}/report`);
        window.open(response.data.report_url, "_blank", "noopener");
    } catch (error) {
        pushNotification(`报告生成失败: ${error.message}`, "danger");
    }
}

function populateModelSelects() {
    const { models = [], modelInfo } = getState();
    const studentLocked = Boolean(modelInfo?.student?.selection_locked);
    const teacherLocked = Boolean(modelInfo?.teacher?.selection_locked);
    const buildOptions = (selectedPath) => ['<option value="">请选择模型</option>', ...models.map((model) => {
        const value = model.relative_path || model.filename;
        const selected = selectedPath && selectedPath.includes(value) ? "selected" : "";
        return `<option value="${value}" ${selected}>${truncate(formatModelDetail(value), 28)}</option>`;
    })].join("");
    if (models.length) {
        els.studentModelSelect.innerHTML = buildOptions(modelInfo?.student?.path);
        els.teacherModelSelect.innerHTML = buildOptions(modelInfo?.teacher?.path);
    }
    els.studentModelSelect.disabled = studentLocked;
    els.teacherModelSelect.disabled = teacherLocked;
    els.applyModelsBtn.disabled = studentLocked && teacherLocked;
    els.modelMeta.innerHTML = `
        <div>
            <strong>${formatModelName(modelInfo?.student?.path, "student")}</strong>
            <span>${truncate(formatModelDetail(modelInfo?.student?.path || "未加载"), 22)}</span>
            <small>${modelInfo?.student?.selection_source_label || "未记录来源"}${modelInfo?.student?.selection_locked ? " · 已锁定" : ""}</small>
        </div>
        <div>
            <strong>${formatModelName(modelInfo?.teacher?.path, "teacher")}</strong>
            <span>${truncate(formatModelDetail(modelInfo?.teacher?.path || "未加载"), 22)}</span>
            <small>${modelInfo?.teacher?.selection_source_label || "未记录来源"}${modelInfo?.teacher?.selection_locked ? " · 已锁定" : ""}</small>
        </div>
    `;
}

function render(state) {
    els.confidenceInput.value = state.confidence;
    els.iouInput.value = state.iou;
    els.frameSkipInput.value = state.frameSkip;
    els.cameraIndexInput.value = state.cameraIndex;
    els.confidenceLabel.textContent = formatNumber(state.confidence, 2);
    els.iouLabel.textContent = formatNumber(state.iou, 2);
    renderTaskPayload(state.activeTaskPayload);
    renderNotifications();
    populateModelSelects();
    renderWebcamDiagnostics();
    renderOverviewHighlights();
    renderLiveBanner();
    renderActionButtons();
}

function renderOverviewHighlights() {
    const { overview, models = [], modelInfo, recentTasks = [] } = getState();
    const loadedCount = [modelInfo?.student?.loaded, modelInfo?.teacher?.loaded].filter(Boolean).length;
    const classCount = (modelInfo?.student?.classes?.length || 0) + (modelInfo?.teacher?.classes?.length || 0);
    const recentCount = recentTasks.length || overview?.recent_tasks?.length || 0;
    const recentLabel = recentTasks[0]?.task_type ? `最近任务：${formatTaskType(recentTasks[0].task_type)}` : "可从历史区快速回看结果";
    const modeSummary = {
        image: "单张素材快速验证",
        batch: "批量素材统一处理",
        video: "连续视频分析流程",
        webcam: "实时机位巡检模式",
    }[getState().mode];
    els.overviewHighlights.innerHTML = `
        <article class="overview-card accent">
            <span>当前模式</span>
            <strong>${formatTaskType(getState().mode)}</strong>
            <small>${modeSummary}</small>
        </article>
        <article class="overview-card">
            <span>模型状态</span>
            <strong>${loadedCount}/2 已就绪</strong>
            <small>${models.length} 个候选模型，${classCount} 个标签</small>
        </article>
        <article class="overview-card">
            <span>最近任务</span>
            <strong>${recentCount}</strong>
            <small>${overview?.username ? `${overview.username} · ${recentLabel}` : recentLabel}</small>
        </article>
    `;
}

function renderTaskPayload(summary) {
    if (!summary) {
        renderAnalysisNarrative(null);
        renderCurrentResultTags(null);
        renderSpeechTemplate(null);
        renderTaskSummaryCards({
            node: els.summaryCards,
            summary: null,
            currentMode: getState().mode,
            formatNumber,
            formatTaskType,
        });
        renderCharts({ student_behavior_stats: {}, teacher_behavior_stats: {} });
        return;
    }
    renderTaskSummaryCards({
        node: els.summaryCards,
        summary,
        currentMode: getState().mode,
        formatNumber,
        formatTaskType,
    });
    renderAnalysisNarrative(summary);
    renderCurrentResultTags(summary);
    renderSpeechTemplate(summary);
        renderTaskVideoMeta({
        node: els.videoMeta,
        summary,
        formatStatus,
        truncate,
        formatFileLabel,
        formatSummaryTone,
    });
    renderCharts(summary);
}

function renderTaskState(extra = null) {
    const task = getState().currentTask;
    if (!task) {
        renderTaskStatePanel({
            node: els.taskState,
            task: null,
            currentMode: getState().mode,
            metrics: {},
            statusPill,
            formatTaskType,
            formatStatus,
            formatNumber,
        });
        renderSystemStats({});
        return;
    }
    const metrics = extra || {};
    renderTaskStatePanel({
        node: els.taskState,
        task,
        currentMode: getState().mode,
        metrics,
        statusPill,
        formatTaskType,
        formatStatus,
        formatNumber,
    });
    renderSystemStats(metrics);
    renderLiveBanner(metrics);
}

function renderSystemStats(metrics = {}) {
    renderSystemStatsPanel({
        node: els.systemStats,
        task: getState().currentTask,
        currentMode: getState().mode,
        metrics,
        confidence: getState().confidence,
        iou: getState().iou,
        cameraIndex: getState().cameraIndex,
        formatTaskType,
        formatNumber,
        formatStatus,
    });
}

function renderAnalysisNarrative(summary) {
    renderAnalysisNarrativeBlock({
        node: els.analysisNarrative,
        summary,
        task: getState().currentTask,
        currentMode: getState().mode,
        formatTaskType,
        getTopBehaviors: (payload, limit) => getTopBehaviors(payload, limit, formatBehaviorLabel),
        formatNumber,
        buildBehaviorNarrative: (mode, topBehaviors, total) => buildBehaviorNarrative(mode, topBehaviors, total, formatNumber),
        getModeNarrativeLead: (mode, total, confidence, duration) => getModeNarrativeLead(mode, total, confidence, duration, formatNumber),
        renderBehaviorTags: (items) => renderBehaviorTags(items, formatNumber),
    });
}

function renderLiveBanner(metrics = {}) {
    renderLiveBannerPanel({
        bannerNode: els.webcamLiveBanner,
        statusNode: els.liveBannerStatus,
        statsNode: els.liveBannerStats,
        isWebcam: getState().mode === "webcam",
        task: getState().currentTask,
        metrics,
        cameraIndex: getState().cameraIndex,
        formatStatus,
        formatNumber,
    });
}

function renderCurrentResultTags(summary) {
    renderCurrentResultTagsBlock({
        node: els.currentResultTags,
        summary,
        getTopBehaviors: (payload, limit) => getTopBehaviors(payload, limit, formatBehaviorLabel),
        renderBehaviorTags: (items) => renderBehaviorTags(items, formatNumber),
    });
}

function renderSpeechTemplate(summary) {
    renderSpeechTemplateBlock({
        node: els.speechTemplate,
        summary,
        currentMode: getState().mode,
        getTopBehaviors: (payload, limit) => getTopBehaviors(payload, limit, formatBehaviorLabel),
        formatNumber,
        getModeNarrativeLead: (mode, total, confidence, duration) => getModeNarrativeLead(mode, total, confidence, duration, formatNumber),
        buildBehaviorNarrative: (mode, topBehaviors, total) => buildBehaviorNarrative(mode, topBehaviors, total, formatNumber),
    });
}

function renderNotifications() {
    els.notifications.innerHTML = getState().notifications.length
        ? getState().notifications.map((item) => `<div class="notification-item ${item.tone || "info"}"><small>${item.createdAt}</small><strong>${item.message}</strong></div>`).join("")
        : `<div class="notification-item">暂无通知</div>`;
}

function renderHistory() {
    const activeTaskId = getState().currentTask?.task_id;
    const taskPayloadMap = getState().taskPayloads || {};
    const selectedIds = new Set((getState().selectedHistoryIds || []).map(String));
    const tasks = getFilteredHistoryTasks();
    updateHistorySelectionMeta(tasks, selectedIds);
    renderHistoryList({
        container: els.historyList,
        tasks,
        activeTaskId,
        selectedIds,
        taskPayloadMap,
        statusPill,
        formatTaskType,
        historyCapabilityBadge,
        truncate,
        formatFileLabel,
        formatRelativeTimeLabel,
        buildTaskHighlight,
        renderBehaviorTags: (items) => renderBehaviorTags(items, formatNumber),
        getTopBehaviors: (payload, limit) => getTopBehaviors(payload, limit, formatBehaviorLabel),
        formatNumber,
        formatStatus,
        onOpenTask: openHistoryTask,
        onToggleSelection: toggleHistorySelection,
    });
}

function updateHistorySelectionMeta(tasks, selectedIds) {
    const meta = getHistorySelectionMeta(tasks, selectedIds, getState().exportingHistoryReports);
    const { totalSelected, exporting } = meta;
    els.historyExportSelectedBtn.disabled = totalSelected === 0 || exporting;
    els.historyExportSelectedBtn.textContent = exporting ? "正在导出..." : "导出选中报告";
    renderHistorySelectionMeta({
        metaNode: els.historySelectionMeta,
        exportButton: els.historyExportSelectedBtn,
        showcaseButton: els.historySelectShowcaseBtn,
        clearButton: els.historyClearSelectedBtn,
        text: meta.text,
        totalSelected,
        exporting,
    });
}

function getFilteredHistoryTasks() {
    return getFilteredHistoryTasksHelper({
        recentTasks: getState().recentTasks || [],
        taskPayloadMap: getState().taskPayloads || {},
        keyword: els.historyFilter.value || "",
        mode: els.historyModeFilter.value || "all",
        sort: els.historySort.value || "recent",
        showcaseOnly: els.historyShowcaseOnly.checked,
        isShowcaseTask: (task, taskPayload) => isShowcaseTaskHelper(task, taskPayload, (payload, limit) => getTopBehaviors(payload, limit, formatBehaviorLabel)),
        compareHistoryTasks: compareHistoryTasksHelper,
    });
}

function focusSpecialHistoryTask(kind) {
    const tasks = getFilteredHistoryTasks();
    const target = getSpecialHistoryTask(tasks, kind);
    if (target) focusHistoryTask(target.task_id);
}

function focusHistoryTask(taskId) {
    const node = els.historyList.querySelector(`.history-item[data-task-id="${taskId}"]`);
    if (node) {
        node.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
}

function toggleHistorySelection(taskId, checked) {
    setState({ selectedHistoryIds: toggleHistorySelectionIds(new Set((getState().selectedHistoryIds || []).map(String)), taskId, checked) });
    renderHistory();
}

function selectVisibleShowcaseTasks() {
    const visibleShowcaseIds = getVisibleShowcaseTaskIds(
        getFilteredHistoryTasks(),
        getState().taskPayloads || {},
        (task, taskPayload) => isShowcaseTaskHelper(task, taskPayload, (payload, limit) => getTopBehaviors(payload, limit, formatBehaviorLabel)),
    );
    if (!visibleShowcaseIds.length) {
        pushNotification("当前筛选结果里没有可展示素材", "info");
        return;
    }
    setState({ selectedHistoryIds: visibleShowcaseIds });
    renderHistory();
    pushNotification(`已选中 ${visibleShowcaseIds.length} 条可展示任务`, "success");
}

function clearHistorySelection() {
    if (!(getState().selectedHistoryIds || []).length) return;
    setState({ selectedHistoryIds: [] });
    renderHistory();
}

async function exportSelectedReports() {
    const taskIds = getState().selectedHistoryIds || [];
    if (!taskIds.length) {
        pushNotification("请先选择要导出的历史任务", "info");
        return;
    }
    try {
        setState({ exportingHistoryReports: true });
        const response = await request("/api/tasks/reports/batch", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ task_ids: taskIds }),
        });
        window.open(response.data.zip_url, "_blank", "noopener");
        pushNotification(`已生成 ${response.data.report_count} 份报告压缩包`, "success");
    } catch (error) {
        pushNotification(`批量导出失败: ${error.message}`, "danger");
    } finally {
        setState({ exportingHistoryReports: false });
        renderHistory();
    }
}

function setPreviewLoading(loading) {
    if (els.previewSurface) {
        els.previewSurface.classList.toggle("is-loading", loading);
    }
}

function restoreEmptyStoppedTaskState(emptyTitle, emptyCopy) {
    setState({ currentTask: null, activeTaskPayload: null });
    clearPreview(emptyTitle, emptyCopy);
    renderTaskState(null);
    renderTaskPayload(null);
    renderActionButtons();
}

async function restoreStoppedTask(taskId, emptyTitle, emptyCopy) {
    try {
        const restored = await restoreStoppedTaskState({
            taskId,
            emptyTitle,
            emptyCopy,
            loadTaskPayload,
            applyResult,
            focusHistoryTask,
            setEmptyState: restoreEmptyStoppedTaskState,
        });
        if (restored.restored) return;
    } catch (error) {
        pushNotification(`停止后加载结果失败: ${error.message}`, "danger");
    }
    restoreEmptyStoppedTaskState(emptyTitle, emptyCopy);
}

async function openDetailViewer() {
    const task = getState().currentTask;
    if (!task) {
        pushNotification("当前没有可细看的任务", "info");
        return;
    }
    try {
        const { imageUrl, detections, title } = await buildInspectorPayload({
            task,
            taskPayload: getState().activeTaskPayload,
            mode: task.task_type || getState().mode,
            browserWebcamActive: browserWebcamSession.active,
            browserWebcamOriginalImage: browserWebcamSession.latestOriginalImage,
            browserWebcamDetections: browserWebcamSession.latestDetections,
            activeAssetIndex: getState().activeAssetIndex,
            resolveActiveAsset,
            request,
            formatTaskType,
            formatFileLabel,
        });
        inspectorState.image = await loadImage(imageUrl);
        inspectorState.detections = detections.map((item, index) => ({ ...item, entryId: index }));
        inspectorState.visibility = detections.map(() => true);
        inspectorState.activeIndex = detections.length ? 0 : -1;
        inspectorState.title = title;
        els.detailModalTitle.textContent = title;
        renderInspector();
        openDialog("detailModal");
    } catch (error) {
        pushNotification(`结果细看失败: ${error.message}`, "danger");
    }
}

function renderInspector() {
    renderInspectorPanel({
        state: inspectorState,
        canvas: els.detailCanvas,
        summaryNode: els.detailSummary,
        listNode: els.detailDetectionList,
        uiSettings: getState().uiSettings || DEFAULT_UI_SETTINGS,
        drawCanvasWithDetections,
        formatBehaviorLabel,
        formatNumber,
        onSelectDetection: (index) => {
            inspectorState.activeIndex = index;
            renderInspector();
        },
        onToggleDetection: (index, checked) => {
            inspectorState.visibility[index] = checked;
            if (!checked && inspectorState.activeIndex === index) {
                inspectorState.activeIndex = inspectorState.visibility.findIndex(Boolean);
            } else if (checked) {
                inspectorState.activeIndex = index;
            }
            renderInspector();
        },
    });
}

function setInspectorVisibility(visible) {
    inspectorState.visibility = inspectorState.visibility.map(() => visible);
    renderInspector();
}

async function randomCallCurrentFrame() {
    const task = getState().currentTask;
    const summary = getState().activeTaskPayload;
    try {
        const payload = await getRandomCallPayload({
            task,
            taskPayload: summary,
            mode: task?.task_type || getState().mode,
            browserWebcamActive: browserWebcamSession.active,
            browserWebcamOriginalImage: browserWebcamSession.latestOriginalImage,
            browserWebcamDetections: browserWebcamSession.latestDetections,
            activeAssetIndex: getState().activeAssetIndex,
            resolveActiveAsset,
            request,
            formatTaskType,
        });
        const target = pickRandomHeadCandidate(payload.detections, isHeadCandidate);
        const image = await loadImage(payload.image);
        renderRandomCallResult({
            canvas: els.randomCallCanvas,
            metaNode: els.randomCallMeta,
            image,
            target,
            label: payload.label,
            drawCanvasWithDetections,
            formatBehaviorLabel,
            formatNumber,
        });
        openDialog("randomCallModal");
    } catch (error) {
        pushNotification(`随机点名失败: ${error.message}`, "danger");
    }
}

async function downloadCurrentAsset() {
    const task = getState().currentTask;
    const asset = resolveActiveAsset(getState().activeTaskPayload, getState().activeAssetIndex);
    const source = getState().activeImageType === "original" ? asset?.original : asset?.result;
    if (!source || !canDownloadCurrentAsset(task, getState().activeTaskPayload)) {
        pushNotification("当前没有可下载的资源", "info");
        return;
    }
    downloadUrl(source, `classroom-${getState().activeImageType}`);
}

function renderWebcamDiagnostics() {
    renderWebcamDiagnosticsPanel({
        node: els.webcamDiagnostics,
        mode: getState().mode,
        diagnostics: getState().webcamDiagnostics,
    });
}

function renderActionButtons() {
    const state = getState();
    const task = state.currentTask;
    const summary = state.activeTaskPayload;
    const mode = task?.task_type || state.mode;
    const hasAsset = canDownloadCurrentAsset(task, summary);
    const webcamMode = state.mode === "webcam";
    const webcamActive = (task?.task_type === "webcam" && task?.status === "processing") || browserWebcamSession.active;
    const webcamStarting = state.webcamStarting;
    const hasPendingFiles = (state.selectedFiles || []).length > 0;
    const runningDetection = task?.status === "processing" && task?.task_type !== "webcam";
    const activeDetections = browserWebcamSession.active ? browserWebcamSession.latestDetections : mergeDetectionsFromTaskPayload(summary);
    const canRandomCall = activeDetections.some((item) => isHeadCandidate(item.behavior));
    const canOpenReport = canOpenReportForTask(task, summary);
    els.stopTaskBtn.classList.toggle("hidden", !(task?.task_type === "video" && task?.status === "processing"));
    els.randomCallBtn.classList.toggle("hidden", !(task && (task.task_type === "webcam" || task.task_type === "video" || hasAsset)));
    els.randomCallBtn.disabled = !canRandomCall;
    els.openDetailBtn.disabled = !(task && (task.task_type === "image" || task.task_type === "batch" || task.task_type === "webcam" || task.task_type === "video"));
    els.downloadAssetBtn.disabled = !hasAsset;
    els.downloadAssetBtn.textContent = hasAsset ? "下载当前资源" : "等待可下载资源";
    els.reportLink.classList.toggle("hidden", !task);
    els.reportLink.classList.toggle("disabled", !canOpenReport);
    els.reportLink.setAttribute("aria-disabled", canOpenReport ? "false" : "true");
    els.startWebcamBtn.classList.toggle("hidden", !webcamMode || webcamActive);
    els.stopWebcamBtn.classList.toggle("hidden", !webcamMode || !webcamActive);
    els.startWebcamBtn.disabled = !webcamMode || webcamStarting || webcamActive;
    els.stopWebcamBtn.disabled = !webcamMode || webcamStarting || !webcamActive;
    els.probeWebcamBtn.disabled = !webcamMode || webcamStarting || webcamActive;
    els.runBtn.disabled = webcamMode || runningDetection || !hasPendingFiles;
    els.runBtn.textContent = runningDetection ? "检测进行中..." : (MODE_CONTENT[state.mode] || MODE_CONTENT.image).runLabel;
}

async function startBrowserWebcamFallback(reason = "") {
    if (!navigator.mediaDevices?.getUserMedia) {
        clearPreview("摄像头不可用", "当前浏览器环境不支持 getUserMedia。");
        pushNotification("当前浏览器不支持摄像头直连", "danger");
        return;
    }
    try {
        clearPreview("等待浏览器授权", "请在浏览器弹窗中允许摄像头访问。");
        els.videoMeta.innerHTML = `<span class="pill processing">等待浏览器授权</span><span class="pill">getUserMedia</span>`;
        pushNotification("正在请求浏览器摄像头权限", "info");
        resetBrowserWebcamSession();
        await startBrowserWebcamSession({
            session: browserWebcamSession,
            request,
            createVideoElement: () => document.createElement("video"),
            createCanvasElement: () => document.createElement("canvas"),
        });

        setState({
            currentTask: {
                task_id: browserWebcamSession.taskId,
                status: "processing",
                task_type: "webcam",
                file_name: "browser_camera",
                processed_frames: 0,
                total_frames: 0,
            },
            activeTaskPayload: null,
        });
        clearPreview("浏览器摄像头启动中", "正在建立浏览器直连采集链路。");
        await waitForBrowserWebcamFirstFrame();
        browserWebcamSession.timer = window.setInterval(() => {
            void captureBrowserWebcamFrame().catch(() => {});
        }, 900);
        pushNotification(reason ? `已切换到浏览器摄像头直连: ${reason}` : "已切换到浏览器摄像头直连", "success");
    } catch (error) {
        if (browserWebcamSession.taskId) {
            await failBrowserWebcamSession(error.message);
        } else {
            resetBrowserWebcamSession();
            clearPreview("摄像头不可用", error.message);
            renderActionButtons();
        }
        pushNotification(`浏览器摄像头直连失败: ${error.message}`, "danger");
    }
}

function waitMs(milliseconds) {
    return new Promise((resolve) => {
        window.setTimeout(resolve, milliseconds);
    });
}

async function waitForBrowserWebcamFirstFrame() {
    const deadline = Date.now() + BROWSER_WEBCAM_FIRST_FRAME_TIMEOUT_MS;
    while (browserWebcamSession.active && Date.now() < deadline) {
        const frame = await captureBrowserWebcamFrame({ silentFailure: true });
        if (frame) {
            return frame;
        }
        await waitMs(160);
    }
    throw new Error(`浏览器摄像头已授权，但在 ${(BROWSER_WEBCAM_FIRST_FRAME_TIMEOUT_MS / 1000).toFixed(1)} 秒内没有拿到首帧`);
}

async function failBrowserWebcamSession(message) {
    if (browserWebcamFailureInFlight) return;
    browserWebcamFailureInFlight = true;
    const taskId = browserWebcamSession.taskId;
    try {
        clearInterval(browserWebcamSession.timer);
        try {
            await stopBrowserWebcamSession({
                session: browserWebcamSession,
                request,
                getBrowserWebcamSessionStats,
                failureReason: message,
            });
        } catch (stopError) {
            console.warn("browser webcam failure finalization failed", stopError);
        }
    } finally {
        resetBrowserWebcamSession();
        browserWebcamFailureInFlight = false;
    }

    try {
        await restoreStoppedTask(taskId, "浏览器摄像头会话失败", message);
    } catch (restoreError) {
        console.warn("browser webcam failure restore failed", restoreError);
        clearPreview("浏览器摄像头会话失败", message);
    }
    await loadHistory().catch(() => {});
    renderActionButtons();
}

async function captureBrowserWebcamFrame({ silentFailure = false } = {}) {
    try {
        const frame = await captureBrowserWebcamSessionFrame({
            session: browserWebcamSession,
            request,
            mergeDetections,
            getBrowserWebcamSessionStats,
            buildBrowserWebcamTaskPayload,
        });
        if (!frame) return null;
        const { stats, taskPayload, annotatedImage, processedFrames } = frame;
        setState({
            activeTaskPayload: taskPayload,
            currentTask: {
                task_id: browserWebcamSession.taskId,
                task_type: "webcam",
                status: "processing",
                file_name: "browser_camera",
                processed_frames: browserWebcamSession.processedFrames,
                total_frames: browserWebcamSession.processedFrames,
            },
        });
        showMedia("image", annotatedImage);
        els.videoMeta.innerHTML = `<span class="pill processing">浏览器直连中</span><span class="pill">当前帧 ${processedFrames}</span>`;
        renderTaskPayload(taskPayload);
        renderTaskState({
            fps: stats.fps,
            total_detections: stats.totalDetections,
            processed_frames: stats.processedFrames,
            total_frames: stats.processedFrames,
            camera_index: "browser",
            backend: "getUserMedia",
            eta_seconds: null,
        });
        renderHistory();
        renderActionButtons();
        return frame;
    } catch (error) {
        await failBrowserWebcamSession(error.message);
        if (!silentFailure) {
            pushNotification(`浏览器摄像头采集失败: ${error.message}`, "danger");
        }
        throw error;
    }
}

async function stopBrowserWebcamFallback() {
    if (!browserWebcamSession.active) return;
    const taskId = browserWebcamSession.taskId;
    let noticeMessage = "浏览器摄像头会话已结束，可以从历史记录回看摘要。";
    let noticeLevel = "success";
    try {
        await stopBrowserWebcamSession({
            session: browserWebcamSession,
            request,
            getBrowserWebcamSessionStats,
        });
    } catch (error) {
        noticeMessage = error.message;
        noticeLevel = "danger";
    } finally {
        resetBrowserWebcamSession();
    }
    await restoreStoppedTask(
        taskId,
        noticeLevel === "success" ? "巡检已停止" : "浏览器摄像头会话失败",
        noticeMessage,
    );
    pushNotification(
        noticeLevel === "success" ? "浏览器摄像头直连已停止" : `浏览器摄像头会话结束失败: ${noticeMessage}`,
        noticeLevel,
    );
    await loadHistory();
}

function resetBrowserWebcamSession() {
    resetBrowserWebcamSessionState(browserWebcamSession);
}

window.classroomAppControls = {
    probeWebcam,
    startWebcam,
    stopWebcam,
};

function openSettingsDialog() {
    syncSettingsForm();
    openDialog("settingsModal");
}

function syncSettingsForm() {
    const settings = { ...DEFAULT_UI_SETTINGS, ...(getState().uiSettings || {}) };
    els.settingDefaultMode.value = settings.default_mode;
    els.settingAutoScan.checked = Boolean(settings.auto_scan_models);
    els.settingShowConfidence.checked = Boolean(settings.show_confidence);
    els.settingShowLabels.checked = Boolean(settings.show_bbox_labels);
}

async function saveSettings() {
    const payload = {
        default_mode: els.settingDefaultMode.value,
        auto_scan_models: els.settingAutoScan.checked,
        show_confidence: els.settingShowConfidence.checked,
        show_bbox_labels: els.settingShowLabels.checked,
    };
    try {
        const response = await request("/api/user/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const settings = { ...DEFAULT_UI_SETTINGS, ...(response.data.settings || {}) };
        setState({ uiSettings: settings });
        els.settingsFeedback.textContent = "设置已保存。";
        pushNotification("界面设置已保存", "success");
        if (settings.default_mode !== getState().mode) {
            switchMode(settings.default_mode);
        } else {
            render(getState());
        }
    } catch (error) {
        els.settingsFeedback.textContent = `保存失败：${error.message}`;
        pushNotification(`设置保存失败: ${error.message}`, "danger");
    }
}

async function resetSettings() {
    try {
        await request("/api/user/config/reset", { method: "POST" });
        await loadConfig();
        els.settingsFeedback.textContent = "设置已重置为默认值。";
        pushNotification("界面设置已重置", "success");
    } catch (error) {
        els.settingsFeedback.textContent = `重置失败：${error.message}`;
        pushNotification(`重置失败: ${error.message}`, "danger");
    }
}

function openCurrentModelDialog() {
    const modelInfo = getState().modelInfo || {};
    els.modelDetailsContent.innerHTML = ["student", "teacher"].map((type) => {
        const item = modelInfo[type] || {};
        return `
            <article class="model-detail-card">
                <strong>${formatModelName(item.path, type)}</strong>
                <span>${truncate(item.path || "未加载", 52)}</span>
                <small>来源：${item.selection_source_label || "未记录"}${item.selection_locked ? " · 已锁定" : ""}</small>
                <small>状态：${item.loaded ? "已加载" : item.error || "未加载"}</small>
                <small>类别数：${item.num_classes || 0}</small>
                ${item.selection_lock_reason ? `<small>说明：${item.selection_lock_reason}</small>` : ""}
                <div class="tag-row compact">${(item.classes || []).slice(0, 8).map((name) => `<span class="mini-tag tone-1"><strong>${formatBehaviorLabel(name)}</strong></span>`).join("") || `<span class="mini-tag muted">暂无类别</span>`}</div>
            </article>
        `;
    }).join("");
    openDialog("modelDetailsModal");
}

async function openModelLibraryDialog() {
    if (!getState().models?.length) {
        await loadModels(true);
    }
    const models = getState().models || [];
    const modelInfo = getState().modelInfo || {};
    els.modelLibraryContent.innerHTML = models.length ? models.map((item) => `
        <article class="model-library-item">
            <strong>${truncate(formatModelDetail(item.relative_path || item.filename), 32)}</strong>
            <span>${truncate(item.relative_path || item.filename, 54)}</span>
            <small>${item.error ? `读取失败：${item.error}` : `${item.num_classes || 0} 个类别 · ${item.file_size_mb || "--"} MB · ${item.task || "detect"}`}</small>
            <div class="tag-row compact">${(item.classes || []).slice(0, 8).map((name, index) => `<span class="mini-tag tone-${(index % 4) + 1}"><strong>${formatBehaviorLabel(name)}</strong></span>`).join("") || `<span class="mini-tag muted">无类别信息</span>`}</div>
            <div class="inline-actions model-library-actions">
                <button class="ghost-btn model-pick-btn" type="button" data-role="student" data-model="${item.relative_path || item.filename}" ${modelInfo.student?.selection_locked ? "disabled" : ""}>设为学生模型</button>
                <button class="ghost-btn model-pick-btn" type="button" data-role="teacher" data-model="${item.relative_path || item.filename}" ${modelInfo.teacher?.selection_locked ? "disabled" : ""}>设为教师模型</button>
            </div>
        </article>
    `).join("") : `<div class="model-library-item">当前未扫描到候选模型</div>`;
    [...els.modelLibraryContent.querySelectorAll(".model-pick-btn")].forEach((node) => {
        node.addEventListener("click", () => pickModelFromLibrary(node.dataset.role, node.dataset.model));
    });
    openDialog("modelLibraryModal");
}

function pickModelFromLibrary(role, modelValue) {
    if (!modelValue) return;
    const select = role === "teacher" ? els.teacherModelSelect : els.studentModelSelect;
    if (!select) return;
    if (select.disabled) {
        pushNotification(`${role === "teacher" ? "教师" : "学生"}模型已由当前启动入口固定`, "info");
        return;
    }
    select.value = modelValue;
    closeDialog("modelLibraryModal");
    pushNotification(`已将 ${truncate(formatModelDetail(modelValue), 24)} 设为${role === "teacher" ? "教师" : "学生"}模型候选，请点击“应用模型”生效`, "success");
}

function getDialogCard(id) {
    return els[id]?.querySelector(".dialog-card") || null;
}

function getDialogFocusableElements(dialog) {
    if (!dialog) return [];
    return [...dialog.querySelectorAll(DIALOG_FOCUSABLE_SELECTOR)].filter((node) => !node.hasAttribute("disabled") && !node.getAttribute("aria-hidden") && !node.classList.contains("hidden"));
}

function focusDialog(id) {
    const dialog = getDialogCard(id);
    if (!dialog) return;
    const [firstFocusable] = getDialogFocusableElements(dialog);
    (firstFocusable || dialog).focus();
}

function trapDialogFocus(event, dialog) {
    const focusable = getDialogFocusableElements(dialog);
    if (!focusable.length) {
        event.preventDefault();
        dialog.focus();
        return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (!dialog.contains(document.activeElement)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
        return;
    }
    if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
    } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
    }
}

function handleDialogKeydown(event) {
    if (!activeDialogId) return;
    const dialog = getDialogCard(activeDialogId);
    if (!dialog) return;
    if (event.key === "Escape") {
        event.preventDefault();
        closeDialog(activeDialogId);
        return;
    }
    if (event.key === "Tab") {
        trapDialogFocus(event, dialog);
    }
}

function openDialog(id) {
    const node = els[id];
    const dialog = getDialogCard(id);
    if (!node || !dialog) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialogOpeners.set(id, opener);
    node.classList.remove("hidden");
    node.setAttribute("aria-hidden", "false");
    activeDialogId = id;
    window.requestAnimationFrame(() => focusDialog(id));
}

function closeDialog(id) {
    const node = els[id];
    if (!node) return;
    node.classList.add("hidden");
    node.setAttribute("aria-hidden", "true");
    if (activeDialogId === id) {
        activeDialogId = null;
    }
    const opener = dialogOpeners.get(id);
    dialogOpeners.delete(id);
    if (opener && typeof opener.focus === "function") {
        opener.focus();
    }
}

// Keep formatting-aware wrappers local so shared helpers stay presentation-agnostic.
function getTopBehaviors(summary, limit = 3) {
    return getTopBehaviorsHelper(summary, limit, formatBehaviorLabel);
}

function renderBehaviorTags(items) {
    return renderBehaviorTagsHelper(items, formatNumber);
}

function buildTaskHighlight(task, summary) {
    return buildTaskHighlightHelper(task, summary, getTopBehaviors, formatNumber);
}

function getModeNarrativeLead(mode, total, confidence, duration) {
    return getModeNarrativeLeadHelper(mode, total, confidence, duration, formatNumber);
}

function buildBehaviorNarrative(mode, topBehaviors, total) {
    return buildBehaviorNarrativeHelper(mode, topBehaviors, total, formatNumber);
}

function drawCanvasWithDetections(canvas, image, detections, visibility, activeIndex, uiSettings = DEFAULT_UI_SETTINGS, activeColor = "#ef4444") {
    return drawCanvasWithDetectionsComponent(
        canvas,
        image,
        detections,
        visibility,
        activeIndex,
        uiSettings,
        activeColor,
        formatBehaviorLabel,
        formatNumber,
    );
}

function loadImage(url) {
    return new Promise((resolve, reject) => {
        const image = new Image();
        image.onload = () => resolve(image);
        image.onerror = () => reject(new Error("无法加载图像资源"));
        image.src = url;
    });
}

function downloadUrl(url, baseName) {
    const link = document.createElement("a");
    link.href = url;
    link.download = `${baseName}-${Date.now()}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
}

function downloadCanvas(canvas, baseName) {
    const link = document.createElement("a");
    link.href = canvas.toDataURL("image/png");
    link.download = `${baseName}-${Date.now()}.png`;
    document.body.appendChild(link);
    link.click();
    link.remove();
}
