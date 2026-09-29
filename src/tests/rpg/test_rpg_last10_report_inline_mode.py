from __future__ import annotations


def test_last10_report_job_is_registered_by_the_rpg_feature() -> None:
    from app.jobs.handlers import registry_from_features
    from app.jobs.models import ResourceClass
    from app.runtime.feature_catalog import load_feature

    registry = registry_from_features((load_feature("rpg"),))
    report = registry.require("rpg.report.last10")

    assert report.resource_class == ResourceClass.CPU
    assert "rpg.report.last10" in registry.types()
