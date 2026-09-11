#!/bin/bash
# MacBook Verify - one-click offline Mac hardware verifier.
# Compatible with the system Bash shipped with macOS.

set -u

VERSION="0.1.0"
OPEN_REPORT=1
OUTPUT_BASE="$HOME/Desktop"
APP_MODE=0

usage() {
  cat <<USAGE
MacBook Verify v$VERSION

Usage:
  verify.sh [--no-open] [--output DIR] [--app] [--help]

Options:
  --no-open      Do not open report.html automatically.
  --output DIR   Write the timestamped report folder inside DIR.
  --app          Internal flag used by the installed .app launcher.
  --help         Show this help.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --no-open)
      OPEN_REPORT=0
      shift
      ;;
    --output)
      if [ "$#" -lt 2 ]; then
        echo "ERROR: --output requires a directory." >&2
        exit 2
      fi
      OUTPUT_BASE="$2"
      shift 2
      ;;
    --app)
      APP_MODE=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ "$(uname -s 2>/dev/null || true)" != "Darwin" ]; then
  echo "MacBook Verify only runs on macOS." >&2
  exit 1
fi

# Force predictable English labels from Apple CLI tools so parsing is stable.
export LANG=C
export LC_ALL=C

TIMESTAMP="$(date '+%Y%m%d-%H%M%S')"
mkdir -p "$OUTPUT_BASE" 2>/dev/null || {
  echo "ERROR: Cannot create output directory: $OUTPUT_BASE" >&2
  exit 1
}
OUT_DIR="$OUTPUT_BASE/MacBook-Verify-$TIMESTAMP"
RAW_DIR="$OUT_DIR/raw"
mkdir -p "$RAW_DIR" || exit 1

CHECK_ROWS="$OUT_DIR/.checks.html"
: > "$CHECK_ROWS"
PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0
INFO_COUNT=0

say() {
  printf '%s\n' "$*"
}

step() {
  printf '▶ %s\n' "$*"
}

collect() {
  file="$1"
  shift
  "$@" > "$RAW_DIR/$file" 2>&1 || true
}

html_escape() {
  printf '%s' "$1" | /usr/bin/sed \
    -e 's/&/\&amp;/g' \
    -e 's/</\&lt;/g' \
    -e 's/>/\&gt;/g' \
    -e 's/"/\&quot;/g' \
    -e "s/'/\&#39;/g"
}

json_escape() {
  # Summary values are single-line strings, so escaping slash/quote is enough here.
  printf '%s' "$1" | /usr/bin/sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

field() {
  file="$1"
  label="$2"
  /usr/bin/awk -v label="$label" '
    {
      line=$0
      sub(/^[ \t]+/, "", line)
      prefix=label ":"
      if (index(line, prefix) == 1) {
        value=substr(line, length(prefix)+1)
        sub(/^[ \t]+/, "", value)
        print value
        exit
      }
    }
  ' "$file" 2>/dev/null
}

ioreg_number() {
  file="$1"
  key="$2"
  /usr/bin/grep -m 1 "\"$key\" =" "$file" 2>/dev/null \
    | /usr/bin/sed -E 's/.*= ([0-9]+).*/\1/' \
    | /usr/bin/head -n 1
}

ioreg_string() {
  file="$1"
  key="$2"
  /usr/bin/grep -m 1 "\"$key\" = \"" "$file" 2>/dev/null \
    | /usr/bin/sed -E 's/.*= "([^"]*)".*/\1/' \
    | /usr/bin/head -n 1
}

add_check() {
  status="$1"
  title="$2"
  detail="$3"

  case "$status" in
    PASS) PASS_COUNT=$((PASS_COUNT + 1)); css="pass" ;;
    WARN) WARN_COUNT=$((WARN_COUNT + 1)); css="warn" ;;
    FAIL) FAIL_COUNT=$((FAIL_COUNT + 1)); css="fail" ;;
    *)    INFO_COUNT=$((INFO_COUNT + 1)); status="INFO"; css="info" ;;
  esac

  escaped_title="$(html_escape "$title")"
  escaped_detail="$(html_escape "$detail")"
  cat >> "$CHECK_ROWS" <<ROW
<tr><td><span class="badge $css">$status</span></td><td><strong>$escaped_title</strong></td><td>$escaped_detail</td></tr>
ROW
}

step "Collecting hardware identity"
collect hardware.txt /usr/sbin/system_profiler SPHardwareDataType
collect platform-ioreg.txt /usr/sbin/ioreg -rd1 -c IOPlatformExpertDevice
collect sysctl.txt /usr/sbin/sysctl -a

step "Collecting battery data"
collect battery-system.txt /usr/sbin/system_profiler SPPowerDataType
collect battery-raw.txt /usr/sbin/ioreg -rn AppleSmartBattery

step "Collecting display and GPU data"
collect display.txt /usr/sbin/system_profiler SPDisplaysDataType

step "Collecting storage data"
collect storage.txt /usr/sbin/system_profiler SPNVMeDataType SPStorageDataType

step "Collecting memory data"
collect memory.txt /usr/sbin/system_profiler SPMemoryDataType

step "Collecting security state"
{
  echo "== macOS =="
  /usr/bin/sw_vers 2>&1 || true
  echo
  echo "== SIP =="
  /usr/bin/csrutil status 2>&1 || true
  echo
  echo "== FileVault =="
  /usr/bin/fdesetup status 2>&1 || true
} > "$RAW_DIR/security.txt"

step "Checking MDM / Automated Device Enrollment"
/usr/bin/profiles status -type enrollment > "$RAW_DIR/mdm.txt" 2>&1 || true

step "Collecting diagnostics exposed by macOS"
/usr/sbin/system_profiler SPDiagnosticsDataType > "$RAW_DIR/diagnostics.txt" 2>&1 || true

step "Looking for CLI-exposed repair history"
SYSTEM_TYPES="$(/usr/sbin/system_profiler -listDataTypes 2>/dev/null || true)"
REPAIR_TYPES="$(printf '%s\n' "$SYSTEM_TYPES" | /usr/bin/grep -Ei 'SP.*(Repair|Parts).*DataType' || true)"
if [ -n "$REPAIR_TYPES" ]; then
  : > "$RAW_DIR/repair-history.txt"
  for repair_type in $REPAIR_TYPES; do
    echo "== $repair_type ==" >> "$RAW_DIR/repair-history.txt"
    /usr/sbin/system_profiler "$repair_type" >> "$RAW_DIR/repair-history.txt" 2>&1 || true
    echo >> "$RAW_DIR/repair-history.txt"
  done
else
  cat > "$RAW_DIR/repair-history.txt" <<'NO_REPAIR_CLI'
No Repair/Parts system_profiler data type was exposed by this macOS build.
This does NOT mean the Mac has never been repaired.
Check: System Settings > General > About > Parts & Service (if that section is available).
NO_REPAIR_CLI
fi

# -----------------------------
# Parse core values
# -----------------------------
HARDWARE="$RAW_DIR/hardware.txt"
BATTERY="$RAW_DIR/battery-system.txt"
BATTERY_RAW="$RAW_DIR/battery-raw.txt"
DISPLAY="$RAW_DIR/display.txt"
STORAGE="$RAW_DIR/storage.txt"
DIAGNOSTICS="$RAW_DIR/diagnostics.txt"

MODEL_NAME="$(field "$HARDWARE" "Model Name")"
MODEL_IDENTIFIER="$(field "$HARDWARE" "Model Identifier")"
MODEL_NUMBER="$(field "$HARDWARE" "Model Number")"
CHIP="$(field "$HARDWARE" "Chip")"
PROCESSOR_NAME="$(field "$HARDWARE" "Processor Name")"
CPU_CORES="$(field "$HARDWARE" "Total Number of Cores")"
MEMORY="$(field "$HARDWARE" "Memory")"
SYSTEM_SERIAL="$(field "$HARDWARE" "Serial Number (system)")"
ACTIVATION_LOCK="$(field "$HARDWARE" "Activation Lock Status")"
PLATFORM_SERIAL="$(ioreg_string "$RAW_DIR/platform-ioreg.txt" "IOPlatformSerialNumber")"
SYSCTL_MODEL="$(/usr/sbin/sysctl -n hw.model 2>/dev/null || true)"
OS_VERSION="$(/usr/bin/sw_vers -productVersion 2>/dev/null || true)"
OS_BUILD="$(/usr/bin/sw_vers -buildVersion 2>/dev/null || true)"

if [ -z "$CHIP" ]; then
  CHIP="$PROCESSOR_NAME"
fi

BATTERY_SERIAL="$(field "$BATTERY" "Serial Number")"
BATTERY_CYCLES="$(field "$BATTERY" "Cycle Count")"
BATTERY_CONDITION="$(field "$BATTERY" "Condition")"
BATTERY_MAX_CAP="$(field "$BATTERY" "Maximum Capacity")"
BATTERY_MAX_NUM="$(printf '%s' "$BATTERY_MAX_CAP" | /usr/bin/tr -cd '0-9')"
BATTERY_DESIGN_CAP="$(ioreg_number "$BATTERY_RAW" "DesignCapacity")"
BATTERY_RAW_MAX="$(ioreg_number "$BATTERY_RAW" "AppleRawMaxCapacity")"
BATTERY_PERM_FAIL="$(ioreg_number "$BATTERY_RAW" "PermanentFailureStatus")"
BATTERY_DISCONNECTS="$(ioreg_number "$BATTERY_RAW" "BatteryCellDisconnectCount")"
BATTERY_DESIGN_CYCLES="$(ioreg_number "$BATTERY_RAW" "DesignCycleCount9C")"
BATTERY_FIRST_USE="$(ioreg_number "$BATTERY_RAW" "DateOfFirstUse")"

DISPLAY_TYPE="$(field "$DISPLAY" "Display Type")"
DISPLAY_RESOLUTION="$(field "$DISPLAY" "Resolution")"
DISPLAY_ONLINE="$(field "$DISPLAY" "Online")"
DISPLAY_CONNECTION="$(field "$DISPLAY" "Connection Type")"
GPU_CORES="$(field "$DISPLAY" "Total Number of Cores")"

SSD_MODEL="$(field "$STORAGE" "Model")"
SSD_CAPACITY="$(field "$STORAGE" "Capacity")"
SSD_TRIM="$(field "$STORAGE" "TRIM Support")"
SSD_SMART="$(field "$STORAGE" "S.M.A.R.T. status")"
if [ -z "$SSD_SMART" ]; then
  SSD_SMART="$(field "$STORAGE" "S.M.A.R.T. Status")"
fi
SSD_DETACHABLE="$(field "$STORAGE" "Detachable Drive")"
SSD_REMOVABLE="$(field "$STORAGE" "Removable Media")"

# -----------------------------
# Automatic checks
# -----------------------------
if [ -n "$SYSTEM_SERIAL" ] && [ -n "$PLATFORM_SERIAL" ]; then
  if [ "$SYSTEM_SERIAL" = "$PLATFORM_SERIAL" ]; then
    add_check PASS "System serial consistency" "system_profiler và IOKit cùng báo serial $SYSTEM_SERIAL."
  else
    add_check FAIL "System serial mismatch" "system_profiler=$SYSTEM_SERIAL nhưng IOKit=$PLATFORM_SERIAL. Cần kiểm tra logic board / firmware / cấu hình máy."
  fi
else
  add_check INFO "System serial consistency" "Không lấy đủ serial từ cả system_profiler và IOKit để đối chiếu."
fi

if [ -n "$MODEL_IDENTIFIER" ] && [ -n "$SYSCTL_MODEL" ]; then
  if [ "$MODEL_IDENTIFIER" = "$SYSCTL_MODEL" ]; then
    add_check PASS "Model consistency" "$MODEL_IDENTIFIER khớp giữa system_profiler và sysctl."
  else
    add_check FAIL "Model mismatch" "system_profiler=$MODEL_IDENTIFIER nhưng sysctl=$SYSCTL_MODEL."
  fi
else
  add_check INFO "Model consistency" "Không lấy đủ dữ liệu để đối chiếu model identifier."
fi

if [ -n "$BATTERY_CONDITION" ]; then
  case "$BATTERY_CONDITION" in
    Normal|normal)
      add_check PASS "Battery condition" "Battery condition: $BATTERY_CONDITION."
      ;;
    *)
      add_check WARN "Battery condition" "Battery condition: $BATTERY_CONDITION. Nên kiểm tra pin kỹ hơn hoặc cân nhắc service."
      ;;
  esac
else
  add_check INFO "Battery detected" "Không có Battery Condition. Máy desktop/runner hoặc pin không được system_profiler cung cấp."
fi

if [ -n "$BATTERY_MAX_NUM" ]; then
  if [ "$BATTERY_MAX_NUM" -ge 80 ] 2>/dev/null; then
    add_check PASS "Battery maximum capacity" "$BATTERY_MAX_CAP — mức sức khỏe pin hiện tại tốt theo ngưỡng kiểm tra của tool."
  elif [ "$BATTERY_MAX_NUM" -ge 70 ] 2>/dev/null; then
    add_check WARN "Battery maximum capacity" "$BATTERY_MAX_CAP — pin đã hao đáng kể."
  else
    add_check WARN "Battery maximum capacity" "$BATTERY_MAX_CAP — pin hao nhiều, nên dự trù thay pin."
  fi
else
  add_check INFO "Battery maximum capacity" "Không lấy được Maximum Capacity."
fi

if [ -n "$BATTERY_CYCLES" ]; then
  if [ -n "$BATTERY_DESIGN_CYCLES" ] && [ "$BATTERY_DESIGN_CYCLES" -gt 0 ] 2>/dev/null; then
    warn_at=$((BATTERY_DESIGN_CYCLES * 80 / 100))
    if [ "$BATTERY_CYCLES" -ge "$BATTERY_DESIGN_CYCLES" ] 2>/dev/null; then
      add_check WARN "Battery cycle count" "$BATTERY_CYCLES cycles; controller design-cycle reference is $BATTERY_DESIGN_CYCLES."
    elif [ "$BATTERY_CYCLES" -ge "$warn_at" ] 2>/dev/null; then
      add_check WARN "Battery cycle count" "$BATTERY_CYCLES / $BATTERY_DESIGN_CYCLES cycles — đã ở vùng cycle cao."
    else
      add_check PASS "Battery cycle count" "$BATTERY_CYCLES / $BATTERY_DESIGN_CYCLES cycles."
    fi
  else
    add_check INFO "Battery cycle count" "$BATTERY_CYCLES cycles. Không có design-cycle reference từ controller để đánh giá tự động."
  fi
fi

if [ -n "$BATTERY_PERM_FAIL" ]; then
  if [ "$BATTERY_PERM_FAIL" = "0" ]; then
    add_check PASS "Battery permanent-failure flag" "PermanentFailureStatus=0."
  else
    add_check FAIL "Battery permanent-failure flag" "PermanentFailureStatus=$BATTERY_PERM_FAIL. Pin/controller đang báo permanent failure."
  fi
fi

if [ -n "$BATTERY_DISCONNECTS" ]; then
  if [ "$BATTERY_DISCONNECTS" = "0" ]; then
    add_check PASS "Battery disconnect counter" "BatteryCellDisconnectCount=0."
  else
    add_check WARN "Battery disconnect counter" "BatteryCellDisconnectCount=$BATTERY_DISCONNECTS. Có dấu vết controller ghi nhận ngắt kết nối pin; đây không phải bằng chứng chắc chắn rằng pin đã bị thay."
  fi
fi

if [ -n "$DISPLAY_TYPE" ]; then
  if [ "$DISPLAY_ONLINE" = "Yes" ] && { [ "$DISPLAY_CONNECTION" = "Internal" ] || [ -z "$DISPLAY_CONNECTION" ]; }; then
    add_check PASS "Built-in display" "$DISPLAY_TYPE; $DISPLAY_RESOLUTION; connection=${DISPLAY_CONNECTION:-unknown}; online=$DISPLAY_ONLINE."
  else
    add_check WARN "Built-in display" "$DISPLAY_TYPE; $DISPLAY_RESOLUTION; connection=${DISPLAY_CONNECTION:-unknown}; online=${DISPLAY_ONLINE:-unknown}."
  fi
else
  add_check WARN "Built-in display" "Không nhận diện được Display Type từ system_profiler."
fi

if [ -n "$SSD_SMART" ]; then
  case "$SSD_SMART" in
    Verified|verified)
      add_check PASS "SSD SMART" "$SSD_MODEL — SMART: $SSD_SMART."
      ;;
    *)
      add_check FAIL "SSD SMART" "$SSD_MODEL — SMART: $SSD_SMART."
      ;;
  esac
else
  add_check INFO "SSD SMART" "Không có SMART status để đánh giá. SSD: ${SSD_MODEL:-unknown}."
fi

if [ -n "$SSD_TRIM" ]; then
  if [ "$SSD_TRIM" = "Yes" ]; then
    add_check PASS "SSD TRIM" "TRIM Support: Yes."
  else
    add_check WARN "SSD TRIM" "TRIM Support: $SSD_TRIM."
  fi
fi

if [ -n "$SSD_DETACHABLE" ]; then
  if [ "$SSD_DETACHABLE" = "No" ]; then
    add_check PASS "Internal SSD attachment" "Detachable Drive: No; Removable Media: ${SSD_REMOVABLE:-unknown}."
  else
    add_check WARN "Internal SSD attachment" "Detachable Drive: $SSD_DETACHABLE; Removable Media: ${SSD_REMOVABLE:-unknown}."
  fi
fi

if printf '%s' "$CHIP" | /usr/bin/grep -q '^Apple M'; then
  if [ -n "$SSD_MODEL" ] && printf '%s' "$SSD_MODEL" | /usr/bin/grep -q '^APPLE SSD'; then
    add_check PASS "Apple Silicon internal storage identity" "$SSD_MODEL được nhận là Apple SSD."
  elif [ -n "$SSD_MODEL" ]; then
    add_check WARN "Apple Silicon internal storage identity" "SSD model=$SSD_MODEL. Với Apple Silicon, cần kiểm tra thêm nếu internal storage không được nhận dạng như Apple SSD."
  fi
fi

if /usr/bin/grep -qi 'System Integrity Protection status: enabled' "$RAW_DIR/security.txt"; then
  add_check PASS "System Integrity Protection" "SIP enabled."
elif /usr/bin/grep -qi 'System Integrity Protection status: disabled' "$RAW_DIR/security.txt"; then
  add_check WARN "System Integrity Protection" "SIP disabled. Điều này không chứng minh phần cứng đã sửa, nhưng là trạng thái bảo mật cần lưu ý."
else
  add_check INFO "System Integrity Protection" "Không xác định được SIP status."
fi

if /usr/bin/grep -qiE 'MDM enrollment:[[:space:]]*Yes|Enrolled via DEP:[[:space:]]*Yes|Automated Device Enrollment.*Yes' "$RAW_DIR/mdm.txt"; then
  add_check WARN "MDM / DEP enrollment" "Máy có dấu hiệu đang được MDM/Automated Device Enrollment quản lý. Với máy cũ, cần xác nhận tổ chức đã release thiết bị trước khi mua."
elif /usr/bin/grep -qiE 'MDM enrollment:[[:space:]]*No|Enrolled via DEP:[[:space:]]*No' "$RAW_DIR/mdm.txt"; then
  add_check PASS "MDM / DEP enrollment" "Không thấy MDM/DEP enrollment trong status hiện tại."
else
  add_check INFO "MDM / DEP enrollment" "Không xác định được enrollment status; xem raw/mdm.txt."
fi

if [ -n "$ACTIVATION_LOCK" ]; then
  case "$ACTIVATION_LOCK" in
    Disabled|disabled)
      add_check PASS "Activation Lock" "Activation Lock: $ACTIVATION_LOCK."
      ;;
    Enabled|enabled)
      add_check WARN "Activation Lock" "Activation Lock: $ACTIVATION_LOCK. Nếu đây là máy đang mua/bán, chủ cũ phải tắt Find My/Activation Lock trước khi bàn giao."
      ;;
    *)
      add_check INFO "Activation Lock" "Activation Lock: $ACTIVATION_LOCK."
      ;;
  esac
fi

if /usr/bin/grep -qi 'FileVault is On' "$RAW_DIR/security.txt"; then
  add_check PASS "FileVault" "FileVault is On."
elif /usr/bin/grep -qi 'FileVault is Off' "$RAW_DIR/security.txt"; then
  add_check INFO "FileVault" "FileVault is Off. Đây là thông tin bảo mật, không phải dấu hiệu sửa phần cứng."
fi

DIAG_RESULT="$(field "$DIAGNOSTICS" "Result")"
if [ -n "$DIAG_RESULT" ]; then
  case "$DIAG_RESULT" in
    Passed|passed)
      add_check PASS "Power-On Self Test" "Diagnostics Result: $DIAG_RESULT."
      ;;
    *)
      add_check WARN "Power-On Self Test" "Diagnostics Result: $DIAG_RESULT."
      ;;
  esac
else
  add_check INFO "Apple Diagnostics" "Normal macOS session không thể tự động chạy toàn bộ Apple Diagnostics. Xem hướng dẫn manual trong report."
fi

if [ -n "$REPAIR_TYPES" ]; then
  add_check INFO "Parts / repair CLI data" "macOS exposes: $(printf '%s' "$REPAIR_TYPES" | tr '\n' ' '). Xem raw/repair-history.txt và đối chiếu Parts & Service trong Settings."
else
  add_check INFO "Parts & Service history" "Build macOS này không expose Repair/Parts data type qua system_profiler. Việc không có dữ liệu CLI KHÔNG chứng minh máy chưa sửa."
fi

if [ "$FAIL_COUNT" -gt 0 ]; then
  OVERALL_CLASS="fail"
  OVERALL_TITLE="Phát hiện vấn đề cần kiểm tra"
  OVERALL_TEXT="Có $FAIL_COUNT mục FAIL. Không nên kết luận máy ổn trước khi xác minh các mục này."
elif [ "$WARN_COUNT" -gt 0 ]; then
  OVERALL_CLASS="warn"
  OVERALL_TITLE="Không thấy mismatch nghiêm trọng, nhưng có cảnh báo"
  OVERALL_TEXT="Có $WARN_COUNT mục WARN. Hãy đọc từng cảnh báo và hoàn tất kiểm tra vật lý trước khi mua/bán."
else
  OVERALL_CLASS="pass"
  OVERALL_TITLE="Không phát hiện bất thường rõ ràng bằng phần mềm"
  OVERALL_TEXT="Các check tự động hiện tại không thấy lỗi/mismatch. Điều này không đồng nghĩa máy chắc chắn 100% chưa từng mở hoặc sửa."
fi

# -----------------------------
# Write machine-readable summary
# -----------------------------
cat > "$OUT_DIR/summary.json" <<JSON
{
  "tool": "MacBook Verify",
  "version": "$(json_escape "$VERSION")",
  "generated_at": "$(json_escape "$(date '+%Y-%m-%d %H:%M:%S %z')")",
  "model_name": "$(json_escape "$MODEL_NAME")",
  "model_identifier": "$(json_escape "$MODEL_IDENTIFIER")",
  "model_number": "$(json_escape "$MODEL_NUMBER")",
  "chip": "$(json_escape "$CHIP")",
  "cpu_cores": "$(json_escape "$CPU_CORES")",
  "gpu_cores": "$(json_escape "$GPU_CORES")",
  "memory": "$(json_escape "$MEMORY")",
  "system_serial": "$(json_escape "$SYSTEM_SERIAL")",
  "platform_serial": "$(json_escape "$PLATFORM_SERIAL")",
  "os_version": "$(json_escape "$OS_VERSION")",
  "os_build": "$(json_escape "$OS_BUILD")",
  "battery": {
    "serial": "$(json_escape "$BATTERY_SERIAL")",
    "cycle_count": "$(json_escape "$BATTERY_CYCLES")",
    "condition": "$(json_escape "$BATTERY_CONDITION")",
    "maximum_capacity": "$(json_escape "$BATTERY_MAX_CAP")",
    "design_capacity_raw": "$(json_escape "$BATTERY_DESIGN_CAP")",
    "apple_raw_max_capacity": "$(json_escape "$BATTERY_RAW_MAX")",
    "permanent_failure_status": "$(json_escape "$BATTERY_PERM_FAIL")",
    "disconnect_count": "$(json_escape "$BATTERY_DISCONNECTS")",
    "design_cycle_count": "$(json_escape "$BATTERY_DESIGN_CYCLES")",
    "date_of_first_use_raw": "$(json_escape "$BATTERY_FIRST_USE")"
  },
  "display": {
    "type": "$(json_escape "$DISPLAY_TYPE")",
    "resolution": "$(json_escape "$DISPLAY_RESOLUTION")",
    "connection": "$(json_escape "$DISPLAY_CONNECTION")",
    "online": "$(json_escape "$DISPLAY_ONLINE")"
  },
  "storage": {
    "model": "$(json_escape "$SSD_MODEL")",
    "capacity": "$(json_escape "$SSD_CAPACITY")",
    "trim": "$(json_escape "$SSD_TRIM")",
    "smart": "$(json_escape "$SSD_SMART")",
    "detachable": "$(json_escape "$SSD_DETACHABLE")",
    "removable": "$(json_escape "$SSD_REMOVABLE")"
  },
  "checks": {
    "pass": $PASS_COUNT,
    "warn": $WARN_COUNT,
    "fail": $FAIL_COUNT,
    "info": $INFO_COUNT
  },
  "conclusion": "$(json_escape "$OVERALL_TITLE")"
}
JSON

cat > "$OUT_DIR/summary.txt" <<SUMMARY
MacBook Verify v$VERSION
Generated: $(date '+%Y-%m-%d %H:%M:%S %z')

Model:              ${MODEL_NAME:-Unknown}
Model Identifier:   ${MODEL_IDENTIFIER:-Unknown}
Model Number:       ${MODEL_NUMBER:-Unknown}
Chip/Processor:     ${CHIP:-Unknown}
CPU Cores:          ${CPU_CORES:-Unknown}
GPU Cores:          ${GPU_CORES:-Unknown}
Memory:             ${MEMORY:-Unknown}
System Serial:      ${SYSTEM_SERIAL:-Unknown}
Platform Serial:    ${PLATFORM_SERIAL:-Unknown}
macOS:              ${OS_VERSION:-Unknown} (${OS_BUILD:-Unknown})

Battery Serial:     ${BATTERY_SERIAL:-Unknown}
Battery Cycles:     ${BATTERY_CYCLES:-Unknown}
Battery Condition:  ${BATTERY_CONDITION:-Unknown}
Battery Max Cap:    ${BATTERY_MAX_CAP:-Unknown}
Battery Disconnect: ${BATTERY_DISCONNECTS:-Unknown}
Permanent Failure:  ${BATTERY_PERM_FAIL:-Unknown}

Display:            ${DISPLAY_TYPE:-Unknown}
Resolution:         ${DISPLAY_RESOLUTION:-Unknown}
Display Connection: ${DISPLAY_CONNECTION:-Unknown}

SSD:                ${SSD_MODEL:-Unknown}
SSD Capacity:       ${SSD_CAPACITY:-Unknown}
SSD SMART:          ${SSD_SMART:-Unknown}
SSD TRIM:           ${SSD_TRIM:-Unknown}

PASS=$PASS_COUNT WARN=$WARN_COUNT FAIL=$FAIL_COUNT INFO=$INFO_COUNT
Conclusion: $OVERALL_TITLE

IMPORTANT: Software checks cannot prove that a Mac has never been opened or repaired.
SUMMARY

# -----------------------------
# HTML report
# -----------------------------
E_MODEL_NAME="$(html_escape "${MODEL_NAME:-Unknown}")"
E_MODEL_IDENTIFIER="$(html_escape "${MODEL_IDENTIFIER:-Unknown}")"
E_MODEL_NUMBER="$(html_escape "${MODEL_NUMBER:-Unknown}")"
E_CHIP="$(html_escape "${CHIP:-Unknown}")"
E_CPU="$(html_escape "${CPU_CORES:-Unknown}")"
E_GPU="$(html_escape "${GPU_CORES:-Unknown}")"
E_MEMORY="$(html_escape "${MEMORY:-Unknown}")"
E_SERIAL="$(html_escape "${SYSTEM_SERIAL:-Unknown}")"
E_OS="$(html_escape "${OS_VERSION:-Unknown} (${OS_BUILD:-Unknown})")"
E_BATTERY_SERIAL="$(html_escape "${BATTERY_SERIAL:-Unknown}")"
E_BATTERY_CYCLES="$(html_escape "${BATTERY_CYCLES:-Unknown}")"
E_BATTERY_CONDITION="$(html_escape "${BATTERY_CONDITION:-Unknown}")"
E_BATTERY_CAP="$(html_escape "${BATTERY_MAX_CAP:-Unknown}")"
E_DISPLAY="$(html_escape "${DISPLAY_TYPE:-Unknown}")"
E_RESOLUTION="$(html_escape "${DISPLAY_RESOLUTION:-Unknown}")"
E_SSD="$(html_escape "${SSD_MODEL:-Unknown}")"
E_SSD_CAP="$(html_escape "${SSD_CAPACITY:-Unknown}")"
E_OVERALL_TITLE="$(html_escape "$OVERALL_TITLE")"
E_OVERALL_TEXT="$(html_escape "$OVERALL_TEXT")"

cat > "$OUT_DIR/report.html" <<HTML_HEAD
<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MacBook Verify Report</title>
<style>
:root{color-scheme:light dark;--bg:#f5f7fb;--card:#fff;--text:#182033;--muted:#667085;--line:#e5e7eb;--pass:#087443;--passbg:#e8f7ef;--warn:#9a6700;--warnbg:#fff4d6;--fail:#b42318;--failbg:#feeceb;--info:#175cd3;--infobg:#eaf2ff}
@media(prefers-color-scheme:dark){:root{--bg:#0e1117;--card:#161b22;--text:#eef2f7;--muted:#9ba7b4;--line:#30363d;--pass:#63d297;--passbg:#123524;--warn:#f0c36a;--warnbg:#3b2f12;--fail:#ff8a84;--failbg:#421b1b;--info:#82b3ff;--infobg:#132b50}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.wrap{max-width:1100px;margin:0 auto;padding:28px 18px 60px}.hero{padding:26px;border:1px solid var(--line);background:var(--card);border-radius:20px;box-shadow:0 8px 30px rgba(0,0,0,.05)}h1{margin:0 0 4px;font-size:30px}.sub{color:var(--muted);margin:0}.verdict{margin-top:20px;padding:17px 18px;border-radius:14px}.verdict.pass{background:var(--passbg);color:var(--pass)}.verdict.warn{background:var(--warnbg);color:var(--warn)}.verdict.fail{background:var(--failbg);color:var(--fail)}.verdict h2{margin:0 0 4px;font-size:20px}.stats{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px}.stat{border:1px solid var(--line);padding:7px 11px;border-radius:999px;background:var(--card)}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:16px}@media(max-width:760px){.grid{grid-template-columns:1fr}}.card{border:1px solid var(--line);background:var(--card);border-radius:16px;padding:20px}.card h2{margin:0 0 14px;font-size:18px}.kv{display:grid;grid-template-columns:170px 1fr;gap:8px 14px}.kv div:nth-child(odd){color:var(--muted)}@media(max-width:520px){.kv{grid-template-columns:1fr}.kv div:nth-child(odd){margin-top:5px}}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:11px 10px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:600}.badge{display:inline-block;font-size:12px;font-weight:800;letter-spacing:.03em;padding:4px 8px;border-radius:999px}.badge.pass{background:var(--passbg);color:var(--pass)}.badge.warn{background:var(--warnbg);color:var(--warn)}.badge.fail{background:var(--failbg);color:var(--fail)}.badge.info{background:var(--infobg);color:var(--info)}a{color:var(--info)}code{background:var(--bg);padding:2px 5px;border-radius:5px}.manual{margin-top:16px}.manual li{margin:8px 0}.serialbox{display:flex;gap:8px;flex-wrap:wrap}.serialbox input{flex:1;min-width:220px;padding:10px;border:1px solid var(--line);border-radius:9px;background:var(--bg);color:var(--text)}button{padding:10px 13px;border:1px solid var(--line);border-radius:9px;background:var(--card);color:var(--text);cursor:pointer;font-weight:600}.pixel-buttons{display:flex;gap:8px;flex-wrap:wrap}.pixel-buttons button{min-width:72px}.notice{padding:13px 15px;border-radius:12px;background:var(--infobg);color:var(--info)}#pixelOverlay{display:none;position:fixed;inset:0;z-index:99999;cursor:pointer}.footer{margin-top:20px;color:var(--muted);font-size:13px}.rawlinks{display:flex;flex-wrap:wrap;gap:8px}.rawlinks a{display:inline-block;border:1px solid var(--line);padding:6px 9px;border-radius:8px;text-decoration:none}
</style>
</head>
<body>
<div id="pixelOverlay" title="Click to exit"></div>
<div class="wrap">
  <section class="hero">
    <h1>MacBook Verify</h1>
    <p class="sub">Offline one-click verification report · v$VERSION · $(html_escape "$(date '+%Y-%m-%d %H:%M:%S %z')")</p>
    <div class="verdict $OVERALL_CLASS">
      <h2>$E_OVERALL_TITLE</h2>
      <div>$E_OVERALL_TEXT</div>
    </div>
    <div class="stats">
      <span class="stat">✅ PASS <strong>$PASS_COUNT</strong></span>
      <span class="stat">⚠️ WARN <strong>$WARN_COUNT</strong></span>
      <span class="stat">❌ FAIL <strong>$FAIL_COUNT</strong></span>
      <span class="stat">ℹ️ INFO <strong>$INFO_COUNT</strong></span>
    </div>
  </section>

  <div class="grid">
    <section class="card">
      <h2>Máy / Logic board identity</h2>
      <div class="kv">
        <div>Model</div><div>$E_MODEL_NAME</div>
        <div>Identifier</div><div>$E_MODEL_IDENTIFIER</div>
        <div>Model Number</div><div>$E_MODEL_NUMBER</div>
        <div>Chip / CPU</div><div>$E_CHIP</div>
        <div>CPU cores</div><div>$E_CPU</div>
        <div>GPU cores</div><div>$E_GPU</div>
        <div>Memory</div><div>$E_MEMORY</div>
        <div>System Serial</div><div><code>$E_SERIAL</code></div>
        <div>macOS</div><div>$E_OS</div>
      </div>
    </section>

    <section class="card">
      <h2>Pin</h2>
      <div class="kv">
        <div>Battery Serial</div><div><code>$E_BATTERY_SERIAL</code></div>
        <div>Cycle Count</div><div>$E_BATTERY_CYCLES</div>
        <div>Condition</div><div>$E_BATTERY_CONDITION</div>
        <div>Maximum Capacity</div><div>$E_BATTERY_CAP</div>
        <div>Disconnect Count</div><div>$(html_escape "${BATTERY_DISCONNECTS:-Unknown}")</div>
        <div>Permanent Failure</div><div>$(html_escape "${BATTERY_PERM_FAIL:-Unknown}")</div>
        <div>Design Capacity raw</div><div>$(html_escape "${BATTERY_DESIGN_CAP:-Unknown}")</div>
        <div>Apple Raw Max</div><div>$(html_escape "${BATTERY_RAW_MAX:-Unknown}")</div>
      </div>
    </section>

    <section class="card">
      <h2>Màn hình</h2>
      <div class="kv">
        <div>Display</div><div>$E_DISPLAY</div>
        <div>Resolution</div><div>$E_RESOLUTION</div>
        <div>Connection</div><div>$(html_escape "${DISPLAY_CONNECTION:-Unknown}")</div>
        <div>Online</div><div>$(html_escape "${DISPLAY_ONLINE:-Unknown}")</div>
      </div>
    </section>

    <section class="card">
      <h2>SSD / Storage</h2>
      <div class="kv">
        <div>SSD</div><div>$E_SSD</div>
        <div>Capacity</div><div>$E_SSD_CAP</div>
        <div>SMART</div><div>$(html_escape "${SSD_SMART:-Unknown}")</div>
        <div>TRIM</div><div>$(html_escape "${SSD_TRIM:-Unknown}")</div>
        <div>Detachable</div><div>$(html_escape "${SSD_DETACHABLE:-Unknown}")</div>
        <div>Removable</div><div>$(html_escape "${SSD_REMOVABLE:-Unknown}")</div>
      </div>
    </section>
  </div>

  <section class="card" style="margin-top:16px">
    <h2>Kết quả kiểm tra tự động</h2>
    <div style="overflow:auto">
      <table>
        <thead><tr><th>Status</th><th>Check</th><th>Chi tiết</th></tr></thead>
        <tbody>
HTML_HEAD
cat "$CHECK_ROWS" >> "$OUT_DIR/report.html"
cat >> "$OUT_DIR/report.html" <<HTML_TAIL
        </tbody>
      </table>
    </div>
  </section>

  <section class="card manual">
    <h2>Kiểm tra vật lý còn lại — phần mềm không thể chứng minh</h2>
    <div class="notice">Không có tool phần mềm nào có thể đảm bảo 100% “máy zin chưa mở”. Hoàn tất các bước dưới đây trước khi kết luận.</div>
    <ol>
      <li><strong>Serial mặt đáy:</strong> nhập serial khắc trên bottom case để so với serial hệ thống.</li>
      <li><strong>Ốc và viền đáy:</strong> kiểm tra đầu ốc trầy/toét, dấu cạy, khe chassis không đều.</li>
      <li><strong>Màn hình:</strong> chạy các màu fullscreen bên dưới để tìm dead/stuck pixel, ám màu hoặc vùng sáng bất thường.</li>
      <li><strong>Parts & Service:</strong> mở <code>System Settings → General → About</code> và xem mục <code>Parts & Service</code> nếu macOS hiển thị.</li>
      <li><strong>Apple Diagnostics:</strong> Apple Silicon: tắt máy → giữ nút nguồn đến Startup Options → nhấn <code>Command-D</code>. Intel: bật máy và giữ <code>D</code>.</li>
      <li><strong>Chức năng:</strong> test bàn phím, Touch ID, trackpad, camera, mic, loa, MagSafe/USB-C/HDMI/SD, Wi-Fi/Bluetooth và sleep/wake.</li>
    </ol>

    <h3>Đối chiếu serial mặt đáy</h3>
    <div class="serialbox">
      <input id="caseSerial" autocomplete="off" placeholder="Nhập serial khắc dưới đáy máy">
      <button onclick="compareSerial()">So sánh</button>
    </div>
    <p id="serialResult"></p>

    <h3>Dead-pixel / uniformity test</h3>
    <p class="sub">Bấm một màu để phủ toàn màn hình; bấm lại màn hình để thoát.</p>
    <div class="pixel-buttons">
      <button onclick="pixelTest('#ffffff')">White</button>
      <button onclick="pixelTest('#000000')">Black</button>
      <button onclick="pixelTest('#ff0000')">Red</button>
      <button onclick="pixelTest('#00ff00')">Green</button>
      <button onclick="pixelTest('#0000ff')">Blue</button>
      <button onclick="pixelTest('#808080')">Gray</button>
    </div>
  </section>

  <section class="card manual">
    <h2>Raw evidence</h2>
    <div class="rawlinks">
      <a href="summary.txt">summary.txt</a>
      <a href="summary.json">summary.json</a>
      <a href="raw/hardware.txt">hardware</a>
      <a href="raw/platform-ioreg.txt">platform ioreg</a>
      <a href="raw/battery-system.txt">battery</a>
      <a href="raw/battery-raw.txt">battery raw</a>
      <a href="raw/display.txt">display</a>
      <a href="raw/storage.txt">storage</a>
      <a href="raw/memory.txt">memory</a>
      <a href="raw/security.txt">security</a>
      <a href="raw/mdm.txt">MDM</a>
      <a href="raw/diagnostics.txt">diagnostics</a>
      <a href="raw/repair-history.txt">repair history</a>
      <a href="manifest.sha256">SHA-256 manifest</a>
    </div>
  </section>

  <p class="footer">MacBook Verify runs locally. Không upload dữ liệu. Report có thể chứa serial/hardware identifiers — hãy che thông tin trước khi đăng công khai.</p>
</div>
<script>
const systemSerial = "$(json_escape "$SYSTEM_SERIAL")";
function compareSerial(){
  const entered=(document.getElementById('caseSerial').value||'').trim().toUpperCase();
  const out=document.getElementById('serialResult');
  if(!entered){out.textContent='Hãy nhập serial dưới đáy máy.';return;}
  if(!systemSerial){out.textContent='Không có system serial để đối chiếu.';return;}
  if(entered===systemSerial.toUpperCase()){
    out.textContent='✅ Khớp serial hệ thống. Đây là tín hiệu tốt, nhưng vẫn không chứng minh máy chưa từng mở.';
  }else{
    out.textContent='❌ KHÔNG KHỚP. System serial: '+systemSerial+'. Cần điều tra bottom case / logic board / lịch sử sửa chữa.';
  }
}
function pixelTest(color){
  const el=document.getElementById('pixelOverlay');
  el.style.background=color;el.style.display='block';
  if(el.requestFullscreen){el.requestFullscreen().catch(()=>{});}
}
document.getElementById('pixelOverlay').addEventListener('click',function(){
  this.style.display='none';
  if(document.fullscreenElement&&document.exitFullscreen){document.exitFullscreen().catch(()=>{});}
});
</script>
</body>
</html>
HTML_TAIL

rm -f "$CHECK_ROWS"

# Integrity manifest for evidence files and summaries. report.html is intentionally
# excluded because users may annotate it after generation.
(
  cd "$OUT_DIR" || exit 0
  for f in raw/*; do
    [ -f "$f" ] || continue
    /usr/bin/shasum -a 256 "$f"
  done
  /usr/bin/shasum -a 256 summary.txt summary.json
) > "$OUT_DIR/manifest.sha256" 2>/dev/null || true

say ""
say "MacBook Verify complete."
say "Report: $OUT_DIR/report.html"
say "PASS=$PASS_COUNT WARN=$WARN_COUNT FAIL=$FAIL_COUNT INFO=$INFO_COUNT"

if [ "$OPEN_REPORT" -eq 1 ]; then
  /usr/bin/open "$OUT_DIR/report.html" >/dev/null 2>&1 || true
fi

if command -v /usr/bin/osascript >/dev/null 2>&1; then
  /usr/bin/osascript -e "display notification \"PASS=$PASS_COUNT  WARN=$WARN_COUNT  FAIL=$FAIL_COUNT\" with title \"MacBook Verify complete\"" >/dev/null 2>&1 || true
fi

# In .command mode, give Finder-launched Terminal enough time to display the path.
if [ "$APP_MODE" -eq 0 ] && [ -t 1 ]; then
  say ""
  say "You can close this Terminal window."
fi

exit 0
