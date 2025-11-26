import json
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).parent / "fraud_db.json"


def _read_db() -> List[Dict]:
    if not DB_PATH.exists():
        return []
    with DB_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_db(data: List[Dict]):
    with DB_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def find_case_by_username(user_name: str) -> Optional[Dict]:
    """Return the first case matching the provided user name (case-insensitive)."""
    data = _read_db()
    for case in data:
        if case.get("userName", "").lower() == user_name.lower():
            return case
    return None


def update_case(user_name: str, status: str, outcome_note: str) -> bool:
    """Update a case's status and outcome note. Returns True if updated."""
    data = _read_db()
    updated = False
    for case in data:
        if case.get("userName", "").lower() == user_name.lower():
            case["status"] = status
            case["outcomeNote"] = outcome_note
            updated = True
            break
    if updated:
        _write_db(data)
    return updated


def list_pending_cases() -> List[Dict]:
    return [c for c in _read_db() if c.get("status") == "pending_review"]
