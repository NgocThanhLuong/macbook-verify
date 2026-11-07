# SSD Deep Health (DriveDx-style, optional)

This module extends MacBook Verify with advanced SMART telemetry, but **is not
DriveDx** and does not copy its proprietary algorithms. It cannot claim parity
where macOS or a disk controller hides SMART attributes.

## Features

| Capability | Availability |
|---|---|
| Drive identification, firmware, capacity, SMART overall status | When exposed by smartctl |
| NVMe available spare, critical warnings, percentage used | When exposed |
| NVMe estimated endurance left (100 − percentage used; clamped) | When exposed; *not* failure probability |
| NVMe total data written/read (decimal TB) | When exposed |
| Power-on hours, power cycles, unsafe shutdowns | When exposed |
| Media errors, error log count, NVMe/ATA error-log entries | When exposed |
| Drive temperature, NVMe temperature sensors | When exposed |
| ATA per-attribute normalized/worst/threshold/raw table | When exposed |
| ATA firmware self-test and NVMe self-test history | When exposed |
| Historical snapshot comparison, new error warnings, trends | Across local runs |
| Color dashboard, machine-readable JSON and TSV | Included |
| Foreground monitoring and opt-in macOS notifications | Included |
| Firmware short/long self-test requests | Explicit opt-in only, if supported |
| Free-space check, read/write data integrity, coarse speed | Already in MacBook Verify |
| SMART-derived performance score / failure probability | Not computed; unreliable without device-specific evidence |
| Background agent, email delivery, DriveDx vendor algorithms | Not implemented |

## Installation

All existing MacBook Verify checks work without additional dependencies.
For SSD Deep Health, install Python 3 and (optionally) smartmontools:

~~~bash
brew install python smartmontools
~~~

Never install a third-party driver or disable macOS security merely to obtain SMART
data. Internal Apple Silicon SSDs **may not expose** the standard counters,
including TBW, wear, and temperature, even with smartctl installed. The tool
reports N/A/UNKNOWN in this case rather than inventing a health percentage.

## Use inside the MacBook Verify report

Run the normal launcher:

~~~bash
./MacBookVerify.command --deep
~~~

The output includes \`ssd-report.html\`, \`ssd-report.json\`,
\`ssd-results.tsv\`, and \`raw/ssd-deep-console.txt\`.
The main \`report.html\` links to the SSD Deep Health dashboard.

### Run independently

~~~bash
python3 scripts/ssd_diagnostics.py --out-dir "$HOME/Desktop/ssd-check"
# Specify a particular accessible physical disk:
python3 scripts/ssd_diagnostics.py --out-dir "$HOME/Desktop/ssd-check" --device /dev/disk0
# Observe changes in foreground every 5 minutes; enable local notifications:
python3 scripts/ssd_diagnostics.py --out-dir "$HOME/Desktop/ssd-watch" --monitor --interval 300 --notify
# Explicit firmware self-test, ONLY if your SSD/driver supports it:
python3 scripts/ssd_diagnostics.py --out-dir "$HOME/Desktop/ssd-check" --device /dev/disk0 --self-test short
~~~

Device names should be checked with \`diskutil list\` and \`smartctl --scan-open\`.
A self-test may be unsupported by Apple firmware. Do not use it while migrating
or repairing an unstable disk without a verified backup.

## How the classification works

* **OK**: firmware SMART passed and no inspected issue detected.
* **WARNING**: anomalies such as historical media errors, increasing error
  counters, unusually high temperature or large endurance consumption.
* **FAILING**: SMART failure, NVMe critical warning, spare exhaustion, or ATA
  normalized attribute crossing its manufacturer threshold.
* **UNKNOWN**: insufficient evidence. **UNKNOWN never means healthy**.

The ordinary MacBook Verify score is a test score, not a prediction of SSD
life expectancy. SSD endurance percentages are **manufacturer estimates**,
and a worn drive may keep working; a nearly new drive can still fail.

Historical snapshots are saved locally under \`~/.macbook-verify/ssd-history\`
unless \`--history-dir\` overrides the path. They may contain a disk serial
in the JSON report (history files are named by a SHA-256-derived identifier).
Clear that folder if running on a seller's Mac and you don't want retained
inspection history. Reports are not uploaded automatically.

## Platform limits

**Apple Silicon:** Apple internal SSD SMART API exposure is inconsistent, and
basic macOS SMART Verified is not equivalent to advanced health attributes.

**USB storage:** Some USB bridges hide SMART. Missing information is not a
drive failure.

**ATA/SATA:** Attribute names and RAW units are vendor-specific; the tool
does not turn arbitrary LBA counters into TBW.

**Firmware self-tests:** Available only where the firmware and transport
implement them. The main MacBook Verify run never starts one automatically.

## Tests

~~~bash
python3 -m unittest discover -s tests -v
bash -n scripts/verify.sh scripts/report.sh
~~~

Fixtures are synthetic; a successful Linux unit test does **not** establish
compatibility with a particular Mac or Apple firmware version. On-device
validation remains required before trusting a purchase decision.

## Export SMART JSON with elevated read permissions (optional)

On some macOS/Apple Silicon combinations, the SSD controller only exposes
advanced attributes to `smartctl` when it runs as root. Do **not** give the
whole MacBook Verify launcher root privileges. Export only the SMART evidence:

~~~bash
diskutil list
# Verify disk identifier before choosing /dev/disk0:
sudo smartctl -a -j /dev/disk0 > "$HOME/Desktop/smart-disk0.json"
python3 scripts/ssd_diagnostics.py --out-dir "$HOME/Desktop/ssd-check" \
  --smart-json-file "$HOME/Desktop/smart-disk0.json"
~~~

The import reads JSON locally and never executes its contents. Your JSON may
contain serial numbers; remove it when no longer needed. SMART telemetry
remains unavailable if the drive firmware does not expose it, even with root.

## Background monitoring (opt-in, no root)

~~~bash
python3 scripts/ssd_monitor_agent.py --install --interval 900
python3 scripts/ssd_monitor_agent.py --status
python3 scripts/ssd_monitor_agent.py --uninstall
~~~

This installs a macOS per-user LaunchAgent that periodically runs the SSD
reader and writes local reports under `~/Library/Application Support/MacBookVerify/SSD/`.
It notifies on newly detected warnings/failures. No SMTP, cloud, email, or
system-wide daemon is installed. It cannot monitor SMART fields blocked by
macOS; such values remain unknown. Uninstalling leaves local history/reports
for manual deletion.
