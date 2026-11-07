#!/usr/bin/env python3
"""Read-only AppleSmartBattery analysis.

Measured capacity percentages are never called a probability of survival.
Unsupported controller keys remain null. No private API, sudo, SMC writes,
charging configuration changes, or attempt to identify a replacement battery.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import html
import json
import math
import os
from pathlib import Path
import plistlib
import re
import statistics
import subprocess
import sys
from typing import Any

VERSION = "1.3.0"
HISTORY_LIMIT = 1000


def positive(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, dict):
        value = value.get("value")
    if isinstance(value, (int, float)) and math.isfinite(value) and value > 0:
        return float(value)
    if isinstance(value, str):
        try:
            n = float(value.replace(",", "").strip())
            return n if math.isfinite(n) and n > 0 else None
        except ValueError:
            pass
    return None


def scalar(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        v = float(value)
        return v if math.isfinite(v) else None
    except (ValueError, TypeError):
        return None


def get(data: dict, key: str) -> Any:
    """Prefer root controller fields, then BatteryData, not substring matching."""
    if key in data:
        return data[key]
    sub = data.get("BatteryData")
    if isinstance(sub, dict):
        return sub.get(key)
    return None


def percent_ratio(top: Any, bottom: Any) -> float | None:
    a, b = positive(top), positive(bottom)
    if a is None or b is None or a > b * 1.6:
        return None
    return round(a * 100 / b, 2)


def numeric_list(value: Any) -> list[float]:
    if not isinstance(value, (list, tuple)):
        return []
    return [float(v) for x in value if (v := positive(x)) is not None]


def raw_temperature(value: Any) -> dict:
    """Apple temperature units differ across controllers; do not silently guess."""
    v = scalar(value)
    if v is None:
        return {"raw": None, "celsius": None, "unit": "unknown"}
    # Explicit plausible conversions, still marked as inferred.
    if 2500 <= v <= 4000:
        c = v / 10 - 273.15
        return {"raw": v, "celsius": round(c, 1), "unit": "inferred_deci_kelvin"}
    if 25000 <= v <= 40000:
        c = v / 100 - 273.15
        return {"raw": v, "celsius": round(c, 1), "unit": "inferred_centi_kelvin"}
    if 5 <= v <= 85:
        return {"raw": v, "celsius": v, "unit": "reported_celsius_unverified"}
    return {"raw": v, "celsius": None, "unit": "unknown"}


def signed_64(value: Any) -> float | None:
    n = scalar(value)
    if n is None:
        return None
    if n >= 2**63:
        return float(int(n) - 2**64)
    return n


def assess(data: dict, system_health: str | None = None, system_condition: str | None = None) -> dict:
    battery_data = data.get("BatteryData") if isinstance(data.get("BatteryData"), dict) else {}
    design = positive(get(data, "DesignCapacity"))
    nominal = positive(get(data, "NominalChargeCapacity"))
    raw_max = positive(get(data, "AppleRawMaxCapacity"))
    full_charge = positive(get(data, "FullChargeCapacity"))
    cycles = scalar(get(data, "CycleCount"))
    design_cycles = positive(get(data, "DesignCycleCount9C")) or positive(get(data, "DesignCycleCount"))
    display_health = None
    if system_health:
        match = re.search(r"(\d{1,3})\s*%", system_health)
        if match and 0 <= int(match.group(1)) <= 100:
            display_health = int(match.group(1))
    # Nominal is most comparable to Battery Health shown by macOS on many
    # Apple Silicon models. Raw is a different physical-controller estimate.
    nominal_pct = percent_ratio(nominal, design)
    raw_pct = percent_ratio(raw_max, design)
    full_pct = percent_ratio(full_charge, design)
    useful_pct = nominal_pct if nominal_pct is not None else (
        full_pct if full_pct is not None else raw_pct
    )
    capacity_source = ("NominalChargeCapacity" if nominal_pct is not None else
                       "FullChargeCapacity" if full_pct is not None else
                       "AppleRawMaxCapacity" if raw_pct is not None else "unavailable")

    voltage_cells = numeric_list(get(data, "CellVoltage"))
    qmax_cells = numeric_list(get(data, "Qmax"))
    # Some controllers only expose arrays inside BatteryData.
    if not voltage_cells:
        voltage_cells = numeric_list(battery_data.get("CellVoltage"))
    if not qmax_cells:
        qmax_cells = numeric_list(battery_data.get("Qmax"))
    delta_mv = round(max(voltage_cells) - min(voltage_cells), 2) if len(voltage_cells) >= 2 else None
    qmax_spread = round((max(qmax_cells) - min(qmax_cells)) / statistics.mean(qmax_cells) * 100, 2) if len(qmax_cells) >= 2 else None

    temperature = raw_temperature(get(data, "Temperature"))
    voltage_mv = positive(get(data, "Voltage"))
    current_ma = signed_64(get(data, "InstantAmperage"))
    if current_ma is None:
        current_ma = signed_64(get(data, "Amperage"))
    # signed_64 cannot preserve unsigned 64-bit precision through float conversion
    if isinstance(get(data, "InstantAmperage"), int) and get(data, "InstantAmperage") >= 2**63:
        current_ma = get(data, "InstantAmperage") - 2**64
    elif isinstance(get(data, "Amperage"), int) and get(data, "Amperage") >= 2**63:
        current_ma = get(data, "Amperage") - 2**64
    power_w = round(float(voltage_mv * current_ma / 1_000_000), 2) if (
        voltage_mv is not None and current_ma is not None
    ) else None

    condition = (system_condition or "").strip()
    pfailure = scalar(get(data, "PermanentFailureStatus"))
    disconnects = scalar(get(data, "BatteryCellDisconnectCount"))
    charge_percent = scalar(get(data, "CurrentCapacity"))
    if charge_percent is not None and not 0 <= charge_percent <= 100:
        charge_percent = None

    alerts: list[dict] = []
    def alert(level: str, reason: str, evidence: str) -> None:
        alerts.append({"severity": level, "reason": reason, "evidence": evidence})

    if condition and condition.casefold() not in ("normal",):
        alert("WARN", "macOS condition needs review", "macOS: " + condition)
    if pfailure is not None and pfailure != 0:
        alert("FAIL", "Battery controller permanent failure", f"flag={pfailure:g}")
    if useful_pct is not None and useful_pct < 80:
        alert("WARN", "Low measured full-charge capacity",
              f"{capacity_source}/{int(design)} = {useful_pct:.2f}%")
    if delta_mv is not None and delta_mv > 60:
        alert("WARN", "Cell voltage imbalance", f"Delta {delta_mv:g} mV; retest at a different charge/load")
    if qmax_spread is not None and qmax_spread > 8:
        alert("WARN", "Cell Qmax spread", f"Delta {qmax_spread:g}% relative to mean; controller-specific")
    # Do not treat nonzero disconnect count as proof of replacement.
    if disconnects is not None and disconnects > 0:
        alert("INFO", "Battery disconnect counter nonzero",
              "Not evidence by itself of replacement: count " + str(int(disconnects)))
    if display_health is not None and nominal_pct is not None and abs(display_health - nominal_pct) >= 5:
        alert("INFO", "macOS / controller health difference",
              f"macOS={display_health}%, nominal={nominal_pct}%; Battery Health Management may differ")

    measured = sum(v is not None for v in (design, nominal, raw_max, cycles, delta_mv, qmax_spread, voltage_mv, current_ma))
    confidence = "HIGH" if measured >= 7 else "MEDIUM" if measured >= 4 else "LOW" if measured >= 2 else "UNAVAILABLE"
    # A heuristic for anomaly review: not an Apple Health percentage.
    diagnostics = None
    if confidence in ("HIGH", "MEDIUM"):
        diagnostics = 100
        if useful_pct is not None:
            diagnostics -= min(30, max(0, 90 - useful_pct) * 2)
        if delta_mv is not None:
            diagnostics -= min(22, max(0, delta_mv - 20) * 0.35)
        if qmax_spread is not None:
            diagnostics -= min(15, max(0, qmax_spread - 4) * 2)
        if condition and condition.casefold() != "normal":
            diagnostics -= 20
        if pfailure is not None and pfailure != 0:
            diagnostics = 0
        diagnostics = round(max(0, min(100, diagnostics)))
    status = "UNAVAILABLE" if confidence == "UNAVAILABLE" else "INFO"
    if any(a["severity"] == "WARN" for a in alerts):
        status = "WARN"
    if any(a["severity"] == "FAIL" for a in alerts):
        status = "FAIL"

    return {
        "version": VERSION, "status": status, "evidence_confidence": confidence,
        "diagnostic_signal_score": diagnostics,
        "note": "Diagnostic score is a transparent anomaly indicator, NOT Apple battery-health %, remaining life, replacement authenticity, or failure probability.",
        "capacity": {
            "design_mah": design, "nominal_mah": nominal, "raw_max_mah": raw_max,
            "full_charge_mah": full_charge, "nominal_health_percent": nominal_pct,
            "raw_health_percent": raw_pct, "full_health_percent": full_pct,
            "capacity_health_percent": useful_pct, "capacity_health_source": capacity_source,
            "macos_reported_health_percent": display_health
        },
        "charging": {
            "charge_percent": charge_percent,
            "is_charging": get(data, "IsCharging"),
            "external_connected": get(data, "ExternalConnected"),
            "voltage_mv": voltage_mv, "instant_current_ma": current_ma,
            "approx_battery_power_w": power_w,
            "adapter_details": {
                "watts": get(data, "AdapterDetails").get("Watts")
                if isinstance(get(data, "AdapterDetails"), dict) else None
            },
            "temperature": temperature
        },
        "cycles": {
            "count": cycles, "design_reference": design_cycles,
            "ratio_percent": round(cycles / design_cycles * 100, 1)
            if cycles is not None and design_cycles else None
        },
        "cells": {
            "voltage_mv": voltage_cells,
            "voltage_delta_mv": delta_mv,
            "qmax": qmax_cells,
            "qmax_spread_percent": qmax_spread
        },
        "controller_flags": {
            "permanent_failure": pfailure,
            "cell_disconnect_count": disconnects,
            "max_temperature_raw": get(data, "MaximumTemperature"),
            "not_charging_reason_raw": get(data, "NotChargingReason")
        },
        "condition": condition or None,
        "alerts": alerts
    }


def parse_system_health(text: str) -> tuple[str | None, str | None]:
    health = re.search(r"(?m)^\s*Maximum Capacity:\s*([0-9]+%)\s*$", text)
    condition = re.search(r"(?m)^\s*Condition:\s*(.+?)\s*$", text)
    return (health.group(1) if health else None, condition.group(1) if condition else None)


def parse_plist(raw: bytes) -> dict:
    obj = plistlib.loads(raw)
    if isinstance(obj, list):
        for entry in obj:
            if isinstance(entry, dict) and (
                "BatteryData" in entry or "DesignCapacity" in entry or "CycleCount" in entry
            ):
                return entry
    if isinstance(obj, dict):
        return obj
    return {}


def collect() -> tuple[dict, str]:
    try:
        cp = subprocess.run(
            ["/usr/sbin/ioreg", "-a", "-r", "-n", "AppleSmartBattery"],
            capture_output=True, timeout=15, check=False
        )
        if cp.returncode == 0 and cp.stdout:
            return parse_plist(cp.stdout), "ioreg_plist"
        return {}, "ioreg unavailable or no AppleSmartBattery instance"
    except (OSError, ValueError, plistlib.InvalidFileException, subprocess.TimeoutExpired) as exc:
        return {}, str(exc)


def history_file(folder: Path, identity: str) -> Path:
    return folder / (hashlib.sha256(identity.encode()).hexdigest()[:24] + ".jsonl")


def load_history(file: Path) -> list[dict]:
    if not file.exists():
        return []
    rows = []
    for line in file.read_text(encoding="utf-8").splitlines()[-HISTORY_LIMIT:]:
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
        except ValueError:
            continue
    return rows


def update_history(file: Path, report: dict) -> list[dict]:
    file.parent.mkdir(parents=True, exist_ok=True)
    old = load_history(file)
    snap = {
        "collected_at": report["collected_at"],
        "capacity_health_percent": report["capacity"]["capacity_health_percent"],
        "raw_health_percent": report["capacity"]["raw_health_percent"],
        "cycle_count": report["cycles"]["count"],
        "cell_delta_mv": report["cells"]["voltage_delta_mv"],
        "qmax_spread_percent": report["cells"]["qmax_spread_percent"],
        "diagnostic_signal_score": report["diagnostic_signal_score"],
        "status": report["status"]
    }
    with file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snap, ensure_ascii=False) + "\n")
    return (old + [snap])[-HISTORY_LIMIT:]


def trend_alerts(report: dict, history: list[dict]) -> None:
    if not history:
        return
    latest = history[-1]
    oldhealth = positive(latest.get("capacity_health_percent"))
    now = positive(report["capacity"]["capacity_health_percent"])
    # A single short-run drop is often gauge recalibration; review rather than FAIL.
    if oldhealth is not None and now is not None and now < oldhealth - 5:
        report["alerts"].append({
            "severity": "WARN", "reason": "Large capacity change since previous check",
            "evidence": f"Previously {oldhealth:.2f}%, now {now:.2f}%; verify after calibration"
        })
        report["status"] = "WARN"


def html_report(r: dict, historical: list[dict]) -> str:
    esc = lambda v: html.escape(str(v if v is not None else "N/A"), quote=True)
    groups = {
        "Battery capacity": {
            "Nominal health (measured %)": r["capacity"]["nominal_health_percent"],
            "Raw controller health (%)": r["capacity"]["raw_health_percent"],
            "macOS reported Battery Health (%)": r["capacity"]["macos_reported_health_percent"],
            "Design capacity (mAh)": r["capacity"]["design_mah"],
            "Nominal capacity (mAh)": r["capacity"]["nominal_mah"],
            "Raw max (mAh)": r["capacity"]["raw_max_mah"]
        },
        "Controller and charging": {
            "Current charge (not health %)": r["charging"]["charge_percent"],
            "Cycles": r["cycles"]["count"],
            "Controller design cycle reference": r["cycles"]["design_reference"],
            "Cell voltage delta (mV)": r["cells"]["voltage_delta_mv"],
            "Cell Qmax spread (%)": r["cells"]["qmax_spread_percent"],
            "Voltage (mV)": r["charging"]["voltage_mv"],
            "Current (mA, signed)": r["charging"]["instant_current_ma"],
            "Approx. battery power (W)": r["charging"]["approx_battery_power_w"],
            "Temperature raw": r["charging"]["temperature"]["raw"],
            "Temperature °C (unit-dependent)": r["charging"]["temperature"]["celsius"],
            "Permanent failure flag": r["controller_flags"]["permanent_failure"],
            "Disconnect counter (not replacement proof)": r["controller_flags"]["cell_disconnect_count"],
        }
    }
    tables = ""
    for group, fields in groups.items():
        tables += "<section><h2>" + esc(group) + "</h2><table>"
        for name, value in fields.items():
            tables += "<tr><td>" + esc(name) + "</td><td><b>" + esc(value) + "</b></td></tr>"
        tables += "</table></section>"
    alerts = "".join(
        "<li><b>" + esc(a["severity"]) + " — " + esc(a["reason"]) + "</b>: " +
        esc(a["evidence"]) + "</li>" for a in r["alerts"]
    )
    start = historical[0] if historical else None
    history_summary = (
        "Snapshots: " + str(len(historical)) + " · first recorded " + esc(start.get("collected_at"))
        if start else "No historical baseline yet"
    )
    return """<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MacBook Verify | Battery Deep</title><style>
:root{color-scheme:dark}body{margin:0;background:#0b1120;color:#e5edf8;font:15px system-ui,-apple-system,sans-serif}
main{max-width:1050px;margin:auto;padding:28px}section{background:#142039;border:1px solid #33445d;border-radius:16px;padding:22px;margin:14px 0}
h1{font-size:30px;margin:0}p{color:#adbed5}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.metric{background:#23334e;border-radius:12px;padding:16px}.metric b{display:block;font-size:27px}small{color:#adbed5}
table{width:100%;border-collapse:collapse}td{padding:10px;border-bottom:1px solid #33445d}
.notice{border-left:4px solid #d4a337;padding:14px;background:#352d1b;border-radius:8px}
@media(max-width:700px){.grid{grid-template-columns:1fr}main{padding:12px}}
</style></head><body><main><section><h1>Battery Deep Diagnostics</h1>
<p>AppleSmartBattery controller data · offline · read-only</p><div class="grid">
<div class="metric"><small>Capacity health</small><b>__HEALTH__</b></div>
<div class="metric"><small>Raw controller estimate</small><b>__RAW__</b></div>
<div class="metric"><small>Diagnostic signal</small><b>__SIGNAL__</b></div></div>
<p class="notice">Capacity health is a ratio of charge capacities, NOT battery authenticity or failure probability.
The independent diagnostic signal score is heuristic and requires multiple sources.
Missing values remain N/A. Individual-cell balance needs readings at multiple charge/load states.</p></section>
__TABLES__
<section><h2>Alerts</h2>__ALERTS__<h2>Historical data</h2><p>__HISTORY__</p>
<p>Local snapshots stored in ~/.macbook-verify/battery-history. Report source: __SOURCE__; confidence: __CONFIDENCE__.</p></section></main></body></html>"""\
        .replace("__HEALTH__", esc(r["capacity"]["capacity_health_percent"]) + "%")\
        .replace("__RAW__", esc(r["capacity"]["raw_health_percent"]) + "%")\
        .replace("__SIGNAL__", esc(r["diagnostic_signal_score"]) + "/100")\
        .replace("__TABLES__", tables)\
        .replace("__ALERTS__", "<ul>" + alerts + "</ul>" if alerts else "<p>No anomaly detected from accessible telemetry.</p>")\
        .replace("__HISTORY__", history_summary)\
        .replace("__SOURCE__", esc(r.get("source", "unknown")))\
        .replace("__CONFIDENCE__", esc(r["evidence_confidence"]))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="MacBook Verify battery deep, no system changes")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--history-dir", default=str(Path.home() / ".macbook-verify" / "battery-history"))
    p.add_argument("--system-power-file", help="Existing system_profiler power.txt evidence")
    p.add_argument("--fixture-json", help=argparse.SUPPRESS)
    p.add_argument("--machine-id", help="Optional history identity (system serial), never uploaded")
    p.add_argument("--raw-evidence-file", help="Original IORegistry plist evidence (saved locally)")
    args = p.parse_args(argv)
    out = Path(args.out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    if args.fixture_json:
        data = json.loads(Path(args.fixture_json).read_text(encoding="utf-8"))
        source = "fixture"
    else:
        data, source = collect()
    health, condition = (None, None)
    if args.system_power_file:
        path = Path(args.system_power_file)
        if path.is_file():
            health, condition = parse_system_health(path.read_text(encoding="utf-8", errors="replace"))
    r = assess(data, health, condition)
    r["source"] = source
    r["collected_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    r["controller_raw_keys"] = sorted(data.keys()) if isinstance(data, dict) else []
    if args.raw_evidence_file and data:
        Path(args.raw_evidence_file).write_bytes(plistlib.dumps(data))
    identity = args.machine_id or str(get(data, "Serial") or get(data, "BatterySerialNumber") or "local-mac")
    historypath = history_file(Path(args.history_dir).expanduser(), identity)
    history = load_history(historypath)
    trend_alerts(r, history)
    if source != "fixture":
        try:
            history = update_history(historypath, r)
        except OSError as exc:
            r["history_warning"] = str(exc)
    (out / "battery-report.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "battery-report.html").write_text(html_report(r, history), encoding="utf-8")
    lines = []
    s = r["status"]
    lines.append(("Battery Deep", "Controller telemetry", "INFO" if s in ("INFO", "UNAVAILABLE") else s,
                  s, "Source: " + source + "; confidence " + r["evidence_confidence"]))
    for name, value in (
        ("Nominal capacity health %", r["capacity"]["nominal_health_percent"]),
        ("Raw controller health %", r["capacity"]["raw_health_percent"]),
        ("Actual charge %", r["charging"]["charge_percent"]),
        ("Battery diagnostic signal", r["diagnostic_signal_score"]),
        ("Cell voltage delta mV", r["cells"]["voltage_delta_mv"]),
        ("Qmax cell spread %", r["cells"]["qmax_spread_percent"]),
        ("Approx battery power W", r["charging"]["approx_battery_power_w"])
    ):
        lines.append(("Battery Deep", name, "INFO", "N/A" if value is None else str(value),
                      "Measured/derived from controller; diagnostic signal is not battery health percentage."))
    for a in r["alerts"]:
        lines.append(("Battery Deep", a["reason"], a["severity"], a["evidence"], "Controller evidence; confirm physically"))
    (out / "battery-results.tsv").write_text("".join("\t".join(str(x).replace("\t", " ").replace("\n", " ") for x in line) + "\n" for line in lines), encoding="utf-8")
    print(json.dumps({
        "status": r["status"], "confidence": r["evidence_confidence"],
        "capacity_health_percent": r["capacity"]["capacity_health_percent"],
        "raw_health_percent": r["capacity"]["raw_health_percent"],
        "diagnostic_signal_score": r["diagnostic_signal_score"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
