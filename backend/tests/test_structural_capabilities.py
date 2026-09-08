"""Compiler eligibility follows interrupted supports without rewriting physical feasibility."""
from types import SimpleNamespace

import pytest

from backend.app.archetypes import CarveRefusal
from backend.app.briefs import brief_for
from backend.app.typology import kit_for
from backend.app.compiler_v3 import _carve_and_allocate
from backend.app.program_massing import datums_for, lattice_for
from backend.app.program_volumes import compile_program_volume_candidate, organize_program_volumes
from backend.app.selection import select_project
from backend.app.tectonics import SYSTEM_BUILDABILITY
from backend.app.transfer_structure import required_structural_capabilities
from backend.tests.test_program_volume_circulation import theatre_score


@pytest.fixture(scope='module')
def theatre():
    score = theatre_score('couperin')
    volumes = organize_program_volumes(score, 'theater', grammar_id='PVG-TERRACED-WEAVE')
    massing = volumes.to_program_massing()
    datums = datums_for(massing, score)
    lattice = lattice_for(massing, datums)
    allocation, carve = _carve_and_allocate(
        lattice, datums, 'theater', brief_for('theater', storeys=len(lattice.occupied)))
    assert not isinstance(carve, CarveRefusal)
    return score, datums, lattice, allocation, carve


def test_transfer_requirement_comes_from_actual_interior_support_nodes():
    carve = SimpleNamespace(house=(0, 0, 12, 10), stage=(12, 0, 18, 10), clear_house_m=7)
    empty = SimpleNamespace(x_lines=[0, 18], y_lines=[0, 10])
    interior = SimpleNamespace(x_lines=[0, 6, 18], y_lines=[0, 5, 10])
    assert required_structural_capabilities(interior, None) == ()
    assert required_structural_capabilities(empty, carve) == ()
    assert required_structural_capabilities(interior, carve) == ('theatre_gravity_transfer',)


def test_transfer_selection_keeps_physical_domain_and_music_preference_visible(theatre):
    score, datums, lattice, allocation, carve = theatre
    required = required_structural_capabilities(lattice, carve)
    assert required == ('theatre_gravity_transfer',)
    arguments = dict(program_id=kit_for('theater').program_id, typology='theater')
    raw, original_domain = select_project(score, datums, lattice, allocation, **arguments)
    selected, domain = select_project(score, datums, lattice, allocation,
                                      required_capabilities=required, **arguments)
    assert domain.model_dump() == original_domain.model_dump()
    assert raw.preferred_system_id == 'STR-SYS-GLULAM-POST-BEAM'
    assert any(option.system_id == raw.preferred_system_id for option in domain.feasible)
    assert selected.system_id == 'STR-SYS-STEEL-FRAME'
    assert selected.grammar_id == raw.preferred_grammar_id
    assert selected.preferred_system_id == raw.preferred_system_id
    assert selected.overruled_by_screen
    assert 'compiler_v3 capability' in selected.overrule_reason
    assert selected.compiler_capability_exclusions[raw.preferred_system_id] == list(required)
    assert all(set(required) <= set(SYSTEM_BUILDABILITY[option.system_id].compiler_capabilities)
               for option in selected.ranked_options)


def test_incapable_theatre_pin_is_refused_before_emission(monkeypatch):
    def cannot_emit(*_args, **_kwargs):
        pytest.fail('Incapable pinned system reached structural emission')
    monkeypatch.setattr('backend.app.compiler_v3._run_sizing', cannot_emit)
    with pytest.raises(ValueError, match='Pinned structural system.*theatre_gravity_transfer'):
        compile_program_volume_candidate(
            theatre_score('couperin'), typology='theater',
            structural_system_id='STR-SYS-GLULAM-POST-BEAM')


def test_non_theatre_retains_glulam_choice():
    score = theatre_score('couperin')
    # Isolate compiler eligibility on a four-storey non-theatre that also survives
    # the existing physical storey-count limit for the timber system.
    score.dimensions = [dimension.model_copy(update={'value': 0.0})
                        if dimension.id == 'tempo_of_change' else dimension
                        for dimension in score.dimensions]
    volumes = organize_program_volumes(score, 'museum')
    massing = volumes.to_program_massing()
    datums = datums_for(massing, score)
    lattice = lattice_for(massing, datums)
    allocation, carve = _carve_and_allocate(
        lattice, datums, 'museum', brief_for('museum', storeys=len(lattice.occupied)))
    required = required_structural_capabilities(lattice, carve)
    assert required == ()
    selected, _domain = select_project(score, datums, lattice, allocation,
                                       program_id=kit_for('museum').program_id,
                                       required_capabilities=required)
    assert selected.system_id == 'STR-SYS-GLULAM-POST-BEAM'
    assert selected.compiler_capability_exclusions == {}


@pytest.mark.parametrize('track', ['couperin', 'funky'])
def test_selected_theatre_hall_and_transfer_close_without_changing_volume_depth(track):
    from backend.app.compiler_v3 import (
        _Builder, _frame_the_volumes, core_anchors, _run_sizing, _emit_structure)
    from backend.app.hall_enclosure import emit_hall
    from backend.app.physical_geometry import physical_projection
    from backend.app.tectonics import FRAME_TECTONICS
    from shapely.geometry import Polygon
    score = theatre_score(track)
    volumes = organize_program_volumes(score, 'theater', grammar_id='PVG-TERRACED-WEAVE')
    massing = volumes.to_program_massing()
    datums = datums_for(massing, score)
    lattice = lattice_for(massing, datums)
    allocation, carve = _carve_and_allocate(
        lattice, datums, 'theater', brief_for('theater', storeys=len(lattice.occupied)))
    _frame_the_volumes(lattice, core_anchors(lattice, datums), datums)
    before = lattice.model_dump()
    frame = FRAME_TECTONICS['FRM-STEEL']
    occupancy, sizing = _run_sizing(datums, lattice, allocation, frame)
    builder = _Builder(datums, lattice)
    _emit_structure(builder, sizing, frame, occupancy, carve=carve)
    emit_hall(builder)
    report = builder.transfer_structure
    assert report.status == 'review_required', (
        report.findings, [(f.id, f.findings) for f in report.frames])
    assert not report.hall_enclosure.findings
    assert report.frames and all(f.activated for f in report.frames)
    assert all(f.total_deflection_mm <= f.span_m * 1000 / 240 for f in report.frames)
    assert all(f.live_deflection_mm <= f.span_m * 1000 / 360 for f in report.frames)
    # Support registration is additive; it may not move any pre-existing datum,
    # volume, core, or regular World XY axis.
    assert lattice.model_dump(exclude={'hall_support_grid'}) == before
    assert lattice.hall_support_grid is not None
    roof = builder.hall_geometry.missing
    from backend.app.hall_stations import hall_axes
    for axis, lines in enumerate(hall_axes(builder)):
        moment = sum(lines[key[axis]] * value[1]
                     for key, value in builder.hall_reactions.items())
        expected = report.hall_enclosure.roof_live_kn * (
            roof.centroid.x if axis == 0 else roof.centroid.y)
        assert moment == pytest.approx(expected, abs=1e-7)
    levels = {level.id: level for level in volumes.levels}
    regions = {union.level_id: Polygon(union.boundary, union.voids)
               for union in volumes.level_unions}
    hall_ids = set(report.hall_enclosure.framing_ids)
    measured = 0
    for group in builder.groups.values():
        for instance in group.instances:
            if (group.subsystem not in {'transfer_frame', 'transfer_restraints'}
                    and group.kind != 'transfer_post' and instance.id not in hall_ids):
                continue
            projection = physical_projection(instance.geometry, {
                instance.geometry.profile: builder.profiles[instance.geometry.profile]})
            owner = levels[instance.level_id]
            # The cap's storey is the host. A deep chord can extend into the
            # preceding authored airspace; every vertically touched union must
            # contain its full physical footprint, not just that host's outline.
            assert min(level.z_base for level in levels.values()) - 1e-5 <= projection.z_bottom
            assert projection.z_top <= owner.z_top + 1e-5
            touched = [level for level in levels.values()
                       if min(level.z_top, projection.z_top)
                       - max(level.z_base, projection.z_bottom) > 1e-5]
            assert touched
            assert all(regions[level.id].buffer(1e-5, join_style=2).covers(projection.footprint)
                       for level in touched)
            measured += 1
    assert measured > 400


@pytest.mark.parametrize('track', ['couperin', 'funky'])
@pytest.mark.parametrize('grammar', ['PVG-STACKED-BANDS', 'PVG-TERRACED-WEAVE', 'PVG-SPLIT-BRIDGE'])
def test_theatre_transfer_has_inboard_registered_boundary_piers(track, grammar):
    from shapely.geometry import Point, Polygon
    from backend.app.compiler_v3 import _frame_the_volumes, core_anchors
    score = theatre_score(track)
    volumes = organize_program_volumes(score, 'theater', grammar_id=grammar)
    massing = volumes.to_program_massing()
    datums = datums_for(massing, score)
    lattice = lattice_for(massing, datums)
    allocation, carve = _carve_and_allocate(
        lattice, datums, 'theater', brief_for('theater', storeys=len(lattice.occupied)))
    assert not isinstance(carve, CarveRefusal)
    _frame_the_volumes(lattice, core_anchors(lattice, datums), datums)
    y0, y1 = min(carve.house[1], carve.stage[1]), max(carve.house[3], carve.stage[3])
    south = [y for y in lattice.y_lines if y <= y0 + 0.002]
    north = [y for y in lattice.y_lines if y >= y1 - 0.002]
    assert south and north
    # A ground-floor location must have positive material around the support;
    # merely registering a line outside the Program Volume is insufficient.
    base = lattice.occupied[0]
    floor = Polygon([(p.x, p.y) for p in base.plate],
                    holes=[[(p.x, p.y) for p in ring] for ring in base.voids])
    xs = [x for x in lattice.x_lines if carve.house[0] + .3 < x < carve.stage[2] - .3]
    assert xs
    assert all(floor.contains(Point(x, y)) for x in xs for y in (max(south), min(north)))
    # Full-brief fit is established for the two selected terraced candidates.
    # The other grammatical pins test the support envelope only; their already
    # unresolved rooms remain visible in allocation and are not promoted here.
    if grammar == 'PVG-TERRACED-WEAVE':
        assert allocation.fits
