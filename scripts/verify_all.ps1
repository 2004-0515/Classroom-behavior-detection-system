Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# PowerShell wrapper for the top-level verification chain.
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "未找到虚拟环境 Python: $python"
}

& $python (Join-Path $PSScriptRoot "verify_all.py")
exit $LASTEXITCODE
