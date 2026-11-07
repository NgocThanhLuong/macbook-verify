#!/usr/bin/env python3
"""Opt-in per-user macOS LaunchAgent for periodic local SSD health snapshots.

No sudo, no private Apple APIs, no cloud account, no remote upload.
Running this script without an action only prints help. Monitoring must be
explicitly installed by the device owner.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

LABEL = "com.macbookverify.ssd-monitor"
AGENT = Path.home() / "Library" / "LaunchAgents" / (LABEL + ".plist")
DATA = Path.home() / "Library" / "Application Support" / "MacBookVerify" / "SSD"


def launchctl(*args: str) -> tuple[int, str]:
    try:
        p = subprocess.run(["/bin/launchctl", *args], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, check=False, timeout=12)
        return p.returncode, p.stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)


def install(interval: int = 900) -> dict:
    if sys.platform != "darwin":
        raise RuntimeError("LaunchAgent monitoring is supported on macOS only")
    if interval < 300:
        raise ValueError("Interval must be >= 300 seconds")
    script = Path(__file__).resolve().parent / "ssd_diagnostics.py"
    if not script.is_file():
        raise FileNotFoundError(str(script))
    AGENT.parent.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable, str(script), "--out-dir", str(DATA),
        "--history-dir", str(Path.home() / ".macbook-verify" / "ssd-history"),
        "--notify-changes"
    ]
    plist = {
        "Label": LABEL, "ProgramArguments": command,
        "StartInterval": interval, "RunAtLoad": True,
        "StandardOutPath": str(DATA / "monitor.log"),
        "StandardErrorPath": str(DATA / "monitor-errors.log"),
        "ProcessType": "Background"
    }
    uid = os.getuid()
    # In case an older copy was already loaded, stop it before updating.
    launchctl("bootout", f"gui/{uid}", str(AGENT))
    AGENT.write_bytes(plistlib.dumps(plist))
    try:
        AGENT.chmod(0o600)
    except OSError:
        pass
    code, msg = launchctl("bootstrap", f"gui/{uid}", str(AGENT))
    if code != 0:
        raise RuntimeError("Agent file created but launchctl failed: " + msg +
                           ". You can retry at login.")
    return {"status": "INSTALLED", "plist": str(AGENT), "interval_seconds": interval,
            "report_dir": str(DATA), "smartctl_installed": bool(shutil.which("smartctl"))}


def uninstall() -> dict:
    code, msg = launchctl("bootout", f"gui/{os.getuid()}", str(AGENT))
    existed = AGENT.exists()
    if existed:
        AGENT.unlink()
    return {"status": "UNINSTALLED", "had_agent": existed,
            "note": "Saved reports and history remain on the machine; remove manually if desired",
            "launchctl_note": msg if code != 0 else ""}


def status() -> dict:
    loaded = False
    code, msg = launchctl("print", f"gui/{os.getuid()}/{LABEL}")
    loaded = code == 0
    interval = None
    if AGENT.exists():
        try:
            interval = plistlib.loads(AGENT.read_bytes()).get("StartInterval")
        except (ValueError, OSError):
            pass
    return {"installed": AGENT.exists(), "loaded": loaded, "interval_seconds": interval,
            "report_dir": str(DATA)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MacBook Verify user-controlled SSD monitor")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--install", action="store_true")
    group.add_argument("--uninstall", action="store_true")
    group.add_argument("--status", action="store_true")
    parser.add_argument("--interval", type=int, default=900, help="seconds; minimum 300")
    args = parser.parse_args(argv)
    import json
    try:
        result = (install(args.interval) if args.install else
                  uninstall() if args.uninstall else status())
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print("Monitor: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
