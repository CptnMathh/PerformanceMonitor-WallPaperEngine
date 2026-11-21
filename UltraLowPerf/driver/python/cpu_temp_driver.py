"""
cpu_temp_driver.py  –  Python interface to CpuTempDriver (kernel-mode)
======================================================================
Communicates with \\Device\\CpuTemp via DeviceIoControl using ctypes
and the Win32 API only.  No third-party packages required beyond the
standard library.

Usage (standalone):
    python cpu_temp_driver.py             # single read
    python cpu_temp_driver.py --loop      # poll every 1 s

Integration with UltraLowPerf collector:
    from driver.python.cpu_temp_driver import KernelTempDriver
    driver = KernelTempDriver()
    millic, status, backend = driver.read()   # milli-Celsius or None

Architecture:
    Python (this file)
        └─ Win32 CreateFile  →  \\\\.\\CpuTemp
        └─ Win32 DeviceIoControl  →  IOCTL_GET_CPU_TEMP
                └─ kernel CpuTempDriver.sys
                        └─ TempBackend dispatcher
                                └─ AmdSmuBackend (Ryzen SMU)
"""

import ctypes
import ctypes.wintypes as wt
import struct
import sys
import time

# ── IOCTL constant (must match ioctl.h) ──────────────────────────────────────
_FILE_DEVICE_UNKNOWN = 0x00000022
_METHOD_BUFFERED     = 0
_FILE_ANY_ACCESS     = 0

def _ctl_code(device_type, func, method, access):
    return (device_type << 16) | (access << 14) | (func << 2) | method

IOCTL_GET_CPU_TEMP = _ctl_code(
    _FILE_DEVICE_UNKNOWN, 0x800, _METHOD_BUFFERED, _FILE_ANY_ACCESS)

CPUTEMP_UNAVAILABLE = 0xFFFFFFFF

# ── Output struct layout (matches CPU_TEMP_OUTPUT in ioctl.h, packed) ────────
# TempMilliC  : uint32   (offset 0)
# Status      : uint32   (offset 4)
# BackendName : char[32] (offset 8)
_OUTPUT_FMT  = "<II32s"       # little-endian, two uint32, 32 raw bytes
_OUTPUT_SIZE = struct.calcsize(_OUTPUT_FMT)   # == 40 bytes

_STATUS_NAMES = {
    0: "OK",
    1: "backend not initialised",
    2: "hardware read error",
    3: "not yet implemented",
}

# ── Win32 API wrappers ────────────────────────────────────────────────────────
_k32 = ctypes.windll.kernel32

_k32.CreateFileW.restype  = wt.HANDLE
_k32.CreateFileW.argtypes = [
    wt.LPCWSTR, wt.DWORD, wt.DWORD,
    ctypes.c_void_p, wt.DWORD, wt.DWORD, wt.HANDLE,
]

_k32.DeviceIoControl.restype  = wt.BOOL
_k32.DeviceIoControl.argtypes = [
    wt.HANDLE, wt.DWORD,
    ctypes.c_void_p, wt.DWORD,   # input buffer
    ctypes.c_void_p, wt.DWORD,   # output buffer
    ctypes.POINTER(wt.DWORD),    # bytes returned
    ctypes.c_void_p,             # OVERLAPPED (NULL)
]

_k32.CloseHandle.restype  = wt.BOOL
_k32.CloseHandle.argtypes = [wt.HANDLE]

# INVALID_HANDLE_VALUE = (HANDLE)-1.  c_void_p(-1).value returns the
# platform-correct unsigned representation (0xFFFFFFFF_FFFFFFFF on Win64).
_INVALID_HANDLE = ctypes.c_void_p(-1).value
_GENERIC_READ   = 0x80000000
_SHARE_RW       = 0x00000001 | 0x00000002
_OPEN_EXISTING  = 3
_FILE_ATTR_NORM = 0x00000080

DEVICE_PATH = r"\\.\CpuTemp"


class DriverNotAvailableError(OSError):
    """Raised when the kernel driver device cannot be opened."""


class KernelTempDriver:
    """
    Context-manager + standalone client for CpuTempDriver.

    with KernelTempDriver() as d:
        millic, status, backend = d.read()
        if millic is None:
            print("unavailable:", status)
        else:
            print(f"{millic / 1000:.1f} °C  [{backend}]")
    """

    def __init__(self, device: str = DEVICE_PATH):
        self._device = device
        self._handle = None

    # ── Context manager ───────────────────────────────────────────────────────

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def open(self):
        """Open a handle to the kernel device.  Raises DriverNotAvailableError."""
        h = _k32.CreateFileW(
            self._device,
            _GENERIC_READ,
            _SHARE_RW,
            None,
            _OPEN_EXISTING,
            _FILE_ATTR_NORM,
            None,
        )
        if h is None or h == _INVALID_HANDLE:
            err = _k32.GetLastError()
            raise DriverNotAvailableError(
                f"Cannot open {self._device!r} (Win32 error 0x{err:08X}). "
                "Is CpuTempDriver installed and running?  "
                "Try running as Administrator."
            )
        self._handle = h

    def close(self):
        """Release the device handle."""
        if self._handle is not None:
            _k32.CloseHandle(self._handle)
            self._handle = None

    # ── Read ──────────────────────────────────────────────────────────────────

    def read(self):
        """
        Send IOCTL_GET_CPU_TEMP to the driver.

        Returns
        -------
        (millic, status_str, backend_name)
            millic       : int   milli-Celsius, or None if UNAVAILABLE
            status_str   : str   human-readable backend status
            backend_name : str   backend identifier ("AmdSmu", "None", …)

        Raises
        ------
        DriverNotAvailableError  if the handle is not open.
        OSError                  if DeviceIoControl fails.
        """
        if self._handle is None:
            raise DriverNotAvailableError("Driver handle not open; call open() first.")

        buf       = ctypes.create_string_buffer(_OUTPUT_SIZE)
        returned  = wt.DWORD(0)

        ok = _k32.DeviceIoControl(
            self._handle,
            IOCTL_GET_CPU_TEMP,
            None, 0,
            buf, _OUTPUT_SIZE,
            ctypes.byref(returned),
            None,
        )
        if not ok:
            err = _k32.GetLastError()
            raise OSError(f"DeviceIoControl failed: Win32 error 0x{err:08X}")

        if returned.value < _OUTPUT_SIZE:
            raise OSError(
                f"Short reply: {returned.value} bytes (expected {_OUTPUT_SIZE})")

        millic_raw, status_code, name_bytes = struct.unpack_from(
            _OUTPUT_FMT, buf.raw, 0)

        backend_name = name_bytes.split(b"\x00")[0].decode("ascii", errors="replace")
        status_text  = _STATUS_NAMES.get(status_code, f"unknown({status_code})")

        millic = None if millic_raw == CPUTEMP_UNAVAILABLE else millic_raw
        return millic, status_text, backend_name

    # ── Convenience: read temp in °C (float) or None ──────────────────────────

    def celsius(self):
        """Return temperature as float °C, or None if unavailable."""
        millic, _, _ = self.read()
        return millic / 1000.0 if millic is not None else None


# ── UltraLowPerf collector integration helper ─────────────────────────────────

def collect_cpu_temp_kernel():
    """
    Drop-in replacement for collect_cpu_temp() using the kernel driver.

    Returns the same dict shape:
        { "cpu_temp": <float|None>, "cpu_temp_method": <str> }

    Fails silently (returns None temp) if the driver is not running.
    """
    try:
        with KernelTempDriver() as d:
            millic, status, backend = d.read()
            if millic is not None:
                return {
                    "cpu_temp":        round(millic / 1000.0, 1),
                    "cpu_temp_method": f"KernelDriver/{backend}",
                }
            else:
                return {
                    "cpu_temp":        None,
                    "cpu_temp_method": f"KernelDriver/{backend}/unavailable",
                }
    except DriverNotAvailableError:
        return {"cpu_temp": None, "cpu_temp_method": "KernelDriver/not_loaded"}
    except Exception as exc:
        return {"cpu_temp": None, "cpu_temp_method": f"KernelDriver/error({exc})"}


# ── CLI ───────────────────────────────────────────────────────────────────────

def _main():
    loop = "--loop" in sys.argv

    try:
        driver = KernelTempDriver()
        driver.open()
    except DriverNotAvailableError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    print(f"CpuTempDriver Python client  –  device: {DEVICE_PATH}")
    print("─" * 50)

    try:
        while True:
            millic, status, backend = driver.read()
            print(f"Backend : {backend}")
            print(f"Status  : {status}")
            if millic is None:
                print("Temp    : UNAVAILABLE")
            else:
                print(f"Temp    : {millic / 1000:.3f} °C  ({millic} m°C)")
            if not loop:
                break
            print()
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        driver.close()


if __name__ == "__main__":
    _main()
