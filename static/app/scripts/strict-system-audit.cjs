#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..', '..', '..');
const DEFAULT_ARTIFACT_DIR = path.join(ROOT, 'docs', '_artifacts');
const DEFAULT_OUTPUT_PATH = path.join(DEFAULT_ARTIFACT_DIR, 'strict-system-audit.json');
const HARD_ISSUE_SEVERITIES = new Set(['blocker', 'major', 'minor']);
const VIEWPORTS = [
    { name: 'desktop-1440x1000', width: 1440, height: 1000, heavy: true },
    { name: 'laptop-1366x900', width: 1366, height: 900, heavy: false },
    { name: 'mobile-390x844', width: 390, height: 844, heavy: false },
];
// Keep the stop flow on a longer clip so the audit really interrupts an active task,
// and keep the complete flow on a short clip so Playwright tracing stays stable.
const SAMPLE_FILES = {
    imageA: path.join(ROOT, 'testfile', '0014012.jpg'),
    imageB: path.join(ROOT, 'testfile', '0009008.jpg'),
    videoStop: path.join(ROOT, 'testfile', 'QQ202618-01246-HD.mp4'),
    videoComplete: path.join(ROOT, 'datasets', 'testdata', 'sample_video.mp4'),
};
const LOGIN_LAYOUT_SELECTORS = ['.login-badge', '.login-card h2', '.login-copy', '.inline-error', '.field span', '.primary-btn', '.login-metric strong', '.login-metric span'];
const DASHBOARD_LAYOUT_SELECTORS = ['.nav-item', '.ghost-btn', '.primary-btn', '.danger-btn', '.pill', '.panel-tag', '.history-selection-meta', '.inline-note', '.panel-head h2', '#workspaceTitle', '.file-chip', '.gallery-item', '#notifications .notification-item'];
const REPORT_LAYOUT_SELECTORS = ['h1', 'h2', '.pill', '.report-action', '.metric-card strong', '.metric-card span', '.speech-card p', '.tag-row .pill'];
const AUDIT_ADMIN_USERNAME = process.env.STRICT_AUDIT_ADMIN_USERNAME || 'audit_admin';
const AUDIT_ADMIN_PASSWORD = process.env.STRICT_AUDIT_ADMIN_PASSWORD || 'audit_password_123';
const AUDIT_PYTHON = process.env.STRICT_AUDIT_PYTHON || 'python';

function parseArgs(argv) {
    const args = {};
    for (let index = 2; index < argv.length; index += 1) {
        const token = argv[index];
        if (!token.startsWith('--')) {
            continue;
        }
        const key = token.slice(2);
        const next = argv[index + 1];
        if (next && !next.startsWith('--')) {
            args[key] = next;
            index += 1;
        } else {
            args[key] = true;
        }
    }
    return args;
}

function ensureDir(targetPath) {
    fs.mkdirSync(targetPath, { recursive: true });
}

function timestampTag() {
    const now = new Date();
    const pad = (value) => String(value).padStart(2, '0');
    return `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
}

function toRelative(targetPath) {
    return path.relative(ROOT, targetPath).split(path.sep).join('/');
}

function writeJson(targetPath, payload) {
    fs.writeFileSync(targetPath, JSON.stringify(payload, null, 2), 'utf-8');
}

function writeBuffer(targetPath, payload) {
    fs.writeFileSync(targetPath, payload);
}

function sanitizeSegment(value) {
    return String(value || '')
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '') || 'audit';
}

function normalizeAuditText(value) {
    return String(value || '').replace(/\s+/g, ' ').trim();
}

function rememberGeneratedReport(audit, key, reportContract) {
    audit.generatedReports = audit.generatedReports || {};
    audit.generatedReports[key] = reportContract;
}

function getGeneratedReports(audit, keys) {
    return keys.map((key) => audit.generatedReports?.[key]).filter(Boolean);
}

function wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function assert(condition, message) {
    if (!condition) {
        throw new Error(message);
    }
}

function findBrowserExecutable() {
    const candidates = [
        process.env.STRICT_AUDIT_BROWSER,
        'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
        'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
        'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    ].filter(Boolean);
    const matched = candidates.find((candidate) => fs.existsSync(candidate));
    if (!matched) {
        throw new Error('未找到可用于 Playwright 审计的 Edge/Chrome 可执行文件');
    }
    return matched;
}

async function launchBrowser(browserPath, { fakeMedia = false } = {}) {
    const args = ['--disable-dev-shm-usage'];
    if (fakeMedia) {
        args.push('--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream');
    }
    return chromium.launch({
        headless: true,
        executablePath: browserPath,
        args,
    });
}

async function installOpenRecorder(page, extraInitScript) {
    await page.addInitScript(() => {
        window.__auditOpenedUrls = [];
        window.open = function patchedWindowOpen(url) {
            window.__auditOpenedUrls.push(String(url || ''));
            return null;
        };
    });
    if (typeof extraInitScript === 'function') {
        await page.addInitScript(extraInitScript);
    }
}

function addIssue(audit, flowState, issue) {
    audit.issues.push({
        flow: flowState.flow,
        viewport: flowState.viewport.name,
        severity: issue.severity,
        repro_steps: issue.repro_steps,
        expected: issue.expected,
        observed: issue.observed,
        console_errors: issue.console_errors || flowState.consoleErrors,
        network_failures: issue.network_failures || flowState.networkFailures,
        evidence_paths: issue.evidence_paths || flowState.evidencePaths,
        missing_regression: issue.missing_regression,
    });
}

function createFlowState(audit, flow, viewport, flowDir, allowHttpFailure) {
    return {
        flow,
        viewport,
        flowDir,
        consoleErrors: [],
        networkFailures: [],
        evidencePaths: [],
        stepLog: [],
        allowHttpFailure,
        origin: audit.baseOrigin,
    };
}

function isIgnorableStreamingPath(pathname) {
    return pathname === '/api/streams/webcam/feed'
        || pathname === '/api/streams/webcam/diagnostics'
        || /^\/api\/streams\/video\/[^/]+\/feed$/.test(pathname);
}

function shouldIgnoreRequestFailure(flowState, request) {
    const failure = request.failure();
    const errorText = failure ? failure.errorText : '';
    if (request.method() !== 'GET') {
        return false;
    }
    const pathname = new URL(request.url()).pathname;
    if (isIgnorableStreamingPath(pathname)) {
        return true;
    }
    if (errorText !== 'net::ERR_ABORTED') {
        return false;
    }
    return pathname.startsWith('/outputs/');
}

function shouldIgnoreResponseFailure(flowState, response) {
    const request = response.request();
    if (request.method() !== 'GET') {
        return false;
    }
    return isIgnorableStreamingPath(new URL(response.url()).pathname);
}

function attachDiagnostics(page, flowState) {
    page.on('pageerror', (error) => {
        flowState.consoleErrors.push({ type: 'pageerror', text: error.message, stack: error.stack || '' });
    });
    page.on('console', (message) => {
        if (message.type() === 'error') {
            flowState.consoleErrors.push({
                type: 'console',
                text: message.text(),
                location: message.location(),
            });
        }
    });
    page.on('requestfailed', (request) => {
        if (!request.url().startsWith(flowState.origin)) {
            return;
        }
        if (shouldIgnoreRequestFailure(flowState, request)) {
            return;
        }
        flowState.networkFailures.push({
            type: 'requestfailed',
            method: request.method(),
            url: request.url(),
            error_text: request.failure() ? request.failure().errorText : 'unknown request failure',
        });
    });
    page.on('response', (response) => {
        if (!response.url().startsWith(flowState.origin)) {
            return;
        }
        if (response.status() < 400) {
            return;
        }
        if (shouldIgnoreResponseFailure(flowState, response)) {
            return;
        }
        if (typeof flowState.allowHttpFailure === 'function' && flowState.allowHttpFailure(response)) {
            return;
        }
        flowState.networkFailures.push({
            type: 'http',
            method: response.request().method(),
            url: response.url(),
            status: response.status(),
        });
    });
}

async function captureScreenshot(page, flowState, name, options = {}) {
    const screenshotPath = path.join(flowState.flowDir, `${sanitizeSegment(name)}.png`);
    await page.screenshot({ path: screenshotPath, fullPage: options.fullPage ?? true });
    flowState.evidencePaths.push(toRelative(screenshotPath));
    return screenshotPath;
}

async function clearOpenedUrls(page) {
    await page.evaluate(() => {
        window.__auditOpenedUrls = [];
    });
}

async function readOpenedUrls(page) {
    return page.evaluate(() => Array.isArray(window.__auditOpenedUrls) ? [...window.__auditOpenedUrls] : []);
}

async function waitForOpenedUrl(page, timeout = 15000) {
    await page.waitForFunction(() => Array.isArray(window.__auditOpenedUrls) && window.__auditOpenedUrls.length > 0, undefined, { timeout });
    const urls = await readOpenedUrls(page);
    return urls[urls.length - 1];
}

async function getNotificationText(page) {
    return page.locator('#notifications').evaluate((node) => (node.innerText || node.textContent || '').replace(/\s+/g, ' ').trim()).catch(() => '');
}

async function waitForNotification(page, matcher, timeout = 15000) {
    const deadline = Date.now() + timeout;
    let lastText = '';
    while (Date.now() < deadline) {
        const text = await getNotificationText(page);
        lastText = text;
        if (matcher.test(text)) {
            return text;
        }
        await wait(250);
    }
    throw new Error(`未在通知区中匹配到: ${matcher}；当前通知: ${lastText || '无'}`);
}

async function waitForNotificationOutcome(page, matchers, timeout = 15000) {
    const deadline = Date.now() + timeout;
    let lastText = '';
    while (Date.now() < deadline) {
        const text = await getNotificationText(page);
        lastText = text;
        const matched = matchers.find((matcher) => matcher.test(text));
        if (matched) {
            return { text, matcher: matched };
        }
        await wait(250);
    }
    throw new Error(`未在通知区中匹配到预期结果；当前通知: ${lastText || '无'}`);
}

function isRetryableWebcamStartNetworkFailure(entry) {
    if (!entry || entry.type !== 'http' || entry.method !== 'POST' || entry.status !== 400 || !entry.url) {
        return false;
    }
    try {
        return new URL(entry.url).pathname === '/api/streams/webcam/start';
    } catch (error) {
        return false;
    }
}

function isRetryableWebcamStartConsoleError(entry) {
    if (!entry || entry.type !== 'console' || !entry.location || !entry.location.url) {
        return false;
    }
    if (!/Failed to load resource: the server responded with a status of 400/i.test(entry.text || '')) {
        return false;
    }
    try {
        return new URL(entry.location.url).pathname === '/api/streams/webcam/start';
    } catch (error) {
        return false;
    }
}

function suppressRetryableWebcamStartFailures(flowState) {
    flowState.networkFailures = flowState.networkFailures.filter((entry) => !isRetryableWebcamStartNetworkFailure(entry));
    flowState.consoleErrors = flowState.consoleErrors.filter((entry) => !isRetryableWebcamStartConsoleError(entry));
}

async function waitForAppShell(page) {
    await page.waitForSelector('#workspaceTitle', { state: 'visible', timeout: 60000 });
    await page.waitForSelector('#historyList', { state: 'attached', timeout: 60000 });
}

function buildLoginAndGo(baseUrl, nextPath) {
    return `${baseUrl}/audit/login-and-go?next=${encodeURIComponent(nextPath)}`;
}

async function openAuthenticatedPage(page, baseUrl, mode = 'image') {
    await page.goto(buildLoginAndGo(baseUrl, `/?audit_mode=${mode}`), { waitUntil: 'domcontentloaded', timeout: 60000 });
    await waitForAppShell(page);
}

async function performLogin(page, baseUrl, username, password) {
    await page.goto(`${baseUrl}/login`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.fill('input[name="username"]', username);
    await page.fill('input[name="password"]', password);
    await Promise.all([
        page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 60000 }),
        page.click('button[type="submit"]'),
    ]);
}

async function countHistoryTasks(page) {
    return page.locator('#historyList [data-task-id]').count();
}

async function waitForHistoryIncrease(page, beforeCount, timeout = 20000) {
    await page.waitForFunction((expected) => document.querySelectorAll('#historyList [data-task-id]').length > expected, beforeCount, { timeout });
}

async function setCameraIndex(page, value) {
    await page.fill('#cameraIndexInput', String(value));
    await page.dispatchEvent('#cameraIndexInput', 'change');
}

async function fetchJson(page, relativeUrl, options = {}) {
    return page.evaluate(async ({ relativeUrl, options }) => {
        const response = await fetch(relativeUrl, options);
        const text = await response.text();
        return {
            status: response.status,
            payload: JSON.parse(text),
        };
    }, { relativeUrl, options });
}

async function getCurrentTaskIdFromReportLink(page) {
    return page.evaluate(() => {
        const link = document.getElementById('reportLink');
        const href = link?.getAttribute('href') || link?.dataset?.href || '';
        const match = href.match(/\/api\/tasks\/([^/]+)\/report$/);
        return match ? match[1] : null;
    });
}

function getExpectedMetricCards(summary, limit = 4) {
    return (summary?.display_metrics?.cards || []).slice(0, limit).map((item) => ({
        label: normalizeAuditText(item?.label),
        value: normalizeAuditText(item?.formatted ?? item?.value ?? '--'),
    }));
}

async function getCurrentTaskSummary(page) {
    const taskId = await getCurrentTaskIdFromReportLink(page);
    if (!taskId) {
        return { ok: false, reason: 'missing_task_id', taskId: null, summary: {} };
    }
    const summaryResponse = await fetchJson(page, `/api/tasks/${taskId}/summary`);
    return {
        ok: summaryResponse.status === 200,
        taskId,
        summary: summaryResponse.payload?.data || {},
    };
}

async function getTaskReportContract(page, taskId) {
    if (!taskId) {
        return { ok: false, reason: 'missing_task_id', taskId: null, summary: {}, reportFilename: '', reportUrl: '' };
    }
    const [summaryResponse, reportResponse] = await Promise.all([
        fetchJson(page, `/api/tasks/${taskId}/summary`),
        fetchJson(page, `/api/tasks/${taskId}/report`),
    ]);
    return {
        ok: summaryResponse.status === 200 && reportResponse.status === 200,
        taskId,
        summary: summaryResponse.payload?.data || {},
        reportFilename: reportResponse.payload?.data?.report_filename || '',
        reportUrl: reportResponse.payload?.data?.report_url || '',
    };
}

async function getCurrentTaskReportContract(page) {
    const taskId = await getCurrentTaskIdFromReportLink(page);
    return getTaskReportContract(page, taskId);
}

function isTrackingPrimaryLabel(label) {
    const normalized = normalizeAuditText(label);
    if (!normalized) {
        return false;
    }
    return !/(总检测数|累计检测次数|检测数)/.test(normalized);
}

function hasTrackingCards(expectedCards) {
    const labels = expectedCards.map((item) => normalizeAuditText(item.label));
    return ['独立目标数', '有效帧覆盖率'].every((label) => labels.includes(normalizeAuditText(label)));
}

async function auditCurrentTaskTracking(page) {
    const taskId = await getCurrentTaskIdFromReportLink(page);
    if (!taskId) {
        return { ok: false, reason: 'missing_task_id' };
    }
    const summaryResponse = await fetchJson(page, `/api/tasks/${taskId}/summary`);
    const detectionsResponse = await fetchJson(page, `/api/tasks/${taskId}/detections`);
    const summary = summaryResponse.payload?.data || {};
    const detections = detectionsResponse.payload?.data || {};
    const allDetections = [
        ...(detections.student_detections || []),
        ...(detections.teacher_detections || []),
    ];
    const summaryTotalDetections = Number(summary.total_detections || 0);
    const expectedCards = getExpectedMetricCards(summary);
    const renderedCards = await page.evaluate(() => (
        Array.from(document.querySelectorAll('#summaryCards .summary-card')).slice(0, 4).map((card) => ({
            label: ((card.querySelector('span') && card.querySelector('span').innerText) || '').replace(/\s+/g, ' ').trim(),
            value: ((card.querySelector('strong') && card.querySelector('strong').innerText) || '').replace(/\s+/g, ' ').trim(),
        }))
    ));
    const expectedPrimary = summary.display_metrics?.primary_stat
        ? normalizeAuditText(`${summary.display_metrics.primary_stat.label} ${summary.display_metrics.primary_stat.formatted || summary.display_metrics.primary_stat.value || 0}`)
        : '';
    const primaryLabel = normalizeAuditText(summary.display_metrics?.primary_stat?.label || '');
    const historyMetricLine = await page.evaluate((currentTaskId) => {
        const items = Array.from(document.querySelectorAll('#historyList .history-item[data-task-id]'));
        const match = items.find((item) => String(item.dataset.taskId || '') === String(currentTaskId));
        if (!match) return '';
        const node = match.querySelector('.history-meta span');
        return ((node && node.innerText) || '').replace(/\s+/g, ' ').trim();
    }, taskId);
    const metricMode = summary.display_metrics?.metric_mode || null;
    const cardsMatchSummary = expectedCards.length === renderedCards.length
        && expectedCards.every((item, index) => item.label === normalizeAuditText(renderedCards[index]?.label) && item.value === normalizeAuditText(renderedCards[index]?.value));
    const historyMetricMatchesSummary = !expectedPrimary || normalizeAuditText(historyMetricLine) === expectedPrimary;
    return {
        ok: summaryResponse.status === 200 && detectionsResponse.status === 200,
        taskId,
        summary,
        detectionCount: allDetections.length,
        summaryTotalDetections,
        detectionCountMatchesSummary: summaryTotalDetections === allDetections.length,
        allHaveTrackIds: allDetections.every((item) => item.track_id != null),
        metricMode,
        expectedCards,
        renderedCards,
        cardsMatchSummary,
        expectedPrimary,
        primaryLabel,
        trackingPrimaryLooksValid: metricMode !== 'tracking' || isTrackingPrimaryLabel(primaryLabel),
        hasRequiredTrackingCards: metricMode !== 'tracking' || hasTrackingCards(expectedCards),
        historyMetricLine,
        historyMetricMatchesSummary,
    };
}

async function auditPageLayout(audit, flowState, page, options) {
    const selectors = options.selectors || [];
    const pageOverflow = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        innerWidth: window.innerWidth,
        hasOverflow: document.documentElement.scrollWidth > window.innerWidth + 2,
    }));
    if (pageOverflow.hasOverflow) {
        addIssue(audit, flowState, {
            severity: 'major',
            repro_steps: [...flowState.stepLog, `在 ${options.label} 视图停留，无需额外操作。`],
            expected: '页面不应出现整页横向滚动，关键内容应保持在视口宽度内。',
            observed: `${options.label} 出现横向滚动，scrollWidth=${pageOverflow.scrollWidth}，viewportWidth=${pageOverflow.innerWidth}。`,
            missing_regression: '现有烟测只验证 DOM 标记和接口契约，没有在真实浏览器视口下检查横向滚动。',
        });
    }
    if (selectors.length) {
        const overflowItems = await page.evaluate((selectorList) => {
            const seen = new Set();
            const results = [];
            const selectorHint = (node) => {
                if (node.id) return `#${node.id}`;
                if (node.className && typeof node.className === 'string') {
                    const firstClass = node.className.trim().split(/\s+/)[0];
                    if (firstClass) return `${node.tagName.toLowerCase()}.${firstClass}`;
                }
                return node.tagName.toLowerCase();
            };
            for (const selector of selectorList) {
                for (const node of document.querySelectorAll(selector)) {
                    if (seen.has(node)) continue;
                    seen.add(node);
                    const style = getComputedStyle(node);
                    const rect = node.getBoundingClientRect();
                    if (style.display === 'none' || style.visibility === 'hidden' || rect.width < 8 || rect.height < 8) {
                        continue;
                    }
                    const text = (node.innerText || node.textContent || '').replace(/\s+/g, ' ').trim();
                    if (!text) continue;
                    const xOverflow = node.scrollWidth > node.clientWidth + 3;
                    const yOverflow = node.scrollHeight > node.clientHeight + 3;
                    if (xOverflow || yOverflow) {
                        results.push({
                            selector: selectorHint(node),
                            text: text.slice(0, 80),
                            scrollWidth: node.scrollWidth,
                            clientWidth: node.clientWidth,
                            scrollHeight: node.scrollHeight,
                            clientHeight: node.clientHeight,
                        });
                    }
                }
            }
            return results.slice(0, 8);
        }, selectors);
        if (overflowItems.length) {
            addIssue(audit, flowState, {
                severity: 'minor',
                repro_steps: [...flowState.stepLog, `保持 ${options.label} 当前状态，检查按钮、标签和说明文本。`],
                expected: '关键文本不应截断后溢出容器，也不应把容器撑出异常滚动。',
                observed: `${options.label} 发现 ${overflowItems.length} 处文本溢出风险，例如 ${overflowItems[0].selector}。`,
                missing_regression: '现有验收没有在真实浏览器布局中扫描文本 scrollWidth/clientWidth 异常。',
            });
        }
    }
    if (options.primarySelector) {
        const primary = await page.evaluate((selector) => {
            const node = document.querySelector(selector);
            if (!node) return { present: false };
            const rect = node.getBoundingClientRect();
            const style = getComputedStyle(node);
            return {
                present: true,
                visible: style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0,
                top: rect.top,
                bottom: rect.bottom,
                left: rect.left,
                right: rect.right,
                viewportHeight: window.innerHeight,
                viewportWidth: window.innerWidth,
                text: (node.innerText || node.textContent || '').replace(/\s+/g, ' ').trim(),
            };
        }, options.primarySelector);
        if (primary.present && primary.visible) {
            const offscreen = primary.bottom > primary.viewportHeight + 4 || primary.right > primary.viewportWidth + 4 || primary.top < -4 || primary.left < -4;
            if (offscreen) {
                addIssue(audit, flowState, {
                    severity: 'major',
                    repro_steps: [...flowState.stepLog, `保持 ${options.label} 当前状态，不滚动页面。`],
                    expected: `${options.primaryLabel || '主操作按钮'} 应保持在首屏可达区域内。`,
                    observed: `${options.primaryLabel || '主操作按钮'} 超出当前视口，可见文本为“${primary.text || '未知按钮'}”。`,
                    missing_regression: '现有烟测不会在不同视口下校验主操作按钮是否离开首屏。',
                });
            }
        }
    }
}

async function auditNotificationSemantics(audit, flowState, page) {
    const semantics = await page.evaluate(() => {
        const node = document.getElementById('notifications');
        return node ? {
            ariaLive: node.getAttribute('aria-live'),
            role: node.getAttribute('role'),
            ariaAtomic: node.getAttribute('aria-atomic'),
        } : null;
    });
    if (!semantics) {
        return;
    }
    const role = semantics.role || '';
    const hasLiveRegion = Boolean(semantics.ariaLive) || ['status', 'alert', 'log'].includes(role);
    if (!hasLiveRegion) {
        addIssue(audit, flowState, {
            severity: 'minor',
            repro_steps: [...flowState.stepLog, '触发任意通知后检查通知容器的无障碍属性。'],
            expected: '通知区应通过 aria-live 或语义 role 向辅助技术播报状态变化。',
            observed: `通知容器缺少 aria-live/role，当前属性为 role=${role || 'null'}、aria-live=${semantics.ariaLive || 'null'}。`,
            missing_regression: '现有验收只看视觉结果，没有审查通知反馈是否可被辅助技术感知。',
        });
    }
}

async function auditDialogAccessibility(audit, flowState, page, { openerSelector, modalId, label }) {
    const closeSelector = `[data-close-dialog="${modalId}"]`;
    flowState.stepLog.push(`打开${label}`);
    await page.locator(openerSelector).scrollIntoViewIfNeeded();
    await page.locator(openerSelector).focus();
    await page.click(openerSelector);
    await page.waitForFunction((id) => {
        const node = document.getElementById(id);
        return node && !node.classList.contains('hidden');
    }, modalId, { timeout: 10000 });

    const focusInside = await page.evaluate((id) => {
        const node = document.getElementById(id);
        const dialog = node ? node.querySelector('.dialog-card') : null;
        return Boolean(dialog && dialog.contains(document.activeElement));
    }, modalId);
    if (!focusInside) {
        addIssue(audit, flowState, {
            severity: 'major',
            repro_steps: [...flowState.stepLog],
            expected: `${label} 打开后，焦点应立即进入弹窗内部。`,
            observed: `${label} 打开后焦点仍停留在弹窗外。`,
            missing_regression: '现有测试没有验证弹窗焦点迁移，截图也无法发现键盘用户会丢失上下文。',
        });
    }

    await page.keyboard.press('Escape');
    await wait(250);
    const closedByEscape = await page.evaluate((id) => {
        const node = document.getElementById(id);
        return Boolean(node && node.classList.contains('hidden'));
    }, modalId);
    if (!closedByEscape) {
        addIssue(audit, flowState, {
            severity: 'major',
            repro_steps: [...flowState.stepLog, '按下 Escape。'],
            expected: `${label} 应支持 Escape 关闭。`,
            observed: `${label} 按下 Escape 后仍保持打开。`,
            missing_regression: '现有验收没有覆盖键盘关闭路径，只看点击流程。',
        });
        await page.click(closeSelector);
        await page.waitForFunction((id) => document.getElementById(id).classList.contains('hidden'), modalId, { timeout: 5000 });
    }

    flowState.stepLog.push(`重新打开${label}`);
    await page.locator(openerSelector).focus();
    await page.click(openerSelector);
    await page.waitForFunction((id) => !document.getElementById(id).classList.contains('hidden'), modalId, { timeout: 10000 });
    await page.click(closeSelector);
    await page.waitForFunction((id) => document.getElementById(id).classList.contains('hidden'), modalId, { timeout: 5000 });
    const focusReturned = await page.evaluate((selector) => document.querySelector(selector) === document.activeElement, openerSelector);
    if (!focusReturned) {
        addIssue(audit, flowState, {
            severity: 'major',
            repro_steps: [...flowState.stepLog, `使用关闭按钮关闭${label}。`],
            expected: `${label} 关闭后，焦点应返回到打开它的按钮。`,
            observed: `${label} 关闭后焦点没有回到原始触发按钮。`,
            missing_regression: '现有验收没有覆盖弹窗关闭后的焦点回退。',
        });
    }
}

async function triggerWindowOpen(page, clickSelector, responsePredicate, timeout = 20000) {
    await clearOpenedUrls(page);
    const waiters = [];
    if (responsePredicate) {
        waiters.push(page.waitForResponse(responsePredicate, { timeout }));
    }
    await page.click(clickSelector);
    if (waiters.length) {
        await Promise.all(waiters);
    }
    return waitForOpenedUrl(page, timeout);
}

async function triggerWindowOpenWithResponse(page, clickSelector, responsePredicate, timeout = 20000) {
    await clearOpenedUrls(page);
    const responsePromise = responsePredicate ? page.waitForResponse(responsePredicate, { timeout }) : null;
    await page.click(clickSelector);
    const response = responsePromise ? await responsePromise : null;
    let responseJson = null;
    if (response) {
        try {
            responseJson = await response.json();
        } catch (error) {
            responseJson = null;
        }
    }
    return {
        openedUrl: await waitForOpenedUrl(page, timeout),
        responseJson,
    };
}

function toAbsoluteUrl(baseUrl, maybeRelativeUrl) {
    if (/^https?:/i.test(maybeRelativeUrl)) {
        return maybeRelativeUrl;
    }
    return `${baseUrl}${maybeRelativeUrl}`;
}

function validateBatchArchiveWithPython(zipPath, expectationsPath, label) {
    return spawnSync(
        AUDIT_PYTHON,
        [path.join(ROOT, 'scripts', 'verify_report_archive.py'), '--zip-path', zipPath, '--expectations-path', expectationsPath, '--label', label],
        {
            cwd: ROOT,
            encoding: 'utf-8',
        },
    );
}

async function auditBatchArchive(audit, flowState, page, zipUrl, expectedReports, label) {
    const zipFileName = path.basename(new URL(toAbsoluteUrl(audit.baseUrl, zipUrl)).pathname);
    const zipPath = path.join(flowState.flowDir, zipFileName || `${sanitizeSegment(label)}.zip`);
    const expectationsPath = path.join(flowState.flowDir, `${sanitizeSegment(label)}-expectations.json`);
    const validationLogPath = path.join(flowState.flowDir, `${sanitizeSegment(label)}-validation.json`);
    const payload = expectedReports.map((item) => ({
        task_id: item.taskId,
        report_filename: item.reportFilename,
        summary: item.summary,
    }));
    writeJson(expectationsPath, payload);
    flowState.evidencePaths.push(toRelative(expectationsPath));
    const downloadResponse = await page.context().request.get(toAbsoluteUrl(audit.baseUrl, zipUrl));
    if (!downloadResponse.ok()) {
        throw new Error(`download failed: ${zipUrl} -> HTTP ${downloadResponse.status()}`);
    }
    const zipBytes = await downloadResponse.body();
    writeBuffer(zipPath, zipBytes);
    flowState.evidencePaths.push(toRelative(zipPath));
    const result = validateBatchArchiveWithPython(zipPath, expectationsPath, label);
    const validationOutput = `${result.stdout || ''}${result.stderr || ''}`.trim();
    writeJson(validationLogPath, { status: result.status, output: validationOutput });
    flowState.evidencePaths.push(toRelative(validationLogPath));
    if (result.status !== 0) {
        addIssue(audit, flowState, {
            severity: 'major',
            repro_steps: [...flowState.stepLog, `导出 ${label} 压缩包并逐份核对报告 HTML。`],
            expected: '批量导出的 ZIP 应包含选中的报告 HTML、manifest/readme，并且每份报告的指标卡片应与对应 summary 保持一致。',
            observed: validationOutput || `${label} ZIP 校验失败`,
            missing_regression: '现有严格审计此前只验证 ZIP 地址是否打开，没有逐份检查压缩包内报告 HTML 与 summary 的一致性。',
        });
    }
}

async function auditModelLibraryNaming(audit, flowState, page) {
    await page.click('#modelLibraryBtn');
    await page.waitForFunction(() => !document.getElementById('modelLibraryModal').classList.contains('hidden'), undefined, { timeout: 10000 });
    const unnamedEntries = await page.evaluate(() => (
        Array.from(document.querySelectorAll('#modelLibraryContent .model-library-item strong'))
            .map((node) => (node.innerText || node.textContent || '').replace(/\s+/g, ' ').trim())
            .filter((text) => /未命名/.test(text))
            .slice(0, 8)
    ));
    if (unnamedEntries.length) {
        addIssue(audit, flowState, {
            severity: 'major',
            repro_steps: [...flowState.stepLog, '打开候选模型库弹窗并检查每个模型入口标题。'],
            expected: '候选模型库里的每个模型入口都应提供稳定、可区分的显示名，不应出现“未命名”。',
            observed: `候选模型库仍有 ${unnamedEntries.length} 个未命名入口，例如: ${unnamedEntries[0]}`,
            missing_regression: '现有严格审计只验证模型库弹窗能打开和可键盘关闭，没有检查实际显示名是否退化成“未命名”。',
        });
    }
    await page.click('#modelLibraryModal [data-close-dialog]');
    await page.waitForFunction(() => document.getElementById('modelLibraryModal').classList.contains('hidden'), undefined, { timeout: 5000 });
}

async function auditReportPage(audit, flowState, context, reportUrl, label, options = {}) {
    const absoluteUrl = toAbsoluteUrl(audit.baseUrl, reportUrl);
    const reportPage = await context.newPage();
    attachDiagnostics(reportPage, flowState);
    await reportPage.goto(absoluteUrl, { waitUntil: 'domcontentloaded' });
    await reportPage.waitForSelector('h1', { timeout: 15000 });
    const requiredText = ['课堂行为检测报告', '学生行为分析', '教师/人头行为分析', '建议与分析'];
    for (const text of requiredText) {
        const visible = await reportPage.locator(`text=${text}`).count();
        assert(visible > 0, `${label} 缺少关键区块: ${text}`);
    }
    const requiredMetricText = options.requiredMetricText || ['总检测数'];
    for (const text of requiredMetricText) {
        const visible = await reportPage.locator(`text=${text}`).count();
        assert(visible > 0, `${label} 缺少关键指标: ${text}`);
    }
    const expectedMetricCards = Array.isArray(options.expectedMetricCards) ? options.expectedMetricCards : [];
    if (expectedMetricCards.length) {
        const renderedMetricCards = await reportPage.evaluate(() => (
            Array.from(document.querySelectorAll('.metric-card')).slice(0, 4).map((card) => ({
                label: ((card.querySelector('span') && card.querySelector('span').innerText) || '').replace(/\s+/g, ' ').trim(),
                value: ((card.querySelector('strong') && card.querySelector('strong').innerText) || '').replace(/\s+/g, ' ').trim(),
            }))
        ));
        const reportMetricsMatch = expectedMetricCards.length === renderedMetricCards.length
            && expectedMetricCards.every((item, index) => (
                item.label === normalizeAuditText(renderedMetricCards[index]?.label)
                && item.value === normalizeAuditText(renderedMetricCards[index]?.value)
            ));
        if (!reportMetricsMatch) {
            addIssue(audit, flowState, {
                severity: 'major',
                repro_steps: [...flowState.stepLog, `打开 ${label} 并检查报告指标卡片。`],
                expected: '报告页 metric cards 应与 summary API 的 display_metrics.cards 前 4 项保持同一口径和同一格式化值。',
                observed: `expected=${JSON.stringify(expectedMetricCards)} rendered=${JSON.stringify(renderedMetricCards)}`,
                missing_regression: '现有严格审计只验证报告页能打开和包含指标标题，无法发现 summary 正确但 HTML 报告仍渲染旧值或错位值的情况。',
            });
        }
    }
    const printCount = await reportPage.locator('.report-action.primary').count();
    if (!printCount) {
        addIssue(audit, flowState, {
            severity: 'major',
            repro_steps: [...flowState.stepLog, `打开 ${label}。`],
            expected: '报告页应提供打印 / 导出 PDF 入口。',
            observed: `${label} 未找到打印 / 导出 PDF 按钮。`,
            missing_regression: '现有验收只验证报告可打开，不会检查报告页关键工具栏是否完整。',
        });
    }
    await captureScreenshot(reportPage, flowState, `${label}-baseline`, { fullPage: true });
    await auditPageLayout(audit, flowState, reportPage, {
        label,
        selectors: REPORT_LAYOUT_SELECTORS,
        primarySelector: '.report-action.primary',
        primaryLabel: '报告页打印 / 导出按钮',
    });
    await reportPage.close();
}

async function runFlow(audit, viewport, flowName, options, task) {
    const flowDir = path.join(audit.runDir, sanitizeSegment(viewport.name), sanitizeSegment(flowName));
    ensureDir(flowDir);
    const flowState = createFlowState(audit, flowName, viewport, flowDir, options.allowHttpFailure);
    const startedAt = Date.now();
    const browser = await launchBrowser(audit.browserPath, { fakeMedia: options.fakeMedia });
    const context = await browser.newContext({
        viewport: { width: viewport.width, height: viewport.height },
        acceptDownloads: true,
    });
    if (options.fakeMedia) {
        await context.grantPermissions(['camera'], { origin: audit.baseOrigin });
    }
    await context.tracing.start({ screenshots: true, snapshots: true });
    const page = await context.newPage();
    await installOpenRecorder(page, options.extraInitScript);
    attachDiagnostics(page, flowState);

    const issueCountBefore = audit.issues.length;
    let unexpectedError = null;
    try {
        await task({ audit, viewport, page, context, flowState });
    } catch (error) {
        unexpectedError = error;
        await captureScreenshot(page, flowState, `${flowName}-unexpected-failure`, { fullPage: true }).catch(() => {});
        addIssue(audit, flowState, {
            severity: 'blocker',
            repro_steps: [...flowState.stepLog],
            expected: `${flowName} 应在当前视口顺利跑完。`,
            observed: `${flowName} 运行时中断: ${error.message}`,
            missing_regression: '现有验收没有覆盖这条完整浏览器交互链路，因此运行时错误不会被提前暴露。',
        });
    }

    if (flowState.consoleErrors.length) {
        addIssue(audit, flowState, {
            severity: 'major',
            repro_steps: [...flowState.stepLog, '观察浏览器控制台输出。'],
            expected: '流程执行期间不应出现未捕获 console error / pageerror。',
            observed: `发现 ${flowState.consoleErrors.length} 条控制台错误，首条为: ${flowState.consoleErrors[0].text}`,
            missing_regression: '现有验收没有在真实浏览器里收集 console error。',
        });
    }
    if (flowState.networkFailures.length) {
        addIssue(audit, flowState, {
            severity: 'major',
            repro_steps: [...flowState.stepLog, '观察流程期间的同源网络请求。'],
            expected: '关键流程不应出现 4xx/5xx 或 requestfailed。',
            observed: `发现 ${flowState.networkFailures.length} 条关键请求失败，首条为: ${flowState.networkFailures[0].url}`,
            missing_regression: '现有验收不会在浏览器层收集请求失败和 4xx/5xx 响应。',
        });
    }

    const consoleLogPath = path.join(flowDir, 'console-errors.json');
    const networkLogPath = path.join(flowDir, 'network-failures.json');
    writeJson(consoleLogPath, flowState.consoleErrors);
    writeJson(networkLogPath, flowState.networkFailures);
    flowState.evidencePaths.push(toRelative(consoleLogPath), toRelative(networkLogPath));

    const issueCountAfter = audit.issues.length;
    const hasFlowIssues = issueCountAfter > issueCountBefore;
    if (hasFlowIssues) {
        const tracePath = path.join(flowDir, 'trace.zip');
        await context.tracing.stop({ path: tracePath });
        flowState.evidencePaths.push(toRelative(tracePath));
    } else {
        await context.tracing.stop();
    }
    await context.close();
    await browser.close();

    audit.flows.push({
        flow: flowName,
        viewport: viewport.name,
        status: unexpectedError ? 'failed' : hasFlowIssues ? 'issues' : 'passed',
        duration_seconds: Number(((Date.now() - startedAt) / 1000).toFixed(2)),
        issue_count: issueCountAfter - issueCountBefore,
        console_error_count: flowState.consoleErrors.length,
        network_failure_count: flowState.networkFailures.length,
        evidence_paths: [...new Set(flowState.evidencePaths)],
    });
}

async function auditSetupRequiredLoginFlow(ctx) {
    const { audit, page, flowState } = ctx;
    flowState.stepLog.push('打开未初始化管理员的登录页');
    await page.goto(`${audit.setupBaseUrl}/login`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.login-form', { timeout: 15000 });
    const setupHint = await page.locator('.inline-error').innerText();
    assert(/init_local_admin\.py/.test(setupHint), '未初始化登录页缺少管理员初始化提示');
    const disabled = await page.locator('button[type="submit"]').isDisabled();
    if (!disabled) {
        addIssue(audit, flowState, {
            severity: 'major',
            repro_steps: [...flowState.stepLog],
            expected: '未初始化管理员时，登录按钮应禁用并明确提示先完成初始化。',
            observed: '未初始化管理员时登录按钮仍可点击。',
            missing_regression: '现有烟测只验证 setup_required 文案存在，没有验证登录 CTA 状态。',
        });
    }
    await captureScreenshot(page, flowState, 'login-setup-required', { fullPage: true });
    await auditPageLayout(audit, flowState, page, {
        label: '未初始化登录页',
        selectors: LOGIN_LAYOUT_SELECTORS,
        primarySelector: 'button[type="submit"]',
        primaryLabel: '登录按钮',
    });
}

async function auditInvalidLoginFlow(ctx) {
    const { audit, page, flowState } = ctx;
    flowState.stepLog.push('打开登录页并提交错误账号密码');
    await page.goto(`${audit.baseUrl}/login`, { waitUntil: 'domcontentloaded' });
    await page.fill('input[name="username"]', 'wrong_user');
    await page.fill('input[name="password"]', 'wrong_password');
    await Promise.all([
        page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 60000 }),
        page.click('button[type="submit"]'),
    ]);
    await page.waitForSelector('.inline-error', { timeout: 15000 });
    const errorText = await page.locator('.inline-error').last().innerText();
    assert(/账号或密码错误/.test(errorText), '错误登录未显示错误提示');
    const focusInfo = await page.evaluate(() => {
        const node = document.activeElement;
        return {
            tag: node ? node.tagName.toLowerCase() : 'none',
            name: node ? node.getAttribute('name') : '',
            insideForm: Boolean(node && node.closest('.login-form')),
            insideError: Boolean(node && node.closest('.inline-error')),
        };
    });
    if (!focusInfo.insideForm && !focusInfo.insideError) {
        addIssue(audit, flowState, {
            severity: 'minor',
            repro_steps: [...flowState.stepLog],
            expected: '错误登录后，焦点应留在表单或错误提示附近，方便直接修正。',
            observed: `错误登录后焦点落在表单外，activeElement=${focusInfo.tag}${focusInfo.name ? `:${focusInfo.name}` : ''}。`,
            missing_regression: '现有验收不会审查错误反馈后的焦点位置。',
        });
    }
    await captureScreenshot(page, flowState, 'login-invalid-credentials', { fullPage: true });
    await auditPageLayout(audit, flowState, page, {
        label: '错误登录页',
        selectors: LOGIN_LAYOUT_SELECTORS,
        primarySelector: 'button[type="submit"]',
        primaryLabel: '登录按钮',
    });
}

async function auditSuccessfulLoginFlow(ctx) {
    const { audit, page, flowState } = ctx;
    flowState.stepLog.push('通过真实登录表单进入控制台');
    await performLogin(page, audit.baseUrl, AUDIT_ADMIN_USERNAME, AUDIT_ADMIN_PASSWORD);
    await waitForAppShell(page);
    const runDisabled = await page.locator('#runBtn').isDisabled();
    if (!runDisabled) {
        addIssue(audit, flowState, {
            severity: 'major',
            repro_steps: [...flowState.stepLog],
            expected: '单图模式在未选文件前应禁用主检测按钮。',
            observed: '成功登录后，未选文件时主检测按钮仍可点击。',
            missing_regression: '现有 smoke 没有把真实登录后的 CTA 状态当成浏览器级验收条件。',
        });
    }
    await captureScreenshot(page, flowState, 'dashboard-after-login', { fullPage: true });
    await auditPageLayout(audit, flowState, page, {
        label: '登录后控制台',
        selectors: DASHBOARD_LAYOUT_SELECTORS,
    });
}

async function switchMode(page, mode) {
    await page.click(`.nav-item[data-mode="${mode}"]`);
    await page.waitForFunction((expectedMode) => {
        const active = document.querySelector('.nav-item.active');
        return active && active.dataset.mode === expectedMode;
    }, mode, { timeout: 10000 });
}

async function auditDashboardFlow(ctx) {
    const { audit, page, flowState } = ctx;
    flowState.stepLog.push('以已登录状态进入主工作台');
    await openAuthenticatedPage(page, audit.baseUrl, 'image');

    const modeExpectations = {
        image: async () => {
            assert(await page.locator('#runBtn').isVisible(), '单图模式未显示主检测按钮');
        },
        batch: async () => {
            assert(await page.locator('#runBtn').isVisible(), '批量模式未显示主检测按钮');
        },
        video: async () => {
            assert(await page.locator('#stopTaskBtn').count() > 0, '视频模式缺少停止按钮容器');
        },
        webcam: async () => {
            const runHidden = await page.evaluate(() => document.getElementById('runBtn').classList.contains('hidden'));
            const controlsVisible = await page.evaluate(() => !document.getElementById('webcamControls').classList.contains('hidden'));
            assert(runHidden && controlsVisible, '摄像头模式未正确切换到专用控制区');
        },
    };

    for (const mode of ['image', 'batch', 'video', 'webcam']) {
        flowState.stepLog.push(`切换到${mode}模式`);
        await switchMode(page, mode);
        await modeExpectations[mode]();
        await auditPageLayout(audit, flowState, page, {
            label: `${mode} 模式控制台`,
            selectors: DASHBOARD_LAYOUT_SELECTORS,
        });
    }

    await auditNotificationSemantics(audit, flowState, page);
    await auditDialogAccessibility(audit, flowState, page, { openerSelector: '#settingsBtn', modalId: 'settingsModal', label: '设置弹窗' });
    await auditDialogAccessibility(audit, flowState, page, { openerSelector: '#currentModelDetailsBtn', modalId: 'modelDetailsModal', label: '当前模型弹窗' });
    await auditDialogAccessibility(audit, flowState, page, { openerSelector: '#modelLibraryBtn', modalId: 'modelLibraryModal', label: '候选模型库弹窗' });
    await auditModelLibraryNaming(audit, flowState, page);
    await captureScreenshot(page, flowState, 'dashboard-modes', { fullPage: true });
}

async function auditImageFlow(ctx) {
    const { audit, page, context, flowState } = ctx;
    flowState.stepLog.push('进入单图模式并准备样例图片');
    await openAuthenticatedPage(page, audit.baseUrl, 'image');
    const beforeHistory = await countHistoryTasks(page);
    const initiallyDisabled = await page.locator('#runBtn').isDisabled();
    if (!initiallyDisabled) {
        addIssue(audit, flowState, {
            severity: 'major',
            repro_steps: [...flowState.stepLog],
            expected: '未选图片前，单图检测按钮应禁用。',
            observed: '未选图片前，单图检测按钮可点击。',
            missing_regression: '现有验收没有把 CTA 可用性作为真实浏览器断言。',
        });
    }
    await page.locator('#fileInput').setInputFiles(SAMPLE_FILES.imageA);
    await page.waitForSelector('#selectedFiles .file-chip strong', { timeout: 10000 });
    const enabledAfterSelect = !(await page.locator('#runBtn').isDisabled());
    if (!enabledAfterSelect) {
        addIssue(audit, flowState, {
            severity: 'major',
            repro_steps: [...flowState.stepLog, '选择一张图片。'],
            expected: '选中图片后，单图检测按钮应立即可用。',
            observed: '选中图片后，单图检测按钮仍然禁用。',
            missing_regression: '现有验收没有在真实选择文件后校验 CTA 状态切换。',
        });
    }
    flowState.stepLog.push('执行单图检测并等待结果');
    await Promise.all([
        page.waitForResponse((response) => response.url().endsWith('/api/detect/image') && response.request().method() === 'POST', { timeout: 30000 }),
        page.click('#runBtn'),
    ]);
    await page.waitForFunction(() => {
        const image = document.getElementById('resultImage');
        const reportLink = document.getElementById('reportLink');
        return image && image.getAttribute('src') && reportLink && reportLink.getAttribute('aria-disabled') === 'false';
    }, undefined, { timeout: 60000 });
    await waitForHistoryIncrease(page, beforeHistory, 20000);
    await captureScreenshot(page, flowState, 'image-result', { fullPage: true });
    await auditPageLayout(audit, flowState, page, {
        label: '单图检测结果页',
        selectors: DASHBOARD_LAYOUT_SELECTORS,
    });
    await auditDialogAccessibility(audit, flowState, page, { openerSelector: '#openDetailBtn', modalId: 'detailModal', label: '结果细看弹窗' });
    const imageSummaryAudit = await getCurrentTaskSummary(page);
    const imageReportContract = await getCurrentTaskReportContract(page);
    flowState.stepLog.push('打开单图报告');
    const reportOpen = await triggerWindowOpenWithResponse(
        page,
        '#reportLink',
        (response) => /\/api\/tasks\/[^/]+\/report$/.test(new URL(response.url()).pathname) && response.request().method() === 'GET',
    );
    const expectedOpenedUrl = imageReportContract.reportUrl || reportOpen.responseJson?.data?.report_url || '';
    if (expectedOpenedUrl && reportOpen.openedUrl !== expectedOpenedUrl) {
        addIssue(audit, flowState, {
            severity: 'major',
            repro_steps: [...flowState.stepLog],
            expected: '点击报告按钮后应打开当前任务对应的 report_url。',
            observed: `报告按钮打开了 ${reportOpen.openedUrl}，但接口返回的是 ${expectedOpenedUrl}`,
            missing_regression: '现有严格审计此前没有把报告按钮实际打开的地址与接口返回的 report_url 逐一对齐。',
        });
    }
    await auditReportPage(audit, flowState, context, reportOpen.openedUrl, '单图报告', {
        requiredMetricText: ['总检测数'],
        expectedMetricCards: getExpectedMetricCards(imageSummaryAudit.summary),
    });
    if (imageReportContract.ok) {
        rememberGeneratedReport(audit, 'image', imageReportContract);
    }
}

async function auditBatchFlow(ctx) {
    const { audit, page, context, flowState } = ctx;
    flowState.stepLog.push('进入批量模式并选择两张样例图片');
    await openAuthenticatedPage(page, audit.baseUrl, 'batch');
    const beforeHistory = await countHistoryTasks(page);
    const exportInitiallyDisabled = await page.locator('#historyExportSelectedBtn').isDisabled();
    if (!exportInitiallyDisabled) {
        addIssue(audit, flowState, {
            severity: 'major',
            repro_steps: [...flowState.stepLog],
            expected: '未选择历史任务前，批量导出按钮应保持禁用。',
            observed: '未选择历史任务前，批量导出按钮已可点击。',
            missing_regression: '现有验收没有检查历史批量工具条的 CTA 状态。',
        });
    }
    const fileChooserPromise = page.waitForEvent('filechooser');
    await page.click('#pickFileBtn');
    const fileChooser = await fileChooserPromise;
    await fileChooser.setFiles([SAMPLE_FILES.imageA, SAMPLE_FILES.imageB]);
    flowState.stepLog.push('执行批量检测');
    await Promise.all([
        page.waitForResponse((response) => response.url().endsWith('/api/detect/batch') && response.request().method() === 'POST', { timeout: 30000 }),
        page.click('#runBtn'),
    ]);
    await page.waitForFunction(() => document.querySelectorAll('#resultGallery .gallery-item').length >= 2, undefined, { timeout: 60000 });
    await waitForHistoryIncrease(page, beforeHistory, 20000);
    await page.click('#historySelectShowcaseBtn');
    await page.waitForFunction(() => {
        const meta = document.getElementById('historySelectionMeta');
        return meta && !/未选择任务/.test(meta.innerText || '');
    }, undefined, { timeout: 10000 });
    const exportEnabled = !(await page.locator('#historyExportSelectedBtn').isDisabled());
    if (!exportEnabled) {
        addIssue(audit, flowState, {
            severity: 'major',
            repro_steps: [...flowState.stepLog, '点击“选中当前可展示”。'],
            expected: '选中可展示历史任务后，导出选中报告按钮应启用。',
            observed: '选中可展示历史任务后，导出按钮仍禁用。',
            missing_regression: '现有验收没有覆盖历史多选和批量导出的按钮状态切换。',
        });
    }
    const batchReportContract = await getCurrentTaskReportContract(page);
    flowState.stepLog.push('打开批量任务报告');
    const reportOpen = await triggerWindowOpenWithResponse(
        page,
        '#reportLink',
        (response) => /\/api\/tasks\/[^/]+\/report$/.test(new URL(response.url()).pathname) && response.request().method() === 'GET',
    );
    const expectedOpenedUrl = batchReportContract.reportUrl || reportOpen.responseJson?.data?.report_url || '';
    if (expectedOpenedUrl && reportOpen.openedUrl !== expectedOpenedUrl) {
        addIssue(audit, flowState, {
            severity: 'major',
            repro_steps: [...flowState.stepLog],
            expected: '点击报告按钮后应打开当前批量任务对应的 report_url。',
            observed: `批量任务报告按钮打开了 ${reportOpen.openedUrl}，但接口返回的是 ${expectedOpenedUrl}`,
            missing_regression: '现有严格审计此前没有把批量任务报告按钮实际打开的地址与接口返回的 report_url 对齐。',
        });
    }
    await auditReportPage(audit, flowState, context, reportOpen.openedUrl, '批量任务报告', {
        requiredMetricText: ['总检测数'],
        expectedMetricCards: getExpectedMetricCards(batchReportContract.summary),
    });
    if (batchReportContract.ok) {
        rememberGeneratedReport(audit, 'batch', batchReportContract);
    }
    await captureScreenshot(page, flowState, 'batch-task-report', { fullPage: true });
    await auditPageLayout(audit, flowState, page, {
        label: '批量检测与历史导出页',
        selectors: DASHBOARD_LAYOUT_SELECTORS,
    });
}

async function auditHistoryBatchExportFlow(ctx) {
    const { audit, page, flowState } = ctx;
    const expectedReports = getGeneratedReports(audit, ['image', 'batch', 'video']);
    if (expectedReports.length < 3) {
        addIssue(audit, flowState, {
            severity: 'coverage_gap',
            repro_steps: [...flowState.stepLog, '尝试基于历史任务导出多份跨模式报告。'],
            expected: '严格审计应在导出前先准备单图、批量、视频三种任务的报告契约。',
            observed: `当前仅缓存了 ${expectedReports.length} 份报告契约，无法完成跨模式 ZIP 校验。`,
            missing_regression: '现有严格审计此前没有把跨模式历史导出和逐份 ZIP 内容校验收进同一条浏览器验收链。',
        });
        return;
    }
    flowState.stepLog.push('进入历史记录并手动选中单图、批量、视频三类任务');
    await openAuthenticatedPage(page, audit.baseUrl, 'image');
    await page.fill('#historyFilter', '');
    await page.selectOption('#historyModeFilter', 'all');
    await page.selectOption('#historySort', 'recent');
    const showcaseOnly = await page.isChecked('#historyShowcaseOnly');
    if (showcaseOnly) {
        await page.click('#historyShowcaseOnly');
    }
    const expectedTaskIds = expectedReports.map((item) => String(item.taskId));
    await page.waitForFunction((taskIds) => taskIds.every((taskId) => document.querySelector(`#historyList .history-select[data-task-id="${taskId}"]`)), expectedTaskIds, { timeout: 20000 });
    for (const taskId of expectedTaskIds) {
        const checkbox = page.locator(`#historyList .history-select[data-task-id="${taskId}"]`);
        if (!(await checkbox.isChecked())) {
            await checkbox.check();
        }
    }
    await page.waitForFunction((expectedCount) => {
        const text = (document.getElementById('historySelectionMeta')?.innerText || '').replace(/\s+/g, ' ').trim();
        return text.includes(`已选 ${expectedCount} 条任务`);
    }, expectedReports.length, { timeout: 10000 });
    const exportEnabled = !(await page.locator('#historyExportSelectedBtn').isDisabled());
    if (!exportEnabled) {
        addIssue(audit, flowState, {
            severity: 'major',
            repro_steps: [...flowState.stepLog, `手动勾选 ${expectedReports.length} 条历史任务。`],
            expected: '手动勾选历史任务后，导出选中报告按钮应启用。',
            observed: '历史导出按钮仍然禁用。',
            missing_regression: '现有严格审计此前没有覆盖跨模式手动勾选历史任务后的导出可用性。',
        });
    }
    flowState.stepLog.push('导出跨模式历史报告 ZIP 并逐份核对 HTML');
    const exportOpen = await triggerWindowOpenWithResponse(
        page,
        '#historyExportSelectedBtn',
        (response) => response.url().endsWith('/api/tasks/reports/batch') && response.request().method() === 'POST',
        30000,
    );
    const payload = exportOpen.responseJson?.data || {};
    if (Number(payload.report_count || 0) !== expectedReports.length) {
        addIssue(audit, flowState, {
            severity: 'major',
            repro_steps: [...flowState.stepLog],
            expected: `导出返回的 report_count 应等于选中的 ${expectedReports.length} 条任务。`,
            observed: `接口返回 report_count=${payload.report_count ?? 'unknown'}`,
            missing_regression: '现有严格审计此前没有把浏览器层的历史勾选数量与后端返回的 report_count 绑定校验。',
        });
    }
    const expectedZipUrl = payload.zip_url || '';
    if (expectedZipUrl && exportOpen.openedUrl !== expectedZipUrl) {
        addIssue(audit, flowState, {
            severity: 'major',
            repro_steps: [...flowState.stepLog],
            expected: '导出按钮应打开接口返回的 zip_url。',
            observed: `导出按钮打开了 ${exportOpen.openedUrl}，但接口返回的是 ${expectedZipUrl}`,
            missing_regression: '现有严格审计此前没有把导出动作实际打开的地址与接口返回的 zip_url 逐一对齐。',
        });
    }
    if (!/\.zip($|\?)/i.test(exportOpen.openedUrl || '')) {
        addIssue(audit, flowState, {
            severity: 'major',
            repro_steps: [...flowState.stepLog],
            expected: '导出所选报告后应打开 ZIP 下载地址。',
            observed: `导出动作打开的地址不是 ZIP: ${exportOpen.openedUrl}`,
            missing_regression: '现有严格审计此前只看按钮能否点击，没有断言浏览器最终打开的是 ZIP 资源。',
        });
    } else {
        await auditBatchArchive(audit, flowState, page, exportOpen.openedUrl, expectedReports, 'history batch export');
    }
    await captureScreenshot(page, flowState, 'history-batch-export-contract', { fullPage: true });
    await auditPageLayout(audit, flowState, page, {
        label: '历史跨模式报告导出页',
        selectors: DASHBOARD_LAYOUT_SELECTORS,
    });
}

async function auditVideoStopFlow(ctx) {
    const { audit, page, flowState } = ctx;
    flowState.stepLog.push('进入视频模式并上传样例视频');
    await openAuthenticatedPage(page, audit.baseUrl, 'video');
    const beforeHistory = await countHistoryTasks(page);
    await page.locator('#fileInput').setInputFiles(SAMPLE_FILES.videoStop);
    flowState.stepLog.push('启动视频检测并在处理中停止任务');
    await Promise.all([
        page.waitForResponse((response) => response.url().endsWith('/api/detect/video') && response.request().method() === 'POST', { timeout: 30000 }),
        page.click('#runBtn'),
    ]);
    await page.waitForFunction(() => {
        const stopButton = document.getElementById('stopTaskBtn');
        return stopButton && !stopButton.classList.contains('hidden');
    }, undefined, { timeout: 20000 });
    await captureScreenshot(page, flowState, 'video-processing', { fullPage: true });
    await page.click('#stopTaskBtn');
    await page.waitForFunction(() => {
        const stateCard = document.getElementById('taskState');
        const reportLink = document.getElementById('reportLink');
        const text = (stateCard && (stateCard.innerText || stateCard.textContent || '')) || '';
        return /已停止\(部分完成\)/.test(text) || (reportLink && reportLink.getAttribute('aria-disabled') === 'false');
    }, undefined, { timeout: 120000 });
    await waitForHistoryIncrease(page, beforeHistory, 20000);
    await captureScreenshot(page, flowState, 'video-stopped', { fullPage: true });
    await auditPageLayout(audit, flowState, page, {
        label: '视频停止态结果页',
        selectors: DASHBOARD_LAYOUT_SELECTORS,
    });
}

async function auditVideoCompleteFlow(ctx) {
    const { audit, page, context, flowState } = ctx;
    flowState.stepLog.push('进入视频模式并等待完整处理结束');
    await openAuthenticatedPage(page, audit.baseUrl, 'video');
    const beforeHistory = await countHistoryTasks(page);
    await page.locator('#fileInput').setInputFiles(SAMPLE_FILES.videoComplete);
    await Promise.all([
        page.waitForResponse((response) => response.url().endsWith('/api/detect/video') && response.request().method() === 'POST', { timeout: 30000 }),
        page.click('#runBtn'),
    ]);
    await page.waitForFunction(() => {
        const link = document.getElementById('reportLink');
        return link && link.getAttribute('aria-disabled') === 'false';
    }, undefined, { timeout: 240000 });
    await waitForHistoryIncrease(page, beforeHistory, 20000);
    await captureScreenshot(page, flowState, 'video-complete', { fullPage: true });
    await page.waitForFunction(() => {
        const video = document.getElementById('resultVideo');
        return Boolean(
            video
            && !video.classList.contains('hidden')
            && (video.currentSrc || video.getAttribute('src') || '')
            && Number.isFinite(video.duration)
            && video.duration > 0
            && !video.error
            && video.readyState >= 2,
        );
    }, undefined, { timeout: 30000 }).catch(() => {});
    const videoState = await page.evaluate(() => {
        const video = document.getElementById('resultVideo');
        return video ? {
            visible: !video.classList.contains('hidden'),
            currentSrc: video.currentSrc || video.getAttribute('src') || '',
            readyState: video.readyState,
            duration: Number.isFinite(video.duration) ? Number(video.duration.toFixed(2)) : null,
            error: video.error ? { code: video.error.code, message: video.error.message || '' } : null,
        } : null;
    });
    if (!videoState || !videoState.visible || !videoState.currentSrc || videoState.readyState < 2 || !videoState.duration || videoState.error) {
        addIssue(audit, flowState, {
            severity: 'major',
            repro_steps: [...flowState.stepLog, '等待视频任务处理完成。'],
            expected: '视频结果预览应加载可播放资源，拿到有效时长，并至少进入 HAVE_CURRENT_DATA 状态。',
            observed: `结果视频状态异常: ${JSON.stringify(videoState)}`,
            missing_regression: '现有后端烟测只验证任务完成和报告生成，没有校验浏览器端视频元数据、有效时长和播放错误状态。',
        });
    }
    const trackingAudit = await auditCurrentTaskTracking(page);
    if (
        !trackingAudit.ok
        || trackingAudit.metricMode !== 'tracking'
        || !trackingAudit.detectionCountMatchesSummary
        || (trackingAudit.detectionCount > 0 && !trackingAudit.allHaveTrackIds)
        || !trackingAudit.cardsMatchSummary
        || !trackingAudit.trackingPrimaryLooksValid
        || !trackingAudit.hasRequiredTrackingCards
        || !trackingAudit.historyMetricMatchesSummary
    ) {
        addIssue(audit, flowState, {
            severity: 'major',
            repro_steps: [...flowState.stepLog, '等待视频任务处理完成后检查 summary/detections 接口、当前 summary 卡片和历史项。'],
            expected: '视频任务 summary 应返回 tracking 型 display_metrics，主指标不能退化回累计检测次数，且 summary.total_detections 应与 detection 明细条数一致；检测明细在有结果时应全部携带 track_id，页面 summary 卡片与历史主指标也应和 summary 保持一致。',
            observed: `tracking 审计结果异常: ${JSON.stringify(trackingAudit)}`,
            missing_regression: '现有界面审计没有把 detail API 与当前 summary 卡片 / 历史主指标绑在一起，无法发现接口值正确但前端渲染错位的情况。',
        });
    }
    await auditPageLayout(audit, flowState, page, {
        label: '视频完成态结果页',
        selectors: DASHBOARD_LAYOUT_SELECTORS,
    });
    flowState.stepLog.push('打开视频报告');
    const videoReportContract = await getCurrentTaskReportContract(page);
    const reportOpen = await triggerWindowOpenWithResponse(
        page,
        '#reportLink',
        (response) => /\/api\/tasks\/[^/]+\/report$/.test(new URL(response.url()).pathname) && response.request().method() === 'GET',
        30000,
    );
    const expectedOpenedUrl = videoReportContract.reportUrl || reportOpen.responseJson?.data?.report_url || '';
    if (expectedOpenedUrl && reportOpen.openedUrl !== expectedOpenedUrl) {
        addIssue(audit, flowState, {
            severity: 'major',
            repro_steps: [...flowState.stepLog],
            expected: '点击视频报告按钮后应打开当前任务对应的 report_url。',
            observed: `视频报告按钮打开了 ${reportOpen.openedUrl}，但接口返回的是 ${expectedOpenedUrl}`,
            missing_regression: '现有严格审计此前没有把视频报告按钮实际打开的地址与接口返回的 report_url 对齐。',
        });
    }
    await auditReportPage(audit, flowState, context, reportOpen.openedUrl, '视频报告', {
        requiredMetricText: ['独立目标数', '有效帧覆盖率'],
        expectedMetricCards: trackingAudit.expectedCards,
    });
    if (videoReportContract.ok) {
        rememberGeneratedReport(audit, 'video', videoReportContract);
    }
}

async function auditWebcamFallbackSuccessFlow(ctx) {
    const { audit, page, flowState } = ctx;
    flowState.stepLog.push('进入摄像头模式并强制走浏览器直连 fallback');
    await openAuthenticatedPage(page, audit.baseUrl, 'webcam');
    const beforeHistory = await countHistoryTasks(page);
    await setCameraIndex(page, 99);
    await page.click('#startWebcamBtn');
    await page.waitForFunction(() => {
        const stopButton = document.getElementById('stopWebcamBtn');
        const image = document.getElementById('resultImage');
        return stopButton && !stopButton.classList.contains('hidden') && image && image.getAttribute('src');
    }, undefined, { timeout: 30000 });
    await waitForNotification(page, /浏览器摄像头直连|已切换到浏览器摄像头直连/, 15000).catch(() => {});
    await captureScreenshot(page, flowState, 'webcam-browser-fallback', { fullPage: true });
    await page.click('#stopWebcamBtn');
    await page.waitForFunction(() => document.getElementById('stopWebcamBtn').classList.contains('hidden'), undefined, { timeout: 30000 });
    await waitForHistoryIncrease(page, beforeHistory, 20000);
    const trackingAudit = await auditCurrentTaskTracking(page);
    if (
        !trackingAudit.ok
        || trackingAudit.metricMode !== 'tracking'
        || !trackingAudit.detectionCountMatchesSummary
        || (trackingAudit.detectionCount > 0 && !trackingAudit.allHaveTrackIds)
        || !trackingAudit.cardsMatchSummary
        || !trackingAudit.trackingPrimaryLooksValid
        || !trackingAudit.hasRequiredTrackingCards
        || !trackingAudit.historyMetricMatchesSummary
    ) {
        addIssue(audit, flowState, {
            severity: 'major',
            repro_steps: [...flowState.stepLog, '停止浏览器 fallback 摄像头会话后检查 summary/detections 接口、当前 summary 卡片和历史项。'],
            expected: '浏览器 fallback 摄像头任务应保存 tracking 型摘要，主指标不能退化回累计检测次数；summary.total_detections 应与检测明细条数一致，检测明细在有结果时应全部回传 track_id，且页面 summary 卡片与历史主指标应和 summary 保持一致。',
            observed: `tracking 审计结果异常: ${JSON.stringify(trackingAudit)}`,
            missing_regression: '现有严格审计覆盖了 fallback 成功路径，但没有验证该路径的 track_id / display_metrics 不仅落库一致，还被前端按同一口径渲染。',
        });
    }
    await auditPageLayout(audit, flowState, page, {
        label: '浏览器摄像头 fallback 结果页',
        selectors: DASHBOARD_LAYOUT_SELECTORS,
    });
}

async function auditWebcamFallbackFailureFlow(ctx) {
    const { audit, page, flowState } = ctx;
    flowState.stepLog.push('进入摄像头模式并模拟浏览器摄像头失败');
    await openAuthenticatedPage(page, audit.baseUrl, 'webcam');
    await setCameraIndex(page, 99);
    await page.click('#startWebcamBtn');
    await page.waitForFunction(() => {
        const notifications = document.getElementById('notifications');
        const emptyState = document.getElementById('emptyState');
        const text = (notifications && notifications.innerText) || '';
        const emptyText = (emptyState && emptyState.innerText) || '';
        return /浏览器摄像头直连失败/.test(text) || /摄像头不可用/.test(emptyText);
    }, undefined, { timeout: 30000 });
    await captureScreenshot(page, flowState, 'webcam-browser-failure', { fullPage: true });
}

async function auditServerWebcamFlow(ctx) {
    const { audit, page, flowState } = ctx;
    let probeState = {
        selectedIndex: null,
        diagnosticsText: '',
        notificationText: '',
        unavailable: false,
        failed: false,
    };
    let serverStarted = false;
    try {
        flowState.stepLog.push('进入摄像头模式并检查服务端摄像头诊断');
        await openAuthenticatedPage(page, audit.baseUrl, 'webcam');
        await page.click('#probeWebcamBtn');
        const probeDeadline = Date.now() + 30000;
        while (Date.now() < probeDeadline) {
            probeState = await page.evaluate(() => {
                const diagnosticsNode = document.getElementById('webcamDiagnostics');
                const notificationsNode = document.getElementById('notifications');
                const diagnosticsText = ((diagnosticsNode && diagnosticsNode.innerText) || '').replace(/\s+/g, ' ').trim();
                const notificationText = ((notificationsNode && notificationsNode.innerText) || '').replace(/\s+/g, ' ').trim();
                const selectedMatch = diagnosticsText.match(/已选机位\s+(\d+)/);
                return {
                    selectedIndex: selectedMatch ? Number(selectedMatch[1]) : null,
                    diagnosticsText,
                    notificationText,
                    unavailable: /未找到可用机位/.test(diagnosticsText) || /未找到可读取画面的摄像头组合/.test(notificationText),
                    failed: /摄像头诊断失败/.test(notificationText),
                };
            });
            if (probeState.selectedIndex !== null || probeState.unavailable || probeState.failed || (probeState.diagnosticsText && !/尚未诊断/.test(probeState.diagnosticsText))) {
                break;
            }
            await wait(250);
        }
        if (probeState.selectedIndex === null) {
            await captureScreenshot(page, flowState, 'webcam-server-diagnostics', { fullPage: true });
            addIssue(audit, flowState, {
                severity: 'coverage_gap',
                repro_steps: [...flowState.stepLog, '检查服务端摄像头诊断结果。'],
                expected: '严格审计应覆盖服务端摄像头启动 / 停止。',
                observed: `当前环境未拿到稳定的服务端摄像头诊断结果，诊断区: ${probeState.diagnosticsText || '无'}；通知区: ${probeState.notificationText || '无'}`,
                missing_regression: '现有验收会在无摄像头环境下跳过服务端启停，但不会把这部分硬件覆盖空洞单独沉淀成机器可读审计结果。',
            });
            return;
        }
        const beforeHistory = await countHistoryTasks(page);
        await setCameraIndex(page, probeState.selectedIndex);
        flowState.stepLog.push('启动并停止服务端摄像头');
        await page.click('#startWebcamBtn');
        const startOutcome = await waitForNotificationOutcome(page, [
            /摄像头已启动/,
            /服务端摄像头不可用，直接切换浏览器直连/,
            /服务端摄像头启动未完成，尝试浏览器直连/,
            /已切换到浏览器摄像头直连/,
            /浏览器摄像头直连失败/,
        ], 45000);
        suppressRetryableWebcamStartFailures(flowState);
        if (!/摄像头已启动/.test(startOutcome.text)) {
            await captureScreenshot(page, flowState, 'webcam-server-diagnostics-gap', { fullPage: true });
            addIssue(audit, flowState, {
                severity: 'coverage_gap',
                repro_steps: [...flowState.stepLog],
                expected: '若当前环境具备稳定的服务端摄像头，严格审计应完成服务端启停；否则应把硬件覆盖缺口记录下来。',
                observed: `当前环境未完成服务端摄像头启停，通知区显示: ${startOutcome.text || '无'}`,
                missing_regression: '现有验收只在接口层预探测一次，没有沿用页面自己的诊断状态来判断这台机器是否真的具备可持续的服务端摄像头链路。',
            });
            const stopVisible = await page.locator('#stopWebcamBtn').isVisible().catch(() => false);
            if (stopVisible) {
                await page.click('#stopWebcamBtn').catch(() => {});
            }
            return;
        }
        serverStarted = true;
        await captureScreenshot(page, flowState, 'webcam-server-live', { fullPage: true });
        await page.click('#stopWebcamBtn');
        await waitForNotification(page, /摄像头已停止|浏览器摄像头直连已停止/, 30000);
        await waitForHistoryIncrease(page, beforeHistory, 20000);
        const trackingAudit = await auditCurrentTaskTracking(page);
        if (
            !trackingAudit.ok
            || trackingAudit.metricMode !== 'tracking'
            || !trackingAudit.detectionCountMatchesSummary
            || (trackingAudit.detectionCount > 0 && !trackingAudit.allHaveTrackIds)
            || !trackingAudit.cardsMatchSummary
            || !trackingAudit.trackingPrimaryLooksValid
            || !trackingAudit.hasRequiredTrackingCards
            || !trackingAudit.historyMetricMatchesSummary
        ) {
            addIssue(audit, flowState, {
                severity: 'major',
                repro_steps: [...flowState.stepLog, '停止服务端摄像头后检查 summary/detections 接口、当前 summary 卡片和历史项。'],
                expected: '服务端摄像头任务应保存 tracking 型摘要，主指标不能退化回累计检测次数；summary.total_detections 应与检测明细条数一致，检测明细在有结果时应全部携带 track_id，且页面 summary 卡片与历史主指标应和 summary 保持一致。',
                observed: `tracking 审计结果异常: ${JSON.stringify(trackingAudit)}`,
                missing_regression: '现有严格审计在服务端摄像头成功路径上只确认能启停，没有验证其落库 summary 与前端展示是否同口径。',
            });
        }
    } catch (error) {
        if (serverStarted) {
            throw error;
        }
        suppressRetryableWebcamStartFailures(flowState);
        flowState.consoleErrors = [];
        flowState.networkFailures = [];
        await captureScreenshot(page, flowState, 'webcam-server-diagnostics-gap', { fullPage: true }).catch(() => {});
        addIssue(audit, flowState, {
            severity: 'coverage_gap',
            repro_steps: [...flowState.stepLog],
            expected: '若当前环境具备稳定的服务端摄像头，严格审计应完成服务端启停；否则应把硬件覆盖缺口记录下来。',
            observed: `当前环境在服务端摄像头探测 / 启动阶段中断: ${error.message || String(error)}；诊断区: ${probeState.diagnosticsText || '无'}；通知区: ${probeState.notificationText || '无'}`,
            missing_regression: '现有验收没有把无摄像头或虚拟化浏览器里的不稳定服务端摄像头链路统一归档成 coverage gap。',
        });
    }
}

function buildAuditSummary(audit) {
    const severityCounts = audit.issues.reduce((accumulator, issue) => {
        accumulator[issue.severity] = (accumulator[issue.severity] || 0) + 1;
        return accumulator;
    }, {});
    const hasHardIssues = audit.issues.some((issue) => HARD_ISSUE_SEVERITIES.has(issue.severity));
    const hasCoverageGaps = audit.issues.some((issue) => issue.severity === 'coverage_gap');
    return {
        generated_at: new Date().toISOString(),
        base_url: audit.baseUrl,
        setup_base_url: audit.setupBaseUrl,
        browser_path: audit.browserPath,
        heavy_flow_viewports: VIEWPORTS.filter((viewport) => viewport.heavy).map((viewport) => viewport.name),
        artifacts_root: toRelative(audit.artifactRoot),
        run_dir: toRelative(audit.runDir),
        overall_status: hasHardIssues ? 'failed' : hasCoverageGaps ? 'passed_with_coverage_gap' : 'passed',
        severity_counts: severityCounts,
        flows: audit.flows,
        issues: audit.issues,
    };
}

async function main() {
    const args = parseArgs(process.argv);
    const baseUrl = args['base-url'] || process.env.STRICT_AUDIT_BASE_URL;
    const setupBaseUrl = args['setup-base-url'] || process.env.STRICT_AUDIT_SETUP_BASE_URL;
    const artifactRoot = path.resolve(args['artifact-dir'] || process.env.STRICT_AUDIT_ARTIFACT_DIR || DEFAULT_ARTIFACT_DIR);
    const outputPath = path.resolve(args.output || process.env.STRICT_AUDIT_OUTPUT_PATH || DEFAULT_OUTPUT_PATH);
    assert(baseUrl, 'missing --base-url');
    assert(setupBaseUrl, 'missing --setup-base-url');
    for (const [label, targetPath] of Object.entries(SAMPLE_FILES)) {
        assert(fs.existsSync(targetPath), `missing sample file for ${label}: ${targetPath}`);
    }

    ensureDir(artifactRoot);
    ensureDir(path.dirname(outputPath));
    const audit = {
        baseUrl,
        setupBaseUrl,
        baseOrigin: new URL(baseUrl).origin,
        artifactRoot,
        runDir: path.join(artifactRoot, `strict-system-audit-${timestampTag()}`),
        browserPath: findBrowserExecutable(),
        flows: [],
        issues: [],
    };
    ensureDir(audit.runDir);

    for (const viewport of VIEWPORTS) {
        if (viewport.heavy) {
            await runFlow(audit, viewport, 'login-setup-required', {}, auditSetupRequiredLoginFlow);
            await runFlow(audit, viewport, 'login-invalid-credentials', {}, auditInvalidLoginFlow);
            await runFlow(audit, viewport, 'login-success', {}, auditSuccessfulLoginFlow);
            await runFlow(audit, viewport, 'dashboard-workspace', {}, auditDashboardFlow);
            await runFlow(audit, viewport, 'image-report', {}, auditImageFlow);
            await runFlow(audit, viewport, 'batch-task-report', {}, auditBatchFlow);
            await runFlow(audit, viewport, 'video-stop', {}, auditVideoStopFlow);
            await runFlow(audit, viewport, 'webcam-browser-fallback', { fakeMedia: true }, auditWebcamFallbackSuccessFlow);
            await runFlow(audit, viewport, 'video-complete', {}, auditVideoCompleteFlow);
            await runFlow(audit, viewport, 'history-batch-export', {}, auditHistoryBatchExportFlow);
            await runFlow(audit, viewport, 'webcam-server-start-stop', {}, auditServerWebcamFlow);
            await runFlow(
                audit,
                viewport,
                'webcam-browser-failure',
                {
                    extraInitScript: () => {
                        if (navigator.mediaDevices) {
                            navigator.mediaDevices.getUserMedia = async () => {
                                throw new Error('audit forced browser webcam failure');
                            };
                        }
                    },
                },
                auditWebcamFallbackFailureFlow,
            );
            continue;
        }
        if (viewport.name === 'laptop-1366x900') {
            await runFlow(audit, viewport, 'dashboard-workspace', {}, auditDashboardFlow);
            continue;
        }
        await runFlow(audit, viewport, 'image-report', {}, auditImageFlow);
    }

    const summary = buildAuditSummary(audit);
    writeJson(outputPath, summary);
    console.log(`Strict system audit summary written to ${toRelative(outputPath)}`);
    console.log(`Strict system audit issues: ${summary.issues.length}`);
    process.exit(summary.overall_status === 'failed' ? 1 : 0);
}

main().catch((error) => {
    console.error(error.stack || error.message || String(error));
    process.exit(1);
});
