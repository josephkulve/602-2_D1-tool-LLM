# pal_v1_gemma.py
#
# PAL v1 (local Gemma 4 via Ollama)
# Two commands:
#   1) ingest  -> store external data
#   2) analyze -> analyze stored data with local Gemma 4
#
# Examples:
#   python pal_v1_gemma.py ingest "{\"entity\":\"truck_17\",\"event_type\":\"shipment\",\"location\":\"taipei\",\"status\":\"delayed\",\"note\":\"flat tire\"}"
#   python pal_v1_gemma.py analyze
#
# Requirements:
#   - Ollama running locally
#   - A Gemma 4 model pulled into Ollama
#   - Recommended first model on smaller laptops: gemma4:e2b
#
# Optional .env settings:
#   OLLAMA_BASE_URL=http://localhost:11434
#   OLLAMA_MODEL=gemma4:e2b
#
# Notes:
#   - This keeps the same PAL v1 CLI shape as pal_v1.py.
#   - It does not use the OpenAI cloud API.
#   - It talks directly to Ollama's local HTTP API.

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List

# --------------------------------------------------
# 0 ENV
# --------------------------------------------------
def load_dotenv(dotenv_path: str = ".env") -> None:
    path = Path(dotenv_path)
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line or line.startswith("REM "):
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e2b")
OLLAMA_TIMEOUT_SECS = int(os.getenv("OLLAMA_TIMEOUT_SECS", "180"))

# --------------------------------------------------
# 1 FILES / CONSTANTS
# --------------------------------------------------
EVENTS_FILE = Path("pal_events.json")

ALLOWED_TOP_KEYS = {
    "timestamp",
    "entity",
    "event_type",
    "location",
    "status",
    "note",
}

REQUIRED_KEYS = {
    "entity",
    "event_type",
    "location",
    "status",
    "note",
}

ANALYSIS_SCHEMA_TEXT = """
Return valid JSON only, with this exact top-level structure:

{
  "summary": "short text summary",
  "abnormal_events": [
    {
      "entity": "string",
      "event_type": "string",
      "location": "string",
      "status": "string",
      "reason": "string"
    }
  ],
  "problem_entities": ["string"],
  "problem_locations": ["string"]
}

Rules:
- Return valid JSON only.
- Do not include markdown.
- "abnormal_events" should contain events that look problematic, unusual, delayed, failed, blocked, missing, or suspicious.
- "problem_entities" should list repeated or notable problematic entities.
- "problem_locations" should list repeated or notable problematic locations.
- If there are no abnormal events, return an empty list.
"""

# --------------------------------------------------
# 2 HELPERS
# --------------------------------------------------
def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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

    for key in REQUIRED_KEYS:
        if key in event and not isinstance(event[key], str):
            errors.append(f"'{key}' must be a string.")

    if "timestamp" in event and not isinstance(event["timestamp"], str):
        errors.append("'timestamp' must be a string.")

    return errors


def normalize_event(event: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(event)
    if "timestamp" not in out:
        out["timestamp"] = utc_now_iso()
    return out


def print_usage() -> None:
    print(
        "Usage:\n"
        "  python pal_v1_gemma.py ingest '<json_event>'\n"
        "  python pal_v1_gemma.py analyze\n\n"
        "Example:\n"
        '  python pal_v1_gemma.py ingest "{\\"entity\\":\\"truck_17\\",\\"event_type\\":\\"shipment\\",\\"location\\":\\"taipei\\",\\"status\\":\\"delayed\\",\\"note\\":\\"flat tire\\"}"\n'
        "  python pal_v1_gemma.py analyze\n\n"
        "Environment:\n"
        "  OLLAMA_BASE_URL=http://localhost:11434\n"
        "  OLLAMA_MODEL=gemma4:e2b\n"
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
# 4 COMMAND: ANALYZE
# --------------------------------------------------
def build_analysis_messages(events: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    events_json = json.dumps(events, indent=2, ensure_ascii=False)

    return [
        {
            "role": "system",
            "content": (
                "You are a structured data analysis model.\n\n"
                f"{ANALYSIS_SCHEMA_TEXT}"
            ),
        },
        {
            "role": "user",
            "content": (
                "Analyze the following stored events.\n\n"
                f"{events_json}"
            ),
        },
    ]


def _extract_json_object(text: str) -> Dict[str, Any]:
    text = text.strip()

    # Best case: pure JSON.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fallback: extract the first {...} block.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        return json.loads(candidate)

    raise ValueError("Model response did not contain valid JSON.")


def request_analysis(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    messages = build_analysis_messages(events)

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0,
        },
    }

    req = urllib.request.Request(
        url=f"{OLLAMA_BASE_URL}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT_SECS) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise RuntimeError(f"Ollama HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            "Could not reach Ollama. Is it running at "
            f"{OLLAMA_BASE_URL}? Original error: {e}"
        ) from e

    response_json = json.loads(raw)
    content = response_json.get("message", {}).get("content", "")
    if not content:
        raise RuntimeError(f"Unexpected Ollama response: {raw}")

    return _extract_json_object(content)


def cmd_analyze() -> None:
    events = load_events()

    if not events:
        print("ANALYZE FAILED")
        print("No events stored yet.")
        return

    print("=== STORED EVENTS ===")
    print(json.dumps(events, indent=2, ensure_ascii=False))

    print(f"\n=== LOCAL MODEL ===\n{OLLAMA_MODEL}")

    try:
        analysis = request_analysis(events)
    except Exception as e:
        print("ANALYZE FAILED")
        print(str(e))
        return

    print("\n=== ANALYSIS ===")
    print(json.dumps(analysis, indent=2, ensure_ascii=False))


# --------------------------------------------------
# 5 MAIN
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
        event_json_text = sys.argv[2]
        cmd_ingest(event_json_text)

    elif command == "analyze":
        cmd_analyze()

    else:
        print(f"Unknown command: {command}\n")
        print_usage()


if __name__ == "__main__":
    main()
