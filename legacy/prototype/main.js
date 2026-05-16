// LEGACY FILE: this script belongs to the retired prototype UI, not the current app shell.
// Current active frontend entry: static/app/main.js
// 全局变量
let currentMode = 'image';
let selectedFiles = [];
let currentTaskId = null;
let webcamInterval = null;
let studentChart = null;
let teacherChart = null;

// 双摄像头轮询
let dualWebcamInterval = null;

// 系统信息（右下角）与 ETA 刷新
let systemInfoInterval = null;
let videoPollingInterval = null;

// 配置信息
let config = {
    confidence: 0.25,
    iou: 0.45,
    frameSkip: 2
};

// 模型信息缓存
let availableModels = [];
let currentModelsInfo = {
    student: null,
    teacher: null
};

// 当前检测数据（用于图片查看器）
let currentDetectionData = null;

// 页面加载完成
$(document).ready(function() {
    initializeApp();
    setupEventListeners();
    loadUserConfig();
    loadConfig();
    checkFirstRun();
});

// 初始化应用
function initializeApp() {
    console.log('应用初始化...');
    initCharts();
    switchMode('image');

    // 系统信息默认占位
    $('#fpsInfo').text('FPS: --');
    $('#detectionCount').text('检测: 0');
}

// 加载用户配置
function loadUserConfig() {
    $.get('/api/user/config', function(response) {
        if (response.success) {
            const userConfig = response.config;
            const params = userConfig.detection_params;
            config.confidence = params.confidence;
            config.iou = params.iou;
            config.frameSkip = params.frame_skip;

            $('#confidenceSlider').val(params.confidence);
            $('#confidenceValue').text(params.confidence);
            $('#iouSlider').val(params.iou);
            $('#iouValue').text(params.iou);
            $('#frameSkip').val(params.frame_skip);

            const lastModels = userConfig.last_models;
            if (lastModels.student || lastModels.teacher) {
                setTimeout(() => {
                    restoreLastModels(lastModels);
                }, 1000);
            }
        }
    });
}

// 检查首次运行
function checkFirstRun() {
    $.get('/api/user/config/first-run', function(response) {
        if (response.is_first_run) {
            setTimeout(() => {
                scanAvailableModels();
                showWelcomeMessage();
            }, 1000);
            $.post('/api/user/config/first-run/done');
        } else {
            loadAvailableModels();
        }
    });
}

function showWelcomeMessage() {
    const message = `
        <div class="alert alert-info alert-dismissible fade show" role="alert">
            <h5><i class="fas fa-rocket"></i> 欢迎使用课堂行为检测系统！</h5>
            <p>这是您第一次使用本系统。系统已自动扫描可用模型。</p>
            <p>请选择模型并开始使用。如需帮助，请查看<strong>使用说明</strong>文档。</p>
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    $('#resultCard').before(message);
}

// 恢复上次的模型选择
function restoreLastModels(lastModels) {
    console.log('恢复模型选择:', lastModels);

    if (lastModels.student) {
        const studentFileName = extractFileName(lastModels.student);
        console.log('学生模型文件名:', studentFileName);
        $('#studentModelSelect').val(studentFileName);
        updateModelInfo('student', studentFileName);
    }
    if (lastModels.teacher) {
        const teacherFileName = extractFileName(lastModels.teacher);
        console.log('人头模型文件名:', teacherFileName);
        $('#teacherModelSelect').val(teacherFileName);
        updateModelInfo('teacher', teacherFileName);
    }

    if (lastModels.student || lastModels.teacher) {
        showAlert('已恢复上次的模型选择', 'info');
    }
}

// 从完整路径中提取文件名
function extractFileName(filePath) {
    if (!filePath) return '';
    const parts = filePath.replace(/\\/g, '/').split('/');
    return parts[parts.length - 1];
}

function saveCurrentModels() {
    const studentModel = $('#studentModelSelect').val();
    const teacherModel = $('#teacherModelSelect').val();

    $.ajax({
        url: '/api/user/config/save-models',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            student: studentModel,
            teacher: teacherModel
        })
    });
}

function saveDetectionParams() {
    $.ajax({
        url: '/api/user/config/detection-params',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            confidence: config.confidence,
            iou: config.iou,
            frame_skip: config.frameSkip
        })
    });
}

// 设置事件监听器
function setupEventListeners() {
    // 导航
    $('#navHistory').click(function(e) {
        e.preventDefault();
        showHistoryModal();
    });

    $('#navSettings').click(function(e) {
        e.preventDefault();
        showSettingsModal();
    });

    // 模式切换
    $('.mode-btn').click(function() {
        const mode = $(this).data('mode');
        $('.mode-btn').removeClass('active');
        $(this).addClass('active');
        switchMode(mode);
    });

    // 双摄像头
    $('#startDualWebcamBtn').click(function() {
        startDualWebcam();
    });
    $('#stopDualWebcamBtn').click(function() {
        stopDualWebcam();
    });

    // 双摄像头画面点击查看详情
    $('#dualWebcamFeedStudent').off('click').on('click', function() {
        if (!$(this).attr('src')) {
            showAlert('双摄像头未启动，暂无画面', 'warning');
            return;
        }
        captureImgElementAndOpenViewer(this);
    });
    $('#dualWebcamFeedTeacher').off('click').on('click', function() {
        if (!$(this).attr('src')) {
            showAlert('双摄像头未启动，暂无画面', 'warning');
            return;
        }
        captureImgElementAndOpenViewer(this);
    });

    // 文件选择
    $('#selectFileBtn').click(function() {
        if (currentMode === 'batch') {
            $('#fileInput').attr('multiple', 'multiple');
        } else {
            $('#fileInput').removeAttr('multiple');
        }
        $('#fileInput').click();
    });

    $('#fileInput').change(function(e) {
        handleFileSelect(e.target.files);
    });

    // 拖拽上传
    const uploadArea = $('#uploadArea');

    uploadArea.on('dragover', function(e) {
        e.preventDefault();
        e.stopPropagation();
        $(this).addClass('drag-over');
    });

    uploadArea.on('dragleave', function(e) {
        e.preventDefault();
        e.stopPropagation();
        $(this).removeClass('drag-over');
    });

    uploadArea.on('drop', function(e) {
        e.preventDefault();
        e.stopPropagation();
        $(this).removeClass('drag-over');
        handleFileSelect(e.originalEvent.dataTransfer.files);
    });

    // 开始检测
    $('#startDetectionBtn').click(function() {
        startDetection();
    });

    // 摄像头
    $('#startWebcamBtn').click(function() {
        startWebcam();
    });

    $('#stopWebcamBtn').click(function() {
        stopWebcam();
    });

    // 参数
    $('#confidenceSlider').on('input', function() {
        const value = $(this).val();
        $('#confidenceValue').text(value);
        config.confidence = parseFloat(value);
        saveDetectionParams();
    });

    $('#iouSlider').on('input', function() {
        const value = $(this).val();
        $('#iouValue').text(value);
        config.iou = parseFloat(value);
        saveDetectionParams();
    });

    $('#frameSkip').change(function() {
        config.frameSkip = parseInt($(this).val());
        saveDetectionParams();
    });

    // 报告
    $('#generateReportBtn').click(function() {
        if (currentTaskId) {
            generateReport(currentTaskId);
        }
    });

    // 模型管理
    $('#scanModelsBtn').click(function() {
        scanAvailableModels();
    });

    $('#viewModelInfoBtn').click(function() {
        console.log('查看当前模型信息按钮被点击');
        viewCurrentModelsInfo();
    });

    $('#loadModelsBtn').click(function() {
        loadModels();
    });

    $('#studentModelSelect').change(function() {
        updateModelInfo('student', $(this).val());
    });

    $('#teacherModelSelect').change(function() {
        updateModelInfo('teacher', $(this).val());
    });

    // 全局事件委托：点击结果图打开详情
    $(document).on('click', '.clickable-image', function() {
        try {
            const detectionDataStr = $(this).attr('data-detection-data');
            if (!detectionDataStr) {
                showAlert('无法加载图片详情，缺少检测数据。', 'danger');
                return;
            }
            const detectionData = JSON.parse(detectionDataStr);
            const imageUrl = detectionData.original_image || $(this).attr('src');
            openImageViewer(imageUrl, detectionData);
        } catch (e) {
            console.error('打开图片查看器时出错:', e);
            showAlert('打开图片详情时出错，请查看控制台。', 'danger');
        }
    });

    // 摄像头画面点击查看详情（截帧检测，不改变原检测流）
    $('#webcamFeed').off('click').on('click', function() {
        if (!$(this).attr('src')) {
            showAlert('摄像头未启动，暂无画面', 'warning');
            return;
        }
        captureImgElementAndOpenViewer(this);
    });
}

// 切换检测模式
function switchMode(mode) {
    currentMode = mode;
    selectedFiles = [];

    $('#uploadCard, #webcamCard, #dualWebcamCard, #resultCard, #progressCard').hide();

    if (mode === 'webcam') {
        $('#webcamCard').show();
    } else if (mode === 'dual-webcam') {
        $('#dualWebcamCard').show();
        loadCameraDevices();
    } else {
        $('#uploadCard').show();
        let hintText = '';
        if (mode === 'image') {
            hintText = '支持 JPG, PNG 格式';
        } else if (mode === 'batch') {
            hintText = '可选择多张图片进行批量检测';
        } else if (mode === 'video') {
            hintText = '支持 MP4, AVI, MOV 格式';
        }
        $('#uploadArea p').text(hintText);
    }

    $('#fileList').empty();
    $('#startDetectionBtn').hide();

    // 双摄像头模式不走上传/检测按钮
    if (mode === 'dual-webcam') {
        $('#fileList').empty();
        $('#startDetectionBtn').hide();
    }
}

// 处理文件选择
function handleFileSelect(files) {
    selectedFiles = Array.from(files);

    if (selectedFiles.length === 0) {
        return;
    }

    const fileList = $('#fileList');
    fileList.empty();

    selectedFiles.forEach((file, index) => {
        const fileItem = $(
            `<div class="file-item fade-in">
                <div class="d-flex align-items-center">
                    <i class="fas fa-file-${getFileIcon(file.name)} text-primary"></i>
                    <div>
                        <strong>${file.name}</strong>
                        <br>
                        <small class="text-muted">${formatFileSize(file.size)}</small>
                    </div>
                </div>
                <i class="fas fa-times remove-file" data-index="${index}"></i>
            </div>`
        );

        fileList.append(fileItem);
    });

    $('.remove-file').click(function() {
        const index = $(this).data('index');
        selectedFiles.splice(index, 1);
        handleFileSelect(selectedFiles);
    });

    if (selectedFiles.length > 0) {
        $('#startDetectionBtn').show();
    }
}

// 开始检测
function startDetection() {
    if (selectedFiles.length === 0) {
        showAlert('请先选择文件', 'warning');
        return;
    }

    console.log('开始检测:', {
        mode: currentMode,
        confidence: config.confidence,
        iou: config.iou,
        frameSkip: config.frameSkip,
        filesCount: selectedFiles.length
    });

    $('#progressCard').show();
    $('#uploadCard').hide();
    $('#resultCard').hide();

    const formData = new FormData();

    if (currentMode === 'image') {
        formData.append('file', selectedFiles[0]);
        formData.append('confidence', config.confidence);
        formData.append('iou', config.iou);

        console.log('发送的参数:', {
            fileName: selectedFiles[0].name,
            confidence: config.confidence,
            iou: config.iou
        });

        detectImage(formData);
    } else if (currentMode === 'batch') {
        selectedFiles.forEach(file => {
            formData.append('files', file);
        });
        formData.append('confidence', config.confidence);
        formData.append('iou', config.iou);
        detectBatch(formData);
    } else if (currentMode === 'video') {
        formData.append('file', selectedFiles[0]);
        formData.append('confidence', config.confidence);
        formData.append('iou', config.iou);
        formData.append('frame_skip', config.frameSkip);
        detectVideo(formData);
    }
}

function detectImage(formData) {
    updateProgress(10, '上传图片中...');

    $.ajax({
        url: '/api/detect/image',
        type: 'POST',
        data: formData,
        processData: false,
        contentType: false,
        success: function(response) {
            updateProgress(100, '检测完成！');
            currentTaskId = response.task_id;
            setTimeout(() => {
                displayImageResult(response);
                updateCharts(response.student_behavior_counts, response.teacher_behavior_counts);
            }, 200);
        },
        error: function(xhr) {
            showAlert('检测失败: ' + (xhr.responseJSON?.error || '未知错误'), 'danger');
            $('#progressCard').hide();
            $('#uploadCard').show();
        }
    });
}

function detectBatch(formData) {
    updateProgress(10, '上传图片中...');

    $.ajax({
        url: '/api/detect/batch',
        type: 'POST',
        data: formData,
        processData: false,
        contentType: false,
        success: function(response) {
            updateProgress(100, '检测完成！');
            currentTaskId = response.task_id;
            setTimeout(() => {
                displayBatchResult(response);
                updateCharts(response.total_student_counts, response.total_teacher_counts);
            }, 200);
        },
        error: function(xhr) {
            showAlert('检测失败: ' + (xhr.responseJSON?.error || '未知错误'), 'danger');
            $('#progressCard').hide();
            $('#uploadCard').show();
        }
    });
}

function detectVideo(formData) {
    updateProgress(10, '上传视频中...');

    $.ajax({
        url: '/api/detect/video',
        type: 'POST',
        data: formData,
        processData: false,
        contentType: false,
        success: function(response) {
            currentTaskId = response.task_id;

            // 新增：如果后端提供实时流，则在结果卡片中边测边播
            if (response.stream_url) {
                displayVideoStreaming(response);
                pollTaskStatusStreaming(response.task_id);
            } else {
                // 兼容旧行为
                pollTaskStatus(response.task_id);
            }
        },
        error: function(xhr) {
            showAlert('检测失败: ' + (xhr.responseJSON?.error || '未知错误'), 'danger');
            $('#progressCard').hide();
            $('#uploadCard').show();
        }
    });
}

function pollTaskStatus(taskId) {
    const pollInterval = setInterval(() => {
        $.get(`/api/task/${taskId}`, function(task) {
            if (task.status === 'completed') {
                clearInterval(pollInterval);
                updateProgress(100, '视频处理完成！');
                $.get(`/api/task/${taskId}/summary`, function(summary) {
                    setTimeout(() => {
                        displayVideoResult(summary);
                        let studentStats = summary.student_behavior_stats;
                        let teacherStats = summary.teacher_behavior_stats;
                        if (typeof studentStats === 'string') {
                            try { studentStats = JSON.parse(studentStats); } catch (e) { studentStats = {}; }
                        }
                        if (typeof teacherStats === 'string') {
                            try { teacherStats = JSON.parse(teacherStats); } catch (e) { teacherStats = {}; }
                        }
                        updateCharts(studentStats, teacherStats);
                    }, 200);
                });
            } else if (task.status === 'failed') {
                clearInterval(pollInterval);
                showAlert('视频处理失败', 'danger');
                $('#progressCard').hide();
                $('#uploadCard').show();
            } else {
                const progress = (task.processed_frames / task.total_frames) * 100 || 0;
                updateProgress(progress, `处理中... ${task.processed_frames}/${task.total_frames} 帧`);
            }
        });
    }, 2000);
}

// // ==================== 视频边测边播（新增，不影响旧逻辑） ====================
// //
// // ==================== 视频边测边播（新增：随机点名 ） ====================
//视频
//
function displayVideoStreaming(response) {
    $('#progressCard').hide();
    $('#resultCard').show();

    const streamUrl = response.stream_url;
    const taskId = response.task_id;

    const content = `
        <div class="mb-2">
            <div class="d-flex justify-content-between align-items-center">
                <h6 class="mb-2"><i class="fas fa-video"></i> 视频实时检测预览</h6>
                <span class="badge bg-warning text-dark" id="videoStreamingStatus">处理中</span>
            </div>
            <div class="text-center" style="background:#f8f9fa; border-radius:10px; padding:10px; position:relative;">
                <img id="videoStreamingImg" src="${streamUrl}?t=${Date.now()}" class="img-fluid clickable-video-frame" style="max-height:70vh; border-radius:10px; cursor:pointer;" alt="视频检测流">
                <div class="position-absolute top-0 end-0 m-2">
                    <button class="btn btn-sm-outline-primary" id="videoFrameDetailBtn" style="font-size: 18px; color: white;>
                        <i class="fas fa-search-plus"></i> 查看详情
                    </button>
                </div>
            </div>
        </div>

        <div class="mb-2 d-flex justify-content-between align-items-center">
            <div class="text-muted" id="videoEtaText">预计剩余时间：--</div>
            <div>
                <button class="btn btn-danger btn-sm" id="stopVideoBtn" data-task-id="${taskId}">
                    <i class="fas fa-stop"></i> 停止检测
                </button>
                <button class="btn btn-warning btn-sm ms-2" id="videoRandomCallBtn">
                    <i class="fas fa-bullseye"></i> 随机点名
                </button>
            </div>
        </div>

        <div class="mb-3">
            <div class="progress-bar" style="height: 22px;">
                <div class="progress-bar progress-bar-striped progress-bar-animated" id="videoStreamingProgressBar" role="progressbar" style="width: 0%"></div>
            </div>
            <div class="text-muted mt-1" id="videoStreamingProgressText">准备中...</div>
        </div>

        <div class="mt-3" id="videoFinalResult" style="display:none;"></div>
    `;

    $('#resultContent').html(content);

    $('#videoFrameDetailBtn').off('click').on('click', function () {
        captureImgElementAndOpenViewer($('#videoStreamingImg')[0]);
    });

    $('#stopVideoBtn').off('click').on('click', function () {
        const tid = $(this).data('task-id');
        if (!confirm('确定停止检测？')) return;
        $.post(`/api/detect/video/stop/${tid}`, () => {
            $('#videoStreamingStatus').removeClass('bg-warning').addClass('bg-secondary').text('已停止');
        });
    });

    // ===========================
    // ✅ 最终版：真正干净原图随机点名
    // ===========================
    $('#videoRandomCallBtn').off('click').on('click', function () {
        $.get(`/api/task/${taskId}/original_frame`, function (res) {
            if (!res.success) {
                showAlert('获取原始帧失败');
                return;
            }

            const originalImage = res.image;

            $.ajax({
                url: '/api/detect/frame',
                type: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({ image: originalImage }),
                success: function (detRes) {
                    if (!detRes.success || !detRes.teacher_detections || detRes.teacher_detections.length === 0) {
                        showAlert('未检测到人头');
                        return;
                    }

                    const boxes = detRes.teacher_detections;
                    const target = boxes[Math.floor(Math.random() * boxes.length)];
                    const [x, y, x2, y2] = target.bbox;

                    const img = new Image();
                    img.onload = function () {
                        const c = document.createElement('canvas');
                        c.width = img.width;
                        c.height = img.height;
                        const cx = c.getContext('2d');
                        cx.drawImage(img, 0, 0);
                        cx.strokeStyle = '#ff0000';
                        cx.lineWidth = 4;
                        cx.strokeRect(x, y, x2 - x, y2 - y);
                    
                        const crop = document.createElement('canvas');
                        crop.width = (x2 - x) * 3;
                        crop.height = (y2 - y) * 3;
                        const ccx = crop.getContext('2d');
                        ccx.drawImage(img, x, y, x2 - x, y2 - y, 0, 0, (x2 - x) * 3, (y2 - y) * 3);

                        showRandomModal(c.toDataURL(), crop.toDataURL());
                    };
                    img.src = originalImage;
                }
            });
        });
    });

    $('#generateReportBtn').off('click').on('click', function () {
        const tid = $(this).data('task-id');
        if (tid) generateReport(tid);
    });

    $('#downloadResultBtn').off('click').on('click', function () {
        const tid = $(this).data('task-id');
        if (tid) window.open(`/api/task/${tid}/download`, '_blank');
    });
}

// 截取图片元素并打开查看器
function captureImgElementAndOpenViewer(imgElement) {
    // 创建canvas来获取当前帧
    const canvas = document.createElement('canvas');
    canvas.width = imgElement.naturalWidth || imgElement.videoWidth || imgElement.width;
    canvas.height = imgElement.naturalHeight || imgElement.videoHeight || imgElement.height;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(imgElement, 0, 0, canvas.width, canvas.height);
    
    // 获取base64数据
    const imgDataUrl = canvas.toDataURL('image/jpeg', 0.9);
    
    // 显示加载中
    const loading = showAlert('正在分析当前帧...', 'info');
    
    // 发送到后端检测
    $.ajax({
        url: '/api/detect/frame',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ image: imgDataUrl }),
        success: function(response) {
            if (response.success) {
                // 使用现有的图片查看器打开结果
                openImageViewer(
                    response.annotated_image || imgDataUrl, // 优先使用带标注的图
                    {
                        student_detections: response.student_detections || [],
                        teacher_detections: response.teacher_detections || [],
                        student_behavior_counts: response.student_behavior_counts || {},
                        teacher_behavior_counts: response.teacher_behavior_counts || {}
                    }
                );
            } else {
                showAlert('分析失败: ' + (response.error || '未知错误'), 'danger');
            }
        },
        error: function(xhr) {
            showAlert('请求失败: ' + (xhr.responseJSON?.error || '网络错误'), 'danger');
        },
        complete: function() {
            // 关闭加载提示
            if (loading && typeof loading.close === 'function') {
                loading.close();
            } else {
                $('.alert').alert('close');
            }
        }
    });
}

// 截取 video 当前帧并打开查看器
function captureVideoElementAndOpenViewer(videoEl) {
    try {
        const canvas = document.createElement('canvas');
        canvas.width = videoEl.videoWidth || videoEl.clientWidth;
        canvas.height = videoEl.videoHeight || videoEl.clientHeight;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);
        const imgDataUrl = canvas.toDataURL('image/jpeg', 0.9);

        const loading = showAlert('正在分析当前帧...', 'info');
        $.ajax({
            url: '/api/detect/frame',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ image: imgDataUrl }),
            success: function(response) {
                if (response.success) {
                    openImageViewer(
                        response.annotated_image || imgDataUrl,
                        {
                            student_detections: response.student_detections || [],
                            teacher_detections: response.teacher_detections || [],
                            student_behavior_counts: response.student_behavior_counts || {},
                            teacher_behavior_counts: response.teacher_behavior_counts || {}
                        }
                    );
                } else {
                    showAlert('分析失败: ' + (response.error || '未知错误'), 'danger');
                }
            },
            error: function(xhr) {
                showAlert('请求失败: ' + (xhr.responseJSON?.error || '网络错误'), 'danger');
            },
            complete: function() {
                if (loading && typeof loading.close === 'function') loading.close();
            }
        });
    } catch (e) {
        console.error(e);
        showAlert('截帧失败，请暂停视频后重试', 'warning');
    }
}

function pollTaskStatusStreaming(taskId) {
    const pollInterval = setInterval(() => {
        // 1) 更新任务进度
        $.get(`/api/task/${taskId}`, function(task) {
            if (task.status === 'completed') {
                clearInterval(pollInterval);

                $('#videoStreamingStatus')
                    .removeClass('bg-warning text-dark')
                    .addClass('bg-success')
                    .text('已完成');

                $('#videoStreamingProgressBar')
                    .removeClass('progress-bar-animated')
                    .removeClass('progress-bar-striped')
                    .css('width', '100%');

                $('#videoEtaText').text('预计剩余时间：0s');
                $('#videoStreamingProgressText').text('视频处理完成，正在加载最终视频...');

                // 拉取 summary，显示最终视频（复用现有 displayVideoResult）
                $.get(`/api/task/${taskId}/summary`, function(summary) {
                    displayVideoResult(summary);

                    let studentStats = summary.student_behavior_stats;
                    let teacherStats = summary.teacher_behavior_stats;
                    if (typeof studentStats === 'string') {
                        try { studentStats = JSON.parse(studentStats); } catch (e) { studentStats = {}; }
                    }
                    if (typeof teacherStats === 'string') {
                        try { teacherStats = JSON.parse(teacherStats); } catch (e) { teacherStats = {}; }
                    }
                    updateCharts(studentStats, teacherStats);

                    // 完成后系统信息复位
                    $('#fpsInfo').text('FPS: --');
                });

            } else if (task.status === 'failed') {
                clearInterval(pollInterval);
                $('#videoStreamingStatus')
                    .removeClass('bg-warning text-dark')
                    .addClass('bg-secondary')
                    .text('已停止/失败');
                $('#videoStreamingProgressBar')
                    .removeClass('progress-bar-animated')
                    .removeClass('progress-bar-striped')
                    .addClass('bg-secondary')
                    .css('width', '100%');
                $('#videoStreamingProgressText').text('视频检测已停止或失败');
                $('#videoEtaText').text('预计剩余时间：--');
                $('#fpsInfo').text('FPS: --');

            } else {
                const total = task.total_frames || 0;
                const processed = task.processed_frames || 0;
                const progress = total > 0 ? Math.min(99, (processed / total) * 100) : 0;

                $('#videoStreamingProgressBar').css('width', progress.toFixed(1) + '%');
                $('#videoStreamingProgressText').text(`处理中... ${processed}/${total} 帧`);
            }
        });

        // 2) 更新实时指标（FPS / ETA / 检测数 -> 系统信息）
        $.get(`/api/detect/video/metrics/${taskId}`, function(resp) {
            if (!resp || !resp.success) return;

            if (resp.fps != null) {
                $('#fpsInfo').text('FPS: ' + Number(resp.fps).toFixed(1));
            }
            if (resp.total_detections != null) {
                $('#detectionCount').text('检测: ' + resp.total_detections);
            }
            if (resp.eta_seconds != null) {
                $('#videoEtaText').text('预计剩余时间：' + formatSeconds(resp.eta_seconds));
            }
        });
    }, 1000);
}

// 显示单张图片结果
function displayImageResult(response) {
    $('#progressCard').hide();
    $('#resultCard').show();

    const content = $(
        `<div class="result-image-container">
            <img src="${response.result_image}" class="result-image clickable-image" alt="检测结果" 
                 data-detection-data='${JSON.stringify(response)}'>
            <div class="image-overlay">
                <i class="fas fa-search-plus"></i> 点击查看详情
            </div>
        </div>
        
        <div class="row mt-3">
            <div class="col-md-6">
                <h6 class="text-primary"><i class="fas fa-user-graduate"></i> 学生行为</h6>
                <div id="studentDetections"></div>
            </div>
            <div class="col-md-6">
                <h6 class="text-success"><i class="fas fa-chalkboard-teacher"></i> 人头</h6>
                <div id="teacherDetections"></div>
            </div>
        </div>
        
        <div class="mt-3">
            <button class="btn btn-primary" id="detectAgainBtn">
                <i class="fas fa-redo"></i> 再次检测
            </button>
            <button class="btn btn-warning" id="randomCallBtn">
                <i class="fas fa-random"></i> 随机点名
            </button>
        </div>`
    );

    $('#resultContent').html(content);
    displayBehaviorList('#studentDetections', response.student_behavior_counts);
    displayBehaviorList('#teacherDetections', response.teacher_behavior_counts);

    $('#detectAgainBtn').click(function() {
        resetDetectionUI();
    });
        // ✅ 正确：写在函数内部，能正常绑定
    $('#randomCallBtn').click(function () {
        console.log("✅ 随机点名按钮点击");
        randomCallRoll(response);
    });
}
function displayBatchResult(response) {
    $('#progressCard').hide();
    $('#resultCard').show();

    let gridHTML = '<div class="batch-results-grid">';

    response.results.forEach((result) => {
        // 批量模式目前未返回每张图的详细detections（后续可扩展）
        const detectionData = {
            student_behavior_counts: {},
            teacher_behavior_counts: {},
            student_detections: [],
            teacher_detections: []
        };

        gridHTML += `
            <div class="batch-result-item fade-in">
                <img src="${result.result_image}" alt="${result.filename}" 
                     class="clickable-image" 
                     data-detection-data='${JSON.stringify(detectionData)}'>
                <div class="image-overlay-mini">
                    <i class="fas fa-search-plus"></i>
                </div>
                <h6>${result.filename}</h6>
                <p class="mb-0">
                    <span class="badge student-badge">学生: ${result.student_count}</span>
                    <span class="badge teacher-badge">人头: ${result.teacher_count}</span>
                </p>
            </div>
        `;
    });

    gridHTML += '</div>';
    gridHTML += `
        <div class="mt-3">
            <button class="btn btn-primary" id="detectAgainBtn">
                <i class="fas fa-redo"></i> 再次检测
            </button>
        </div>
    `;

    $('#resultContent').html(gridHTML);

    $('#detectAgainBtn').click(function() {
        resetDetectionUI();
    });
}

function displayVideoResult(summary) {
    $('#progressCard').hide();
    $('#resultCard').show();

    const videoFile = summary.file_name;
    const outputVideo = `/outputs/result_${summary.task_id}_${videoFile}`;

    const content = $(
        `<div class="position-relative">
            <video id="resultVideoPlayer" controls class="result-image w-100" style="cursor:pointer;" title="暂停后点击查看当前帧详情">
                <source src="${outputVideo}" type="video/mp4">
                您的浏览器不支持视频播放
            </video>
            <div class="position-absolute top-0 end-0 m-2">
                <button class="btn btn-sm btn-outline-primary" id="videoPlayerFrameDetailBtn" title="查看当前帧详情">
                    <i class="fas fa-search-plus"></i> 查看详情
                </button>
            </div>
        </div>
        
        <div class="row mt-3">
            <div class="col-md-3">
                <div class="info-card">
                    <small class="text-muted">处理帧数</small>
                    <h4>${summary.processed_frames}</h4>
                </div>
            </div>
            <div class="col-md-3">
                <div class="info-card">
                    <small class="text-muted">总检测数</small>
                    <h4>${summary.total_detections}</h4>
                </div>
            </div>
            <div class="col-md-3">
                <div class="info-card">
                    <small class="text-muted">平均置信度</small>
                    <h4>${(summary.average_confidence * 100).toFixed(1)}%</h4>
                </div>
            </div>
            <div class="col-md-3">
                <div class="info-card">
                    <small class="text-muted">处理时长</small>
                    <h4>${summary.duration.toFixed(1)}s</h4>
                </div>
            </div>
        </div>
        
        <div class="mt-3">
            <button class="btn btn-primary" id="detectAgainBtn">
                <i class="fas fa-redo"></i> 再次检测
            </button>
        </div>`
    );

    $('#resultContent').html(content);

    // 查看当前帧详情（最终播放器）
    $('#videoPlayerFrameDetailBtn').off('click').on('click', function() {
        const videoEl = document.getElementById('resultVideoPlayer');
        if (videoEl) captureVideoElementAndOpenViewer(videoEl);
    });
    $('#resultVideoPlayer').off('click').on('click', function() {
        // 建议暂停后再点，避免取到模糊帧
        captureVideoElementAndOpenViewer(this);
    });

    $('#detectAgainBtn').click(function() {
        resetDetectionUI();
    });
}

// 重置检测界面
function resetDetectionUI() {
    selectedFiles = [];
    $('#fileInput').val('');
    $('#fileList').empty();
    $('#startDetectionBtn').hide();

    $('#resultCard').hide();
    $('#progressCard').hide();
    $('#uploadCard').show();

    if (studentChart) {
        studentChart.data.labels = [];
        studentChart.data.datasets[0].data = [];
        studentChart.update();
    }
    if (teacherChart) {
        teacherChart.data.labels = [];
        teacherChart.data.datasets[0].data = [];
        teacherChart.update();
    }
}

// 显示行为列表
function displayBehaviorList(selector, behaviors) {
    const container = $(selector);
    container.empty();

    if (!behaviors || Object.keys(behaviors).length === 0) {
        container.html('<p class="text-muted">未检测到行为</p>');
        return;
    }

    const total = Object.values(behaviors).reduce((a, b) => a + b, 0);

    Object.entries(behaviors).forEach(([behavior, count]) => {
        const percentage = ((count / total) * 100).toFixed(1);
        const item = $(
            `<div class="behavior-stat-item">
                <span class="behavior-name">${behavior}</span>
                <div>
                    <span class="behavior-count">${count}</span>
                    <span class="behavior-percentage">${percentage}%</span>
                </div>
            </div>`
        );
        container.append(item);
    });
}

// 启动摄像头
// function startWebcam() {
//     $.ajax({
//         url: '/api/webcam/start',
//         type: 'POST',
//         contentType: 'application/json',
//         data: JSON.stringify({
//             confidence: config.confidence,
//             iou: config.iou
//         }),
//         success: function() {
//             $('#webcamFeed').attr('src', '/api/webcam/feed?t=' + Date.now());
//             $('#startWebcamBtn').hide();
//             $('#stopWebcamBtn').show();
//             webcamInterval = setInterval(updateWebcamStats, 1000);
//             showAlert('摄像头已启动', 'success');
//         },
//         error: function(xhr) {
//             showAlert('启动失败: ' + (xhr.responseJSON?.error || '未知错误'), 'danger');
//         }
//     });
// }
// 启动摄像头 + 新增随机点名按钮
// 启动摄像头（自动处理重复运行问题）
function startWebcam() {
    // ✅ 关键：先停止可能正在运行的摄像头，再启动
    $.post('/api/webcam/stop', function() {
        console.log("先停止已有摄像头");
    }).always(function() {
        // 停止后再启动
        $.ajax({
            url: '/api/webcam/start',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                confidence: config.confidence,
                iou: config.iou
            }),
            success: function() {
                $('#webcamFeed').attr('src', '/api/webcam/feed?t=' + Date.now());
                $('#startWebcamBtn').hide();
                $('#stopWebcamBtn').show();

                // 随机点名按钮
                $('#webcamRandomCallBtn').remove();
                $('#webcamCard .card-body').append(`
                    <button id="webcamRandomCallBtn" class="btn btn-warning mt-3 w-100">
                        <i class="fas fa-bullseye"></i> 随机点名
                    </button>
                `);

                $('#webcamRandomCallBtn').off('click').on('click', function () {
                    webcamRandomCall();
                });

                clearInterval(webcamInterval);
                webcamInterval = setInterval(updateWebcamStats, 1000);
                showAlert('摄像头已启动', 'success');
            },
            error: function(xhr) {
                showAlert('启动失败: ' + (xhr.responseJSON?.error || '未知错误'), 'danger');
            }
        });
    });
}

// function stopWebcam() {
//     $.post('/api/webcam/stop', function() {
//         $('#webcamFeed').attr('src', '');
//         $('#startWebcamBtn').show();
//         $('#stopWebcamBtn').hide();
//         if (webcamInterval) {
//             clearInterval(webcamInterval);
//             webcamInterval = null;
//         }
//         showAlert('摄像头已停止', 'info');
//     });
// }
function stopWebcam() {
    $.post('/api/webcam/stop', function() {
        $('#webcamFeed').attr('src', '');
        $('#startWebcamBtn').show();
        $('#stopWebcamBtn').hide();

        // ✅ 清除随机点名按钮
        $('#webcamRandomCallBtn').remove();

        if (webcamInterval) {
            clearInterval(webcamInterval);
            webcamInterval = null;
        }
        showAlert('摄像头已停止', 'info');
    });
}

// ==================== 双摄像头（新增，不影响原单摄像头） ====================
function startDualWebcam() {
    const studentIdx = parseInt($('#studentCameraSelect').val());
    const teacherIdx = parseInt($('#teacherCameraSelect').val());
    if (isNaN(studentIdx) || isNaN(teacherIdx)) {
        showAlert('请选择两个摄像头', 'warning');
        return;
    }

    $.ajax({
        url: '/api/webcam/dual/start',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            student_camera_index: studentIdx,
            teacher_camera_index: teacherIdx,
            confidence: config.confidence,
            iou: config.iou
        }),
        success: function(resp) {
            $('#dualWebcamFeedStudent').attr('src', '/api/webcam/dual/feed/student?t=' + Date.now());
            $('#dualWebcamFeedTeacher').attr('src', '/api/webcam/dual/feed/teacher?t=' + Date.now());
            $('#startDualWebcamBtn').hide();
            $('#stopDualWebcamBtn').show();

            // 每秒刷新统计与系统信息（复用现有渲染方式）
            if (dualWebcamInterval) clearInterval(dualWebcamInterval);
            dualWebcamInterval = setInterval(updateDualWebcamStats, 1000);

            showAlert('双摄像头已启动', 'success');
        },
        error: function(xhr) {
            showAlert('启动失败: ' + (xhr.responseJSON?.error || '未知错误'), 'danger');
        }
    });
}

function stopDualWebcam() {
    $.post('/api/webcam/dual/stop', function() {
        $('#dualWebcamFeedStudent').attr('src', '');
        $('#dualWebcamFeedTeacher').attr('src', '');
        $('#startDualWebcamBtn').show();
        $('#stopDualWebcamBtn').hide();

        if (dualWebcamInterval) {
            clearInterval(dualWebcamInterval);
            dualWebcamInterval = null;
        }

        showAlert('双摄像头已停止', 'info');
    }).fail(function(xhr) {
        showAlert('停止失败: ' + (xhr.responseJSON?.error || '未知错误'), 'danger');
    });
}

function updateDualWebcamStats() {
    $.get('/api/webcam/dual/stats', function(stats) {
        // 双摄像头：学生画面 -> student_*，人头画面 -> teacher_*
        // 仍然把两边统计更新到右侧面板（与原体验一致）
        updateCharts(stats.student_behavior_ratios || {}, stats.teacher_behavior_ratios || {});
        displayRealtimeStats({
            student_counts: stats.student_counts || {},
            teacher_counts: stats.teacher_counts || {},
            student_behavior_ratios: stats.student_behavior_ratios || {},
            teacher_behavior_ratios: stats.teacher_behavior_ratios || {}
        });

        // 系统信息
        if (stats && stats.fps != null) {
            $('#fpsInfo').text('FPS: ' + Number(stats.fps).toFixed(1));
        }
        if (stats && stats.total_detections != null) {
            $('#detectionCount').text('检测: ' + stats.total_detections);
        }
        if (stats && stats.uptime_seconds != null) {
            $('#fpsInfo').text($('#fpsInfo').text() + ' | 时长: ' + formatSeconds(stats.uptime_seconds));
        }
    });
}

function updateWebcamStats() {
    $.get('/api/webcam/stats', function(stats) {
        updateCharts(stats.student_behavior_ratios, stats.teacher_behavior_ratios);
        displayRealtimeStats(stats);

        // 更新系统信息（与右侧占比同步刷新）
        if (stats && stats.fps != null) {
            $('#fpsInfo').text('FPS: ' + Number(stats.fps).toFixed(1));
        }
        if (stats && stats.total_detections != null) {
            $('#detectionCount').text('检测: ' + stats.total_detections);
        }
        if (stats && stats.uptime_seconds != null) {
            // 在FPS旁边显示运行时长
            $('#fpsInfo').text($('#fpsInfo').text() + ' | 时长: ' + formatSeconds(stats.uptime_seconds));
        }
    });
}

function displayRealtimeStats(stats) {
    const studentContainer = $('#studentStats');
    studentContainer.empty();

    Object.entries(stats.student_counts).forEach(([behavior, count]) => {
        const ratio = stats.student_behavior_ratios[behavior] || 0;
        studentContainer.append(`
            <div class="realtime-stat">
                <span class="stat-label">${behavior}</span>
                <div>
                    <span class="stat-value">${count}</span>
                    <small class="text-muted">(${ratio.toFixed(1)}%)</small>
                </div>
            </div>
        `);
    });

    const teacherContainer = $('#teacherStats');
    teacherContainer.empty();

    Object.entries(stats.teacher_counts).forEach(([behavior, count]) => {
        const ratio = stats.teacher_behavior_ratios[behavior] || 0;
        teacherContainer.append(`
            <div class="realtime-stat">
                <span class="stat-label">${behavior}</span>
                <div>
                    <span class="stat-value">${count}</span>
                    <small class="text-muted">(${ratio.toFixed(1)}%)</small>
                </div>
            </div>
        `);
    });
}

// 初始化图表
function initCharts() {
    const chartConfig = {
        type: 'doughnut',
        data: {
            labels: [],
            datasets: [{
                data: [],
                backgroundColor: [
                    '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0',
                    '#9966FF', '#FF9F40', '#FF6384', '#C9CBCF'
                ]
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    position: 'bottom'
                }
            }
        }
    };

    const studentCtx = document.getElementById('studentChart').getContext('2d');
    studentChart = new Chart(studentCtx, JSON.parse(JSON.stringify(chartConfig)));

    const teacherCtx = document.getElementById('teacherChart').getContext('2d');
    teacherChart = new Chart(teacherCtx, JSON.parse(JSON.stringify(chartConfig)));
}

function updateCharts(studentData, teacherData) {
    if (studentData && Object.keys(studentData).length > 0) {
        studentChart.data.labels = Object.keys(studentData);
        studentChart.data.datasets[0].data = Object.values(studentData);
        studentChart.update();
    }

    if (teacherData && Object.keys(teacherData).length > 0) {
        teacherChart.data.labels = Object.keys(teacherData);
        teacherChart.data.datasets[0].data = Object.values(teacherData);
        teacherChart.update();
    }
}

function updateProgress(percent, text) {
    $('#progressBar').css('width', percent + '%').attr('aria-valuenow', percent);
    $('#progressText').text(text);
}

function generateReport(taskId) {
    $.get(`/api/report/${taskId}`, function(response) {
        if (response.success) {
            window.open(response.report_url, '_blank');
            showAlert('报告生成成功！', 'success');
        }
    }).fail(function(xhr) {
        showAlert('报告生成失败: ' + (xhr.responseJSON?.error || '未知错误'), 'danger');
    });
}

function loadConfig() {
    $.get('/api/config', function(conf) {
        console.log('配置加载成功', conf);
    });
}

function scanAvailableModels() {
    showAlert('正在扫描模型...', 'info');

    $.get('/api/models/scan', function(response) {
        if (response.success) {
            availableModels = response.models;

            const studentSelect = $('#studentModelSelect');
            const teacherSelect = $('#teacherModelSelect');

            const currentStudent = studentSelect.val();
            const currentTeacher = teacherSelect.val();

            studentSelect.empty();
            teacherSelect.empty();

            studentSelect.append('<option value="">请选择模型...</option>');
            teacherSelect.append('<option value="">请选择模型...</option>');

            availableModels.forEach(model => {
                const optionText = model.error ? `${model.filename} (加载失败)` : `${model.filename} (${model.num_classes}类)`;
                if (!model.error) {
                    studentSelect.append(`<option value="${model.filename}">${optionText}</option>`);
                    teacherSelect.append(`<option value="${model.filename}">${optionText}</option>`);
                }
            });

            if (currentStudent) studentSelect.val(currentStudent);
            if (currentTeacher) teacherSelect.val(currentTeacher);

            showAlert(`发现 ${response.total} 个模型文件`, 'success');
            if (availableModels.length > 0) {
                showModelsDetails(availableModels);
            }
        } else {
            showAlert('扫描失败: ' + response.error, 'danger');
        }
    }).fail(function() {
        showAlert('扫描失败，请检查模型目录', 'danger');
    });
}

function showModelsDetails(models) {
    let detailsHTML = '<div class="models-details">';

    models.forEach(model => {
        if (model.error) {
            detailsHTML += `
                <div class="alert alert-danger">
                    <h6><i class="fas fa-exclamation-triangle"></i> ${model.filename}</h6>
                    <p class="mb-0">错误: ${model.error}</p>
                </div>
            `;
        } else {
            detailsHTML += `
                <div class="card mb-3">
                    <div class="card-header bg-primary text-white">
                        <h6 class="mb-0"><i class="fas fa-file"></i> ${model.filename}</h6>
                    </div>
                    <div class="card-body">
                        <p><strong>文件大小:</strong> ${model.file_size_mb} MB</p>
                        <p><strong>类别数量:</strong> ${model.num_classes}</p>
                        <p><strong>类别列表:</strong></p>
                        <div class="badge-container">
                            ${model.classes.map(c => `<span class="badge bg-info me-1 mb-1">${c}</span>`).join('')}
                        </div>
                    </div>
                </div>
            `;
        }
    });

    detailsHTML += '</div>';

    const modal = $(
        `<div class="modal fade" id="modelsDetailsModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header bg-primary text-white">
                        <h5 class="modal-title"><i class="fas fa-list"></i> 可用模型详情</h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body" style="max-height: 60vh; overflow-y: auto;">
                        ${detailsHTML}
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                    </div>
                </div>
            </div>
        </div>`
    );

    $('#modelsDetailsModal').remove();
    $('body').append(modal);
    const bsModal = new bootstrap.Modal(document.getElementById('modelsDetailsModal'));
    bsModal.show();
}

function updateModelInfo(modelType, filename) {
    if (!filename) {
        $(`#${modelType}ModelInfo`).text('暂无信息');
        return;
    }

    const model = availableModels.find(m => m.filename === filename);

    if (model && !model.error) {
        const infoText = `${model.num_classes} 个类别: ${model.classes.slice(0, 3).join(', ')}${model.classes.length > 3 ? '...' : ''}`;
        $(`#${modelType}ModelInfo`).text(infoText);
    } else {
        $(`#${modelType}ModelInfo`).text('模型信息不可用');
    }
}

function viewCurrentModelsInfo() {
    console.log('开始获取当前模型信息...');
    $.get('/api/models/info', function(response) {
        console.log('获取模型信息响应:', response);
        if (response.success) {
            currentModelsInfo = {
                student: response.student_model,
                teacher: response.teacher_model
            };
            showCurrentModelsInfo(currentModelsInfo);
        } else {
            showAlert('获取模型信息失败: ' + response.error, 'danger');
        }
    }).fail(function(xhr, status, error) {
        console.error('获取模型信息失败:', status, error);
        showAlert('获取模型信息失败: ' + error, 'danger');
    });
}

function showCurrentModelsInfo(info) {
    let infoHTML = '<div class="current-models-info">';

    infoHTML += '<div class="card mb-3">';
    infoHTML += '<div class="card-header bg-primary text-white">';
    infoHTML += '<h6 class="mb-0"><i class="fas fa-user-graduate"></i> 学生行为模型</h6>';
    infoHTML += '</div>';
    infoHTML += '<div class="card-body">';

    if (info.student.loaded) {
        infoHTML += `<p><strong>模型路径:</strong> ${info.student.path}</p>`;
        infoHTML += `<p><strong>类别数量:</strong> ${info.student.num_classes}</p>`;
        infoHTML += `<p><strong>检测类别:</strong></p>`;
        infoHTML += '<div class="badge-container">';
        info.student.classes.forEach(cls => {
            infoHTML += `<span class="badge bg-primary me-1 mb-1">${cls}</span>`;
        });
        infoHTML += '</div>';
    } else {
        infoHTML += `<div class="alert alert-warning mb-0">模型未加载或加载失败</div>`;
        if (info.student.error) {
            infoHTML += `<p class="text-danger mt-2">错误: ${info.student.error}</p>`;
        }
    }

    infoHTML += '</div></div>';

    infoHTML += '<div class="card mb-3">';
    infoHTML += '<div class="card-header bg-success text-white">';
    infoHTML += '<h6 class="mb-0"><i class="fas fa-chalkboard-teacher"></i> 点名模型</h6>';
    infoHTML += '</div>';
    infoHTML += '<div class="card-body">';

    if (info.teacher.loaded) {
        infoHTML += `<p><strong>模型路径:</strong> ${info.teacher.path}</p>`;
        infoHTML += `<p><strong>类别数量:</strong> ${info.teacher.num_classes}</p>`;
        infoHTML += `<p><strong>检测类别:</strong></p>`;
        infoHTML += '<div class="badge-container">';
        info.teacher.classes.forEach(cls => {
            infoHTML += `<span class="badge bg-success me-1 mb-1">${cls}</span>`;
        });
        infoHTML += '</div>';
    } else {
        infoHTML += `<div class="alert alert-warning mb-0">模型未加载或加载失败</div>`;
        if (info.teacher.error) {
            infoHTML += `<p class="text-danger mt-2">错误: ${info.teacher.error}</p>`;
        }
    }

    infoHTML += '</div></div>';
    infoHTML += '</div>';

    const modal = $(
        `<div class="modal fade" id="currentModelsModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header bg-info text-white">
                        <h5 class="modal-title"><i class="fas fa-info-circle"></i> 当前模型信息</h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        ${infoHTML}
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                    </div>
                </div>
            </div>
        </div>`
    );

    $('#currentModelsModal').remove();
    $('body').append(modal);
    const bsModal = new bootstrap.Modal(document.getElementById('currentModelsModal'));
    bsModal.show();
}

function loadAvailableModels() {
    scanAvailableModels();
}

function loadModels() {
    const studentModel = $('#studentModelSelect').val();
    const teacherModel = $('#teacherModelSelect').val();

    if (!studentModel && !teacherModel) {
        showAlert('请至少选择一个模型', 'warning');
        return;
    }

    showAlert('正在加载模型...', 'info');

    const promises = [];

    if (studentModel) {
        promises.push(
            $.ajax({
                url: '/api/models/load',
                type: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({
                    type: 'student',
                    model: studentModel
                })
            })
        );
    }

    if (teacherModel) {
        promises.push(
            $.ajax({
                url: '/api/models/load',
                type: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({
                    type: 'teacher',
                    model: teacherModel
                })
            })
        );
    }

    Promise.all(promises)
        .then(() => {
            showAlert('模型加载成功！系统将使用新的模型进行检测。', 'success');
            saveCurrentModels();
            setTimeout(() => {
                viewCurrentModelsInfo();
            }, 500);
        })
        .catch((error) => {
            showAlert('模型加载失败: ' + (error.responseJSON?.error || '未知错误'), 'danger');
        });
}

// ==================== 历史记录功能（保留） ====================
function showHistoryModal() {
    $.get('/api/tasks/recent?limit=50', function(tasks) {
        const historyList = $('#historyList');
        historyList.empty();

        if (tasks.length === 0) {
            historyList.html('<div class="empty-state"><i class="fas fa-inbox"></i><h5>暂无历史记录</h5></div>');
        } else {
            tasks.forEach(task => {
                const item = createHistoryItem(task);
                historyList.append(item);
            });
        }

        const modal = new bootstrap.Modal(document.getElementById('historyModal'));
        modal.show();
    });
}

function createHistoryItem(task) {
    const createdDate = new Date(task.created_at).toLocaleString('zh-CN');
    const statusBadge = task.status === 'completed' ?
        '<span class="badge bg-success">已完成</span>' :
        '<span class="badge bg-warning">处理中</span>';

    const typeIcons = {
        'image': 'fa-image',
        'batch': 'fa-images',
        'video': 'fa-video',
        'webcam': 'fa-camera'
    };

    const icon = typeIcons[task.task_type] || 'fa-file';

    return $(
        `<div class="history-item card mb-2">
            <div class="card-body">
                <div class="d-flex justify-content-between align-items-start">
                    <div>
                        <h6 class="mb-1">
                            <i class="fas ${icon}"></i> ${task.file_name || '未命名任务'}
                        </h6>
                        <small class="text-muted">
                            <i class="fas fa-clock"></i> ${createdDate} |
                            <i class="fas fa-tag"></i> ${getTaskTypeName(task.task_type)}
                        </small>
                    </div>
                    <div>
                        ${statusBadge}
                    </div>
                </div>
                <div class="mt-2">
                    <button class="btn btn-sm btn-primary view-task-btn" data-task-id="${task.task_id}">
                        <i class="fas fa-eye"></i> 查看
                    </button>
                    <button class="btn btn-sm btn-info generate-report-btn" data-task-id="${task.task_id}">
                        <i class="fas fa-file-alt"></i> 报告
                    </button>
                </div>
            </div>
        </div>`
    );
}

function getTaskTypeName(type) {
    const names = {
        'image': '单张图片',
        'batch': '批量图片',
        'video': '视频文件',
        'webcam': '实时摄像头'
    };
    return names[type] || type;
}

$(document).on('click', '.view-task-btn', function() {
    const taskId = $(this).data('task-id');
    viewTaskDetails(taskId);
});

$(document).on('click', '.generate-report-btn', function() {
    const taskId = $(this).data('task-id');
    generateReport(taskId);
});

$('#clearHistoryBtn').click(function() {
    if (confirm('确定要清空所有历史记录吗？此操作不可恢复。')) {
        showAlert('历史记录清空功能待完善（需要新增后端API）', 'warning');
    }
});

function viewTaskDetails(taskId) {
    $.get(`/api/task/${taskId}/summary`, function(summary) {
        if (!summary || !summary.task_id) {
            showAlert('无法获取任务详情', 'danger');
            return;
        }
        $('#historyModal').modal('hide');
        showTaskDetailsModal(summary);
    }).fail(function(xhr) {
        showAlert('获取任务详情失败: ' + (xhr.responseJSON?.error || '未知错误'), 'danger');
    });
}

function showTaskDetailsModal(summary) {
    let studentStats = summary.student_behavior_stats || {};
    let teacherStats = summary.teacher_behavior_stats || {};

    if (typeof studentStats === 'string') {
        try { studentStats = JSON.parse(studentStats); } catch (e) { studentStats = {}; }
    }

    if (typeof teacherStats === 'string') {
        try { teacherStats = JSON.parse(teacherStats); } catch (e) { teacherStats = {}; }
    }

    const studentTotal = Object.values(studentStats).reduce((a, b) => a + b, 0);
    const teacherTotal = Object.values(teacherStats).reduce((a, b) => a + b, 0);

    let detailsHTML = `
        <div class="task-details">
            <div class="card mb-3">
                <div class="card-header bg-primary text-white">
                    <h6 class="mb-0"><i class="fas fa-info-circle"></i> 基本信息</h6>
                </div>
                <div class="card-body">
                    <div class="row">
                        <div class="col-md-6">
                            <p><strong>任务ID:</strong> ${summary.task_id}</p>
                            <p><strong>任务类型:</strong> ${getTaskTypeName(summary.task_type)}</p>
                            <p><strong>文件名:</strong> ${summary.file_name || '未命名'}</p>
                        </div>
                        <div class="col-md-6">
                            <p><strong>创建时间:</strong> ${new Date(summary.created_at).toLocaleString('zh-CN')}</p>
                            <p><strong>状态:</strong> ${getStatusBadge(summary.status)}</p>
                            <p><strong>处理帧数:</strong> ${summary.processed_frames || 0} / ${summary.total_frames || 0}</p>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="card mb-3">
                <div class="card-header bg-success text-white">
                    <h6 class="mb-0"><i class="fas fa-chart-bar"></i> 检测统计</h6>
                </div>
                <div class="card-body">
                    <div class="row">
                        <div class="col-md-4">
                            <div class="text-center">
                                <h3 class="text-primary">${summary.total_detections || 0}</h3>
                                <p class="text-muted">总检测数</p>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="text-center">
                                <h3 class="text-info">${studentTotal}</h3>
                                <p class="text-muted">学生行为</p>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="text-center">
                                <h3 class="text-success">${teacherTotal}</h3>
                                <p class="text-muted">人头统计</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="row">
                <div class="col-md-6">
                    <div class="card mb-3">
                        <div class="card-header bg-info text-white">
                            <h6 class="mb-0"><i class="fas fa-user-graduate"></i> 学生行为分布</h6>
                        </div>
                        <div class="card-body">
                            ${generateBehaviorBars(studentStats, studentTotal)}
                        </div>
                    </div>
                </div>
                
                <div class="col-md-6">
                    <div class="card mb-3">
                        <div class="card-header bg-warning text-dark">
                            <h6 class="mb-0"><i class="fas fa-chalkboard-teacher"></i> 人头行为分布</h6>
                        </div>
                        <div class="card-body">
                            ${generateBehaviorBars(teacherStats, teacherTotal)}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    let modal = $('#taskDetailsModal');
    if (modal.length === 0) {
        modal = $(
            `<div class="modal fade" id="taskDetailsModal" tabindex="-1">
                <div class="modal-dialog modal-xl">
                    <div class="modal-content">
                        <div class="modal-header bg-primary text-white">
                            <h5 class="modal-title"><i class="fas fa-file-alt"></i> 任务详情</h5>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body" id="taskDetailsBody"></div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-primary" onclick="generateReport('${summary.task_id}')">
                                <i class="fas fa-file-alt"></i> 生成报告
                            </button>
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                        </div>
                    </div>
                </div>
            </div>`
        );
        $('body').append(modal);
    }

    $('#taskDetailsBody').html(detailsHTML);
    const bsModal = new bootstrap.Modal(document.getElementById('taskDetailsModal'));
    bsModal.show();
}

function generateBehaviorBars(stats, total) {
    if (!stats || Object.keys(stats).length === 0) {
        return '<p class="text-muted">暂无数据</p>';
    }

    let html = '';
    const sortedStats = Object.entries(stats).sort((a, b) => b[1] - a[1]);

    sortedStats.forEach(([behavior, count]) => {
        const percentage = total > 0 ? (count / total * 100).toFixed(1) : 0;
        html += `
            <div class="mb-2">
                <div class="d-flex justify-content-between mb-1">
                    <strong>${behavior}</strong>
                    <span>${count} (${percentage}%)</span>
                </div>
                <div class="progress">
                    <div class="progress-bar" style="width: ${percentage}%"></div>
                </div>
            </div>
        `;
    });

    return html;
}

function getStatusBadge(status) {
    const badges = {
        'completed': '<span class="badge bg-success">已完成</span>',
        'processing': '<span class="badge bg-warning">处理中</span>',
        'failed': '<span class="badge bg-danger">失败</span>'
    };
    return badges[status] || '<span class="badge bg-secondary">未知</span>';
}

// ==================== 设置功能（保留） ====================
function showSettingsModal() {
    $.get('/api/user/settings', function(response) {
        if (response.success) {
            const settings = response.settings;
            $('#settingAutoScan').prop('checked', settings.auto_scan_models);
            $('#settingShowConfidence').prop('checked', settings.show_confidence);
            $('#settingShowLabels').prop('checked', settings.show_bbox_labels);
            $('#settingDefaultMode').val(settings.default_mode);
        }
    });

    $.get('/api/user/config/detection-params', function(response) {
        if (response.success) {
            const params = response.params;
            $('#settingConfidence').val(params.confidence);
            $('#settingIOU').val(params.iou);
            $('#settingFrameSkip').val(params.frame_skip);
        }
    });

    const modal = new bootstrap.Modal(document.getElementById('settingsModal'));
    modal.show();
}

$('#saveSettingsBtn').click(function() {
    const settings = {
        auto_scan_models: $('#settingAutoScan').is(':checked'),
        show_confidence: $('#settingShowConfidence').is(':checked'),
        show_bbox_labels: $('#settingShowLabels').is(':checked'),
        default_mode: $('#settingDefaultMode').val()
    };

    const params = {
        confidence: parseFloat($('#settingConfidence').val()),
        iou: parseFloat($('#settingIOU').val()),
        frame_skip: parseInt($('#settingFrameSkip').val())
    };

    $.ajax({
        url: '/api/user/settings',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(settings)
    });

    $.ajax({
        url: '/api/user/config/detection-params',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(params)
    });

    showAlert('设置已保存', 'success');
    $('#settingsModal').modal('hide');
    setTimeout(() => location.reload(), 1000);
});

$('#resetSettingsBtn').click(function() {
    if (confirm('确定要重置所有设置为默认值吗？')) {
        $.post('/api/user/config/reset', function() {
            showAlert('设置已重置，页面将刷新', 'success');
            setTimeout(() => location.reload(), 1500);
        });
    }
});

// ==================== 图片查看器功能 ====================
let viewerCanvas = null;
let viewerCtx = null;
let viewerImage = null;
let selectedDetections = new Set();

// 类别筛选
let selectedCategories = new Set();

function openImageViewer(imageUrl, detectionData) {
    currentDetectionData = detectionData;

    viewerCanvas = document.getElementById('detectionCanvas');
    viewerCtx = viewerCanvas.getContext('2d');

    viewerImage = new Image();
    viewerImage.crossOrigin = 'anonymous';
    viewerImage.onload = function() {
        const container = document.getElementById('canvasContainer');
        const containerWidth = container ? container.clientWidth : 900;
        const containerHeight = Math.min(window.innerHeight * 0.78, 820);

        const imgW = viewerImage.width;
        const imgH = viewerImage.height;

        // 画布内部分辨率使用原图尺寸，避免被缩放后看起来“很小/很糊”
        // 显示尺寸交给CSS控制（width:100%, height:100%, max-height限制）
        viewerCanvas.width = imgW;
        viewerCanvas.height = imgH;
        viewerCanvas.style.width = '100%';
        viewerCanvas.style.height = containerHeight + 'px';

        // 初始化：全选框 + 全选类别
        selectedDetections.clear();
        const allDetections = [
            ...(detectionData.student_detections || []).map((d) => ({...d, role: '学生'})),
            ...(detectionData.teacher_detections || []).map((d) => ({...d, role: '人头'})),
        ];

        allDetections.forEach((_, idx) => selectedDetections.add(idx));

        selectedCategories.clear();
        allDetections.forEach((d) => selectedCategories.add(`${d.role}:${d.behavior}`));

        // 渲染列表
        generateDetectionList(detectionData);
        generateCategoryFilter(detectionData);
        generateDetectionInfo(detectionData);

        drawImageWithDetections();

        const modal = new bootstrap.Modal(document.getElementById('imageViewerModal'));
        modal.show();
    };

    viewerImage.onerror = function() {
        showAlert('图片加载失败', 'danger');
    };

    viewerImage.src = imageUrl;
}

function drawImageWithDetections() {
    if (!viewerImage || !viewerCanvas || !viewerCtx) return;

    viewerCtx.clearRect(0, 0, viewerCanvas.width, viewerCanvas.height);
    // 画布内部以原图尺寸绘制，显示缩放由CSS负责
    viewerCtx.drawImage(viewerImage, 0, 0, viewerCanvas.width, viewerCanvas.height);

    const scaleX = viewerCanvas.width / viewerImage.width;
    const scaleY = viewerCanvas.height / viewerImage.height;

    // 合并检测框（带role）
    const merged = [
        ...(currentDetectionData.student_detections || []).map((d) => ({...d, role: '学生'})),
        ...(currentDetectionData.teacher_detections || []).map((d) => ({...d, role: '人头'})),
    ];

    merged.forEach((det, idx) => {
        const key = `${det.role}:${det.behavior}`;
        if (selectedDetections.has(idx) && selectedCategories.has(key)) {
            const color = det.role === '学生' ? '#007bff' : '#28a745';
            drawDetectionBox(det, scaleX, scaleY, color);
        }
    });
}

function drawDetectionBox(detection, scaleX, scaleY, color) {
    if (!detection.bbox || detection.bbox.length !== 4) return;

    const [x1, y1, x2, y2] = detection.bbox;
    const x = x1 * scaleX;
    const y = y1 * scaleY;
    const width = (x2 - x1) * scaleX;
    const height = (y2 - y1) * scaleY;

    viewerCtx.strokeStyle = color;
    viewerCtx.lineWidth = 3;
    viewerCtx.strokeRect(x, y, width, height);

    const label = `${detection.role} ${detection.behavior} ${(detection.confidence * 100).toFixed(1)}%`;
    viewerCtx.font = '14px Arial';
    const textWidth = viewerCtx.measureText(label).width;

    viewerCtx.fillStyle = color;
    viewerCtx.fillRect(x, Math.max(0, y - 24), textWidth + 10, 24);

    viewerCtx.fillStyle = 'white';
    viewerCtx.fillText(label, x + 5, Math.max(14, y - 7));
}

// 生成“按类别筛选”
function generateCategoryFilter(data) {
    const filterList = $('#detectionFilterList');

    // 插入类别筛选区（放在列表顶上）
    const merged = [
        ...(data.student_detections || []).map((d) => ({...d, role: '学生'})),
        ...(data.teacher_detections || []).map((d) => ({...d, role: '人头'})),
    ];

    const categoryCount = {};
    merged.forEach((d) => {
        const key = `${d.role}:${d.behavior}`;
        categoryCount[key] = (categoryCount[key] || 0) + 1;
    });

    const keys = Object.keys(categoryCount);
    if (keys.length === 0) {
        return;
    }

    const html = `
        <div class="mb-3 p-2 border rounded" style="background:#fff;">
            <div class="fw-bold mb-2"><i class="fas fa-tags"></i> 按类别筛选</div>
            ${keys.map((k) => {
                const [role, behavior] = k.split(':');
                const checked = selectedCategories.has(k) ? 'checked' : '';
                const badge = role === '学生' ? 'bg-primary' : 'bg-success';
                return `
                    <div class="form-check">
                        <input class="form-check-input category-checkbox" type="checkbox" data-key="${k}" id="cat_${role}_${behavior}" ${checked}>
                        <label class="form-check-label" for="cat_${role}_${behavior}">
                            <span class="badge ${badge} me-1">${role}</span>
                            ${behavior} <span class="text-muted">(${categoryCount[k]})</span>
                        </label>
                    </div>
                `;
            }).join('')}
        </div>
    `;

    filterList.prepend(html);
}

// 生成检测框列表（逐框）
function generateDetectionList(data) {
    const filterList = $('#detectionFilterList');
    filterList.empty();

    const merged = [
        ...(data.student_detections || []).map((d) => ({...d, role: '学生'})),
        ...(data.teacher_detections || []).map((d) => ({...d, role: '人头'})),
    ];

    if (merged.length === 0) {
        filterList.append('<p class="text-muted">没有检测到任何对象</p>');
        return;
    }

    merged.forEach((d, idx) => {
        const colorClass = d.role === '学生' ? 'text-primary' : 'text-success';
        const checked = selectedDetections.has(idx) ? 'checked' : '';
        filterList.append(`
            <div class="detection-item p-2 mb-2 border rounded" style="cursor:pointer; background:#f8f9fa;">
                <div class="form-check">
                    <input class="form-check-input detection-checkbox" type="checkbox" data-index="${idx}" id="det_${idx}" ${checked}>
                    <label class="form-check-label w-100" for="det_${idx}" style="cursor:pointer;">
                        <span class="badge bg-secondary me-1">${d.role}</span>
                        <strong class="${colorClass}">${d.behavior}</strong>
                        <br>
                        <small class="text-muted">置信度: ${(d.confidence * 100).toFixed(1)}%</small>
                    </label>
                </div>
            </div>
        `);
    });
}

function generateDetectionInfo(data) {
    const statsBox = $('#detectionStats');
    const studentTotal = data.student_detections ? data.student_detections.length : 0;
    const teacherTotal = data.teacher_detections ? data.teacher_detections.length : 0;

    statsBox.html(`
        <small>
            <div class="d-flex justify-content-between mb-1">
                <span><i class="fas fa-user-graduate text-primary"></i> 学生:</span>
                <strong>${studentTotal}</strong>
            </div>
            <div class="d-flex justify-content-between mb-1">
                <span><i class="fas fa-chalkboard-teacher text-success"></i> 人头:</span>
                <strong>${teacherTotal}</strong>
            </div>
            <hr class="my-2">
            <div class="d-flex justify-content-between">
                <span>总计:</span>
                <strong class="text-primary">${studentTotal + teacherTotal}</strong>
            </div>
        </small>
    `);

    const detailsBox = $('#detectionDetails');
    const all = [
        ...(data.student_detections || []).map((d) => ({...d, role: '学生'})),
        ...(data.teacher_detections || []).map((d) => ({...d, role: '人头'})),
    ];

    if (all.length === 0) {
        detailsBox.html('<div class="text-muted">暂无检测信息</div>');
        return;
    }

    all.sort((a, b) => (b.confidence || 0) - (a.confidence || 0));

    const rows = all.map((d) => {
        const conf = d.confidence != null ? (d.confidence * 100).toFixed(1) + '%' : '—';
        const bbox = Array.isArray(d.bbox) ? d.bbox.map((v) => v.toFixed(1)).join(', ') : '—';
        return `
            <div class="d-flex justify-content-between border-bottom py-1">
                <div>
                    <span class="badge bg-secondary me-1">${d.role}</span>
                    <strong>${d.behavior || 'unknown'}</strong>
                    <span class="text-muted">(${conf})</span>
                </div>
                <div class="text-muted" style="max-width:55%; text-align:right; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                    bbox: ${bbox}
                </div>
            </div>
        `;
    }).join('');

    detailsBox.html(`<div class="small">${rows}</div>`);
}

// checkbox事件
$(document).on('change', '.detection-checkbox', function() {
    const idx = $(this).data('index');
    if ($(this).is(':checked')) selectedDetections.add(idx);
    else selectedDetections.delete(idx);
    drawImageWithDetections();
});

$(document).on('change', '.category-checkbox', function() {
    const key = $(this).data('key');
    if ($(this).is(':checked')) selectedCategories.add(key);
    else selectedCategories.delete(key);
    drawImageWithDetections();
});

$('#showAllBoxes').click(function() {
    // 全选检测框
    selectedDetections.clear();
    const total = (currentDetectionData.student_detections || []).length + (currentDetectionData.teacher_detections || []).length;
    for (let i = 0; i < total; i++) selectedDetections.add(i);
    $('.detection-checkbox').prop('checked', true);

    // 全选类别
    selectedCategories.clear();
    const merged = [
        ...(currentDetectionData.student_detections || []).map((d) => ({...d, role: '学生'})),
        ...(currentDetectionData.teacher_detections || []).map((d) => ({...d, role: '人头'})),
    ];
    merged.forEach((d) => selectedCategories.add(`${d.role}:${d.behavior}`));
    $('.category-checkbox').prop('checked', true);

    drawImageWithDetections();
});

$('#hideAllBoxes').click(function() {
    selectedDetections.clear();
    $('.detection-checkbox').prop('checked', false);
    drawImageWithDetections();
});

$('#clearAllBoxes').click(function() {
    selectedDetections.clear();
    selectedCategories.clear();
    $('.detection-checkbox').prop('checked', false);
    $('.category-checkbox').prop('checked', false);

    if (viewerImage && viewerCanvas && viewerCtx) {
        viewerCtx.clearRect(0, 0, viewerCanvas.width, viewerCanvas.height);
        viewerCtx.drawImage(viewerImage, 0, 0, viewerCanvas.width, viewerCanvas.height);
    }
});

$('#downloadDetailedImage').click(function() {
    if (viewerCanvas) {
        const link = document.createElement('a');
        link.download = 'detection_result_' + Date.now() + '.png';
        link.href = viewerCanvas.toDataURL();
        link.click();
    }
});

// 其他工具函数
function getFileIcon(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    const iconMap = {
        'jpg': 'image', 'jpeg': 'image', 'png': 'image', 'bmp': 'image',
        'mp4': 'video', 'avi': 'video', 'mov': 'video', 'mkv': 'video'
    };
    return iconMap[ext] || 'file';
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

function showAlert(message, type = 'info') {
    // 返回一个可关闭句柄，便于某些场景手动关闭
    let closed = false;
    const alert = $(
        `<div class="alert alert-${type} alert-dismissible fade show position-fixed top-0 start-50 translate-middle-x mt-3" 
             role="alert" style="z-index: 9999; min-width: 300px;">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>`
    );

    $('body').append(alert);

    const timer = setTimeout(() => {
        if (closed) return;
        alert.fadeOut(() => alert.remove());
    }, 3000);

    return {
        close: function() {
            if (closed) return;
            closed = true;
            clearTimeout(timer);
            try { alert.remove(); } catch (e) {}
        }
    };
}

// 秒数格式化（用于ETA/时长显示）
function formatSeconds(seconds) {
    if (seconds == null || isNaN(seconds)) return '--';
    seconds = Math.max(0, Math.floor(Number(seconds)));
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) return `${h}h ${m}m ${s}s`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
}

// 枚举摄像头设备（用于双摄像头）
async function loadCameraDevices() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
        showAlert('当前浏览器不支持摄像头枚举', 'warning');
        return;
    }

    try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const cams = devices.filter(d => d.kind === 'videoinput');

        const studentSelect = $('#studentCameraSelect');
        const teacherSelect = $('#teacherCameraSelect');
        studentSelect.empty();
        teacherSelect.empty();

        if (cams.length === 0) {
            studentSelect.append('<option value="">未发现摄像头</option>');
            teacherSelect.append('<option value="">未发现摄像头</option>');
            return;
        }

        cams.forEach((cam, idx) => {
            const name = cam.label || `摄像头 ${idx}`;
            studentSelect.append(`<option value="${idx}">${name}</option>`);
            teacherSelect.append(`<option value="${idx}">${name}</option>`);
        });

        // 默认选择0/1（若有）
        studentSelect.val('0');
        if (cams.length > 1) teacherSelect.val('1');

    } catch (e) {
        console.error(e);
        showAlert('获取摄像头列表失败，请允许浏览器摄像头权限', 'warning');
    }

}
// ======================
// 随机点名(单张检测) - 从人头框中随机选择（：整张图+红框+人头截图）
// ======================
function randomCallRoll(detectionData) {
    console.log("✅ 执行随机点名", detectionData);

    // 取出人头框
    let headBoxes = detectionData.teacher_detections || [];

    if (headBoxes.length === 0) {
        alert("未检测到人头，无法点名！");
        return;
    }

    // 随机选一个人头
    let randomBox = headBoxes[Math.floor(Math.random() * headBoxes.length)];
    let [x, y, x2, y2] = randomBox.bbox;

    // ==============================================
    // 第一步：在【原图】上画红色框，生成带标记的整张图片
    // ==============================================
    let img = new Image();
    img.crossOrigin = "anonymous";
    img.src = detectionData.original_image; // ✅ 使用原图！

    img.onload = function () {
        // 画布1：整张图 + 红色框
        let canvasFull = document.createElement("canvas");
        let ctxFull = canvasFull.getContext("2d");
        canvasFull.width = img.width;
        canvasFull.height = img.height;

        // 画整张原图
        ctxFull.drawImage(img, 0, 0);

        // 画红色框（醒目）
        ctxFull.strokeStyle = "#ff0000";
        ctxFull.lineWidth = 4; // 粗细
        ctxFull.strokeRect(x, y, x2 - x, y2 - y);

        // 转图片
        let fullImageUrl = canvasFull.toDataURL("image/png");

        // ==============================================
        // 第二步：截取人头小图（同样从原图截取）
        // ==============================================
        let canvasCrop = document.createElement("canvas");
        let ctxCrop = canvasCrop.getContext("2d");
        let w = x2 - x;
        let h = y2 - y;
        let scale = 3; // 放大倍数
        canvasCrop.width = w * scale;
        canvasCrop.height = h * scale;

        ctxCrop.drawImage(img, x, y, w, h, 0, 0, w * scale, h * scale);
        let cropImageUrl = canvasCrop.toDataURL("image/png");

        // ==============================================
        // 第三步：弹窗展示（整张图 + 截图）
        // ==============================================
        showRandomModal(fullImageUrl, cropImageUrl);
    };
}

// 弹窗：显示整张图（红框）+ 人头截图
function showRandomModal(fullImgUrl, cropImgUrl) {
    let modal = $(`
    <div class="modal fade show" style="display:block; background:rgba(0,0,0,0.85); z-index:9999;">
        <div class="modal-dialog modal-lg modal-dialog-centered">
            <div class="modal-content">
                <div class="modal-header bg-warning">
                    <h5>🎯 随机点名成功</h5>
                    <button type="button" class="btn-close" onclick="$(this).closest('.modal').remove();"></button>
                </div>
                <div class="modal-body text-center">
                    <!-- 整张图片（带红框标记） -->
                    <h6 class="text-primary">📍 选中位置</h6>
                    <img src="${fullImgUrl}" class="img-fluid rounded border mb-3" style="max-height:400px;">
                    
                    <!-- 人头截图 -->
                    <h6 class="text-success">✅ 选中学生</h6>
                    <img src="${cropImgUrl}" class="img-fluid rounded border" style="max-height:180px;">
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" onclick="$(this).closest('.modal').remove();">关闭</button>
                </div>
            </div>
        </div>
    </div>
    `);
    $("body").append(modal);
}
// ======================
// 视频随机点名（使用【原始画面】标红框）
// ======================
function randomCallRollVideoOriginalFrame(originalImageBase64, teacherDetections) {
    console.log("✅ 视频原始帧随机点名", teacherDetections);

    let headBoxes = teacherDetections;
    if (headBoxes.length === 0) {
        alert("未检测到人头！");
        return;
    }

    // 随机选一个人头
    let randomBox = headBoxes[Math.floor(Math.random() * headBoxes.length)];
    let [x, y, x2, y2] = randomBox.bbox;

    // 在【原始画面】上画红框
    let img = new Image();
    img.onload = function () {
        let canvasFull = document.createElement("canvas");
        let ctxFull = canvasFull.getContext("2d");
        canvasFull.width = img.width;
        canvasFull.height = img.height;

        // 画 原始干净画面
        ctxFull.drawImage(img, 0, 0);

        // 画红框（只画这一个！）
        ctxFull.strokeStyle = "#ff0000";
        ctxFull.lineWidth = 5;
        ctxFull.strokeRect(x, y, x2 - x, y2 - y);

        let fullImageUrl = canvasFull.toDataURL("image/png");

        // 截取人头小图
        let canvasCrop = document.createElement("canvas");
        let ctxCrop = canvasCrop.getContext("2d");
        let w = x2 - x;
        let h = y2 - y;
        canvasCrop.width = w;
        canvasCrop.height = h;
        ctxCrop.drawImage(img, x, y, w, h, 0, 0, w, h);
        let cropImageUrl = canvasCrop.toDataURL("image/png");

        // 弹出窗口
        showRandomModal(fullImageUrl, cropImageUrl);
    };
    img.src = originalImageBase64;
}
// ======================
// 实时摄像头 → 随机点名（人头模型随机抽取）
// ======================
// ======================
// 实时摄像头 → 随机点名（使用【原始干净帧】，不在标注图上画框）
// ======================
// ======================
// 实时摄像头 → 随机点名（修复版）
// ======================
function webcamRandomCall() {
    // ✅ 修复：用你自己项目里的真实变量判断摄像头状态
    if (!webcamInterval) {
        alert("请先开启摄像头");
        return;
    }

    // 1. 获取原始帧
    fetch("/api/webcam/original_frame")
    .then(res => res.json())
    .then(res => {
        if (!res.success) {
            alert("获取原始帧失败：" + res.error);
            return;
        }

        // 2. 把原图传给后端检测人头
        fetch("/api/detect/frame", {
            method: "POST",
            headers: {"Content-Type":"application/json"},
            body: JSON.stringify({image: res.image})
        })
        .then(r=>r.json())
        .then(det=>{
            if (!det.success || !det.teacher_detections || det.teacher_detections.length === 0) {
                alert("未检测到可点名人头");
                return;
            }

            // 随机选一个人头
            let item = det.teacher_detections[Math.floor(Math.random() * det.teacher_detections.length)];
            let [x1,y1,x2,y2] = item.bbox;

            // 画图+弹窗裁剪图
            let img = new Image();
            img.onload = function(){
                let canvas = document.createElement("canvas");
                canvas.width = img.width;
                canvas.height = img.height;
                let ctx = canvas.getContext("2d");
                ctx.drawImage(img,0,0);
                ctx.strokeStyle = "red";
                ctx.lineWidth = 3;
                ctx.strokeRect(x1,y1,x2-x1,y2-y1);

                // 裁剪人头
                let crop = document.createElement("canvas");
                crop.width = x2-x1;
                crop.height = y2-y1;
                let cctx = crop.getContext("2d");
                cctx.drawImage(img, x1,y1,x2-x1,y2-y1, 0,0,crop.width,crop.height);

                // 弹窗显示结果
                showRandomModal(canvas.toDataURL(), crop.toDataURL());
            };
            img.src = res.image;
        })
    })
    .catch(err=>{
        alert("请求异常，随机点名失败");
        console.error(err);
    })
}
