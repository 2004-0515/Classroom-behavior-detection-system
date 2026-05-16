const STATUS_LABELS = {
    completed: "已完成",
    processing: "处理中",
    failed: "失败",
    stopped_partial: "已停止(部分完成)",
    pending: "等待中",
    success: "成功",
    info: "提示",
    danger: "异常",
};

const TASK_TYPE_LABELS = {
    image: "单图检测",
    batch: "批量检测",
    video: "视频检测",
    webcam: "实时摄像头",
};

const MODE_BADGES = {
    image: "单图",
    batch: "批量",
    video: "视频",
    webcam: "摄像头",
};

const BEHAVIOR_LABELS = {
    read: "阅读",
    reading: "阅读",
    write: "书写",
    writing: "书写",
    hand: "举手",
    handraising: "举手",
    head: "人头",
    bowhead: "低头",
    raisehead: "抬头",
    upright: "坐姿端正",
    inclusion: "专注听讲",
    sleep: "睡觉",
    usingphone: "使用手机",
    phone: "手机",
    computer: "电脑",
    book: "书本",
    patches: "课本区域",
    guidingstudents: "巡视指导",
};

function normalizeLookupKey(value) {
    return String(value || "")
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, "");
}

function toSlug(value) {
    return String(value || "")
        .trim()
        .toLowerCase()
        .replace(/[\\/]/g, " ")
        .replace(/\.[a-z0-9]+$/i, "")
        .replace(/[_-]+/g, " ")
        .replace(/\s+/g, " ");
}

function stripPath(value) {
    return String(value || "").split(/[\\/]/).pop() || "";
}

function toTitleWords(value) {
    return value
        .split(" ")
        .filter(Boolean)
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(" ");
}

function prettifyAsciiLabel(value) {
    const slug = toSlug(value);
    const lookupKey = normalizeLookupKey(value);
    if (!slug) return "未命名";
    if (BEHAVIOR_LABELS[lookupKey]) return BEHAVIOR_LABELS[lookupKey];
    const compact = slug
        .replace(/\b(best|last|final|v\d+)\b/gi, "")
        .replace(/\s+/g, " ")
        .trim();
    if (!compact) return "未命名";
    return toTitleWords(compact);
}

export function formatNumber(value, digits = 0) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return "--";
    }
    return Number(value).toFixed(digits);
}

export function formatStatus(status) {
    return STATUS_LABELS[status] || STATUS_LABELS.info;
}

export function statusPill(status) {
    const tone = status || "info";
    return `<span class="pill ${tone}">${formatStatus(status)}</span>`;
}

export function truncate(value, length = 38) {
    if (!value) return "--";
    return value.length > length ? `${value.slice(0, length)}...` : value;
}

export function formatTaskType(type) {
    return TASK_TYPE_LABELS[type] || "检测任务";
}

export function formatModeBadge(mode) {
    return MODE_BADGES[mode] || "任务";
}

export function formatBehaviorLabel(value) {
    if (!value) return "未标注行为";
    if (/[一-龥]/.test(value)) return value;
    return prettifyAsciiLabel(value);
}

export function formatBehaviorStats(stats = {}) {
    const next = {};
    Object.entries(stats || {}).forEach(([key, value]) => {
        const label = formatBehaviorLabel(key);
        next[label] = (next[label] || 0) + Number(value || 0);
    });
    return next;
}

export function formatFileLabel(value, fallback = "未命名文件") {
    if (!value) return fallback;
    if (/^\d+\s+images$/i.test(String(value).trim())) {
        return `${String(value).trim().split(/\s+/)[0]} 张图片`;
    }
    const raw = stripPath(value).replace(/\.[a-z0-9]+$/i, "");
    if (!raw) return fallback;
    if (/[一-龥]/.test(raw)) return raw;
    return prettifyAsciiLabel(raw);
}

export function formatModelName(value, role = "") {
    const base = stripPath(value);
    const slug = toSlug(base);
    if (!slug) {
        return role === "student" ? "学生行为模型" : role === "teacher" ? "人头检测模型" : "检测模型";
    }
    if (/(behavior|student)/.test(slug)) return "学生行为模型";
    if (/(teacher|head|heand)/.test(slug)) return "人头检测模型";
    return `${prettifyAsciiLabel(base)} 模型`;
}

export function formatModelDetail(value) {
    const base = stripPath(value);
    if (!base) return "未加载";
    const name = base.replace(/\.[a-z0-9]+$/i, "");
    if (/[一-龥]/.test(name)) return name;
    return prettifyAsciiLabel(name);
}

export function formatRelativeTimeLabel(value) {
    if (!value) return "--";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
    });
}

export function formatSummaryTone(total) {
    if (Number(total || 0) <= 0) return "静态";
    if (Number(total || 0) < 20) return "轻量";
    if (Number(total || 0) < 80) return "稳定";
    return "高密度";
}
