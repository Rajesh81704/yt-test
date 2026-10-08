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
            forwarded_uri = headers.get(b"x-forwarded-uri", b"").decode("utf-8")
            matched_path = headers.get(b"x-matched-path", b"").decode("utf-8")
            scope_path = scope.get("path", "")

            target_path = None
            if forwarded_uri and forwarded_uri not in ("/api/index.py", "/api/index", "/api", "/api/"):
                target_path = forwarded_uri.split("?")[0]
            elif scope_path and scope_path not in ("/api/index.py", "/api/index", "/api", "/api/"):
                target_path = scope_path
            elif matched_path and matched_path not in ("/api/index.py", "/api/index", "/api", "/api/"):
                target_path = matched_path

            if target_path:
                for prefix in ("/api/index.py", "/api/index", "/api"):
                    if target_path.startswith(prefix):
                        target_path = target_path[len(prefix):]
                        break
                scope["path"] = target_path if target_path else "/"
            else:
                scope["path"] = "/"

        await self.app(scope, receive, send)


app = VercelPathMiddleware(fastapi_app)
