import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models import ResearchTaskStatus  # noqa: E402
from app.services.harness import build_thesis_inbox_digest, build_thesis_inbox_items  # noqa: E402
from app.storage import QuantRepository  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Harness-driven Thesis Inbox suggestions.")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite+pysqlite:///market_data.sqlite3"))
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON instead of a text digest.")
    args = parser.parse_args()

    repository = QuantRepository(args.database_url)
    items = build_thesis_inbox_items(
        research_tasks=repository.query_research_tasks(status=ResearchTaskStatus.PROPOSED.value, limit=50),
        findings=repository.query_research_findings(limit=50),
        review_sessions=repository.query_review_sessions(limit=50),
        limit=args.limit,
    )
    if not args.dry_run:
        for item in items:
            repository.save_thesis_inbox_item(item)

    if args.json:
        print(json.dumps([item.model_dump(mode="json") for item in items], indent=2))
    else:
        print(build_thesis_inbox_digest(items))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
