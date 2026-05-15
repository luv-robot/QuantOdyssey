import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.catalog import build_worldquant_style_factor_catalog  # noqa: E402
from app.storage import QuantRepository  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed WorldQuant-style factor formula metadata.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--save-to-db", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report, items = build_worldquant_style_factor_catalog()
    payload = {
        "report": report.model_dump(mode="json"),
        "items": [item.model_dump(mode="json") for item in items],
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if args.save_to_db:
        repository = QuantRepository(os.getenv("DATABASE_URL", "sqlite+pysqlite:///market_data.sqlite3"))
        for item in items:
            repository.save_factor_formula_item(item)
        repository.save_factor_formula_catalog_report(report)
    print(json.dumps(report.model_dump(mode="json"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
