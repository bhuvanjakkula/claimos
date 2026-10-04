import sys
from pathlib import Path

# Add parent directory to sys.path so 'app' package is found
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from app.main import app as fastapi_app

async def app(scope, receive, send):
    if scope["type"] == "http":
        headers = dict(scope.get("headers", []))
        
        # Check if Vercel forwarded the original URI in headers
        forwarded_path = None
        for h in [b"x-forwarded-uri", b"x-matched-path", b"x-invoke-path"]:
            if h in headers:
                val = headers[h].decode("utf-8", errors="replace")
                if val and val != "/api/index.py" and val != "/api":
                    forwarded_path = val.split("?")[0]
                    break
        
        if forwarded_path:
            scope["path"] = forwarded_path
            if "raw_path" in scope:
                scope["raw_path"] = forwarded_path.encode("ascii", "replace")
        else:
            path = scope.get("path", "")
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
