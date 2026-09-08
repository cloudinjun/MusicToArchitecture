"""A registered roof continues the selected facade without another occupied floor."""
import pytest
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from backend.app.compiler_v3 import _emit_roof
from backend.app.envelope import (
    _roof_interface_surfaces, closure_solid_bearings, emit_envelope,
)
from backend.app.facade_control import (
    canonical_role_for, facade_control_for, facade_band_levels,
    validate_facade_collar,
)
from backend.app.geometry import QuadGeometry
from backend.app.grammar_specs import spec_for
from backend.app.roof import roof_control_for
from backend.app.tectonics import ENVELOPE_TECTONICS
from backend.tests.test_envelope_closure import RECT, builder, elements, ring


def uncovered_roof_perimeter(band, panels, z, collar_depth):
    """Measure elevation coverage, allowing the grammar's recessed glazing."""
    missing = 0.0
    boundary = band.weather_boundary
    for a, end in zip(boundary, boundary[1:] + boundary[:1]):
        dx, dy = end[0] - a[0], end[1] - a[1]
        length = (dx * dx + dy * dy) ** .5
        ux, uy = dx / length, dy / length
        intervals = []
        for panel in panels:
            if not min(p.z for p in panel.corners) <= z <= max(p.z for p in panel.corners):
                continue
            p, q = panel.corners[:2]
            if abs((q.x-p.x)*uy - (q.y-p.y)*ux) > 1e-6:
                continue
            if max(abs((v.x-a[0])*uy - (v.y-a[1])*ux) for v in (p,q)) > collar_depth + 1e-6:
                continue
            values = [(v.x-a[0])*ux + (v.y-a[1])*uy for v in (p,q)]
            lo, hi = max(0., min(values)), min(length, max(values))
            if hi > lo:
                intervals.append(LineString([(lo, 0), (hi, 0)]))
        missing += LineString([(0, 0), (length, 0)]).difference(
            unary_union(intervals).buffer(1e-6)).length
    return missing


@pytest.mark.parametrize('trim_material', ['terracotta', 'steel_dark', 'concrete_light'])
@pytest.mark.parametrize('tectonic_id,grammar_id', [
    ('ENV-DEEP-LATTICE', 'FCD-09-CRITICAL-REGIONALISM'),
    ('ENV-CURTAIN-WALL', 'FCD-01-INTERNATIONAL-STYLE'),
    ('ENV-PUNCHED-WALL', 'FCD-03-BRUTALISM'),
])
@pytest.mark.parametrize('roof_plate', [
    RECT,
    ring([(0, 0), (12, 0), (12, 4), (6, 4), (6, 8), (0, 8)]),
], ids=['setback-rectangle', 'concave-L'])
def test_roof_band_emits_selected_grammar_at_its_own_boundary_and_height(
        trim_material, tectonic_id, grammar_id, roof_plate, monkeypatch):
    larger = ring([(-2, -2), (14, -2), (14, 10), (-2, 10)])
    b = builder([larger, larger, roof_plate])
    b.lattice.program_volume_source_digest = 'roof-band-regression'
    roof = b.lattice.roof
    b.lattice.roof_control = roof_control_for(
        [(p.x, p.y) for p in roof.plate], [], datum_z=roof.z,
        truss_depth_m=b.datums.value('truss_depth_m'))
    source = [level.model_dump() for level in b.lattice.levels]
    env = ENVELOPE_TECTONICS[tectonic_id].model_copy(
        update={'trim_material': trim_material})
    monkeypatch.setitem(ENVELOPE_TECTONICS, env.id, env)
    spec = spec_for(grammar_id)
    control = facade_control_for(b.lattice, b.datums, env, spec)
    b.lattice.facade_control = control
    band = control.level(roof.id)
    assert band.source_boundary == b.lattice.roof_control.boundary
    assert band.z_base == roof.z
    assert band.z_top == b.lattice.roof_control.physical_top_z
    assert not Polygon(band.source_boundary).equals(Polygon([(p.x, p.y) for p in larger]))
    _emit_roof(b)
    lining = [e for e in elements(b) if e.part_role == 'parapet_inner_finish']
    coping = [e for e in elements(b) if e.part_role == 'coping']
    assert lining and coping
    assert all(e.material_profile == env.trim_material for e in lining + coping)
    assert all(e.supports for e in lining + coping)
    assert any(ident.startswith('ENV-ROOF-COPING') for ident, _ in
               _roof_interface_surfaces(b, band.z_top))
    emit_envelope(b, env, spec)
    roof_skin = [e for e in elements(b) if e.level_id == roof.id
                 and canonical_role_for(e) is not None]
    panels = [e.geometry for e in roof_skin if isinstance(e.geometry, QuadGeometry)]
    assert panels
    assert min(p.z for g in panels for p in g.corners) == pytest.approx(band.z_base)
    assert max(p.z for g in panels for p in g.corners) == pytest.approx(band.z_top)
    # Extents alone permit a missing side. Read emitted skin at three heights
    # and require the complete weather perimeter, including the concave corner.
    for fraction in (.2, .5, .8):
        z = band.z_base + fraction * (band.z_top - band.z_base)
        uncovered = uncovered_roof_perimeter(band, panels, z, control.resolved_offset_m)
        assert uncovered < 1e-5, (tectonic_id, fraction, uncovered)
    # Negative control: removing the roof skin must expose the missing perimeter.
    assert uncovered_roof_perimeter(band, [], band.z_base, 0) > 0
    assert not [f for f in validate_facade_collar(control, roof_skin, b.profiles)
                if f.status == 'failed']
    _, failed = closure_solid_bearings(b)
    assert not [ident for ident in failed if roof.id in ident]
    from backend.app.physical_geometry import physical_projection
    for element in elements(b):
        if element.kind != 'external_strut' or not element.id.startswith('ENV-RET-'):
            continue
        extent = physical_projection(element.geometry, b.profiles)
        host_band = control.level(element.level_id)
        if '-BASE-' in element.id:
            assert extent.z_top <= host_band.z_base + 1e-6
        elif element.level_id == roof.id:
            assert extent.z_top <= band.z_top + 1e-6
        else:
            # The lower exposed soffit is the corresponding HEAD panel bottom.
            panels_at_head = [e for e in elements(b)
                              if e.id.startswith(f'ENV-RET-{element.level_id}-HEAD-P')]
            assert extent.z_bottom >= min(e.geometry.z_base for e in panels_at_head) - 1e-6
            assert extent.z_top <= max(e.geometry.z_top for e in panels_at_head) + 1e-6
    assert [level.model_dump() for level in b.lattice.levels] == source


def test_legacy_without_roof_control_keeps_occupied_facade_hosts():
    b = builder()
    b.lattice.program_volume_source_digest = 'legacy-regression'
    env = ENVELOPE_TECTONICS['ENV-DEEP-LATTICE']
    spec = spec_for('FCD-09-CRITICAL-REGIONALISM')
    assert facade_band_levels(b.lattice) == b.lattice.occupied
    control = facade_control_for(b.lattice, b.datums, env, spec)
    assert control.level(b.lattice.roof.id) is None
    emit_envelope(b, env, spec)
    assert not [e for e in elements(b) if e.level_id == b.lattice.roof.id
                and canonical_role_for(e) is not None]
