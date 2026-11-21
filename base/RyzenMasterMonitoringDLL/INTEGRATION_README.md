# AMD Ryzen Master SDK Integration

## Overview

This document describes the integration of the AMD Ryzen Master Monitoring SDK (version 3.1.1.5478) into StrangeCat Monitor.

## What is AMD Ryzen Master SDK?

The AMD Ryzen Master SDK provides direct access to AMD Ryzen CPU metrics including:
- **Temperature**: CPU package temperature
- **Power**: PPT (Package Power Tracking), EDC (Electrical Design Current), TDC (Thermal Design Current)
- **Voltage**: Core voltages, SoC voltage
- **Clock speeds**: Peak speed, FCLK, memory clocks
- **Advanced metrics**: Core count, cache sizes, memory timings, etc.

## Requirements

### Hardware
- AMD Ryzen CPU (supported by Ryzen Master SDK)
- See `Monitor.cpp` in the SDK for the list of supported CPU IDs

### Software
- Windows 10/11
- Administrator privileges (required for driver access)
- AMD Ryzen Master Driver (auto-installed by SDK if not present)

### Files Needed
To enable AMD monitoring, you need:
1. **AMDRyzenMasterMonitoringDLL.dll** - The main monitoring DLL
2. **Driver files** (auto-installed by SDK if in same directory):
   - AMDRyzenMasterDriver.inf
   - AMDRyzenMasterDriver.cat
   - AMDRyzenMasterDriver.sys

## Integration Details

### Files Added/Modified

#### New Files
- `base/ryzen_master.py` - Python wrapper for the AMD Ryzen Master DLL
  - Defines ctypes structures matching the DLL
  - Provides high-level functions for metric collection
  - Handles initialization, caching, and error handling

#### Modified Files
- `base/collector.py` - Added AMD metric collection functions
  - `collect_ryzen_quick()` - Fast metrics (temp, PPT, EDC, TDC, voltages)
  - `collect_ryzen_full()` - Comprehensive metrics (all available data)
  - Integrated into the DataCollector loop with appropriate refresh rates

- `base/config.py` - Added configuration options
  - New refresh rates: `RATE_RYZEN_QUICK = 2.0s`, `RATE_RYZEN_FULL = 10.0s`
  - New default settings: `show_amd_temp`, `show_amd_ppt`, `show_amd_edc`, `show_amd_tdc`
  - Updated `rate_for()` function to handle AMD metrics
  - Added translations for AMD metric options

- `base/metrics.py` - Added AMD metrics to the UI
  - New metric keys: `amd_temp`, `amd_ppt`, `amd_edc`, `amd_tdc`
  - Proper formatting for units (°C, W, A)
  - Color coding and thresholds

- `build.bat` - Updated build process
  - Copies AMDRyzenMasterMonitoringDLL.dll if present
  - Includes ryzen_master.py in the build
  - Conditionally includes the DLL in the PyInstaller package

### Metrics Available

#### Quick Metrics (refreshed every 2 seconds)
- `amd_temp` - CPU temperature (°C)
- `amd_ppt` - Package Power Tracking (W)
- `amd_edc` - Electrical Design Current for VDD (A)
- `amd_tdc` - Thermal Design Current for VDD (A)
- `amd_peak_voltage` - Peak core voltage (V)
- `amd_avg_voltage` - Average core voltage (V)

#### Full Metrics (refreshed every 10 seconds)
All quick metrics plus:
- `amd_ppt_limit` - PPT limit (W)
- `amd_edc_limit` - EDC limit for VDD (A)
- `amd_tdc_limit` - TDC limit for VDD (A)
- `amd_soc_edc` - EDC for SoC (A)
- `amd_soc_edc_limit` - EDC limit for SoC (A)
- `amd_soc_tdc` - TDC for SoC (A)
- `amd_soc_tdc_limit` - TDC limit for SoC (A)
- `amd_vdd_power` - VDDCR_VDD power (W)
- `amd_soc_power` - VDDCR_SOC power (W)
- `amd_peak_speed` - Peak clock speed (MHz)
- `amd_soc_voltage` - SoC voltage (V)
- `amd_core_count` - Number of cores
- `amd_core_parked` - Number of parked cores
- `amd_l1_dcache` - L1 data cache size (KB)
- `amd_l1_icache` - L1 instruction cache size (KB)
- `amd_l3_cache` - L3 cache size (KB)
- `amd_fclk` - FCLK frequency (MHz)
- `amd_cclk_fmax` - CCLK Fmax (MHz)
- `amd_mode` - Performance mode (Manual/PBO/AutoOC/Reserved)
- `amd_vddio` - VDDIO voltage (mV)
- `amd_mem_clock` - Memory clock (MHz)
- `amd_tcl`, `amd_tcdrd`, `amd_tras`, `amd_trp` - Memory timings

## Usage

### Enabling AMD Monitoring

1. **Obtain the DLL**:
   - Compile the SDK from source in `base/RyzenMasterMonitoringDLL/`
   - Or obtain the pre-compiled `AMDRyzenMasterMonitoringDLL.dll`
   - Place it in the `base/` directory

2. **Run as Administrator**:
   - The SDK requires admin privileges to access the CPU driver
   - Right-click the application and select "Run as administrator"

3. **Configure in Settings**:
   - Open StrangeCat Monitor
   - Go to Settings → Metrics
   - Enable/disable AMD metrics as desired:
     - Show AMD CPU TEMP
     - Show AMD PPT
     - Show AMD EDC
     - Show AMD TDC

### Building with AMD Support

The build script (`build.bat`) automatically detects if the DLL is present:
- If `AMDRyzenMasterMonitoringDLL.dll` exists in `base/`, it will be included in the build
- If not found, AMD monitoring will be disabled (the app will still work without it)

To build:
```batch
build.bat
```

### Fallback Behavior

If the AMD SDK is not available:
- The wrapper gracefully handles the missing DLL
- `_HAS_RYZEN_MASTER` is set to `False`
- AMD metrics return empty values
- The UI shows "—" for AMD metrics
- Other monitoring (CPU, RAM, GPU, etc.) continues normally

## Architecture

### Threading and Safety

The SDK documentation specifies:
- **Do not query in parallel from different threads**
- **Use a Mutex or sync point**
- **CPUUsage() requires 100ms delta - don't call more frequently than 125ms**

Our implementation:
- Uses a global lock (`_ryzen_lock`) for all AMD SDK calls
- Implements caching to avoid excessive API calls
- Quick metrics cached for 2 seconds
- Full metrics cached for 10 seconds
- CPU usage rate-limited to 125ms minimum

### Data Flow

```
ryzen_master.py (wrapper)
    ↓ (ctypes)
AMDRyzenMasterMonitoringDLL.dll
    ↓ (driver communication)
AMD Ryzen Master Driver
    ↓ (hardware access)
AMD Ryzen CPU
```

### Integration Points

1. **Initialization** (`check_ryzen_available()`):
   - Checks if DLL exists
   - Verifies admin privileges
   - Checks for authentic AMD CPU
   - Verifies CPU is supported
   - Checks driver installation
   - Calls `PlatformInit()`

2. **Collection** (in DataCollector loop):
   - `collect_ryzen_quick()` - Called every 2 seconds
   - `collect_ryzen_full()` - Called every 10 seconds
   - Results merged into `_data` dict
   - History updated for graphing

3. **Display** (via metrics.py):
   - Metrics added to sidebar if enabled
   - Values formatted with appropriate units
   - Color coding based on thresholds

## Troubleshooting

### AMD metrics not showing

1. **Check if DLL exists**:
   - Verify `AMDRyzenMasterMonitoringDLL.dll` is in the `base/` directory
   - For builds, check if it was included by PyInstaller

2. **Check admin privileges**:
   - Run the application as administrator
   - The SDK requires admin access to the CPU driver

3. **Check CPU compatibility**:
   - Verify you have an AMD Ryzen CPU
   - Check if your CPU ID is in the supported list (see `Monitor.cpp`)

4. **Check driver installation**:
   - The SDK should auto-install the driver if files are present
   - Check Windows Device Manager for "AMDRyzenMasterDriverV16"

### Build issues

If the build fails to include the DLL:
1. Ensure the DLL is in `base/AMDRyzenMasterMonitoringDLL.dll`
2. Check the build output for error messages
3. Verify the DLL is not locked by another process

### Performance issues

If the application becomes slow:
1. AMD SDK calls are already rate-limited
2. Check if other monitoring tools are running (Ryzen Master, HWiNFO, etc.)
3. The SDK may conflict with other tools accessing the CPU driver

## Limitations

- **Windows only**: The SDK is Windows-specific
- **AMD only**: Only works with AMD Ryzen CPUs
- **Admin required**: Must run as administrator
- **Single instance**: Cannot run multiple instances with AMD monitoring enabled
- **Driver conflicts**: May conflict with other tools using the Ryzen Master driver

## Future Enhancements

Potential improvements:
- Add more AMD metrics to the UI (core parking, cache info, memory timings)
- Add AMD-specific graph views
- Implement AMD PBO tuning controls (read-only initially)
- Add per-core temperature monitoring (if available)
- Support for AMD GPU metrics via ROCm/ADL

## References

- AMD Ryzen Master SDK: `base/RyzenMasterMonitoringDLL/`
- SDK README: `base/RyzenMasterMonitoringDLL/README.md`
- Sample app: `base/RyzenMasterMonitoringDLL/AMDRyzenMasterMonitoringSampleApp.vcxproj`

## License

The AMD Ryzen Master SDK is copyrighted by Advanced Micro Devices, Inc.
See the SDK files for specific licensing terms.
