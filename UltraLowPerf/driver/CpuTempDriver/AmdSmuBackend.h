/*
 * AmdSmuBackend.h  –  AMD System Management Unit temperature backend (header)
 *
 * Background on AMD SMU temperature access
 * ────────────────────────────────────────
 * On Zen 3 / Zen 4 (AM4 / AM5) the CPU die temperature (Tdie / Tctl) is
 * managed by the System Management Unit – a dedicated ARM Cortex-M firmware
 * core embedded in the SoC.  The SMU exposes its sensor mailbox through PCI
 * configuration space of the internal "data fabric" function (DF F3).
 *
 * There is NO official public API, ACPI method, or WMI object for this.
 * Projects like LibreHardwareMonitor, HWiNFO, and ryzen_smu (Linux) obtain
 * the temperature by reverse-engineering the mailbox protocol.
 *
 * This header defines the INTERFACE for such a backend.  The implementation
 * (.c file) is a PLACEHOLDER: it initialises the PCI lookup machinery but
 * performs no actual mailbox communication.  Real implementation requires
 * knowledge of the undocumented SMU mailbox commands (e.g. rsmu_cmd table).
 *
 * Extension guide
 * ───────────────
 * 1. Locate the AMD "SMU" PCI device:
 *      Bus=0, Dev=0, Func=0  (root bridge, varies per SoC revision)
 *    Specifically DF Func 3 on the northbridge for Zen 3/4:
 *      VendorID = 0x1022, DeviceID = 0x14B5 (example, check ACPI/PCI IDs)
 *
 * 2. Send mailbox commands via MMIO/PCI-cfg registers:
 *      SMU_ADDR_MSG    – write command ID
 *      SMU_ADDR_RESP   – poll for OK (0x01)
 *      SMU_ADDR_ARG0   – read/write argument
 *
 * 3. Command for Tdie (example from ryzen_smu, NOT guaranteed stable):
 *      Zen4: MP1_MSG_GetTempDie (exact value: platform-specific)
 *
 * Do NOT hard-code register offsets without verification on target hardware.
 */

#pragma once
#include "TempBackend.h"

/*
 * AmdSmuBackend_GetOps()
 *   Returns a pointer to the statically-allocated TEMP_BACKEND_OPS for the
 *   AMD SMU backend.  Pass this to TempBackend_Register() in DriverEntry.
 */
const TEMP_BACKEND_OPS *AmdSmuBackend_GetOps(void);

/* ── PCI location constants for Zen 4 (AM5) northbridge ────────────────────
 *
 * These are the PCI BDF (Bus/Device/Function) coordinates that typically
 * hold the SMU mailbox on Zen 4.  Treat as approximate – validate against
 * ACPI tables (_HID, _CID) before using in production.
 *
 * AMD publishes some PCI IDs in the IOMMU specification; SMU mailbox
 * register offsets are NOT publicly documented.
 */
#define AMD_SMU_PCI_BUS       0x00
#define AMD_SMU_PCI_DEV       0x00
#define AMD_SMU_PCI_FUNC      0x00   /* root / NB function – refine per SKU */

/*
 * Placeholder mailbox register offsets (not functional – illustrative only).
 * Real values must be obtained from reverse-engineering or vendor NDA.
 */
#define AMD_SMU_REG_MSG       0x00   /* message register offset */
#define AMD_SMU_REG_RESP      0x04   /* response register offset */
#define AMD_SMU_REG_ARG0      0x08   /* argument 0 register offset */

#define AMD_SMU_RESP_OK       0x01   /* SMU response: command accepted */
#define AMD_SMU_RESP_TIMEOUT  0x00   /* SMU response: not ready */
