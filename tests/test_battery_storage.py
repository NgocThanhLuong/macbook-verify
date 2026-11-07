#!/usr/bin/env python3
"""Battery controller + non-destructive SSD I/O validation (synthetic fixtures)."""
import json
import os
from pathlib import Path
import plistlib
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import battery_diagnostics as batt
import storage_probe as probe


def battery(**overrides):
    d = {
        "DesignCapacity": 6500,
        "NominalChargeCapacity": 5850,
        "AppleRawMaxCapacity": 5700,
        "FullChargeCapacity": 5840,
        "CurrentCapacity": 72,
        "CycleCount": 175,
        "Voltage": 11900,
        "InstantAmperage": 1000,
        "IsCharging": True,
        "ExternalConnected": True,
        "Temperature": 2980,
        "Qmax": [5100, 5060, 5080],
        "CellVoltage": [3961, 3967, 3960],
        "PermanentFailureStatus": 0,
        "BatteryCellDisconnectCount": 0,
    }
    d.update(overrides)
    return d


class BatteryTests(unittest.TestCase):
    def test_capacity_nominal_and_raw_are_distinct(self):
        result = batt.assess(battery(), "90%", "Normal")
        cap = result["capacity"]
        self.assertEqual(cap["nominal_health_percent"], 90)
        self.assertEqual(cap["raw_health_percent"], 87.69)
        self.assertEqual(cap["capacity_health_percent"], 90)
        self.assertEqual(cap["macos_reported_health_percent"], 90)
        self.assertEqual(result["charging"]["charge_percent"], 72)
        self.assertEqual(result["cells"]["voltage_delta_mv"], 7)
        self.assertEqual(result["evidence_confidence"], "HIGH")

    def test_health_unavailable_no_fabricated_percentage(self):
        result = batt.assess({"CycleCount": 1, "MaxCapacity": 100})
        self.assertIsNone(result["capacity"]["capacity_health_percent"])
        self.assertIsNone(result["capacity"]["raw_health_percent"])
        self.assertIsNone(result["diagnostic_signal_score"])
        self.assertEqual(result["status"], "UNAVAILABLE")

    def test_permanent_failure_flag(self):
        result = batt.assess(battery(PermanentFailureStatus=8))
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["diagnostic_signal_score"], 0)

    def test_low_health_warning(self):
        result = batt.assess(battery(NominalChargeCapacity=4800, AppleRawMaxCapacity=4600))
        self.assertEqual(result["status"], "WARN")
        self.assertTrue(any(x["reason"].startswith("Low measured") for x in result["alerts"]))

    def test_cell_imbalance_warning(self):
        result = batt.assess(battery(CellVoltage=[3900, 3980, 3910]))
        self.assertEqual(result["status"], "WARN")
        self.assertEqual(result["cells"]["voltage_delta_mv"], 80)

    def test_qmax_imbalance_warning(self):
        result = batt.assess(battery(Qmax=[5000, 5700, 4700]))
        self.assertEqual(result["status"], "WARN")

    def test_battery_disconnected_flag_not_proof_of_repair(self):
        result = batt.assess(battery(BatteryCellDisconnectCount=2))
        self.assertTrue(any(x["severity"] == "INFO" for x in result["alerts"]))
        self.assertNotEqual(result["status"], "FAIL")

    def test_large_health_jump_only_review(self):
        old = [{"capacity_health_percent": 95}]
        current = batt.assess(battery())
        batt.trend_alerts(current, old)
        self.assertEqual(current["status"], "INFO")  # 95 -> 90 is exactly five, no warning
        old = [{"capacity_health_percent": 98}]
        batt.trend_alerts(current, old)
        self.assertEqual(current["status"], "WARN")

    def test_signed_64_amperage(self):
        raw = battery(InstantAmperage=2**64-850)
        report = batt.assess(raw)
        self.assertEqual(report["charging"]["instant_current_ma"], -850)
        self.assertLess(report["charging"]["approx_battery_power_w"], 0)

    def test_source_plist_parse(self):
        data = battery()
        record = batt.parse_plist(plistlib.dumps([data]))
        self.assertEqual(record["DesignCapacity"], 6500)

    def test_parse_macos_power_report(self):
        health, condition = batt.parse_system_health(
            "Cycle Count: 175\n  Condition: Normal\n  Maximum Capacity: 90%\n")
        self.assertEqual(health, "90%")
        self.assertEqual(condition, "Normal")

    def test_fixture_cli_and_html(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            fixture = base / "fixture.json"
            fixture.write_text(json.dumps(battery()))
            out = base / "out"
            rc = batt.main(["--fixture-json", str(fixture), "--out-dir", str(out),
                            "--history-dir", str(base / "history")])
            self.assertEqual(rc, 0)
            report = json.loads((out / "battery-report.json").read_text())
            self.assertEqual(report["capacity"]["nominal_health_percent"], 90)
            self.assertIn("Battery Deep Diagnostics", (out / "battery-report.html").read_text())
            self.assertIn("Nominal capacity health", (out / "battery-results.tsv").read_text())


class StorageProbeTests(unittest.TestCase):
    def test_sha256_write_read_and_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            data = probe.measure(2, base)
            self.assertEqual(data["status"], "PASS")
            self.assertEqual(data["bytes_verified"], 2 * 1024 * 1024)
            self.assertIsNotNone(data["write_latency_p95_ms"])
            self.assertFalse(data["compressed_test_data"])
            self.assertFalse(list(base.glob(".mbv-ssd-probe-*")))

    def test_rejects_oversized_probe(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                probe.measure(99999, Path(folder))

    def test_probe_json_report(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            rc = probe.main(["--size-mib", "2", "--scratch-dir", str(base),
                             "--out-dir", str(base / "result"),
                             "--history-dir", str(base / "history")])
            self.assertEqual(rc, 0)
            report = json.loads((base / "result" / "ssd-io-probe.json").read_text())
            self.assertEqual(report["status"], "PASS")
            self.assertIn("PASS", (base / "result" / "ssd-io-probe.tsv").read_text())

    def test_percentiles(self):
        self.assertEqual(probe.percentile([1.5, 4.0, 2.0], .5), 2.0)
        self.assertIsNone(probe.percentile([], .99))


if __name__ == "__main__":
    unittest.main()
