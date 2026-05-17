Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# PowerShell wrapper for the top-level verification chain.
$root = Split-Path -Parent $PSScriptRoot
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
    Write-Error "未找到可用 Python 运行时"
}

$env:CLASSROOM_PYTHON = $python
& $python (Join-Path $PSScriptRoot "verify_all.py")
exit $LASTEXITCODE
