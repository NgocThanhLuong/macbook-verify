#!/usr/bin/env python3
"""Bounded, non-destructive filesystem SSD integrity + I/O latency probe.

Writes only a fresh temporary file in an approved scratch directory.
Uses incompressible random data, SHA-256, fsync, random read verification.
It is NOT a NAND scan, not direct SMART, and measurements can hit APFS cache.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import tempfile
import time

CHUNK = 1024 * 1024


def percentile(data: list[float], p: float) -> float | None:
    if not data:
        return None
    xs = sorted(data)
    i = min(len(xs) - 1, max(0, int((len(xs) - 1) * p)))
    return round(xs[i], 3)


def measure(size_mib: int, scratch: Path) -> dict:
    if not 1 <= size_mib <= 2048:
        raise ValueError("Test size must be 1..2048 MiB")
    scratch = scratch.expanduser().resolve(strict=True)
    if not scratch.is_dir():
        raise ValueError("Scratch directory missing")
    free = os.statvfs(str(scratch))
    available = free.f_bavail * free.f_frsize
    if available < (size_mib + 512) * CHUNK:
        return {"status": "SKIP", "reason": "Not enough available space for bounded SSD probe",
                "required_mib": size_mib + 512, "available_mib": round(available / CHUNK, 1)}
    name = None
    start = time.monotonic()
    write_samples = []
    read_samples = []
    expected = []
    sha_written = hashlib.sha256()
    sha_read = hashlib.sha256()
    written_bytes = size_mib * CHUNK
    result = {
        "status": "FAIL", "size_mib": size_mib, "scratch_mount": str(scratch),
        "note": "Filesystem I/O with APFS/page cache effects; not a NAND-level error scan."
    }
    try:
        # Exclusive newly-created file; never accept an existing arbitrary path.
        fd, name = tempfile.mkstemp(prefix=".mbv-ssd-probe-", suffix=".bin", dir=str(scratch))
        try:
            with os.fdopen(fd, "wb", buffering=0) as f:
                t0 = time.monotonic()
                for _ in range(size_mib):
                    buf = os.urandom(CHUNK)  # incompressible; no misleading APFS zero compression.
                    checksum = hashlib.sha256(buf).digest()
                    expected.append(checksum)
                    sha_written.update(buf)
                    tic = time.monotonic()
                    n = f.write(buf)
                    if n != CHUNK:
                        raise OSError("Short write")
                    write_samples.append((time.monotonic() - tic) * 1000)
                tic = time.monotonic()
                os.fsync(f.fileno())
                sync_ms = (time.monotonic() - tic) * 1000
                write_elapsed = max(.000001, time.monotonic() - t0)
            t0 = time.monotonic()
            with open(name, "rb", buffering=0) as f:
                for i in range(size_mib):
                    tic = time.monotonic()
                    buf = f.read(CHUNK)
                    read_samples.append((time.monotonic() - tic) * 1000)
                    if len(buf) != CHUNK:
                        raise OSError("Short read at chunk " + str(i))
                    sha_read.update(buf)
                    if hashlib.sha256(buf).digest() != expected[i]:
                        raise IOError("Data integrity mismatch at chunk " + str(i))
                read_elapsed = max(.000001, time.monotonic() - t0)
            if sha_read.digest() != sha_written.digest():
                raise IOError("SHA-256 mismatch between write/read streams")
            result.update({
                "status": "PASS", "bytes_verified": written_bytes,
                "whole_file_sha256": sha_written.hexdigest(),
                "write_mib_s": round(size_mib / write_elapsed, 1),
                "read_mib_s": round(size_mib / read_elapsed, 1),
                "fsync_ms": round(sync_ms, 2),
                "write_latency_p50_ms": percentile(write_samples, .5),
                "write_latency_p95_ms": percentile(write_samples, .95),
                "write_latency_p99_ms": percentile(write_samples, .99),
                "read_latency_p95_ms": percentile(read_samples, .95),
                "read_latency_p99_ms": percentile(read_samples, .99),
                "duration_sec": round(time.monotonic() - start, 2),
                "compressed_test_data": False,
                "persistent_device_scan": False
            })
        except (OSError, ValueError) as exc:
            result["reason"] = str(exc)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)
    return result


def trend_check(report: dict, history: list[dict]) -> None:
    # Compare only identical block sizes. Cache/thermal state can dominate,
    # so slowdown is review-only, never hard fail.
    if report.get("status") != "PASS":
        return
    matching = [r for r in history[-50:] if r.get("status") == "PASS"
                and r.get("size_mib") == report.get("size_mib")
                and r.get("scratch_mount") == report.get("scratch_mount")]
    if len(matching) < 3:
        return
    for key in ("write_mib_s", "read_mib_s"):
        baseline = [x.get(key) for x in matching[-10:] if isinstance(x.get(key), (int, float)) and x[key] > 0]
        current = report.get(key)
        if len(baseline) >= 3 and current < statistics.median(baseline) * .45:
            report.setdefault("warnings", []).append(
                key + " is <45% of own prior median; check APFS cache/temperature/background load")
            )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Safe SSD filesystem I/O and latency probe")
    p.add_argument("--size-mib", type=int, default=256)
    p.add_argument("--scratch-dir", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--history-dir", type=Path, default=Path.home() / ".macbook-verify" / "storage-history")
    args = p.parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.history_dir.mkdir(parents=True, exist_ok=True)
    history_file = args.history_dir / "probe-samples.jsonl"
    old = []
    if history_file.is_file():
        for line in history_file.read_text(encoding="utf-8").splitlines()[-100:]:
            try:
                old.append(json.loads(line))
            except ValueError:
                continue
    try:
        result = measure(args.size_mib, args.scratch_dir)
    except (ValueError, OSError) as exc:
        result = {"status": "FAIL", "reason": str(exc)}
    trend_check(result, old)
    if result.get("status") == "PASS":
        with history_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps({k:v for k,v in result.items()
                                if k not in ("whole_file_sha256",)}, ensure_ascii=False) + "\n")
    (args.out_dir / "ssd-io-probe.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    status = result["status"]
    rows = [("Active", "SSD random-data integrity probe", status,
             str(result.get("bytes_verified", "Unavailable")) + " bytes" if status == "PASS" else status,
             "Incompressible file write, fsync and SHA-256 re-read; non-destructive")]
    if status == "PASS":
        for key, title, unit in [
            ("write_mib_s", "SSD file write throughput", " MiB/s"),
            ("read_mib_s", "SSD file read throughput", " MiB/s"),
            ("fsync_ms", "SSD file fsync latency", " ms"),
            ("write_latency_p95_ms", "SSD write latency p95", " ms"),
            ("read_latency_p95_ms", "SSD read latency p95", " ms")
        ]:
            rows.append(("Performance", title, "INFO", str(result.get(key)) + unit,
                         "Informational; affected by filesystem cache, file size, CPU and load"))
        for warning in result.get("warnings", []):
            rows.append(("Performance", "SSD performance trend", "WARN", "Review", warning))
    else:
        rows.append(("Active", "SSD probe detail", "INFO", result.get("reason", "unavailable"), "No existing files modified"))
    (args.out_dir / "ssd-io-probe.tsv").write_text(
        "".join("\t".join(str(col).replace("\t", " ").replace("\n", " ")
                          for col in row) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k != "whole_file_sha256"}, ensure_ascii=False))
    return 0 if status in ("PASS", "SKIP", "FAIL") else 2


if __name__ == "__main__":
    raise SystemExit(main())
