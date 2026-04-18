# pal_core_01_detect.py
#
# PAL Core 01 - Detect
#
# Commands:
#   1) ingest -> store one event
#   2) scan   -> scan stored events and generate alerts
#   3) demo   -> load demo events and scan
#
# Examples:
#   python pal_core_01_detect.py ingest "{\"site\":\"A\",\"type\":\"power_spike\",\"severity\":2}"
#   python pal_core_01_detect.py scan
#   python pal_core_01_detect.py demo
#
# Notes:
# - Deterministic only
# - No OpenAI needed in v1
# - Stores events in JSON file
# - Detects suspicious constellations inside a time window

import json
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

# --------------------------------------------------
# 1 FILES / CONSTANTS
# --------------------------------------------------
EVENTS_FILE = Path("pal_core_events.json")

ALLOWED_TOP_KEYS = {
    "timestamp",
    "site",
    "type",
    "severity",
    "note",
}

REQUIRED_KEYS = {
    "site",
    "type",
    "severity",
}

# Hardcoded v1 rule set
RULES = [
    {
        "name": "suspicious_activity",
        "site_types": ["power_spike", "camera_offline", "truck_delay"],
        "window_minutes": 30,
        "min_total_severity": 3,
    }
]

# --------------------------------------------------
# 2 HELPERS
# --------------------------------------------------
def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def parse_iso_timestamp(ts: str) -> datetime:
    # Accept trailing Z or normal ISO timezone format
    ts = ts.strip()
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

def load_events() -> List[Dict[str, Any]]:
    if not EVENTS_FILE.exists():
        return []

    try:
        data = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("Events file must contain a JSON list.")
        return data
    except Exception as e:
        raise RuntimeError(f"Failed to load {EVENTS_FILE}: {e}")

def save_events(events: List[Dict[str, Any]]) -> None:
    EVENTS_FILE.write_text(
        json.dumps(events, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

def validate_event(event: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    if not isinstance(event, dict):
        return ["Event must be a JSON object."]

    for key in REQUIRED_KEYS:
        if key not in event:
            errors.append(f"Missing required key: '{key}'.")

    for key in event.keys():
        if key not in ALLOWED_TOP_KEYS:
            errors.append(f"Unexpected key: '{key}'.")

    if "site" in event and not isinstance(event["site"], str):
        errors.append("'site' must be a string.")

    if "type" in event and not isinstance(event["type"], str):
        errors.append("'type' must be a string.")

    if "severity" in event:
        if not isinstance(event["severity"], int):
            errors.append("'severity' must be an integer.")
        elif event["severity"] < 0:
            errors.append("'severity' must be >= 0.")

    if "note" in event and not isinstance(event["note"], str):
        errors.append("'note' must be a string.")

    if "timestamp" in event:
        if not isinstance(event["timestamp"], str):
            errors.append("'timestamp' must be a string.")
        else:
            try:
                parse_iso_timestamp(event["timestamp"])
            except Exception:
                errors.append("'timestamp' must be valid ISO format.")

    return errors

def normalize_event(event: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(event)
    if "timestamp" not in out:
        out["timestamp"] = utc_now_iso()
    if "note" not in out:
        out["note"] = ""
    return out

def print_usage() -> None:
    print(
        "Usage:\n"
        "  python pal_core_01_detect.py ingest '<json_event>'\n"
        "  python pal_core_01_detect.py scan\n"
        "  python pal_core_01_detect.py demo\n\n"
        "Examples:\n"
        '  python pal_core_01_detect.py ingest "{\\"site\\":\\"A\\",\\"type\\":\\"power_spike\\",\\"severity\\":2}"\n'
        "  python pal_core_01_detect.py scan\n"
        "  python pal_core_01_detect.py demo"
    )

# --------------------------------------------------
# 3 COMMAND: INGEST
# --------------------------------------------------
def cmd_ingest(event_json_text: str) -> None:
    try:
        event = json.loads(event_json_text)
    except Exception as e:
        print("INGEST FAILED")
        print(f"Invalid JSON input: {e}")
        return

    errors = validate_event(event)
    if errors:
        print("INGEST FAILED")
        for err in errors:
            print(f"- {err}")
        return

    event = normalize_event(event)

    events = load_events()
    events.append(event)
    save_events(events)

    print("INGEST OK")
    print(f"Saved to: {EVENTS_FILE.resolve()}")
    print("Event:")
    print(json.dumps(event, indent=2, ensure_ascii=False))

# --------------------------------------------------
# 4 DETECTION ENGINE
# --------------------------------------------------
def group_events_by_site(events: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for e in events:
        site = e["site"]
        out.setdefault(site, []).append(e)
    return out

def compute_confidence(min_total_severity: int, actual_total_severity: int) -> float:
    if min_total_severity <= 0:
        return 0.5
    ratio = actual_total_severity / float(min_total_severity)
    # Cap at 0.99, floor at 0.50 for matched alert
    return round(max(0.50, min(0.99, 0.50 + 0.20 * (ratio - 1.0))), 2)

def find_latest_time(events: List[Dict[str, Any]]) -> Optional[datetime]:
    if not events:
        return None
    return max(parse_iso_timestamp(e["timestamp"]) for e in events)

def detect_rule_for_site(
    site: str,
    site_events: List[Dict[str, Any]],
    rule: Dict[str, Any],
) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []

    required_types = list(rule["site_types"])
    window_minutes = int(rule["window_minutes"])
    min_total_severity = int(rule["min_total_severity"])

    # Sort ascending by time
    sorted_events = sorted(site_events, key=lambda e: parse_iso_timestamp(e["timestamp"]))

    # Try each event timestamp as end of window
    for anchor_event in sorted_events:
        anchor_time = parse_iso_timestamp(anchor_event["timestamp"])
        window_start = anchor_time - timedelta(minutes=window_minutes)

        window_events = [
            e for e in sorted_events
            if window_start <= parse_iso_timestamp(e["timestamp"]) <= anchor_time
        ]

        types_in_window = {e["type"] for e in window_events}

        if not all(req_type in types_in_window for req_type in required_types):
            continue

        matched_events: List[Dict[str, Any]] = []
        for req_type in required_types:
            # pick latest event of each required type inside window
            candidates = [e for e in window_events if e["type"] == req_type]
            chosen = sorted(candidates, key=lambda e: parse_iso_timestamp(e["timestamp"]))[-1]
            matched_events.append(chosen)

        matched_events = sorted(matched_events, key=lambda e: parse_iso_timestamp(e["timestamp"]))
        total_severity = sum(int(e["severity"]) for e in matched_events)

        if total_severity < min_total_severity:
            continue

        first_time = parse_iso_timestamp(matched_events[0]["timestamp"])
        last_time = parse_iso_timestamp(matched_events[-1]["timestamp"])
        span_minutes = (last_time - first_time).total_seconds() / 60.0

        alert = {
            "alert_type": rule["name"],
            "site": site,
            "matched_events": [
                {
                    "type": e["type"],
                    "severity": e["severity"],
                    "timestamp": e["timestamp"],
                    "note": e.get("note", ""),
                }
                for e in matched_events
            ],
            "total_severity": total_severity,
            "confidence": compute_confidence(min_total_severity, total_severity),
            "reason": (
                f"Matched required constellation within {window_minutes} minutes "
                f"(actual span: {round(span_minutes, 1)} minutes)."
            ),
        }
        alerts.append(alert)

    # Deduplicate identical alerts by event timestamps/types
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for alert in alerts:
        key = (
            alert["alert_type"],
            alert["site"],
            tuple((e["type"], e["timestamp"]) for e in alert["matched_events"]),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(alert)

    return deduped

def detect_alerts(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []

    by_site = group_events_by_site(events)

    for site, site_events in by_site.items():
        for rule in RULES:
            site_alerts = detect_rule_for_site(site, site_events, rule)
            alerts.extend(site_alerts)

    return alerts

# --------------------------------------------------
# 5 COMMAND: SCAN
# --------------------------------------------------
def cmd_scan() -> None:
    events = load_events()

    if not events:
        print("SCAN FAILED")
        print("No events stored yet.")
        return

    print("=== STORED EVENTS ===")
    print(json.dumps(events, indent=2, ensure_ascii=False))

    alerts = detect_alerts(events)

    print("\n=== RULES ===")
    print(json.dumps(RULES, indent=2, ensure_ascii=False))

    print("\n=== ALERTS ===")
    if not alerts:
        print("[]")
        return

    print(json.dumps(alerts, indent=2, ensure_ascii=False))

# --------------------------------------------------
# 6 COMMAND: DEMO
# --------------------------------------------------
def demo_events() -> List[Dict[str, Any]]:
    base = datetime(2026, 4, 11, 10, 0, 0, tzinfo=timezone.utc)

    def ts(minutes: int) -> str:
        return (base + timedelta(minutes=minutes)).isoformat()

    return [
        {
            "site": "A",
            "type": "power_spike",
            "severity": 2,
            "note": "unexpected jump in electricity usage",
            "timestamp": ts(0),
        },
        {
            "site": "A",
            "type": "camera_offline",
            "severity": 1,
            "note": "camera feed lost",
            "timestamp": ts(8),
        },
        {
            "site": "A",
            "type": "truck_delay",
            "severity": 2,
            "note": "vehicle delay near site",
            "timestamp": ts(20),
        },
        {
            "site": "B",
            "type": "power_spike",
            "severity": 1,
            "note": "minor fluctuation",
            "timestamp": ts(3),
        },
        {
            "site": "B",
            "type": "truck_delay",
            "severity": 1,
            "note": "small traffic delay",
            "timestamp": ts(40),
        },
    ]

def cmd_demo() -> None:
    events = demo_events()
    save_events(events)

    print("DEMO OK")
    print(f"Saved demo events to: {EVENTS_FILE.resolve()}")
    print("\n=== STORED EVENTS ===")
    print(json.dumps(events, indent=2, ensure_ascii=False))

    alerts = detect_alerts(events)

    print("\n=== ALERTS ===")
    print(json.dumps(alerts, indent=2, ensure_ascii=False))

# --------------------------------------------------
# 7 MAIN
# --------------------------------------------------
def main() -> None:
    if len(sys.argv) < 2:
        print_usage()
        return

    command = sys.argv[1].strip().lower()

    if command == "ingest":
        if len(sys.argv) < 3:
            print("Missing JSON event for ingest.\n")
            print_usage()
            return
        cmd_ingest(sys.argv[2])

    elif command == "scan":
        cmd_scan()

    elif command == "demo":
        cmd_demo()

    else:
        print(f"Unknown command: {command}\n")
        print_usage()

if __name__ == "__main__":
    main()