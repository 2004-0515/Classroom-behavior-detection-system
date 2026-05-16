param(
    [int]$Port = 5001,
    [int]$ScreenshotTimeoutSeconds = 75
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$python = Join-Path $root ".venv\Scripts\python.exe"
$serverScript = Join-Path $root "scripts\audit_server.py"
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

$chromeCandidates = @(
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Google\Chrome\Application\chrome.exe"
)
$browser = $chromeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $browser) {
    throw "Chrome or Edge was not found; browser visual audit cannot run."
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$profileDir = Join-Path $artifactDir "chrome-profile-$timestamp"
$batchZipPath = Join-Path $artifactDir "browser-audit-batch-$timestamp.zip"
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
        "--user-data-dir=$profileDir",
        "--window-size=$Size",
        "--timeout=30000",
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

function Generate-Report {
    param(
        [string]$BaseUrl,
        [string]$TaskId
    )
    $payload = Invoke-HttpJson -Method "Get" -Url "$BaseUrl/api/tasks/$TaskId/report" -Label "generate report"
    Assert-ApiSuccess $payload "generate report"
    return $payload.data
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

function Assert-ReportHtml {
    param(
        [string]$BaseUrl,
        [string]$ReportUrl
    )
    $encodedReport = [uri]::EscapeDataString($ReportUrl)
    $response = Invoke-WebRequest -UseBasicParsing "$BaseUrl/audit/login-and-go?next=$encodedReport" -TimeoutSec 15
    $html = [string]$response.Content
    foreach ($marker in @("report-toolbar", "preview-box", "analysis-grid")) {
        if ($html -notmatch [regex]::Escape($marker)) {
            throw "Report HTML is missing expected marker: $marker"
        }
    }
}

function Assert-BatchArchive {
    param([string]$ZipPath)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        $names = @($archive.Entries | ForEach-Object { $_.FullName })
        if ($names -notcontains "readme.txt") {
            throw "Batch archive missing readme.txt"
        }
        if ($names -notcontains "manifest.csv") {
            throw "Batch archive missing manifest.csv"
        }
        $reportCount = @($names | Where-Object { $_ -like "report-*.html" }).Count
        if ($reportCount -lt 2) {
            throw "Batch archive does not contain enough report HTML files"
        }
    } finally {
        $archive.Dispose()
    }
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
    $taskId1 = Detect-ImageTask $baseUrl $sampleImages[0]
    $taskId2 = Detect-ImageTask $baseUrl $sampleImages[1]
    $reportInfo = Generate-Report $baseUrl $taskId1
    Assert-ReportHtml $baseUrl ([string]$reportInfo.report_url)

    $batchInfo = Export-BatchReports $baseUrl @($taskId1, $taskId2)
    Download-File "$baseUrl$([string]$batchInfo.zip_url)" $batchZipPath
    Assert-BatchArchive $batchZipPath

    $loginShot = Join-Path $artifactDir "browser-audit-login.png"
    $dashboardShot = Join-Path $artifactDir "browser-audit-dashboard.png"
    $webcamShot = Join-Path $artifactDir "browser-audit-webcam.png"
    $reportShot = Join-Path $artifactDir "browser-audit-report.png"

    Capture-Page "$baseUrl/login" $loginShot "1366,900"
    Capture-Page "$baseUrl/audit/login-and-go?next=%2F" $dashboardShot "1440,1000"
    Capture-Page "$baseUrl/audit/login-and-go?next=%2F%3Faudit_mode%3Dwebcam" $webcamShot "1440,1000"
    $encodedReport = [uri]::EscapeDataString([string]$reportInfo.report_url)
    Capture-Page "$baseUrl/audit/login-and-go?next=$encodedReport" $reportShot "1440,1000"

    $summary = [ordered]@{
        generated_at = (Get-Date).ToString("s")
        browser = $browser
        base_url = $baseUrl
        task_ids = @($taskId1, $taskId2)
        report_url = [string]$reportInfo.report_url
        batch_zip_url = [string]$batchInfo.zip_url
        batch_zip_path = (Resolve-Path $batchZipPath).Path
        report_markers_verified = $true
        screenshots = @(
            (Resolve-Path $loginShot).Path,
            (Resolve-Path $dashboardShot).Path,
            (Resolve-Path $webcamShot).Path,
            (Resolve-Path $reportShot).Path
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
