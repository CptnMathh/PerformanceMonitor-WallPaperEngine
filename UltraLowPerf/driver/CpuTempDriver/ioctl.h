/*
 * ioctl.h  –  Shared IOCTL definitions for CpuTempDriver
 *
 * Included by BOTH the kernel-mode driver AND any user-mode application.
 * Keep this header dependency-free so it compiles with Win32 SDK alone.
 *
 * Device path (user-mode)  :  \\.\CpuTemp
 * Device path (kernel)     :  \Device\CpuTemp
 * Symbolic link            :  \DosDevices\CpuTemp
 */

#pragma once

/* ── IOCTL code ─────────────────────────────────────────────────────────────
 *
 * CTL_CODE(DeviceType, Function, Method, Access)
 *
 *   FILE_DEVICE_UNKNOWN  = 0x22
 *   Function             = 0x800  (first app-defined slot)
 *   METHOD_BUFFERED      = 0       – kernel copies in/out via system buffer
 *   FILE_ANY_ACCESS      = 0       – no special privilege needed beyond OPEN
 */
#define CPUTEMP_DEVICE_TYPE  0x00000022ul   /* FILE_DEVICE_UNKNOWN */
#define CPUTEMP_IOCTL_FUNC   0x800ul

/* Self-contained fallback defines so this header compiles standalone.
 * ntddk.h / winioctl.h define the same values; the guards prevent redefinition. */
#ifndef METHOD_BUFFERED
#define METHOD_BUFFERED  0
#endif
#ifndef FILE_ANY_ACCESS
#define FILE_ANY_ACCESS  0
#endif

#define IOCTL_GET_CPU_TEMP \
    ( ((CPUTEMP_DEVICE_TYPE) << 16) | \
      ((FILE_ANY_ACCESS)     << 14) | \
      ((CPUTEMP_IOCTL_FUNC)  <<  2) | \
      (METHOD_BUFFERED) )

/* ── Output structure returned by IOCTL_GET_CPU_TEMP ────────────────────────
 *
 * TempMilliC :  Temperature in milli-Celsius (divide by 1000 for °C).
 *               CPUTEMP_UNAVAILABLE when the backend cannot read the sensor.
 *
 * Status     :  0   = success
 *               1   = backend not initialised
 *               2   = hardware read error
 *               3   = feature not yet implemented
 *
 * BackendName:  Short ASCII string naming the active backend,
 *               e.g. "AmdSmu", "Simulated", "None".
 */
#define CPUTEMP_UNAVAILABLE  0xFFFFFFFFul

#pragma pack(push, 1)
typedef struct _CPU_TEMP_OUTPUT {
    unsigned long  TempMilliC;      /* milli-Celsius  or CPUTEMP_UNAVAILABLE */
    unsigned long  Status;          /* see status codes above                  */
    char           BackendName[32]; /* NUL-terminated ASCII backend identifier */
} CPU_TEMP_OUTPUT;
#pragma pack(pop)

#define CPU_TEMP_OUTPUT_SIZE  sizeof(CPU_TEMP_OUTPUT)
