# Checks and interpretation

MacBook Verify separates **evidence** from **claims**. Each rule is intentionally conservative.

## Automatic PASS/WARN/FAIL rules

| Area | Test | PASS | WARN / FAIL |
| --- | --- | --- | --- |
| Identity | System serial | `system_profiler` == IOKit | FAIL on mismatch |
| Identity | Model identifier | `system_profiler` == `sysctl hw.model` | FAIL on mismatch |
| Battery | macOS condition | `Normal` | WARN otherwise |
| Battery | Maximum capacity | >= 80% | WARN below 80% |
| Battery | Cycle count | below 80% of controller design reference | WARN at/above 80% reference |
| Battery | PermanentFailureStatus | `0` | FAIL when non-zero |
| Battery | Cell voltage spread | <= 20 mV snapshot | WARN above 20 mV; retest at different SOC/load |
| Battery | Qmax spread | <= 5% | WARN above 5% |
| Battery | Raw max/design | >= 80% | WARN below 80% |
| Storage | SMART | `Verified` | FAIL when explicitly not verified |
| Storage | I/O integrity | write + read + SHA-256 match | FAIL on I/O/checksum error |
| Display | Built-in identity | online + internal | WARN when missing/unexpected |
| Ownership | MDM/ADE | explicit not-enrolled result | FAIL when enrolled |
| Security | SIP | enabled | WARN when disabled/unconfirmed |
| Active | CPU/hash stability | no repeated hash mismatch during load | FAIL on integrity mismatch |
| Active | RAM native pattern test | two 64-bit patterns verify | FAIL on mismatch; SKIP if compiler unavailable |
| History | Recent panic/reset filenames | none found in selected window | WARN when matching reports exist |

## Why performance numbers are INFO

SSD read/write speed and short CPU workload timing are affected by cache, free space, thermals, power mode, background jobs and model generation. The tool records coarse throughput for comparison but does not use a universal benchmark threshold as evidence of a bad SSD.

## Battery cautions

A single cell-voltage snapshot can be affected by state of charge and load. A non-zero `BatteryCellDisconnectCount` can have multiple explanations. Neither should be presented alone as proof that a battery has been replaced.

`DateOfFirstUse=0` or another unavailable manufacturing/first-use field is treated as missing evidence, not a failure.

## Repair history cautions

The presence of macOS components named `CoreRepairKit`, `CoreRepairUI`, `mobilerepaird`, `corerepaird`, etc. is not evidence that the individual Mac was repaired. They are operating-system components.

If a Repair/Parts system-profiler data type is exposed, MacBook Verify preserves it as raw evidence. If it is not exposed, the report explicitly says that absence is not proof of originality.

## Interactive tests

Interactive results are user-observed and stored separately from automatic scoring. This avoids turning subjective checks such as display uniformity, speaker distortion, screw marks or hinge feel into fake machine-generated certainty.

## Apple Diagnostics

Apple Diagnostics requires booting into its diagnostic environment. MacBook Verify cannot truthfully automate that from a normal macOS session, so the report includes it as a guided final check instead.
