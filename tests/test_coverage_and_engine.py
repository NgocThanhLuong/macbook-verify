#!/usr/bin/env python3
"""Device provenance, Apple coverage and diagnostic risk tests (offline only)."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import apple_coverage as coverage
import ssd_diagnostics as ssd
import ssd_health_engine as engine


class CoverageTests(unittest.TestCase):
    SERIAL = "F123456789"

    def test_no_invented_manufacture_date_for_random_serial(self):
        result = coverage.classify_serial(self.SERIAL)
        self.assertIsNone(result["manufacture_date"])
        self.assertTrue(result["format"].startswith("randomized"))

    def test_model_year_is_not_production_date(self):
        model = coverage.model_metadata("MacBookPro18,1", ROOT / "data" / "models.tsv")
        self.assertEqual(model["model_year"], 2021)
        with tempfile.TemporaryDirectory() as temp:
            result = coverage.generate_report(self.SERIAL, model, None, Path(temp))
            self.assertEqual(result["model_year"], 2021)
            self.assertFalse(result["model_year_is_manufacture_year"])
            self.assertIsNone(result["manufacture_date"])
            self.assertIsNone(result["activation_date"])
            self.assertIsNone(result["warranty_expires"])
            self.assertEqual(result["coverage_status"], "UNVERIFIED")
            html_content = (Path(temp) / "apple-coverage.html").read_text()
            self.assertIn("Copy serial", html_content)
            self.assertIn("checkcoverage.apple.com", html_content)

    def test_import_requires_matching_serial(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "record.json"
            p.write_text(json.dumps({
                "serial": "DIFFERENT1", "source": "user_supplied",
                "warranty_expires": "2027-05-01"
            }))
            with self.assertRaises(ValueError):
                coverage.import_record(p, self.SERIAL)

    def test_import_dates_never_claim_apple_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "record.json"
            p.write_text(json.dumps({
                "serial": self.SERIAL, "source": "apple_coverage_user_capture",
                "warranty_expires": "2027-06-15", "coverage_type": "Limited Warranty"
            }))
            record = coverage.import_record(p, self.SERIAL)
            self.assertFalse(record["verified_by_tool"])
            self.assertIsNone(record["activation_date"])
            self.assertEqual(record["warranty_expires"], "2027-06-15")

    def test_coverage_import_cannot_fake_activation_from_apple(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "record.json"
            p.write_text(json.dumps({
                "serial": self.SERIAL, "source": "apple_coverage_user_capture",
                "activation_date": "2026-01-01"
            }))
            with self.assertRaises(ValueError):
                coverage.import_record(p, self.SERIAL)

    def test_invalid_dates_and_untrusted_manufacture_date(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "record.json"
            p.write_text(json.dumps({
                "serial": self.SERIAL, "source": "user_supplied",
                "manufacture_date": "2021-10-07"
            }))
            with self.assertRaises(ValueError):
                coverage.import_record(p, self.SERIAL)
            p.write_text(json.dumps({
                "serial": self.SERIAL, "source": "receipt",
                "manufacture_date": "2021-99-99"
            }))
            with self.assertRaises(ValueError):
                coverage.import_record(p, self.SERIAL)

    def test_copied_apple_page_expiry_is_only_user_supplied(self):
        data = coverage.import_clipboard_text(
            "MacBook Pro 16-inch\nValid Purchase Date\nLimited Warranty\nExpires June 30, 2027",
            self.SERIAL
        )
        self.assertEqual(data["warranty_expires"], "2027-06-30")
        self.assertIsNone(data["activation_date"])
        self.assertEqual(data["source"], "apple_coverage_user_capture")

    def test_cli_json_import_and_local_storage(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            p = root / "record.json"
            p.write_text(json.dumps({
                "serial": self.SERIAL, "source": "apple_coverage_user_capture",
                "warranty_expires": "2027-05-01"
            }))
            args = ["--serial", self.SERIAL, "--model-identifier", "MacBookPro18,1",
                    "--out-dir", str(root / "out"), "--cache-dir", str(root / "cache"),
                    "--import-json", str(p)]
            self.assertEqual(coverage.main(args), 0)
            data = json.loads((root / "out" / "apple-coverage.json").read_text())
            self.assertEqual(data["warranty_expires"], "2027-05-01")
            self.assertFalse(data["verified_by_tool"])
            self.assertEqual(coverage.main(args[:-2]), 0)  # uses local saved record

    def test_serial_validation(self):
        for bad in ("", "../../etc/passwd", "A B C", "ABCDEFGHIJKLMNO"):
            with self.assertRaises(ValueError):
                coverage.validate_serial(bad)


class SSDEngineTests(unittest.TestCase):
    def nvme(self, **kwargs):
        log = dict(
            critical_warning=0, percentage_used=10, available_spare=95,
            available_spare_threshold=10, media_errors=0,
            data_units_written=2000000, temperature=39, power_on_hours=100
        )
        log.update(kwargs)
        return dict(
            model_name="APPLE SSD", smart_status={"passed": True},
            nvme_smart_health_information_log=log
        )

    def test_nvme_diagnostic_score_is_not_endurance_percent(self):
        rec = ssd.assess(self.nvme())
        self.assertEqual(rec["evidence_confidence"], "DETAILED")
        self.assertIsNotNone(rec["diagnostic_signal_score"])
        self.assertNotEqual(rec["diagnostic_signal_score"], ssd.mval(rec, "estimated_lifetime_left"))
        self.assertIn("not failure probability", rec["interpretation"])

    def test_unavailable_data_has_no_fake_health_rating(self):
        rec = ssd.assess({"model_name": "controller only"})
        self.assertEqual(rec["evidence_confidence"], "UNAVAILABLE")
        self.assertIsNone(rec["diagnostic_signal_score"])
        self.assertIsNone(rec["performance_rating"])

    def test_ata_relative_health_near_threshold_warns(self):
        rec = ssd.assess({
            "smart_status": {"passed": True},
            "ata_smart_attributes": {"table": [{
                "id": 5, "name": "Reallocated_Sector_Ct", "value": 12,
                "thresh": 10, "worst": 12, "raw": {"value": 0}
            }]}
        })
        self.assertTrue(any(x["status"] == "WARNING" for x in rec["important_indicators"]))

    def test_increasing_ata_critical_counter_flagged(self):
        prev = {
            "attributes": [{"id": 5, "name": "Reallocated_Sector_Ct", "raw": 1, "value": 100}]
        }
        rec = ssd.assess({
            "smart_status": {"passed": True},
            "ata_smart_attributes": {"table": [{
                "id": 5, "name": "Reallocated_Sector_Ct", "raw": {"value": 3},
                "value": 99, "worst": 99, "thresh": 10
            }]}
        })
        engine.comparison_alerts(rec, prev)
        self.assertTrue(any("counter increased" in a["title"] for a in rec["alerts"]))

    def test_ata_history_saved_attribute_values(self):
        rec = ssd.assess({
            "smart_status": {"passed": True},
            "ata_smart_attributes": {"table": [{
                "id": 197, "name": "Current_Pending_Sector",
                "value": 100, "thresh": 0, "raw": {"value": 0}
            }]}
        })
        self.assertIn("attributes", ssd.snapshot(rec))


if __name__ == "__main__":
    unittest.main()
