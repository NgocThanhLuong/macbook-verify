#!/usr/bin/env python3
"""Offline MacBook comparison; never turns score into proof of legal ownership."""
from __future__ import annotations
import argparse
import html
import json
from pathlib import Path
from typing import Any

HTML = Path(__file__).with_name("compare-macs.html").read_text(encoding="utf-8")


def read_report(path:Path)->dict:
    f=path/"summary.json" if path.is_dir() else path
    result=json.loads(f.read_text(encoding="utf-8"))
    if not isinstance(result,dict):
        raise ValueError("summary.json phải là object")
    return result


def read_pro(path:Path)->dict:
    parent=path if path.is_dir() else path.parent
    f=parent/"system-information.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError,ValueError):
        return {}


def risk_flags(summary:dict,pro:dict)->list[str]:
    warnings=[]
    counts=summary.get("counts") or {}
    if counts.get("fail",0)>0:
        warnings.append("Có bài kiểm tra FAIL — cần xem chi tiết")
    if counts.get("warn",0)>0:
        warnings.append("Có mục WARN — cần kiểm tra lại")
    checks=pro.get("checks") or []
    if any(c.get("area")=="ownership" and c.get("status")=="FAIL" for c in checks):
        warnings.insert(0,"RỦI RO MDM/ADE: máy báo có quản lý tổ chức")
    # Regardless of read-only profiles output, seller erase+activation is mandatory.
    warnings.append("Chưa thể xác nhận quyền sở hữu/Activation Lock trước khi xóa và kích hoạt lại qua Internet")
    if (summary.get("ssd_deep") or {}).get("evidence_confidence") in ("UNAVAILABLE",None,""):
        warnings.append("SSD SMART chuyên sâu thiếu dữ liệu")
    return warnings


def compare(a:dict,b:dict,pro_a:dict|None=None,pro_b:dict|None=None,
            price_a:int=0,price_b:int=0,trade:int=0)->dict:
    trade=max(0,trade)
    columns={}
    keys=[
        ("model","Model"),("chip","Chip CPU"),("memory","RAM"),
        ("ssd_model","SSD"),("battery_max_capacity","Pin macOS"),
        ("battery_cycles","Chu kỳ pin"),("score","Điểm kiểm tra"),
    ]
    for key,label in keys:
        columns[label]=[a.get(key,"N/A"),b.get(key,"N/A")]
    for key,label in [
        ("capacity_health_percent","Pin theo controller (%)"),
        ("raw_health_percent","Pin raw controller (%)"),
        ("diagnostic_signal_score","Tín hiệu cảnh báo pin"),
    ]:
        columns[label]=[(a.get("battery_deep") or {}).get(key,"N/A"),
                        (b.get("battery_deep") or {}).get(key,"N/A")]
    for key,label in [
        ("total_written_tb","SSD đã ghi (TB)"),
        ("estimated_endurance_remaining_percent","SSD còn lại theo NVMe (%)"),
        ("diagnostic_signal_score","Tín hiệu cảnh báo SSD"),
    ]:
        columns[label]=[(a.get("ssd_deep") or {}).get(key,"N/A"),
                        (b.get("ssd_deep") or {}).get(key,"N/A")]
    return {
        "items":{"Máy A":{"name":a.get("model"),"price_vnd":price_a,
                            "top_up_vnd":max(0,price_a-trade) if price_a else None,
                            "warnings":risk_flags(a,pro_a or {})},
                 "Máy B":{"name":b.get("model"),"price_vnd":price_b,
                            "top_up_vnd":max(0,price_b-trade) if price_b else None,
                            "warnings":risk_flags(b,pro_b or {})}},
        "columns":columns,
        "note":"Điểm số chỉ mô tả bài kiểm tra. Không xác minh quyền sở hữu hay chắc chắn máy chưa sửa chữa."
    }


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description="So sánh hai MacBook qua summary.json")
    p.add_argument("--a",type=Path)
    p.add_argument("--b",type=Path)
    p.add_argument("--price-a",type=int,default=0)
    p.add_argument("--price-b",type=int,default=0)
    p.add_argument("--trade-in",type=int,default=0)
    p.add_argument("--out-dir",type=Path,required=True)
    args=p.parse_args(argv)
    if (args.a is None)!=(args.b is None):
        p.error("--a và --b phải đi cùng nhau")
    args.out_dir.mkdir(parents=True,exist_ok=True)
    (args.out_dir/"compare-macs.html").write_text(HTML, encoding="utf-8")
    if args.a and args.b:
        a,b=read_report(args.a),read_report(args.b)
        data=compare(a,b,read_pro(args.a),read_pro(args.b),
                     args.price_a,args.price_b,args.trade_in)
        (args.out_dir/"compare-macs.json").write_text(
            json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
