# CpuTempDriver – Build & Deployment Guide

## Architecture overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Python (UltraLowPerf / collector.py)                           │
│    collect_cpu_temp_kernel()  ←  cpu_temp_driver.py             │
│                                        │ ctypes DeviceIoControl │
├────────────────────────────────────────┼────────────────────────┤
│  Win32 user-mode                        \\\\.\\CpuTemp           │
├────────────────────────────────────────┼────────────────────────┤
│  Kernel (ring-0)               \\Device\\CpuTemp                │
│    CpuTempDriver.sys                                            │
│      └─ TempBackend dispatcher                                  │
│            └─ AmdSmuBackend  (placeholder → extend here)        │
└─────────────────────────────────────────────────────────────────┘
```

## Prerequisites

| Tool | Requis pour | Vérifié | Download |
|------|-------------|---------|----------|
| Visual Studio 2022 (v17+) | Tout | ✅ présent (v18 Insiders) | visualstudio.microsoft.com |
| **C++ workload** (MSVC v143) | test_app + driver | ✅ présent | Via VS Installer → "Développement Desktop C++" |
| **Windows SDK** 10.0.26100.0 | test_app, Python | ✅ présent | Via VS Installer |
| **WDK** 10.0.26100.0 ← **MANQUANT** | driver kernel (.sys) | ❌ absent | [Télécharger le WDK](https://learn.microsoft.com/windows-hardware/drivers/download-the-wdk) |
| Windows 11 VM (test signing) | charger le .sys | — | Pour tester le driver |
| devcon.exe | installer le .sys | — | Inclus dans WDK: `Tools\x64\devcon.exe` |

> ⚠️ **WDK ≠ Windows SDK**
> - **Windows SDK** = headers/libs user-mode (`um/`, `ucrt/`) → suffit pour `CpuTempTest.c` et Python.
> - **WDK** = headers/libs kernel-mode (`km/`) + MSBuild targets `WindowsKernelModeDriver10.0`
>   → requis pour compiler `CpuTempDriver.sys`.
>
> Les deux sont installés séparément.  Le WDK version **doit correspondre** exactement au SDK installé.

### Installer le WDK (étapes)

1. Télécharger l'installeur WDK sur [learn.microsoft.com/windows-hardware/drivers/download-the-wdk](https://learn.microsoft.com/windows-hardware/drivers/download-the-wdk)
2. Lancer `wdksetup.exe` → choisir "Install Windows Driver Kit - Windows 10.0.26100.x to this computer"
3. À la fin, l'installeur propose **"Install Windows Driver Kit Visual Studio extension"** → **accepter**
   (c'est ce qui installe le platform toolset `WindowsKernelModeDriver10.0` dans VS)
4. Redémarrer VS après l'installation

---

## Step 1 – Enable test signing (test machine only)

The driver is not WHQL-signed.  Run in an **elevated PowerShell** on the
target machine (VM recommended):

```powershell
bcdedit /set testsigning on
# Reboot required
Restart-Computer
```

> **Production**: Submit the driver package to the Microsoft Hardware Dev Center
> for attestation signing.  Attestation signing is free, does not require WHQL,
> and works on all Windows 11 machines without test mode.

---

## Step 2 – Build the kernel driver

1. Open **Visual Studio 2022**
2. `File → Open → Project/Solution` → select `driver\CpuTempDriver\CpuTempDriver.vcxproj`
3. Select configuration **Debug | x64**
4. `Build → Build Solution`

Output: `driver\CpuTempDriver\x64\Debug\CpuTempDriver.sys`

---

## Step 3 – Install the driver

Copy to the test machine (or use a shared folder):
```
CpuTempDriver.sys
CpuTempDriver.inf
WdfCoInstaller01033.dll   ← from WDK redist folder
```

WDK redistributable location:
```
C:\Program Files (x86)\Windows Kits\10\Redist\<SDK>\wdf\kmdf\x64\1.33\
```

Install (elevated Command Prompt):
```cmd
devcon.exe install CpuTempDriver.inf Root\CpuTempDriver
```

Verify:
```cmd
devcon.exe status Root\CpuTempDriver
sc query CpuTempDriver
```

Uninstall:
```cmd
devcon.exe remove Root\CpuTempDriver
```

---

## Step 4 – Build the user-mode test app

No WDK required.  Use a **Developer Command Prompt for VS 2022**:

```cmd
cd driver\test_app
cl /W4 /WX /nologo CpuTempTest.c /link kernel32.lib
```

Run:
```cmd
CpuTempTest.exe            # single read
CpuTempTest.exe --loop     # poll every 1 s
```

Expected output (backend not yet implemented):
```
CpuTempTest  –  device opened successfully
─────────────────────────────────────────
Backend : AmdSmu
Status  : not yet implemented (3)
Temp    : UNAVAILABLE
```

---

## Step 5 – Run the Python client

No installation needed (`ctypes` only):

```cmd
python driver\python\cpu_temp_driver.py
python driver\python\cpu_temp_driver.py --loop
```

### Integrating with UltraLowPerf collector

In `base/collector.py`, add the kernel driver as the highest-priority source
inside `collect_cpu_temp()`:

```python
from driver.python.cpu_temp_driver import collect_cpu_temp_kernel

def collect_cpu_temp():
    # Try kernel driver first (self-contained, no external tools)
    result = collect_cpu_temp_kernel()
    if result.get("cpu_temp") is not None:
        return result
    # … existing fallbacks (LHM, HWiNFO64, CoreTemp) …
```

---

## Step 6 – Implementing real AMD SMU reads

Once you have the correct register offsets for the Ryzen 7 8700F (Zen 4 / AM5):

1. Open `driver\CpuTempDriver\AmdSmuBackend.c`
2. Locate the `FUTURE IMPLEMENTATION POINT` comment block inside `_AmdSmu_ReadTempMilliC()`
3. Replace the stub with the MMIO mailbox sequence described in the comments
4. Update `AMD_SMU_PCI_*` constants in `AmdSmuBackend.h` with verified BDF coordinates

**Resources for reverse-engineering SMU mailbox commands:**
- `ryzen_smu` (Linux kernel module, GPL): github.com/leogx9r/ryzen_smu
- `LibreHardwareMonitor` source (C#): github.com/LibreHardwareMonitor/LibreHardwareMonitor
  → `Hardware/Cpu/AmdCpu.cs`, `AmdSmu.cs`
- AMD BIOS and Kernel Developer Guide (BKDG) – partial register maps available on AMD developer portal

---

## File map

```
driver/
├── CpuTempDriver/
│   ├── ioctl.h              ← shared IOCTL definitions (kernel + user-mode)
│   ├── TempBackend.h        ← abstract backend interface (vtable)
│   ├── TempBackend.c        ← backend dispatcher / registration
│   ├── AmdSmuBackend.h      ← AMD SMU backend header + extension guide
│   ├── AmdSmuBackend.c      ← AMD SMU backend (placeholder)
│   ├── CpuTempDriver.c      ← KMDF driver entry, device, IOCTL handler
│   ├── CpuTempDriver.inf    ← driver installation manifest
│   └── CpuTempDriver.vcxproj
├── test_app/
│   └── CpuTempTest.c        ← user-mode C console client
├── python/
│   └── cpu_temp_driver.py   ← Python ctypes client + collector integration
└── BUILD.md                 ← this file
```
