import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.operations import run_health_checks  # noqa: E402


def main() -> int:
    report = run_health_checks()
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.status in {"ok", "warn"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
