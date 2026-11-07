#!/usr/bin/env python3
"""MacBook Verify 2.0: detailed, Vietnamese, offline macOS inventory + evidence.

All shell commands are read-only. Explicit APFS verification uses diskutil
verifyVolume only if requested. Hardware presence != functionality or original
Apple parts. Missing fields remain unknown. No privilege escalation.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys
from typing import Any

VERSION="2.0.0"
PROFILER={
    "SPHardwareDataType":"Phần cứng / CPU / Apple Silicon",
    "SPDisplaysDataType":"GPU / Metal / Màn hình",
    "SPMemoryDataType":"Bộ nhớ RAM",
    "SPNVMeDataType":"Ổ cứng NVMe / SSD",
    "SPStorageDataType":"Phân vùng và ổ lưu trữ",
    "SPSerialATADataType":"Thiết bị SATA",
    "SPPowerDataType":"Pin / Sạc / Nguồn",
    "SPSoftwareDataType":"macOS / Hệ thống",
    "SPiBridgeDataType":"Chip bảo mật / Firmware",
    "SPThunderboltDataType":"Thunderbolt / USB-C",
    "SPUSBDataType":"Thiết bị USB",
    "SPCardReaderDataType":"Đầu đọc thẻ",
    "SPAudioDataType":"Âm thanh",
    "SPCameraDataType":"Camera",
    "SPAirPortDataType":"Wi-Fi",
    "SPBluetoothDataType":"Bluetooth",
    "SPNetworkDataType":"Mạng",
    "SPDiagnosticsDataType":"Chẩn đoán hệ thống",
}
LABELS={
    "chip_type":"Chip", "cpu_type":"Loại CPU", "number_processors":"Số CPU",
    "number_cores":"Số lõi CPU", "physical_memory":"Dung lượng RAM",
    "machine_model":"Mã đời máy", "machine_name":"Tên máy",
    "serial_number":"Số sê-ri", "boot_rom_version":"Phiên bản firmware",
    "os_version":"Phiên bản macOS", "kernel_version":"Phiên bản kernel",
    "spdisplays_gpu":"Tên GPU", "spdisplays_gpu_cores":"Số lõi GPU",
    "sppci_model":"Mẫu GPU", "spdisplays_metal":"Khả năng hỗ trợ Metal",
    "spdisplays_resolution":"Độ phân giải", "spdisplays_pixelresolution":"Độ phân giải vật lý",
    "spdisplays_refreshRate":"Tần số quét",
    "size":"Dung lượng", "model":"Model", "trim_support":"Hỗ trợ TRIM",
    "smart_status":"Trạng thái SMART", "cycle_count":"Chu kỳ sạc",
    "battery_health":"Sức khỏe pin", "charge_remaining":"Mức pin còn lại",
    "serial_num":"Số sê-ri", "manufacturer":"Nhà sản xuất",
}
GROUPS=[
 ("cpu","CPU / Bộ xử lý"),
 ("gpu","GPU / Đồ họa"),
 ("memory","Bộ nhớ / RAM"),
 ("storage","SSD / APFS"),
 ("power","Pin và nguồn"),
 ("thermal","Nhiệt độ / giới hạn hiệu năng"),
 ("security","Bảo mật / Quyền sở hữu"),
 ("repair","Lịch sử sửa chữa"),
 ("sleep","Ngủ / Thức / Độ ổn định"),
 ("devices","Màn hình / cổng / kết nối"),
]
RED_FLAG_PATTERNS=("Enrolled via DEP: Yes","MDM enrollment: Yes")


def run(argv: list[str], timeout: int=25)->tuple[int,str]:
    try:
        p=subprocess.run(argv, text=True, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, timeout=timeout, check=False)
        return p.returncode,p.stdout[:12_000_000]
    except (OSError,subprocess.TimeoutExpired) as e:
        return 127,str(e)


def field_sysctl(key: str)->str|None:
    code,out=run(["/usr/sbin/sysctl","-n",key],7)
    return out.strip() if code==0 and out.strip() else None


def read_raw(raw:Path, filename:str, maximum:int=200_000)->str:
    try:
        return (raw/filename).read_text(encoding="utf-8",errors="replace")[:maximum]
    except OSError:
        return ""


def parse_plist_command(argv:list[str],timeout:int=20)->dict:
    code,output=run(argv,timeout)
    if code!=0:
        return {"available":False,"reason":output[:200]}
    try:
        parsed=plistlib.loads(output.encode("utf-8"))
        return {"available":True,"data":parsed}
    except (ValueError,TypeError,plistlib.InvalidFileException):
        return {"available":False,"reason":"Dữ liệu plist không đọc được"}


def supported_profiler_types()->set[str]|None:
    status,raw=run(["/usr/sbin/system_profiler","-listDataTypes"],15)
    if status!=0:
        return None
    return set(re.findall(r"\bSP[A-Za-z0-9]+DataType\b",raw))


def profiler_collect()->tuple[dict,dict]:
    supported=supported_profiler_types()
    types=[key for key in PROFILER if supported is None or key in supported]
    # One system_profiler invocation: avoids repeated hardware scans and retains
    # all native keys, nested devices and each reported display/port.
    status,output=run(["/usr/sbin/system_profiler","-json",*types],130)
    if status!=0:
        return {},{"status":"UNAVAILABLE","message":output[:500]}
    try:
        data=json.loads(output)
        if not isinstance(data,dict):
            raise ValueError("Invalid top-level System Profiler JSON")
        return data,{"status":"PASS","collected_types":types,"present":list(data.keys())}
    except ValueError as exc:
        return {},{"status":"UNAVAILABLE","message":str(exc)}


def flatten(node:Any,prefix:str="",limit:int=600)->list[tuple[str,str]]:
    result=[]
    def visit(obj:Any,path:str,depth:int)->None:
        if len(result)>=limit:
            return
        if depth>16:
            result.append((path,"…"));return
        if isinstance(obj,dict):
            for key,val in obj.items():
                translated=LABELS.get(key,key)
                visit(val, path+" / "+translated if path else translated,depth+1)
        elif isinstance(obj,list):
            for index,val in enumerate(obj):
                visit(val,f"{path} [{index+1}]",depth+1)
        elif obj is not None:
            result.append((path,str(obj)))
    visit(node,prefix,0)
    return result


def first_item(data:dict,key:str)->dict:
    items=data.get(key) or []
    if isinstance(items,list):
        for item in items:
            if isinstance(item,dict):
                return item
    return {}


def nested_find(data:Any,keys:set[str],maximum:int=20)->list[str]:
    found=[]
    def visit(o:Any):
        if len(found)>=maximum:
            return
        if isinstance(o,dict):
            for key,value in o.items():
                if key in keys and not isinstance(value,(dict,list)):
                    found.append(str(value))
                visit(value)
        elif isinstance(o,list):
            for value in o:visit(value)
    visit(data)
    return found


def cpu_metrics(hardware:dict)->dict:
    n=lambda key:field_sysctl(key)
    total=n("hw.ncpu") or n("hw.physicalcpu")
    levels=[]
    for i in range(4):
        label=n(f"hw.perflevel{i}.name")
        cores=n(f"hw.perflevel{i}.physicalcpu")
        if label or cores:
            levels.append({"loại":label or "Không xác định","số_lõi":cores})
    return {
        "chip":hardware.get("chip_type") or hardware.get("cpu_type"),
        "cores":hardware.get("number_cores") or total,
        "logical_cores":n("hw.logicalcpu"),
        "physical_cores":n("hw.physicalcpu"),
        "performance_efficiency_clusters":levels,
        "architecture":n("hw.machine"),
        "cpu_brand":n("machdep.cpu.brand_string"),
        "cpu_frequency_hz":n("hw.cpufrequency"),
        "cache_l1_data_bytes":n("hw.l1dcachesize"),
        "cache_l2_bytes":n("hw.l2cachesize"),
        "cache_l3_bytes":n("hw.l3cachesize"),
        "memory_bytes":n("hw.memsize"),
        "model_identifier":hardware.get("machine_model"),
        "serial":hardware.get("serial_number"),
        "firmware":hardware.get("boot_rom_version"),
    }


def gpu_metrics(displays:dict)->dict:
    items=displays.get("SPDisplaysDataType") or []
    entries=[]
    for entry in items if isinstance(items,list) else []:
        if not isinstance(entry,dict):continue
        entries.append({
            "name":entry.get("sppci_model") or entry.get("_name"),
            "cores":entry.get("spdisplays_gpu_cores") or entry.get("gpu_cores"),
            "metal":entry.get("spdisplays_metal"),
            "vendor":entry.get("spdisplays_vendor"),
            "bus":entry.get("sppci_bus"),
            "vram":entry.get("spdisplays_vram"),
            "displays":entry.get("spdisplays_ndrvs") or [],
        })
    return {"devices":entries,"core_count_detected":any(e.get("cores") for e in entries),
            "note":"RAM unified không phải VRAM riêng; số GPU cores tùy phiên bản chip và dữ liệu macOS."}


def sleep_events(pmset:str)->dict:
    lines=pmset.splitlines()
    categories={
        "sleep":sum(bool(re.search(r"\bEntering Sleep\b",s,re.I)) for s in lines),
        "wake":sum(bool(re.search(r"\bWake from\b|\bWake\b",s,re.I)) for s in lines),
        "failure_mentions":sum(bool(re.search(r"sleep.*fail|wake.*fail|shutdown cause",s,re.I)) for s in lines),
    }
    return {"counts":categories,"recent_events":lines[-100:],
            "note":"Tổng số dòng log không chứng minh phần cứng bị lỗi; log có thể bị xóa/rotate."}


def perform_checks(raw:Path,profile:dict,gpu:dict,sysdata:dict,verify_apfs:bool)->dict:
    checks=[]
    def add(area:str,title:str,status:str,value:str,detail:str):
        checks.append({"area":area,"title":title,"status":status,"value":value,"detail":detail})
    _,therm=run(["/usr/bin/pmset","-g","therm"],12)
    _,sleep=run(["/usr/bin/pmset","-g","log"],22)
    _,sips=run(["/usr/bin/csrutil","status"],12)
    _,gate=run(["/usr/sbin/spctl","--status"],12)
    _,filevault=run(["/usr/bin/fdesetup","status"],12)
    mdm=read_raw(raw,"mdm.txt")
    repair=read_raw(raw,"repair-history.txt")
    boot_os=run(["/usr/bin/sw_vers","-productVersion"],8)[1].strip()
    security={
        "sip":sips[:600],"gatekeeper":gate[:600],"filevault":filevault[:600],
        "mdm_readout":mdm[:2000],
        "firmware":profile.get("firmware"),
        "macos":boot_os,
        "is_apple_silicon":str(profile.get("architecture","")).lower()=="arm64",
    }
    red_enrollment=bool(re.search(r"Enrolled via DEP:\s*Yes|MDM enrollment:\s*Yes",mdm,re.I))
    denied=bool(re.search(r"Enrolled via DEP:\s*No|MDM enrollment:\s*No",mdm,re.I))
    add("ownership","Quản lý tổ chức / MDM / ADE",
        "FAIL" if red_enrollment else "INFO",
        "Đã đăng ký tổ chức" if red_enrollment else "Chưa ghi nhận đăng ký" if denied else "Chưa đủ dữ liệu",
        "Cần xác minh sau khi xóa và kích hoạt máy qua Internet; lệnh profiles không chứng minh ADE vĩnh viễn.")
    add("ownership","Activation Lock / iCloud","INFO","Cần xác minh",
        "Trước khi trả tiền, người bán đăng xuất, xóa máy và bạn kích hoạt lại thành công; không bypass khóa.")
    add("repair","Lịch sử linh kiện / sửa chữa","INFO",
        "Có dữ liệu CLI" if repair and not repair.startswith("No Repair/Parts") else "Không có dữ liệu đầy đủ",
        "macOS 26+ có thể hiển thị Cài đặt > Cài đặt chung > Giới thiệu > Linh kiện & dịch vụ; không phải mọi sửa chữa đều có.")
    limits=re.findall(r"\b(?:CPU|GPU|Scheduler)_Speed_Limit\b\s*=\s*(\d+)",therm)
    limited=any(int(v)<100 for v in limits)
    add("thermal","Giới hạn hiệu năng qua pmset","WARN" if limited else "INFO",
        "Có dấu hiệu giới hạn" if limited else "Không phát hiện giới hạn trong mẫu",
        "Chỉ là snapshot; không có cảm biến nhiệt độ chính xác nếu macOS không công khai.")
    apfs=parse_plist_command(["/usr/sbin/diskutil","apfs","list","-plist"],30)
    root=parse_plist_command(["/usr/sbin/diskutil","info","-plist","/"],20)
    apfs_verify={"status":"SKIP","note":"Chỉ chạy khi có --verify-apfs; không tự sửa ổ."}
    if verify_apfs:
        rc,out=run(["/usr/sbin/diskutil","verifyVolume","/"],120)
        apfs_verify={"status":"PASS" if rc==0 else "WARN","exit_code":rc,"output":out[-4000:],
                     "note":"Verify Volume không phải phép thử vật lý NAND; không chạy repairVolume."}
        add("storage","Kiểm tra APFS (verifyVolume)",apfs_verify["status"],
            "Không phát hiện lỗi" if rc==0 else "Cần xem log","Kiểm tra logic cấu trúc ổ, không tự sửa.")
    storage={"apfs":apfs,"root_disk":root,"verify":apfs_verify}
    sleep_data=sleep_events(sleep)
    sleep_data["source"]="pmset -g log"
    add("sleep","Lịch sử ngủ/thức", "INFO",str(sleep_data["counts"]["failure_mentions"])+" dòng cần xem",
        "Số lần xuất hiện từ khóa không kết luận lỗi; kiểm tra sau nhiều chu kỳ sleep thực.")
    gpu_actual=gpu.get("devices",[])
    add("gpu","Thông số GPU macOS", "INFO",str(len(gpu_actual))+" GPU",
        "Có thể kiểm tra Metal compute riêng trong chế độ Deep/Burn-in.")
    ane="Không xác minh được ANE bằng phép tính"
    add("ane","Neural Engine / Core ML", "SKIP",ane,
        "Chip Apple Silicon có thể có ANE; CPU/GPU fallback của Core ML không phải xác nhận ANE đã chạy.")
    add("display","Màn hình mini-LED / ProMotion / True Tone","INFO","Cần kiểm tra hình ảnh thực tế",
        "Báo cáo có cấu hình màn hình; phải xác minh điểm chết, sọc, đồng đều sáng, XDR, True Tone bằng mắt.")
    add("ports","Cổng Thunderbolt, USB, HDMI, SD, MagSafe","INFO","Có bản kiểm kê thiết bị",
        "Cổng trống không chứng minh hoạt động. Cần kết nối phụ kiện thật và xác nhận.")
    return {
        "checks":checks,"thermal":{"pmset":therm[:3000],"speed_limits":limits},
        "sleep":sleep_data,"security":security,"storage":storage,
        "repair":{"cli_excerpt":repair[:3000],"parts_and_service_requires_manual_review":True},
    }


def html_overview(report:dict)->str:
    esc=lambda value:html.escape(str(value if value is not None else "Không có dữ liệu"),quote=True)
    profile=report["cpu"]
    gpu=report["gpu"]
    checks=report["checks"]
    cards=[
        ("Chip / CPU",profile.get("chip")),("Số lõi CPU",profile.get("cores")),
        ("GPU",", ".join(str(d.get("name") or "?") for d in gpu.get("devices",[]))),
        ("Số nhân GPU",", ".join(str(d.get("cores") or "N/A") for d in gpu.get("devices",[]))),
        ("RAM",report["hardware"].get("physical_memory")),("Model",profile.get("model_identifier")),
        ("macOS",report["security"].get("macos")),("Firmware",profile.get("firmware")),
        ("Metal GPU thực tế",(gpu.get("metal_runtime") or {}).get("gpu_name")),
        ("GPU Metal test",(gpu.get("metal_runtime") or {}).get("status")),
    ]
    top="".join("<div class='metric'><span>"+esc(k)+"</span><b>"+esc(v)+"</b></div>" for k,v in cards)
    checks_html="".join(
        "<tr><td>"+esc(x["area"])+"</td><td>"+esc(x["title"])+"</td><td><span class='state "+esc(x["status"].lower())+"'>"+esc(x["status"])+"</span></td><td>"+esc(x["value"])+"</td><td>"+esc(x["detail"])+"</td></tr>"
        for x in checks)
    sections=[]
    for key,label in PROFILER.items():
        data=report["system_profiler"].get(key,[])
        if not data:
            continue
        fields=flatten(data,limit=700)
        body="".join("<tr><td>"+esc(a)+"</td><td>"+esc(b)+"</td></tr>" for a,b in fields)
        sections.append("<details><summary>"+esc(label)+" <small>("+str(len(fields))+" thuộc tính)</small></summary>"
                        "<div class='scroll'><table><thead><tr><th>Thông số</th><th>Giá trị macOS</th></tr></thead><tbody>"
                        +body+"</tbody></table></div></details>")
    sec=report["security"]
    manual=[
      "Đăng xuất iCloud / Find My, xóa máy và kích hoạt qua Internet thành công",
      "Kiểm tra macOS 26+: Cài đặt > Cài đặt chung > Giới thiệu > Linh kiện & dịch vụ",
      "Kiểm tra Apple Diagnostics: tắt máy, giữ nút nguồn tới Tùy chọn, nhấn Command-D",
      "Màn hình: trắng, đen, xám, RGB, gradient, xem pixel chết / hở sáng / mini-LED",
      "Bàn phím, Touch ID, trackpad, loa trái/phải, mic, webcam và từng cổng bằng thiết bị thật",
      "Rút sạc: xả pin nhẹ, quan sát điện áp và tình trạng tụt pin; dừng khi pin yếu",
      "Đóng/mở nắp, sleep/wake, sạc MagSafe/USB-C, Wi-Fi/Bluetooth",
      "Kiểm tra ngoại hình, ốc, vết cạy, dấu oxy hóa và serial đáy máy",
    ]
    manual_html="".join("<li>"+esc(item)+"</li>" for item in manual)
    return """<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MacBook Verify — Thông tin hệ thống chuyên sâu</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}
body{background:#0b1221;color:#eaf0ff;margin:0;font:14px -apple-system,BlinkMacSystemFont,system-ui,sans-serif}
main{max-width:1400px;margin:auto;padding:24px}h1{font-size:30px;margin:0 0 5px}h2{font-size:20px}
section,details{margin:14px 0;background:#172239;border:1px solid #344761;border-radius:16px;padding:18px}
.summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.metric{background:#23334d;padding:15px;border-radius:12px;min-width:0}
.metric span{font-size:12px;color:#a6b8d6;display:block}.metric b{display:block;margin-top:8px;overflow-wrap:anywhere;font-size:18px}
.small,small,p{color:#afc0d9}details>summary{font-size:16px;font-weight:700;cursor:pointer;padding:7px}
.scroll{overflow:auto;max-height:700px}table{border-collapse:collapse;width:100%}td,th{padding:10px 12px;border-bottom:1px solid #31415e;text-align:left;vertical-align:top;overflow-wrap:anywhere}td:first-child{max-width:500px;color:#a9c0ec}th{color:#9ab1d4}li{padding:5px}
.state{font-weight:700;padding:4px 8px;border-radius:6px;background:#34445b}.state.fail{background:#831c2d}.state.warn{background:#785319}
a{color:#91caff}@media(max-width:900px){.summary{grid-template-columns:repeat(2,1fr)}main{padding:12px}}
@media(max-width:520px){.summary{grid-template-columns:1fr}}
</style></head><body><main>
<header><h1>Thông tin hệ thống & Kiểm định chuyên sâu</h1>
<p>MacBook Verify 2.0 · System Information mở rộng · Thu thập tại máy · Không tự sửa đổi phần cứng</p></header>
<section><h2>Thông số CPU / GPU / hệ thống</h2><div class="summary">__CARDS__</div>
<p>Thông số được lấy từ System Information và sysctl. Nếu không được macOS báo cáo, chương trình hiển thị không có dữ liệu.</p></section>
<section><h2>Đánh giá rủi ro và hướng dẫn kiểm tra</h2><div class="scroll"><table><tr><th>Nhóm</th><th>Kiểm tra</th><th>Trạng thái</th><th>Giá trị</th><th>Diễn giải</th></tr>__CHECKS__</table></div>
<p><strong>Lưu ý:</strong> không ghi nhận MDM/Activation Lock không chứng minh máy có thể kích hoạt lại. Không dùng điểm số tự động thay thế kiểm tra quyền sở hữu.</p></section>
<section><h2>Thông tin gốc đầy đủ (System Information)</h2><p>Mở từng nhóm để xem toàn bộ trường và thiết bị con được macOS báo cáo.</p>
__SECTIONS__</section>
<section><h2>Danh sách kiểm định thủ công</h2><ol>__MANUAL__</ol>
<p><a href="https://support.apple.com/vi-vn/102550">Hướng dẫn Apple Diagnostics</a> ·
<a href="https://support.apple.com/vi-vn/123123">Linh kiện & dịch vụ</a></p></section>
<footer><p>Dữ liệu có thể chứa serial, địa chỉ mạng, thông tin thiết bị. Cẩn trọng khi chia sẻ báo cáo ZIP.</p></footer>
</main></body></html>"""\
        .replace("__CARDS__",top).replace("__CHECKS__",checks_html)\
        .replace("__SECTIONS__","".join(sections))\
        .replace("__MANUAL__",manual_html)


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description="MacBook Verify: System Information tiếng Việt")
    p.add_argument("--out-dir",required=True,type=Path)
    p.add_argument("--raw-dir",type=Path)
    p.add_argument("--verify-apfs",action="store_true",help="Explicit read-only diskutil verifyVolume")
    p.add_argument("--fixture-json",type=Path,help=argparse.SUPPRESS)
    args=p.parse_args(argv)
    args.out_dir.mkdir(parents=True,exist_ok=True)
    raw=args.raw_dir or args.out_dir/"raw"
    if args.fixture_json:
        sysdata=json.loads(args.fixture_json.read_text(encoding="utf-8"))
        collection={"status":"FIXTURE"}
    elif sys.platform=="darwin":
        sysdata,collection=profiler_collect()
    else:
        sysdata,collection={},{"status":"UNAVAILABLE","message":"Only macOS supports native System Profiler"}
    hardware=first_item(sysdata,"SPHardwareDataType")
    cpu=cpu_metrics(hardware) if sys.platform=="darwin" and not args.fixture_json else {
        "chip":hardware.get("chip_type") or hardware.get("cpu_type"),
        "cores":hardware.get("number_cores"),
        "model_identifier":hardware.get("machine_model"),
        "firmware":hardware.get("boot_rom_version"),
    }
    gpu=gpu_metrics(sysdata)
    # Merge real Metal device metadata from native compute test, if present.
    metal_path=raw/"metal-gpu.json"
    if metal_path.is_file():
        try:
            metal_info=json.loads(metal_path.read_text(encoding="utf-8"))
            if isinstance(metal_info,dict):
                gpu["metal_runtime"]=metal_info
        except (OSError,ValueError):
            gpu["metal_runtime"]={"status":"UNKNOWN"}
    if sys.platform=="darwin" and not args.fixture_json:
        analyzed=perform_checks(raw,cpu,gpu,sysdata,args.verify_apfs)
    else:
        analyzed={"checks":[],"thermal":{},"sleep":{},"security":{},
                  "storage":{},"repair":{}}
    report={
        "tool":"MacBook Verify — Thông tin hệ thống","version":VERSION,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "collection":collection,"hardware":hardware,"cpu":cpu,"gpu":gpu,
        "system_profiler":sysdata,**analyzed,
    }
    out=args.out_dir
    (out/"system-information.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"system-information.html").write_text(
        html_overview(report),encoding="utf-8")
    rows=[]
    for c in report["checks"]:
        rows.append(("Pro "+c["area"],c["title"],c["status"],c["value"],c["detail"]))
    if collection.get("status")=="UNAVAILABLE":
        rows.append(("Pro","System Information inventory","INFO","Unavailable",
                     collection.get("message","macOS did not return data")))
    elif collection.get("status") in ("PASS","FIXTURE"):
        rows.append(("Pro","System Information inventory","INFO",
                     str(len(sysdata))+" data types","Raw full JSON retained; see system-information.html"))
    (out/"pro-results.tsv").write_text("".join(
        "\t".join(str(col).replace("\t"," ").replace("\n"," ") for col in row)+"\n" for row in rows),
        encoding="utf-8")
    print(json.dumps({"collection":collection.get("status"),"cpu":cpu.get("chip"),
                      "gpu":len(gpu.get("devices",[]))},ensure_ascii=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
