"""Contact work stops at its exact lower bound without changing its verdict."""
import math
from types import SimpleNamespace as NS

import pytest

from backend.app import dependencies as dep
from backend.app.geometry import BoxGeometry, ExtrusionGeometry, MemberGeometry, v2, v3


def record(geometry):
    return NS(instance=NS(geometry=geometry))


def reference_gap(a, b):
    value = min(min(dep._point_to_geometry(p, b) for p in dep._vertices(a)),
                min(dep._point_to_geometry(p, a) for p in dep._vertices(b)))
    slack = sum(dep.MEMBER_SLACK_M for g in (a, b) if isinstance(g, MemberGeometry))
    return max(0.0, value - slack)


@pytest.mark.parametrize('shift', [0.0, 0.2, 5.0])
@pytest.mark.parametrize('kind', ['member', 'box', 'extrusion'])
def test_short_circuit_keeps_bidirectional_contact_measurement(shift, kind):
    slab = ExtrusionGeometry(boundary=[v2(0, 0), v2(8, 0), v2(8, 6), v2(0, 6)],
                             z_base=0, z_top=0.3)
    candidates = {
        'member': MemberGeometry(path=[v3(2, 2, 0.3 + shift), v3(4, 2, 0.3 + shift)], profile='TEST'),
        'box': BoxGeometry(center=v3(2, 2, 0.8 + shift), size=v3(1, 1, 1)),
        'extrusion': ExtrusionGeometry(boundary=[v2(1, 1), v2(3, 1), v2(3, 3), v2(1, 3)],
                                      z_base=0.3 + shift, z_top=1.0 + shift),
    }
    other = candidates[kind]
    expected = reference_gap(slab, other)
    assert dep._contact_gap(record(slab), record(other)) == pytest.approx(expected)
    assert dep._contact_gap(record(other), record(slab)) == pytest.approx(expected)


def test_proven_zero_contact_does_not_scan_every_slab_vertex(monkeypatch):
    slab = ExtrusionGeometry(boundary=[v2(10 * math.cos(t * math.tau / 256),
                                          10 * math.sin(t * math.tau / 256))
                                       for t in range(256)], z_base=0, z_top=0.3)
    member = MemberGeometry(path=[v3(0, 0, 0.3), v3(1, 0, 0.3)], profile='TEST')
    original = dep._point_to_geometry
    calls = []

    def measured(point, geometry):
        calls.append(1)
        return original(point, geometry)

    monkeypatch.setattr(dep, '_point_to_geometry', measured)
    assert dep._contact_gap(record(slab), record(member)) == 0.0
    assert len(calls) == 1
