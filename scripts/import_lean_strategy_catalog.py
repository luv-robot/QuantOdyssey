import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.catalog import build_lean_strategy_catalog  # noqa: E402
from app.services.catalog.lean import LEAN_REPO_URL  # noqa: E402
from app.storage import QuantRepository  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import QuantConnect Lean algorithm metadata.")
    parser.add_argument("--lean-path", type=Path, help="Existing local Lean checkout.")
    parser.add_argument("--clone-url", default=LEAN_REPO_URL)
    parser.add_argument("--clone-dir", type=Path, default=Path("/tmp/QuantConnect-Lean"))
    parser.add_argument("--refresh-clone", action="store_true")
    parser.add_argument("--max-files", type=int)
    parser.add_argument("--exclude-regression", action="store_true")
    parser.add_argument("--language", choices=["python", "csharp"])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--save-to-db", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    lean_path = args.lean_path or _ensure_clone(args.clone_url, args.clone_dir, args.refresh_clone)
    report, items = build_lean_strategy_catalog(
        lean_path,
        repo_url=args.clone_url,
        max_files=args.max_files,
        include_regression=not args.exclude_regression,
        language=args.language,
    )
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
            repository.save_strategy_catalog_item(item)
        repository.save_strategy_catalog_report(report)
    print(json.dumps(report.model_dump(mode="json"), indent=2))
    return 0


def _ensure_clone(clone_url: str, clone_dir: Path, refresh: bool) -> Path:
    if refresh and clone_dir.exists():
        shutil.rmtree(clone_dir)
    if not clone_dir.exists():
        clone_dir.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(clone_dir)],
            check=True,
        )
    return clone_dir


if __name__ == "__main__":
    raise SystemExit(main())
