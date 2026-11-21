/*
 * CpuTempDriver.c  –  KMDF kernel-mode driver entry point
 *
 * Exposes \Device\CpuTemp  →  \DosDevices\CpuTemp  →  \\.\CpuTemp
 *
 * IOCTL surface:
 *   IOCTL_GET_CPU_TEMP   →  fills CPU_TEMP_OUTPUT, always returns STATUS_SUCCESS
 *
 * Backend chain (first to init wins):
 *   AmdSmuBackend   (placeholder, returns UNAVAILABLE until implemented)
 *
 * Build: Visual Studio 2022 + WDK 10.0.26100  (Windows 11 24H2 target)
 *   Configuration: Debug | x64   (switch to Release for production)
 */

#include <ntddk.h>
#include <wdf.h>
#include <wdmsec.h>     /* SDDL_DEVOBJ_SYS_ALL_ADM_RWX_WORLD_R */

#include "ioctl.h"
#include "TempBackend.h"
#include "AmdSmuBackend.h"

/* ── Driver strings ──────────────────────────────────────────────────────── */
#define DRIVER_TAG          'tpCT'       /* pool allocation tag "TCpt" */
#define DEVICE_NAME         L"\\Device\\CpuTemp"
#define DOS_DEVICE_NAME     L"\\DosDevices\\CpuTemp"

/* ── Forward declarations ────────────────────────────────────────────────── */
DRIVER_INITIALIZE            DriverEntry;
EVT_WDF_DRIVER_DEVICE_ADD    EvtDeviceAdd;
EVT_WDF_IO_QUEUE_IO_DEVICE_CONTROL  EvtIoDeviceControl;
EVT_WDF_OBJECT_CONTEXT_CLEANUP      EvtDriverCleanup;

/* ── Driver cleanup (called by WDF when the driver object is destroyed) ────
 * This is the correct place to release global resources like TempBackend.   */
VOID EvtDriverCleanup(_In_ WDFOBJECT Driver)
{
    UNREFERENCED_PARAMETER(Driver);
    KdPrint(("CpuTempDriver: EvtDriverCleanup – releasing backends\n"));
    TempBackend_Unload();
}

/* ══════════════════════════════════════════════════════════════════════════
 * DriverEntry
 *   Standard WDF entry point.  Registers EvtDeviceAdd and triggers the
 *   PnP manager to call it immediately for the root-enumerated device.
 * ══════════════════════════════════════════════════════════════════════════*/
NTSTATUS DriverEntry(
    _In_ PDRIVER_OBJECT  DriverObject,
    _In_ PUNICODE_STRING RegistryPath)
{
    WDF_DRIVER_CONFIG    config;
    WDF_OBJECT_ATTRIBUTES driverAttrs;
    NTSTATUS             status;

    KdPrint(("CpuTempDriver: DriverEntry\n"));

    WDF_DRIVER_CONFIG_INIT(&config, EvtDeviceAdd);

    /* Attach cleanup callback to the WDFDRIVER object so TempBackend_Unload()
     * is called when WDF destroys the driver object during unload.           */
    WDF_OBJECT_ATTRIBUTES_INIT(&driverAttrs);
    driverAttrs.EvtCleanupCallback = EvtDriverCleanup;

    status = WdfDriverCreate(
        DriverObject,
        RegistryPath,
        &driverAttrs,
        &config,
        WDF_NO_HANDLE);

    if (!NT_SUCCESS(status)) {
        KdPrint(("CpuTempDriver: WdfDriverCreate failed 0x%08X\n", status));
        return status;
    }

    /* ── Register temperature backend(s) ───────────────────────────────────
     * Add more backends here in priority order; TempBackend_Register ignores
     * any backend after the first successful one.                            */
    TempBackend_Register(AmdSmuBackend_GetOps());

    KdPrint(("CpuTempDriver: DriverEntry complete\n"));
    return STATUS_SUCCESS;
}

/* ══════════════════════════════════════════════════════════════════════════
 * EvtDeviceAdd
 *   Creates the device object and its default I/O queue.
 * ══════════════════════════════════════════════════════════════════════════*/
NTSTATUS EvtDeviceAdd(
    _In_    WDFDRIVER       Driver,
    _Inout_ PWDFDEVICE_INIT DeviceInit)
{
    NTSTATUS                    status;
    WDFDEVICE                   device;
    WDFQUEUE                    queue;
    WDF_IO_QUEUE_CONFIG         queueCfg;
    UNICODE_STRING              devName, dosName;

    UNREFERENCED_PARAMETER(Driver);

    KdPrint(("CpuTempDriver: EvtDeviceAdd\n"));

    /* ── Assign the kernel device name ─────────────────────────────────── */
    RtlInitUnicodeString(&devName, DEVICE_NAME);
    status = WdfDeviceInitAssignName(DeviceInit, &devName);
    if (!NT_SUCCESS(status)) {
        KdPrint(("CpuTempDriver: WdfDeviceInitAssignName failed 0x%08X\n", status));
        return status;
    }

    /* ── Set a permissive SDDL so user-mode apps can open without elevation.
     *    In production, restrict to "O:BAG:BAD:P(A;;GA;;;SY)(A;;GA;;;BA)"
     *    or similar to require Administrator.                                */
    status = WdfDeviceInitAssignSDDLString(
        DeviceInit,
        &SDDL_DEVOBJ_SYS_ALL_ADM_RWX_WORLD_R);
    if (!NT_SUCCESS(status)) {
        KdPrint(("CpuTempDriver: WdfDeviceInitAssignSDDLString failed 0x%08X\n", status));
        return status;
    }

    /* ── Create the device ─────────────────────────────────────────────── */
    status = WdfDeviceCreate(
        &DeviceInit,
        WDF_NO_OBJECT_ATTRIBUTES,
        &device);
    if (!NT_SUCCESS(status)) {
        KdPrint(("CpuTempDriver: WdfDeviceCreate failed 0x%08X\n", status));
        return status;
    }

    /* ── Create the DOS symbolic link (\\.\CpuTemp) ────────────────────── */
    RtlInitUnicodeString(&dosName, DOS_DEVICE_NAME);
    status = WdfDeviceCreateSymbolicLink(device, &dosName);
    if (!NT_SUCCESS(status)) {
        KdPrint(("CpuTempDriver: WdfDeviceCreateSymbolicLink failed 0x%08X\n", status));
        return status;
    }

    /* ── Create the default I/O queue (sequential) ──────────────────────── */
    WDF_IO_QUEUE_CONFIG_INIT_DEFAULT_QUEUE(&queueCfg, WdfIoQueueDispatchSequential);
    queueCfg.EvtIoDeviceControl = EvtIoDeviceControl;

    status = WdfIoQueueCreate(
        device,
        &queueCfg,
        WDF_NO_OBJECT_ATTRIBUTES,
        &queue);
    if (!NT_SUCCESS(status)) {
        KdPrint(("CpuTempDriver: WdfIoQueueCreate failed 0x%08X\n", status));
        return status;
    }

    KdPrint(("CpuTempDriver: device created successfully\n"));
    return STATUS_SUCCESS;
}

/* ══════════════════════════════════════════════════════════════════════════
 * EvtIoDeviceControl
 *   Handles all IOCTL requests.  Currently supports only IOCTL_GET_CPU_TEMP.
 *   Returns STATUS_SUCCESS in all paths; temperature validity is communicated
 *   through the output buffer (CPU_TEMP_OUTPUT.Status / .TempMilliC).
 * ══════════════════════════════════════════════════════════════════════════*/
VOID EvtIoDeviceControl(
    _In_ WDFQUEUE   Queue,
    _In_ WDFREQUEST Request,
    _In_ size_t     OutputBufferLength,
    _In_ size_t     InputBufferLength,
    _In_ ULONG      IoControlCode)
{
    NTSTATUS        status;
    CPU_TEMP_OUTPUT output;
    PVOID           pOutBuf  = NULL;
    size_t          written  = 0;

    UNREFERENCED_PARAMETER(Queue);
    UNREFERENCED_PARAMETER(InputBufferLength);

    KdPrint(("CpuTempDriver: IOCTL 0x%08X received\n", IoControlCode));

    switch (IoControlCode) {

    /* ── IOCTL_GET_CPU_TEMP ──────────────────────────────────────────────── */
    case IOCTL_GET_CPU_TEMP:

        if (OutputBufferLength < sizeof(CPU_TEMP_OUTPUT)) {
            KdPrint(("CpuTempDriver: output buffer too small (%Iu < %Iu)\n",
                     OutputBufferLength, sizeof(CPU_TEMP_OUTPUT)));
            WdfRequestComplete(Request, STATUS_BUFFER_TOO_SMALL);
            return;
        }

        /* Route through the backend dispatcher – never raises exceptions. */
        RtlZeroMemory(&output, sizeof(output));
        TempBackend_ReadTemp(
            &output.TempMilliC,
            &output.Status,
             output.BackendName);

        /* Copy output into the METHOD_BUFFERED system buffer. */
        status = WdfRequestRetrieveOutputBuffer(
            Request, sizeof(CPU_TEMP_OUTPUT), &pOutBuf, NULL);
        if (!NT_SUCCESS(status)) {
            KdPrint(("CpuTempDriver: WdfRequestRetrieveOutputBuffer failed 0x%08X\n", status));
            WdfRequestComplete(Request, status);
            return;
        }

        RtlCopyMemory(pOutBuf, &output, sizeof(CPU_TEMP_OUTPUT));
        written = sizeof(CPU_TEMP_OUTPUT);

        KdPrint(("CpuTempDriver: IOCTL_GET_CPU_TEMP done – TempMilliC=%lu Status=%lu Backend=%s\n",
                 output.TempMilliC, output.Status, output.BackendName));

        WdfRequestCompleteWithInformation(Request, STATUS_SUCCESS, written);
        break;

    /* ── Unknown IOCTL ───────────────────────────────────────────────────── */
    default:
        KdPrint(("CpuTempDriver: unknown IOCTL 0x%08X\n", IoControlCode));
        WdfRequestComplete(Request, STATUS_INVALID_DEVICE_REQUEST);
        break;
    }
}
