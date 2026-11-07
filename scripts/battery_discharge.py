#!/usr/bin/env python3
"""Opt-in bounded battery-discharge observation; does NOT actively drain battery.

Requires AC adapter disconnected before starting. Samples AppleSmartBattery
controller without changing charge limits, waking the machine or stressing CPU.
Duration 1..30 minutes; aborts if charge falls below 30% or AC is reconnected.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import html
import json
from pathlib import Path
import sys
import time

import battery_diagnostics as battery


def on_ac(data:dict)->bool|None:
    v=battery.get(data,"ExternalConnected")
    if isinstance(v,bool):
        return v
    if isinstance(v,int):
        return bool(v)
    return None


def sample()->dict:
    data,source=battery.collect()
    outcome=battery.assess(data)
    return {
        "at":datetime.now(timezone.utc).isoformat(),
        "source":source,"ac_connected":on_ac(data),
        "charge_percent":outcome["charging"]["charge_percent"],
        "voltage_mv":outcome["charging"]["voltage_mv"],
        "current_ma":outcome["charging"]["instant_current_ma"],
        "battery_power_w":outcome["charging"]["approx_battery_power_w"],
        "temperature":outcome["charging"]["temperature"],
        "capacity_health_percent":outcome["capacity"]["capacity_health_percent"],
        "status":outcome["status"],
    }


def evaluate(samples:list[dict],elapsed_sec:float,reason:str)->dict:
    known=[s for s in samples if s.get("charge_percent") is not None]
    delta=None
    slope=None
    if len(known)>1:
        a,b=known[0],known[-1]
        delta=round(float(a["charge_percent"])-float(b["charge_percent"]),2)
        if elapsed_sec>30:
            slope=round(delta/(elapsed_sec/60),2)
    warn=[]
    if slope is not None and slope>3:
        warn.append("Mức pin giảm nhanh (>3%/phút) trong lần quan sát; phụ thuộc tải và hiệu chỉnh.")
    if any(s.get("status")=="FAIL" for s in samples):
        warn.append("Controller có cờ lỗi; xem báo cáo Battery Deep.")
    return {"mode":"observational_battery_discharge","status":"WARN" if warn else
            "SKIP" if len(samples)<2 else "INFO",
            "reason":reason,"sample_count":len(samples),
            "elapsed_seconds":round(elapsed_sec,1),"charge_drop_percent":delta,
            "observed_drop_percent_per_minute":slope,
            "warnings":warn,"samples":samples,
            "disclaimer":"Không phải ước lượng chính xác thời lượng pin hay phép thử dung lượng Wh."}


def html_report(report:dict)->str:
    esc=lambda x:html.escape(str(x),quote=True)
    lines="".join("<tr><td>"+esc(x.get("at",""))+"</td><td>"+esc(x.get("charge_percent","N/A"))+
                  "</td><td>"+esc(x.get("voltage_mv","N/A"))+"</td><td>"+esc(x.get("current_ma","N/A"))+
                  "</td><td>"+esc(x.get("battery_power_w","N/A"))+"</td><td>"+esc(x.get("ac_connected","?"))+
                  "</td></tr>" for x in report.get("samples",[]))
    return ("<!doctype html><html lang='vi'><meta charset='utf-8'><title>Đánh giá pin khi xả</title>"
            "<style>body{font:15px system-ui;background:#101a2c;color:white;margin:30px}"
            "table{border-collapse:collapse;width:100%}td,th{padding:12px;border-bottom:1px solid #40516b}"
            "h1{color:#bdd6ff}</style><h1>Quan sát pin khi rút sạc</h1><p>Trạng thái: "+
            esc(report["status"])+" · "+esc(report["reason"])+"</p><p>Mức giảm: "+
            esc(report.get("charge_drop_percent"))+"% · Trung bình: "+
            esc(report.get("observed_drop_percent_per_minute"))+"% / phút</p>"
            "<p>Không chứng minh pin nguyên bản, cũng không dự đoán chính xác thời lượng pin.</p>"
            "<table><tr><th>Thời gian</th><th>Pin (%)</th><th>mV</th><th>mA</th><th>W</th><th>Đang cắm sạc</th></tr>"+
            lines+"</table><p>"+esc("; ".join(report.get("warnings",[])))+"</p></html>")


def observe(duration_minutes:int,interval_seconds:int,collector=sample,sleep_fn=time.sleep,clock=time.monotonic)->dict:
    first=collector()
    if first.get("ac_connected") is not False:
        return evaluate([first],0,"SKIP: phải rút bộ sạc và controller xác nhận đang dùng pin")
    if first.get("charge_percent") is None:
        return evaluate([first],0,"SKIP: controller không cung cấp % pin hiện tại")
    if first["charge_percent"]<35:
        return evaluate([first],0,"SKIP: cần pin >=35% để kiểm tra an toàn")
    samples=[first]
    start=clock()
    reason="Hoàn thành lấy mẫu theo thời lượng đã chọn"
    try:
        while clock()-start < duration_minutes*60:
            sleep_fn(min(interval_seconds,max(0,duration_minutes*60-(clock()-start))))
            next_sample=collector()
            samples.append(next_sample)
            if next_sample.get("ac_connected") is not False:
                reason="Dừng vì cắm sạc hoặc không còn xác định trạng thái AC"
                break
            pct=next_sample.get("charge_percent")
            if pct is not None and pct<30:
                reason="Dừng do pin xuống dưới 30%"
                break
    except KeyboardInterrupt:
        reason="Người dùng dừng quan sát"
    return evaluate(samples,clock()-start,reason)


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description="Quan sát xả pin — tùy chọn, không tải cưỡng bức")
    p.add_argument("--minutes",type=int,default=3)
    p.add_argument("--interval",type=int,default=15)
    p.add_argument("--out-dir",type=Path,required=True)
    args=p.parse_args(argv)
    if not 1<=args.minutes<=30 or not 5<=args.interval<=60:
        p.error("--minutes 1..30; --interval 5..60")
    args.out_dir.mkdir(parents=True,exist_ok=True)
    report=observe(args.minutes,args.interval)
    (args.out_dir/"battery-discharge.json").write_text(
        json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    (args.out_dir/"battery-discharge.html").write_text(
        html_report(report),encoding="utf-8")
    (args.out_dir/"battery-discharge.tsv").write_text(
        "Battery\tQuan sát xả pin\t"+report["status"]+"\t"+
        str(report.get("charge_drop_percent") or "N/A")+"% thay đổi\t"+
        report["reason"].replace("\t"," ")+"\n",encoding="utf-8")
    print(json.dumps({"status":report["status"],"samples":report["sample_count"],
                      "drop":report.get("charge_drop_percent")},ensure_ascii=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
