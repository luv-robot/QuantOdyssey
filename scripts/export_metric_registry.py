#!/usr/bin/env python
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.metrics import performance_metric_registry  # noqa: E402


def main() -> int:
    records = [item.to_record() for item in performance_metric_registry()]
    print(json.dumps({"metrics": records}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
