"""Secondary members need their whole section on supported floor, not one point."""
from copy import deepcopy

import pytest
from shapely.geometry import LineString, Polygon

from backend.app.physical_geometry import physical_projection
from backend.tests.test_world_xy_frame_integration import _frame, _massing


def _elements(builder):
    return {element.id: element for group in builder.groups.values() for element in group.expand()}


@pytest.mark.parametrize('flange_only', [False, True])
def test_joist_crossing_a_small_void_is_refused_without_fabricating_a_free_end(flange_only):
    massing = _massing()
    baseline = _frame(massing=massing)
    before = _elements(baseline)
    target = before['STR-JST-X04-S01-Y01-L01']
    x = target.geometry.path[0].x
    half = baseline.profiles[target.geometry.profile].width_m / 2
    # Between the actual supports at y=4 and y=8, away from the old midpoint test.
    # In the flange case even the complete centreline misses the void.
    x0, x1 = (x+half/2, x+half*1.5) if flange_only else (x-half/2, x+half/2)
    void = [(x0, 5.2), (x1, 5.2), (x1, 5.6), (x0, 5.6)]
    altered = deepcopy(massing)
    altered.levels[1].voids.append(void)
    result = _frame(massing=altered)
    after = _elements(result)
    assert target.id not in after
    assert all(support in after for support in target.supports)
    assert not any(ident.startswith(target.id+'-') for ident in after)
    notes = [note for note in result.world_xy_frame_notes if 'Unresolved floor framing' in note]
    assert len(notes) == 1 and target.id in notes[0]
    assert 'replacement framing and floor-deck spans require design' in notes[0]
    if flange_only:
        axis = LineString([(p.x,p.y) for p in target.geometry.path])
        assert not axis.intersects(Polygon(void))
    assert physical_projection(target.geometry, baseline.profiles).footprint.intersection(
        Polygon(void)).area > 0
    # Supported neighbours retain their section and hosts; the grid is not moved.
    assert result.lattice.x_lines == baseline.lattice.x_lines
    assert result.lattice.y_lines == baseline.lattice.y_lines
    remaining = [e for e in after.values() if e.kind == 'secondary_joist']
    assert remaining
    for element in remaining:
        assert element.geometry.profile == before[element.id].geometry.profile
        assert element.supports == before[element.id].supports
        level = result.lattice.levels[element.lattice_index['level']]
        floor = Polygon([(p.x,p.y) for p in level.plate],
                        holes=[[(p.x,p.y) for p in ring] for ring in level.voids])
        assert floor.buffer(1e-7).covers(physical_projection(
            element.geometry, result.profiles).footprint)
