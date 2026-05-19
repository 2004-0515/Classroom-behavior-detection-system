param(
    [int]$Port = 5001,
    [int]$ScreenshotTimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$python = $null
if ($env:CLASSROOM_PYTHON -and (Test-Path $env:CLASSROOM_PYTHON)) {
    $python = $env:CLASSROOM_PYTHON
} else {
    $venvPython = Join-Path $root ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        $python = $venvPython
    } else {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if ($pythonCommand) {
            $python = $pythonCommand.Source
        }
    }
}
if (-not $python) {
    throw "Python runtime was not found; browser visual audit cannot run."
}
$env:CLASSROOM_PYTHON = $python
$serverScript = Join-Path $root "scripts\audit_server.py"
$verifyArchiveScript = Join-Path $root "scripts\verify_report_archive.py"
$artifactDir = Join-Path $root "docs\_artifacts"
New-Item -ItemType Directory -Force $artifactDir | Out-Null

$sampleImages = @(
    (Join-Path $root "testfile\0014012.jpg"),
    (Join-Path $root "testfile\0009008.jpg")
)
foreach ($sampleImage in $sampleImages) {
    if (-not (Test-Path $sampleImage)) {
        throw "Required browser audit sample is missing: $sampleImage"
    }
}
$sampleVideo = Join-Path $root "testfile\QQ202618-01246-HD.mp4"
if (-not (Test-Path $sampleVideo)) {
    throw "Required browser audit sample is missing: $sampleVideo"
}

$chromeCandidates = @(
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Google\Chrome\Application\chrome.exe"
)
$browser = $chromeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $browser) {
    throw "Chrome or Edge was not found; browser visual audit cannot run."
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"

$batchZipPath = Join-Path $artifactDir "browser-audit-batch-$timestamp.zip"
$batchExpectationsPath = Join-Path $artifactDir "browser-audit-batch-$timestamp.expectations.json"
$batchValidationPath = Join-Path $artifactDir "browser-audit-batch-$timestamp.validation.json"
$outLog = Join-Path $artifactDir "browser_audit_server.out.log"
$errLog = Join-Path $artifactDir "browser_audit_server.err.log"
$server = $null
Add-Type -AssemblyName System.Net.Http
$httpHandler = New-Object System.Net.Http.HttpClientHandler
$httpHandler.CookieContainer = New-Object System.Net.CookieContainer
$httpHandler.UseCookies = $true
$httpClient = New-Object System.Net.Http.HttpClient($httpHandler)
$httpClient.Timeout = [TimeSpan]::FromSeconds(90)

function Wait-AuditServer {
    param([string]$Url)
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                return
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    throw "Audit server did not start in time: $Url"
}

function Capture-Page {
    param(
        [string]$Url,
        [string]$Output,
        [string]$Size = "1440,1000"
    )
    $lastFailure = $null
    for ($attempt = 1; $attempt -le 2; $attempt++) {
        $captureProfileDir = Join-Path $artifactDir ("chrome-profile-" + [guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Force $captureProfileDir | Out-Null
        if (Test-Path $Output) {
            Remove-Item -LiteralPath $Output -Force
        }
        try {
            $args = @(
                "--headless",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-gpu-compositing",
                "--disable-software-rasterizer",
                "--disable-features=VizDisplayCompositor",
                "--disable-extensions",
                "--no-first-run",
                "--no-default-browser-check",
                "--user-data-dir=$captureProfileDir",
                "--window-size=$Size",
                "--timeout=60000",
                "--run-all-compositor-stages-before-draw",
                "--screenshot=$Output",
                $Url
            )
            $argString = ($args | ForEach-Object {
                if ($_ -match "\s") { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
            }) -join " "
            $process = Start-Process -FilePath $browser -ArgumentList $argString -PassThru -WindowStyle Hidden
            $finished = Wait-Process -Id $process.Id -Timeout $ScreenshotTimeoutSeconds -ErrorAction SilentlyContinue
            if (-not $process.HasExited) {
                Stop-Process -Id $process.Id -Force
                throw "Browser screenshot timed out: $Url"
            }
            if ($process.ExitCode -ne 0) {
                throw "Browser screenshot failed: $Url"
            }
            $item = Get-Item $Output
            if ($item.Length -lt 1000) {
                throw "Screenshot file is too small and may not have rendered: $Output"
            }
            return
        } catch {
            $lastFailure = $_
            if ($attempt -lt 2) {
                Start-Sleep -Seconds 2
            }
        } finally {
            Remove-Item -LiteralPath $captureProfileDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    throw $lastFailure
}

function Invoke-HttpJson {
    param(
        [string]$Method,
        [string]$Url,
        [System.Net.Http.HttpContent]$Content,
        [string]$Label
    )
    $httpMethod = New-Object System.Net.Http.HttpMethod($Method.ToUpperInvariant())
    $request = New-Object System.Net.Http.HttpRequestMessage($httpMethod, $Url)
    if ($Content) {
        $request.Content = $Content
    }
    try {
        $response = $httpClient.SendAsync($request).Result
        $body = $response.Content.ReadAsStringAsync().Result
        return $body | ConvertFrom-Json
    } catch {
        throw "$Label returned invalid JSON: $($_.Exception.Message)"
    } finally {
        $request.Dispose()
        if ($Content) {
            $Content.Dispose()
        }
    }
}

function Assert-ApiSuccess {
    param(
        [object]$Payload,
        [string]$Label
    )
    if (-not $Payload.success) {
        $errorCode = $Payload.error.code
        $errorMessage = $Payload.error.message
        throw "$Label failed: [$errorCode] $errorMessage"
    }
}

function Login-AuditSession {
    param([string]$BaseUrl)
    $content = New-Object System.Net.Http.StringContent('{"username":"audit_admin","password":"audit_password_123"}', [System.Text.Encoding]::UTF8, "application/json")
    $payload = Invoke-HttpJson -Method "Post" -Url "$BaseUrl/api/auth/login" -Content $content -Label "audit login"
    Assert-ApiSuccess $payload "audit login"
}

function Detect-ImageTask {
    param(
        [string]$BaseUrl,
        [string]$ImagePath
    )
    $content = New-Object System.Net.Http.MultipartFormDataContent
    $fileStream = [System.IO.File]::OpenRead($ImagePath)
    try {
        $fileContent = New-Object System.Net.Http.StreamContent($fileStream)
        $fileContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse("image/jpeg")
        $content.Add($fileContent, "file", [System.IO.Path]::GetFileName($ImagePath))
        $content.Add((New-Object System.Net.Http.StringContent("0.25")), "confidence")
        $content.Add((New-Object System.Net.Http.StringContent("0.45")), "iou")
        $payload = Invoke-HttpJson -Method "Post" -Url "$BaseUrl/api/detect/image" -Content $content -Label "detect image"
    } finally {
        $fileStream.Dispose()
    }
    Assert-ApiSuccess $payload "detect image"
    return [string]$payload.data.task_id
}

function Wait-TaskCompletion {
    param(
        [string]$BaseUrl,
        [string]$TaskId,
        [int]$TimeoutSeconds = 180
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $payload = Invoke-HttpJson -Method "Get" -Url "$BaseUrl/api/tasks/$TaskId" -Label "task detail"
        Assert-ApiSuccess $payload "task detail"
        $task = $payload.data
        $status = [string]$task.status
        if ($status -eq "completed") {
            return $task
        }
        if ($status -and $status -ne "processing") {
            throw "Task $TaskId finished with unexpected status: $status"
        }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    throw "Task $TaskId did not finish within $TimeoutSeconds seconds"
}

function Detect-BatchTask {
    param(
        [string]$BaseUrl,
        [string[]]$ImagePaths
    )
    $content = New-Object System.Net.Http.MultipartFormDataContent
    $fileStreams = @()
    try {
        foreach ($imagePath in $ImagePaths) {
            $fileStream = [System.IO.File]::OpenRead($imagePath)
            $fileStreams += $fileStream
            $fileContent = New-Object System.Net.Http.StreamContent($fileStream)
            $fileContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse("image/jpeg")
            $content.Add($fileContent, "files", [System.IO.Path]::GetFileName($imagePath))
        }
        $content.Add((New-Object System.Net.Http.StringContent("0.25")), "confidence")
        $content.Add((New-Object System.Net.Http.StringContent("0.45")), "iou")
        $payload = Invoke-HttpJson -Method "Post" -Url "$BaseUrl/api/detect/batch" -Content $content -Label "detect batch"
    } finally {
        foreach ($fileStream in $fileStreams) {
            $fileStream.Dispose()
        }
    }
    Assert-ApiSuccess $payload "detect batch"
    $taskId = [string]$payload.data.task_id
    [void](Wait-TaskCompletion $BaseUrl $taskId 60)
    return $taskId
}

function Detect-VideoTask {
    param(
        [string]$BaseUrl,
        [string]$VideoPath
    )
    $content = New-Object System.Net.Http.MultipartFormDataContent
    $fileStream = [System.IO.File]::OpenRead($VideoPath)
    try {
        $fileContent = New-Object System.Net.Http.StreamContent($fileStream)
        $fileContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse("video/mp4")
        $content.Add($fileContent, "file", [System.IO.Path]::GetFileName($VideoPath))
        $content.Add((New-Object System.Net.Http.StringContent("0.25")), "confidence")
        $content.Add((New-Object System.Net.Http.StringContent("0.45")), "iou")
        $content.Add((New-Object System.Net.Http.StringContent("8")), "frame_skip")
        $payload = Invoke-HttpJson -Method "Post" -Url "$BaseUrl/api/detect/video" -Content $content -Label "detect video"
    } finally {
        $fileStream.Dispose()
    }
    Assert-ApiSuccess $payload "detect video"
    $taskId = [string]$payload.data.task_id
    [void](Wait-TaskCompletion $BaseUrl $taskId 180)
    return $taskId
}

function Generate-Report {
    param(
        [string]$BaseUrl,
        [string]$TaskId
    )
    $payload = Invoke-HttpJson -Method "Get" -Url "$BaseUrl/api/tasks/$TaskId/report" -Label "generate report"
    Assert-ApiSuccess $payload "generate report"
    return $payload.data
}

function Get-TaskSummary {
    param(
        [string]$BaseUrl,
        [string]$TaskId
    )
    $payload = Invoke-HttpJson -Method "Get" -Url "$BaseUrl/api/tasks/$TaskId/summary" -Label "task summary"
    Assert-ApiSuccess $payload "task summary"
    return $payload.data
}

function Build-ReportContract {
    param(
        [string]$BaseUrl,
        [string]$TaskId,
        [string]$Label
    )
    $summary = Get-TaskSummary $baseUrl $taskId
    $reportInfo = Generate-Report $baseUrl $taskId
    $reportHtmlPath = Join-Path $artifactDir "browser-audit-report-$Label-$timestamp.html"
    $reportSummaryPath = Join-Path $artifactDir "browser-audit-report-$Label-$timestamp.summary.json"
    $reportValidationPath = Join-Path $artifactDir "browser-audit-report-$Label-$timestamp.validation.json"
    $validation = Verify-ReportHtml `
        -BaseUrl $baseUrl `
        -ReportUrl ([string]$reportInfo.report_url) `
        -Summary $summary `
        -Label "$Label report" `
        -HtmlPath $reportHtmlPath `
        -SummaryPath $reportSummaryPath `
        -ValidationPath $reportValidationPath
    return [pscustomobject]@{
        task_id = $taskId
        summary = $summary
        report_url = [string]$reportInfo.report_url
        report_filename = [string]$reportInfo.report_filename
        label = $Label
        report_html_path = $reportHtmlPath
        report_summary_path = $reportSummaryPath
        report_validation_path = $reportValidationPath
        html_validation = $validation
    }
}

function Export-BatchReports {
    param(
        [string]$BaseUrl,
        [string[]]$TaskIds
    )
    $body = @{ task_ids = $TaskIds } | ConvertTo-Json -Depth 3 -Compress
    $content = New-Object System.Net.Http.StringContent($body, [System.Text.Encoding]::UTF8, "application/json")
    $payload = Invoke-HttpJson -Method "Post" -Url "$BaseUrl/api/tasks/reports/batch" -Content $content -Label "batch report export"
    Assert-ApiSuccess $payload "batch report export"
    return $payload.data
}

function Download-File {
    param(
        [string]$Url,
        [string]$OutputPath
    )
    $response = $httpClient.GetAsync($Url).Result
    if (-not $response.IsSuccessStatusCode) {
        throw "download failed: $Url"
    }
    try {
        $bytes = $response.Content.ReadAsByteArrayAsync().Result
        [System.IO.File]::WriteAllBytes($OutputPath, $bytes)
        $item = Get-Item $OutputPath
        if ($item.Length -lt 1000) {
            throw "downloaded file is unexpectedly small: $OutputPath"
        }
    } finally {
        $response.Dispose()
    }
}

function Write-Utf8TextFile {
    param(
        [string]$Path,
        [string]$Text
    )
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Text, $utf8NoBom)
}

function Write-Utf8JsonFile {
    param(
        [string]$Path,
        [object]$Payload,
        [int]$Depth = 10
    )
    $json = $Payload | ConvertTo-Json -Depth $Depth
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $json, $utf8NoBom)
}

function Verify-ReportHtml {
    param(
        [string]$BaseUrl,
        [string]$ReportUrl,
        [object]$Summary,
        [string]$Label,
        [string]$HtmlPath,
        [string]$SummaryPath,
        [string]$ValidationPath
    )
    $encodedReport = [uri]::EscapeDataString($ReportUrl)
    $response = Invoke-WebRequest -UseBasicParsing "$BaseUrl/audit/login-and-go?next=$encodedReport" -TimeoutSec 15
    if ($response.StatusCode -ne 200) {
        throw "report HTML unavailable: $($response.StatusCode)"
    }
    Write-Utf8TextFile -Path $HtmlPath -Text ([string]$response.Content)
    Write-Utf8JsonFile -Path $SummaryPath -Payload $Summary
    $output = & $python $verifyArchiveScript `
        --html-path $HtmlPath `
        --summary-path $SummaryPath `
        --label $Label `
        --required-marker report-toolbar `
        --required-marker preview-box `
        --required-marker analysis-grid 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($output -join [Environment]::NewLine)
    }
    $outputText = ($output -join [Environment]::NewLine)
    $payload = $outputText | ConvertFrom-Json
    Write-Utf8JsonFile -Path $ValidationPath -Payload $payload
    return $payload
}

function Verify-BatchArchive {
    param(
        [string]$ZipPath,
        [object[]]$ExpectedReports = @(),
        [string]$Label = "browser visual audit batch archive",
        [string]$ExpectationsPath,
        [string]$ValidationPath
    )
    $expectations = @($ExpectedReports | ForEach-Object {
        [ordered]@{
            report_filename = [string]$_.report_filename
            summary = $_.summary
        }
    })
    Write-Utf8JsonFile -Path $ExpectationsPath -Payload $expectations
    $output = & $python $verifyArchiveScript --zip-path $ZipPath --expectations-path $ExpectationsPath --label $Label 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($output -join [Environment]::NewLine)
    }
    $outputText = ($output -join [Environment]::NewLine)
    $payload = $outputText | ConvertFrom-Json
    Write-Utf8JsonFile -Path $ValidationPath -Payload $payload
    return $payload
}

try {
    $server = Start-Process `
        -FilePath $python `
        -ArgumentList "`"$serverScript`" --port $Port" `
        -WorkingDirectory $root `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -WindowStyle Hidden `
        -PassThru

    $baseUrl = "http://127.0.0.1:$Port"
    Wait-AuditServer "$baseUrl/api/auth/session"

    Login-AuditSession $baseUrl
    $taskId1 = Detect-ImageTask $BaseUrl $sampleImages[0]
    $batchTaskId = Detect-BatchTask $BaseUrl $sampleImages
    $videoTaskId = Detect-VideoTask $BaseUrl $sampleVideo
    $imageReport = Build-ReportContract $baseUrl $taskId1 "image"
    $batchReport = Build-ReportContract $baseUrl $batchTaskId "batch"
    $videoReport = Build-ReportContract $baseUrl $videoTaskId "video"

    $batchInfo = Export-BatchReports $baseUrl @($taskId1, $batchTaskId, $videoTaskId)
    Download-File "$baseUrl$([string]$batchInfo.zip_url)" $batchZipPath
    if ([int]$batchInfo.report_count -ne 3) {
        throw "Batch archive report_count mismatch: $($batchInfo.report_count)"
    }
    $expectedReports = @($imageReport, $batchReport, $videoReport)
    $batchValidation = Verify-BatchArchive `
        -ZipPath $batchZipPath `
        -ExpectedReports $expectedReports `
        -ExpectationsPath $batchExpectationsPath `
        -ValidationPath $batchValidationPath

    $loginShot = Join-Path $artifactDir "browser-audit-login.png"
    $dashboardShot = Join-Path $artifactDir "browser-audit-dashboard.png"
    $webcamShot = Join-Path $artifactDir "browser-audit-webcam.png"
    $reportShot = Join-Path $artifactDir "browser-audit-report.png"
    $videoReportShot = Join-Path $artifactDir "browser-audit-video-report.png"

    Capture-Page "$baseUrl/login" $loginShot "1366,900"
    Capture-Page "$baseUrl/audit/login-and-go?next=%2F" $dashboardShot "1440,1000"
    Capture-Page "$baseUrl/audit/login-and-go?next=%2F%3Faudit_mode%3Dwebcam" $webcamShot "1440,1000"
    $encodedReport = [uri]::EscapeDataString([string]$imageReport.report_url)
    Capture-Page "$baseUrl/audit/login-and-go?next=$encodedReport" $reportShot "1440,1000"
    $encodedVideoReport = [uri]::EscapeDataString([string]$videoReport.report_url)
    Capture-Page "$baseUrl/audit/login-and-go?next=$encodedVideoReport" $videoReportShot "1440,1000"

    $summary = [ordered]@{
        generated_at = (Get-Date).ToString("s")
        browser = $browser
        python = $python
        base_url = $baseUrl
        task_ids = @($taskId1, $batchTaskId, $videoTaskId)
        report_url = [string]$imageReport.report_url
        video_report_url = [string]$videoReport.report_url
        batch_zip_url = [string]$batchInfo.zip_url
        batch_zip_path = (Resolve-Path $batchZipPath).Path
        batch_zip_expectations_path = (Resolve-Path $batchExpectationsPath).Path
        batch_zip_validation_path = (Resolve-Path $batchValidationPath).Path
        report_markers_verified = $true
        report_metric_cards_verified = [int]$imageReport.html_validation.metric_count -gt 0
        batch_task_report_metric_cards_verified = [int]$batchReport.html_validation.metric_count -gt 0
        video_report_metric_cards_verified = [int]$videoReport.html_validation.metric_count -gt 0
        report_validation_paths = [ordered]@{
            image = (Resolve-Path $imageReport.report_validation_path).Path
            batch = (Resolve-Path $batchReport.report_validation_path).Path
            video = (Resolve-Path $videoReport.report_validation_path).Path
        }
        report_summary_paths = [ordered]@{
            image = (Resolve-Path $imageReport.report_summary_path).Path
            batch = (Resolve-Path $batchReport.report_summary_path).Path
            video = (Resolve-Path $videoReport.report_summary_path).Path
        }
        report_html_paths = [ordered]@{
            image = (Resolve-Path $imageReport.report_html_path).Path
            batch = (Resolve-Path $batchReport.report_html_path).Path
            video = (Resolve-Path $videoReport.report_html_path).Path
        }
        batch_report_entries_verified = [int]$batchValidation.report_count
        batch_report_filenames_verified = @($batchValidation.verified_reports)
        screenshots = @(
            (Resolve-Path $loginShot).Path,
            (Resolve-Path $dashboardShot).Path,
            (Resolve-Path $webcamShot).Path,
            (Resolve-Path $reportShot).Path,
            (Resolve-Path $videoReportShot).Path
        )
    }
    $summaryPath = Join-Path $artifactDir "browser-visual-audit.json"
    $summary | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 $summaryPath
    $summary | ConvertTo-Json -Depth 4
    Write-Host "Browser visual audit passed."
} finally {
    if ($server -and -not $server.HasExited) {
        Stop-Process -Id $server.Id -Force
    }
}
