from __future__ import annotations

import argparse
import http.client
import json
import urllib.error
import urllib.request
from typing import Any

FALLBACK = "I don't know based on the available sources"


def request_json(method: str, url: str, payload: dict[str, Any] | None = None, timeout: float = 60.0) -> tuple[int, Any, str]:
    data = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            body = json.loads(raw) if raw else None
            return int(resp.status), body, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            body = json.loads(raw) if raw else None
        except Exception:
            body = raw
        return int(exc.code), body, raw
    except (urllib.error.URLError, TimeoutError, http.client.RemoteDisconnected) as exc:
        raw = str(exc)
        return 0, {"error": raw}, raw


def _is_schema_ok(body: Any) -> bool:
    return isinstance(body, dict) and set(body.keys()) == {"answer", "sources", "confidence"}


def run(base_url: str, case: str, min_confidence: float) -> int:
    url = base_url.rstrip("/") + "/api/chat/ask"

    if case == "off":
        status, body, raw = request_json("POST", url, {"question": "What services does OBE provide?"})
        ok = status in (404, 503) and status != 500 and isinstance(body, dict)
        print(json.dumps({"case": case, "status": status, "body": body}, indent=2, ensure_ascii=False))
        print("PASS" if ok else f"FAIL: expected 404/503 JSON and not 500, got {status} body={raw[:400]}")
        return 0 if ok else 1

    if case == "on-happy":
        status, body, raw = request_json(
            "POST",
            url,
            {"question": "Summarize OBE experience in villas and what they provide."},
        )
        ok = (
            status == 200
            and _is_schema_ok(body)
            and isinstance(body.get("answer"), str)
            and bool(body.get("answer", "").strip())
            and isinstance(body.get("sources"), list)
            and len(body.get("sources")) > 0
            and all(isinstance(s, str) and s.startswith("http") for s in body.get("sources"))
            and isinstance(body.get("confidence"), (int, float))
            and 0.0 <= float(body.get("confidence")) <= 1.0
        )
        print(json.dumps({"case": case, "status": status, "body": body}, indent=2, ensure_ascii=False))
        print("PASS" if ok else f"FAIL: happy-path schema/constraints failed body={raw[:400]}")
        return 0 if ok else 1

    if case == "on-unanswerable":
        status, body, raw = request_json(
            "POST",
            url,
            {"question": "What is OBE annual revenue and net profit?"},
        )
        answer = str(body.get("answer") if isinstance(body, dict) else "")
        sources = body.get("sources") if isinstance(body, dict) else None
        conf = float(body.get("confidence", -1)) if isinstance(body, dict) else -1.0
        ok = (
            status == 200
            and _is_schema_ok(body)
            and FALLBACK in answer
            and isinstance(sources, list)
            and len(sources) == 0
            and conf < float(min_confidence)
        )
        print(json.dumps({"case": case, "status": status, "body": body, "threshold": min_confidence}, indent=2, ensure_ascii=False))
        print("PASS" if ok else f"FAIL: unanswerable behavior failed body={raw[:400]}")
        return 0 if ok else 1

    if case == "ollama-fallback":
        status, body, raw = request_json(
            "POST",
            url,
            {"question": "Summarize OBE experience in villas and what they provide."},
        )
        stacktrace_markers = ("Traceback", "Exception", "File \"")
        raw_has_stacktrace = any(m in raw for m in stacktrace_markers)
        ok = (
            status != 500
            and _is_schema_ok(body)
            and isinstance(body.get("answer"), str)
            and isinstance(body.get("sources"), list)
            and isinstance(body.get("confidence"), (int, float))
            and not raw_has_stacktrace
        )
        print(json.dumps({"case": case, "status": status, "body": body}, indent=2, ensure_ascii=False))
        print("PASS" if ok else f"FAIL: ollama fallback constraints failed body={raw[:400]}")
        return 0 if ok else 1

    print(f"FAIL: unknown case {case}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 4 public RAG endpoint gate checks")
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--case", required=True, choices=["off", "on-happy", "on-unanswerable", "ollama-fallback"])
    parser.add_argument("--min-confidence", type=float, default=0.55)
    args = parser.parse_args()
    return run(args.base_url, args.case, args.min_confidence)


if __name__ == "__main__":
    raise SystemExit(main())
