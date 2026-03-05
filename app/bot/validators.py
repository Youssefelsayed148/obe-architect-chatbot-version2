import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[0-9\s\-()]{7,20}$")

def is_email(s: str) -> bool:
    return bool(EMAIL_RE.match(s.strip()))

def is_phone(s: str) -> bool:
    return normalize_phone(s) is not None


def normalize_phone(s: str) -> str | None:
    if not s:
        return None

    cleaned = s.strip().replace("\u00A0", " ")
    if not cleaned:
        return None

    if not PHONE_RE.match(cleaned):
        return None

    # Keep only leading '+' and digits so values are stored consistently.
    compact = re.sub(r"[()\-\s]", "", cleaned)
    if compact.startswith("00"):
        compact = f"+{compact[2:]}"

    if compact.count("+") > 1 or ("+" in compact and not compact.startswith("+")):
        return None

    digits = re.sub(r"\D", "", compact)
    if len(digits) < 8 or len(digits) > 15:
        return None

    return f"+{digits}"
