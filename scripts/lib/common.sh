#!/bin/bash
# Shared helpers for MacBook Verify. Bash 3.2 compatible.

mbv_step() { printf '\n▶ %s\n' "$*"; }
mbv_info() { printf '  %s\n' "$*"; }

collect_file() {
  _file="$1"; shift
  "$@" > "$RAW_DIR/$_file" 2>&1 || true
}

clean_one_line() {
  printf '%s' "$1" | /usr/bin/tr '\t\r\n' '   ' | /usr/bin/sed -E 's/[ ]+/ /g; s/^ //; s/ $//'
}

record_result() {
  _area="$(clean_one_line "$1")"
  _test="$(clean_one_line "$2")"
  _status="$(clean_one_line "$3")"
  _value="$(clean_one_line "$4")"
  _detail="$(clean_one_line "$5")"
  case "$_status" in PASS|WARN|FAIL|INFO|SKIP) ;; *) _status="INFO" ;; esac
  printf '%s\t%s\t%s\t%s\t%s\n' "$_area" "$_test" "$_status" "$_value" "$_detail" >> "$RESULTS_FILE"
}

field() {
  _file="$1"; _label="$2"
  /usr/bin/awk -v label="$_label" '
    {
      line=$0; sub(/^[ \t]+/, "", line); prefix=label ":"
      if (index(line,prefix)==1) { value=substr(line,length(prefix)+1); sub(/^[ \t]+/,"",value); print value; exit }
    }
  ' "$_file" 2>/dev/null
}

ioreg_string() {
  _file="$1"; _key="$2"
  /usr/bin/grep -m 1 "\"$_key\" = \"" "$_file" 2>/dev/null | /usr/bin/sed -E 's/.*= "([^"]*)".*/\1/' | /usr/bin/head -n 1
}

ioreg_number() {
  _file="$1"; _key="$2"
  /usr/bin/grep -m 1 "\"$_key\" =" "$_file" 2>/dev/null | /usr/bin/sed -E 's/.*= ([0-9]+).*/\1/' | /usr/bin/head -n 1
}

ioreg_nested_number() {
  _file="$1"; _key="$2"
  /usr/bin/grep -m 1 "\"$_key\"=" "$_file" 2>/dev/null | /usr/bin/sed -E "s/.*\"$_key\"=([0-9]+).*/\\1/" | /usr/bin/head -n 1
}

ioreg_nested_list() {
  _file="$1"; _key="$2"
  /usr/bin/grep -m 1 "\"$_key\"=(" "$_file" 2>/dev/null | /usr/bin/sed -E "s/.*\"$_key\"=\\(([^)]*)\\).*/\\1/" | /usr/bin/tr ',' ' ' | /usr/bin/sed -E 's/[ ]+/ /g; s/^ //; s/ $//'
}

minmax_delta() {
  # Prints: min max delta count
  printf '%s\n' "$1" | /usr/bin/awk '
    { for(i=1;i<=NF;i++){ if($i ~ /^[0-9]+$/){ v=$i+0; if(n==0||v<mn)mn=v; if(n==0||v>mx)mx=v; n++ } } }
    END { if(n>0) printf "%d %d %d %d\n",mn,mx,mx-mn,n }
  '
}

html_escape() {
  printf '%s' "$1" | /usr/bin/sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' -e 's/"/\&quot;/g' -e "s/'/\&#39;/g"
}

json_escape() {
  printf '%s' "$1" | /usr/bin/sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | /usr/bin/tr '\r\n' '  '
}

status_counts() {
  /usr/bin/awk -F '\t' '
    $3=="PASS"{p++} $3=="WARN"{w++} $3=="FAIL"{f++} $3=="INFO"{i++} $3=="SKIP"{s++}
    END{printf "%d %d %d %d %d\n",p+0,w+0,f+0,i+0,s+0}
  ' "$RESULTS_FILE"
}

health_score() {
  /usr/bin/awk -F '\t' '
    $3=="PASS"{p++} $3=="WARN"{w++} $3=="FAIL"{f++}
    END { n=p+w+f; if(n==0) print 0; else printf "%d\n", ((p*100+w*60)/n)+0.5 }
  ' "$RESULTS_FILE"
}

area_score() {
  _area="$1"
  /usr/bin/awk -F '\t' -v a="$_area" '
    $1==a && $3=="PASS"{p++} $1==a && $3=="WARN"{w++} $1==a && $3=="FAIL"{f++}
    END { n=p+w+f; if(n==0) print "N/A"; else printf "%d", ((p*100+w*60)/n)+0.5 }
  ' "$RESULTS_FILE"
}

safe_int() { case "$1" in ''|*[!0-9]*) printf '0' ;; *) printf '%s' "$1" ;; esac; }

command_exists() { command -v "$1" >/dev/null 2>&1; }
