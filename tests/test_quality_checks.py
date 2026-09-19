"""Tests des contrôles de qualité.

On vérifie ici la structure des contrôles, sans base de données : que chaque
contrôle expose bien une colonne `violations`, que les familles attendues
sont couvertes, et que la verdict `passed` se comporte correctement. Les
contrôles eux-mêmes sont exécutés contre PostgreSQL par le pipeline.
"""

from __future__ import annotations

import re

from vienna_vibe.quality import Check, CheckResult, build_checks

CHECKS = build_checks(freshness_max_age_hours=3)


def test_every_check_selects_a_violations_column() -> None:
    """Le contrat d'un contrôle : renvoyer une colonne nommée violations."""
    for check in CHECKS:
        assert re.search(r"\bAS\s+violations\b", check.sql, re.IGNORECASE), check.name


def test_all_families_are_covered() -> None:
    families = {check.family for check in CHECKS}

    assert families == {
        "fraîcheur",
        "unicité",
        "complétude",
        "plages",
        "intégrité",
        "volumétrie",
    }


def test_check_names_are_unique() -> None:
    names = [check.name for check in CHECKS]

    assert len(names) == len(set(names))


def test_every_check_has_a_description() -> None:
    for check in CHECKS:
        assert check.description.strip(), check.name


def test_freshness_threshold_is_injected() -> None:
    freshness = next(c for c in CHECKS if c.name == "weather_freshness")

    assert "INTERVAL '3 hours'" in freshness.sql


def test_result_passes_only_at_zero_violations() -> None:
    check = CHECKS[0]

    assert CheckResult(check=check, violations=0).passed is True
    assert CheckResult(check=check, violations=1).passed is False
    assert CheckResult(check=check, violations=999).passed is False


def test_volume_anomaly_tolerates_short_history() -> None:
    """Un projet qui démarre n'a pas d'historique : le contrôle ne doit pas
    échouer les premiers jours, sinon il crie au loup en permanence."""
    volume = next(c for c in CHECKS if c.name == "weather_volume_anomaly")

    assert "< 24 THEN 0" in volume.sql


def test_checks_are_immutable() -> None:
    check = Check(name="x", family="plages", sql="SELECT 0 AS violations", description="d")

    try:
        check.name = "y"  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("Un contrôle doit être immuable.")
