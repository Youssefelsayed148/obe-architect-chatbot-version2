import sys
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

# Ensure project root is importable when pytest is invoked from different shells/entrypoints.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def client(monkeypatch):
    import app.main as main

    # Keep tests offline by default.
    monkeypatch.setattr(main, "init_db", lambda: None)
    with TestClient(main.app) as test_client:
        yield test_client
