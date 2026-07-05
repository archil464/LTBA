from benchmarks import benchmark_v4
from benchmarks import use_case_pack_v1


def test_benchmark_smoke_runs_quickly():
    class NS:
        smoke = True
        reproduce_results = False
        components = "all"
        repeats = 1
        sizes = ""
        include_trials = False

    report = benchmark_v4.run(NS())
    assert "rows" in report
    assert len(report["rows"]) > 0


def test_benchmark_repeated_trials_include_aggregates_and_trial_rows():
    class NS:
        smoke = True
        reproduce_results = False
        components = "LTBA-1"
        repeats = 3
        sizes = "1,2"
        include_trials = True

    report = benchmark_v4.run(NS())

    assert report["repeats"] == 3
    assert report["sizes"] == [1, 2]
    assert "environment" in report
    assert len(report["rows"]) == 2
    assert "trial_rows" in report
    assert len(report["trial_rows"]) == 6

    first = report["rows"][0]
    assert first["trials"] == 3
    assert "ltba_build_time_mean" in first
    assert "ltba_build_time_min" in first
    assert "ltba_build_time_max" in first


def test_use_case_pack_smoke_reports_comparisons():
    class NS:
        smoke = True
        repeats = 2
        scenarios = "all"
        reproduce_results = False

    report = use_case_pack_v1.run(NS())

    assert report["pack"] == "LTBA Use Case Pack v1"
    assert report["repeats"] == 2
    assert len(report["scenarios"]) == 2
    assert len(report["rows"]) == 6
    assert len(report["scenario_winners"]) == 2

    backends = {row["backend"] for row in report["rows"]}
    assert "ltba" in backends
    assert "explicit" in backends
    assert "bdd" in backends
