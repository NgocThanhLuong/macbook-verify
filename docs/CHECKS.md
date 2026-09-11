# What MacBook Verify can and cannot prove

MacBook Verify is intentionally conservative. A software report is evidence about the **current state visible to macOS**, not a forensic guarantee that the machine has never been repaired.

## Strong automatic signals

### Identity consistency

The tool compares the serial reported by `system_profiler` with `IOPlatformSerialNumber` from IOKit, and compares the model identifier against `sysctl hw.model`. A mismatch is treated as a serious finding.

### Battery

The report captures Apple's normal battery fields plus useful controller data when available:

- cycle count
- condition
- maximum capacity
- battery serial
- design-cycle reference
- `PermanentFailureStatus`
- `BatteryCellDisconnectCount`
- raw design/max capacity values

A non-zero battery disconnect counter can be useful evidence that the battery/controller has experienced a disconnect, but it is **not proof by itself that the battery was replaced**.

### Display

The tool checks how macOS identifies the built-in display, its resolution, online status, and internal connection type. A normal result does not prove that the panel has never been replaced with another genuine/compatible assembly.

### SSD

The tool captures the internal NVMe/SSD identity, SMART status, TRIM, and detachable/removable flags. On Apple Silicon, an internal Apple SSD identity is expected. Board-level storage repair cannot be ruled out from this check alone.

### MDM / DEP

`profiles status -type enrollment` is collected because a used Mac that remains managed by a company or school can become unusable or re-enroll after erase. Any positive enrollment indication should be resolved with the seller/organization before purchase.

### Security

SIP, FileVault, Activation Lock, and available diagnostics are reported. These are important ownership/security signals, but most are not direct evidence of hardware replacement.

## Parts & Service history

Newer macOS versions may show a **Parts & Service** section in System Settings → General → About. Apple does not expose the same information consistently through a stable public command-line interface on every macOS build.

MacBook Verify dynamically checks whether a Repair/Parts `system_profiler` data type exists. If it does not, the report explicitly tells the user to inspect the Settings UI manually.

Do not interpret “no CLI repair data” as “never repaired.”

## Checks that remain physical/manual

- serial printed/etched on the bottom case versus system serial
- screw-head wear and pry marks
- chassis gaps, dents, replaced bottom case
- liquid-contact evidence and corrosion
- dead/stuck pixels and display uniformity
- keyboard, Touch ID, trackpad, ports, camera, microphone, speakers
- Apple Diagnostics boot environment

The generated HTML report includes a bottom-case serial comparator and fullscreen pixel-test colors to make these manual checks faster.
