#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Signe avec un certificat de test, active le test-signing,
    installe et démarre CpuTempDriver.sys.

.USAGE
    Ouvrir PowerShell en tant qu'Administrateur, puis :
    Set-ExecutionPolicy Bypass -Scope Process -Force
    .\install_driver.ps1
#>

$ErrorActionPreference = "Stop"
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$DriverDir  = Join-Path $ScriptDir "CpuTempDriver\x64\Debug"
$SysFile    = Join-Path $DriverDir "CpuTempDriver.sys"
$InfFile    = Join-Path $DriverDir "CpuTempDriver.inf"
$SignTool   = "C:\Program Files (x86)\Windows Kits\10\bin\10.0.28000.0\x64\signtool.exe"
$DevCon     = "C:\Program Files (x86)\Windows Kits\10\Tools\10.0.28000.0\x64\devcon.exe"
$HardwareId = "Root\CpuTempDriver"

Write-Host "=== CpuTempDriver – Installation ===" -ForegroundColor Cyan
Write-Host ""

# ── 0. Vérifications ──────────────────────────────────────────────────────────
foreach ($f in @($SysFile, $InfFile, $SignTool, $DevCon)) {
    if (-not (Test-Path $f)) {
        Write-Host "[ERREUR] Fichier manquant : $f" -ForegroundColor Red
        exit 1
    }
}
Write-Host "[OK] Tous les fichiers présents" -ForegroundColor Green

# ── 1. Activer le test-signing (si pas déjà actif) ───────────────────────────
$tsStatus = (bcdedit /enum "{current}" | Select-String "testsigning")
if ($tsStatus -match "Yes") {
    Write-Host "[OK] Test-signing déjà activé" -ForegroundColor Green
} else {
    Write-Host "[...] Activation du test-signing (redémarrage requis après)" -ForegroundColor Yellow
    bcdedit /set testsigning on | Out-Null
    Write-Host "[OK] Test-signing activé – le watermark 'Test Mode' apparaîtra au prochain démarrage" -ForegroundColor Green
}

# ── 2. Créer/récupérer le certificat de test ─────────────────────────────────
$CertSubject = "CN=CpuTempDriverTestCert"
$existingCert = Get-ChildItem Cert:\LocalMachine\My | Where-Object { $_.Subject -eq $CertSubject } | Select-Object -First 1

if ($existingCert) {
    Write-Host "[OK] Certificat de test existant réutilisé : $($existingCert.Thumbprint)" -ForegroundColor Green
    $cert = $existingCert
} else {
    Write-Host "[...] Création du certificat de test auto-signé"
    $cert = New-SelfSignedCertificate `
        -Subject $CertSubject `
        -Type CodeSigningCert `
        -CertStoreLocation "Cert:\LocalMachine\My" `
        -KeyUsage DigitalSignature `
        -FriendlyName "CpuTempDriver Test Certificate"
    Write-Host "[OK] Certificat créé : $($cert.Thumbprint)" -ForegroundColor Green
}

# ── 3. Faire confiance au certificat (TrustedPublisher + Root) ────────────────
foreach ($storeName in @("TrustedPublisher", "Root")) {
    $store = New-Object System.Security.Cryptography.X509Certificates.X509Store($storeName, "LocalMachine")
    $store.Open("ReadWrite")
    if (-not ($store.Certificates | Where-Object { $_.Thumbprint -eq $cert.Thumbprint })) {
        $store.Add($cert)
        Write-Host "[OK] Certificat ajouté au store '$storeName'" -ForegroundColor Green
    } else {
        Write-Host "[OK] Certificat déjà présent dans '$storeName'" -ForegroundColor Green
    }
    $store.Close()
}

# ── 4. Signer le .sys ─────────────────────────────────────────────────────────
Write-Host "[...] Signature de $SysFile"
& $SignTool sign /fd sha256 /sha1 $cert.Thumbprint /t "http://timestamp.digicert.com" $SysFile 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARN] Timestamping échoué – nouvelle tentative sans timestamp" -ForegroundColor Yellow
    & $SignTool sign /fd sha256 /sha1 $cert.Thumbprint $SysFile
}
if ($LASTEXITCODE -ne 0) { Write-Host "[ERREUR] Signature échouée" -ForegroundColor Red; exit 1 }
Write-Host "[OK] Driver signé" -ForegroundColor Green

# ── 5. Désinstaller l'ancienne version si présente ───────────────────────────
$existing = & $DevCon find $HardwareId 2>&1
if ($existing -match $HardwareId) {
    Write-Host "[...] Suppression de l'ancienne installation"
    & $DevCon remove $HardwareId | Out-Null
    Write-Host "[OK] Ancienne version supprimée" -ForegroundColor Green
}

# ── 6. Installer le driver avec devcon ───────────────────────────────────────
Write-Host "[...] Installation : devcon install $InfFile $HardwareId"
$result = & $DevCon install $InfFile $HardwareId 2>&1
Write-Host $result
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERREUR] Installation échouée (code $LASTEXITCODE)" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Driver installé" -ForegroundColor Green

# ── 7. Vérifier que le service est démarré ───────────────────────────────────
Start-Sleep -Seconds 2
$svc = Get-Service -Name "CpuTempDriver" -ErrorAction SilentlyContinue
if ($svc) {
    Write-Host "[OK] Service : $($svc.Status)" -ForegroundColor Green
} else {
    Write-Host "[WARN] Service 'CpuTempDriver' non trouvé via Get-Service" -ForegroundColor Yellow
    sc.exe query CpuTempDriver
}

Write-Host ""
Write-Host "=== Installation terminée ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Tester maintenant :" -ForegroundColor White
Write-Host "  .\CpuTempDriver\x64\Debug\  ->  CpuTempTest.exe" -ForegroundColor Gray

# ── Note redémarrage ─────────────────────────────────────────────────────────
$tsNow = (bcdedit /enum "{current}" | Select-String "testsigning")
if ($tsNow -match "Yes") {
    Write-Host ""
    Write-Host "[INFO] Test-signing activé. Si c'est la première fois, redémarrer Windows" -ForegroundColor Yellow
    Write-Host "       pour que le mode test prenne effet avant de charger le driver." -ForegroundColor Yellow
}
