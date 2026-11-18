#!/usr/bin/env python3
"""Offline regression tests for repair/provenance evidence assessment."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import repair_audit


def put(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


class RepairAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.raw = self.out / "raw"
        self.raw.mkdir()
        put(self.out / "system-information.json", {
            "hardware": {"serial_number": "SERIAL1234"}
        })
        put(self.out / "apple-coverage.json", {
            "serial": "SERIAL1234", "purchase_date": "2022-06-22"
        })
        put(self.out / "battery-report.json", {
            "cycles": {"count": 24},
            "capacity": {"macos_reported_health_percent": 100}
        })
        (self.raw / "mdm.txt").write_text(
            "Enrolled via DEP: No\nMDM enrollment: No\n", encoding="utf-8"
        )

    def test_low_cycle_old_battery_is_not_repair_proof(self):
        report = repair_audit.assess(
            self.out, self.raw, today=repair_audit.dt.date(2026, 11, 18))
        plausibility = [x for x in report["checks"] if "ít chu kỳ" in x["title"]]
        self.assertEqual(len(plausibility), 1)
        self.assertEqual(plausibility[0]["status"], "INFO")
        self.assertFalse(report["has_verified_repair"])
        self.assertFalse(any(x["status"] == "FAIL" for x in report["checks"]))

    def test_mdm_enrolled_is_failure(self):
        (self.raw / "mdm.txt").write_text(
            "Enrolled via DEP: Yes\nMDM enrollment: Yes\n", encoding="utf-8")
        report = repair_audit.assess(self.out, self.raw)
        self.assertTrue(any(x["status"] == "FAIL" and "MDM" in x["title"]
                            for x in report["checks"]))

    def test_serial_disagreement_is_failure(self):
        put(self.out / "apple-coverage.json", {"serial": "OTHERSERIAL"})
        report = repair_audit.assess(self.out, self.raw)
        self.assertTrue(any(x["status"] == "FAIL" and "Serial" in x["title"]
                            for x in report["checks"]))

    def test_previous_summary_cycle_reset(self):
        prior = self.out / "previous.json"
        put(prior, {"serial": "SERIAL1234", "battery_cycles": "179",
                    "battery_max_capacity": "89%"})
        report = repair_audit.assess(self.out, self.raw, prior)
        self.assertTrue(any(x["status"] == "WARN" and "Chu kỳ pin giảm" in x["title"]
                            for x in report["checks"]))

    def test_health_drop_is_warning_not_repair_conclusion(self):
        put(self.out / "battery-report.json", {
            "cycles": {"count": 179},
            "capacity": {"macos_reported_health_percent": 89}
        })
        prior = self.out / "previous.json"
        put(prior, {"serial": "SERIAL1234", "battery_cycles": 147,
                    "battery_max_capacity": "97%"})
        report = repair_audit.assess(self.out, self.raw, prior)
        self.assertTrue(any(x["status"] == "WARN" and "Sức khỏe pin" in x["title"]
                            for x in report["checks"]))
        self.assertFalse(report["has_verified_repair"])

    def test_different_serial_does_not_compare_batteries(self):
        prior = self.out / "previous.json"
        put(prior, {"serial": "DIFFERENT", "battery_cycles": 2000,
                    "battery_max_capacity": "95%"})
        report = repair_audit.assess(self.out, self.raw, prior)
        self.assertFalse(any("Chu kỳ pin giảm" in x["title"]
                             for x in report["checks"]))

    def test_reports_written_without_device_or_network_calls(self):
        with patch.object(sys, "argv", ["repair_audit.py", "--out-dir",
                                        str(self.out), "--raw-dir", str(self.raw)]):
            self.assertEqual(repair_audit.main(), 0)
        self.assertTrue((self.out / "repair-audit.json").is_file())
        self.assertTrue((self.out / "repair-audit.html").is_file())
        self.assertTrue((self.out / "repair-audit.tsv").is_file())
        page = (self.out / "repair-audit.html").read_text(encoding="utf-8")
        self.assertIn("Parts & Service", page)
        self.assertIn("repair-manual-observation.json", page)


if __name__ == "__main__":
    unittest.main()
