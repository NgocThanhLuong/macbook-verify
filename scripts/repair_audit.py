#!/usr/bin/env python3
"""Read-only repair/provenance evidence audit for an already collected MacBook Verify report.

This is an evidence triage tool, not an originality or repair-authenticity detector.
No undocumented Apple APIs, administrator rights, network access, or device changes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
from pathlib import Path
from typing import Any

APPLE_PARTS_URL = "https://support.apple.com/123123"


def load_json(path: Path) -> dict:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def numeric(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    return float(match.group()) if match else None


def normalized_serial(value: Any) -> str:
    return str(value or "").strip().upper()


def parse_date(value: Any) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def assess(out_dir: Path, raw_dir: Path, previous_summary: Path | None = None,
           today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    coverage = load_json(out_dir / "apple-coverage.json")
    battery = load_json(out_dir / "battery-report.json")
    system = load_json(out_dir / "system-information.json")
    summary = load_json(out_dir / "summary.json")
    mdm = load_text(raw_dir / "mdm.txt")
    repair = load_text(raw_dir / "repair-history.txt")
    checks: list[dict] = []

    def add(title: str, status: str, evidence: str, guidance: str) -> None:
        checks.append({
            "title": title, "status": status, "evidence": evidence,
            "guidance": guidance
        })

    system_serial = normalized_serial(
        (system.get("hardware") or {}).get("serial_number") or summary.get("serial")
    )
    coverage_serial = normalized_serial(coverage.get("serial"))
    if system_serial and coverage_serial:
        if system_serial != coverage_serial:
            add("Serial hệ thống / Apple Coverage", "FAIL",
                "Serial trong hai báo cáo không khớp",
                "Đối chiếu serial trên thân máy, System Information và bản ghi coverage.")
        else:
            add("Serial hệ thống / Apple Coverage", "INFO",
                "Hai nguồn báo cùng serial",
                "Chỉ xác minh dữ liệu thu thập; không chứng minh mainboard nguyên bản.")
    else:
        add("Serial hệ thống / Apple Coverage", "INFO", "Thiếu dữ liệu đối chiếu",
            "Mở System Information và Apple Coverage, kiểm tra cùng một serial.")

    if re.search(r"(?:Enrolled via DEP|MDM enrollment):\s*Yes\b", mdm, re.I):
        add("Quản lý doanh nghiệp MDM/ADE", "FAIL", "macOS báo có đăng ký quản lý",
            "Chỉ mua khi chủ sở hữu hợp pháp giải phóng máy khỏi Apple Business và xác minh sau khi xóa/kích hoạt online.")
    elif re.search(r"(?:Enrolled via DEP|MDM enrollment):\s*No\b", mdm, re.I):
        add("Quản lý doanh nghiệp MDM/ADE", "INFO",
            "Không ghi nhận enrollment ở thời điểm kiểm tra",
            "Kết quả tại chỗ không loại trừ Remote Management ở lần thiết lập sau; cần xóa và kích hoạt online.")
    else:
        add("Quản lý doanh nghiệp MDM/ADE", "INFO", "Không đủ dữ liệu",
            "Kiểm tra trực tiếp quyền sở hữu, Activation Lock và thiết lập lại qua Internet.")

    if repair and not repair.startswith("No Repair/Parts"):
        add("Dữ liệu sửa chữa do macOS cung cấp", "INFO",
            "Có dữ liệu CLI để xem lại trong raw/repair-history.txt",
            "Đọc từng bản ghi và kiểm tra Parts & Service trong Settings. Không suy luận chỉ từ tên tiến trình.")
    else:
        add("Dữ liệu sửa chữa do macOS cung cấp", "INFO",
            "Không có lịch sử sửa chữa đầy đủ qua command line",
            "Trên macOS Tahoe 26+ kiểm tra General > About > Parts & Service; không hiện mục này KHÔNG chứng minh máy chưa sửa.")

    battery_capacity = battery.get("capacity") or {}
    battery_cycles = battery.get("cycles") or {}
    cycles = numeric(battery_cycles.get("count"))
    if cycles is None:
        cycles = numeric(summary.get("battery_cycles"))
    health = numeric(battery_capacity.get("macos_reported_health_percent"))
    if health is None:
        health = numeric(summary.get("battery_max_capacity"))
    purchase_date = parse_date(coverage.get("purchase_date"))
    age_days = (today - purchase_date).days if purchase_date and purchase_date <= today else None
    if age_days is not None and age_days >= 365 * 3 and cycles is not None and health is not None and cycles <= 50 and health >= 98:
        add("Pin ít chu kỳ so với ngày mua được ghi nhận", "INFO",
            f"Ngày mua {purchase_date.isoformat()}; {int(cycles)} chu kỳ; sức khỏe báo {health:g}%",
            "Có thể là hàng tồn kho/ít dùng, thay pin hoặc dữ liệu controller khác thực tế. Không xác định được nguyên bản từ các số này; kiểm tra pin dưới tải và chứng từ.")
    else:
        add("Đối chiếu tuổi pin và chu kỳ", "INFO",
            f"Ngày mua {purchase_date.isoformat() if purchase_date else 'chưa xác minh'}; "
            f"chu kỳ {int(cycles) if cycles is not None else 'N/A'}; "
            f"sức khỏe {format(health, 'g') + '%' if health is not None else 'N/A'}",
            "Ngày mua trên Apple Coverage có thể do người dùng nhập; không phải ngày sản xuất hay lần kích hoạt đầu tiên.")

    if previous_summary:
        previous = load_json(previous_summary)
        previous_serial = normalized_serial(previous.get("serial"))
        if not previous:
            add("So sánh báo cáo cũ", "INFO", "Không đọc được JSON hợp lệ",
                "Chọn summary.json của chính máy này từ lần chạy trước.")
        elif not system_serial or not previous_serial or system_serial != previous_serial:
            add("So sánh báo cáo cũ", "INFO", "Không thể xác minh cùng một máy",
                "Không so sánh pin giữa hai serial khác nhau.")
        else:
            old_cycle = numeric(previous.get("battery_cycles"))
            old_health = numeric(previous.get("battery_max_capacity"))
            if cycles is not None and old_cycle is not None:
                delta_cycle = cycles - old_cycle
                if delta_cycle < -5:
                    add("Chu kỳ pin giảm so với báo cáo cũ", "WARN",
                        f"{int(old_cycle)} → {int(cycles)} chu kỳ",
                        "Có thể do thay pin/bộ điều khiển, can thiệp dữ liệu hoặc nguồn số liệu khác nhau; cần xác minh.")
                else:
                    add("Thay đổi chu kỳ pin", "INFO",
                        f"{int(old_cycle)} → {int(cycles)} chu kỳ",
                        "Một lần cắm sạc không nhất thiết tương đương một chu kỳ.")
                if old_health is not None and health is not None and 0 <= delta_cycle <= 100:
                    drop = old_health - health
                    if drop >= 5:
                        add("Sức khỏe pin giảm đáng kể", "WARN",
                            f"{old_health:g}% → {health:g}% trong {int(delta_cycle)} chu kỳ",
                            "Có thể là tái hiệu chỉnh dung lượng hoặc pin lão hóa; không đủ bằng chứng bị chỉnh pin.")
                    elif drop <= -8:
                        add("Sức khỏe pin tăng rõ", "INFO",
                            f"{old_health:g}% → {health:g}%",
                            "Cần xác minh thay pin, hiệu chỉnh lại bộ điều khiển hoặc dữ liệu cũ không đáng tin.")
            else:
                add("So sánh báo cáo cũ", "INFO", "Thiếu dữ liệu chu kỳ",
                    "Cần summary.json có serial và battery_cycles.")

    return {
        "schema_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "scope": "repair evidence triage; not originality certification",
        "evidence_limitations": [
            "A clean software report cannot prove a Mac was never opened, serviced or repaired.",
            "MacBook Pro 2021 Parts & Service history does not provide full battery/display service coverage.",
            "100% battery health and low cycle count cannot authenticate the original battery.",
            "A currently unenrolled Mac can still require Remote Management on online setup."
        ],
        "checks": checks,
        "manual_actions": [
            "Mở Settings > General > About > Parts & Service (macOS Tahoe 26+). Ghi trạng thái, ngày sửa và chụp bằng chứng.",
            "Đối chiếu serial trên đáy, trong System Information và chứng từ của người bán.",
            "Soi ốc đáy, khe thân máy, dấu cạy và oxy hóa; nhờ kỹ thuật độc lập kiểm tra nếu mua máy đắt tiền.",
            "Chạy Apple Diagnostics riêng; kiểm tra pin thực tế và thử đủ các cổng.",
            "Với máy thanh lý công ty: xóa máy và kích hoạt qua Internet; yêu cầu chứng minh đã release khỏi Apple Business.",
            "Yêu cầu cam kết bằng văn bản về nguồn gốc, tình trạng sửa chữa và chính sách đổi trả."
        ],
        "references": [
            {"title": "Apple Mac parts and service history", "url": APPLE_PARTS_URL},
            {"title": "Apple MacBook Pro 16-inch 2021 repair manual",
             "url": "https://support.apple.com/100568"}
        ],
        "has_verified_repair": False,
        "note": "Only the owner/Apple repair record and physical evidence can clarify repairs. Flags are not a fraud verdict."
    }


def render_html(report: dict) -> str:
    e = lambda x: html.escape(str(x), quote=True)
    rows = "".join(
        f'<tr><td class="{e(c["status"].lower())}">{e(c["status"])}</td>'
        f'<td>{e(c["title"])}</td><td>{e(c["evidence"])}</td>'
        f'<td>{e(c["guidance"])}</td></tr>' for c in report["checks"]
    )
    actions = "".join(f"<li>{e(a)}</li>" for a in report["manual_actions"])
    return f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MacBook Verify | Repair & Provenance Audit</title>
<style>body{{font:15px -apple-system,BlinkMacSystemFont,sans-serif;margin:0;color:#e9eefb;background:#0b1220}}
main{{max-width:1100px;margin:30px auto;padding:0 18px}}
section{{background:#151e30;border:1px solid #35445c;border-radius:16px;padding:22px;margin:18px 0}}
h1{{font-size:32px}}h2{{font-size:21px}}p,li{{line-height:1.65}}
table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{padding:12px;border-bottom:1px solid #36445d;text-align:left;vertical-align:top}}
.pass{{color:#66dca2}}.warn{{color:#ffcc66}}.fail{{color:#ff7387}}.info{{color:#84baff}}
.notice{{border-left:4px solid #ffbb55;padding:12px;background:#392f22}}
a{{color:#9cc7ff}}select,textarea,button{{font:inherit;padding:10px;border-radius:8px}}
button{{background:#3464b0;color:white;border:0;cursor:pointer}}
label{{display:block;margin:14px 0}}select,textarea{{width:100%;max-width:660px;background:#101827;color:white;border:1px solid #536179}}
@media(max-width:700px){{table{{display:block;overflow:auto}}}}</style></head><body><main>
<h1>Repair & Provenance Audit</h1>
<p>Đánh giá bằng chứng liên quan sửa chữa, pin và quản lý doanh nghiệp — chạy offline, chỉ đọc.</p>
<section class="notice"><b>Không phải giấy chứng nhận máy nguyên bản.</b>
Không có kiểm tra phần mềm nào phát hiện được tất cả các lần mở máy, thay pin, thay màn hoặc sửa main.
Cảnh báo pin không đồng nghĩa pin giả hay pin đã thay.</section>
<section><h2>Đối chiếu tự động</h2><table><thead><tr><th>Trạng thái</th><th>Kiểm tra</th><th>Bằng chứng</th><th>Cần làm</th></tr></thead><tbody>{rows}</tbody></table></section>
<section><h2>Checklist kiểm tra tại cửa hàng</h2><ol>{actions}</ol>
<p>Trên macOS Tahoe 26+: <strong>System Settings → General → About → Parts & Service</strong>.
MacBook Pro 2021 chỉ hỗ trợ lịch sử đối với một số hạng mục (ví dụ mainboard, Touch ID).
Không có mục này không phải bằng chứng chưa sửa.</p>
<p><a href="{APPLE_PARTS_URL}" target="_blank" rel="noopener">Tài liệu Apple: Parts & Service</a></p></section>
<section><h2>Ghi nhận thủ công Parts & Service (không tự xác thực)</h2>
<label>Trạng thái quan sát trực tiếp trên máy<select id="parts">
<option value="not_checked">Chưa kiểm tra</option><option value="not_shown">Không hiện mục Parts & Service</option>
<option value="genuine">Genuine (theo màn hình Apple)</option><option value="used">Used (theo màn hình Apple)</option>
<option value="unknown">Unknown (theo màn hình Apple)</option>
<option value="unverified">Unverified (theo màn hình Apple)</option></select></label>
<label>Hạng mục, ngày sửa, bằng chứng/ghi chú<textarea id="note" rows="4" placeholder="Ví dụ: Touch ID Board, 2024-01-12; lưu ảnh chứng từ riêng"></textarea></label>
<button id="export">Lưu phiếu ghi nhận thủ công (JSON)</button>
<p>Phiếu lưu về máy người dùng, không được thêm vào kết luận tự động và không tải lên Internet.</p></section>
<script>document.getElementById("export").addEventListener("click",()=>{{
const data={{source:"manual_observation_unverified",parts_status:document.getElementById("parts").value,
notes:document.getElementById("note").value,recorded_at:new Date().toISOString()}};
const u=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{{type:"application/json"}}));
const a=document.createElement("a");a.href=u;a.download="repair-manual-observation.json";a.click();URL.revokeObjectURL(u);
}});</script></main></body></html>"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repair & provenance evidence audit (offline, read-only)")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--previous-summary", type=Path, help="Previous summary.json from the SAME Mac")
    args = parser.parse_args(argv)
    out_dir = args.out_dir.expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = args.raw_dir.expanduser() if args.raw_dir else out_dir / "raw"
    report = assess(out_dir, raw_dir, args.previous_summary)
    (out_dir / "repair-audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "repair-audit.html").write_text(render_html(report), encoding="utf-8")
    lines = []
    for c in report["checks"]:
        lines.append("\t".join(
            str(x).replace("\t", " ").replace("\n", " ") for x in
            ("Repair Audit", c["title"], c["status"], c["evidence"], c["guidance"])
        ))
    (out_dir / "repair-audit.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"checks": len(report["checks"]),
                      "warnings": sum(x["status"] == "WARN" for x in report["checks"]),
                      "failures": sum(x["status"] == "FAIL" for x in report["checks"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
