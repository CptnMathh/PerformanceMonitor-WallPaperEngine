"""
Data collector using ThreadPoolExecutor for parallel metric collection.
Optimized for minimal CPU/RAM consumption.
"""
import time
import threading
import collections
import os
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
import psutil
import subprocess
import ctypes

# ── AMD Ryzen Master SDK ─────────────────────────────────────────────────────
try:
    from ryzen_master import init_and_check, get_quick_metrics, get_full_metrics, cleanup
    _HAS_RYZEN_MASTER = True
except ImportError:
    _HAS_RYZEN_MASTER = False

_app_start_time = time.time()
_net_prev = dict(sent=0, recv=0, t=0.0)
_net_lock = threading.Lock()

_gpu_cache = dict(ts=0.0, data={
    "gpu_usage": 0.0, "gpu_temp": 0.0,
    "vram_used_gb": 0.0, "vram_total_gb": 0.0, "vram_usage": 0.0,
    "gpu_name": "GPU", "gpu_ok": False,
})
_gpu_lock = threading.Lock()

_disk_drives = []
_disk_lock = threading.Lock()

_cpu_name_cache = None

# ── AMD Ryzen Master SDK state ───────────────────────────────────────────────
_ryzen_available = None  # None=untested, True=available, False=not available
_ryzen_lock = threading.Lock()
_ryzen_cache = dict(ts=0.0, data={})
_ryzen_full_cache = dict(ts=0.0, data={})

# ── LibreHardwareMonitor HTTP reader ──────────────────────────────────────────
LHM_URL         = "http://localhost:8085/data.json"
_LHM_TIMEOUT    = 1.5
_LHM_RETRY_FAIL = 60.0
_lhm_ok         = None   # None=untested  True=ok  False=failed
_lhm_retry_ts   = 0.0


def get_cpu_name():
    """Return the marketing CPU name (e.g. 'AMD Ryzen 7 8700F'), cached.

    platform.processor() returns 'AMD64 Family...' on Windows, so we read the
    registry ProcessorNameString instead.
    """
    global _cpu_name_cache
    if _cpu_name_cache:
        return _cpu_name_cache
    name = None
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
        winreg.CloseKey(key)
        name = (name or "").strip()
    except Exception:
        name = None
    if not name:
        try:
            import platform
            name = platform.processor() or "CPU"
        except Exception:
            name = "CPU"
    _cpu_name_cache = name
    return _cpu_name_cache


def cached_disk_drives():
    """Return the last-detected disk drives without re-scanning (fast)."""
    with _disk_lock:
        return list(_disk_drives)


def detect_disk_drives():
    global _disk_drives
    with _disk_lock:
        try:
            drives = []
            for partition in psutil.disk_partitions(all=False):
                dev = partition.device
                if not dev or len(dev) < 2 or dev[1] != ":":
                    continue
                drive = dev[:2].upper()
                if drive not in drives:
                    drives.append(drive)
            _disk_drives = sorted(drives)
            return _disk_drives
        except Exception:
            return []


# ── LHM helpers ───────────────────────────────────────────────────────────────

# Display order for sensor groups inside each hardware card
_LHM_GROUP_ORDER = ["load", "temperatures", "fans", "clocks", "voltages", "powers", "data"]

# Friendly labels for each group key (used by LHMView)
LHM_GROUP_LABELS = {
    "load":         "Charge",
    "temperatures": "Températures",
    "fans":         "Ventilateurs",
    "clocks":       "Fréquences",
    "voltages":     "Tensions",
    "powers":       "Puissance",
    "data":         "Mémoire",
}

# Friendly labels for hardware types (used by LHMView)
LHM_HW_LABELS = {
    "cpu":  "PROCESSEUR",
    "gpu":  "CARTE GRAPHIQUE",
    "ram":  "MÉMOIRE RAM",
    "mb":   "CARTE MÈRE",
    "disk": "STOCKAGE",
}


def _lhm_parse_val_unit(raw):
    """Return (float_value, unit_str) from a LHM sensor string like '45.0 °C'."""
    parts = str(raw or "").strip().split()
    if not parts:
        return None, ""
    try:
        val = float(parts[0].replace(",", "."))
    except ValueError:
        return None, ""
    unit = parts[1] if len(parts) > 1 else ""
    if unit == "GHz":          # normalise to MHz for uniform display
        val = round(val * 1000, 0)
        unit = "MHz"
    return val, unit


def _lhm_collect(node, hw_list=None, hw_ctx=None, grp_ctx=None):
    """Recursively walk the LHM data.json tree.

    Builds a list of hardware dicts, each with:
      {"name": str, "type": str, "groups": {group_name: [{"name", "val", "unit"}, ...]}}
    hw_type is detected from ImageURL; group from Text ("Temperatures", "Load", …).
    Both contexts are sticky across child recursion.
    """
    if hw_list is None:
        hw_list = []

    text = (node.get("Text") or "").strip()
    img  = (node.get("ImageURL") or "").lower()
    kids = node.get("Children") or []
    tl   = text.lower()

    # ── Detect hardware boundary ──────────────────────────────────────────────
    detected_hw = None
    if "cpu.png" in img:
        detected_hw = "cpu"
    elif "nvidia" in img:
        detected_hw = "gpu"
    elif "amd.png" in img:
        if any(k in tl for k in ("radeon", "rx ", "vega", "navi", "rdna")):
            detected_hw = "gpu"
        elif any(k in tl for k in ("ryzen", "athlon", "threadripper", "epyc")):
            detected_hw = "cpu"
    elif "ram" in img or tl == "generic memory":
        detected_hw = "ram"
    elif any(t in img for t in ("motherboard", "chip.png", "mobo")):
        detected_hw = "mb"
    elif any(t in img for t in ("hdd", "ssd")):
        detected_hw = "disk"
    # text-based fallback when ImageURL is generic
    elif hw_ctx is None:
        if any(k in tl for k in ("geforce", "rtx ", "gtx ", "quadro")):
            detected_hw = "gpu"
        elif tl == "generic memory":
            detected_hw = "ram"

    if detected_hw is not None:
        hw_ctx = {"name": text, "type": detected_hw, "groups": {}}
        hw_list.append(hw_ctx)
        grp_ctx = None

    # ── Detect sensor-group boundary ──────────────────────────────────────────
    if hw_ctx and tl in ("temperatures", "load", "data", "clocks",
                         "fans", "powers", "voltages"):
        grp_ctx = tl
        hw_ctx["groups"].setdefault(grp_ctx, [])

    # ── Leaf sensor ───────────────────────────────────────────────────────────
    if not kids:
        if hw_ctx and grp_ctx:
            val, unit = _lhm_parse_val_unit(node.get("Value"))
            if val is not None:
                hw_ctx["groups"][grp_ctx].append(
                    {"name": text, "val": val, "unit": unit})
        return hw_list

    for child in kids:
        _lhm_collect(child, hw_list, hw_ctx, grp_ctx)
    return hw_list


def _lhm_flat_metrics(hw_list):
    """Extract key flat metrics from the hardware list to update _data directly."""
    flat = {}
    for hw in hw_list:
        ht     = hw["type"]
        groups = hw["groups"]
        if ht == "cpu":
            for s in groups.get("load", []):
                if "total" in s["name"].lower():
                    flat.setdefault("cpu_lhm", s["val"])
            for s in groups.get("temperatures", []):
                if "package" in s["name"].lower():
                    flat["cpu_temp"] = s["val"]
                elif "cpu_temp" not in flat:
                    flat["cpu_temp"] = s["val"]
            # AMD-specific metrics from LHM
            for s in groups.get("powers", []):
                n = s["name"].lower()
                if "package" in n or "ppt" in n:
                    flat["amd_ppt"] = s["val"]
                elif "core" in n or "tdc" in n:
                    flat["amd_tdc"] = s["val"]
                elif "soc" in n or "edc" in n:
                    flat["amd_edc"] = s["val"]
            for s in groups.get("clocks", []):
                n = s["name"].lower()
                if "core" in n and ("speed" in n or "clock" in n):
                    flat["cpu_freq_cur"] = s["val"] / 1000 if s["val"] > 1000 else s["val"]
        elif ht == "gpu":
            for s in groups.get("load", []):
                if s["name"].lower() == "gpu core":
                    flat["gpu_usage"] = s["val"]      # ← matches Task Manager
            for s in groups.get("temperatures", []):
                if "core" in s["name"].lower():
                    flat.setdefault("gpu_temp", s["val"])
            for s in groups.get("data", []):
                n = s["name"].lower()
                if "used" in n and "memory" in n:
                    flat["vram_used_gb"] = s["val"]
                elif "total" in n and "memory" in n:
                    flat["vram_total_gb"] = s["val"]
        elif ht in ("mb", "cpu"):   # mobo or CPU sub-chip fans
            for s in groups.get("fans", []):
                n = s["name"].lower()
                if "cpu" in n:
                    flat.setdefault("cpu_fan", s["val"])
                else:
                    flat.setdefault("case_fans", s["val"])

    vt = flat.get("vram_total_gb", 0)
    vu = flat.get("vram_used_gb")
    if vt and vu is not None:
        flat["vram_usage"] = round(vu / vt * 100, 1)

    return flat


def collect_from_lhm():
    """Fetch all hardware sensors from LibreHardwareMonitor's HTTP server.

    Returns a dict with:
      - Flat keys (gpu_usage, gpu_temp, cpu_temp, …) that override psutil/nvidia-smi
      - "_lhm_hw": structured hardware list consumed by LHMView
      - "_lhm_ok": bool indicating successful connection
    Falls back gracefully (returns {}) when LHM is not running.
    """
    global _lhm_ok, _lhm_retry_ts
    now = time.time()
    if _lhm_ok is False and now < _lhm_retry_ts:
        return {"_lhm_ok": False, "_lhm_hw": []}
    try:
        with urllib.request.urlopen(LHM_URL, timeout=_LHM_TIMEOUT) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        hw_list = _lhm_collect(raw)
        flat    = _lhm_flat_metrics(hw_list)
        flat["_lhm_ok"] = True
        flat["_lhm_hw"] = hw_list
        _lhm_ok = True
        return flat
    except Exception:
        _lhm_ok = False
        _lhm_retry_ts = now + _LHM_RETRY_FAIL
        return {"_lhm_ok": False, "_lhm_hw": []}


def collect_cpu():
    """Collect cheap CPU metrics (fast, runs frequently).

    Note: process/thread counting is intentionally NOT done here because
    iterating over every process is expensive (~seconds) and would stall the
    fast CPU sampling cadence. See collect_procs().
    """
    try:
        pct = psutil.cpu_percent(interval=0)
        percore = [round(p, 1) for p in psutil.cpu_percent(interval=0, percpu=True)]
        freq = psutil.cpu_freq()
        cur_ghz = round(freq.current / 1000, 2) if freq else 0.0
        max_ghz = round(freq.max / 1000, 2) if freq else 0.0
        logical = psutil.cpu_count(logical=True) or 0
        physical = psutil.cpu_count(logical=False) or 0
        uptime_sys = time.time() - psutil.boot_time()
        uptime_app = time.time() - _app_start_time
        return dict(
            cpu=round(pct, 1),
            cpu_percore=percore,
            cpu_freq_cur=cur_ghz,
            cpu_freq_max=max_ghz,
            cpu_logical=logical,
            cpu_physical=physical,
            cpu_name=get_cpu_name(),
            uptime_sys=uptime_sys,
            uptime_app=uptime_app,
        )
    except Exception:
        return dict(cpu=0.0, cpu_percore=[], cpu_freq_cur=0, cpu_freq_max=0,
                    cpu_logical=0, cpu_physical=0, uptime_sys=0, uptime_app=0)


def collect_procs():
    """Collect process and thread counts (expensive, runs infrequently)."""
    try:
        procs = len(psutil.pids())
        threads = 0
        for p in psutil.process_iter(["num_threads"]):
            try:
                threads += p.info.get("num_threads") or 0
            except Exception:
                pass
        return dict(process_count=procs, thread_count=threads)
    except Exception:
        return dict(process_count=0, thread_count=0)


def collect_ram():
    """Collect RAM metrics."""
    try:
        m = psutil.virtual_memory()
        return dict(
            memory=round(m.percent, 1),
            memory_used_gb=round(m.used / 1024**3, 1),
            memory_total_gb=round(m.total / 1024**3, 1),
            memory_avail_gb=round(m.available / 1024**3, 1),
        )
    except Exception:
        return dict(memory=0.0, memory_used_gb=0, memory_total_gb=0, memory_avail_gb=0)


def collect_gpu():
    """Collect GPU metrics with caching."""
    with _gpu_lock:
        now = time.time()
        if now - _gpu_cache["ts"] < 4.0 - 0.1:
            return dict(_gpu_cache["data"])
    try:
        out = subprocess.check_output(
            ["nvidia-smi",
             "--query-gpu=utilization.gpu,temperature.gpu,"
             "memory.used,memory.total,name",
             "--format=csv,noheader,nounits"],
            encoding="utf-8",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=3,
        )
        parts = [x.strip() for x in out.strip().split(",")]
        mu = float(parts[2]) / 1024
        mt = float(parts[3]) / 1024
        data = dict(
            gpu_usage=round(float(parts[0]), 1),
            gpu_temp=round(float(parts[1]), 1),
            vram_used_gb=round(mu, 1),
            vram_total_gb=round(mt, 1),
            vram_usage=round(mu / mt * 100, 1) if mt else 0.0,
            gpu_name=parts[4] if len(parts) > 4 else "GPU",
            gpu_ok=True,
        )
    except Exception:
        data = dict(gpu_usage=0.0, gpu_temp=0.0, vram_used_gb=0,
                    vram_total_gb=0, vram_usage=0.0,
                    gpu_name="GPU", gpu_ok=False)
    with _gpu_lock:
        _gpu_cache["data"] = data
        _gpu_cache["ts"] = time.time()
        return dict(data)


def collect_net(cfg=None):
    """Collect network metrics."""
    try:
        with _net_lock:
            now = psutil.net_io_counters()
            t_now = time.time()
            prev = _net_prev.copy()
            dt = max(t_now - prev["t"], 0.01)
            # Determine unit based on config (mb or kb)
            unit = (cfg or {}).get("net_unit", "mb")
            divisor = 1_048_576 if unit == "mb" else 1_024
            up = max(round((now.bytes_sent - prev["sent"]) / dt / divisor, 2), 0.0)
            dn = max(round((now.bytes_recv - prev["recv"]) / dt / divisor, 2), 0.0)
            _net_prev.update(sent=now.bytes_sent, recv=now.bytes_recv, t=t_now)
        return dict(upload_speed=up, download_speed=dn)
    except Exception:
        return dict(upload_speed=0.0, download_speed=0.0)


_disk_cache = {}        # drive -> last good metrics dict
_disk_poll_ts = {}      # drive -> last poll timestamp
_disk_slow = set()      # drives whose disk_usage() is slow (e.g. sleeping HDD)
_DISK_SLOW_SECS = 0.8   # a poll slower than this marks the drive "slow"
_DISK_SLOW_BACKOFF = 300.0   # slow drives are only re-polled every 5 min


def collect_disks():
    """Collect disk metrics with adaptive per-drive back-off.

    psutil.disk_usage() can block for several seconds on a sleeping/spinning-up
    HDD (and can hold the GIL during the wait, freezing the whole app). To keep
    the UI fluid we measure each drive's poll time: a drive that is slow is
    flagged and only re-polled occasionally, while its last-known values are
    served from cache in the meantime.
    """
    now = time.time()
    try:
        parts = psutil.disk_partitions(all=False)
    except Exception:
        return dict(_disk_cache)

    for part in parts:
        dev = part.device
        if not dev or len(dev) < 2 or dev[1] != ":":
            continue
        drive = dev[:2].upper()

        # Back off slow drives: serve cached data instead of waking them.
        if drive in _disk_slow and drive in _disk_cache:
            if (now - _disk_poll_ts.get(drive, 0)) < _DISK_SLOW_BACKOFF:
                continue

        t0 = time.perf_counter()
        try:
            du = psutil.disk_usage(drive)
            _disk_cache[drive] = dict(
                pct=round(du.percent, 1),
                used=round(du.used / 1024**3, 1),
                total=round(du.total / 1024**3, 1),
                free=round(du.free / 1024**3, 1),
            )
        except Exception:
            pass
        dt = time.perf_counter() - t0
        _disk_poll_ts[drive] = now
        if dt > _DISK_SLOW_SECS:
            _disk_slow.add(drive)
        elif dt < 0.3:
            _disk_slow.discard(drive)

    return dict(_disk_cache)


def collect_cpu_temp():
    """Collect CPU temperature from various sources."""
    val, method = None, "unavailable"
    
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for k in ("coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz", "nct6798"):
                if k in temps:
                    vs = [e.current for e in temps[k] if 0 < e.current < 130]
                    if vs:
                        val, method = round(sum(vs)/len(vs), 1), f"psutil/{k}"
                        break
            if val is None:
                for name, sensors in temps.items():
                    vs = [e.current for e in sensors if 0 < e.current < 130]
                    if vs:
                        val, method = round(sum(vs)/len(vs), 1), f"psutil/{name}"
                        break
    except Exception:
        pass
    
    try:
        import wmi
        for ns in ("root/LibreHardwareMonitor", "root/OpenHardwareMonitor"):
            try:
                vs = [s.Value for s in wmi.WMI(namespace=ns).Sensor()
                      if s.SensorType == "Temperature"
                      and any(k in s.Name.lower() for k in
                              ("cpu", "core", "package", "tdie", "tccd"))
                      and s.Value and 0 < s.Value < 130]
                if vs:
                    val = round(sum(vs)/len(vs), 1)
                    method = ns.split("/")[1]
                    break
            except Exception:
                pass
    except Exception:
        pass
    
    try:
        MAX = 128
        class _CT(ctypes.Structure):
            _fields_ = [
                ("uiLoad", ctypes.c_uint * MAX),
                ("uiTjMax", ctypes.c_uint * MAX),
                ("uiCoreCnt", ctypes.c_uint),
                ("uiCPUCnt", ctypes.c_uint),
                ("fTemp", ctypes.c_float * MAX),
                ("fVID", ctypes.c_float),
                ("fCPUSpeed", ctypes.c_float),
                ("fFSBSpeed", ctypes.c_float),
                ("fMultiplier", ctypes.c_float),
                ("sCPUName", ctypes.c_char * 100),
                ("ucFahrenheit", ctypes.c_ubyte),
                ("ucDeltaToTjMax", ctypes.c_ubyte),
            ]
        hnd = ctypes.windll.kernel32.OpenFileMappingW(
            0x0004, False, "CoreTempMappingObject")
        if hnd:
            ptr = ctypes.windll.kernel32.MapViewOfFile(hnd, 0x0004, 0, 0, 0)
            if ptr:
                raw = ctypes.string_at(ptr, ctypes.sizeof(_CT))
                ctypes.windll.kernel32.UnmapViewOfFile(ptr)
                ctypes.windll.kernel32.CloseHandle(hnd)
                d = _CT.from_buffer(
                    ctypes.create_string_buffer(raw, ctypes.sizeof(_CT)))
                n = max(0, min(int(d.uiCoreCnt), MAX))
                vs = [d.fTemp[i] for i in range(n) if 0 < d.fTemp[i] < 130]
                if vs:
                    val, method = round(sum(vs)/len(vs), 1), "CoreTemp"
            else:
                ctypes.windll.kernel32.CloseHandle(hnd)
    except Exception:
        pass
    
    return dict(cpu_temp=val, cpu_temp_method=method)


def collect_fans():
    """Collect fan speeds."""
    cpu_fan, case_fans = None, []
    cpu_kw = ("cpu", "pump", "water", "aio", "liquid")
    case_kw = ("case", "chassis", "sys", "fan")
    try:
        f = psutil.sensors_fans()
        if f:
            for name, lst in f.items():
                for fan in lst:
                    if fan.current and fan.current > 50:
                        n = name.lower()
                        if any(k in n for k in cpu_kw):
                            if cpu_fan is None or fan.current > cpu_fan:
                                cpu_fan = round(fan.current)
                        else:
                            case_fans.append(round(fan.current))
    except Exception:
        pass
    try:
        import wmi
        for ns in ("root/LibreHardwareMonitor", "root/OpenHardwareMonitor"):
            try:
                for s in wmi.WMI(namespace=ns).Sensor():
                    if s.SensorType == "Fan" and s.Value and s.Value > 50:
                        n = s.Name.lower()
                        if any(k in n for k in cpu_kw):
                            if cpu_fan is None or s.Value > cpu_fan:
                                cpu_fan = round(s.Value)
                        else:
                            case_fans.append(round(s.Value))
            except Exception:
                pass
    except Exception:
        pass
    avg_case = round(sum(case_fans)/len(case_fans)) if case_fans else None
    return dict(cpu_fan=cpu_fan, case_fans=avg_case, case_fans_list=case_fans)


# ── AMD Ryzen Master ──────────────────────────────────────────────────────────

def check_ryzen_available():
    """Check if Ryzen Master SDK is available and initialize it."""
    global _ryzen_available
    
    if not _HAS_RYZEN_MASTER:
        _ryzen_available = False
        return False
    
    with _ryzen_lock:
        if _ryzen_available is not None:
            return _ryzen_available
        
        try:
            result = init_and_check()
            _ryzen_available = result.get("available", False)
            return _ryzen_available
        except Exception:
            _ryzen_available = False
            return False


def collect_ryzen_quick():
    """Collect quick AMD Ryzen metrics (lightweight, runs frequently)."""
    if not _HAS_RYZEN_MASTER:
        return {}
    
    with _ryzen_lock:
        now = time.time()
        if now - _ryzen_cache["ts"] < 2.0 - 0.1:  # Cache for 2 seconds
            return dict(_ryzen_cache["data"])
    
    # Check availability if not done yet
    if _ryzen_available is None:
        check_ryzen_available()
    
    if not _ryzen_available:
        return {}
    
    try:
        data = get_quick_metrics()
        if data:
            data["ryzen_ok"] = True
        else:
            data = {"ryzen_ok": False}
        
        with _ryzen_lock:
            _ryzen_cache["data"] = data
            _ryzen_cache["ts"] = now
        return dict(data)
    except Exception:
        return {"ryzen_ok": False}


def collect_ryzen_full():
    """Collect full AMD Ryzen metrics (comprehensive, runs infrequently)."""
    if not _HAS_RYZEN_MASTER:
        return {}
    
    with _ryzen_lock:
        now = time.time()
        if now - _ryzen_full_cache["ts"] < 10.0 - 0.1:  # Cache for 10 seconds
            return dict(_ryzen_full_cache["data"])
    
    # Check availability if not done yet
    if _ryzen_available is None:
        check_ryzen_available()
    
    if not _ryzen_available:
        return {}
    
    try:
        data = get_full_metrics()
        if data:
            data["ryzen_ok"] = True
        else:
            data = {"ryzen_ok": False}
        
        with _ryzen_lock:
            _ryzen_full_cache["data"] = data
            _ryzen_full_cache["ts"] = now
        return dict(data)
    except Exception:
        return {"ryzen_ok": False}


class DataCollector:
    """Main data collector using ThreadPoolExecutor with optimized rates."""
    
    def __init__(self, cfg):
        from config import RATE_CPU, RATE_RAM, RATE_NET, RATE_GPU, RATE_TEMP, RATE_FAN, RATE_DISK, HIST_LEN
        
        self._cfg = cfg
        self._lock    = threading.Lock()
        self._data    = {}
        self._disks   = {}
        self._lhm_data= {"ok": False, "hardware": []}
        self._hist    = {}
        self._last    = {}
        self._running = False
        self._pool = ThreadPoolExecutor(
            max_workers=min(os.cpu_count() or 4, 8),
            thread_name_prefix="SCat",
        )
        self._thread = None
        
        # Initialize histories
        for key in ("cpu", "ram", "gpu", "gpu_temp", "vram", "net_dn", "net_up",
                    "cpu_temp", "cpu_fan", "case_fans", "amd_temp", "amd_ppt"):
            self._hist[key] = collections.deque([0.0] * HIST_LEN, maxlen=HIST_LEN)

        # Running stats for the General section (min / max / sum / count)
        self._stats = {}
        for key in ("cpu", "ram", "gpu", "gpu_temp", "vram", "net_dn", "net_up",
                    "cpu_temp", "cpu_fan", "case_fans", "amd_temp", "amd_ppt"):
            self._stats[key] = dict(mn=None, mx=None, sm=0.0, cnt=0)
        
        # Initialize network
        collect_net()
        time.sleep(0.05)
        
        # Detect disk drives
        detect_disk_drives()
    
    def start(self):
        """Start the collector thread."""
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, name="SCat-collect", daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop the collector."""
        self._running = False
        self._pool.shutdown(wait=False, cancel_futures=True)

    def update_cfg(self, cfg):
        """Update the collector's configuration at runtime."""
        with self._lock:
            self._cfg = cfg
    
    def _loop(self):
        """Main collection loop with optimized refresh rates.

        Tasks are dispatched to the thread pool and their results are stored
        via non-blocking done-callbacks. This way slow collectors (GPU via
        nvidia-smi, temperature/fans via WMI) never stall the fast
        CPU/RAM/NET updates, keeping the UI fluid and spreading work across
        cores.
        """
        from config import rate_for

        # Avoid dispatching the same task again while a previous one is running.
        inflight = set()

        def dispatch(key, rate, fn):
            if not self._running:
                return
            now = time.time()
            if key in inflight:
                return
            if now - self._last.get(key, 0) < rate:
                return
            self._last[key] = now
            inflight.add(key)
            try:
                fut = self._pool.submit(fn)
            except RuntimeError:
                # Pool was shut down while looping.
                inflight.discard(key)
                return
            fut.add_done_callback(lambda f, k=key: self._on_result(k, f, inflight))

        while self._running:
            cfg = self._cfg
            # LHM first: overrides nvidia-smi gpu/temp values when connected
            dispatch("lhm",  rate_for("lhm",  cfg), collect_from_lhm)
            dispatch("cpu",  rate_for("cpu",  cfg), collect_cpu)
            dispatch("ram",  rate_for("ram",  cfg), collect_ram)
            dispatch("net",  rate_for("net",  cfg), lambda: collect_net(cfg))
            dispatch("proc", rate_for("proc", cfg), collect_procs)
            dispatch("gpu",  rate_for("gpu",  cfg), collect_gpu)
            dispatch("temp", rate_for("temp", cfg), collect_cpu_temp)
            dispatch("fans", rate_for("fans", cfg), collect_fans)
            dispatch("disk", rate_for("disk", cfg), collect_disks)
            # AMD Ryzen Master (if available)
            dispatch("ryzen_quick", rate_for("ryzen_quick", cfg), collect_ryzen_quick)
            dispatch("ryzen_full", rate_for("ryzen_full", cfg), collect_ryzen_full)
            time.sleep(0.1)

    def _on_result(self, key, fut, inflight):
        """Store a completed collection result (runs in worker thread)."""
        try:
            result = fut.result()
            with self._lock:
                if key == "disk":
                    self._disks = result or {}
                elif key == "lhm" and isinstance(result, dict):
                    # Split LHM result: structured data → _lhm_data, flat metrics → _data
                    self._lhm_data = {
                        "ok":       bool(result.get("_lhm_ok", False)),
                        "hardware": result.get("_lhm_hw", []),
                    }
                    flat = {k: v for k, v in result.items()
                            if not k.startswith("_lhm")}
                    self._data.update(flat)
                elif isinstance(result, dict):
                    self._data.update(result)
            self._update_hist(result if key != "disk" else {}, key)
        except Exception:
            pass
        finally:
            inflight.discard(key)
    
    def _update_hist(self, data, key):
        """Update history deque."""
        pushes = []
        if key == "cpu":
            pushes = [("cpu", data.get("cpu", 0))]
        elif key == "ram":
            pushes = [("ram", data.get("memory", 0))]
        elif key == "gpu":
            pushes = [
                ("gpu", data.get("gpu_usage", 0)),
                ("gpu_temp", data.get("gpu_temp", 0)),
                ("vram", data.get("vram_usage", 0)),
            ]
        elif key == "net":
            pushes = [
                ("net_dn", data.get("download_speed", 0)),
                ("net_up", data.get("upload_speed", 0)),
            ]
        elif key == "temp":
            pushes = [("cpu_temp", data.get("cpu_temp", 0) or 0)]
        elif key == "fans":
            pushes = [
                ("cpu_fan", data.get("cpu_fan", 0) or 0),
                ("case_fans", data.get("case_fans", 0) or 0),
            ]
        elif key == "ryzen_quick":
            pushes = [
                ("amd_temp", data.get("amd_temp", 0) or 0),
                ("amd_ppt", data.get("amd_ppt", 0) or 0),
            ]
        
        with self._lock:
            for hkey, hval in pushes:
                if hkey in self._hist:
                    self._hist[hkey].append(float(hval))
                v = float(hval)
                if hkey in self._stats and v > 0:
                    s = self._stats[hkey]
                    s["mn"] = v if s["mn"] is None else min(s["mn"], v)
                    s["mx"] = v if s["mx"] is None else max(s["mx"], v)
                    s["sm"] += v
                    s["cnt"] += 1
            # Disk history per drive
            for drive, ddata in self._disks.items():
                hk = f"disk_{drive}"
                if hk not in self._hist:
                    self._hist[hk] = collections.deque([0.0] * 300, maxlen=300)
                self._hist[hk].append(float(ddata.get("pct", 0)))
    
    def snapshot(self):
        """Get current data snapshot."""
        with self._lock:
            d = dict(self._data)
            d["_disks"]    = dict(self._disks)
            d["_lhm"]      = dict(self._lhm_data)
            d["_hist"]     = {k: list(v) for k, v in self._hist.items()}
            d["uptime_app"]= time.time() - _app_start_time
            # Computed stats: {key: {min, max, avg}}
            stats = {}
            for k, s in self._stats.items():
                if s["cnt"] > 0:
                    stats[k] = {
                        "min": round(s["mn"], 1),
                        "max": round(s["mx"], 1),
                        "avg": round(s["sm"] / s["cnt"], 1),
                    }
            d["_stats"] = stats
        return d
    
    def http_payload(self):
        """Get HTTP payload in exact required format."""
        with self._lock:
            d = self._data
            di = self._disks
            ps = {}
            ps["cpu"] = d.get("cpu", 0)
            ps["cpu_percore"] = d.get("cpu_percore", [])
            ps["memory"] = d.get("memory", 0)
            used = d.get("memory_used_gb", 0)
            total = d.get("memory_total_gb", 0)
            ps["memory_gb"] = f"{used:.1f} GB/{total:.1f} GB"
            ps["gpu_usage"] = d.get("gpu_usage", 0)
            ps["vram_usage"] = d.get("vram_usage", 0)
            vu = d.get("vram_used_gb", 0)
            vt = d.get("vram_total_gb", 0)
            ps["vram_gb"] = f"{vu:.1f} GB/{vt:.1f} GB"
            ps["gpu_temp"] = d.get("gpu_temp", 0)
            ps["upload_speed"] = d.get("upload_speed", 0)
            ps["download_speed"] = d.get("download_speed", 0)
            ps["timestamp"] = d.get("timestamp", time.time())
            # AMD Ryzen Master metrics
            ps["amd_temp"] = d.get("amd_temp")
            ps["amd_ppt"] = d.get("amd_ppt")
            ps["amd_edc"] = d.get("amd_edc")
            ps["amd_tdc"] = d.get("amd_tdc")
            for drive, dd in di.items():
                k = drive.lower().replace(":", "") + "_disk"
                ps[k] = f"{dd.get('used', 0):.1f} GB/{dd.get('total', 0):.1f} GB"
        return dict(timestamp=time.time(), psutil=ps, hwinfo=[])
