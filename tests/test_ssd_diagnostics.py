#!/usr/bin/env python3
"""Offline unit tests using synthetic SMART telemetry. No real drive accessed."""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ssd_diagnostics as ssd


def nvme(**changes):
    log = dict(
        critical_warning=0, temperature=38, available_spare=100,
        available_spare_threshold=10, percentage_used=12,
        data_units_written=39062500, data_units_read=78125000,
        power_cycles=50, power_on_hours=300, unsafe_shutdowns=0,
        media_errors=0, num_err_log_entries=0
    )
    log.update(changes)
    return dict(model_name="APPLE SSD AP1024", serial_number="TEST-DRIVE",
                smart_status={"passed": True}, nvme_smart_health_information_log=log)


class SmartTests(unittest.TestCase):
    def test_nvme_units_and_lifetime(self):
        drive = ssd.assess(nvme(), "/dev/disk0")
        self.assertEqual(drive["status"], "OK")
        self.assertEqual(ssd.mval(drive, "total_written_tb"), 20)
        self.assertEqual(ssd.mval(drive, "total_read_tb"), 40)
        self.assertEqual(ssd.mval(drive, "estimated_lifetime_left"), 88)
        self.assertEqual(ssd.mval(drive, "temperature_c"), 38)

    def test_missing_smart_and_wear_remain_unknown(self):
        drive = ssd.assess({"model_name": "Apple controller"}, "/dev/disk0")
        self.assertEqual(drive["status"], "UNKNOWN")
        self.assertIsNone(ssd.mval(drive, "estimated_lifetime_left"))
        self.assertIsNone(ssd.mval(drive, "total_written_tb"))

    def test_critical_warning_is_failing(self):
        drive = ssd.assess(nvme(critical_warning=1), "/dev/disk0")
        self.assertEqual(drive["status"], "FAILING")

    def test_smart_failure_is_failing(self):
        data = nvme()
        data["smart_status"]["passed"] = False
        self.assertEqual(ssd.assess(data)["status"], "FAILING")

    def test_media_errors_warning_not_automatic_failure(self):
        drive = ssd.assess(nvme(media_errors=2))
        self.assertEqual(drive["status"], "WARNING")

    def test_percentage_used_clamped(self):
        drive = ssd.assess(nvme(percentage_used=120))
        self.assertEqual(ssd.mval(drive, "estimated_lifetime_left"), 0)
        self.assertEqual(drive["status"], "WARNING")

    def test_low_spare_is_failing(self):
        self.assertEqual(ssd.assess(nvme(available_spare=7))["status"], "FAILING")

    def test_trend_alerts(self):
        previous = ssd.snapshot(ssd.assess(nvme(media_errors=0, unsafe_shutdowns=2)))
        current = ssd.assess(nvme(media_errors=1, unsafe_shutdowns=3))
        ssd.add_trend_alerts(current, previous)
        self.assertTrue(any("increased" in a["title"] for a in current["alerts"]))

    def test_ata_attributes_and_no_unjustified_tbw(self):
        raw = {
            "model_name": "SATA SSD",
            "smart_status": {"passed": True},
            "ata_smart_attributes": {"table": [
                {"id": 5, "name": "Reallocated_Sector_Ct", "value": 100,
                 "worst": 100, "thresh": 10, "raw": {"value": 2}},
                {"id": 241, "name": "Total_LBAs_Written", "value": 100,
                 "worst": 100, "thresh": 0, "raw": {"value": 500000}}
            ]}
        }
        drive = ssd.assess(raw)
        self.assertEqual(drive["status"], "WARNING")
        self.assertIsNone(ssd.mval(drive, "total_written_tb"))
        self.assertEqual(len(drive["attributes"]), 2)

    def test_html_escapes_device_strings(self):
        drive = ssd.assess(nvme())
        drive["name"] = "<script>alert(1)</script>"
        report = ssd.html_report([drive], {})
        self.assertIn("&lt;script&gt;", report)
        self.assertNotIn("<script>alert(1)</script>", report)

    def test_cli_reports_and_history(self):
        with tempfile.TemporaryDirectory() as root:
            base = pathlib.Path(root)
            fixture = base / "fixture.json"
            fixture.write_text(json.dumps(nvme()), encoding="utf-8")
            out = base / "report"
            cmd = [
                sys.executable, str(ROOT / "scripts" / "ssd_diagnostics.py"),
                "--out-dir", str(out), "--history-dir", str(base / "history"),
                "--fixture", str(fixture)
            ]
            subprocess.check_call(cmd, stdout=subprocess.DEVNULL)
            subprocess.check_call(cmd, stdout=subprocess.DEVNULL)
            data = json.loads((out / "ssd-report.json").read_text())
            self.assertEqual(data["records"][0]["status"], "OK")
            self.assertIn("SSD Deep", (out / "ssd-results.tsv").read_text())
            self.assertIn("Endurance history", (out / "ssd-report.html").read_text())
            files = list((base / "history").glob("*.jsonl"))
            self.assertEqual(len(files), 1)
            self.assertEqual(len(files[0].read_text().splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
