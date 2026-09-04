"""The corpus report's endpoint and collision accounting."""

import pytest

from backend.scripts.run_audio_saturation_corpus import (
    _collision_groups, _collision_rate, _distribution, _series,
)


def test_endpoint_accounting_separates_exact_from_near():
    result = _series([0.0, 0.01, 0.5, 0.99, 1.0], 0.02)
    assert result['exact_endpoint_count'] == 2
    assert result['near_endpoint_count'] == 4
    assert result['exact_endpoint_rate'] == pytest.approx(0.4)
    assert result['near_endpoint_rate'] == pytest.approx(0.8)


def test_collision_rate_counts_duplicate_runs_not_pairs():
    groups = _collision_groups([
        ('a', (1, 2)), ('b', (1, 2)), ('c', (1, 2)), ('d', (3, 4))])
    assert groups == [['a', 'b', 'c']]
    assert _collision_rate(groups, 4) == pytest.approx(0.5)


def test_raw_distribution_is_interpolated_and_deterministic():
    result = _distribution([0.0, 10.0, 20.0])
    assert result['p05'] == pytest.approx(1.0)
    assert result['median'] == pytest.approx(10.0)
    assert result['p95'] == pytest.approx(19.0)
