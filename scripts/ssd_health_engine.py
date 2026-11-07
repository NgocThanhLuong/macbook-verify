#!/usr/bin/env python3
"""Explainable SMART-based risk indicators for MacBook Verify.

Not proprietary DriveDx algorithms, not a failure prediction and not a warranty
of remaining drive life. Only model-independent, transparent rules.
"""
from __future__ import annotations
from typing import Any

# ATA attributes where a positive raw count is relevant to health. Attributes
# can still be vendor-specific; names are primary, IDs are supporting context.
CRITICAL_NAMES = (
    "reallocated_sector_ct", "reallocated_event_count", "current_pending_sector",
    "offline_uncorrectable", "reported_uncorrect", "program_fail_count",
    "erase_fail_count", "runtime_bad_block", "used_rsvd_blk_cnt_tot",
)
IMPORTANT_NAMES = (
    "wear_leveling_count", "percent_lifetime_remain", "ssd_life_left",
    "remaining_lifetime_perc", "media_wearout_indicator",
    "temperature_celsius", "power_on_hours", "power_cycle_count",
)
COUNT_NAMES = ("reallocated_sector_ct", "current_pending_sector", "offline_uncorrectable",
               "reported_uncorrect", "program_fail_count", "erase_fail_count")


def n(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, dict):
        return n(value.get("value"))
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def enrich(record: dict, raw: dict) -> dict:
    """Add confidence + attribute ratings; preserve original parsed status."""
    attrs: list[dict] = record.get("attributes") or []
    metrics: dict = record.get("metrics", {})
    indicators: list[dict] = []
    degraded: list[float] = []
    for attr in attrs:
        name = str(attr.get("name") or "").lower()
        label = str(attr.get("name") or "Unknown")
        v, threshold, raw_count = n(attr.get("value")), n(attr.get("threshold")), n(attr.get("raw"))
        is_important = name in CRITICAL_NAMES or name in IMPORTANT_NAMES
        category = "critical" if name in CRITICAL_NAMES else "important" if is_important else "general"
        rating = None
        status = "INFO"
        if threshold and threshold > 0 and v is not None:
            # Relative distance between a current normalized value and its
            # firmware failure threshold. Not an estimate of remaining years.
            reference = max(100, v, threshold + 1)
            rating = max(0, min(100, round(100 * (v - threshold) / (reference - threshold), 1)))
            if v <= threshold:
                status = "FAILING"
            elif category == "critical" and v - threshold <= 5:
                status = "WARNING"
            if category == "critical":
                degraded.append(rating)
        if name in COUNT_NAMES and raw_count is not None and raw_count > 0:
            status = "WARNING" if status != "FAILING" else status
        indicators.append({
            "name": label, "id": attr.get("id"), "group": category,
            "status": status, "distance_to_threshold_percent": rating,
            "value": attr.get("value"), "threshold": attr.get("threshold"),
            "worst": attr.get("worst"), "raw": attr.get("raw")
        })
    nvme = raw.get("nvme_smart_health_information_log")
    if isinstance(nvme, dict):
        for name, key, inverse in (
            ("Rated endurance remaining", "estimated_lifetime_left", False),
            ("Available spare", "available_spare", False),
            ("Media errors", "media_errors", True),
            ("Unsafe shutdowns", "unsafe_shutdowns", True),
            ("Critical warning bits", "critical_warning", True)):
            value = n((metrics.get(key) or {}).get("value"))
            if value is None:
                continue
            if key == "critical_warning":
                status = "FAILING" if value > 0 else "OK"
            elif key == "available_spare":
                threshold = n((metrics.get("available_spare_threshold") or {}).get("value"))
                status = "FAILING" if threshold is not None and value <= threshold else "WARNING" if value < 20 else "OK"
            elif key == "estimated_lifetime_left":
                status = "WARNING" if value <= 20 else "OK"
            else:
                status = "WARNING" if value > 0 else "OK"
            indicators.append({"name": name, "group": "critical" if key in ("critical_warning","media_errors") else "important",
                               "status": status, "value": value, "unit": "",
                               "source": "NVMe SMART"})
    record["important_indicators"] = indicators
    smart = metrics.get("smart_passed", {}).get("value")
    coverage = sum(1 for key in ("percentage_used", "available_spare", "media_errors",
                                  "power_on_hours", "temperature_c") if metrics.get(key) is not None)
    coverage += sum(1 for a in indicators if a.get("group") == "critical")
    record["evidence_confidence"] = (
        "DETAILED" if coverage >= 5 else "PARTIAL" if coverage >= 2 else
        "BASIC" if smart is not None else "UNAVAILABLE"
    )
    # A transparent health SIGNAL; do not mislabel as firmware SSD Health %.
    used = n((metrics.get("percentage_used") or {}).get("value"))
    spare = n((metrics.get("available_spare") or {}).get("value"))
    if record["evidence_confidence"] in ("DETAILED", "PARTIAL"):
        score = 100.0
        if used is not None:
            score -= min(35, used * .35)
        if spare is not None and spare < 30:
            score -= min(25, (30 - spare) * 1.25)
        if any(i["status"] == "FAILING" for i in indicators) or smart is False:
            score = min(score, 10)
        elif any(i["status"] == "WARNING" for i in indicators):
            score = min(score, 65)
        if degraded:
            score = min(score, min(degraded))
        record["diagnostic_signal_score"] = max(0, round(score))
    else:
        record["diagnostic_signal_score"] = None
    record["performance_rating"] = None  # Do not infer performance from short I/O benchmarks.
    record["interpretation"] = (
        "Signal score summarizes available SMART warnings; not failure probability or lifetime %. "
        "UNKNOWN/BASIC signal is not evidence of a healthy SSD."
    )
    return record


def comparison_alerts(record: dict, previous: dict | None) -> None:
    """Add clear warnings if normalized values degrade or error raw counters rise."""
    if not previous:
        return
    previous_attrs = {str(v.get("id")): v for v in previous.get("attributes", [])
                      if isinstance(v, dict)}
    for cur in record.get("attributes", []):
        old = previous_attrs.get(str(cur.get("id")))
        if not old:
            continue
        name = str(cur.get("name") or "").lower()
        currval, lastval = n(cur.get("value")), n(old.get("value"))
        currraw, lastraw = n(cur.get("raw")), n(old.get("raw"))
        if name in CRITICAL_NAMES and currval is not None and lastval is not None and currval < lastval:
            record["alerts"].append({
                "severity": "WARNING", "title": "Critical ATA indicator degraded",
                "detail": str(cur.get("name")) + " normalized: " + str(lastval) + " → " + str(currval)
            })
        if name in COUNT_NAMES and currraw is not None and lastraw is not None and currraw > lastraw:
            record["alerts"].append({
                "severity": "WARNING", "title": "ATA error counter increased",
                "detail": str(cur.get("name")) + " raw: +" + str(currraw - lastraw)
            })
    if any(a.get("severity") == "WARNING" for a in record["alerts"]) and record["status"] not in ("FAILING",):
        record["status"] = "WARNING"
