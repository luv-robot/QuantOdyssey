import os
import shutil
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse


REQUIRED_KEYS = ["OPENAI_API_KEY"]
OPTIONAL_KEYS = ["ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "POSTGRES_URL", "QDRANT_URL"]
BINARIES = ["freqtrade", "docker"]
URLS = {
    "Prefect": os.getenv("PREFECT_API_URL", "http://127.0.0.1:4200/api"),
    "n8n": os.getenv("N8N_URL", "http://127.0.0.1:5678"),
}


def check_port(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if host is None:
        return False
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def main() -> int:
    failed = False
    print("Environment check")
    print("=================")
    for binary in BINARIES:
        path = shutil.which(binary) or _venv_binary(binary)
        print(f"{binary}: {path or 'missing'}")
        failed = failed or path is None

    for key in REQUIRED_KEYS:
        ok = bool(os.getenv(key))
        print(f"{key}: {'set' if ok else 'missing'}")
        failed = failed or not ok

    for key in OPTIONAL_KEYS:
        print(f"{key}: {'set' if os.getenv(key) else 'missing'}")

    for name, url in URLS.items():
        print(f"{name} reachable at {url}: {'yes' if check_port(url) else 'no'}")

    return 1 if failed else 0


def _venv_binary(binary: str) -> str | None:
    candidate = Path(sys.executable).parent / binary
    return str(candidate) if candidate.exists() else None


if __name__ == "__main__":
    raise SystemExit(main())
