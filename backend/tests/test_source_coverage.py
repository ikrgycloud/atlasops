import pytest

from atlasops.investigation import _source_coverage


def test_deployment_run_url_never_counts_as_log_coverage():
    observed_at = "2026-10-26T12:00:00+00:00"
    coverage = _source_coverage(
        [
            {
                "kind": "deployment",
                "observed_at": observed_at,
                "data": {"reference": "https://github.com/example/project/actions/runs/123"},
            }
        ]
    )

    assert coverage["deployments"]["status"] == "available"
    assert coverage["deployments"]["count"] == 1
    assert coverage["logs"]["status"] == "missing"
    assert coverage["logs"]["count"] == 0
    assert coverage["logs"]["latest_observation"] is None


@pytest.mark.parametrize(
    "data",
    [
        {"reference": "https://monitoring.example/alert/123"},
        {"log_references": None},
        {"log_references": []},
        {"log_references": "https://logs.example/record/123"},
        {"log_references": [""]},
        {"log_references": ["   "]},
        {"log_references": [123]},
        {"log_references": ["/var/log/app.log", None]},
    ],
)
def test_generic_links_and_invalid_log_reference_fields_do_not_count(data):
    coverage = _source_coverage(
        [{"kind": "observation", "observed_at": "2026-10-26T12:00:00+00:00", "data": data}]
    )
    assert coverage["logs"]["status"] == "missing"
    assert coverage["logs"]["count"] == 0


def test_explicit_log_evidence_determines_count_and_freshness():
    first = "2026-10-26T12:00:00+00:00"
    latest = "2026-10-26T12:01:00+00:00"
    coverage = _source_coverage(
        [
            {
                "kind": "log_reference",
                "observed_at": first,
                "data": {"reference": "https://logs.example/record/123"},
            },
            {"kind": "observation", "observed_at": latest, "data": {"log_references": ["/var/log/app.log"]}},
            {
                "kind": "deployment",
                "observed_at": "2026-10-26T12:02:00+00:00",
                "data": {"reference": "https://ci.example/run/456"},
            },
        ]
    )

    assert coverage["logs"]["status"] == "available"
    assert coverage["logs"]["count"] == 2
    assert coverage["logs"]["latest_observation"] == latest
