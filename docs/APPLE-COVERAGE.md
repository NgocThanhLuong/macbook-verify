# Apple Coverage & Device Provenance

This module adds model-year, manufacturing, purchase, activation, and Apple
warranty evidence to the same report as hardware and SSD health.

## What is actually possible?

| Field | MacBook Verify | Reliability |
|---|---|---|
| Serial, model identifier | Automatically from macOS | Local hardware report; compare physical bottom-case serial |
| Model year (e.g. 2021 M1 Max) | Automatically from model database | Model *introduction*, not build date |
| Exact manufacture date for modern Apple serial | **Not available** | Apple randomized serials since 2021 do not encode build date |
| Exact first activation date | **Not available from Apple's public serial checker** | Never estimate from a warranty expiration |
| Valid Purchase Date status | From user-copied Apple Coverage result | Does not establish exact purchase/activation day |
| Purchase date | When supported by receipt or human-imported Apple record | Marked user-supplied, not machine-authenticated |
| Warranty expiration | Enter/import observed Apple result | User-supplied, not machine-authenticated |
| AppleCare expiration | Enter/import observed Apple result | User-supplied, not machine-authenticated |
| Ownership / MDM | Existing MacBook Verify checks | Not substitutes for erase/re-activation |

There is **no documented unrestricted anonymous public API** that this app can
use to fetch Apple warranty, activation and manufacture dates by serial alone.
Apple's checkcoverage.apple.com may require CAPTCHA or sign-in. This tool
intentionally does not bypass CAPTCHA, scrape session tokens, or ask you for an
Apple Account password.

Official references:
- https://checkcoverage.apple.com/
- https://mysupport.apple.com/
- https://support.apple.com/vi-vn/102607
- https://support.apple.com/en-us/102865

## Guided Apple coverage (fewest manual steps)

Run the included macOS launcher:

~~~bash
bash CheckAppleCoverage.command
~~~

It reads your local Mac model and serial, copies the serial to the clipboard,
opens Apple's official site, and waits while you complete Apple's own
verification. Once the results appear, press Cmd+A/Cmd+C in the browser and
return to Terminal to import the copied text. The date parser supports several
English and Vietnamese expiry formats, but cannot guarantee compatibility with
all Apple page variants. Imported records remain labelled as user-copied.

This avoids typing the serial and individual dates, but *cannot* avoid Apple's
CAPTCHA/sign-in or independently authenticate the imported result.

## Fastest official check

Run MacBook Verify normally:

~~~bash
./MacBookVerify.command --deep
~~~

Open **Apple Coverage & Device Provenance** in the generated report.
Click **Copy serial** → **Apple Check Coverage**, paste the serial, and
complete any verification Apple requires.

To launch this directly from Terminal (copies serial with macOS pbcopy and
opens the official site only when explicitly requested):

~~~bash
python3 scripts/apple_coverage.py \
    --serial "YOUR_MAC_SERIAL" \
    --model-identifier "MacBookPro18,1" \
    --out-dir "$HOME/Desktop/my-coverage-check" \
    --open-official
~~~

Nothing is transmitted until you explicitly submit to Apple's site.

## Include Apple results in the same MacBook Verify report

The generated \`apple-coverage.html\` contains a form for dates observed on
Apple's website. Export \`coverage-import.json\`, then run:

~~~bash
python3 scripts/apple_coverage.py \
    --serial "YOUR_MAC_SERIAL" \
    --model-identifier "MacBookPro18,1" \
    --out-dir "$HOME/Desktop/coverage-check" \
    --import-json "$HOME/Downloads/coverage-import.json"

./MacBookVerify.command --deep
~~~

The import is cached under \`~/.macbook-verify/coverage/\` and the next full
inspection includes the fields in \`report.html\`, \`summary.json\`,
\`summary.txt\`, and \`apple-coverage.html\`.

For a supported English result copied from the official site, an alternative is:

~~~bash
# Explicitly reads the current macOS clipboard; copy only the Apple result.
python3 scripts/apple_coverage.py --serial "YOUR_MAC_SERIAL" \
    --out-dir "$HOME/Desktop/coverage-check" --import-clipboard
~~~

The text parser uses label-specific patterns and may not recognize every
localization or website revision; check the displayed date before purchase.

### Input format

~~~json
{
  "serial": "YOUR_MAC_SERIAL",
  "source": "apple_coverage_user_capture",
  "coverage_type": "Limited Warranty",
  "purchase_date_status": "Valid Purchase Date",
  "warranty_expires": "2027-05-01",
  "applecare_expires": null,
  "purchase_date": null,
  "activation_date": null,
  "manufacture_date": null,
  "notes": "Checked on official Apple website"
}
~~~

Supported sources: \`apple_coverage_user_capture\`, \`receipt\`,
\`user_supplied\`, \`repair_record\`.

Do not enter a manufacturing date based on model release date or battery date.
For a receipt/repair document, report the document's actual label and source;
there may still be no proof of when this individual Mac was assembled.

## Privacy

- Apple serial numbers are collected locally and embedded in the report, as
  with existing MacBook Verify features; review before sharing ZIPs.
- Imported records are clearly labelled **user supplied / not verified by the
  tool**. They are not authenticated Apple API responses.
- No external web request or Apple login is performed by the inspector.
- Delete \`~/.macbook-verify/coverage/\` after checking a seller's Mac if you
  don't want a cached local record.
- The 2021 M1 Pro and M1 Max models use randomized serials; a site promising
  their *exact manufacture week* from serial alone is unreliable.
