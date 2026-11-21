"""
AMD Ryzen Master SDK Monitoring DLL wrapper.

Provides access to AMD Ryzen CPU metrics via the AMDRyzenMasterMonitoringDLL.dll.

The DLL must be in the same directory as this script or in the system PATH.
Required driver files (if not installed):
- AMDRyzenMasterDriver.inf
- AMDRyzenMasterDriver.cat
- AMDRyzenMasterDriver.sys
"""
import ctypes
import os
import threading
from typing import Optional, Dict, Any


# ── Structs matching the DLL definitions ──────────────────────────────────────

class RMQuickStats(ctypes.Structure):
    """Quick stats from ShortQuery() - lightweight, fast."""
    _fields_ = [
        ("Init", ctypes.c_int),
        ("fPPTValue", ctypes.c_float),        # Power Package Tracking (W)
        ("fEDCValue_VDD", ctypes.c_float),    # Electrical Design Current (A)
        ("fTDCValue_VDD", ctypes.c_float),    # Thermal Design Current (A)
        ("dTemperature", ctypes.c_double),    # CPU Temperature (C)
        ("dPeakCoreVoltage", ctypes.c_double), # Peak core voltage (V)
        ("dAvgCoreVoltage", ctypes.c_double),  # Average core voltage (V)
    ]


class RMFullStats(ctypes.Structure):
    """Full stats from LongQuery() - comprehensive but slower."""
    _fields_ = [
        ("Init", ctypes.c_int),
        ("uCoreCount", ctypes.c_int),
        ("uCorePark", ctypes.c_int),
        ("L1DataCache", ctypes.c_int),
        ("L1InstructionCache", ctypes.c_int),
        ("L3Cache", ctypes.c_int),
        ("fPPTLimit", ctypes.c_float),
        ("fPPTValue", ctypes.c_float),
        ("fEDCLimit_VDD", ctypes.c_float),
        ("fEDCValue_VDD", ctypes.c_float),
        ("fTDCLimit_VDD", ctypes.c_float),
        ("fTDCValue_VDD", ctypes.c_float),
        ("fEDCLimit_SOC", ctypes.c_float),
        ("fEDCValue_SOC", ctypes.c_float),
        ("fTDCLimit_SOC", ctypes.c_float),
        ("fTDCValue_SOC", ctypes.c_float),
        ("fcHTCLimit", ctypes.c_float),
        ("fFCLKP0Freq", ctypes.c_float),
        ("fVDDCR_VDD_Power", ctypes.c_float),
        ("fVDDCR_SOC_Power", ctypes.c_float),
        ("fCCLK_Fmax", ctypes.c_float),
        ("eMode", ctypes.c_int),              # 0=Manual, 1=PBO, 2=AutoOC, 3=Reserved
        ("dPeakSpeed", ctypes.c_double),      # Peak clock speed (MHz)
        ("dPeakCoreVoltage", ctypes.c_double),
        ("dAvgCoreVoltage", ctypes.c_double),
        ("dSocVoltage", ctypes.c_double),
        ("dTemperature", ctypes.c_double),
        ("uVDDIO", ctypes.c_int),
        ("uMemClock", ctypes.c_int),
        ("uTcl", ctypes.c_int),
        ("uTcdrd", ctypes.c_int),
        ("uTras", ctypes.c_int),
        ("uTrp", ctypes.c_int),
    ]


class RMSystemInfo(ctypes.Structure):
    """System info from IsSupported()."""
    _fields_ = [
        ("Privileges", ctypes.c_int),         # 1 if running as admin
        ("SupportedOS", ctypes.c_int),        # 1 if OS is supported
        ("DriverService", ctypes.c_int),       # 1 if driver is installed
        ("SupportedProc", ctypes.c_int),      # 1 if CPU is supported
        ("AuthenticAMD", ctypes.c_int),       # 1 if authentic AMD CPU
    ]


# ── Global state ─────────────────────────────────────────────────────────────

_dll = None
_dll_lock = threading.Lock()
_initialized = False
_last_usage_check = 0.0
_last_cpu_usage = 0.0


# ── DLL loading ───────────────────────────────────────────────────────────────

def _load_dll() -> Optional[ctypes.WinDLL]:
    """Load the AMDRyzenMasterMonitoringDLL.dll."""
    global _dll
    
    with _dll_lock:
        if _dll is not None:
            return _dll
        
        # Try to load from current directory first
        dll_path = os.path.join(os.path.dirname(__file__), "AMDRyzenMasterMonitoringDLL.dll")
        if not os.path.exists(dll_path):
            # Try from parent directory (for bundled builds)
            dll_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                                    "AMDRyzenMasterMonitoringDLL.dll")
        
        try:
            _dll = ctypes.WinDLL(dll_path)
            return _dll
        except Exception:
            # Try loading from system PATH
            try:
                _dll = ctypes.WinDLL("AMDRyzenMasterMonitoringDLL.dll")
                return _dll
            except Exception:
                return None


# ── DLL function wrappers ─────────────────────────────────────────────────────

def is_supported() -> Optional[RMSystemInfo]:
    """Check if the system supports Ryzen Master monitoring.
    
    Returns:
        RMSystemInfo struct or None if DLL not available.
    """
    dll = _load_dll()
    if dll is None:
        return None
    
    try:
        dll.IsSupported.restype = RMSystemInfo
        dll.IsSupported.argtypes = []
        return dll.IsSupported()
    except Exception:
        return None


def platform_init() -> bool:
    """Initialize the Ryzen Master monitoring platform.
    
    Must be called before ShortQuery/LongQuery.
    Returns True on success, False on failure.
    """
    global _initialized
    
    dll = _load_dll()
    if dll is None:
        return False
    
    try:
        dll.PlatformInit.restype = ctypes.c_bool
        dll.PlatformInit.argtypes = []
        result = dll.PlatformInit()
        _initialized = result
        return result
    except Exception:
        _initialized = False
        return False


def platform_uninit() -> bool:
    """Uninitialize the Ryzen Master monitoring platform."""
    global _initialized
    
    dll = _load_dll()
    if dll is None:
        return False
    
    try:
        dll.PlatformUninit.restype = ctypes.c_bool
        dll.PlatformUninit.argtypes = []
        result = dll.PlatformUninit()
        _initialized = False
        return result
    except Exception:
        _initialized = False
        return False


def short_query() -> Optional[RMQuickStats]:
    """Query quick stats (lightweight, fast).
    
    Returns:
        RMQuickStats struct or None if failed.
    """
    dll = _load_dll()
    if dll is None or not _initialized:
        return None
    
    try:
        dll.ShortQuery.restype = RMQuickStats
        dll.ShortQuery.argtypes = []
        result = dll.ShortQuery()
        if result.Init == 1:
            return result
        return None
    except Exception:
        return None


def long_query() -> Optional[RMFullStats]:
    """Query full stats (comprehensive, slower).
    
    Returns:
        RMFullStats struct or None if failed.
    """
    dll = _load_dll()
    if dll is None or not _initialized:
        return None
    
    try:
        dll.LongQuery.restype = RMFullStats
        dll.LongQuery.argtypes = []
        result = dll.LongQuery()
        if result.Init == 1:
            return result
        return None
    except Exception:
        return None


def cpu_usage() -> Optional[float]:
    """Get CPU usage percentage.
    
    Note: This uses a 100ms delta internally. Don't call more frequently
    than every 125ms.
    
    Returns:
        CPU usage percentage (0-100) or None if failed.
    """
    global _last_usage_check, _last_cpu_usage
    
    dll = _load_dll()
    if dll is None:
        return None
    
    # Rate limit to 125ms minimum
    import time
    now = time.time()
    if now - _last_usage_check < 0.125:
        return _last_cpu_usage
    
    try:
        dll.CPUUsage.restype = ctypes.c_double
        dll.CPUUsage.argtypes = []
        result = dll.CPUUsage()
        _last_usage_check = now
        _last_cpu_usage = result
        return result
    except Exception:
        return None


# ── High-level convenience functions ─────────────────────────────────────────

def init_and_check() -> Dict[str, Any]:
    """Initialize and check if Ryzen Master monitoring is available.
    
    Returns:
        Dict with keys:
        - available: bool (True if all checks pass)
        - system_info: RMSystemInfo or None
        - initialized: bool
        - message: str (error message if not available)
    """
    sys_info = is_supported()
    if sys_info is None:
        return {
            "available": False,
            "system_info": None,
            "initialized": False,
            "message": "DLL not found or failed to load"
        }
    
    # Check if we have admin privileges
    if sys_info.Privileges != 1:
        return {
            "available": False,
            "system_info": sys_info,
            "initialized": False,
            "message": "Admin privileges required"
        }
    
    # Check if it's an authentic AMD CPU
    if sys_info.AuthenticAMD != 1:
        return {
            "available": False,
            "system_info": sys_info,
            "initialized": False,
            "message": "Not an authentic AMD CPU"
        }
    
    # Check if CPU is supported
    if sys_info.SupportedProc != 1:
        return {
            "available": False,
            "system_info": sys_info,
            "initialized": False,
            "message": "CPU not supported by Ryzen Master SDK"
        }
    
    # Check if driver is installed
    if sys_info.DriverService != 1:
        return {
            "available": False,
            "system_info": sys_info,
            "initialized": False,
            "message": "Ryzen Master driver not installed"
        }
    
    # Try to initialize
    if not platform_init():
        return {
            "available": False,
            "system_info": sys_info,
            "initialized": False,
            "message": "Platform initialization failed"
        }
    
    return {
        "available": True,
        "system_info": sys_info,
        "initialized": True,
        "message": "OK"
    }


def get_quick_metrics() -> Dict[str, Any]:
    """Get quick metrics in a Python-friendly dict format.
    
    Returns:
        Dict with AMD-specific metrics or empty dict if unavailable.
    """
    if not _initialized:
        return {}
    
    stats = short_query()
    if stats is None:
        return {}
    
    return {
        "amd_temp": round(stats.dTemperature, 1) if stats.dTemperature >= 0 else None,
        "amd_ppt": round(stats.fPPTValue, 1) if stats.fPPTValue >= 0 else None,
        "amd_edc": round(stats.fEDCValue_VDD, 1) if stats.fEDCValue_VDD >= 0 else None,
        "amd_tdc": round(stats.fTDCValue_VDD, 1) if stats.fTDCValue_VDD >= 0 else None,
        "amd_peak_voltage": round(stats.dPeakCoreVoltage, 3) if stats.dPeakCoreVoltage >= 0 else None,
        "amd_avg_voltage": round(stats.dAvgCoreVoltage, 3) if stats.dAvgCoreVoltage >= 0 else None,
    }


def get_full_metrics() -> Dict[str, Any]:
    """Get full metrics in a Python-friendly dict format.
    
    Returns:
        Dict with comprehensive AMD metrics or empty dict if unavailable.
    """
    if not _initialized:
        return {}
    
    stats = long_query()
    if stats is None:
        return {}
    
    # Mode mapping
    mode_names = {0: "Manual", 1: "PBO", 2: "AutoOC", 3: "Reserved"}
    mode = mode_names.get(stats.eMode, "Unknown")
    
    return {
        "amd_temp": round(stats.dTemperature, 1) if stats.dTemperature >= 0 else None,
        "amd_ppt": round(stats.fPPTValue, 1) if stats.fPPTValue >= 0 else None,
        "amd_ppt_limit": round(stats.fPPTLimit, 1) if stats.fPPTLimit >= 0 else None,
        "amd_edc": round(stats.fEDCValue_VDD, 1) if stats.fEDCValue_VDD >= 0 else None,
        "amd_edc_limit": round(stats.fEDCLimit_VDD, 1) if stats.fEDCLimit_VDD >= 0 else None,
        "amd_tdc": round(stats.fTDCValue_VDD, 1) if stats.fTDCValue_VDD >= 0 else None,
        "amd_tdc_limit": round(stats.fTDCLimit_VDD, 1) if stats.fTDCLimit_VDD >= 0 else None,
        "amd_soc_edc": round(stats.fEDCValue_SOC, 1) if stats.fEDCValue_SOC >= 0 else None,
        "amd_soc_edc_limit": round(stats.fEDCLimit_SOC, 1) if stats.fEDCLimit_SOC >= 0 else None,
        "amd_soc_tdc": round(stats.fTDCValue_SOC, 1) if stats.fTDCValue_SOC >= 0 else None,
        "amd_soc_tdc_limit": round(stats.fTDCLimit_SOC, 1) if stats.fTDCLimit_SOC >= 0 else None,
        "amd_vdd_power": round(stats.fVDDCR_VDD_Power, 1) if stats.fVDDCR_VDD_Power >= 0 else None,
        "amd_soc_power": round(stats.fVDDCR_SOC_Power, 1) if stats.fVDDCR_SOC_Power >= 0 else None,
        "amd_peak_speed": round(stats.dPeakSpeed, 0) if stats.dPeakSpeed >= 0 else None,
        "amd_peak_voltage": round(stats.dPeakCoreVoltage, 3) if stats.dPeakCoreVoltage >= 0 else None,
        "amd_avg_voltage": round(stats.dAvgCoreVoltage, 3) if stats.dAvgCoreVoltage >= 0 else None,
        "amd_soc_voltage": round(stats.dSocVoltage, 3) if stats.dSocVoltage >= 0 else None,
        "amd_core_count": stats.uCoreCount if stats.uCoreCount >= 0 else None,
        "amd_core_parked": stats.uCorePark if stats.uCorePark >= 0 else None,
        "amd_l1_dcache": stats.L1DataCache if stats.L1DataCache >= 0 else None,
        "amd_l1_icache": stats.L1InstructionCache if stats.L1InstructionCache >= 0 else None,
        "amd_l3_cache": stats.L3Cache if stats.L3Cache >= 0 else None,
        "amd_fclk": round(stats.fFCLKP0Freq, 0) if stats.fFCLKP0Freq >= 0 else None,
        "amd_cclk_fmax": round(stats.fCCLK_Fmax, 0) if stats.fCCLK_Fmax >= 0 else None,
        "amd_mode": mode,
        "amd_vddio": stats.uVDDIO if stats.uVDDIO >= 0 else None,
        "amd_mem_clock": stats.uMemClock if stats.uMemClock >= 0 else None,
        "amd_tcl": stats.uTcl if stats.uTcl >= 0 else None,
        "amd_tcdrd": stats.uTcdrd if stats.uTcdrd >= 0 else None,
        "amd_tras": stats.uTras if stats.uTras >= 0 else None,
        "amd_trp": stats.uTrp if stats.uTrp >= 0 else None,
    }


def cleanup():
    """Cleanup and uninitialize the platform."""
    platform_uninit()
