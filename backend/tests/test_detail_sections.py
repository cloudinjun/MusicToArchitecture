"""Detail sections are model readings with an honest student-review boundary."""

from types import SimpleNamespace

import pytest

from backend.app.detail_sections import compile_detail_sections, select_detail_cuts
from backend.app.drawing_sheet import SetIdentity, SheetSpec
from backend.app.drawings import DrawingSet, Placement, Sheet, _redrawn_content_mm
from backend.app.geometry import BoxGeometry, ExtrusionGeometry, QuadGeometry, Vector2, v3


def test_layer_labels_are_cut_representatives_not_unanchored_material_lists():
    from backend.app.detail_sections import _Element, _detail_label_elements
    def element(key,role,assembly,material='concrete'):
        return _Element(SimpleNamespace(kind='roof_deck',material_profile=material,
            semantic_layer='envelope',subsystem='roof'),
            SimpleNamespace(id=key,part_role=role,assembly_id=assembly))
    rows=[element('target','membrane','roof','membrane'),
          element('deck-a','deck','roof'),element('deck-b','deck','roof'),
          element('insulation','insulation','roof','insulation'),
          element('uncut','coping','roof'),element('unrelated','beam','frame')]
    index={row.id:row for row in rows}
    audit=SimpleNamespace(cut_element_bboxes_m={row.id:(0,0,1,1)
        for row in rows if row.id!='uncut'})
    selected=_detail_label_elements(audit,SimpleNamespace(target_element_ids=['target']),index)
    assert {row[0].id for row in selected}=={'target','deck-a','insulation'}
    assert all(row[0].id in audit.cut_element_bboxes_m for row in selected)


def test_material_labels_do_not_promote_group_depth_to_layer_thickness(detail_model):
    for group in detail_model.element_groups:
        if group.kind == 'glazing_panel':
            group.thickness_m = .22
    details = compile_detail_sections(detail_model)
    text = [annotation.text for drawing in details for annotation in drawing.annotations
            if annotation.kind == 'text']
    assert any('Glass' in line for line in text)
    assert not any('nominal' in line for line in text)
    assert any('OVERALL' in line for line in text)


@pytest.mark.parametrize('normal,bearing', [((1,0),0), ((0,1),270)])
def test_landing_cut_uses_portal_orientation_and_preserves_failed_target(detail_model, normal, bearing):
    landing = _instance('landing',BoxGeometry(center=v3(4,4,3.9),size=v3(2,2,.2)),
                        assembly_id='core',part_role='floor_landing')
    detail_model.element_groups.append(_group('stair_landing','concrete',landing))
    side = SimpleNamespace(support_ids=['landing'])
    failed = SimpleNamespace(id='failed-portal',side_a=side,side_b=side,
        center=(5,4),normal=normal,floor_z=4.,passable=False,door_ids=['door'])
    good = SimpleNamespace(**{**vars(failed),'id':'good-portal','passable':True})
    detail_model.portals = SimpleNamespace(portals=[good,failed])
    spec = next(s for s in select_detail_cuts(detail_model) if s.detail_kind=='landing_access')
    assert spec.bearing_deg == bearing
    assert spec.origin_xy == (5,4)
    assert spec.target_element_ids == ['door','landing']
    assert spec.crop_width_m == 8
    assert 'failed-portal' in spec.rationale and 'passable=False' in spec.rationale


def _instance(identifier, geometry, *, assembly_id=None, part_role=None, supports=()):
    return SimpleNamespace(
        id=identifier, geometry=geometry, assembly_id=assembly_id, part_role=part_role,
        supports=list(supports),
        position=(geometry.center if isinstance(geometry, BoxGeometry) else v3(0, 0, 0)),
    )


def _group(kind, material, *instances, thickness_m=None, semantic_layer=None,
           subsystem=None, rule_refs=()):
    envelope = kind in {
        'roof_deck', 'parapet', 'spandrel_panel', 'glazing_panel', 'external_strut',
        'entrance_door',
    }
    circulation = kind in {'ramp_landing'}
    layer = semantic_layer or ('envelope' if envelope else
                               'circulation' if circulation else 'structure')
    system = subsystem or ('expressed_frame' if kind in {
        'spandrel_panel', 'glazing_panel', 'external_strut'} else
        'roof' if kind in {'roof_deck', 'parapet'} else
        'entrance' if kind == 'entrance_door' else
        'ramps' if circulation else 'floors')
    return SimpleNamespace(kind=kind, semantic_layer=layer, subsystem=system,
                           material_profile=material, thickness_m=thickness_m,
                           rule_refs=list(rule_refs), instances=list(instances))


@pytest.fixture
def detail_model():
    plate = [Vector2(x=x, y=y) for x, y in ((0, 0), (10, 0), (10, 10), (0, 10))]
    levels = [
        SimpleNamespace(id='L00', kind='ground', z=0.0, plate=plate),
        SimpleNamespace(id='L01', kind='occupied', z=4.0, plate=plate),
        SimpleNamespace(id='L02', kind='roof', z=8.0, plate=plate),
    ]
    slab = ExtrusionGeometry(boundary=plate, z_base=3.78, z_top=4.0)
    roof = ExtrusionGeometry(boundary=plate, z_base=7.78, z_top=8.0)
    glazing = QuadGeometry(corners=(
        v3(10.0, 3.0, 4.25), v3(10.0, 7.0, 4.25),
        v3(10.0, 7.0, 7.7), v3(10.0, 3.0, 7.7)))
    spandrel = QuadGeometry(corners=(
        v3(10.0, 3.0, 3.8), v3(10.0, 7.0, 3.8),
        v3(10.0, 7.0, 4.25), v3(10.0, 3.0, 4.25)))
    groups = [
        _group('floor_slab', 'concrete', _instance('STR-SLAB-L01', slab)),
        _group('roof_deck', 'roof', _instance('ENV-DECK-ROOF', roof)),
        _group('parapet', 'steel', _instance(
            'ENV-PAR-EAST', BoxGeometry(center=v3(9.9, 5.0, 8.55),
                                        size=v3(0.2, 10.0, 1.1)),
            assembly_id='ROOF-L02-EDGE', part_role='coping',
            supports=['ENV-DECK-ROOF'])),
        _group('spandrel_panel', 'steel', _instance(
            'ENV-SPD-L01-S001', spandrel, assembly_id='HTS-L01-EDGE-001',
            part_role='enclosure', supports=['ENV-STR-L01-S001']), thickness_m=0.12),
        _group('glazing_panel', 'glass', _instance(
            'ENV-GLZ-L01-S001', glazing, assembly_id='HTS-L01-EDGE-001',
            part_role='glazing', supports=['ENV-STR-L01-S001']), thickness_m=0.05),
        _group('external_strut', 'steel', _instance(
            'ENV-STR-L01-S001', BoxGeometry(center=v3(9.5, 5.0, 4.1),
                                            size=v3(1.0, 0.16, 0.16)),
            assembly_id='HTS-L01-EDGE-001', part_role='support',
            supports=['STR-SLAB-L01'])),
        _group('entrance_door', 'glass', _instance(
            'ENV-ENT-L00', BoxGeometry(center=v3(9.9, 1.0, 1.2),
                                      size=v3(0.12, 1.8, 2.4)),
            assembly_id='CIR-ENTRY-L00', part_role='threshold',
            supports=['CIR-RMP-LND-00'])),
        _group('ramp_landing', 'concrete', _instance(
            'CIR-RMP-LND-00', BoxGeometry(center=v3(7.8, 1.0, 0.1),
                                         size=v3(4.2, 1.5, 0.2)),
            assembly_id='CIR-ENTRY-L00', part_role='landing',
            supports=['STR-SLAB-L01'])),
    ]
    return SimpleNamespace(
        model_id='building-v3-detail-fixture', score_id='score-detail-fixture',
        typology='museum', structural_system_id='STR-SYS-STEEL-FRAME',
        facade_grammar_id='FCD-06-HIGH-TECH', envelope_tectonic_id='ENV-EXPRESSED',
        profiles={}, materials={'concrete': object(), 'roof': object(), 'steel': object(),
                                'glass': object()},
        lattice=SimpleNamespace(levels=levels, massing_id='MAS-SLAB', cutaway=False),
        element_groups=groups,
    )


def test_selects_three_required_detail_families_and_high_tech_enlargement(detail_model):
    specs = select_detail_cuts(detail_model)

    assert [spec.detail_kind for spec in specs[:3]] == [
        'roof_edge', 'facade_floor', 'entry_circulation']
    assert [spec.scale_denominator for spec in specs] == [20, 20, 20, 10]
    assert specs[-1].parent_spec_id == 'DTL-FACADE-FLOOR-20'
    assert specs[1].target_element_ids == [
        'ENV-GLZ-L01-S001', 'ENV-SPD-L01-S001', 'ENV-STR-L01-S001']


def test_every_detail_is_a_cropped_model_projection_with_its_own_readiness(detail_model):
    model_ids = {instance.id for group in detail_model.element_groups
                 for instance in group.instances}
    details = compile_detail_sections(detail_model)

    assert len(details) == 4
    for drawing in details:
        assert drawing.kind == 'detail'
        assert drawing.marks
        assert {mark.element_id for mark in drawing.marks} <= model_ids
        assert drawing.detail_audit.source == 'compiled_model_projection'
        assert drawing.detail_audit.projection_verified
        assert drawing.detail_audit.cut_bbox_m
        assert drawing.detail_audit.cut_element_bboxes_m
        assert drawing.detail_audit.key_dimensions_m['projected_width'] > 0
        assert drawing.detail_audit.key_dimensions_m['projected_height'] > 0
        assert drawing.detail_audit.material_roles
        assert drawing.detail_audit.assemblies
        assert drawing.detail_audit.host_element_ids
        assert drawing.detail_readiness.professional_review_required is True
        assert drawing.detail_readiness.construction_document_status == 'not_evaluated'
        assert drawing.detail_readiness.permit_status == 'not_evaluated'
        assert drawing.detail_readiness.status == 'ready_with_limitations'
        assert drawing.detail_readiness.missing_layers
        assert any(check.status == 'unevaluated'
                   for check in drawing.detail_readiness.checks)
        assert 'PROFESSIONAL REVIEW REQUIRED' in drawing.body_svg((0.0, 0.0))


def test_detail_svg_prints_model_evidence_dimensions_and_open_seam(detail_model):
    roof = next(drawing for drawing in compile_detail_sections(detail_model)
                if drawing.detail_audit.detail_kind == 'roof_edge')
    svg = roof.to_svg()
    width_mm = roof.detail_audit.key_dimensions_m['projected_width'] * 1000
    height_mm = roof.detail_audit.key_dimensions_m['projected_height'] * 1000

    assert f'>OVERALL {width_mm:.0f}<' in svg
    assert f'>OVERALL {height_mm:.0f}<' in svg
    assert 'Student review · professional follow-on retained' in svg
    assert 'Open:' in svg
    assert 'professional review required' in svg


def test_roof_detail_crop_tracks_selected_membrane_above_roof_datum(detail_model):
    plate = detail_model.lattice.levels[-1].plate
    membrane = ExtrusionGeometry(
        boundary=plate, z_base=10.8, z_top=10.805)
    detail_model.element_groups.append(_group(
        'roof_deck', 'roof', _instance(
            'ENV-ROOF-MEMBRANE', membrane,
            assembly_id='ROOF-L02-WARM-001', part_role='waterproofing_membrane',
            supports=['ENV-DECK-ROOF']),
        semantic_layer='envelope', subsystem='roof'))

    spec = next(spec for spec in select_detail_cuts(detail_model)
                if spec.detail_kind == 'roof_edge')
    roof = next(drawing for drawing in compile_detail_sections(detail_model)
                if drawing.detail_audit.detail_kind == 'roof_edge')

    assert spec.target_element_ids == ['ENV-ROOF-MEMBRANE']
    assert spec.target_point_m[2] == pytest.approx(10.8025)
    assert roof.detail_audit.target_elements_drawn == ['ENV-ROOF-MEMBRANE']
    assert roof.detail_audit.projection_verified
    assert roof.detail_readiness.status == 'ready_with_limitations'


def test_facade_detail_accepts_weather_skin_with_outboard_screen(detail_model):
    detail_model.facade_grammar_id = 'FCD-09-CRITICAL-REGIONALISM'
    detail_model.element_groups = [
        group for group in detail_model.element_groups
        if group.kind not in {'entrance_door', 'ramp_landing'}]
    for group in detail_model.element_groups:
        if group.kind in {'spandrel_panel', 'glazing_panel'}:
            group.subsystem = 'backing_skin'
        elif group.kind == 'external_strut':
            group.subsystem = 'screen'

    facade = next(drawing for drawing in compile_detail_sections(detail_model)
                  if drawing.detail_audit.detail_kind == 'facade_floor')
    coverage = next(check for check in facade.detail_readiness.checks
                    if check.id == 'D3-FACADE-ROLE-COVERAGE')

    assert facade.detail_audit.facade_roles == ['outboard_screen', 'weather_skin']
    assert coverage.status == 'passed'
    assert facade.detail_readiness.status == 'ready_with_limitations'
    assert 'High-tech' not in facade.title
    assert 'High-tech' not in facade.subtitle


def test_details_issue_in_a4xx_and_manifest_retains_per_view_reports(detail_model):
    details = compile_detail_sections(detail_model)
    issued = DrawingSet(model_id=detail_model.model_id, plans=[], sections=[], details=details)
    issued.lay_out(detail_model)

    assert issued.details == details
    assert issued.all == details
    assert issued.sheets
    assert all(sheet.number.startswith('A-4') and sheet.kind == 'detail'
               for sheet in issued.sheets)
    rows = issued.manifest(detail_model)['sheets']
    detail_rows = [drawing for row in rows if row['kind'] == 'detail'
                   for drawing in row['drawings']]
    assert len(detail_rows) == 4
    assert all(drawing['detail_audit']['source'] == 'compiled_model_projection'
               for drawing in detail_rows)
    assert all(drawing['detail_readiness']['professional_review_required']
               for drawing in detail_rows)


def test_missing_assembly_identity_blocks_detail_readiness(detail_model):
    for group in detail_model.element_groups:
        if group.kind in {'entrance_door', 'ramp_landing'}:
            for instance in group.instances:
                instance.assembly_id = None
                instance.part_role = None

    entry = next(drawing for drawing in compile_detail_sections(detail_model)
                 if drawing.detail_audit.detail_kind == 'entry_circulation')

    assert entry.detail_readiness.status == 'blocked'
    assembly = next(check for check in entry.detail_readiness.checks
                    if check.id == 'D3-ASSEMBLY-ID')
    assert assembly.status == 'failed'


def test_named_unresolved_interface_is_carried_as_professional_follow_on(detail_model):
    for group in detail_model.element_groups:
        if group.kind in {'entrance_door', 'ramp_landing'}:
            group.rule_refs = ['MTA-CIRCULATION-INTERFACE-UNRESOLVED']
            for instance in group.instances:
                instance.supports = []

    entry = next(drawing for drawing in compile_detail_sections(detail_model)
                 if drawing.detail_audit.detail_kind == 'entry_circulation')

    assert entry.detail_readiness.status == 'ready_with_limitations'
    assert entry.detail_audit.unresolved_interfaces == [
        'MTA-CIRCULATION-INTERFACE-UNRESOLVED']
    interface = next(check for check in entry.detail_readiness.checks
                     if check.id == 'D3-HOST-INTERFACE')
    assert interface.status == 'passed'
    assert any('professional follow-on' in line
               for line in entry.detail_readiness.limitations)
    declared = next(check for check in entry.detail_readiness.checks
                    if check.id == 'D3-DECLARED-INTERFACES')
    assert declared.status == 'unevaluated'
    assert 'interface:MTA-CIRCULATION-INTERFACE-UNRESOLVED' in (
        entry.detail_readiness.unresolved)


def test_mixed_scale_sheet_says_as_noted_and_cover_sizes_each_source_scale(detail_model):
    parent, enlargement = [drawing for drawing in compile_detail_sections(detail_model)
                           if drawing.detail_audit.detail_kind == 'facade_floor']
    identity = SetIdentity(
        model_id=detail_model.model_id, score_id=detail_model.score_id,
        typology=detail_model.typology, massing_id=detail_model.lattice.massing_id,
        structural_system_id=detail_model.structural_system_id,
        facade_grammar_id=detail_model.facade_grammar_id,
        envelope_tectonic_id=detail_model.envelope_tectonic_id,
        compiler_version='test')
    spec = SheetSpec(paper='A0', number='A-401', identity=identity)
    sheet = Sheet(number='A-401', kind='detail',
                  placements=[Placement(parent, 30, 30), Placement(enlargement, 400, 30)],
                  spec=spec)

    assert sheet.scale_name == 'As noted'
    assert '>As noted<' in sheet.to_svg()
    for drawing in (parent, enlargement):
        width, height = _redrawn_content_mm(drawing, 400)
        u0, v0, u1, v1 = drawing.extents
        assert width == pytest.approx((u1 - u0) * 1000 / 400)
        assert height == pytest.approx((v1 - v0) * 1000 / 400)
