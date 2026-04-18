# pal_core_03_allocate.py
#
# PAL Core 03 - Allocate
#
# Commands:
#   1) demo   -> load demo tasks/workers and show allocation
#   2) status -> show current state and allocation
#   3) reset  -> reset to demo state and show allocation
#
# Examples:
#   python pal_core_03_allocate.py demo
#   python pal_core_03_allocate.py status
#   python pal_core_03_allocate.py reset
#
# Notes:
# - Deterministic only
# - No AI needed in v1
# - Greedy priority-based allocator
# - Assigns limited workers to highest-priority tasks they can perform

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# --------------------------------------------------
# 1 FILES / CONSTANTS
# --------------------------------------------------
STATE_FILE = Path("pal_core_allocate_state.json")

DEMO_STATE = {
    "tasks": [
        {
            "task_id": "T001",
            "type": "repair",
            "priority": 10,
            "duration": 2,
            "required_skill": "repair",
            "location": "Site_A",
        },
        {
            "task_id": "T002",
            "type": "delivery",
            "priority": 6,
            "duration": 1,
            "required_skill": "delivery",
            "location": "Site_B",
        },
        {
            "task_id": "T003",
            "type": "inspection",
            "priority": 4,
            "duration": 1,
            "required_skill": "inspect",
            "location": "Site_C",
        },
        {
            "task_id": "T004",
            "type": "repair",
            "priority": 8,
            "duration": 2,
            "required_skill": "repair",
            "location": "Site_D",
        },
        {
            "task_id": "T005",
            "type": "delivery",
            "priority": 3,
            "duration": 1,
            "required_skill": "delivery",
            "location": "Site_E",
        },
    ],
    "workers": [
        {
            "worker_id": "W001",
            "skills": ["repair"],
            "capacity": 2,
            "location": "Depot_1",
        },
        {
            "worker_id": "W002",
            "skills": ["delivery", "inspect"],
            "capacity": 2,
            "location": "Depot_2",
        },
        {
            "worker_id": "W003",
            "skills": ["repair", "inspect"],
            "capacity": 1,
            "location": "Depot_3",
        },
    ],
}

# --------------------------------------------------
# 2 HELPERS
# --------------------------------------------------
def load_state() -> Dict[str, Any]:
    if not STATE_FILE.exists():
        return json.loads(json.dumps(DEMO_STATE))
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))

def save_state(state: Dict[str, Any]) -> None:
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

def reset_state() -> Dict[str, Any]:
    state = json.loads(json.dumps(DEMO_STATE))
    save_state(state)
    return state

def print_usage() -> None:
    print(
        "Usage:\n"
        "  python pal_core_03_allocate.py demo\n"
        "  python pal_core_03_allocate.py status\n"
        "  python pal_core_03_allocate.py reset\n\n"
        "Examples:\n"
        "  python pal_core_03_allocate.py demo\n"
        "  python pal_core_03_allocate.py status\n"
        "  python pal_core_03_allocate.py reset"
    )

def worker_can_do_task(worker: Dict[str, Any], task: Dict[str, Any], remaining_capacity: int) -> bool:
    return (
        task["required_skill"] in worker["skills"]
        and remaining_capacity >= int(task["duration"])
    )

def sort_tasks(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Highest priority first, then shortest duration first, then task_id
    return sorted(
        tasks,
        key=lambda t: (-int(t["priority"]), int(t["duration"]), t["task_id"])
    )

def find_best_worker_for_task(
    workers: List[Dict[str, Any]],
    remaining_capacity: Dict[str, int],
    task: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []

    for w in workers:
        wid = w["worker_id"]
        rem = remaining_capacity.get(wid, 0)
        if worker_can_do_task(w, task, rem):
            candidates.append(w)

    if not candidates:
        return None

    # Choose worker with:
    # 1) smallest adequate remaining capacity after assignment
    # 2) fewest skills (more specialized first)
    # 3) worker_id
    def score(w: Dict[str, Any]) -> Tuple[int, int, str]:
        rem = remaining_capacity[w["worker_id"]]
        post = rem - int(task["duration"])
        return (post, len(w["skills"]), w["worker_id"])

    return sorted(candidates, key=score)[0]

def allocate(state: Dict[str, Any]) -> Dict[str, Any]:
    tasks = sort_tasks(state["tasks"])
    workers = list(state["workers"])

    remaining_capacity: Dict[str, int] = {
        w["worker_id"]: int(w["capacity"]) for w in workers
    }

    assignments: List[Dict[str, Any]] = []
    unassigned: List[Dict[str, Any]] = []

    for task in tasks:
        best_worker = find_best_worker_for_task(workers, remaining_capacity, task)

        if best_worker is None:
            unassigned.append({
                "task_id": task["task_id"],
                "type": task["type"],
                "priority": task["priority"],
                "duration": task["duration"],
                "required_skill": task["required_skill"],
                "location": task["location"],
                "reason": "no_available_worker_with_skill_and_capacity",
            })
            continue

        wid = best_worker["worker_id"]
        remaining_capacity[wid] -= int(task["duration"])

        assignments.append({
            "task_id": task["task_id"],
            "task_type": task["type"],
            "priority": task["priority"],
            "duration": task["duration"],
            "required_skill": task["required_skill"],
            "task_location": task["location"],
            "worker_id": wid,
            "worker_skills": best_worker["skills"],
            "worker_location": best_worker["location"],
        })

    worker_utilization: List[Dict[str, Any]] = []
    for w in workers:
        wid = w["worker_id"]
        cap = int(w["capacity"])
        rem = remaining_capacity[wid]
        used = cap - rem
        util = round((used / cap), 2) if cap > 0 else 0.0
        worker_utilization.append({
            "worker_id": wid,
            "capacity": cap,
            "used": used,
            "remaining": rem,
            "utilization": util,
        })

    total_priority_completed = sum(int(a["priority"]) for a in assignments)
    total_priority_unassigned = sum(int(t["priority"]) for t in unassigned)
    assigned_task_count = len(assignments)
    unassigned_task_count = len(unassigned)

    return {
        "assignments": assignments,
        "unassigned_tasks": unassigned,
        "assigned_task_count": assigned_task_count,
        "unassigned_task_count": unassigned_task_count,
        "total_priority_completed": total_priority_completed,
        "total_priority_unassigned": total_priority_unassigned,
        "worker_utilization": worker_utilization,
    }

def print_state_and_allocation(state: Dict[str, Any]) -> None:
    print("=== ALLOCATION STATE ===")
    print(json.dumps(state, indent=2, ensure_ascii=False))

    print("\n=== ALLOCATION RESULT ===")
    print(json.dumps(allocate(state), indent=2, ensure_ascii=False))

# --------------------------------------------------
# 3 COMMANDS
# --------------------------------------------------
def cmd_demo() -> None:
    state = reset_state()
    print("DEMO OK")
    print(f"Saved state to: {STATE_FILE.resolve()}")
    print_state_and_allocation(state)

def cmd_status() -> None:
    state = load_state()
    print_state_and_allocation(state)

def cmd_reset() -> None:
    state = reset_state()
    print("RESET OK")
    print(f"Saved state to: {STATE_FILE.resolve()}")
    print_state_and_allocation(state)

# --------------------------------------------------
# 4 MAIN
# --------------------------------------------------
def main() -> None:
    if len(sys.argv) < 2:
        print_usage()
        return

    command = sys.argv[1].strip().lower()

    if command == "demo":
        cmd_demo()
    elif command == "status":
        cmd_status()
    elif command == "reset":
        cmd_reset()
    else:
        print(f"Unknown command: {command}\n")
        print_usage()

if __name__ == "__main__":
    main()