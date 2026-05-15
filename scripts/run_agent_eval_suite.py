from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.agent_eval import build_builtin_agent_eval_cases, run_agent_eval_suite  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run QuantOdyssey Agent Eval Suite V0.1.")
    parser.add_argument(
        "--responses",
        help="Optional JSON file mapping case_id to agent response text.",
    )
    parser.add_argument("--json", action="store_true", help="Print full JSON instead of a summary.")
    args = parser.parse_args()

    cases = build_builtin_agent_eval_cases()
    responses = _load_responses(args.responses, cases)
    run = run_agent_eval_suite(responses, cases=cases)

    if args.json:
        print(run.model_dump_json(indent=2))
        return

    print(f"Agent Eval Suite: {run.suite_version}")
    print(f"passed: {run.passed}")
    print(f"aggregate_scores: {json.dumps(run.aggregate_scores, sort_keys=True)}")
    for result in run.results:
        status = "PASS" if result.passed else "FAIL"
        print(f"- {status} {result.case_id}: score={result.score}")
        for finding in result.findings:
            print(f"  {finding}")


def _load_responses(path: str | None, cases) -> dict[str, str]:
    if path is None:
        return {
            case.case_id: " ".join([*case.expected_terms, "evidence discipline followed"])
            for case in cases
        }
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return {str(key): str(value) for key, value in payload.items()}


if __name__ == "__main__":
    main()
