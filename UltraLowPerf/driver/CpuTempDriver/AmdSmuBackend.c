/*
 * AmdSmuBackend.c  –  AMD SMU temperature backend (placeholder implementation)
 *
 * Current state:  STUB – Initialize() succeeds and claims the backend, but
 * ReadTempMilliC() returns CPUTEMP_UNAVAILABLE with Status NOT_IMPL.
 *
 * The PCI probing scaffolding is present and demonstrates the correct kernel
 * API calls (HalGetBusDataByOffset / READ_PORT_ULONG / MmMapIoSpace) so a
 * future implementer has a sound starting point.
 *
 * See AmdSmuBackend.h for the full technical background and extension guide.
 */

#include <ntddk.h>
#include <wdm.h>
#include "TempBackend.h"
#include "AmdSmuBackend.h"
#include "ioctl.h"

/* ── Internal state ──────────────────────────────────────────────────────── */
static BOOLEAN g_Initialised = FALSE;

/*
 * _AmdSmu_ProbePci()
 *   Attempts to locate the AMD northbridge PCI device by walking the PCI
 *   bus with HalGetBusDataByOffset.  Returns TRUE if a device at the
 *   expected BDF responds with a plausible Vendor/Device ID.
 *
 *   NOTE: This is probe-only.  No MMIO mapping is performed here.
 */
static BOOLEAN _AmdSmu_ProbePci(void)
{
    PCI_SLOT_NUMBER Slot;
    ULONG           VendorDevice = 0;
    ULONG           BytesRead;

    Slot.u.AsULONG          = 0;
    Slot.u.bits.DeviceNumber   = AMD_SMU_PCI_DEV;
    Slot.u.bits.FunctionNumber = AMD_SMU_PCI_FUNC;

    BytesRead = HalGetBusDataByOffset(
        PCIConfiguration,          /* BusDataType */
        AMD_SMU_PCI_BUS,           /* BusNumber   */
        Slot.u.AsULONG,            /* SlotNumber  */
        &VendorDevice,             /* Buffer      */
        0,                         /* Offset (VendorID at 0) */
        sizeof(VendorDevice));

    if (BytesRead != sizeof(VendorDevice))
        return FALSE;

    /* Vendor must be AMD (0x1022); Device ID varies per SKU – just check vendor. */
    if ((VendorDevice & 0xFFFF) != 0x1022)
        return FALSE;

    KdPrint(("CpuTempDriver: AMD PCI device found at BDF %02X:%02X.%X  ID=0x%08X\n",
             AMD_SMU_PCI_BUS, AMD_SMU_PCI_DEV, AMD_SMU_PCI_FUNC, VendorDevice));

    return TRUE;
}

/* ── Backend vtable callbacks ────────────────────────────────────────────── */

static NTSTATUS _AmdSmu_Initialize(void)
{
    KdPrint(("CpuTempDriver: AmdSmuBackend Initialize()\n"));

    if (!_AmdSmu_ProbePci()) {
        KdPrint(("CpuTempDriver: AMD PCI probe failed – backend will return UNAVAILABLE\n"));
        /*
         * We still return STATUS_SUCCESS so the driver loads and the IOCTL
         * path is reachable; ReadTempMilliC() will report NOT_IMPL safely.
         */
    }

    g_Initialised = TRUE;
    return STATUS_SUCCESS;
}

static NTSTATUS _AmdSmu_ReadTempMilliC(ULONG *OutMilliC)
{
    ASSERT(OutMilliC != NULL);
    *OutMilliC = CPUTEMP_UNAVAILABLE;

    if (!g_Initialised)
        return STATUS_DEVICE_NOT_READY;

    /*
     * ════════════════════════════════════════════════════════════════════════
     * FUTURE IMPLEMENTATION POINT
     * ════════════════════════════════════════════════════════════════════════
     *
     * Steps required to read Tdie/Tctl from the AMD SMU on Zen 4 (AM5):
     *
     * 1. Map the SMU MMIO aperture:
     *      PHYSICAL_ADDRESS pa = { .QuadPart = <SMU_BASE_ADDRESS> };
     *      PVOID pMmio = MmMapIoSpace(pa, <SMU_SIZE>, MmNonCached);
     *
     * 2. Write the mailbox command for Tdie:
     *      WRITE_REGISTER_ULONG((PULONG)((PUCHAR)pMmio + AMD_SMU_REG_ARG0), 0);
     *      WRITE_REGISTER_ULONG((PULONG)((PUCHAR)pMmio + AMD_SMU_REG_MSG),  <CMD_ID>);
     *
     * 3. Poll for response (with timeout):
     *      for (int i = 0; i < 1000; i++) {
     *          resp = READ_REGISTER_ULONG((PULONG)((PUCHAR)pMmio + AMD_SMU_REG_RESP));
     *          if (resp == AMD_SMU_RESP_OK) break;
     *          KeStallExecutionProcessor(100); // 100 µs
     *      }
     *
     * 4. Read temperature argument:
     *      ULONG raw = READ_REGISTER_ULONG((PULONG)((PUCHAR)pMmio + AMD_SMU_REG_ARG0));
     *      // Tdie encoding (Zen 4): (raw >> 21) * 125  →  milli-Celsius
     *      *OutMilliC = ((raw >> 21) & 0x7FF) * 125;
     *
     * 5. Unmap:
     *      MmUnmapIoSpace(pMmio, <SMU_SIZE>);
     *
     * ════════════════════════════════════════════════════════════════════════
     * These offsets and command IDs are NOT confirmed for the Ryzen 7 8700F.
     * Treat the above as a structural guide, not working code.
     * ════════════════════════════════════════════════════════════════════════
     */

    KdPrint(("CpuTempDriver: AmdSmuBackend ReadTempMilliC() – NOT IMPLEMENTED, returning UNAVAILABLE\n"));
    return STATUS_NOT_IMPLEMENTED;
}

static void _AmdSmu_Cleanup(void)
{
    KdPrint(("CpuTempDriver: AmdSmuBackend Cleanup()\n"));
    g_Initialised = FALSE;
}

/* ── Static vtable instance (positional init for C89/MSVC kernel-mode compat) */
static const TEMP_BACKEND_OPS g_AmdSmuOps = {
    "AmdSmu",               /* Name           */
    _AmdSmu_Initialize,     /* Initialize     */
    _AmdSmu_ReadTempMilliC, /* ReadTempMilliC */
    _AmdSmu_Cleanup,        /* Cleanup        */
};

const TEMP_BACKEND_OPS *AmdSmuBackend_GetOps(void)
{
    return &g_AmdSmuOps;
}
