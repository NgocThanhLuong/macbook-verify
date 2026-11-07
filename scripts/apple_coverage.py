#!/usr/bin/env python3
"""Apple device provenance & coverage companion for MacBook Verify.

IMPORTANT: Apple does not publish a general anonymous warranty-check API.
This tool NEVER guesses AppleCare dates, silently transmits a serial, solves a
CAPTCHA, or conflates Apple purchase-date status with first activation.

It offers an official-site handoff (copy serial, open site), local metadata,
user-assisted import of observed Apple results, and a transparent HTML report.
"""
from __future__ import annotations
import argparse
from datetime import date, datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import webbrowser

CHECK_URL = "https://checkcoverage.apple.com/"
SUPPORT_URL = "https://mysupport.apple.com/"
APPLE_HELP = "https://support.apple.com/vi-vn/102607"
FIELDS = ("purchase_date", "activation_date", "warranty_expires", "applecare_expires", "manufacture_date")
SOURCES = ("apple_coverage_user_capture", "receipt", "user_supplied", "repair_record")
LIMIT = 64 * 1024


def validate_serial(value: str) -> str:
    serial = value.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{8,14}", serial):
        raise ValueError("Serial must be 8–14 alphanumeric characters")
    return serial


def valid_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except (ValueError, AttributeError):
        raise ValueError("Dates must be ISO YYYY-MM-DD")


def key_for(serial: str) -> str:
    return hashlib.sha256(serial.encode("ascii")).hexdigest()[:24]


def model_metadata(identifier: str, model_file: Path) -> dict:
    result = {"model_identifier": identifier, "model_year": None, "model_name": ""}
    if not model_file.is_file():
        return result
    for line in model_file.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) > 2 and parts[0] == identifier:
            result["model_name"] = parts[1]
            try:
                result["model_year"] = int(parts[2])
            except ValueError:
                pass
            break
    return result


def classify_serial(serial: str) -> dict:
    """Never decode random 2021+ serials as manufacturing timestamps."""
    return {
        "format": "randomized_or_undocumented" if len(serial) != 11 and len(serial) != 12 else
                  "legacy_length_ambiguous",
        "manufacture_date": None,
        "reason": "Modern Apple serials do not encode manufacture dates. Legacy length alone is insufficient to prove date/plant.",
    }


def import_record(path: Path, serial: str) -> dict:
    if path.stat().st_size > LIMIT:
        raise ValueError("Coverage import exceeds 64 KB")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Coverage import must be a JSON object")
    if validate_serial(str(data.get("serial", ""))) != serial:
        raise ValueError("Imported serial must exactly match this Mac")
    source = data.get("source", "user_supplied")
    if source not in SOURCES:
        raise ValueError("Unrecognized coverage source")
    dates = {}
    for field in FIELDS:
        raw = data.get(field)
        dates[field] = valid_date(raw) if raw is not None else None
    if dates["manufacture_date"] and source not in ("receipt", "repair_record"):
        raise ValueError("Manufacture date requires explicit documentary evidence")
    if dates["activation_date"] and source == "apple_coverage_user_capture":
        raise ValueError("Apple Coverage alone does not establish exact first activation date")
    return {
        "serial": serial,
        "source": source,
        "verified_by_tool": False,
        "source_description": str(data.get("source_description", ""))[:200],
        "coverage_type": str(data.get("coverage_type", "Unknown"))[:100],
        "purchase_date_status": str(data.get("purchase_date_status", "Unknown"))[:100],
        "notes": str(data.get("notes", ""))[:500],
        "captured_at": datetime.now(timezone.utc).isoformat(),
        **dates
    }


def stored_path(folder: Path, serial: str) -> Path:
    return folder / (key_for(serial) + ".json")


def record_from_disk(folder: Path, serial: str) -> dict | None:
    path = stored_path(folder, serial)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("serial") == serial:
            return data
    except (OSError, ValueError, AttributeError):
        pass
    return None


def import_clipboard_text(text: str, serial: str) -> dict:
    """Conservative parsing for Apple Coverage *user-copied* text, never site-authenticated."""
    if len(text) > LIMIT:
        raise ValueError("Clipboard text exceeds 64 KB")
    # All dates must be captured from a specifically labelled line, not from
    # unrelated Apple web page text. Common English formats only, ISO fallback.
    expires_pattern = re.compile(
        r"(?:Estimated Expiration Date|Expires?|Expiration Date)\s*[:\-\s]+\s*"
        r"([A-Za-z]+ \d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2})",
        re.I
    )
    match = expires_pattern.search(text)
    expiry = None
    if match:
        raw = match.group(1).strip()
        for fmt in ("%B %d, %Y", "%B %d %Y", "%Y-%m-%d"):
            try:
                expiry = datetime.strptime(raw, fmt).date().isoformat()
                break
            except ValueError:
                continue
    return {
        "serial": serial, "source": "apple_coverage_user_capture",
        "source_description": "User copied text from Apple Coverage; not machine-authenticated",
        "purchase_date_status": "Valid Purchase Date" if re.search(r"\bValid Purchase Date\b", text, re.I) else "Unknown",
        "coverage_type": "AppleCare" if re.search(r"AppleCare", text, re.I) else
                         "Limited Warranty" if re.search(r"Limited Warranty", text, re.I) else "Unknown",
        "warranty_expires": expiry,
        "activation_date": None,
        "manufacture_date": None,
        "notes": "Expiry parsed from copied text; verify which coverage plan it belongs to." if expiry else "No reliably parsable expiry date. Enter documented date using JSON import.",
    }


def generate_report(serial: str, model: dict, saved: dict | None, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    facts = classify_serial(serial)
    now = date.today()
    dates = {field: (saved or {}).get(field) for field in FIELDS}
    expiration = dates["applecare_expires"] or dates["warranty_expires"]
    status = "UNVERIFIED"
    if expiration:
        status = "EXPIRED" if date.fromisoformat(expiration) < now else "ACTIVE (USER-SUPPLIED)"
    result = {
        "serial": serial,
        "model_identifier": model.get("model_identifier", ""),
        "model_name": model.get("model_name", ""),
        "model_year": model.get("model_year"),
        "model_year_is_manufacture_year": False,
        "serial_format": facts["format"],
        "manufacture_date": dates["manufacture_date"],
        "activation_date": dates["activation_date"],
        "purchase_date": dates["purchase_date"],
        "warranty_expires": dates["warranty_expires"],
        "applecare_expires": dates["applecare_expires"],
        "coverage_type": (saved or {}).get("coverage_type", "Unknown"),
        "purchase_date_status": (saved or {}).get("purchase_date_status", "Unknown"),
        "coverage_status": status,
        "provenance": (saved or {}).get("source", "not_available"),
        "verified_by_tool": False,
        "observed_at": (saved or {}).get("captured_at"),
        "source_description": (saved or {}).get("source_description", ""),
        "note": "The Apple website may require a CAPTCHA/sign-in. This tool has no public warranty API access.",
        "check_url": CHECK_URL,
        "support_url": SUPPORT_URL,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "apple-coverage.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    e = lambda x: html.escape(str(x or "Chưa xác minh"), quote=True)
    rows = []
    labels = [
        ("Đời máy (model year)", str(result["model_year"]) if result["model_year"] else None,
         "Đây là năm model được giới thiệu, KHÔNG phải ngày sản xuất"),
        ("Ngày sản xuất", result["manufacture_date"],
         "Apple không mã hóa ngày sản xuất trong serial ngẫu nhiên từ 2021"),
        ("Ngày kích hoạt đầu tiên", result["activation_date"],
         "Không suy đoán từ ngày mua hoặc hạn bảo hành"),
        ("Ngày mua được ghi nhận", result["purchase_date"],
         "Dữ liệu chỉ có khi người dùng nhập từ chứng từ chính thức"),
        ("Tình trạng ngày mua", result["purchase_date_status"],
         "Valid Purchase Date không cung cấp ngày kích hoạt"),
        ("Loại bảo hành", result["coverage_type"],
         "Thông tin do người dùng đối chiếu nguồn Apple"),
        ("Ngày hết bảo hành giới hạn", result["warranty_expires"],
         "Kiểm tra trực tiếp trên website Apple"),
        ("Ngày hết AppleCare", result["applecare_expires"],
         "Nếu không có gói AppleCare, để trống"),
    ]
    for title, value, note in labels:
        rows.append("<tr><td>" + e(title) + "</td><td><strong>" + e(value) +
                    "</strong></td><td class='muted'>" + e(note) + "</td></tr>")
    # No external serial transfer except a user-initiated official Apple form.
    template = """<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MacBook Verify | Apple Coverage</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{background:#0c1424;color:#e7efff;font:15px system-ui,-apple-system,sans-serif;margin:0}
main{max-width:1080px;margin:auto;padding:30px}section{background:#172239;border:1px solid #344762;padding:25px;border-radius:18px;margin:15px 0}
h1{margin:0 0 8px;font-size:30px}h2{margin:0 0 12px}.muted{color:#aebdda}
button,a.action{display:inline-block;background:#345eaf;border:0;border-radius:9px;padding:12px 16px;color:#fff;text-decoration:none;font-weight:700;cursor:pointer;margin:3px}
code{color:#a3dcfa;overflow-wrap:anywhere}table{width:100%;border-collapse:collapse}td{border-bottom:1px solid #334560;padding:12px;vertical-align:top}
input,select,textarea{width:100%;background:#111d31;border:1px solid #426080;border-radius:8px;color:white;padding:11px;font:inherit}
label{display:block;margin:12px 0 6px;color:#acbedb}.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:15px}
.notice{border-left:4px solid #eab308;padding:15px;background:#332b1a;border-radius:10px}
@media(max-width:720px){.grid{grid-template-columns:1fr}main{padding:12px}section{padding:15px}}
</style></head><body><main><section><h1>Apple Coverage & Provenance</h1>
<p class="muted">Serial: <code id="serial"></code> · Model <strong id="model"></strong></p>
<button id="copy">Copy serial</button><a class="action" href="https://checkcoverage.apple.com/" target="_blank" rel="noopener">Apple Check Coverage</a>
<a class="action" href="https://mysupport.apple.com/" target="_blank" rel="noopener">My Support</a>
<p id="copyMessage" class="muted"></p>
<p class="notice"><b>Giới hạn xác minh:</b> Apple có thể yêu cầu CAPTCHA/đăng nhập. Ứng dụng không sử dụng API không chính thức và không tự gửi serial.
Ngày sản xuất của Mac 2021+ không thể suy ra từ serial ngẫu nhiên. Ngày mua không đồng nghĩa ngày kích hoạt.</p></section>
<section><h2>Thông tin hiện có</h2><table>__ROWS__</table>
<p class="muted">Coverage status: __STATUS__ · Source: __SOURCE__. Những ngày ghi nhận từ người dùng không được phần mềm xác thực với máy chủ Apple.</p></section>
<section><h2>Ghi nhận kết quả từ Apple (không gửi lên server)</h2><p class="muted">Mở Check Coverage, điền serial từ clipboard và xác minh theo yêu cầu của Apple.
Sau đó nhập ngày Apple hiển thị hoặc dán kết quả được sao chép. Tải JSON để cập nhật báo cáo bằng lệnh CLI.</p>
<label>Paste text từ Apple Coverage</label><textarea id="paste" rows="4" placeholder="Paste text from official Apple page"></textarea>
<button id="parse">Parse ngày hết hạn (English)</button><div class="grid">
<div><label>Ngày hết bảo hành (YYYY-MM-DD)</label><input type="date" id="warranty"></div>
<div><label>Ngày hết AppleCare (YYYY-MM-DD)</label><input type="date" id="applecare"></div>
<div><label>Ngày mua (nếu chứng từ hiển thị chính xác)</label><input type="date" id="purchase"></div>
<div><label>Loại bảo hành</label><select id="type"><option>Unknown</option><option>Limited Warranty</option><option>AppleCare</option><option>Coverage Expired</option></select></div>
</div><label>Ghi chú chứng từ</label><input id="notes" placeholder="Proof of Coverage / receipt / screenshot">
<button id="download">Export coverage-import.json</button>
<p id="info" class="muted">Ghi nhận do người dùng nhập, không được hệ thống tự xác thực.</p>
<pre>python3 scripts/apple_coverage.py --serial SERIAL --import-json coverage-import.json --out-dir /path/to/report</pre>
</section></main>
<script>
const serial=__SERIAL_JSON__, model=__MODEL_JSON__;
document.getElementById("serial").textContent=serial;
document.getElementById("model").textContent=model;
const info=document.getElementById("info");
document.getElementById("copy").onclick=async function(){
  try { await navigator.clipboard.writeText(serial); document.getElementById("copyMessage").textContent="Copied"; }
  catch(e){const ta=document.createElement("textarea");ta.value=serial;document.body.appendChild(ta);ta.select();
    document.execCommand("copy");ta.remove();document.getElementById("copyMessage").textContent="Serial selected for copying";}
};
document.getElementById("parse").onclick=function(){
const txt=document.getElementById("paste").value;
const found=txt.match(/(?:Estimated Expiration Date|Expires?|Expiration Date)\s*[:\-\s]+\s*([A-Za-z]+ \d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2})/i);
if(!found){info.textContent="Không phát hiện nhãn ngày hết hạn rõ ràng, hãy nhập thủ công.";return}
const dt=new Date(found[1]);
if(!Number.isNaN(dt.valueOf())) {
  document.getElementById("warranty").value=dt.getFullYear()+"-"+String(dt.getMonth()+1).padStart(2,"0")+"-"+String(dt.getDate()).padStart(2,"0");
  info.textContent="Parsed date from pasted text. Verify coverage type/expiry against Apple page.";
}
};
document.getElementById("download").onclick=function(){
const g=id=>document.getElementById(id).value;
const data={serial,source:"apple_coverage_user_capture",source_description:"Manually transcribed from Apple's site",
warranty_expires:g("warranty")||null,applecare_expires:g("applecare")||null,purchase_date:g("purchase")||null,
coverage_type:g("type"),notes:g("notes"),manufacture_date:null,activation_date:null};
const blob=new Blob([JSON.stringify(data,null,2)],{type:"application/json"});
const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="coverage-import.json";a.click();
setTimeout(()=>URL.revokeObjectURL(a.href),500);
info.textContent="Exported. Run import CLI to include data in next report.";
};
</script></body></html>"""
    page = template.replace("__ROWS__", "".join(rows)).replace("__STATUS__", e(status))
    page = page.replace("__SOURCE__", e(result["provenance"]))
    page = page.replace("__SERIAL_JSON__", json.dumps(serial).replace("<", "\\u003c"))
    page = page.replace("__MODEL_JSON__", json.dumps(model.get("model_name", "")).replace("<", "\\u003c"))
    (out_dir / "apple-coverage.html").write_text(page, encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Local Apple coverage and provenance evidence")
    p.add_argument("--serial", required=True, help="Mac's system serial, local use only")
    p.add_argument("--model-identifier", default="")
    p.add_argument("--models-file", default=str(Path(__file__).resolve().parents[1] / "data" / "models.tsv"))
    p.add_argument("--out-dir", required=True)
    p.add_argument("--cache-dir", default=str(Path.home() / ".macbook-verify" / "coverage"))
    p.add_argument("--import-json", type=Path, help="Explicit human-confirmed Apple/receipt evidence")
    p.add_argument("--import-clipboard", action="store_true", help="Use clipboard text copied from official Apple coverage page")
    p.add_argument("--open-official", action="store_true", help="Explicit action: copy serial and open Apple website")
    args = p.parse_args(argv)
    try:
        serial = validate_serial(args.serial)
        folder = Path(args.cache_dir).expanduser()
        if args.import_json and args.import_clipboard:
            p.error("Choose only one import method")
        imported = None
        if args.import_json:
            imported = import_record(args.import_json, serial)
        elif args.import_clipboard:
            if sys.platform != "darwin":
                raise ValueError("Clipboard import requires macOS")
            clip = subprocess.run(["pbpaste"], capture_output=True, text=True, check=True, timeout=8).stdout
            data = import_clipboard_text(clip, serial)
            # No exact Apple activation or manufacture date available.
            imported = import_record_from_values(data)
        if imported:
            folder.mkdir(parents=True, exist_ok=True)
            stored_path(folder, serial).write_text(json.dumps(imported, ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                os.chmod(stored_path(folder, serial), 0o600)
            except OSError:
                pass
        saved = record_from_disk(folder, serial)
        model = model_metadata(args.model_identifier, Path(args.models_file))
        output = generate_report(serial, model, saved, Path(args.out_dir))
        if args.open_official:
            if sys.platform == "darwin" and shutil.which("pbcopy"):
                subprocess.run(["pbcopy"], input=serial, text=True, check=False, timeout=5)
            webbrowser.open(CHECK_URL)
        print(json.dumps({"serial": serial, "model_year": model.get("model_year"),
                          "manufacture_date": output["manufacture_date"],
                          "activation_date": output["activation_date"],
                          "warranty_expires": output["warranty_expires"],
                          "status": output["coverage_status"],
                          "source": output["provenance"]}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        print("Apple Coverage: " + str(exc), file=sys.stderr)
        return 2


def import_record_from_values(data: dict) -> dict:
    """Validate text capture same way as JSON file, without writing a scratch file."""
    serial = validate_serial(data["serial"])
    return {
        "serial": serial, "source": "apple_coverage_user_capture",
        "source_description": str(data.get("source_description", ""))[:200],
        "purchase_date_status": str(data.get("purchase_date_status", "Unknown"))[:100],
        "coverage_type": str(data.get("coverage_type", "Unknown"))[:100],
        "notes": str(data.get("notes", ""))[:500],
        "verified_by_tool": False, "captured_at": datetime.now(timezone.utc).isoformat(),
        **{k: (valid_date(data.get(k)) if data.get(k) else None) for k in FIELDS}
    }


if __name__ == "__main__":
    raise SystemExit(main())
