#!/bin/bash

configure_test_profile() {
  case "$MODE" in
    quick) CPU_SECONDS=8; STORAGE_MB=128; MEMORY_MB=64; LOG_DAYS=7 ;;
    deep) CPU_SECONDS=45; STORAGE_MB=1024; MEMORY_MB=512; LOG_DAYS=30 ;;
    burn-in) CPU_SECONDS=180; STORAGE_MB=1024; MEMORY_MB=1024; LOG_DAYS=30 ;;
    *) CPU_SECONDS=20; STORAGE_MB=512; MEMORY_MB=256; LOG_DAYS=14 ;;
  esac
}

run_cpu_test() {
  mbv_step "Active CPU / thermal stability test (${CPU_SECONDS}s)"
  _cores="$(/usr/sbin/sysctl -n hw.logicalcpu 2>/dev/null || echo 1)"
  _cores="$(safe_int "$_cores")"; [ "$_cores" -lt 1 ] && _cores=1; [ "$_cores" -gt 16 ] && _cores=16
  _seed="$SCRATCH_DIR/cpu-seed.bin"
  /bin/dd if=/dev/zero of="$_seed" bs=1048576 count=16 >/dev/null 2>&1 || true
  _expected="$(/usr/bin/shasum -a 256 "$_seed" 2>/dev/null | /usr/bin/awk '{print $1}')"
  _pids=""; _i=0
  while [ "$_i" -lt "$_cores" ]; do
    /usr/bin/yes > /dev/null 2>&1 & _pids="$_pids $!"; _i=$((_i+1))
  done
  _start="$(date +%s)"; _hash_fail=0
  : > "$RAW_DIR/cpu-thermal.txt"
  while :; do
    _now="$(date +%s)"; _elapsed=$((_now-_start)); [ "$_elapsed" -ge "$CPU_SECONDS" ] && break
    _h="$(/usr/bin/shasum -a 256 "$_seed" 2>/dev/null | /usr/bin/awk '{print $1}')"
    [ -n "$_expected" ] && [ "$_h" != "$_expected" ] && _hash_fail=$((_hash_fail+1))
    { echo "--- t=${_elapsed}s ---"; /usr/bin/pmset -g therm 2>&1 || true; } >> "$RAW_DIR/cpu-thermal.txt"
    /bin/sleep 2
  done
  for _p in $_pids; do /bin/kill "$_p" >/dev/null 2>&1 || true; done
  wait >/dev/null 2>&1 || true
  if [ "$_hash_fail" -eq 0 ]; then
    record_result Active "CPU sustained load + hash integrity" PASS "${CPU_SECONDS}s / ${_cores} workers" "Repeated SHA-256 remained stable while CPU workers were saturated."
  else
    record_result Active "CPU sustained load + hash integrity" FAIL "$_hash_fail hash mismatches" "Unexpected integrity mismatch during CPU load. Retest and investigate stability."
  fi
  if /usr/bin/grep -Eqi 'CPU_Speed_Limit[[:space:]]*=[[:space:]]*(0|[1-7][0-9])|Thermal.*(Warning|Level).*=[[:space:]]*[1-9]' "$RAW_DIR/cpu-thermal.txt"; then
    record_result Thermal "Thermal pressure during CPU test" WARN "Pressure observed" "pmset reported a possible thermal/power limit; inspect raw/cpu-thermal.txt and repeat under normal ambient conditions."
  else
    record_result Thermal "Thermal pressure during CPU test" PASS "No obvious limit" "No obvious severe thermal-limit signature parsed from pmset snapshots. This is not a temperature sensor calibration test."
  fi
}

run_memory_test() {
  mbv_step "Memory integrity test (${MEMORY_MB} MiB target)"
  _src="$PROJECT_ROOT/helpers/memory_test.c"; _bin="$SCRATCH_DIR/memory-test"
  if [ -f "$_src" ] && command_exists /usr/bin/cc && /usr/bin/cc -O2 "$_src" -o "$_bin" > "$RAW_DIR/memory-build.txt" 2>&1; then
    if "$_bin" "$MEMORY_MB" > "$RAW_DIR/memory-active.txt" 2>&1; then
      _line="$(/usr/bin/tail -n 1 "$RAW_DIR/memory-active.txt" 2>/dev/null)"
      record_result Active "RAM pattern integrity" PASS "${MEMORY_MB} MiB" "${_line:-Pattern write/read verification completed.}"
    else
      record_result Active "RAM pattern integrity" FAIL "${MEMORY_MB} MiB" "Native memory pattern test returned an error; inspect raw/memory-active.txt."
    fi
  else
    /usr/bin/memory_pressure -Q > "$RAW_DIR/memory-pressure.txt" 2>&1 || true
    record_result Active "RAM pattern integrity" SKIP "Compiler unavailable" "No developer compiler was available to build the bundled native memory tester. memory_pressure snapshot was collected instead."
  fi
}

run_storage_test() {
  mbv_step "Storage write/read/checksum test (${STORAGE_MB} MiB temporary file)"
  _f="$SCRATCH_DIR/storage-test.bin"
  _wlog="$RAW_DIR/storage-write.txt"; _rlog="$RAW_DIR/storage-read.txt"
  _t0="$(date +%s)"
  /bin/dd if=/dev/zero of="$_f" bs=1048576 count="$STORAGE_MB" > /dev/null 2> "$_wlog"; _wrc=$?
  /bin/sync
  _t1="$(date +%s)"; _wsec=$((_t1-_t0)); [ "$_wsec" -lt 1 ] && _wsec=1
  _hash1="$(/usr/bin/shasum -a 256 "$_f" 2>/dev/null | /usr/bin/awk '{print $1}')"
  _t2="$(date +%s)"
  /bin/dd if="$_f" of=/dev/null bs=1048576 > /dev/null 2> "$_rlog"; _rrc=$?
  _hash2="$(/bin/cat "$_f" 2>/dev/null | /usr/bin/shasum -a 256 | /usr/bin/awk '{print $1}')"
  _t3="$(date +%s)"; _rsec=$((_t3-_t2)); [ "$_rsec" -lt 1 ] && _rsec=1
  _wmbs=$((STORAGE_MB/_wsec)); _rmbs=$((STORAGE_MB/_rsec))
  if [ "$_wrc" -eq 0 ] && [ "$_rrc" -eq 0 ] && [ -n "$_hash1" ] && [ "$_hash1" = "$_hash2" ]; then
    record_result Active "SSD filesystem I/O integrity" PASS "${STORAGE_MB} MiB verified" "Temporary file wrote, read, and produced identical SHA-256 through two read paths."
  else
    record_result Active "SSD filesystem I/O integrity" FAIL "I/O/checksum failure" "write_rc=$_wrc read_rc=$_rrc checksum_match=$([ "$_hash1" = "$_hash2" ] && echo yes || echo no)."
  fi
  record_result Performance "SSD coarse write throughput" INFO "~${_wmbs} MiB/s" "Coarse wall-clock measurement only; Desktop/iCloud is not used for scratch data."
  record_result Performance "SSD coarse read throughput" INFO "~${_rmbs} MiB/s" "Coarse wall-clock measurement; filesystem cache may influence this value, so it is not a benchmark score."
  /bin/rm -f "$_f"
}

run_network_test() {
  mbv_step "Network controller / local connectivity test"
  _gateway="$(/sbin/route -n get default 2>/dev/null | /usr/bin/awk '/gateway:/{print $2;exit}')"
  if [ -n "$_gateway" ]; then
    if /sbin/ping -c 3 -W 1000 "$_gateway" > "$RAW_DIR/network-ping.txt" 2>&1; then
      record_result Network "Default gateway reachability" PASS "$_gateway" "Local network path responds to ICMP."
    else
      record_result Network "Default gateway reachability" INFO "$_gateway unreachable" "Could be firewall/network policy rather than a Wi-Fi hardware fault."
    fi
  else
    record_result Network "Default gateway reachability" INFO "No default route" "Network may be intentionally offline."
  fi
  if /usr/bin/dscacheutil -q host -a name apple.com > "$RAW_DIR/network-dns.txt" 2>&1 && /usr/bin/grep -q '^ip_address:' "$RAW_DIR/network-dns.txt"; then
    record_result Network "DNS resolution" PASS "apple.com resolved" "DNS stack responded."
  else
    record_result Network "DNS resolution" INFO "No resolution" "May simply be offline; not treated as a hardware failure."
  fi
}

run_error_history_test() {
  mbv_step "Scanning recent panic / shutdown / device-error evidence"
  : > "$RAW_DIR/recent-diagnostics.txt"
  _panic_count=0
  for _dir in "$HOME/Library/Logs/DiagnosticReports" "/Library/Logs/DiagnosticReports"; do
    [ -d "$_dir" ] || continue
    /usr/bin/find "$_dir" -type f -mtime -"$LOG_DAYS" \( -iname '*panic*' -o -iname '*Kernel*' -o -iname '*GPU*Reset*' \) -print >> "$RAW_DIR/recent-diagnostics.txt" 2>/dev/null || true
  done
  _panic_count="$(/usr/bin/grep -c '.' "$RAW_DIR/recent-diagnostics.txt" 2>/dev/null || echo 0)"
  _panic_count="$(safe_int "$_panic_count")"
  if [ "$_panic_count" -eq 0 ]; then
    record_result History "Recent panic/reset reports" PASS "0 in ${LOG_DAYS}d" "No matching panic/kernel/GPU-reset diagnostic filenames found in standard DiagnosticReports locations."
  else
    record_result History "Recent panic/reset reports" WARN "$_panic_count in ${LOG_DAYS}d" "Review raw/recent-diagnostics.txt; filenames alone do not establish a hardware cause."
  fi
  /usr/bin/pmset -g log 2>/dev/null | /usr/bin/grep -Ei 'shutdown cause|thermal|failure|sleep.*fail|wake.*fail' | /usr/bin/tail -n 500 > "$RAW_DIR/power-history.txt" || true
  _power_events="$(/usr/bin/grep -c '.' "$RAW_DIR/power-history.txt" 2>/dev/null || echo 0)"; _power_events="$(safe_int "$_power_events")"
  record_result History "Power/sleep warning log" INFO "$_power_events matched lines" "Review raw/power-history.txt for context; many matched lines are benign."
}

run_postload_battery_test() {
  mbv_step "Post-load battery telemetry snapshot"
  /usr/sbin/ioreg -rn AppleSmartBattery > "$RAW_DIR/battery-postload.txt" 2>&1 || true
  _max_temp="$(ioreg_nested_number "$RAW_DIR/battery-postload.txt" "MaximumTemperature")"
  [ -z "$_max_temp" ] && _max_temp="$(ioreg_nested_number "$BATTERY_RAW" "MaximumTemperature")"
  if [ -n "$_max_temp" ]; then
    if [ "$_max_temp" -ge 60 ] 2>/dev/null; then
      record_result Battery "Lifetime maximum temperature" WARN "${_max_temp}°C" "Battery telemetry reports a high lifetime maximum temperature."
    else
      record_result Battery "Lifetime maximum temperature" INFO "${_max_temp}°C" "Historical controller metric; not the current temperature."
    fi
  fi
  _after_cells="$(ioreg_nested_list "$RAW_DIR/battery-postload.txt" "CellVoltage")"
  if [ -n "$_after_cells" ]; then
    set -- $(minmax_delta "$_after_cells"); _d="$3"
    [ "$_d" -le 30 ] && record_result Battery "Cell balance after load" PASS "${_d} mV" "Cell delta remains low after active test." || record_result Battery "Cell balance after load" WARN "${_d} mV" "Repeat on battery at moderate state of charge; load/SOC can affect instantaneous delta."
  fi
}

run_active_tests() {
  configure_test_profile
  run_cpu_test
  run_memory_test
  run_storage_test
  run_network_test
  run_error_history_test
  run_postload_battery_test
}
