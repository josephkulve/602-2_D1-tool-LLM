# pal_v6_s3_hard_prompts.py

import requests
import json

BASE_URL = "http://localhost:8000"
API_KEY = "ShihanBeijing"

HEADERS = {
    "Content-Type": "application/json",
    "x-api-key": API_KEY,
}

# PROMPTS = [
#     "Analyze truck_99",
#     "Compare delayed shipments in Taipei vs blocked shipments in Tainan",
#     "Compare truck_99 with truck_17",
# ]

# PROMPTS = [
#    "Analyze delayed shipments in Taipei and compare them with all events in Kaohsiung",
#    "Which locations appear most operationally risky?",
#     "Which entities should be investigated first based on repeated problems?",
# ]

# PROMPTS = [
#     "Compare operational issues across Taipei, Tainan, and Kaohsiung",
#     "Which trucks show recurring problems and what patterns stand out?",
# ]

PROMPTS = [
    "Summarize the most abnormal events in the dataset",
    "Which locations have the highest concentration of delayed or blocked shipments?"
]

def test_run_prompt(prompt: str):
    r = requests.post(
        f"{BASE_URL}/run",
        headers=HEADERS,
        json={"prompt": prompt},
        timeout=120,
    )
    print("\n" + "=" * 80)
    print("PROMPT:")
    print(prompt)
    print("\nSTATUS:")
    print(r.status_code)

    try:
        data = r.json()
        print("\nRESPONSE:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception:
        print("\nRAW RESPONSE:")
        print(r.text)

def test_metric_endpoint(path: str):
    r = requests.get(f"{BASE_URL}{path}", headers={"x-api-key": API_KEY}, timeout=60)
    print("\n" + "=" * 80)
    print(f"METRIC ENDPOINT: {path}")
    print("\nSTATUS:")
    print(r.status_code)
    try:
        print("\nRESPONSE:")
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    except Exception:
        print("\nRAW RESPONSE:")
        print(r.text)

def main():
    # deterministic metrics first
    test_metric_endpoint("/recurring_problems")
    test_metric_endpoint("/problem_locations")
    test_metric_endpoint("/status_summary")

    # then harder prompts
    for prompt in PROMPTS:
        test_run_prompt(prompt)

if __name__ == "__main__":
    main()


