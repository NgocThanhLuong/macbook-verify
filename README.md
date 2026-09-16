# MacBook Verify

**MacBook Verify v1.0** is a one-click, offline macOS verification and self-test tool for checking a used MacBook before buying, selling, or servicing it.

It combines **static hardware evidence**, **active self-tests**, **deep battery telemetry**, **recent error-history scanning**, and an **interactive physical/function test wizard**. It deliberately does **not** claim that software can prove a Mac is “100% original”.

## One click

Clone/download the repo, then double-click:

```text
MacBookVerify.command
```

Default mode is **Full Check**. A timestamped report folder and ZIP are created on the Desktop and `report.html` opens automatically.

To install a standalone app, double-click:

```text
Install.command
```

It creates:

```text
~/Applications/MacBook Verify.app
```

## Test modes

```bash
./MacBookVerify.command --quick
./MacBookVerify.command --full
./MacBookVerify.command --deep
./MacBookVerify.command --burn-in
./MacBookVerify.command --static-only
```

| Mode | Intended use | Active profile |
| --- | --- | --- |
| Quick | Fast shop-floor check | short CPU, 64 MiB RAM, 128 MiB SSD scratch |
| Full | Default used-Mac inspection | 20s CPU, 256 MiB RAM, 512 MiB SSD scratch |
| Deep | Suspicious/expensive machine | 45s CPU, 512 MiB RAM, 1 GiB SSD scratch, 30-day history |
| Burn-in | Post-repair stability | 180s CPU, 1 GiB RAM, 1 GiB SSD scratch |
| Static-only | No workload/write test | inventory + analysis only |

Temporary storage test data is created under `/private/tmp`, not Desktop/iCloud, and is deleted after the run.

## Automatic checks

### Identity / ownership
- Model, model identifier, model number, chip, CPU/GPU cores, RAM
- Serial cross-check: `system_profiler` vs IOKit
- Model identifier cross-check: `system_profiler` vs `sysctl`
- Local model-reference validation for supported models
- MDM / Automated Device Enrollment detection
- Activation Lock state

### Battery deep analysis
- macOS condition, cycle count, maximum capacity
- Controller design capacity and raw max capacity
- Permanent failure flag
- Battery disconnect counter
- Per-cell voltage spread
- Qmax spread between cells
- Post-load cell-balance snapshot
- Lifetime maximum-temperature telemetry when exposed

Battery telemetry is interpreted conservatively. A non-zero disconnect counter, for example, is **not** automatically called proof of a battery replacement.

### Display / storage / devices
- Built-in display identity, native resolution, internal/online state
- Local model-reference resolution comparison where known
- Internal SSD model/capacity, TRIM, SMART, detachable status
- Camera, microphone, speakers, Wi-Fi and Bluetooth enumeration
- USB / Thunderbolt inventory preserved as raw evidence

### Security / repair evidence
- SIP
- FileVault
- Parts & Service / repair data types when macOS exposes them
- Apple diagnostics information exposed to `system_profiler`

Framework names such as `CoreRepairKit`, `mobilerepaird`, or `corerepaird` are **not treated as repair evidence by themselves**.

## Active self-tests

### CPU / stability
MacBook Verify saturates logical CPU workers for the selected duration while repeatedly hashing a deterministic block. It also samples `pmset -g therm` for obvious pressure/limit signatures.

### RAM pattern integrity
If Apple developer command-line tools are available, the bundled native C helper is compiled locally and verifies two 64-bit patterns across the selected memory amount. If no compiler is installed, this test is clearly marked **SKIP** rather than pretending RAM was tested.

### SSD functional I/O
The tool creates a temporary file on the root volume, writes it, reads it through a second path, verifies SHA-256 consistency, and records coarse throughput. Throughput is **INFO only** because filesystem cache, free space, thermals and model differences make a universal pass/fail speed threshold misleading.

### Network and history
- Default-gateway reachability
- DNS resolution
- Recent panic/kernel/GPU-reset diagnostic filenames
- Power/sleep warning-history snapshot

## Interactive test wizard

The generated `report.html` also contains a local browser-based wizard for things that cannot be proven from a static command:

- Bottom-case serial comparison
- Screw/chassis physical inspection
- Fullscreen white/black/gray/R/G/B display test
- Keyboard event map
- Trackpad move/click/right-click/scroll counters
- Left/right/stereo speaker tones
- Camera preview + microphone level meter (browser permission required)
- Guided Thunderbolt/USB-C, MagSafe, HDMI, SD and headphone-port checks
- Hinge, liquid/corrosion signs, Touch ID
- Apple Diagnostics reboot checklist

Interactive results are kept in browser `localStorage` and can be exported as `interactive-results.json`. Nothing is uploaded by MacBook Verify.

## Output

```text
~/Desktop/MacBook-Verify-YYYYMMDD-HHMMSS/
├── report.html
├── summary.txt
├── summary.json
├── results.tsv
├── manifest.sha256
└── raw/
    ├── hardware.txt
    ├── battery-system.txt
    ├── battery-raw.txt
    ├── battery-postload.txt
    ├── display.txt
    ├── storage.txt
    ├── cpu-thermal.txt
    ├── memory-active.txt          # when native test is available
    ├── mdm.txt
    ├── repair-history.txt
    ├── recent-diagnostics.txt
    └── ...

~/Desktop/MacBook-Verify-YYYYMMDD-HHMMSS.zip
```

## Result semantics

- **PASS** — the specific check completed and met its rule.
- **WARN** — review/retest is recommended.
- **FAIL** — a concrete inconsistency or high-risk condition was detected.
- **INFO** — useful evidence that should not be scored as pass/fail.
- **SKIP** — test was not possible in the current environment.

The automatic health score excludes INFO/SKIP. It is a **health/check score**, not an originality percentage.

## What software still cannot prove

Even a perfect report cannot reliably prove that:

- the bottom case has never been opened;
- a board-level IC/component repair never happened;
- a genuine Apple assembly was never replaced by another genuine assembly;
- liquid damage was never cleaned;
- every empty physical port works without connecting known-good test hardware.

Use the interactive/physical checks, macOS **System Settings → General → About → Parts & Service** when available, and Apple Diagnostics before a high-value purchase.

## Privacy

The tool runs locally and does not upload reports. Reports may contain serial numbers and hardware identifiers. Redact them before posting publicly.

## Requirements

- macOS 11+
- `/bin/bash` (Apple system Bash compatible)
- Standard Apple CLI utilities
- Optional: Apple Command Line Tools for the native RAM pattern test
- No Homebrew, Python, Node.js, server, account, or cloud service required

## License

MIT

#Demo
<img width="1728" height="1117" alt="image" src="https://github.com/user-attachments/assets/e7ac9515-608a-4733-8e40-d45de9fc8abb" />

