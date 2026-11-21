/*
 * CpuTempTest.c  –  User-mode console test for CpuTempDriver
 *
 * Build (Developer Command Prompt, no WDK needed):
 *   cl /W4 /WX /nologo CpuTempTest.c /link kernel32.lib
 *
 * Usage:
 *   CpuTempTest.exe             → single read
 *   CpuTempTest.exe --loop      → poll every 1 second until Ctrl+C
 *
 * The driver must be installed and running before launching this app.
 * Run as Administrator if the device SDDL requires it (see .inf).
 */

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ── Shared IOCTL definitions ────────────────────────────────────────────── */
/* Mirror of ioctl.h (no WDK types needed in user-mode). */
#define CPUTEMP_UNAVAILABLE  0xFFFFFFFFul

#define CTL_CODE(DeviceType, Function, Method, Access) \
    ( ((DeviceType) << 16) | ((Access) << 14) | ((Function) << 2) | (Method) )

#define FILE_DEVICE_UNKNOWN   0x00000022
#define METHOD_BUFFERED       0
#define FILE_ANY_ACCESS       0

#define IOCTL_GET_CPU_TEMP \
    CTL_CODE(FILE_DEVICE_UNKNOWN, 0x800, METHOD_BUFFERED, FILE_ANY_ACCESS)

#pragma pack(push, 1)
typedef struct {
    unsigned long  TempMilliC;
    unsigned long  Status;
    char           BackendName[32];
} CPU_TEMP_OUTPUT;
#pragma pack(pop)

/* ── Status strings ──────────────────────────────────────────────────────── */
static const char *status_str(unsigned long s)
{
    switch (s) {
    case 0: return "OK";
    case 1: return "backend not initialised";
    case 2: return "hardware read error";
    case 3: return "not yet implemented";
    default: return "unknown";
    }
}

/* ── Single IOCTL round-trip ─────────────────────────────────────────────── */
static int query_temp(HANDLE hDev)
{
    CPU_TEMP_OUTPUT out    = {0};
    DWORD           bytes  = 0;
    BOOL            ok;

    ok = DeviceIoControl(
        hDev,
        IOCTL_GET_CPU_TEMP,
        NULL,  0,                           /* no input buffer */
        &out,  sizeof(CPU_TEMP_OUTPUT),     /* output buffer   */
        &bytes,
        NULL);

    if (!ok) {
        fprintf(stderr, "[ERROR] DeviceIoControl failed: 0x%08lX\n",
                GetLastError());
        return 1;
    }

    if (bytes < sizeof(CPU_TEMP_OUTPUT)) {
        fprintf(stderr, "[ERROR] short reply: %lu bytes (expected %zu)\n",
                bytes, sizeof(CPU_TEMP_OUTPUT));
        return 1;
    }

    printf("Backend : %s\n", out.BackendName[0] ? out.BackendName : "(none)");
    printf("Status  : %s (%lu)\n", status_str(out.Status), out.Status);

    if (out.TempMilliC == CPUTEMP_UNAVAILABLE) {
        printf("Temp    : UNAVAILABLE\n");
    } else {
        double tempC = (double)out.TempMilliC / 1000.0;
        printf("Temp    : %.3f °C  (%lu m°C)\n", tempC, out.TempMilliC);
    }

    return 0;
}

/* ── Entry point ─────────────────────────────────────────────────────────── */
int main(int argc, char *argv[])
{
    HANDLE hDev;
    int    loop = 0;
    int    rc   = 0;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--loop") == 0) loop = 1;
    }

    /* Open the device exposed by CpuTempDriver. */
    hDev = CreateFileA(
        "\\\\.\\CpuTemp",
        GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        NULL,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        NULL);

    if (hDev == INVALID_HANDLE_VALUE) {
        DWORD err = GetLastError();
        fprintf(stderr, "[ERROR] Cannot open \\\\.\\CpuTemp  (error 0x%08lX)\n", err);
        if (err == ERROR_FILE_NOT_FOUND || err == ERROR_PATH_NOT_FOUND)
            fprintf(stderr, "        Make sure CpuTempDriver is installed and running.\n");
        else if (err == ERROR_ACCESS_DENIED)
            fprintf(stderr, "        Try running as Administrator.\n");
        return 1;
    }

    printf("CpuTempTest  –  device opened successfully\n");
    printf("─────────────────────────────────────────\n");

    if (loop) {
        printf("Polling every 1 s  (Ctrl+C to stop)\n\n");
        while (1) {
            rc = query_temp(hDev);
            printf("\n");
            Sleep(1000);
        }
    } else {
        rc = query_temp(hDev);
    }

    CloseHandle(hDev);
    return rc;
}
