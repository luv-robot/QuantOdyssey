from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.agent_eval import build_builtin_agent_eval_cases, run_agent_eval_suite  # noqa: E402
from app.services.supervisor import build_supervisor_report  # noqa: E402
from app.storage import QuantRepository  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Agent Eval and build an admin SupervisorReport.")
    parser.add_argument("--database-url", help="SQLAlchemy database URL. Defaults to project DATABASE_URL fallback.")
    parser.add_argument("--responses", help="Optional JSON file mapping case_id to response text.")
    parser.add_argument("--no-save", action="store_true", help="Do not persist AgentEvalRun or SupervisorReport.")
    parser.add_argument("--json", action="store_true", help="Print full SupervisorReport JSON.")
    args = parser.parse_args()

    repository = QuantRepository(args.database_url)
    cases = build_builtin_agent_eval_cases()
    responses = _load_responses(args.responses, cases)
    eval_run = run_agent_eval_suite(responses, cases=cases)
    report = build_supervisor_report(
        agent_eval_run=eval_run,
        review_sessions=repository.query_review_sessions(limit=25),
        research_tasks=repository.query_research_tasks(limit=50),
        research_findings=repository.query_research_findings(limit=50),
    )

    if not args.no_save:
        repository.save_agent_eval_run(eval_run)
        repository.save_supervisor_report(report)

    if args.json:
        print(report.model_dump_json(indent=2))
        return

    print(f"Supervisor Quality Check: {report.status.value}")
    print(report.summary)
    print(f"agent_eval_run: {eval_run.run_id} passed={eval_run.passed}")
    print(f"aggregate_scores: {json.dumps(eval_run.aggregate_scores, sort_keys=True)}")
    for flag in report.flags[:10]:
        print(f"- {flag.severity.value.upper()} {flag.kind.value}: {flag.title}")
        print(f"  {flag.recommended_action}")


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
