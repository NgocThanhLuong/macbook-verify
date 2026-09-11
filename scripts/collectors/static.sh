#!/bin/bash

collect_static_data() {
  mbv_step "Collecting hardware, security and device inventory"
  collect_file hardware.txt /usr/sbin/system_profiler SPHardwareDataType
  collect_file platform-ioreg.txt /usr/sbin/ioreg -rd1 -c IOPlatformExpertDevice
  collect_file battery-system.txt /usr/sbin/system_profiler SPPowerDataType
  collect_file battery-raw.txt /usr/sbin/ioreg -rn AppleSmartBattery
  collect_file display.txt /usr/sbin/system_profiler SPDisplaysDataType
  collect_file storage.txt /usr/sbin/system_profiler SPNVMeDataType SPStorageDataType
  collect_file memory.txt /usr/sbin/system_profiler SPMemoryDataType
  collect_file camera.txt /usr/sbin/system_profiler SPCameraDataType
  collect_file audio.txt /usr/sbin/system_profiler SPAudioDataType
  collect_file bluetooth.txt /usr/sbin/system_profiler SPBluetoothDataType
  collect_file wifi.txt /usr/sbin/system_profiler SPAirPortDataType
  collect_file usb.txt /usr/sbin/system_profiler SPUSBDataType
  collect_file thunderbolt.txt /usr/sbin/system_profiler SPThunderboltDataType
  collect_file diagnostics.txt /usr/sbin/system_profiler SPDiagnosticsDataType
  {
    echo "== macOS =="; /usr/bin/sw_vers 2>&1 || true
    echo; echo "== SIP =="; /usr/bin/csrutil status 2>&1 || true
    echo; echo "== FileVault =="; /usr/bin/fdesetup status 2>&1 || true
    echo; echo "== Gatekeeper =="; /usr/sbin/spctl --status 2>&1 || true
  } > "$RAW_DIR/security.txt"
  /usr/bin/profiles status -type enrollment > "$RAW_DIR/mdm.txt" 2>&1 || true

  _types="$(/usr/sbin/system_profiler -listDataTypes 2>/dev/null || true)"
  _repair="$(printf '%s\n' "$_types" | /usr/bin/grep -Ei 'SP.*(Repair|Parts).*DataType' || true)"
  if [ -n "$_repair" ]; then
    : > "$RAW_DIR/repair-history.txt"
    for _t in $_repair; do echo "== $_t ==" >> "$RAW_DIR/repair-history.txt"; /usr/sbin/system_profiler "$_t" >> "$RAW_DIR/repair-history.txt" 2>&1 || true; done
  else
    cat > "$RAW_DIR/repair-history.txt" <<'EOF'
No Repair/Parts system_profiler data type is exposed by this macOS build.
This is NOT proof that the Mac has never been repaired.
Also check System Settings > General > About > Parts & Service when available.
EOF
  fi
}

analyze_static_data() {
  mbv_step "Analyzing static hardware evidence"
  HARDWARE="$RAW_DIR/hardware.txt"; BATTERY="$RAW_DIR/battery-system.txt"; BATTERY_RAW="$RAW_DIR/battery-raw.txt"; DISPLAY="$RAW_DIR/display.txt"; STORAGE="$RAW_DIR/storage.txt"
  MODEL_NAME="$(field "$HARDWARE" "Model Name")"; MODEL_IDENTIFIER="$(field "$HARDWARE" "Model Identifier")"; MODEL_NUMBER="$(field "$HARDWARE" "Model Number")"
  CHIP="$(field "$HARDWARE" "Chip")"; [ -z "$CHIP" ] && CHIP="$(field "$HARDWARE" "Processor Name")"
  CPU_CORES="$(field "$HARDWARE" "Total Number of Cores")"; MEMORY="$(field "$HARDWARE" "Memory")"; SYSTEM_SERIAL="$(field "$HARDWARE" "Serial Number (system)")"; ACTIVATION_LOCK="$(field "$HARDWARE" "Activation Lock Status")"
  PLATFORM_SERIAL="$(ioreg_string "$RAW_DIR/platform-ioreg.txt" "IOPlatformSerialNumber")"; SYSCTL_MODEL="$(/usr/sbin/sysctl -n hw.model 2>/dev/null || true)"; OS_VERSION="$(/usr/bin/sw_vers -productVersion 2>/dev/null || true)"; OS_BUILD="$(/usr/bin/sw_vers -buildVersion 2>/dev/null || true)"
  BATTERY_SERIAL="$(field "$BATTERY" "Serial Number")"; BATTERY_CYCLES="$(field "$BATTERY" "Cycle Count")"; BATTERY_CONDITION="$(field "$BATTERY" "Condition")"; BATTERY_MAX_CAP="$(field "$BATTERY" "Maximum Capacity")"; BATTERY_MAX_NUM="$(printf '%s' "$BATTERY_MAX_CAP" | /usr/bin/tr -cd '0-9')"
  BATTERY_DESIGN_CAP="$(ioreg_number "$BATTERY_RAW" "DesignCapacity")"; BATTERY_RAW_MAX="$(ioreg_number "$BATTERY_RAW" "AppleRawMaxCapacity")"; BATTERY_PERM_FAIL="$(ioreg_number "$BATTERY_RAW" "PermanentFailureStatus")"; BATTERY_DISCONNECTS="$(ioreg_number "$BATTERY_RAW" "BatteryCellDisconnectCount")"; BATTERY_DESIGN_CYCLES="$(ioreg_number "$BATTERY_RAW" "DesignCycleCount9C")"
  DISPLAY_TYPE="$(field "$DISPLAY" "Display Type")"; DISPLAY_RESOLUTION="$(field "$DISPLAY" "Resolution")"; DISPLAY_ONLINE="$(field "$DISPLAY" "Online")"; DISPLAY_CONNECTION="$(field "$DISPLAY" "Connection Type")"; GPU_CORES="$(field "$DISPLAY" "Total Number of Cores")"
  SSD_MODEL="$(field "$STORAGE" "Model")"; SSD_CAPACITY="$(field "$STORAGE" "Capacity")"; SSD_TRIM="$(field "$STORAGE" "TRIM Support")"; SSD_SMART="$(field "$STORAGE" "S.M.A.R.T. status")"; [ -z "$SSD_SMART" ] && SSD_SMART="$(field "$STORAGE" "S.M.A.R.T. Status")"; SSD_DETACHABLE="$(field "$STORAGE" "Detachable Drive")"

  if [ -n "$SYSTEM_SERIAL" ] && [ -n "$PLATFORM_SERIAL" ]; then [ "$SYSTEM_SERIAL" = "$PLATFORM_SERIAL" ] && record_result Identity "Serial consistency" PASS "$SYSTEM_SERIAL" "system_profiler and IOKit match." || record_result Identity "Serial consistency" FAIL "$SYSTEM_SERIAL != $PLATFORM_SERIAL" "Unexpected serial mismatch; inspect logic board/firmware/configuration."; else record_result Identity "Serial consistency" INFO "Unavailable" "Could not obtain both sources."; fi
  if [ -n "$MODEL_IDENTIFIER" ] && [ -n "$SYSCTL_MODEL" ]; then [ "$MODEL_IDENTIFIER" = "$SYSCTL_MODEL" ] && record_result Identity "Model identifier consistency" PASS "$MODEL_IDENTIFIER" "system_profiler and sysctl match." || record_result Identity "Model identifier consistency" FAIL "$MODEL_IDENTIFIER != $SYSCTL_MODEL" "Unexpected model identity mismatch."; fi

  if [ -f "$PROJECT_ROOT/data/models.tsv" ] && [ -n "$MODEL_IDENTIFIER" ]; then
    DB_NAME="$(/usr/bin/awk -F '\t' -v id="$MODEL_IDENTIFIER" '$1==id{print $2;exit}' "$PROJECT_ROOT/data/models.tsv")"
    DB_YEAR="$(/usr/bin/awk -F '\t' -v id="$MODEL_IDENTIFIER" '$1==id{print $3;exit}' "$PROJECT_ROOT/data/models.tsv")"
    DB_RES="$(/usr/bin/awk -F '\t' -v id="$MODEL_IDENTIFIER" '$1==id{print $4;exit}' "$PROJECT_ROOT/data/models.tsv")"
    DB_NOTES="$(/usr/bin/awk -F '\t' -v id="$MODEL_IDENTIFIER" '$1==id{print $5;exit}' "$PROJECT_ROOT/data/models.tsv")"
    if [ -n "$DB_NAME" ]; then
      record_result Identity "Model database" PASS "$DB_NAME ($DB_YEAR)" "$DB_NOTES"
      if [ -n "$DB_RES" ] && [ -n "$DISPLAY_RESOLUTION" ]; then printf '%s' "$DISPLAY_RESOLUTION" | /usr/bin/grep -Fq "$DB_RES" && record_result Display "Native resolution vs model" PASS "$DISPLAY_RESOLUTION" "Matches local model reference." || record_result Display "Native resolution vs model" WARN "$DISPLAY_RESOLUTION" "Reference expects $DB_RES; verify display/model mapping."; fi
    else record_result Identity "Model database" INFO "$MODEL_IDENTIFIER" "Not in local reference DB; generic checks still run."; fi
  fi

  case "$BATTERY_CONDITION" in Normal|normal) record_result Battery Condition PASS "$BATTERY_CONDITION" "macOS reports normal condition.";; '') record_result Battery Condition INFO Unavailable "Condition not exposed.";; *) record_result Battery Condition WARN "$BATTERY_CONDITION" "Battery needs attention.";; esac
  if [ -n "$BATTERY_MAX_NUM" ]; then if [ "$BATTERY_MAX_NUM" -ge 80 ] 2>/dev/null; then record_result Battery "Maximum capacity" PASS "$BATTERY_MAX_CAP" "At/above 80%."; else record_result Battery "Maximum capacity" WARN "$BATTERY_MAX_CAP" "Significant wear."; fi; fi
  if [ -n "$BATTERY_CYCLES" ]; then _dc="$(safe_int "$BATTERY_DESIGN_CYCLES")"; if [ "$_dc" -gt 0 ]; then _warn=$((_dc*80/100)); [ "$BATTERY_CYCLES" -ge "$_warn" ] 2>/dev/null && record_result Battery "Cycle count" WARN "$BATTERY_CYCLES / $_dc" "High cycle region." || record_result Battery "Cycle count" PASS "$BATTERY_CYCLES / $_dc" "Below 80% of controller reference."; else record_result Battery "Cycle count" INFO "$BATTERY_CYCLES" "No design-cycle reference."; fi; fi
  if [ -n "$BATTERY_PERM_FAIL" ]; then [ "$BATTERY_PERM_FAIL" = 0 ] && record_result Battery "Permanent failure flag" PASS 0 "No permanent failure reported." || record_result Battery "Permanent failure flag" FAIL "$BATTERY_PERM_FAIL" "Controller reports permanent failure."; fi
  if [ -n "$BATTERY_DISCONNECTS" ]; then [ "$BATTERY_DISCONNECTS" = 0 ] && record_result Battery "Disconnect counter" PASS 0 "No disconnect recorded by this counter." || record_result Battery "Disconnect counter" WARN "$BATTERY_DISCONNECTS" "Non-zero is not proof of replacement; review."; fi

  _cells="$(ioreg_nested_list "$BATTERY_RAW" CellVoltage)"; if [ -n "$_cells" ]; then set -- $(minmax_delta "$_cells"); _d="$3"; [ "$_d" -le 20 ] && record_result Battery "Cell voltage balance" PASS "${_d} mV" "$4 cells, range $1-$2 mV." || record_result Battery "Cell voltage balance" WARN "${_d} mV" "Repeat at different SOC/load before judging."; fi
  _q="$(ioreg_nested_list "$BATTERY_RAW" Qmax)"; if [ -n "$_q" ]; then set -- $(minmax_delta "$_q"); _pct="$(/usr/bin/awk -v d="$3" -v m="$2" 'BEGIN{if(m>0)printf "%.2f",d*100/m;else print 0}')"; if /usr/bin/awk -v p="$_pct" 'BEGIN{exit !(p<=5)}'; then record_result Battery "Qmax cell balance" PASS "${_pct}% spread" "$4 values, range $1-$2."; else record_result Battery "Qmax cell balance" WARN "${_pct}% spread" "Uneven Qmax values; retest."; fi; fi
  if [ -n "$BATTERY_DESIGN_CAP" ] && [ -n "$BATTERY_RAW_MAX" ] && [ "$BATTERY_DESIGN_CAP" -gt 0 ] 2>/dev/null; then _ratio="$(/usr/bin/awk -v r="$BATTERY_RAW_MAX" -v d="$BATTERY_DESIGN_CAP" 'BEGIN{printf "%.1f",r*100/d}')"; if /usr/bin/awk -v p="$_ratio" 'BEGIN{exit !(p>=80)}'; then record_result Battery "Raw capacity vs design" PASS "${_ratio}%" "Raw max=$BATTERY_RAW_MAX, design=$BATTERY_DESIGN_CAP."; else record_result Battery "Raw capacity vs design" WARN "${_ratio}%" "Below 80%."; fi; fi

  if [ -n "$DISPLAY_TYPE" ]; then if [ "$DISPLAY_ONLINE" = Yes ] && { [ "$DISPLAY_CONNECTION" = Internal ] || [ -z "$DISPLAY_CONNECTION" ]; }; then record_result Display "Built-in display identity" PASS "$DISPLAY_TYPE" "$DISPLAY_RESOLUTION; internal/online."; else record_result Display "Built-in display identity" WARN "$DISPLAY_TYPE" "$DISPLAY_RESOLUTION; connection=${DISPLAY_CONNECTION:-unknown}."; fi; else record_result Display "Built-in display identity" WARN "Not identified" "No display type parsed."; fi
  case "$SSD_SMART" in Verified|verified) record_result Storage SMART PASS "$SSD_SMART" "SMART verified.";; '') record_result Storage SMART INFO Unavailable "SMART not exposed.";; *) record_result Storage SMART FAIL "$SSD_SMART" "SMART not verified.";; esac
  [ "$SSD_TRIM" = Yes ] && record_result Storage TRIM PASS Enabled "$SSD_MODEL; $SSD_CAPACITY" || record_result Storage TRIM INFO "${SSD_TRIM:-unknown}" "$SSD_MODEL; $SSD_CAPACITY"
  [ "$SSD_DETACHABLE" = No ] && record_result Storage "Internal/non-detachable" PASS No "Expected internal storage path." || { [ -n "$SSD_DETACHABLE" ] && record_result Storage "Internal/non-detachable" WARN "$SSD_DETACHABLE" "Unexpected for built-in storage."; }

  /usr/bin/grep -qi 'System Integrity Protection status: enabled' "$RAW_DIR/security.txt" && record_result Security SIP PASS Enabled "SIP enabled." || record_result Security SIP WARN "Not confirmed" "Disabled or unavailable."
  if /usr/bin/grep -qi 'FileVault is On' "$RAW_DIR/security.txt"; then record_result Security FileVault PASS On "Encryption enabled."; elif /usr/bin/grep -qi 'FileVault is Off' "$RAW_DIR/security.txt"; then record_result Security FileVault INFO Off "Not a hardware defect."; else record_result Security FileVault INFO Unknown "Could not determine."; fi
  if /usr/bin/grep -Eqi 'Enrolled via DEP:[[:space:]]*Yes|MDM enrollment:[[:space:]]*Yes' "$RAW_DIR/mdm.txt"; then record_result Ownership "MDM / Automated Enrollment" FAIL ENROLLED "Critical used-Mac check: organization management is present."; elif /usr/bin/grep -Eqi 'Enrolled via DEP:[[:space:]]*No|MDM enrollment:[[:space:]]*No' "$RAW_DIR/mdm.txt"; then record_result Ownership "MDM / Automated Enrollment" PASS "Not enrolled" "No enrollment reported."; else record_result Ownership "MDM / Automated Enrollment" INFO Unknown "Review raw/mdm.txt."; fi
  case "$ACTIVATION_LOCK" in Enabled|enabled) record_result Ownership "Activation Lock" INFO Enabled "Normal while in use; seller must remove before handover.";; Disabled|disabled) record_result Ownership "Activation Lock" PASS Disabled "Disabled.";; '') : ;; *) record_result Ownership "Activation Lock" INFO "$ACTIVATION_LOCK" "Review before transfer.";; esac

  /usr/bin/grep -Eqi 'Camera|Model ID|Unique ID|FaceTime' "$RAW_DIR/camera.txt" && record_result Devices Camera PASS Detected "Use live wizard to verify image." || record_result Devices Camera WARN "Not detected" "No camera inventory parsed."
  /usr/bin/grep -Eqi 'MacBook.*Speakers|Built-in Output|Speaker' "$RAW_DIR/audio.txt" && record_result Devices Speaker PASS Detected "Use stereo tone wizard." || record_result Devices Speaker INFO "Not confirmed" "Review audio inventory."
  /usr/bin/grep -Eqi 'Microphone|Built-in Input' "$RAW_DIR/audio.txt" && record_result Devices Microphone PASS Detected "Use mic-level wizard." || record_result Devices Microphone INFO "Not confirmed" "Review audio inventory."
  /usr/bin/grep -Eqi 'State:[[:space:]]*On' "$RAW_DIR/bluetooth.txt" && record_result Devices Bluetooth PASS On "Controller responds." || record_result Devices Bluetooth INFO "Off/unknown" "Turn on and retest if needed."
  /usr/bin/grep -q 'Interfaces:' "$RAW_DIR/wifi.txt" && record_result Devices Wi-Fi PASS Detected "Wi-Fi interface enumerated." || record_result Devices Wi-Fi WARN "Not detected" "No Wi-Fi interface parsed."
  /usr/bin/grep -q '^No Repair/Parts' "$RAW_DIR/repair-history.txt" && record_result Repair "Parts & Service CLI history" INFO "Not exposed" "Not proof of originality; check System Settings and physical condition." || record_result Repair "Parts & Service CLI history" INFO "Data available" "Review raw/repair-history.txt."
}
