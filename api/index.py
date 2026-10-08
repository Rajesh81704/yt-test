import sys
import os

# Ensure root directory is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app as fastapi_app


class VercelPathMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            headers = dict(scope.get("headers", []))
            raw_uri = headers.get(b"x-forwarded-uri", b"").decode("utf-8") or headers.get(b"x-matched-path", b"").decode("utf-8")

            if raw_uri:
                clean_path = raw_uri.split("?")[0]
                if clean_path and clean_path not in ("/api/index.py", "/api/index", "/api"):
                    scope["path"] = clean_path
            else:
                path = scope.get("path", "")
                for prefix in ("/api/index.py", "/api/index", "/api"):
                    if path.startswith(prefix):
                        remainder = path[len(prefix):]
                        scope["path"] = remainder if remainder else "/"
                        break

        await self.app(scope, receive, send)


app = VercelPathMiddleware(fastapi_app)
