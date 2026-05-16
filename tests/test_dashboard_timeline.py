from scripts.dashboard_streamlit import _build_research_timeline


def test_dashboard_timeline_scopes_harness_findings_and_validation_reports() -> None:
    items = _build_research_timeline(
        findings=[
            {
                "finding_id": "finding_regime",
                "thesis_id": "thesis_a",
                "finding_type": "regime_bucket_test",
                "severity": "medium",
                "summary": "Regime coverage is uneven.",
                "observations": ["trend bucket dominates"],
                "created_at": "2026-05-15T10:00:00",
                "evidence_refs": ["research_task:task_regime"],
            },
            {
                "finding_id": "finding_other",
                "thesis_id": "thesis_b",
                "finding_type": "baseline_test",
                "severity": "low",
                "summary": "Other thesis finding.",
                "created_at": "2026-05-15T11:00:00",
            },
        ],
        walk_forward_reports=[
            {
                "report_id": "wf_a",
                "strategy_family": "failed_breakout_punishment",
                "source_universe_report_id": "universe_a",
                "passed": False,
                "pass_rate": 0.111,
                "completed_windows": 9,
                "passed_windows": 1,
                "min_trades_per_window": 10,
                "findings": ["Completed 9 walk-forward window(s); 1 passed."],
                "created_at": "2026-05-15T12:00:00",
            }
        ],
        family_monte_carlo_reports=[
            {
                "report_id": "mc_family_a",
                "strategy_family": "failed_breakout_punishment",
                "source_universe_report_id": "universe_a",
                "passed": True,
                "probability_of_loss": 0.25,
                "p05_return": -0.05,
                "sampled_trade_count": 80,
                "simulations": 100,
                "findings": ["Bootstrap path risk is acceptable."],
                "created_at": "2026-05-15T09:00:00",
            }
        ],
        strategy_monte_carlo_reports=[
            {
                "report_id": "mc_strategy_a",
                "strategy_id": "strategy_a",
                "source_backtest_id": "backtest_a",
                "probability_of_loss": 0.55,
                "median_return": 0.01,
                "p05_return": -0.12,
                "horizon_trades": 20,
                "created_at": "2026-05-15T13:00:00",
            }
        ],
        orderflow_acceptance_reports=[],
        universe_reports=[
            {
                "report_id": "universe_a",
                "thesis_id": "thesis_a",
                "strategy_family": "failed_breakout_punishment",
            }
        ],
        strategies=[{"strategy_id": "strategy_a", "thesis_id": "thesis_a"}],
        thesis_id="thesis_a",
        strategy_id=None,
        limit=10,
    )

    titles = [item["title"] for item in items]
    assert titles[0] == "Strategy MC · strategy_a"
    assert "Walk-forward · failed_breakout_punishment" in titles
    assert "Family MC · failed_breakout_punishment" in titles
    assert "Finding · Regime Bucket Test" in titles
    assert all("Other thesis finding" not in item["summary"] for item in items)
    assert next(item for item in items if item["title"].startswith("Walk-forward"))["level"] == "warn"
    assert next(item for item in items if item["title"].startswith("Strategy MC"))["level"] == "warn"


def test_dashboard_timeline_filters_to_selected_strategy_when_present() -> None:
    items = _build_research_timeline(
        findings=[],
        walk_forward_reports=[],
        family_monte_carlo_reports=[],
        strategy_monte_carlo_reports=[
            {
                "report_id": "mc_strategy_a",
                "strategy_id": "strategy_a",
                "probability_of_loss": 0.1,
                "median_return": 0.02,
                "p05_return": -0.02,
                "horizon_trades": 20,
                "created_at": "2026-05-15T10:00:00",
            },
            {
                "report_id": "mc_strategy_b",
                "strategy_id": "strategy_b",
                "probability_of_loss": 0.1,
                "median_return": 0.02,
                "p05_return": -0.02,
                "horizon_trades": 20,
                "created_at": "2026-05-15T11:00:00",
            },
        ],
        orderflow_acceptance_reports=[],
        universe_reports=[],
        strategies=[
            {"strategy_id": "strategy_a", "thesis_id": "thesis_a"},
            {"strategy_id": "strategy_b", "thesis_id": "thesis_a"},
        ],
        thesis_id="thesis_a",
        strategy_id="strategy_a",
        limit=10,
    )

    assert [item["title"] for item in items] == ["Strategy MC · strategy_a"]
