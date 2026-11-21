/*
 * TempBackend.h  –  Abstract temperature backend interface (kernel-mode)
 *
 * Every backend (AMD SMU, simulated, future Intel, …) must fill one
 * TEMP_BACKEND_OPS structure and register it via TempBackend_Register().
 *
 * The driver calls only through this vtable – it never touches backend
 * internals directly, which keeps the coupling at zero.
 *
 *  ┌──────────────────────────────────────────────────────────────┐
 *  │              CpuTempDriver  (KMDF core)                      │
 *  │   EvtIoDeviceControl → TempBackend_ReadTemp()                │
 *  │                              │                               │
 *  │               TEMP_BACKEND_OPS vtable                        │
 *  │                    ┌─────────┴──────────┐                   │
 *  │            AmdSmuBackend          SimulatedBackend           │
 *  └──────────────────────────────────────────────────────────────┘
 */

#pragma once
#include <ntddk.h>

/* ── Status codes (backend-internal) ───────────────────────────────────────*/
#define BACKEND_STATUS_OK            0ul
#define BACKEND_STATUS_NOT_INIT      1ul
#define BACKEND_STATUS_HW_ERROR      2ul
#define BACKEND_STATUS_NOT_IMPL      3ul

/* ── Vtable ─────────────────────────────────────────────────────────────── */
typedef struct _TEMP_BACKEND_OPS {

    /* Human-readable name, e.g. "AmdSmu" (max 31 chars + NUL). */
    const char *Name;

    /*
     * Initialize()
     *   Called once when the driver is loaded.
     *   Return STATUS_SUCCESS or an NTSTATUS error.
     *   On failure the driver falls back to the next registered backend.
     */
    NTSTATUS (*Initialize)(void);

    /*
     * ReadTempMilliC()
     *   Read the current CPU temperature.
     *   On success  : writes milli-Celsius to *OutMilliC, returns STATUS_SUCCESS.
     *   On failure  : *OutMilliC = CPUTEMP_UNAVAILABLE, returns error NTSTATUS.
     *
     *   IRQL must be <= PASSIVE_LEVEL when this is called.
     */
    NTSTATUS (*ReadTempMilliC)(ULONG *OutMilliC);

    /*
     * Cleanup()
     *   Called when the driver unloads.  Release any resources claimed in
     *   Initialize().  Must not fail silently.
     */
    void (*Cleanup)(void);

} TEMP_BACKEND_OPS;

/* ── Registration API (called from each backend's init code) ────────────── */

/*
 * TempBackend_Register()
 *   Register a backend.  Only the first successfully-initialised backend
 *   is used; subsequent ones are ignored.
 *   Must be called at IRQL == PASSIVE_LEVEL (e.g. from DriverEntry).
 */
NTSTATUS TempBackend_Register(const TEMP_BACKEND_OPS *Ops);

/*
 * TempBackend_ReadTemp()
 *   Dispatch a read to the active backend.
 *   If no backend is registered, fills *Out with CPUTEMP_UNAVAILABLE and
 *   Status = BACKEND_STATUS_NOT_INIT.  Never crashes even when unimplemented.
 */
NTSTATUS TempBackend_ReadTemp(ULONG *OutMilliC, ULONG *OutStatus, char OutName[32]);

/*
 * TempBackend_Unload()
 *   Called from DriverUnload to let the active backend clean up.
 */
void TempBackend_Unload(void);
