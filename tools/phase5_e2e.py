from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


def _request_json(method: str, url: str, payload: dict[str, Any] | None = None, timeout: float = 30.0) -> tuple[int, Any]:
    data = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            body = json.loads(raw) if raw else None
            return int(response.status), body
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        body = None
        if raw:
            try:
                body = json.loads(raw)
            except Exception:
                body = raw
        return int(exc.code), body


def _check_schema(body: Any) -> bool:
    if not isinstance(body, dict):
        return False
    keys = set(body.keys())
    return keys == {"answer", "sources", "confidence"}


def run(base_url: str) -> int:
    base = base_url.rstrip("/")
    checks: list[tuple[str, bool, str]] = []

    health_status, health_body = _request_json("GET", f"{base}/health")
    checks.append(("health", health_status == 200 and isinstance(health_body, dict) and health_body.get("ok") is True, f"status={health_status} body={health_body}"))

    answerable_status, answerable_body = _request_json(
        "POST",
        f"{base}/api/chat/ask",
        {"question": "Summarize OBE experience in villas and what they provide."},
        timeout=60.0,
    )
    answerable_ok = (
        answerable_status == 200
        and _check_schema(answerable_body)
        and isinstance(answerable_body.get("answer"), str)
        and bool(answerable_body.get("answer", "").strip())
        and isinstance(answerable_body.get("sources"), list)
        and isinstance(answerable_body.get("confidence"), (int, float))
    )
    checks.append(("chat_ask_answerable", answerable_ok, f"status={answerable_status} body={answerable_body}"))

    unanswerable_status, unanswerable_body = _request_json(
        "POST",
        f"{base}/api/chat/ask",
        {"question": "What is OBE annual revenue and net profit?"},
        timeout=60.0,
    )
    fallback_text = "I don't know based on the available sources."
    unanswerable_ok = (
        unanswerable_status == 200
        and _check_schema(unanswerable_body)
        and isinstance(unanswerable_body.get("answer"), str)
        and fallback_text in unanswerable_body.get("answer", "")
    )
    checks.append(("chat_ask_unanswerable", unanswerable_ok, f"status={unanswerable_status} body={unanswerable_body}"))

    guided_status, guided_body = _request_json(
        "POST",
        f"{base}/api/chat/message",
        {"channel": "web", "user_id": "phase5-smoke", "session_id": None, "text": "Hello", "button_id": None},
        timeout=60.0,
    )
    guided_ok = (
        guided_status == 200
        and isinstance(guided_body, dict)
        and isinstance(guided_body.get("session_id"), str)
        and isinstance(guided_body.get("messages"), list)
    )
    checks.append(("chat_message_smoke", guided_ok, f"status={guided_status} body={guided_body}"))

    all_passed = True
    for name, ok, detail in checks:
        state = "PASS" if ok else "FAIL"
        print(f"[{state}] {name}: {detail}")
        if not ok:
            all_passed = False

    return 0 if all_passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 5 E2E smoke checks through nginx.")
    parser.add_argument("--base-url", default="http://localhost:8080", help="Base URL exposed by nginx (default: http://localhost:8080)")
    args = parser.parse_args()
    return run(args.base_url)


if __name__ == "__main__":
    raise SystemExit(main())
