#!/usr/bin/env python3
"""Optional deep SSD/NVMe diagnostics for MacBook Verify.

Only reads SMART telemetry unless --self-test was explicitly requested.
Requires Python 3 (standard library); smartctl (smartmontools) is optional.
Missing or inaccessible attributes are UNKNOWN, never invented as 100% health.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import time
from typing import Any
from ssd_health_engine import enrich, comparison_alerts

VERSION = "1.2.0"
SEVERITY = {"UNKNOWN": 0, "OK": 1, "WARNING": 2, "FAILING": 3}
MAX_HISTORY_POINTS = 2000


def call(argv: list[str], timeout: int = 18) -> tuple[int, str, str]:
    try:
        cp = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, timeout=timeout, check=False)
        return cp.returncode, cp.stdout, cp.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, "", str(exc)


def number(value: Any) -> int | float | None:
    if isinstance(value, dict):
        value = value.get("value")
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        value = value.strip().replace(",", "")
        try:
            return float(value) if "." in value else int(value)
        except ValueError:
            pass
    return None


def metric(record: dict, name: str, value: Any, unit: str = "",
           note: str = "") -> None:
    record["metrics"][name] = {"value": value, "unit": unit, "note": note}


def add_alert(record: dict, severity: str, title: str, detail: str) -> None:
    record["alerts"].append({"severity": severity, "title": title, "detail": detail})


def sget(obj: Any, *keys: str, default: Any = None) -> Any:
    for key in keys:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(key)
    return obj if obj is not None else default


def assess(raw: dict[str, Any], device: str = "unknown") -> dict:
    """Analyze smartctl -a -j output. No unsupported proprietary health heuristics."""
    record: dict[str, Any] = {
        "device": device, "name": sget(raw, "model_name", default="Unknown"),
        "serial": str(raw.get("serial_number") or ""),
        "protocol": "NVMe" if "nvme_smart_health_information_log" in raw else
                    "ATA" if "ata_smart_attributes" in raw else "Unknown",
        "status": "UNKNOWN", "metrics": {}, "alerts": [],
        "attributes": [], "errors": [], "self_tests": [],
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "source": "smartctl", "evidence_available": bool(raw),
    }
    if raw.get("model_family"):
        record["family"] = raw["model_family"]
    if raw.get("firmware_version"):
        record["firmware"] = raw["firmware_version"]
    capacity = number(sget(raw, "user_capacity", "bytes"))
    if capacity is not None:
        metric(record, "capacity_bytes", int(capacity), "bytes")
    healthy = sget(raw, "smart_status", "passed")
    if healthy is True:
        record["status"] = "OK"
        metric(record, "smart_passed", True)
    elif healthy is False:
        record["status"] = "FAILING"
        metric(record, "smart_passed", False)
        add_alert(record, "FAILING", "SMART reports failure",
                  "Drive firmware reports an overall SMART failure.")
    else:
        metric(record, "smart_passed", None, note="Not exposed by device/driver")

    nvme = raw.get("nvme_smart_health_information_log")
    if isinstance(nvme, dict):
        record["protocol"] = "NVMe"
        mapping = {
            "critical_warning": ("critical_warning", ""),
            "available_spare": ("available_spare", "%"),
            "available_spare_threshold": ("available_spare_threshold", "%"),
            "percentage_used": ("percentage_used", "%"),
            "power_cycles": ("power_cycles", ""),
            "power_on_hours": ("power_on_hours", "hours"),
            "unsafe_shutdowns": ("unsafe_shutdowns", ""),
            "media_errors": ("media_errors", ""),
            "num_err_log_entries": ("error_log_entries", ""),
            "controller_busy_time": ("controller_busy_time", "minutes"),
            "warning_temp_time": ("warning_temperature_time", "minutes"),
            "critical_comp_time": ("critical_temperature_time", "minutes"),
            "host_read_commands": ("host_read_commands", ""),
            "host_write_commands": ("host_write_commands", ""),
        }
        for key, (dest, unit) in mapping.items():
            val = number(nvme.get(key))
            if val is not None:
                metric(record, dest, val, unit)
        for source, name in (("data_units_written", "total_written_tb"),
                             ("data_units_read", "total_read_tb")):
            units = number(nvme.get(source))
            if units is not None:
                # NVMe SMART data units are 1000 * 512 bytes (decimal terabytes).
                metric(record, name, round(units * 512000 / 10**12, 3), "TB",
                       "NVMe data units: 512,000 bytes each")
        used = number(nvme.get("percentage_used"))
        if used is not None:
            # Percentage Used is an estimate of endurance consumed, not failure risk.
            metric(record, "estimated_lifetime_left", max(0, 100 - used), "%",
                   "Endurance estimate from NVMe Percentage Used, not a failure prediction")
            if used >= 100:
                add_alert(record, "WARNING", "Rated endurance consumed",
                          "NVMe Percentage Used is 100% or more; drive may still work.")
            elif used >= 80:
                add_alert(record, "WARNING", "High endurance consumption",
                          "NVMe Percentage Used reached 80%.")
        temp = number(nvme.get("temperature"))
        if temp is not None:
            if temp > 200:  # handle raw Kelvin reports defensively
                temp -= 273.15
            metric(record, "temperature_c", round(temp, 1), "°C")
            if temp >= 70:
                add_alert(record, "WARNING", "High SSD temperature",
                          "Current reported SSD temperature is at least 70°C.")
        sensors = nvme.get("temperature_sensors")
        if isinstance(sensors, list):
            values = [number(v) for v in sensors]
            metric(record, "temperature_sensors_c", [
                round(v - 273.15 if v > 200 else v, 1)
                for v in values if v is not None], "°C")
        warning = number(nvme.get("critical_warning"))
        if warning is not None and warning != 0:
            add_alert(record, "FAILING", "NVMe critical warning",
                      "NVMe critical_warning bitmask is non-zero: " + str(warning))
        spare = number(nvme.get("available_spare"))
        threshold = number(nvme.get("available_spare_threshold"))
        if spare is not None and threshold is not None and spare <= threshold:
            add_alert(record, "FAILING", "Available spare below threshold",
                      "Reported spare capacity has reached the drive threshold.")
        elif spare is not None and spare < 20:
            add_alert(record, "WARNING", "Low available spare",
                      "Reported available spare is below 20%.")
        errors = number(nvme.get("media_errors"))
        if errors is not None and errors > 0:
            add_alert(record, "WARNING", "Historical media errors",
                      "Media errors are nonzero. Compare historical snapshots for growth.")
        err_log = raw.get("nvme_error_information_log")
        if isinstance(err_log, list):
            record["errors"] = err_log[:20]
        nvme_test = raw.get("nvme_self_test_log")
        if isinstance(nvme_test, dict):
            record["self_tests"] = nvme_test.get("table", [])[:20]

    attrs = sget(raw, "ata_smart_attributes", "table", default=[])
    if isinstance(attrs, list):
        for attr in attrs:
            if not isinstance(attr, dict):
                continue
            entry = {
                "id": attr.get("id"), "name": attr.get("name", ""),
                "value": attr.get("value"), "worst": attr.get("worst"),
                "threshold": attr.get("thresh"),
                "raw": sget(attr, "raw", "value"),
                "when_failed": attr.get("when_failed", "")
            }
            record["attributes"].append(entry)
            val, threshold = number(entry["value"]), number(entry["threshold"])
            if val is not None and threshold is not None and threshold > 0 and val <= threshold:
                add_alert(record, "FAILING", "ATA SMART attribute threshold",
                          str(entry["name"]) + " crossed manufacturer threshold.")
            key = str(entry["name"]).lower()
            raw_value = number(entry["raw"])
            if key in ("reallocated_sector_ct", "current_pending_sector",
                       "offline_uncorrectable", "reported_uncorrect") and raw_value and raw_value > 0:
                add_alert(record, "WARNING", "ATA media error attribute",
                          str(entry["name"]) + " reports " + str(raw_value) + ".")
            if key in ("ssd_life_left", "percent_lifetime_remain",
                       "percent_lifetime_remaining") and val is not None and 0 <= val <= 100:
                metric(record, "estimated_lifetime_left", val, "%",
                       "Manufacturer-normalized ATA indicator; vendor-dependent")
            if key in ("total_lbas_written", "host_writes_32mib"):
                # Units vary by manufacturer; retain raw without falsely labeling TBW.
                metric(record, key, raw_value, "vendor-specific")
        atemp = number(sget(raw, "temperature", "current"))
        if atemp is not None:
            metric(record, "temperature_c", atemp, "°C")
            if atemp >= 70:
                add_alert(record, "WARNING", "High drive temperature",
                          "Current temperature at least 70°C.")
        for source, name in (("power_on_time", "power_on_hours"),
                             ("power_cycle_count", "power_cycles")):
            val = number(sget(raw, source, "hours" if source == "power_on_time" else "value"))
            if val is not None:
                metric(record, name, val)
        log = raw.get("ata_smart_error_log") or {}
        count = number(sget(log, "summary", "count"))
        if count is not None:
            metric(record, "error_log_entries", count)
            if count > 0:
                add_alert(record, "WARNING", "ATA error log",
                          "SMART ATA error log has one or more entries.")
        record["errors"] = sget(log, "summary", "table", default=[])[:20]
        record["self_tests"] = sget(raw, "ata_smart_self_test_log", "standard",
                                    "table", default=[])[:20]
    if record["status"] == "UNKNOWN" and not record["metrics"]:
        record["note"] = "No readable SMART details; cannot assess SSD wear."
    for alert in record["alerts"]:
        if SEVERITY[alert["severity"]] > SEVERITY[record["status"]]:
            record["status"] = alert["severity"]
    enrich(record, raw)
    return record


def mval(rec: dict, key: str) -> Any:
    value = sget(rec, "metrics", key)
    return value.get("value") if isinstance(value, dict) else value


def add_trend_alerts(rec: dict, prev: dict | None) -> None:
    if not prev:
        return
    for key, label in (("media_errors", "Media errors"),
                       ("error_log_entries", "Error log entries"),
                       ("unsafe_shutdowns", "Unsafe shutdowns")):
        a, b = number(mval(rec, key)), number(mval(prev, key))
        if a is not None and b is not None and a > b:
            add_alert(rec, "WARNING", label + " increased",
                      "New SMART events since previous snapshot: +" + str(a-b))
            if rec["status"] != "FAILING":
                rec["status"] = "WARNING"
    before, after = number(mval(prev, "estimated_lifetime_left")), number(mval(rec, "estimated_lifetime_left"))
    if before is not None and after is not None and after > before + 5:
        add_alert(rec, "WARNING", "Endurance indicator reset or changed",
                  "Large lifetime increase may reflect device replacement or firmware differences.")
        if rec["status"] != "FAILING":
            rec["status"] = "WARNING"


def diskutil_devices() -> list[str]:
    code, stdout, _ = call(["diskutil", "list", "-plist"])
    if code != 0:
        return []
    try:
        data = plistlib.loads(stdout.encode())
    except (ValueError, TypeError, plistlib.InvalidFileException):
        return []
    result = []
    for disk in data.get("WholeDisks", []):
        if not isinstance(disk, str) or not disk.startswith("disk") or not disk[4:].isdigit():
            continue
        status, output, _ = call(["diskutil", "info", "-plist", disk])
        if status != 0:
            continue
        try:
            details = plistlib.loads(output.encode())
        except (ValueError, TypeError, plistlib.InvalidFileException):
            continue
        if details.get("VirtualOrPhysical") == "Virtual":
            continue
        if details.get("WholeDisk") is False:
            continue
        result.append("/dev/" + disk)
    return result


def discover() -> list[str]:
    result: list[str] = []
    if shutil.which("smartctl"):
        _, output, _ = call(["smartctl", "--scan-open", "-j"])
        try:
            scanned = json.loads(output)
            for entry in scanned.get("devices", []):
                name = entry.get("name", "")
                if isinstance(name, str) and name.startswith("/dev/"):
                    result.append(name)
        except (ValueError, AttributeError):
            pass
    return list(dict.fromkeys(result + diskutil_devices()))


def collect(device: str) -> dict:
    rc, stdout, stderr = call(["smartctl", "-a", "-j", device], 30)
    try:
        data = json.loads(stdout)
        if not isinstance(data, dict):
            raise ValueError("Expected JSON object")
        rec = assess(data, device)
        if "nvme_smart_health_information_log" not in data and "ata_smart_attributes" not in data:
            rec["note"] = "Detailed SMART not exposed by controller/driver."
        rec["smartctl_exit_status"] = rc
        return rec
    except ValueError:
        return {
            "device": device, "name": "Unknown", "serial": "", "protocol": "Unknown",
            "status": "UNKNOWN", "metrics": {}, "alerts": [], "attributes": [],
            "errors": [], "self_tests": [], "collected_at": datetime.now(timezone.utc).isoformat(),
            "source": "smartctl", "evidence_available": False,
            "note": (stderr or stdout or "smartctl unavailable/permission denied")[:500]
        }


def key_for(rec: dict) -> str:
    identifier = rec.get("serial") or rec.get("device", "unknown")
    return hashlib.sha256(str(identifier).encode()).hexdigest()[:20]


def history_path(folder: Path, rec: dict) -> Path:
    return folder / (key_for(rec) + ".jsonl")


def load_history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines()[-MAX_HISTORY_POINTS:]:
        try:
            data = json.loads(line)
            if isinstance(data, dict):
                rows.append(data)
        except ValueError:
            continue
    return rows


def snapshot(rec: dict) -> dict:
    return {
        "at": rec["collected_at"], "device": rec["device"], "name": rec["name"],
        "status": rec["status"], "metrics": {key: val.get("value") for key, val in rec["metrics"].items()},
        "attributes": [
            {"id": a.get("id"), "name": a.get("name"), "value": a.get("value"), "raw": a.get("raw")}
            for a in rec.get("attributes", [])
        ]
    }


def save_history(path: Path, rec: dict) -> list[dict]:
    path.parent.mkdir(parents=True, exist_ok=True)
    old = load_history(path)
    snap = snapshot(rec)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snap, ensure_ascii=False) + "\n")
    return (old + [snap])[-MAX_HISTORY_POINTS:]


def report_rows(rec: dict) -> list[tuple[str, str, str, str, str]]:
    device = rec.get("name") or rec["device"]
    rows = [("SSD Deep", device + " SMART telemetry",
             "INFO" if rec["status"] == "UNKNOWN" else
             "PASS" if rec["status"] == "OK" else
             "WARN" if rec["status"] == "WARNING" else "FAIL",
             rec["status"], rec.get("note", "Assessment from accessible SMART attributes."))]
    for title, key, unit in (
        ("Estimated endurance remaining", "estimated_lifetime_left", "%"),
        ("Total written", "total_written_tb", "TB"),
        ("Total read", "total_read_tb", "TB"),
        ("Temperature", "temperature_c", "°C"),
        ("Power-on hours", "power_on_hours", "hours"),
        ("Media errors", "media_errors", ""),
        ("Error log entries", "error_log_entries", ""),
        ("Unsafe shutdowns", "unsafe_shutdowns", ""),
        ("Available spare", "available_spare", "%")):
        val = mval(rec, key)
        if val is not None:
            rows.append(("SSD Deep", device + " " + title, "INFO", str(val) + unit,
                         sget(rec, "metrics", key, "note", default="SMART telemetry")))
    if rec.get("diagnostic_signal_score") is not None:
        rows.append(("SSD Deep", device + " Diagnostic signal score", "INFO",
                     str(rec["diagnostic_signal_score"]) + "/100",
                     "Explainable SMART diagnostic indicator, not manufacturer health or failure prediction."))
    rows.append(("SSD Deep", device + " Evidence confidence", "INFO",
                 rec.get("evidence_confidence", "UNAVAILABLE"), "Based on readable SMART attribute coverage."))
    for alert in rec["alerts"]:
        rows.append(("SSD Deep", device + " " + alert["title"],
                     "FAIL" if alert["severity"] == "FAILING" else "WARN",
                     alert["severity"], alert["detail"]))
    return rows


def sparkline(rows: list[dict], key: str) -> str:
    values = []
    for row in rows[-40:]:
        raw = number(sget(row, "metrics", key))
        if raw is not None:
            values.append(float(raw))
    if len(values) < 2:
        return "<span class='quiet'>Not enough historical snapshots</span>"
    low, high = min(values), max(values)
    span = max(high - low, .000001)
    pts = " ".join(f"{10+i*480/(len(values)-1):.1f},{105-(v-low)/span*85:.1f}" for i, v in enumerate(values))
    return (f"<svg viewBox='0 0 500 120' role='img' aria-label='{html.escape(key)} trend'>"
            f"<polyline points='{pts}' fill='none' stroke='#60a5fa' stroke-width='3'/>"
            "</svg>")


def html_report(records: list[dict], histories: dict[str, list[dict]]) -> str:
    esc = lambda value: html.escape(str(value), quote=True)
    panels = []
    for rec in records:
        cards = []
        metrics = [
            ("Endurance remaining", "estimated_lifetime_left", "%"),
            ("Written", "total_written_tb", " TB"),
            ("Read", "total_read_tb", " TB"),
            ("Temperature", "temperature_c", " °C"),
            ("Power-on", "power_on_hours", " h"),
            ("Media errors", "media_errors", ""),
            ("Unsafe shutdowns", "unsafe_shutdowns", ""),
            ("Available spare", "available_spare", "%"),
        ]
        for name, key, suffix in metrics:
            val = mval(rec, key)
            cards.append(f"<div class='metric'><small>{esc(name)}</small><b>{esc(val) if val is not None else 'N/A'}{suffix if val is not None else ''}</b></div>")
        attrs = "".join(
            "<tr>" + "".join(f"<td>{esc(attr.get(k,''))}</td>" for k in ("id", "name", "value", "worst", "threshold", "raw")) + "</tr>"
            for attr in rec["attributes"]
        )
        alerts = "".join(f"<li><strong>{esc(a['severity'])}: {esc(a['title'])}</strong> — {esc(a['detail'])}</li>" for a in rec["alerts"])
        important = "".join("<tr><td>" + esc(v.get("name", "")) + "</td><td>" +
                            esc(v.get("group", "")) + "</td><td>" +
                            esc(v.get("status", "")) + "</td><td>" +
                            esc(v.get("distance_to_threshold_percent", "N/A")) +
                            "</td></tr>" for v in rec.get("important_indicators", []))
        signal = rec.get("diagnostic_signal_score")
        signal_text = "N/A" if signal is None else str(signal) + "/100 (diagnostic signal, not SSD life)"
        history = histories.get(key_for(rec), [])
        panels.append(
            f"<section><div class='head'><div><h2>{esc(rec['name'])}</h2><p>{esc(rec['device'])} · {esc(rec['protocol'])} · {esc(rec.get('firmware',''))}</p></div>"
            f"<strong class='state {esc(rec['status'].lower())}'>{esc(rec['status'])}</strong></div>"
            f"<div class='metrics'>{''.join(cards)}</div>"
            f"<p><b>Evidence confidence:</b> {esc(rec.get('evidence_confidence','UNAVAILABLE'))} · "
            f"<b>SMART diagnostic signal:</b> {esc(signal_text)}</p>"
            f"<h3>Important health indicators</h3><div class='scroll'><table><tr><th>Indicator</th><th>Group</th><th>Status</th><th>Distance to threshold %</th></tr>{important}</table></div>"
            f"<p class='quiet'>{esc(rec.get('note','SMART attributes are device-dependent.'))}</p>"
            f"<h3>Problems and warnings</h3>{'<ul>'+alerts+'</ul>' if alerts else '<p>No warning raised from available attributes.</p>'}"
            f"<h3>Endurance history</h3>{sparkline(history, 'estimated_lifetime_left')}"
            f"<h3>Media errors history</h3>{sparkline(history, 'media_errors')}"
            f"<h3>SMART attributes</h3><div class='scroll'><table><tr><th>ID</th><th>Name</th><th>Value</th><th>Worst</th><th>Threshold</th><th>Raw</th></tr>{attrs}</table></div>"
            f"<details><summary>Self-test log ({len(rec['self_tests'])} entries)</summary><pre>{esc(json.dumps(rec['self_tests'],indent=2,ensure_ascii=False))}</pre></details>"
            f"<details><summary>Drive error log ({len(rec['errors'])} entries)</summary><pre>{esc(json.dumps(rec['errors'],indent=2,ensure_ascii=False))}</pre></details>"
            "</section>"
        )
    return """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MacBook Verify | SSD Deep Health</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#0b1220;color:#e8efff;font:15px -apple-system,system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:32px}header,section{background:#151f33;border:1px solid #31415a;border-radius:18px;padding:24px;margin:16px 0}
h1{font-size:30px;margin:0 0 8px}h2{margin:0 0 6px}.quiet,p,small{color:#a9bad7}.head{display:flex;justify-content:space-between;gap:14px;align-items:center}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:10px;margin:20px 0}
.metric{background:#202e47;padding:15px;border-radius:12px}.metric small{display:block}.metric b{display:block;font-size:22px;margin-top:8px}
.state{border-radius:999px;padding:9px 14px;background:#334155}.ok{background:#14532d}.warning{background:#854d0e}.failing{background:#991b1b}
.scroll{overflow:auto}table{width:100%;border-collapse:collapse}td,th{padding:9px;border-bottom:1px solid #334155;text-align:left}
svg{width:100%;height:100px;background:#0c1829;border-radius:12px}pre{white-space:pre-wrap;word-wrap:break-word}
a{color:#93c5fd}li{padding:4px}footer{color:#a9bad7;font-size:13px}
</style></head><body><main><header><h1>SSD Deep Health</h1><p>MacBook Verify — offline DriveDx-style telemetry and trends</p>
<p>SMART missing ≠ SSD healthy. Endurance remaining is a vendor estimate, not a reliability guarantee.</p></header>""" + (
        "".join(panels) if panels else "<section><h2>SSD telemetry unavailable</h2><p>Install Python 3 and smartmontools, or review the built-in macOS SMART and I/O integrity checks. Apple Silicon may not expose advanced NVMe telemetry.</p></section>"
    ) + """<footer>Evidence is collected locally. SMART self-tests are not launched automatically. Avoid publicly sharing serial numbers in JSON reports.</footer></main></body></html>"""


def run_once(args: argparse.Namespace) -> tuple[list[dict], dict[str, list[dict]]]:
    out = Path(args.out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    history_dir = Path(args.history_dir).expanduser() if args.history_dir else Path.home() / ".macbook-verify" / "ssd-history"
    if args.fixture:
        fixture_data = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
        records = [assess(fixture_data, args.device or "fixture")]
    elif not shutil.which("smartctl"):
        records = []
    else:
        devices = [args.device] if args.device else discover()
        records = [collect(device) for device in devices]
    histories = {}
    rows = []
    for rec in records:
        hpath = history_path(history_dir, rec)
        before = load_history(hpath)
        prev = before[-1] if before else None
        add_trend_alerts(rec, prev)
        comparison_alerts(rec, prev)
        try:
            histories[key_for(rec)] = save_history(hpath, rec)
        except OSError as exc:
            rec["history_warning"] = str(exc)
            histories[key_for(rec)] = before
        rows.extend(report_rows(rec))
    if not records:
        reason = "smartctl not found" if not shutil.which("smartctl") and not args.fixture else "No readable physical drives"
        rows.append(("SSD Deep", "Advanced SMART", "INFO", "Unavailable", reason))
    (out / "ssd-report.json").write_text(json.dumps({
        "tool": "MacBook Verify SSD Deep", "version": VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "records": records}, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "ssd-report.html").write_text(html_report(records, histories), encoding="utf-8")
    (out / "ssd-results.tsv").write_text("".join(
        "\t".join(str(c).replace("\t", " ").replace("\n", " ") for c in row) + "\n"
        for row in rows), encoding="utf-8")
    return records, histories


def notify(text: str) -> None:
    if sys.platform == "darwin" and shutil.which("osascript"):
        # AppleScript quoted strings; notifications only in explicitly enabled monitor mode.
        call(["osascript", "-e", "display notification " + json.dumps(text) +
              " with title \"MacBook Verify SSD\""], timeout=10)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline DriveDx-style SMART diagnostics")
    parser.add_argument("--out-dir", required=True, help="Report output directory")
    parser.add_argument("--history-dir", help="Persistent local history directory")
    parser.add_argument("--device", help="Explicit /dev/diskN or other supported disk path")
    parser.add_argument("--fixture", help=argparse.SUPPRESS)
    parser.add_argument("--monitor", action="store_true", help="Foreground periodic SMART monitoring")
    parser.add_argument("--interval", type=int, default=300, help="Monitoring interval in seconds (>= 30)")
    parser.add_argument("--iterations", type=int, default=0, help="0 = until interrupted")
    parser.add_argument("--notify", action="store_true", help="macOS alerts on changed WARNING/FAILING status")
    parser.add_argument("--notify-changes", action="store_true",
                        help="For one-shot scheduled runs: warn only on newly detected problems")
    parser.add_argument("--self-test", choices=("short", "long"),
                        help="Explicitly request a firmware SMART self-test; needs --device")
    args = parser.parse_args(argv)
    if args.self_test:
        if not args.device or not args.device.startswith("/dev/"):
            parser.error("--self-test requires explicit --device /dev/diskN")
        if not shutil.which("smartctl"):
            parser.error("smartctl is required for firmware self-test")
        rc, out, err = call(["smartctl", "-t", args.self_test, args.device], 30)
        print(out or err)
        return 0 if rc == 0 else 1
    if args.monitor and args.interval < 30:
        parser.error("--interval must be >= 30 seconds")
    count = 0
    previous_states: dict[str, str] = {}
    while True:
        records, _ = run_once(args)
        for rec in records:
            print(rec["device"], rec["status"], json.dumps({
                "life_left": mval(rec, "estimated_lifetime_left"),
                "written_tb": mval(rec, "total_written_tb"),
                "temperature_c": mval(rec, "temperature_c")}))
            identity = key_for(rec)
            status = rec["status"]
            if args.notify_changes and status in ("WARNING", "FAILING"):
                history = load_history(history_path(
                    Path(args.history_dir).expanduser() if args.history_dir else
                    Path.home() / ".macbook-verify" / "ssd-history", rec))
                prior = history[-2] if len(history) > 1 else None
                if prior is None or prior.get("status") != status or any(
                    "increased" in a["title"] or "degraded" in a["title"] for a in rec["alerts"]
                ):
                    notify(rec["name"] + ": " + status + "; review SSD report")
            if args.monitor and args.notify and status in ("WARNING", "FAILING") and (
                previous_states.get(identity) != status or any("increased" in a["title"] for a in rec["alerts"])
            ):
                notify(rec["name"] + ": " + status + "; review SSD report")
            previous_states[identity] = status
        count += 1
        if not args.monitor or (args.iterations and count >= args.iterations):
            break
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
