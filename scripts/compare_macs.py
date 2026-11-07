#!/usr/bin/env python3
"""Offline MacBook comparison; never turns score into proof of legal ownership."""
from __future__ import annotations
import argparse
import html
import json
from pathlib import Path
from typing import Any


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


HTML="""<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MacBook Verify — So sánh máy</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{background:#101827;color:#eaf1ff;font:15px system-ui,-apple-system,sans-serif;margin:0}
main{max-width:1150px;margin:auto;padding:28px}section{background:#17243a;border:1px solid #344763;border-radius:16px;padding:18px;margin:14px 0}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:15px}input{padding:10px;width:100%;border:1px solid #405b7f;border-radius:8px;background:#0d1829;color:#fff}
label{display:block;font-size:13px;color:#aebfd9;margin:10px 0 5px}button{background:#315fc7;border:0;border-radius:8px;padding:12px 16px;color:white;cursor:pointer;font-weight:700}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #344763;padding:11px;text-align:left}
.note{color:#e0b66d}small{color:#aebfd9}b{font-weight:700}@media(max-width:740px){.grid{grid-template-columns:1fr}main{padding:12px}}
</style></head><body><main><h1>So sánh hai MacBook</h1>
<p>Chọn hai file <code>summary.json</code> từ báo cáo MacBook Verify. Trình duyệt chỉ đọc file trên máy, không upload ra Internet.</p>
<section><div class="grid"><div><h2>Máy A</h2><input type="file" id="a" accept=".json,application/json"></div>
<div><h2>Máy B</h2><input type="file" id="b" accept=".json,application/json"></div>
<div><label>Giá bán máy A (VND)</label><input id="priceA" type="number" min="0" value="40000000"></div>
<div><label>Giá bán máy B (VND)</label><input id="priceB" type="number" min="0" value="40000000"></div>
<div><label>Giá thu máy cũ (VND)</label><input id="trade" type="number" min="0" value="21675000"></div>
<div style="align-self:end"><button id="compare">So sánh báo cáo</button></div></div></section>
<section><h2>Kết quả</h2><p id="cost"></p><p class="note">Dù kết quả tốt, vẫn phải xác minh MDM, Activation Lock sau khi xóa và kích hoạt qua Internet. Điểm số không chứng minh linh kiện zin.</p>
<div style="overflow:auto"><table id="result"><thead><tr><th>Hạng mục</th><th>Máy A</th><th>Máy B</th></tr></thead><tbody></tbody></table></div><p id="status"></p></section>
<script>
const fields=[
["model","Model"],["chip","Chip CPU"],["memory","RAM"],["ssd_model","SSD"],
["battery_max_capacity","Pin macOS"],["battery_cycles","Chu kỳ pin"],["score","Điểm kiểm tra"],
["battery_deep.capacity_health_percent","Dung lượng pin theo controller (%)"],
["battery_deep.raw_health_percent","Dung lượng pin Raw (%)"],
["battery_deep.diagnostic_signal_score","Tín hiệu cảnh báo pin"],
["ssd_deep.total_written_tb","SSD đã ghi (TB)"],
["ssd_deep.estimated_endurance_remaining_percent","Độ bền SSD theo NVMe (%)"],
["ssd_deep.diagnostic_signal_score","Tín hiệu cảnh báo SSD"],
["ssd_deep.evidence_confidence","Độ tin cậy dữ liệu SSD"]
];
const el=id=>document.getElementById(id);
const val=(object,path)=>path.split(".").reduce((a,k)=>a?.[k],object)??"N/A";
const money=v=>new Intl.NumberFormat("vi-VN").format(v)+" ₫";
function cell(row,text){const c=document.createElement("td");c.textContent=String(text);row.appendChild(c)}
el("compare").onclick=async function(){
try {
const [af,bf]=[el("a").files[0],el("b").files[0]];
if(!af||!bf)throw Error("Hãy chọn đủ hai báo cáo summary.json");
const [a,b]=await Promise.all([af.text().then(JSON.parse),bf.text().then(JSON.parse)]);
if(!a.model||!b.model)throw Error("File không phải summary.json của MacBook Verify");
const body=el("result").querySelector("tbody");body.replaceChildren();
for(const [key,label] of fields){const tr=document.createElement("tr");cell(tr,label);cell(tr,val(a,key));cell(tr,val(b,key));body.appendChild(tr)}
const priceA=Math.max(0,Number(el("priceA").value)||0);
const priceB=Math.max(0,Number(el("priceB").value)||0);
const trade=Math.max(0,Number(el("trade").value)||0);
el("cost").textContent="Bù máy A: "+money(Math.max(0,priceA-trade))+" · Bù máy B: "+money(Math.max(0,priceB-trade));
const ac=a.counts||{},bc=b.counts||{};
el("status").textContent="Máy A: "+(ac.fail||0)+" FAIL, "+(ac.warn||0)+" WARN. Máy B: "+(bc.fail||0)+" FAIL, "+(bc.warn||0)+" WARN. Chi tiết rủi ro xem report.html từng máy.";
} catch(e){el("status").textContent="Lỗi: "+e.message}
};
</script></main></body></html>"""


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
    (args.out_dir/"compare-macs.html").write_text(HTML,encoding="utf-8")
    if args.a and args.b:
        a,b=read_report(args.a),read_report(args.b)
        data=compare(a,b,read_pro(args.a),read_pro(args.b),
                     args.price_a,args.price_b,args.trade_in)
        (args.out_dir/"compare-macs.json").write_text(
            json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
