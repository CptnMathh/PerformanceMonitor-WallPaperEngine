/*
 * TempBackend.c  –  Backend dispatcher / registration (kernel-mode)
 *
 * Holds the single "active backend" slot.  All driver code routes reads
 * through TempBackend_ReadTemp(); no direct backend coupling exists.
 */

#include <ntddk.h>
#include "TempBackend.h"
#include "ioctl.h"

/* Single active backend (first one that initialises successfully). */
static const TEMP_BACKEND_OPS *g_ActiveBackend = NULL;

/* ── Public API ──────────────────────────────────────────────────────────── */

NTSTATUS TempBackend_Register(const TEMP_BACKEND_OPS *Ops)
{
    NTSTATUS status;

    if (Ops == NULL || Ops->Initialize == NULL ||
        Ops->ReadTempMilliC == NULL || Ops->Cleanup == NULL) {
        KdPrint(("CpuTempDriver: TempBackend_Register – invalid ops pointer\n"));
        return STATUS_INVALID_PARAMETER;
    }

    /* Only register if no backend is active yet. */
    if (g_ActiveBackend != NULL) {
        KdPrint(("CpuTempDriver: backend '%s' already active, ignoring '%s'\n",
                 g_ActiveBackend->Name, Ops->Name ? Ops->Name : "?"));
        return STATUS_SUCCESS;
    }

    KdPrint(("CpuTempDriver: attempting to initialise backend '%s'\n",
             Ops->Name ? Ops->Name : "?"));

    status = Ops->Initialize();
    if (!NT_SUCCESS(status)) {
        KdPrint(("CpuTempDriver: backend '%s' Initialize() failed: 0x%08X\n",
                 Ops->Name ? Ops->Name : "?", status));
        return status;
    }

    g_ActiveBackend = Ops;
    KdPrint(("CpuTempDriver: backend '%s' registered and active\n",
             g_ActiveBackend->Name));
    return STATUS_SUCCESS;
}

NTSTATUS TempBackend_ReadTemp(ULONG *OutMilliC, ULONG *OutStatus, char OutName[32])
{
    NTSTATUS status;

    /* Always initialise outputs to safe defaults. */
    *OutMilliC = CPUTEMP_UNAVAILABLE;
    *OutStatus = BACKEND_STATUS_NOT_INIT;
    RtlZeroMemory(OutName, 32);
    RtlCopyMemory(OutName, "None", 4);

    if (g_ActiveBackend == NULL)
        return STATUS_DEVICE_NOT_READY;

    /* Copy backend name (bounded, strlen is safe since Name is always a literal). */
    if (g_ActiveBackend->Name) {
        size_t len = strlen(g_ActiveBackend->Name);
        if (len > 31) len = 31;
        RtlCopyMemory(OutName, g_ActiveBackend->Name, len);
        OutName[len] = '\0';
    }

    status = g_ActiveBackend->ReadTempMilliC(OutMilliC);
    if (NT_SUCCESS(status)) {
        *OutStatus = BACKEND_STATUS_OK;
    } else if (status == STATUS_NOT_IMPLEMENTED) {
        *OutStatus = BACKEND_STATUS_NOT_IMPL;
    } else if (status == STATUS_DEVICE_NOT_READY) {
        *OutStatus = BACKEND_STATUS_NOT_INIT;
    } else {
        *OutStatus = BACKEND_STATUS_HW_ERROR;
    }

    /* Never propagate an error NTSTATUS upward – the IOCTL succeeds and the
     * caller inspects Status + TempMilliC to understand the situation.       */
    return STATUS_SUCCESS;
}

void TempBackend_Unload(void)
{
    if (g_ActiveBackend != NULL && g_ActiveBackend->Cleanup != NULL) {
        g_ActiveBackend->Cleanup();
        g_ActiveBackend = NULL;
    }
}
