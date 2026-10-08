import sys
import os
import urllib.parse

# Ensure root directory is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app as fastapi_app


class VercelPathMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            headers = dict(scope.get("headers", []))
            query_string = scope.get("query_string", b"").decode("utf-8")
            query_params = urllib.parse.parse_qs(query_string)

            target_path = None

            if "path" in query_params and query_params["path"][0]:
                target_path = query_params["path"][0]

            if not target_path or target_path in ("/api/index.py", "/api/index", "/api", "/api/"):
                for header_key in (b"x-forwarded-uri", b"x-invoke-path", b"x-original-url", b"x-matched-path"):
                    val = headers.get(header_key, b"").decode("utf-8").split("?")[0]
                    if val and val not in ("/api/index.py", "/api/index", "/api", "/api/"):
                        target_path = val
                        break

            if not target_path or target_path in ("/api/index.py", "/api/index", "/api", "/api/"):
                scope_path = scope.get("path", "")
                if scope_path and scope_path not in ("/api/index.py", "/api/index", "/api", "/api/"):
                    target_path = scope_path

            if target_path:
                for prefix in ("/api/index.py", "/api/index", "/api"):
                    if target_path.startswith(prefix):
                        target_path = target_path[len(prefix):]
                        break
                scope["path"] = target_path if target_path.startswith("/") else "/" + target_path
            else:
                scope["path"] = "/"

        await self.app(scope, receive, send)


app = VercelPathMiddleware(fastapi_app)
