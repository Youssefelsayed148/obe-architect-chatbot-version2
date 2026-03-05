import time
import uuid
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}
logger = logging.getLogger("app.middleware")

class RequestIdAndSecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-Id") or f"req_{uuid.uuid4().hex[:12]}"
        start = time.time()

        try:
            response: Response = await call_next(request)
        except Exception:
            logger.exception(
                "Unhandled exception for request_id=%s method=%s path=%s",
                req_id,
                request.method,
                request.url.path,
            )
            raise

        response.headers["X-Request-Id"] = req_id
        for k, v in SECURITY_HEADERS.items():
            response.headers[k] = v

        duration_ms = int((time.time() - start) * 1000)
        logger.info(
            "request_id=%s method=%s path=%s status=%s duration_ms=%s",
            req_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )

        return response
