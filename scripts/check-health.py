"""Check the local API process; persistence is not wired into the API yet."""

import json
import os
from urllib.request import urlopen

url = os.environ.get("CLIOVA_API_URL", "http://localhost:8000").rstrip("/")
with urlopen(f"{url}/health", timeout=5) as response:
    payload = json.load(response)
if payload != {"status": "ok", "service": "cliova"}:
    raise SystemExit(f"Unexpected health response: {payload!r}")
print("Cliova API is healthy")
