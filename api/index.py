import sys
import urllib.parse
from pathlib import Path

# Add parent directory to sys.path so 'app' package is found
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from app.main import app as fastapi_app

async def app(scope, receive, send):
    if scope["type"] == "http":
        path = scope.get("path", "")
        headers = dict(scope.get("headers", []))
        forwarded_path = None

        # 1. Check if route is provided via query parameter __vercel_route__
        query_bytes = scope.get("query_string", b"")
        if query_bytes and b"__vercel_route__=" in query_bytes:
            try:
                qs_str = query_bytes.decode("utf-8", errors="replace")
                parsed_qs = urllib.parse.parse_qs(qs_str)
                if "__vercel_route__" in parsed_qs:
                    val = parsed_qs["__vercel_route__"][0]
                    if val:
                        forwarded_path = val if val.startswith("/") else "/" + val
                    del parsed_qs["__vercel_route__"]
                    scope["query_string"] = urllib.parse.urlencode(parsed_qs, doseq=True).encode("utf-8")
            except Exception:
                pass

        # 2. Check if path is already a valid application path (not Vercel lambda handler name)
        if not forwarded_path and path and not path.startswith("/api/index.py") and not path.startswith("/api/index") and path != "/api":
            await fastapi_app(scope, receive, send)
            return

        # 3. Check Vercel route matches header
        if not forwarded_path and b"x-now-route-matches" in headers:
            try:
                matches = headers[b"x-now-route-matches"].decode("utf-8")
                parsed = urllib.parse.parse_qs(matches)
                if "1" in parsed and parsed["1"]:
                    candidate = parsed["1"][0]
                    if candidate:
                        forwarded_path = candidate if candidate.startswith("/") else "/" + candidate
            except Exception:
                pass

        # 4. Check other Vercel proxy headers
        if not forwarded_path:
            for h in [b"x-invoke-path", b"x-matched-path", b"x-forwarded-uri"]:
                if h in headers:
                    val = headers[h].decode("utf-8", errors="replace")
                    if val and not val.startswith("/api/index.py") and not val.startswith("/api/index") and val != "/api":
                        candidate = val.split("?")[0]
                        forwarded_path = candidate if candidate.startswith("/") else "/" + candidate
                        break

        # 5. Fallback path resolution
        if forwarded_path:
            scope["path"] = forwarded_path
            if "raw_path" in scope:
                scope["raw_path"] = forwarded_path.encode("ascii", "replace")
        else:
            for prefix in ["/api/index.py", "/api/index", "/api"]:
                if path == prefix:
                    scope["path"] = "/"
                    if "raw_path" in scope:
                        scope["raw_path"] = b"/"
                    break
                elif path.startswith(prefix + "/"):
                    clean_path = path[len(prefix):]
                    scope["path"] = clean_path
                    if "raw_path" in scope:
                        scope["raw_path"] = clean_path.encode("ascii", "replace")
                    break

    await fastapi_app(scope, receive, send)
