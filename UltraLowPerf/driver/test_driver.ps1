<#
.SYNOPSIS
    Teste CpuTempDriver : lance CpuTempTest.exe et cpu_temp_driver.py
    puis affiche les résultats côte à côte.
#>

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$TestExe    = Join-Path $ScriptDir "CpuTempDriver\x64\Debug\CpuTempTest.exe"
$PythonScript = Join-Path $ScriptDir "python\cpu_temp_driver.py"

Write-Host "=== CpuTempDriver – Tests ===" -ForegroundColor Cyan
Write-Host ""

# ── Vérifier que le service tourne ──────────────────────────────────────────
$svc = Get-Service "CpuTempDriver" -ErrorAction SilentlyContinue
if (-not $svc) {
    Write-Host "[ERREUR] Service 'CpuTempDriver' introuvable. Lancer install_driver.ps1 d'abord." -ForegroundColor Red
    exit 1
}
Write-Host "Service CpuTempDriver : $($svc.Status)" -ForegroundColor $(if($svc.Status -eq 'Running'){'Green'}else{'Yellow'})
Write-Host ""

# ── Test C ────────────────────────────────────────────────────────────────────
if (Test-Path $TestExe) {
    Write-Host "--- CpuTempTest.exe ---" -ForegroundColor Cyan
    & $TestExe
    Write-Host ""
} else {
    Write-Host "[SKIP] CpuTempTest.exe introuvable à : $TestExe" -ForegroundColor Yellow
}

# ── Test Python ───────────────────────────────────────────────────────────────
if (Test-Path $PythonScript) {
    Write-Host "--- cpu_temp_driver.py ---" -ForegroundColor Cyan
    python $PythonScript
    Write-Host ""
} else {
    Write-Host "[SKIP] cpu_temp_driver.py introuvable à : $PythonScript" -ForegroundColor Yellow
}
