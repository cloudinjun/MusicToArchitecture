"""Sparse broad-phase parity without relaxing the physical joint test."""
import builtins
import random

import pytest

from backend.app.axis import AxisSkeleton, ON_AXIS_M, _point_segment_distance
from backend.app.geometry import v3


@pytest.mark.parametrize('scale', [.01, 1., 100.])
def test_sparse_t_joints_equal_exhaustive_endpoint_measurement(scale):
    rng = random.Random(37)
    skeleton = AxisSkeleton()
    for index in range(30):
        a = v3(*(scale * rng.uniform(-1, 1) for _ in range(3)))
        b = v3(*(scale * rng.uniform(-1, 1) for _ in range(3)))
        skeleton.segment(f'DIAG-{index}', [a, b], 'brace')
        # One true T-joint and one close miss, across positive/negative buckets.
        for offset in (0., ON_AXIS_M * 3):
            p = v3((a.x+b.x)/2, (a.y+b.y)/2, (a.z+b.z)/2+offset)
            skeleton.segment(f'T-{index}-{offset}', [p, v3(p.x+scale, p.y, p.z)], 'beam')
    free = skeleton.node(v3(0, 0, 0))  # Unowned points never create T-joints.
    endpoints = {node for s in skeleton.segments.values() for node in (s.start, s.end)}
    expected = {
        s.id: {node for node in endpoints if _point_segment_distance(
            skeleton.point(node), skeleton.point(s.start), skeleton.point(s.end)) <= ON_AXIS_M}
        for s in skeleton.segments.values()}
    skeleton.finalise()
    assert {s.id: s.nodes for s in skeleton.segments.values()} == expected
    if free not in endpoints:
        assert all(free not in s.nodes for s in skeleton.segments.values())


def test_long_spatial_diagonal_does_not_enumerate_empty_centimetre_cubes(monkeypatch):
    skeleton = AxisSkeleton()
    skeleton.segment('DIAG', [v3(-30, -30, -30), v3(30, 30, 30)], 'brace')
    skeleton.segment('JOINT', [v3(0, 0, 0), v3(5, 0, 0)], 'beam')

    def bounded_range(*args):
        result = builtins.range(*args)
        assert len(result) <= 64, 'Dense spatial extent enumeration returned'
        return result

    monkeypatch.setattr('backend.app.axis.range', bounded_range, raising=False)
    skeleton.finalise()
    assert skeleton.connections()['DIAG'] == {'JOINT'}
