from fastapi import Header, HTTPException
from app.settings import settings

def require_admin(x_api_key: str | None = Header(default=None)):
    if not x_api_key or x_api_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Unauthorized")