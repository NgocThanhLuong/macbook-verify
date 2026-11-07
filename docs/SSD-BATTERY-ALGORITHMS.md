# SSD + Battery Diagnostic Algorithms (v1.3)

MacBook Verify adds read-only diagnostics with transparent evidence provenance.
The algorithms do not replicate DriveDx's proprietary prediction models and
cannot unlock SSD firmware data that macOS does not expose.

## SSD
- Read NVMe/ATA SMART (when driver/permission allows) and analyze firmware
  critical warnings, media errors, endurance used, spare, temperature, power
  hours, unsafe shutdowns and ATA attribute threshold crossing.
- Compute a separate **SMART diagnostic signal** (0–100, heuristic), with
  evidence-confidence label. This is NOT the official remaining SSD life %,
  manufacturer endorsement, or a probability the drive will survive.
- Use a bounded, non-destructive scratch-file test that writes up to 1 GiB
  of incompressible random data, calls fsync and verifies full SHA-256 on reread.
  Measure approximate read/write speed and p95 latency, store historical
  baselines, and warn on strong regressions. Reads may still hit APFS cache.
- Do not infer SSD health from throughput alone. Inability to retrieve
  TBW or Percentage Used returns N/A, not a fabricated percentage.

## Battery

Capacity health from controller:
  NominalCapacityHealth% = 100 * NominalChargeCapacity / DesignCapacity
  RawCapacityHealth%     = 100 * AppleRawMaxCapacity / DesignCapacity

macOS displayed Battery Health is kept as a separate measurement.
CurrentCapacity is the *charge level* and is not battery capacity health.

Additional accessible AppleSmartBattery evidence:
- cycle count and optional design-cycle reference;
- individual cell voltages and spread in mV;
- Qmax per-cell spread in %;
- raw and nominal capacities, current, voltage, approximate battery power;
- controller temperature (inferred units explicitly labelled);
- permanent-failure flags and battery-disconnect counter;
- locally persisted trend snapshots.

A separate 0–100 battery diagnostic signal summarizes visible anomalies.
The diagnostic signal is not the capacity health %, remaining years, or proof
the battery is factory-original. A battery with 100% and five cycles can be
a replacement, and a nonzero disconnect counter is not proof of replacement.
If capacity references are absent, health is N/A.

## Run

    brew install python smartmontools
    ./MacBookVerify.command --deep

Optional read-only standalone probes:

    python3 scripts/battery_diagnostics.py --out-dir "$HOME/Desktop/battery-check"
    mkdir -p /private/tmp/macbook-verify-scratch
    python3 scripts/storage_probe.py --size-mib 64 --scratch-dir /private/tmp/macbook-verify-scratch --out-dir "$HOME/Desktop/ssd-check"

To capture smartctl with elevated read permissions **for a verified device**:

    diskutil list
    sudo smartctl -a -j /dev/disk0 > "$HOME/Desktop/smart-disk0.json"
    python3 scripts/ssd_diagnostics.py --out-dir "$HOME/Desktop/ssd-smart" --smart-json-file "$HOME/Desktop/smart-disk0.json"

Do not run the full verifier with sudo. All scratch files are newly created and
removed. The write test is not a block-level NAND scrub. Some controllers do
not expose privileged telemetry even with sudo.

## Official Apple warranty and activation checks

https://checkcoverage.apple.com/?locale=vi_VN

The site has a serial form and may require CAPTCHA/sign-in. No supported,
unrestricted public serial-to-coverage JSON endpoint has been verified.
CheckAppleCoverage.command copies the current Mac's serial and opens Apple;
the user completes Apple's validation and copies the results for local import.

Model introduction year is NOT manufacturing date. Most 2021+ Mac serials are
randomized, and exact first activation cannot reliably be derived by
subtracting one year from warranty expiration.

## Validation

Run the full suite locally or in GitHub Actions:

    python3 -m unittest discover -s tests -v
    bash -n scripts/verify.sh scripts/report.sh scripts/tests/active.sh

The CI uses synthetic battery and SSD fixtures and a macOS report smoke test.
Real M1 Pro/Max hardware verification remains necessary for sensor coverage.
