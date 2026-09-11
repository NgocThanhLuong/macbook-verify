# MacBook Verify

**MacBook Verify** is a one-click, offline macOS hardware verification tool for checking a used MacBook before buying, selling, or servicing it.

> The tool detects software-visible health, identity, security, storage, battery, display, MDM, and consistency signals. It **cannot prove 100% that a Mac has never been opened or repaired**; physical inspection and Apple Parts & Service history may still be required.

## One-click usage

### Option A — Run directly

Double-click:

```text
MacBookVerify.command
```

The tool collects only targeted hardware/system information, creates a timestamped report folder on the Desktop, and automatically opens `report.html`.

### Option B — Install as a Mac app

Double-click:

```text
Install.command
```

This creates:

```text
~/Applications/MacBook Verify.app
```

After that, open **MacBook Verify** like a normal application whenever you want to check a Mac.

## What it checks

- Mac model, model identifier, chip, CPU/GPU core count, RAM
- System serial consistency between `system_profiler` and IOKit
- Battery health, cycle count, maximum capacity, battery serial, permanent failure flags
- Built-in display type, resolution, online/internal connection state
- Internal Apple SSD/NVMe model, TRIM, SMART status, removable/detachable flags
- SIP, FileVault, boot/security information when exposed by macOS
- MDM / Automated Device Enrollment status — important for second-hand Macs
- Apple hardware diagnostics information exposed by macOS
- Repair / Parts & Service-related data types when the current macOS build exposes them to `system_profiler`
- A manual checklist for items software cannot prove: bottom-case serial, screw marks, liquid damage, dead pixels, keyboard/trackpad/ports, and Apple Diagnostics boot test

## Output

A run creates a folder similar to:

```text
~/Desktop/MacBook-Verify-20260911-104500/
├── report.html
├── summary.txt
├── manifest.sha256
└── raw/
    ├── hardware.txt
    ├── platform-ioreg.txt
    ├── battery-system.txt
    ├── battery-raw.txt
    ├── display.txt
    ├── storage.txt
    ├── security.txt
    ├── mdm.txt
    ├── diagnostics.txt
    └── repair-history.txt   # when available
```

## Status meaning

- **PASS** — value is healthy/consistent for the check being performed.
- **WARN** — value deserves attention or manual verification.
- **FAIL** — a concrete inconsistency or unhealthy state was detected.
- **INFO** — useful information that cannot be judged automatically.

The final verdict is deliberately conservative. MacBook Verify does **not** produce a fake “100% original” score.

## Privacy

MacBook Verify runs locally and does not upload data anywhere. Reports can contain device serial numbers and other hardware identifiers, so redact them before posting a report publicly.

## Requirements

- macOS
- `/bin/zsh`
- Standard Apple command-line utilities (`system_profiler`, `ioreg`, `csrutil`, `profiles`, etc.)
- No Homebrew, Python, Node.js, or third-party dependencies

## Command-line options

```bash
/bin/zsh scripts/verify.sh
/bin/zsh scripts/verify.sh --no-open
/bin/zsh scripts/verify.sh --output ~/Documents
```

## Important limitations

Software alone cannot reliably determine whether a Mac has ever had board-level repair, an original Apple part replaced with another genuine part, a bottom case swapped, screws opened, or liquid damage cleaned. Apple Diagnostics also requires rebooting into its dedicated environment and therefore cannot be fully automated from a normal macOS session.

## License

MIT
