"""Program Volume circulation intent changes real geometry and constrains cores."""
from __future__ import annotations

import pytest
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from backend.app.assembly_metadata import annotate_program_volume_circulation
from backend.app.compiler_v3 import (
    _Builder, _carve_and_allocate, _core_box, _emit_circulation, _emit_entry_canopy,
    _plan_approach,
    _program_carrier_regions, _resolve_program_circulation, core_anchors,
)
from backend.app.briefs import brief_for
from backend.app.envelope import planned_entrance
from backend.app.facade_control import canonical_role_for
from backend.app.geometry import BoxGeometry, v3
from backend.app.models import ArchitecturalScore, ScoreDimension
from backend.app.geometry_review import _polygon, _z_interval
from backend.app.dependencies import compile_dependency_graph
from backend.app.program_massing import datums_for, lattice_for
from backend.app.program_volume_contracts import covers_registered_footprint, PLAN_IDENTITY_TOLERANCE_M
from backend.app.program_volumes import (
    compile_program_volume_candidate, organize_program_volumes,
)
from backend.tests.test_program_volume_semantics import GRAMMARS, _score


def _chain(grammar):
    score = _score()
    volumes = organize_program_volumes(score, 'museum', grammar_id=grammar)
    massing = volumes.to_program_massing()
    datums = datums_for(massing, score)
    return volumes, datums, lattice_for(massing, datums)


# Frozen measured R2 readings reproduce the two failed theatre arrivals without
# depending on a mutable artifact folder or running audio extraction in a test.
THEATRE_READINGS = {
    'couperin': {
        'interruption': (0.512577841855058, .74),
        'tempo_of_change': (0.4019285929951691, .812),
        'continuity': (0.6354270391664678, .72),
        'repetition': (0.32190383895747965, .78),
        'genre_style': (0.574749687709957, .35),
        'tension_release': (0.08902317639572402, .95),
        'hierarchy': (0.7151248137155294, .8),
        'density': (0.48387507179187017, .9),
        'variation': (0.6967173741276103, .75),
        'polyphony': (0.7272306239050488, .55),
    },
    'funky': {
        'interruption': (0.04085977414718147, .74),
        'tempo_of_change': (0.3094618055555556, .875),
        'continuity': (0.6093536742468401, .72),
        'repetition': (0.7104823281090287, .78),
        'genre_style': (0.5801271825284638, .35),
        'tension_release': (0.18752083605062878, .95),
        'hierarchy': (0.6746612254169826, .8),
        'density': (0.5125757460774214, .9),
        'variation': (0.3189537587321193, .75),
        'polyphony': (0.4990453586920464, .55),
    },
}


def theatre_score(track):
    return ArchitecturalScore(
        score_id=f'entry-regression-{track}', source_audio_sha256='8' * 64,
        dimensions=[ScoreDimension(
            id=key, value=value, confidence=confidence,
            source_feature=f'frozen_r2_{key}', extraction_method='manual',
            architectural_proposal='Frozen measured theatre entry regression.')
                    for key, (value, confidence) in THEATRE_READINGS[track].items()],
        mapping_rules=[])


@pytest.mark.parametrize('track', THEATRE_READINGS)
def test_theatre_arrival_fits_its_carrier_and_reaches_public_circulation(track):
    score = theatre_score(track)
    volumes = organize_program_volumes(score, 'theater', grammar_id='PVG-TERRACED-WEAVE')
    massing = volumes.to_program_massing()
    datums = datums_for(massing, score)
    lattice = lattice_for(massing, datums)
    allocation, carve = _carve_and_allocate(
        lattice, datums, 'theater', brief_for('theater', storeys=len(lattice.occupied)))
    from backend.app.archetypes import TheatreCarve
    assert isinstance(carve, TheatreCarve)
    approach = _plan_approach(lattice, datums)
    assert approach['ramp'] is not None
    assert approach['ramp'].compliance() == []
    intent = lattice.circulation_intent
    carrier = next(volume for volume in volumes.volumes
                   if volume.id == intent.entry_station.source_volume_id)
    assert carrier.role == 'circulation_spine'
    assert carrier.grid_rect[2] - carrier.grid_rect[0] == 3
    assert not any(key.endswith(':PUBLIC-ENTRY')
                   for key in allocation.public_circulation.unresolved)
    entrance = planned_entrance(lattice, datums, approach)
    assert entrance.center == pytest.approx(approach['entry_point'])
    builder = _Builder(datums, lattice)
    _emit_entry_canopy(builder)
    canopy = next(instance.geometry for group in builder.groups.values()
                  for instance in group.instances if instance.id == 'ENV-CAN-ENTRY')
    delta = (canopy.center.x - entrance.center[0], canopy.center.y - entrance.center[1])
    assert sum(delta[i] * entrance.tangent[i] for i in (0, 1)) == pytest.approx(0, abs=1e-5)
    assert sum(delta[i] * entrance.inward[i] for i in (0, 1)) < 0
    assert canopy.center.z - canopy.size.z / 2 >= entrance.floor_z + 2.6 - 1e-5


@pytest.fixture(scope='module')
def stacked_candidate():
    model, _volumes = compile_program_volume_candidate(
        _score(), typology='museum',
        volume_grammar_id='PVG-STACKED-BANDS')
    return model


@pytest.fixture(scope='module')
def library_stacked_kernel():
    score = _score()
    volumes = organize_program_volumes(
        score, 'library', grammar_id='PVG-STACKED-BANDS')
    def assert_owner_meets_remote(space_id):
        owner = next(volume for volume in volumes.volumes
                     if volume.space_ids == [space_id])
        remote = max(
            (volume for volume in volumes.volumes
             if volume.level_id == owner.level_id
             and volume.role == 'circulation_spine'),
            key=lambda volume: volume.grid_rect[0])
        owner_shape = box(*volumes.rect_of(owner))
        remote_shape = box(*volumes.rect_of(remote))
        assert owner_shape.intersection(remote_shape).area <= 1.0e-7
        assert owner_shape.boundary.intersection(remote_shape.boundary).length > 1.0e-7
        return owner

    assert_owner_meets_remote('SP-QUIET')
    assert_owner_meets_remote('SP-SPECIAL')
    assert_owner_meets_remote('SP-PERIODICALS')
    massing = volumes.to_program_massing()
    datums = datums_for(massing, score)
    lattice = lattice_for(massing, datums)
    allocation, carve = _carve_and_allocate(
        lattice, datums, 'library',
        brief_for('library', storeys=len(lattice.occupied)))
    return volumes, datums, lattice, allocation, carve


def _instances(model):
    return {
        instance.id: instance
        for group in model.element_groups
        for instance in group.instances
    }


def _instance_kinds(model):
    return {
        instance.id: group.kind
        for group in model.element_groups
        for instance in group.instances
    }


def test_program_volume_facade_instances_have_controlled_assembly_metadata(
        stacked_candidate):
    control = stacked_candidate.lattice.facade_control
    assert control is not None
    controlled = [
        element for element in stacked_candidate.elements
        if canonical_role_for(element) is not None]
    assert controlled
    assert all(element.assembly_id for element in controlled)
    assert all(element.part_role for element in controlled)
    assert stacked_candidate.spatial.counts['PV-FACADE-COLLAR'] == 0


@pytest.mark.parametrize('grammar', GRAMMARS)
def test_every_core_is_inside_declared_carrier_on_every_served_floor(grammar):
    _volumes, datums, lattice = _chain(grammar)
    anchors = core_anchors(lattice, datums)
    carriers = _program_carrier_regions(lattice)
    cores = [('primary', anchors['primary'], anchors['served'])]
    if anchors['second'] is not None:
        cores.append(('second', anchors['second'], anchors['second_served']))
    cores.extend((f'extra-{index + 1}', point, levels)
                 for index, (point, levels) in enumerate(anchors['extras']))

    assert cores and anchors['primary'] is not None
    for label, point, levels in cores:
        served = {level.id for level in levels if level.kind == 'occupied'}
        footprint = box(*_core_box(
            *point, anchors['width'], anchors['run']))
        assert served, label
        assert served <= set(carriers), label
        assert all(covers_registered_footprint(carriers[level_id],footprint)
                   for level_id in served), label


@pytest.mark.parametrize('shift,expected',[(0.,True),(2e-7,False),(.01,False)])
def test_serialized_core_midpoint_does_not_create_or_hide_carrier_overflow(shift,expected):
    from shapely.affinity import translate
    carrier = box(4.73,11.92,7.77,18.6)
    point = ((4.73+7.77)/2,(11.92+18.6)/2)
    footprint = translate(box(*_core_box(*point,1.2,2.88)),xoff=shift)
    assert PLAN_IDENTITY_TOLERANCE_M == 1e-7
    assert covers_registered_footprint(carrier,footprint) is expected


def test_archetype_and_program_rooms_leave_program_volume_circulation_unclaimed(
        library_stacked_kernel):
    _volumes, _datums, lattice, allocation, carve = library_stacked_kernel
    assert carve is not None and not getattr(carve, 'precluded', None)
    intent = lattice.circulation_intent
    assert intent is not None
    circulation_ids = set(intent.carrier_volume_ids) | set(intent.connector_volume_ids)
    protected = {}
    for region in lattice.program_volume_regions:
        if region.id not in circulation_ids:
            continue
        protected.setdefault(region.level_id, []).append(
            box(*region.resolve_bounds(lattice)))
    protected = {level_id: unary_union(regions)
                 for level_id, regions in protected.items()}

    conflicts = []
    for zone in allocation.zones:
        authority = protected.get(zone.level_id)
        if authority is None:
            continue
        overlap = box(zone.x0, zone.y0, zone.x1, zone.y1).intersection(
            authority).area
        if overlap > 1.0e-7:
            conflicts.append((zone.space_id, zone.level_id, round(overlap, 4)))
    assert conflicts == []


def test_carrier_remains_available_for_a_complete_primary_core_after_allocation(
        library_stacked_kernel):
    _volumes, datums, lattice, _allocation, _carve = library_stacked_kernel
    anchors = core_anchors(lattice, datums)
    assert anchors['primary'] is not None
    served = {level.id for level in anchors['served'] if level.kind == 'occupied'}
    occupied = {level.id for level in lattice.occupied}
    assert served == occupied
    footprint = box(*_core_box(
        *anchors['primary'], anchors['width'], anchors['run']))
    carriers = _program_carrier_regions(lattice)
    assert all(carriers[level_id].covers(footprint) for level_id in served)


def test_archetype_floor_removals_remain_valid_plan_readings(
        library_stacked_kernel):
    _volumes, _datums, lattice, _allocation, _carve = library_stacked_kernel
    invalid = []
    for level in lattice.occupied:
        floor = Polygon(
            [(point.x, point.y) for point in level.plate],
            holes=[[(point.x, point.y) for point in ring]
                   for ring in level.voids])
        if floor.is_empty or not floor.is_valid or floor.area <= 0.0:
            invalid.append(level.id)
    assert invalid == []


@pytest.mark.parametrize('grammar', GRAMMARS)
def test_core_authority_survives_structural_grid_reframing(grammar):
    _volumes, datums, lattice = _chain(grammar)
    first = core_anchors(lattice, datums)
    second = core_anchors(lattice, datums)
    assert first['primary'] == second['primary']
    assert lattice.program_volume_x_lines
    assert lattice.program_volume_y_lines


def test_three_volume_grammars_emit_three_public_stair_signatures():
    signatures = {}
    for grammar in GRAMMARS:
        _volumes, datums, lattice = _chain(grammar)
        builder = _Builder(datums, lattice)
        _emit_circulation(builder)
        tread_ids = sorted(
            instance.id
            for group in builder.groups.values() if group.kind == 'stair_tread'
            for instance in group.instances
            if instance.id.startswith(('CIR-TRD-F01', 'CIR-TRD-TC', 'CIR-TRD-BS')))
        signatures[grammar] = (
            builder.approach['public_stair_family'],
            tuple(identifier.split('-')[2][:2] for identifier in tread_ids),
            len(tread_ids),
        )
    assert len(set(signatures.values())) == len(GRAMMARS)


def test_terraced_cascade_public_stair_emits_explicit_support_contract():
    _volumes, datums, lattice = _chain('PVG-TERRACED-WEAVE')
    builder = _Builder(datums, lattice)
    _emit_circulation(builder)
    instances = {
        instance.id: (group.kind, instance)
        for group in builder.groups.values()
        for instance in group.instances
    }

    treads = [instance for identifier, (kind, instance) in instances.items()
              if identifier.startswith('CIR-TRD-TC')]
    assert treads
    assert all(instance.supports == [
        f'CIR-STG-{instance.id.split("CIR-TRD-")[1].split("-S")[0]}-L',
        f'CIR-STG-{instance.id.split("CIR-TRD-")[1].split("-S")[0]}-R',
    ] for instance in treads)

    landings = [instance for identifier, (kind, instance) in instances.items()
                if identifier.startswith('CIR-PUBLIC-TC-LND-')]
    assert len(landings) == 2
    assert all(len(instance.supports) == 2 for instance in landings)
    assert all(all(host in instances for host in instance.supports)
               for instance in landings)

    rails = [instance for identifier, (kind, instance) in instances.items()
             if identifier.startswith('CIR-RAL-TC')]
    assert rails
    assert all(instance.supports for instance in rails)
    assert all(all(host in instances for host in instance.supports)
               for instance in rails)


def test_terraced_cascade_explicit_support_id_cannot_fall_back_to_tc_name_guess():
    _volumes, datums, lattice = _chain('PVG-TERRACED-WEAVE')
    builder = _Builder(datums, lattice)
    _emit_circulation(builder)
    groups = [group.model_copy(deep=True) for group in builder.groups.values()]
    tread = next(instance for group in groups for instance in group.instances
                 if instance.id.startswith('CIR-TRD-TC'))
    tread.supports[:] = ['CIR-STG-TC00-MISSING', 'CIR-STG-TC00-ALSO-MISSING']
    report = compile_dependency_graph(groups)
    coverage = next(check for check in report.checks
                    if check.id == 'DEP-REQUIRED-COVERAGE')
    minimum = next(check for check in report.checks
                   if check.id == 'DEP-MINIMUM-SUPPORTS')
    assert tread.id in coverage.affected_ids
    assert tread.id in minimum.affected_ids


def test_rotated_program_volume_ramp_retains_ada_geometry():
    _volumes, datums, lattice = _chain('PVG-STACKED-BANDS')
    approach = _plan_approach(lattice, datums)
    ramp = approach['ramp']
    assert ramp is not None
    assert ramp.compliance() == []
    # This entry edge is vertical, so a real transformed run travels in world Y.
    assert any(abs(run.end_y - run.start_y) > 1.0 for run in ramp.runs)
    assert all(run.length > 0.0 for run in ramp.runs)


def test_resolved_plan_keeps_checked_geometry_separate_from_route_continuity():
    _volumes, datums, lattice = _chain('PVG-STACKED-BANDS')
    builder = _Builder(datums, lattice)
    _emit_circulation(builder)
    plan = _resolve_program_circulation(builder)

    assert plan is not None
    by_id = {finding.id: finding for finding in plan.findings}
    assert by_id['PV-CIRC-CORE-CARRIER'].status == 'passed'
    assert by_id['PV-CIRC-PUBLIC-STAIR'].status == 'passed'
    assert by_id['PV-CIRC-ACCESSIBLE-APPROACH'].status == 'passed'
    assert by_id['PV-CIRC-PORTAL-ATTACHMENT'].status == 'unevaluated'
    assert by_id['PV-CIRC-INTERIOR-CONTINUATION'].status == 'unevaluated'
    assert plan.status == 'unevaluated'
    assert plan.public_stair_ids
    assert plan.exterior_exception_ids


@pytest.mark.parametrize('grammar', ['PVG-TERRACED-WEAVE', 'PVG-SPLIT-BRIDGE'])
def test_reported_fallback_access_stair_is_an_explicit_exterior_exception(grammar):
    _volumes, datums, lattice = _chain(grammar)
    lattice.circulation_intent.approach_depth_m = 1.0
    builder = _Builder(datums, lattice)
    _emit_circulation(builder)
    plan = _resolve_program_circulation(builder)

    fallback_ids = {
        identifier for identifier in builder.element_ids
        if identifier.startswith((
            'CIR-TRD-R01', 'CIR-STG-R01', 'CIR-RAL-R01', 'CIR-LND-ACCESS'))
    }
    assert fallback_ids
    assert fallback_ids <= set(plan.exterior_exception_ids)


def test_program_volume_circulation_parts_are_detail_traceable():
    _volumes, datums, lattice = _chain('PVG-TERRACED-WEAVE')
    builder = _Builder(datums, lattice)
    _emit_circulation(builder)
    annotated = annotate_program_volume_circulation(builder)
    groups = [group for group in builder.groups.values()
              if group.semantic_layer == 'circulation']
    instances = [instance for group in groups for instance in group.instances]

    assert annotated == len(instances) > 0
    assert all(instance.assembly_id and instance.part_role
               for instance in instances)
    assert all(instance.supports
               or 'MTA-CIRCULATION-INTERFACE-UNRESOLVED' in group.rule_refs
               for group in groups for instance in group.instances)
    assert all(group.datum_refs for group in groups)
    assert all('MTA-CIRCULATION-ASSEMBLY-001' in group.rule_refs
               for group in groups)


def test_program_volume_stage_access_has_its_own_detail_assembly():
    _volumes, datums, lattice = _chain('PVG-TERRACED-WEAVE')
    builder = _Builder(datums, lattice)
    builder.add(
        'PRG-STG-ACCESS-L01-STEP00', 'stair_tread', 'circulation',
        'stage_access', BoxGeometry(center=v3(0.5, 0.5, 0.1),
                                    size=v3(1, 1, 0.2)),
        'timber', level_id='L01')
    builder.add(
        'PRG-STG-ACCESS-L01-TOP', 'stage_platform', 'circulation',
        'stage_access', BoxGeometry(center=v3(1.5, 0.5, 0.45),
                                    size=v3(1, 1, 0.9)),
        'timber', level_id='L01')

    annotate_program_volume_circulation(builder)
    instances = [instance for group in builder.groups.values()
                 for instance in group.instances]
    assert {instance.assembly_id for instance in instances} == {
        'ASM-PV-STAGE-ACCESS-L01'}
    assert {instance.part_role for instance in instances} == {
        'tread', 'stage_arrival_platform'}


def test_completed_candidate_closes_the_real_program_volume_route(stacked_candidate):
    plan = stacked_candidate.circulation_plan
    assert plan is not None
    by_id = {finding.id: finding for finding in plan.findings}
    assert by_id['PV-CIRC-PORTAL-ATTACHMENT'].status == 'passed'
    assert by_id['PV-CIRC-INTERIOR-CONTINUATION'].status == 'passed'

    portal = next(
        candidate for candidate in stacked_candidate.portals.portals
        if candidate.id == plan.attachment_portal_id)
    assert portal.kind == 'entrance'
    assert portal.passable


def test_core_door_threshold_is_emitted_floor_through_the_wall(stacked_candidate):
    instances = _instances(stacked_candidate)
    kinds = _instance_kinds(stacked_candidate)
    landing = instances['CIR-LND-L01']
    threshold = instances['CIR-LND-L01-THR']
    door = instances['CIR-COR-LND-L01-DR']
    landing_plan = _polygon(landing.geometry)
    threshold_plan = _polygon(threshold.geometry)
    door_plan = _polygon(door.geometry)

    assert threshold.part_role == 'landing_door_threshold'
    assert 'CIR-LND-L01' in threshold.supports
    slab_supports = [support_id for support_id in threshold.supports
                     if kinds[support_id] == 'floor_slab']
    assert slab_supports
    threshold_relations = [
        relation for relation in stacked_candidate.dependency_graph.relations
        if relation.dependent_id == threshold.id
    ]
    assert {relation.host_id for relation in threshold_relations} == set(
        threshold.supports)
    assert all(relation.topology_status == 'geometry_checked'
               for relation in threshold_relations)
    assert threshold_plan.covers(door_plan)
    assert threshold_plan.intersection(landing_plan).area > 0.0
    assert _z_interval(threshold.geometry)[1] == pytest.approx(
        _z_interval(landing.geometry)[1], abs=0.005)

    floor = unary_union([
        _polygon(element.geometry) for element in stacked_candidate.elements
        if element.level_id == 'L01' and element.kind == 'floor_slab'
    ])
    assert threshold_plan.intersection(floor).area > 0.0


def test_completed_candidate_obeys_the_program_volume_physical_protocol(
        stacked_candidate):
    """The published PV path measures bodies, not only their centre-lines."""
    report = stacked_candidate.spatial
    assert report.counts['PV-INTERNAL-SOLID-CONTAINMENT'] == 0
    assert report.counts['PV-FACADE-COLLAR'] == 0
    assert not [finding for finding in report.findings
                if finding.rule_id.startswith('PV-')
                and finding.severity == 'violation']


def test_ramp_gallery_has_real_level_joints(stacked_candidate):
    instances = _instances(stacked_candidate)
    top = next(
        landing for landing in stacked_candidate.accessible_route.landings
        if landing.kind == 'top')
    chain = (
        f'CIR-RMP-LND-{top.index:02d}',
        'CIR-RMP-LND-ENTRY-LINK',
        'CIR-LND-ENTRY',
    )
    for first_id, second_id in zip(chain, chain[1:]):
        first = instances[first_id].geometry
        second = instances[second_id].geometry
        assert _polygon(first).intersection(_polygon(second)).area > 1.0e-5
        assert _z_interval(first)[1] == pytest.approx(
            _z_interval(second)[1], abs=0.005)


def test_shifted_gallery_fails_attachment_while_portal_stays_open(stacked_candidate):
    builder = _Builder(stacked_candidate.datum_set, stacked_candidate.lattice)
    builder.groups = {
        (index,): group.model_copy(deep=True)
        for index, group in enumerate(stacked_candidate.element_groups)
    }
    builder.element_ids = set(_instances(stacked_candidate))
    builder.accessible_route = stacked_candidate.accessible_route
    builder.public_stair_ids = list(
        stacked_candidate.circulation_plan.public_stair_ids)
    builder.approach['ramp_link_id'] = 'CIR-RMP-LND-ENTRY-LINK'
    link = next(
        instance
        for group in builder.groups.values()
        for instance in group.instances
        if instance.id == 'CIR-RMP-LND-ENTRY-LINK')
    link.geometry = link.geometry.model_copy(update={
        'center': link.geometry.center.model_copy(update={
            'x': link.geometry.center.x + 100.0,
        }),
    })

    plan = _resolve_program_circulation(
        builder, portal_report=stacked_candidate.portals)
    by_id = {finding.id: finding for finding in plan.findings}
    assert by_id['PV-CIRC-PORTAL-ATTACHMENT'].status == 'failed'
    assert any(
        portal.id == plan.attachment_portal_id and portal.passable
        for portal in stacked_candidate.portals.portals)


def test_ramp_gallery_does_not_collide_with_public_stair(stacked_candidate):
    instances = _instances(stacked_candidate)
    link = instances['CIR-RMP-LND-ENTRY-LINK'].geometry
    link_plan, link_z = _polygon(link), _z_interval(link)
    collisions = []
    for identifier in stacked_candidate.circulation_plan.public_stair_ids:
        # The entry landing is the intended walking-surface joint; every other
        # public-stair solid must remain clear of the gallery body.
        if identifier == 'CIR-LND-ENTRY':
            continue
        geometry = instances[identifier].geometry
        footprint, interval = _polygon(geometry), _z_interval(geometry)
        if footprint is None or interval is None:
            continue
        if (link_plan.intersection(footprint).area > 1.0e-5
                and min(link_z[1], interval[1])
                - max(link_z[0], interval[0]) > 1.0e-5):
            collisions.append(identifier)
    assert collisions == []


@pytest.mark.parametrize('grammar', GRAMMARS)
def test_facade_entrance_uses_the_same_program_volume_boundary_station(grammar):
    _volumes, datums, lattice = _chain(grammar)
    approach = _plan_approach(lattice, datums)
    entrance = planned_entrance(lattice, datums, approach)
    expected, tangent, outward = lattice.circulation_intent.entry_station.resolve(lattice)

    assert entrance is not None
    assert entrance.level_id == lattice.circulation_intent.entry_station.level_id
    assert entrance.center == pytest.approx(expected, abs=1e-4)
    assert abs(entrance.tangent[0] * tangent[0]
               + entrance.tangent[1] * tangent[1]) == pytest.approx(1.0)
    assert entrance.inward[0] * outward[0] + entrance.inward[1] * outward[1] < -0.999


def test_narrow_carrier_fails_by_name_without_shrinking_or_relocating_stair():
    _volumes, datums, lattice = _chain('PVG-STACKED-BANDS')
    carrier_ids = set(lattice.circulation_intent.carrier_volume_ids)
    lattice.program_volume_regions = [
        region.model_copy(update={'grid_rect': (0, 0, 1, 1)})
        if region.id in carrier_ids else region
        for region in lattice.program_volume_regions
    ]
    with pytest.raises(ValueError, match='PV-CIRC-SPINE-NO-FIT'):
        core_anchors(lattice, datums)


def test_carefree_library_delivers_the_full_brief_inside_program_volume_floor():
    """The score that exposed the repeated owner-stack/core collision stays closed."""
    values = {
        'tempo_of_change': 0.3094618055555556,
        'tension_release': 0.10298816024834384,
        'density': 0.6470988401166138,
        'continuity': 0.5793812280842068,
        'repetition': 0.6565784937614356,
        'variation': 0.36587409542915517,
        'hierarchy': 0.5266758676111001,
        'interruption': 0.050428235201131134,
        'polyphony': 0.7389349300912866,
        'genre_style': 0.5007323152875212,
    }
    confidences = {
        'tempo_of_change': 0.865,
        'tension_release': 0.95,
        'density': 0.9,
        'continuity': 0.72,
        'repetition': 0.78,
        'variation': 0.75,
        'hierarchy': 0.8,
        'interruption': 0.74,
        'polyphony': 0.55,
        'genre_style': 0.35,
    }
    template = _score()
    score = template.model_copy(update={
        'dimensions': [dimension.model_copy(update={
                           'value': values[dimension.id],
                           'confidence': confidences[dimension.id],
                       })
                       for dimension in template.dimensions],
    })
    volumes = organize_program_volumes(
        score, 'library', grammar_id='PVG-STACKED-BANDS')
    massing = volumes.to_program_massing()
    datums = datums_for(massing, score)
    lattice = lattice_for(massing, datums)
    brief = brief_for('library', storeys=len(lattice.occupied))
    allocation, _carve = _carve_and_allocate(
        lattice, datums, 'library', brief)

    assert allocation.required_area_m2 == pytest.approx(3066.5)
    assert allocation.unplaced == []
    assert allocation.short == []
    assert allocation.fits
    assert {zone.space_id for zone in allocation.zones} == {
        space.id for space in brief}
    assert all(zone.area_delivered_m2 >= zone.area_required_m2 - 0.05
               for zone in allocation.zones)

    l03 = {zone.space_id: zone for zone in allocation.zones
           if zone.level_id == 'L03'}
    plan = allocation.public_circulation
    assert plan is not None
    required_gap = plan.clear_width_m + 2 * plan.wall_allowance_m
    assert l03['SP-STAFF'].y0 - l03['SP-CHILDREN'].y1 >= required_gap
    quiet_path = next(path for path in plan.paths
                      if path.target_id == 'SP-QUIET')
    special_path = next(path for path in plan.paths
                        if path.target_id == 'SP-SPECIAL')
    periodicals_path = next(path for path in plan.paths
                            if path.target_id == 'SP-PERIODICALS')
    stair_roots = {tuple(path.points[0]) for path in plan.paths
                   if path.target_id.startswith('STAIR-')}
    assert tuple(quiet_path.points[-1]) in stair_roots
    assert tuple(special_path.points[-1]) in stair_roots
    assert tuple(periodicals_path.points[-1]) in stair_roots
    assert LineString(quiet_path.points).length < 20.0
    assert LineString(special_path.points).length < 30.0
    assert LineString(periodicals_path.points).length < 30.0

    program_floor = {}
    for region in lattice.program_volume_regions:
        if region.role not in ('program', 'archetype'):
            continue
        program_floor.setdefault(region.level_id, []).append(
            box(*region.resolve_bounds(lattice)))
    program_floor = {level_id: unary_union(parts)
                     for level_id, parts in program_floor.items()}
    assert all(program_floor[zone.level_id].buffer(1.0e-7).covers(
        box(zone.x0, zone.y0, zone.x1, zone.y1))
        for zone in allocation.zones)
