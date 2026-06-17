from benchmarks import benchmark_v4


def test_benchmark_smoke_runs_quickly():
    class NS:
        smoke = True
        reproduce_results = False
        components = "all"

    report = benchmark_v4.run(NS())
    assert "rows" in report
    assert len(report["rows"]) > 0
