# Cloud Development

This document defines how QuantOdyssey should be developed from Codex Cloud or other cloud
workspaces.

## Goal

Cloud development should make the project independent from a local desktop session while keeping
production data and secrets protected.

Recommended split:

```text
GitHub = source of truth and CI
Codex Cloud = isolated development tasks and PRs
Vultr VPS = persistent runtime and data services
```

Codex Cloud should not be treated as the production server.

## Environment

Use Python 3.11.

Bootstrap:

```bash
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Verify:

```bash
python -m pytest
```

Expected baseline:

```text
87 passed
```

Optional local dashboard dependencies:

```bash
pip install -e ".[dashboard]"
```

Optional orchestration dependencies:

```bash
pip install -e ".[orchestration]"
```

## CI

GitHub Actions runs the minimal test gate:

```text
.github/workflows/ci.yml
```

The CI job uses:

```text
ubuntu-latest
Python 3.11
pip install -e ".[dev]"
python -m pytest
```

CI must pass before deploying to the VPS.

## Branch Rules

Use `codex/*` branches for cloud-agent work.

Examples:

```text
codex/review-session-model
codex/funding-event-baselines
codex/cloud-bootstrap
codex/dashboard-research-ux
```

Avoid direct pushes to `main` unless the user explicitly requests it.

For multi-agent work, assign disjoint ownership:

```text
Research UX Agent: docs, pre-review, ReviewSession, Dashboard UX
Backtest Agent: baseline, EventEpisode, Monte Carlo, validation
Data Agent: market data, funding/OI, imports, quality checks
Ops Agent: CI, deployment, health checks, backups
```

Agents should not edit the same files in parallel unless the work is intentionally coordinated.

## Protected Runtime Data

Do not commit:

```text
.env
caddy/auth.caddy
logs/
schemas/
*.sqlite3
freqtrade_user_data/data/
freqtrade_user_data/backtest_results/
freqtrade_user_data/strategies/*.py
```

Generated strategy files are runtime artifacts. Keep only:

```text
freqtrade_user_data/strategies/.gitkeep
```

## Secrets

Production secrets should stay in the VPS or a managed secret store.

Do not put these in Codex Cloud logs, prompts, commits, or test fixtures:

```text
OPENAI_API_KEY
exchange API keys
database passwords
n8n secrets
Caddy basic auth hashes
Telegram tokens
email credentials
```

Cloud tasks may use placeholder `.env.example` values, but real credentials must be injected by the
runtime environment.

## Deployment Boundary

Codex Cloud develops and tests code. Vultr runs persistent services.

Production deploy should be:

```text
merge to main
CI passes
VPS pulls main
docker compose starts services
health checks pass
backup policy remains intact
```

Do not let development agents directly mutate production databases unless the user explicitly
approves a migration or repair task.

## Current High-Priority Tracks

1. ReviewSession model and dashboard experience.
2. Funding Crowding Fade real L1 validation: OHLCV + funding + OI.
3. EventEpisode aggregation and event-level baselines.
4. Research Maturity Score implementation.
5. Cloud deploy/bootstrap and CI hardening.

## Smoke Commands

Run all tests:

```bash
python -m pytest
```

Run thesis pre-review tests:

```bash
python -m pytest tests/test_thesis_pre_review.py
```

Run human-led pipeline tests:

```bash
python -m pytest tests/test_human_research_pipeline.py
```

