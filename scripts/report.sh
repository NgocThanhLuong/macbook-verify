#!/bin/bash

generate_report() {
  mbv_step "Generating dashboard and interactive verification wizard"
  set -- $(status_counts)
  PASS_COUNT="$1"; WARN_COUNT="$2"; FAIL_COUNT="$3"; INFO_COUNT="$4"; SKIP_COUNT="$5"
  SCORE="$(health_score)"

  if [ "$FAIL_COUNT" -gt 0 ]; then VERDICT="PHÁT HIỆN LỖI — CẦN KIỂM TRA"; VERDICT_CLASS="fail";
  elif [ "$WARN_COUNT" -gt 2 ]; then VERDICT="CẦN KIỂM TRA CẢNH BÁO"; VERDICT_CLASS="warn";
  else VERDICT="CHƯA PHÁT HIỆN LỖI RÕ TRONG BÀI TEST"; VERDICT_CLASS="pass"; fi


  MODEL_YEAR_COVERAGE="Unknown"
  MANUFACTURE_DATE_COVERAGE="Unverified"
  ACTIVATION_DATE_COVERAGE="Unverified"
  WARRANTY_EXPIRES_COVERAGE="Unverified"
  APPLECARE_EXPIRES_COVERAGE="Unverified"
  COVERAGE_SOURCE_COVERAGE="Unavailable"
  if [ -s "$OUT_DIR/apple-coverage.json" ] && command -v python3 >/dev/null 2>&1; then
    _cov="$(/usr/bin/env python3 - "$OUT_DIR/apple-coverage.json" <<'PY_COV'
import json,sys
try:
    d=json.load(open(sys.argv[1]))
    keys=("model_year","manufacture_date","activation_date","warranty_expires","applecare_expires","provenance")
    for k in keys:
        v=d.get(k)
        print("".join(c for c in str(v if v is not None else "Unverified") if c.isalnum() or c in "-_./ ()")[:60])
except (OSError,ValueError):
    print("\n".join(["Unverified"]*6))
PY_COV
)"
    MODEL_YEAR_COVERAGE="$(printf '%s\n' "$_cov" | /usr/bin/sed -n '1p')"
    MANUFACTURE_DATE_COVERAGE="$(printf '%s\n' "$_cov" | /usr/bin/sed -n '2p')"
    ACTIVATION_DATE_COVERAGE="$(printf '%s\n' "$_cov" | /usr/bin/sed -n '3p')"
    WARRANTY_EXPIRES_COVERAGE="$(printf '%s\n' "$_cov" | /usr/bin/sed -n '4p')"
    APPLECARE_EXPIRES_COVERAGE="$(printf '%s\n' "$_cov" | /usr/bin/sed -n '5p')"
    COVERAGE_SOURCE_COVERAGE="$(printf '%s\n' "$_cov" | /usr/bin/sed -n '6p')"
  fi


  BAT_NOMINAL="N/A"
  BAT_RAW="N/A"
  BAT_SIGNAL="N/A"
  BAT_CONFIDENCE="UNAVAILABLE"
  if command -v python3 >/dev/null 2>&1 && [ -s "$OUT_DIR/battery-report.json" ]; then
    _battery="$(/usr/bin/env python3 - "$OUT_DIR/battery-report.json" <<'PY_BAT'
import json,sys
try:
    r=json.load(open(sys.argv[1]))
    values=(
        r.get("capacity",{}).get("capacity_health_percent"),
        r.get("capacity",{}).get("raw_health_percent"),
        r.get("diagnostic_signal_score"),
        r.get("evidence_confidence")
    )
    print("\n".join(str(x) if x is not None else "N/A" for x in values))
except (OSError,ValueError,TypeError):
    print("N/A\nN/A\nN/A\nUNAVAILABLE")
PY_BAT
)"
    BAT_NOMINAL="$(printf '%s\n' "$_battery" | /usr/bin/sed -n '1p')"
    BAT_RAW="$(printf '%s\n' "$_battery" | /usr/bin/sed -n '2p')"
    BAT_SIGNAL="$(printf '%s\n' "$_battery" | /usr/bin/sed -n '3p')"
    BAT_CONFIDENCE="$(printf '%s\n' "$_battery" | /usr/bin/sed -n '4p')"
  fi



  SSD_USED="N/A"
  SSD_LIFE="N/A"
  SSD_TBW="N/A"
  SSD_SIGNAL="N/A"
  SSD_EVIDENCE="UNAVAILABLE"
  SSD_DEEP_STATUS="UNKNOWN"
  if command -v python3 >/dev/null 2>&1 && [ -s "$OUT_DIR/ssd-report.json" ]; then
    _ssd="$(/usr/bin/env python3 - "$OUT_DIR/ssd-report.json" <<'PY_SSD'
import json,sys
try:
    data=json.load(open(sys.argv[1]))
    devices=data.get("records",[])
    internal=[r for r in devices if str(r.get("device","")).startswith("/dev/disk")]
    r=(internal or devices or [{}])[0]
    m=r.get("metrics",{})
    def metric(k):
        v=m.get(k,{}).get("value")
        return "N/A" if v is None else str(v)
    values=[metric("percentage_used"),metric("estimated_lifetime_left"),
            metric("total_written_tb"),r.get("diagnostic_signal_score"),
            r.get("evidence_confidence","UNAVAILABLE"),r.get("status","UNKNOWN")]
    print("\n".join(str(v) if v is not None else "N/A" for v in values))
except (OSError,ValueError,TypeError,AttributeError):
    print("N/A\nN/A\nN/A\nN/A\nUNAVAILABLE\nUNKNOWN")
PY_SSD
)"
    SSD_USED="$(printf '%s\n' "$_ssd" | /usr/bin/sed -n '1p')"
    SSD_LIFE="$(printf '%s\n' "$_ssd" | /usr/bin/sed -n '2p')"
    SSD_TBW="$(printf '%s\n' "$_ssd" | /usr/bin/sed -n '3p')"
    SSD_SIGNAL="$(printf '%s\n' "$_ssd" | /usr/bin/sed -n '4p')"
    SSD_EVIDENCE="$(printf '%s\n' "$_ssd" | /usr/bin/sed -n '5p')"
    SSD_DEEP_STATUS="$(printf '%s\n' "$_ssd" | /usr/bin/sed -n '6p')"
  fi


  PRO_CHIP="$CHIP"
  PRO_GPU_NAME="Không có dữ liệu"
  PRO_GPU_CORES="$GPU_CORES"
  PRO_CPU_PHYSICAL="$CPU_CORES"
  PRO_CPU_PERF="N/A"
  PRO_CPU_EFF="N/A"
  PRO_MEM="$MEMORY"
  PRO_FIRMWARE="N/A"
  if [ -s "$OUT_DIR/system-information.json" ] && command -v python3 >/dev/null 2>&1; then
    _p="$(/usr/bin/env python3 - "$OUT_DIR/system-information.json" <<'PY_PRO'
import json,sys
try:
    d=json.load(open(sys.argv[1]))
    c=d.get("cpu") or {}
    g=d.get("gpu") or {}
    devices=g.get("devices") or []
    gpu=devices[0] if devices else {}
    levels=c.get("performance_efficiency_clusters") or []
    perf=next((x.get("số_lõi") for x in levels if "performance" in str(x.get("loại","")).lower()),None)
    eff=next((x.get("số_lõi") for x in levels if "efficiency" in str(x.get("loại","")).lower()),None)
    fields=[c.get("chip"),gpu.get("name"),gpu.get("cores"),c.get("physical_cores"),
            perf,eff,(d.get("hardware") or {}).get("physical_memory"),c.get("firmware")]
    for v in fields:
        print("".join(ch for ch in str(v if v is not None else "N/A") if ch.isalnum() or ch in " .,_-/()")[:90])
except (OSError,ValueError,TypeError):
    print("N/A\n"*8,end="")
PY_PRO
)"
    PRO_CHIP="$(printf '%s\n' "$_p" | /usr/bin/sed -n '1p')"
    PRO_GPU_NAME="$(printf '%s\n' "$_p" | /usr/bin/sed -n '2p')"
    PRO_GPU_CORES="$(printf '%s\n' "$_p" | /usr/bin/sed -n '3p')"
    PRO_CPU_PHYSICAL="$(printf '%s\n' "$_p" | /usr/bin/sed -n '4p')"
    PRO_CPU_PERF="$(printf '%s\n' "$_p" | /usr/bin/sed -n '5p')"
    PRO_CPU_EFF="$(printf '%s\n' "$_p" | /usr/bin/sed -n '6p')"
    PRO_MEM="$(printf '%s\n' "$_p" | /usr/bin/sed -n '7p')"
    PRO_FIRMWARE="$(printf '%s\n' "$_p" | /usr/bin/sed -n '8p')"
  fi

  ID_SCORE="$(area_score Identity)"; BAT_SCORE="$(area_score Battery)"; SSD_SCORE="$(area_score Storage)"; ACTIVE_SCORE="$(area_score Active)"

  cat > "$OUT_DIR/summary.txt" <<EOF_SUMMARY
MacBook Verify v$VERSION
Generated: $(date)
Mode: $MODE

Model: ${MODEL_NAME:-Unknown}
Model Identifier: ${MODEL_IDENTIFIER:-Unknown}
Model Number: ${MODEL_NUMBER:-Unknown}
Chip: ${CHIP:-Unknown}
CPU physical cores: ${PRO_CPU_PHYSICAL:-N/A}
CPU performance cores: ${PRO_CPU_PERF:-N/A}
CPU efficiency cores: ${PRO_CPU_EFF:-N/A}
GPU name: ${PRO_GPU_NAME:-N/A}
GPU cores: ${PRO_GPU_CORES:-N/A}
Firmware: ${PRO_FIRMWARE:-N/A}
CPU: ${CPU_CORES:-Unknown}
GPU: ${GPU_CORES:-Unknown}
Memory: ${MEMORY:-Unknown}
Serial: ${SYSTEM_SERIAL:-Unknown}
macOS: ${OS_VERSION:-Unknown} (${OS_BUILD:-Unknown})

Battery: ${BATTERY_MAX_CAP:-Unknown}, ${BATTERY_CYCLES:-Unknown} cycles, ${BATTERY_CONDITION:-Unknown}
Battery nominal health: ${BAT_NOMINAL:-N/A}%
Battery raw health: ${BAT_RAW:-N/A}%
Battery diagnostic signal (not health %): ${BAT_SIGNAL:-N/A}/100
SSD: ${SSD_MODEL:-Unknown}, ${SSD_CAPACITY:-Unknown}, SMART=${SSD_SMART:-Unknown}
SSD endurance used (NVMe): ${SSD_USED:-N/A}%
SSD total written: ${SSD_TBW:-N/A} TB
SSD diagnostic signal (not wear %): ${SSD_SIGNAL:-N/A}/100
SSD evidence: ${SSD_EVIDENCE:-UNAVAILABLE}
Apple model year: ${MODEL_YEAR_COVERAGE}
Manufacture: ${MANUFACTURE_DATE_COVERAGE} (not inferred from serial)
First activation: ${ACTIVATION_DATE_COVERAGE} (not inferred from warranty)
Apple warranty expiry: ${WARRANTY_EXPIRES_COVERAGE}
AppleCare expiry: ${APPLECARE_EXPIRES_COVERAGE}
Coverage evidence source: ${COVERAGE_SOURCE_COVERAGE}
Display: ${DISPLAY_TYPE:-Unknown}, ${DISPLAY_RESOLUTION:-Unknown}

PASS=$PASS_COUNT WARN=$WARN_COUNT FAIL=$FAIL_COUNT INFO=$INFO_COUNT SKIP=$SKIP_COUNT
Health score: $SCORE/100
Verdict: $VERDICT

IMPORTANT: A PASS does not prove that a genuine Apple part was never replaced, nor that board-level repair never occurred. Physical inspection and Apple Parts & Service history remain necessary.
EOF_SUMMARY

  cat > "$OUT_DIR/summary.json" <<EOF_JSON
{
  "tool": "MacBook Verify",
  "version": "$(json_escape "$VERSION")",
  "mode": "$(json_escape "$MODE")",
  "generated_at": "$(json_escape "$(date '+%Y-%m-%dT%H:%M:%S%z')")",
  "model": "$(json_escape "${MODEL_NAME:-}")",
  "model_identifier": "$(json_escape "${MODEL_IDENTIFIER:-}")",
  "model_number": "$(json_escape "${MODEL_NUMBER:-}")",
  "chip": "$(json_escape "${CHIP:-}")",
  "memory": "$(json_escape "${MEMORY:-}")",
  "cpu_physical_cores": "$(json_escape "${PRO_CPU_PHYSICAL:-N/A}")",
  "cpu_performance_cores": "$(json_escape "${PRO_CPU_PERF:-N/A}")",
  "cpu_efficiency_cores": "$(json_escape "${PRO_CPU_EFF:-N/A}")",
  "gpu_name": "$(json_escape "${PRO_GPU_NAME:-N/A}")",
  "gpu_cores": "$(json_escape "${PRO_GPU_CORES:-N/A}")",
  "firmware": "$(json_escape "${PRO_FIRMWARE:-N/A}")",
  "serial": "$(json_escape "${SYSTEM_SERIAL:-}")",
  "macos": "$(json_escape "${OS_VERSION:-}")",
  "battery_max_capacity": "$(json_escape "${BATTERY_MAX_CAP:-}")",
  "battery_cycles": "$(json_escape "${BATTERY_CYCLES:-}")",
  "battery_deep": {
    "capacity_health_percent": "$(json_escape "${BAT_NOMINAL:-N/A}")",
    "raw_health_percent": "$(json_escape "${BAT_RAW:-N/A}")",
    "diagnostic_signal_score": "$(json_escape "${BAT_SIGNAL:-N/A}")",
    "evidence_confidence": "$(json_escape "${BAT_CONFIDENCE:-UNAVAILABLE}")"
  },
  "ssd_model": "$(json_escape "${SSD_MODEL:-}")",
  "ssd_deep": {
    "endurance_used_percent": "$(json_escape "${SSD_USED:-N/A}")",
    "estimated_endurance_remaining_percent": "$(json_escape "${SSD_LIFE:-N/A}")",
    "total_written_tb": "$(json_escape "${SSD_TBW:-N/A}")",
    "diagnostic_signal_score": "$(json_escape "${SSD_SIGNAL:-N/A}")",
    "evidence_confidence": "$(json_escape "${SSD_EVIDENCE:-UNAVAILABLE}")",
    "status": "$(json_escape "${SSD_DEEP_STATUS:-UNKNOWN}")"
  },
  "apple_coverage": {
    "model_year": "$(json_escape "${MODEL_YEAR_COVERAGE:-}")",
    "manufacture_date": "$(json_escape "${MANUFACTURE_DATE_COVERAGE:-}")",
    "activation_date": "$(json_escape "${ACTIVATION_DATE_COVERAGE:-}")",
    "warranty_expires": "$(json_escape "${WARRANTY_EXPIRES_COVERAGE:-}")",
    "applecare_expires": "$(json_escape "${APPLECARE_EXPIRES_COVERAGE:-}")",
    "source": "$(json_escape "${COVERAGE_SOURCE_COVERAGE:-}")"
  },
  "display": "$(json_escape "${DISPLAY_TYPE:-}")",
  "score": $SCORE,
  "verdict": "$(json_escape "$VERDICT")",
  "counts": {"pass":$PASS_COUNT,"warn":$WARN_COUNT,"fail":$FAIL_COUNT,"info":$INFO_COUNT,"skip":$SKIP_COUNT}
}
EOF_JSON

  ROWS="$OUT_DIR/.result-rows.html"; : > "$ROWS"
  while IFS="$(printf '\t')" read -r _area _test _status _value _detail; do
    [ -z "$_area" ] && continue
    _css="$(printf '%s' "$_status" | /usr/bin/tr '[:upper:]' '[:lower:]')"
    cat >> "$ROWS" <<EOF_ROW
<tr data-area="$(html_escape "$_area")" data-status="$(html_escape "$_status")"><td><span class="badge $_css">$(html_escape "$_status")</span></td><td>$(html_escape "$_area")</td><td><strong>$(html_escape "$_test")</strong></td><td>$(html_escape "$_value")</td><td class="detail">$(html_escape "$_detail")</td></tr>
EOF_ROW
  done < "$RESULTS_FILE"

  _serial_js="$(json_escape "${SYSTEM_SERIAL:-}")"
  _report_key="mbv-${SYSTEM_SERIAL:-unknown}-${TIMESTAMP}"

  cat > "$OUT_DIR/report.html" <<EOF_HTML
<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MacBook Verify — ${MODEL_IDENTIFIER:-Mac}</title>
<style>
:root{--bg:#0b1020;--panel:#121a2d;--panel2:#19233a;--text:#edf2ff;--muted:#9aa9c6;--pass:#38d996;--warn:#ffbd4a;--fail:#ff647c;--info:#6eb7ff;--skip:#7f8aa5;--line:#273450;--accent:#8aa8ff}*{box-sizing:border-box}body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display",Inter,system-ui,sans-serif;background:linear-gradient(160deg,#080d18,#10182a 50%,#0a1020);color:var(--text)}.wrap{max-width:1240px;margin:auto;padding:28px}.hero{display:grid;grid-template-columns:1.4fr .8fr;gap:18px}.card{background:rgba(18,26,45,.94);border:1px solid var(--line);border-radius:18px;padding:20px;box-shadow:0 14px 50px #0005}.eyebrow{color:var(--accent);font-size:12px;font-weight:800;letter-spacing:.12em;text-transform:uppercase}h1{font-size:36px;margin:7px 0 8px}h2{margin:4px 0 16px;font-size:22px}h3{margin:14px 0 8px}.muted{color:var(--muted)}.verdict{font-weight:900;font-size:24px}.verdict.pass{color:var(--pass)}.verdict.warn{color:var(--warn)}.verdict.fail{color:var(--fail)}.score{font-size:58px;font-weight:900;line-height:1}.score small{font-size:20px;color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}.metric{background:var(--panel2);border:1px solid var(--line);padding:15px;border-radius:14px}.metric b{display:block;font-size:24px;margin-top:4px}.p{color:var(--pass)}.w{color:var(--warn)}.f{color:var(--fail)}.i{color:var(--info)}.tabs{display:flex;flex-wrap:wrap;gap:8px;margin:24px 0 12px}.tabs button,.btn{border:1px solid var(--line);background:var(--panel2);color:var(--text);border-radius:10px;padding:10px 14px;cursor:pointer;font-weight:700}.tabs button.active,.btn.primary{background:#304b91;border-color:#5979ce}.btn.good{background:#174c3c}.btn.bad{background:#592738}.btn.warn{background:#594521}.btn.skip{background:#30384b}.section{margin-top:20px}.tableWrap{overflow:auto;border:1px solid var(--line);border-radius:14px}table{border-collapse:collapse;width:100%;min-width:900px;background:#111a2c}th,td{text-align:left;padding:11px 12px;border-bottom:1px solid #202d49;vertical-align:top}th{position:sticky;top:0;background:#17223a;z-index:1;color:#b9c8e6}.detail{color:#b7c4dc;max-width:520px}.badge{font-size:11px;padding:4px 8px;border-radius:999px;font-weight:900}.badge.pass{color:#09261c;background:var(--pass)}.badge.warn{color:#382400;background:var(--warn)}.badge.fail{color:#35000a;background:var(--fail)}.badge.info{color:#061d37;background:var(--info)}.badge.skip{color:#fff;background:var(--skip)}.facts{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.fact{padding:11px;border-radius:10px;background:#0d1527;border:1px solid var(--line)}.fact span{display:block;color:var(--muted);font-size:12px}.manual{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}.manualItem{background:#0d1527;border:1px solid var(--line);border-radius:13px;padding:14px}.manualItem .choices{display:flex;gap:6px;flex-wrap:wrap;margin-top:9px}.manualItem[data-result="PASS"]{border-color:#2d8d68}.manualItem[data-result="FAIL"]{border-color:#b3485b}.manualItem[data-result="WARN"]{border-color:#b18738}.manualItem[data-result="SKIP"]{opacity:.65}.screenBtns{display:flex;gap:8px;flex-wrap:wrap}.screenColor{height:44px;min-width:70px}.kbd{display:grid;grid-template-columns:repeat(12,minmax(36px,1fr));gap:5px;margin-top:10px}.key{font-size:11px;padding:9px 4px;text-align:center;background:#202c45;border:1px solid #354666;border-radius:7px}.key.hit{background:#176e52;border-color:#35d39b}.trackpad{height:210px;border:2px dashed #526789;border-radius:18px;display:flex;align-items:center;justify-content:center;text-align:center;color:var(--muted);user-select:none;touch-action:manipulation}.trackStats{display:flex;gap:14px;flex-wrap:wrap;margin:10px 0}.mediaGrid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.preview{width:100%;max-height:300px;background:#000;border-radius:12px}.level{height:12px;background:#202b45;border-radius:999px;overflow:hidden}.level>div{height:100%;width:0;background:var(--pass)}.raw{display:flex;gap:8px;flex-wrap:wrap}.raw a{color:#a8c5ff;background:#0e1729;border:1px solid var(--line);padding:7px 9px;border-radius:8px;text-decoration:none}.notice{border-left:4px solid var(--warn);padding:12px 14px;background:#2b2315;border-radius:8px}.overlay{position:fixed;inset:0;z-index:9999;display:none;align-items:flex-end;justify-content:center}.overlayControls{padding:15px;margin:20px;background:#111a2ddd;border-radius:14px;display:flex;gap:8px;flex-wrap:wrap}.footer{margin:30px 0;color:var(--muted);font-size:13px}@media(max-width:820px){.hero,.manual,.mediaGrid{grid-template-columns:1fr}.grid{grid-template-columns:repeat(2,1fr)}.facts{grid-template-columns:1fr}.kbd{grid-template-columns:repeat(6,1fr)}.wrap{padding:14px}h1{font-size:28px}}@media print{body{background:#fff;color:#111}.card{box-shadow:none;border-color:#bbb;background:#fff}.muted,.detail{color:#555}.tabs,.interactiveOnly,.overlay{display:none!important}.tableWrap{overflow:visible}table{min-width:0;background:#fff}th{background:#eee;color:#111}.fact,.metric,.manualItem{background:#fafafa;color:#111}}
</style></head><body><div class="wrap">
<div class="hero"><div class="card"><div class="eyebrow">MacBook Verify v$VERSION · $MODE mode</div><h1>${MODEL_NAME:-MacBook} <span class="muted">${MODEL_IDENTIFIER:-}</span></h1><div class="verdict $VERDICT_CLASS">$VERDICT</div><p class="muted">Self-test + software-visible hardware evidence. Generated $(date '+%Y-%m-%d %H:%M:%S').</p><div class="facts"><div class="fact"><span>Chip</span>${CHIP:-Unknown}</div><div class="fact"><span>Memory</span>${MEMORY:-Unknown}</div><div class="fact"><span>Serial</span>${SYSTEM_SERIAL:-Unknown}</div><div class="fact"><span>Battery</span>${BATTERY_MAX_CAP:-?} · ${BATTERY_CYCLES:-?} cycles</div><div class="fact"><span>SSD</span>${SSD_MODEL:-Unknown}</div><div class="fact"><span>Display</span>${DISPLAY_RESOLUTION:-Unknown}</div></div></div>
<div class="card"><div class="eyebrow">Điểm tổng hợp bài kiểm tra</div><div class="score">$SCORE<small>/100</small></div><p class="muted">INFO/SKIP are excluded from scoring. A high score is not proof that every part is factory-original.</p><div class="grid"><div class="metric"><span class="muted">PASS</span><b class="p">$PASS_COUNT</b></div><div class="metric"><span class="muted">WARN</span><b class="w">$WARN_COUNT</b></div><div class="metric"><span class="muted">FAIL</span><b class="f">$FAIL_COUNT</b></div><div class="metric"><span class="muted">INFO</span><b class="i">$INFO_COUNT</b></div></div></div></div>
<div class="grid"><div class="metric"><span class="muted">Identity</span><b>$ID_SCORE</b></div><div class="metric"><span class="muted">Battery</span><b>$BAT_SCORE</b></div><div class="metric"><span class="muted">Storage</span><b>$SSD_SCORE</b></div><div class="metric"><span class="muted">Active tests</span><b>$ACTIVE_SCORE</b></div></div>
<div class="notice"><strong>Giới hạn quan trọng:</strong> phần mềm không thể chứng minh 100% máy chưa từng mở, chưa sửa main cấp linh kiện, hoặc chưa thay một linh kiện Apple chính hãng khác. Hãy dùng phần Interactive/Physical bên dưới cùng Parts & Service của macOS.</div>
<div class="section card">
<div class="eyebrow">Thông số phần cứng / System Information</div>
<h2>CPU · GPU · RAM · SSD · Firmware</h2>
<div class="facts">
  <div class="fact"><span>CPU / Chip</span>${PRO_CHIP:-N/A}</div>
  <div class="fact"><span>CPU lõi vật lý</span>${PRO_CPU_PHYSICAL:-N/A}</div>
  <div class="fact"><span>CPU hiệu năng (P-cores)</span>${PRO_CPU_PERF:-N/A}</div>
  <div class="fact"><span>CPU tiết kiệm (E-cores)</span>${PRO_CPU_EFF:-N/A}</div>
  <div class="fact"><span>GPU</span>${PRO_GPU_NAME:-N/A}</div>
  <div class="fact"><span>Số nhân GPU</span>${PRO_GPU_CORES:-N/A}</div>
  <div class="fact"><span>RAM unified</span>${PRO_MEM:-N/A}</div>
  <div class="fact"><span>SSD</span>${SSD_MODEL:-N/A} · ${SSD_CAPACITY:-N/A}</div>
  <div class="fact"><span>Firmware</span>${PRO_FIRMWARE:-N/A}</div>
</div>
<p class="muted">MacOS không cung cấp thông số nào thì hiển thị N/A. GPU Metal test kiểm tra phép tính; không chứng minh Neural Engine được sử dụng.</p>
<p><a class="btn primary" href="system-information.html">Xem toàn bộ System Information (CPU, GPU, RAM, màn hình, ổ cứng, cổng, bảo mật...)</a></p>
<p><a class="btn" href="compare-macs.html">So sánh hai máy và tính tiền cần bù</a></p>
<p><a class="btn" href="battery-discharge.html">Quan sát xả pin (tùy chọn)</a></p>
</div>
<div class="section card"><h2>Kết quả kiểm tra tự động</h2><div class="tabs" id="filters"><button class="active" data-filter="ALL">All</button><button data-filter="FAIL">FAIL</button><button data-filter="WARN">WARN</button><button data-filter="Battery">Battery</button><button data-filter="Active">Active</button><button data-filter="Storage">Storage</button><button data-filter="Ownership">Ownership</button><button data-filter="History">History</button></div><div class="tableWrap"><table id="results"><thead><tr><th>Status</th><th>Area</th><th>Test</th><th>Value</th><th>Assessment</th></tr></thead><tbody>
$(cat "$ROWS")
</tbody></table></div></div>
<div class="section card interactiveOnly"><div class="eyebrow">Kiểm tra thực tế</div><h2>Hướng dẫn kiểm tra ngoại hình và chức năng</h2><p class="muted">Các kết quả này do người kiểm tra xác nhận. Chúng được lưu cục bộ trong trình duyệt và không tự upload.</p>
<h3>1. Bottom-case serial & physical inspection</h3><div class="manual"><div class="manualItem" data-id="bottom-serial"><strong>Serial dưới đáy máy</strong><p class="muted">Nhập serial khắc ở đáy để so với system serial.</p><input id="bottomSerial" style="width:100%;padding:10px;border-radius:8px;border:1px solid var(--line);background:#080f1e;color:white" placeholder="Serial dưới đáy"><p id="serialResult" class="muted">Expected: ${SYSTEM_SERIAL:-Unknown}</p></div><div class="manualItem" data-id="screws"><strong>Ốc + nắp đáy</strong><p class="muted">Soi đầu ốc, màu ốc, mép cạy, khe chassis, tem/serial.</p><div class="choices"></div></div></div>
<h3>2. Display fullscreen test</h3><div class="screenBtns"><button class="btn screenColor" data-color="#fff" style="background:#fff;color:#111">White</button><button class="btn screenColor" data-color="#000" style="background:#000">Black</button><button class="btn screenColor" data-color="#808080" style="background:#808080">Gray</button><button class="btn screenColor" data-color="#f00" style="background:#f00">Red</button><button class="btn screenColor" data-color="#0f0" style="background:#0f0;color:#111">Green</button><button class="btn screenColor" data-color="#00f" style="background:#00f">Blue</button><button class="btn" id="gradientBtn">Gradient</button></div><div class="manualItem" data-id="display-visual" style="margin-top:10px"><strong>Pixel / uniformity / line / flicker</strong><div class="choices"></div></div>
<h3>3. Keyboard test</h3><p class="muted">Nhấn từng phím. Phím nhận được event sẽ chuyển xanh. Fn/brightness/media keys có thể bị macOS giữ lại.</p><div id="keyboard" class="kbd"></div><div class="manualItem" data-id="keyboard" style="margin-top:10px"><strong>Keyboard final result</strong><div class="choices"></div></div>
<h3>4. Trackpad test</h3><div id="trackpad" class="trackpad">Move pointer here · left/right click · scroll<br>Trackpad gesture events are partially browser-dependent.</div><div class="trackStats"><span>Move: <b id="moveCount">0</b></span><span>Click: <b id="clickCount">0</b></span><span>Right click: <b id="rightCount">0</b></span><span>Scroll: <b id="wheelCount">0</b></span></div><div class="manualItem" data-id="trackpad"><strong>Trackpad final result</strong><div class="choices"></div></div>
<h3>5. Speaker / microphone / camera</h3><div class="mediaGrid"><div class="manualItem" data-id="speaker"><strong>Stereo speaker test</strong><p class="muted">Nghe rõ từng bên, không rè/rung bất thường.</p><button class="btn" onclick="tone(-1)">◀ Left</button> <button class="btn" onclick="tone(1)">Right ▶</button> <button class="btn" onclick="tone(0)">Stereo</button><div class="choices"></div></div><div class="manualItem" data-id="media"><strong>Camera + microphone live test</strong><p class="muted">Browser sẽ xin quyền local. Camera phải lên hình; mic meter phải dao động khi nói.</p><button class="btn primary" id="startMedia">Start camera/mic</button> <button class="btn" id="stopMedia">Stop</button><video id="preview" class="preview" autoplay muted playsinline></video><div class="level"><div id="micLevel"></div></div><div class="choices"></div></div></div>
<h3>6. Ports / charging</h3><div class="manual" id="ports"></div>
<h3>7. Final physical checks</h3><div class="manual"><div class="manualItem" data-id="hinge"><strong>Hinge / chassis / lid</strong><div class="choices"></div></div><div class="manualItem" data-id="liquid"><strong>Liquid/corrosion signs</strong><div class="choices"></div></div><div class="manualItem" data-id="touchid"><strong>Touch ID enrollment/unlock</strong><div class="choices"></div></div><div class="manualItem" data-id="apple-diagnostics"><strong>Apple Diagnostics reboot test</strong><p class="muted">Apple Silicon: shut down → hold power until startup options → Command-D.</p><div class="choices"></div></div></div>
<div style="margin-top:16px"><button class="btn primary" id="exportManual">Export interactive-results.json</button> <button class="btn" onclick="window.print()">Print / Save PDF</button> <span id="manualSummary" class="muted"></span></div></div>
<div class="section card"><h2>Apple Coverage & Device Provenance</h2>
<p class="muted">Model year is not manufacture date. Apple's randomized 2021+ serials do not encode production date. First activation must not be inferred from warranty expiry.</p>
<div class="facts">
  <div class="fact"><span>Model year</span>${MODEL_YEAR_COVERAGE:-Unknown}</div>
  <div class="fact"><span>Manufactured</span>${MANUFACTURE_DATE_COVERAGE:-Unverified}</div>
  <div class="fact"><span>First activation</span>${ACTIVATION_DATE_COVERAGE:-Unverified}</div>
  <div class="fact"><span>Warranty expiry</span>${WARRANTY_EXPIRES_COVERAGE:-Unverified}</div>
  <div class="fact"><span>AppleCare expiry</span>${APPLECARE_EXPIRES_COVERAGE:-Unverified}</div>
  <div class="fact"><span>Evidence</span>${COVERAGE_SOURCE_COVERAGE:-Unavailable}</div>
</div><p><a class="btn primary" href="apple-coverage.html">Check official Apple coverage / import result</a></p></div>
<div class="section card"><h2>SSD Deep Diagnostics</h2>
<p class="muted">SSD endurance % comes from controller SMART when available. Diagnostic signal is a separate warning heuristic — neither means chance of survival.</p>
<div class="facts"><div class="fact"><span>NVMe endurance used</span>${SSD_USED:-N/A}%</div>
<div class="fact"><span>Estimated endurance remaining</span>${SSD_LIFE:-N/A}%</div>
<div class="fact"><span>Total data written</span>${SSD_TBW:-N/A} TB</div>
<div class="fact"><span>Diagnostic signal</span>${SSD_SIGNAL:-N/A}/100</div>
<div class="fact"><span>SMART status</span>${SSD_DEEP_STATUS:-UNKNOWN}</div>
<div class="fact"><span>Evidence confidence</span>${SSD_EVIDENCE:-UNAVAILABLE}</div></div>
<p><a class="btn primary" href="ssd-report.html">Full SMART/SSD diagnostic detail</a></p></div>
<div class="section card"><h2>Battery Deep Diagnostics</h2>
<p class="muted">Battery health and raw controller estimates are measured separately. The diagnostic signal is heuristic and is NOT a remaining-lifetime or authenticity percentage.</p>
<div class="facts"><div class="fact"><span>Capacity Health</span>${BAT_NOMINAL:-N/A}%</div>
<div class="fact"><span>Raw controller Health</span>${BAT_RAW:-N/A}%</div>
<div class="fact"><span>Diagnostic signal</span>${BAT_SIGNAL:-N/A}/100</div>
<div class="fact"><span>Evidence confidence</span>${BAT_CONFIDENCE:-UNAVAILABLE}</div></div>
<p><a class="btn primary" href="battery-report.html">Full battery analysis and cell diagnostics</a></p></div>
<div class="section card"><h2>Bằng chứng và dữ liệu gốc</h2><div class="raw"><a href="raw/hardware.txt">Hardware</a><a href="raw/battery-system.txt">Battery</a><a href="raw/battery-raw.txt">Battery raw</a><a href="battery-report.html">Battery Deep</a><a href="battery-report.json">Battery Deep JSON</a><a href="ssd-io-probe.json">SSD I/O Probe (if active)</a><a href="raw/battery-postload.txt">Battery post-load</a><a href="raw/display.txt">Display</a><a href="raw/storage.txt">Storage</a><a href="system-information.html">System Information chi tiết</a><a href="system-information.json">System Information JSON</a><a href="compare-macs.html">So sánh MacBook</a><a href="battery-discharge.html">Quan sát pin</a><a href="raw/metal-gpu.json">Metal GPU (nếu đã test)</a><a href="ssd-report.html">SSD Deep Health</a><a href="apple-coverage.html">Apple Coverage / Provenance</a><a href="apple-coverage.json">Apple Coverage JSON</a><a href="ssd-report.json">SSD Deep JSON (if available)</a><a href="ssd-results.tsv">SSD Deep TSV (if available)</a><a href="raw/cpu-thermal.txt">CPU/Thermal</a><a href="raw/memory-active.txt">Memory</a><a href="raw/mdm.txt">MDM</a><a href="raw/repair-history.txt">Repair history</a><a href="raw/recent-diagnostics.txt">Panic history</a><a href="raw/power-history.txt">Power history</a><a href="results.tsv">All result rows</a><a href="summary.json">Summary JSON</a></div></div>
<div class="footer">MacBook Verify runs locally. Reports contain hardware identifiers. Redact serials before posting publicly.</div></div>
<div class="overlay" id="overlay"><div class="overlayControls"><button class="btn" data-next="#fff">White</button><button class="btn" data-next="#000">Black</button><button class="btn" data-next="#808080">Gray</button><button class="btn" data-next="#f00">Red</button><button class="btn" data-next="#0f0">Green</button><button class="btn" data-next="#00f">Blue</button><button class="btn primary" id="closeOverlay">Exit</button></div></div>
<script>
const EXPECTED_SERIAL="$_serial_js"; const STORE_KEY="$(json_escape "$_report_key")";
const state=JSON.parse(localStorage.getItem(STORE_KEY)||'{}');
function save(){localStorage.setItem(STORE_KEY,JSON.stringify(state));updateManualSummary()}
function choices(el){const box=el.querySelector('.choices');if(!box)return;['PASS','WARN','FAIL','SKIP'].forEach(function(s){const b=document.createElement('button');b.className='btn '+(s==='PASS'?'good':s==='FAIL'?'bad':s==='WARN'?'warn':'skip');b.textContent=s;b.onclick=function(){state[el.dataset.id]=s;el.dataset.result=s;save()};box.appendChild(b)});if(state[el.dataset.id])el.dataset.result=state[el.dataset.id]}
document.querySelectorAll('.manualItem').forEach(choices);
function updateManualSummary(){let c={PASS:0,WARN:0,FAIL:0,SKIP:0};Object.values(state).forEach(function(v){if(c[v]!==undefined)c[v]++});document.getElementById('manualSummary').textContent='Interactive: '+c.PASS+' pass · '+c.WARN+' warn · '+c.FAIL+' fail · '+c.SKIP+' skip'}
updateManualSummary();
document.querySelectorAll('#filters button').forEach(function(b){b.onclick=function(){document.querySelectorAll('#filters button').forEach(function(x){x.classList.remove('active')});b.classList.add('active');const f=b.dataset.filter;document.querySelectorAll('#results tbody tr').forEach(function(r){r.style.display=(f==='ALL'||r.dataset.status===f||r.dataset.area===f)?'':'none'})}});
const serialInput=document.getElementById('bottomSerial');serialInput.addEventListener('input',function(){const v=serialInput.value.trim().toUpperCase();const out=document.getElementById('serialResult');if(!v){out.textContent='Expected: '+EXPECTED_SERIAL;return}if(v===EXPECTED_SERIAL.toUpperCase()){out.textContent='✅ MATCH — bottom serial equals system serial';out.className='p'}else{out.textContent='❌ MISMATCH — expected '+EXPECTED_SERIAL;out.className='f'}});
const overlay=document.getElementById('overlay');function openScreen(bg){overlay.style.display='flex';overlay.style.background=bg;if(document.documentElement.requestFullscreen)document.documentElement.requestFullscreen().catch(function(){})}document.querySelectorAll('.screenColor').forEach(function(b){b.onclick=function(){openScreen(b.dataset.color)}});document.getElementById('gradientBtn').onclick=function(){overlay.style.display='flex';overlay.style.background='linear-gradient(90deg,#000,#fff,#000),linear-gradient(#f00,#0f0,#00f)';if(document.documentElement.requestFullscreen)document.documentElement.requestFullscreen().catch(function(){})};document.querySelectorAll('[data-next]').forEach(function(b){b.onclick=function(){overlay.style.background=b.dataset.next}});document.getElementById('closeOverlay').onclick=function(){overlay.style.display='none';if(document.exitFullscreen)document.exitFullscreen()};
const keyDefs=['Escape','Digit1','Digit2','Digit3','Digit4','Digit5','Digit6','Digit7','Digit8','Digit9','Digit0','Backspace','Tab','KeyQ','KeyW','KeyE','KeyR','KeyT','KeyY','KeyU','KeyI','KeyO','KeyP','BracketLeft','BracketRight','CapsLock','KeyA','KeyS','KeyD','KeyF','KeyG','KeyH','KeyJ','KeyK','KeyL','Semicolon','Quote','Enter','ShiftLeft','KeyZ','KeyX','KeyC','KeyV','KeyB','KeyN','KeyM','Comma','Period','Slash','ShiftRight','ControlLeft','AltLeft','MetaLeft','Space','MetaRight','AltRight','ArrowLeft','ArrowUp','ArrowDown','ArrowRight'];const kbd=document.getElementById('keyboard');keyDefs.forEach(function(k){const d=document.createElement('div');d.className='key';d.dataset.code=k;d.textContent=k.replace('Key','').replace('Digit','');kbd.appendChild(d)});window.addEventListener('keydown',function(e){const el=kbd.querySelector('[data-code="'+e.code+'"]');if(el)el.classList.add('hit')});
let mv=0,cl=0,rc=0,wh=0;const pad=document.getElementById('trackpad');pad.addEventListener('pointermove',function(){mv++;document.getElementById('moveCount').textContent=mv});pad.addEventListener('click',function(){cl++;document.getElementById('clickCount').textContent=cl});pad.addEventListener('contextmenu',function(e){e.preventDefault();rc++;document.getElementById('rightCount').textContent=rc});pad.addEventListener('wheel',function(){wh++;document.getElementById('wheelCount').textContent=wh});
function tone(pan){const A=window.AudioContext||window.webkitAudioContext;const ctx=new A();const osc=ctx.createOscillator();const gain=ctx.createGain();gain.gain.value=.12;osc.frequency.value=660;if(ctx.createStereoPanner){const p=ctx.createStereoPanner();p.pan.value=pan;osc.connect(gain).connect(p).connect(ctx.destination)}else{osc.connect(gain).connect(ctx.destination)}osc.start();osc.stop(ctx.currentTime+1);osc.onended=function(){ctx.close()}}
let stream=null,aCtx=null,raf=null;document.getElementById('startMedia').onclick=async function(){try{stream=await navigator.mediaDevices.getUserMedia({video:true,audio:true});document.getElementById('preview').srcObject=stream;const A=window.AudioContext||window.webkitAudioContext;aCtx=new A();const src=aCtx.createMediaStreamSource(stream);const an=aCtx.createAnalyser();an.fftSize=256;src.connect(an);const buf=new Uint8Array(an.frequencyBinCount);const draw=function(){an.getByteFrequencyData(buf);let m=0;buf.forEach(function(v){m=Math.max(m,v)});document.getElementById('micLevel').style.width=Math.min(100,m/2.55)+'%';raf=requestAnimationFrame(draw)};draw()}catch(e){alert('Camera/mic test unavailable: '+e.message+'\nYou can still verify using system apps and mark the result manually.')}};document.getElementById('stopMedia').onclick=function(){if(raf)cancelAnimationFrame(raf);if(stream)stream.getTracks().forEach(function(t){t.stop()});if(aCtx)aCtx.close();document.getElementById('preview').srcObject=null};
const portNames=['Thunderbolt / USB-C left #1','Thunderbolt / USB-C left #2','Thunderbolt / USB-C right','MagSafe charging','HDMI output','SD card reader','3.5 mm headphone jack'];const ports=document.getElementById('ports');portNames.forEach(function(name,i){const d=document.createElement('div');d.className='manualItem';d.dataset.id='port-'+i;d.innerHTML='<strong>'+name+'</strong><p class="muted">Connect a known-good device/cable and verify detection/function. SKIP if this port is absent on the model.</p><div class="choices"></div>';ports.appendChild(d);choices(d)});
document.getElementById('exportManual').onclick=function(){const data={tool:'MacBook Verify',reportKey:STORE_KEY,systemSerial:EXPECTED_SERIAL,exportedAt:new Date().toISOString(),results:state,keyboardHit:Array.from(document.querySelectorAll('.key.hit')).map(function(x){return x.dataset.code}),trackpad:{move:mv,click:cl,rightClick:rc,scroll:wh}};const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='interactive-results.json';a.click();setTimeout(function(){URL.revokeObjectURL(a.href)},1000)};
</script></body></html>
EOF_HTML
}
