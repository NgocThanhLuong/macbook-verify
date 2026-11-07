#!/usr/bin/env python3
"""Offline coverage for MacBook Verify v2.0 professional inspector."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import pro_inspection as pro
import compare_macs as cmp
import battery_discharge as discharge


FIXTURE={
    "SPHardwareDataType":[{
        "chip_type":"Apple M1 Max","number_cores":"10","physical_memory":"64 GB",
        "machine_model":"MacBookPro18,1","serial_number":"SAMPLE_SERIAL",
        "boot_rom_version":"2021.0"
    }],
    "SPDisplaysDataType":[{
        "_name":"Apple M1 Max","sppci_model":"Apple M1 Max",
        "spdisplays_gpu_cores":"32","spdisplays_metal":"Metal 3",
        "spdisplays_ndrvs":[{"_name":"Liquid Retina XDR",
                              "spdisplays_resolution":"3456 x 2234"}]
    }],
    "SPNVMeDataType":[{"_name":"APPLE SSD AP1024","size":"1 TB",
                        "smart_status":"Verified"}]
}


class ProInspectorTests(unittest.TestCase):
    def test_hardware_and_gpu_are_from_profiler(self):
        hw=pro.first_item(FIXTURE,"SPHardwareDataType")
        self.assertEqual(hw["number_cores"],"10")
        gpu=pro.gpu_metrics(FIXTURE)
        self.assertEqual(gpu["devices"][0]["cores"],"32")
        self.assertEqual(gpu["devices"][0]["name"],"Apple M1 Max")

    def test_nested_system_info_field_translation(self):
        values=pro.flatten(FIXTURE["SPDisplaysDataType"])
        self.assertTrue(any("Số lõi GPU" in key for key,_ in values))
        self.assertTrue(any("3456 x 2234" in value for _,value in values))

    def test_escapes_untrusted_devices(self):
        fixture=json.loads(json.dumps(FIXTURE))
        fixture["SPDisplaysDataType"][0]["_name"]="<img src=x onerror=alert(1)>"
        report={"cpu":{"chip":"Apple M1 Max","cores":"10"},"gpu":pro.gpu_metrics(fixture),
                "hardware":pro.first_item(fixture,"SPHardwareDataType"),
                "security":{"macos":"26"},"checks":[],
                "system_profiler":fixture}
        page=pro.html_overview(report)
        self.assertNotIn("<img src=x onerror",page)
        self.assertIn("&lt;img",page)

    def test_log_match_is_not_a_hardware_failure(self):
        summary=pro.sleep_events("Entering Sleep\nWake from Standby\nSleep fail\n")
        self.assertEqual(summary["counts"]["failure_mentions"],1)
        self.assertEqual(summary["counts"]["sleep"],1)

    def test_fixture_cli_creates_vietnamese_report(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp)
            fixture=base/"profile.json"
            fixture.write_text(json.dumps(FIXTURE),encoding="utf-8")
            out=base/"output"
            code=pro.main(["--fixture-json",str(fixture),"--out-dir",str(out)])
            self.assertEqual(code,0)
            raw=json.loads((out/"system-information.json").read_text())
            self.assertEqual(raw["gpu"]["devices"][0]["cores"],"32")
            page=(out/"system-information.html").read_text()
            self.assertIn("CPU / Bộ xử lý",page)
            self.assertIn("GPU / Đồ họa",page)
            self.assertIn("Thông tin hệ thống",page)
            self.assertIn("Apple M1 Max",page)
            self.assertIn("SPNVMeDataType",raw["system_profiler"])


class ComparisonTests(unittest.TestCase):
    def example(self):
        return {"model":"MacBook Pro 16 M1 Max","chip":"M1 Max",
                "memory":"64 GB","ssd_model":"1TB SSD",
                "battery_max_capacity":"93%","battery_cycles":"222",
                "score":88,"counts":{"pass":15,"fail":0,"warn":1},
                "ssd_deep":{"total_written_tb":"12.4","evidence_confidence":"DETAILED"},
                "battery_deep":{"capacity_health_percent":"91"}}

    def test_compare_prices_and_risk_gates(self):
        a=self.example()
        b=self.example()
        b["counts"]["fail"]=1
        res=cmp.compare(a,b,{},{"checks":[{
            "area":"ownership","status":"FAIL","title":"MDM"}]},
            price_a=40_000_000,price_b=41_500_000,trade=21_675_000)
        self.assertEqual(res["items"]["Máy A"]["top_up_vnd"],18_325_000)
        self.assertEqual(res["items"]["Máy B"]["top_up_vnd"],19_825_000)
        self.assertTrue(any("MDM" in x for x in res["items"]["Máy B"]["warnings"]))
        self.assertTrue(any("Activation Lock" in x for x in res["items"]["Máy A"]["warnings"]))

    def test_interactive_compare_is_local_only(self):
        self.assertIn('type="file"',cmp.HTML)
        self.assertIn("summary.json",cmp.HTML)
        self.assertNotIn("fetch(",cmp.HTML)
        self.assertNotIn("XMLHttpRequest",cmp.HTML)

    def test_compare_cli_creates_html(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            self.assertEqual(cmp.main(["--out-dir",str(base)]),0)
            self.assertTrue((base/"compare-macs.html").is_file())


class DischargeTests(unittest.TestCase):
    def test_refuses_when_ac_connected(self):
        samples=[{"ac_connected":True,"charge_percent":90}]
        res=discharge.observe(1,15,collector=lambda:samples[0])
        self.assertEqual(res["status"],"SKIP")
        self.assertEqual(res["sample_count"],1)

    def test_refuses_low_charge(self):
        res=discharge.observe(1,15,collector=lambda:{"ac_connected":False,"charge_percent":19})
        self.assertEqual(res["status"],"SKIP")

    def test_observes_without_forcing_load(self):
        states=iter([
            {"ac_connected":False,"charge_percent":70,"status":"INFO"},
            {"ac_connected":False,"charge_percent":69,"status":"INFO"},
            {"ac_connected":False,"charge_percent":68,"status":"INFO"}
        ])
        clock=[0.]
        def now():return clock[0]
        def advance(s):clock[0]+=s
        outcome=discharge.observe(1,30,collector=lambda:next(states),
                                  sleep_fn=advance,clock=now)
        self.assertEqual(outcome["status"],"INFO")
        self.assertEqual(outcome["charge_drop_percent"],2)
        self.assertEqual(outcome["sample_count"],3)


if __name__=="__main__":
    unittest.main()
