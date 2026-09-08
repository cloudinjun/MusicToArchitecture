from types import SimpleNamespace

import pytest

from backend.app.geometry import BoxGeometry, MemberGeometry, ProfileSpec, v3
from backend.app.spatial_rules import SpatialIndex, rule_walking_surfaces_meet_flush


def model(step=0.0, rotation=False):
    # Same emitted four-station sweep as the compact arrival, with level end pads.
    def point(x, y, z):
        return v3(-y, x, z) if rotation else v3(x, y, z)
    ramp = MemberGeometry(path=[point(0, 0, -.12), point(0, 1, -.12),
                                point(0, 5, .18), point(0, 6, .18)], profile='R')
    landing = BoxGeometry(center=point(0, .3, -.12 + step),
                          size=v3(.6, 1, .24) if rotation else v3(1, .6, .24))
    def group(kind, geometry):
        return SimpleNamespace(kind=kind, subsystem='ramps', semantic_layer='circulation',
                               instances=[SimpleNamespace(id=kind, level_id='L01', geometry=geometry)])
    return SimpleNamespace(element_groups=[group('ramp', ramp), group('ramp_landing', landing)],
                           profiles={'R': ProfileSpec(id='R', shape='rectangle', width_m=1, depth_m=.24)})


@pytest.mark.parametrize('rotation', [False, True])
def test_low_landing_reads_local_ramp_height(rotation):
    assert not rule_walking_surfaces_meet_flush(SpatialIndex(model(rotation=rotation)))


@pytest.mark.parametrize('rotation', [False, True])
def test_real_step_is_still_reported(rotation):
    findings = rule_walking_surfaces_meet_flush(SpatialIndex(model(.12, rotation)))
    assert len(findings) == 1
    # Averaged sweep tangents tilt the end pad by a fraction of a millimetre.
    assert findings[0].measure == pytest.approx(.12, abs=.001)
