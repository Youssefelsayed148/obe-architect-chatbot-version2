import json
from dataclasses import dataclass
from typing import Any, Dict
import redis
from app.settings import settings

r = redis.Redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
)

SESSION_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days

@dataclass
class Session:
    state: str
    data: Dict[str, Any]

def _key(session_id: str) -> str:
    return f"session:{session_id}"

def get_session(session_id: str) -> Session:
    raw = r.get(_key(session_id))
    if not raw:
        sess = Session(state="WELCOME", data={})
        save_session(session_id, sess)
        return sess
    obj = json.loads(raw)
    return Session(state=obj.get("state", "WELCOME"), data=obj.get("data", {}))

def save_session(session_id: str, sess: Session) -> None:
    r.setex(_key(session_id), SESSION_TTL_SECONDS, json.dumps({"state": sess.state, "data": sess.data}))

def set_state(session_id: str, state: str) -> None:
    sess = get_session(session_id)
    sess.state = state
    save_session(session_id, sess)

def set_data(session_id: str, key: str, value: Any) -> None:
    sess = get_session(session_id)
    sess.data[key] = value
    save_session(session_id, sess)

def get_data(session_id: str) -> Dict[str, Any]:
    return get_session(session_id).data
