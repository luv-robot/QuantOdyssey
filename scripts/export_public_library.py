import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models import PublicArtifactStatus, PublicArtifactVisibility  # noqa: E402
from app.storage import QuantRepository  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Export redacted public thesis and strategy cards.")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite+pysqlite:///market_data.sqlite3"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--include-unlisted", action="store_true")
    args = parser.parse_args()

    repository = QuantRepository(args.database_url)
    visibilities = [PublicArtifactVisibility.PUBLIC.value]
    if args.include_unlisted:
        visibilities.append(PublicArtifactVisibility.UNLISTED.value)

    theses = []
    strategies = []
    for visibility in visibilities:
        theses.extend(
            repository.query_public_thesis_cards(
                visibility=visibility,
                status=PublicArtifactStatus.PUBLISHED.value,
                limit=500,
            )
        )
        strategies.extend(
            repository.query_public_strategy_cards(
                visibility=visibility,
                status=PublicArtifactStatus.PUBLISHED.value,
                limit=500,
            )
        )
    payload = {
        "version": "public_library_v0.1",
        "theses": [item.model_dump(mode="json") for item in theses],
        "strategies": [item.model_dump(mode="json") for item in strategies],
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.output is None:
        print(text)
    else:
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"Exported public library to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
