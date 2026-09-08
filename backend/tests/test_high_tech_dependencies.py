"""High-Tech facade carriers keep their emitter-owned support chain."""

from backend.app.dependencies import compile_dependency_graph
from backend.app.geometry import BoxGeometry, MemberGeometry, QuadGeometry, v3
from backend.app.models_v3 import ElementGroup, ElementInstance


def _instance(identifier, geometry, *, supports=(), assembly_id=None):
    return ElementInstance(
        id=identifier,
        level_id='L01',
        geometry=geometry,
        position=v3(0.0, 0.0, 0.0),
        dimensions=v3(1.0, 1.0, 1.0),
        supports=list(supports),
        assembly_id=assembly_id,
    )


def _group(index, kind, layer, subsystem, instance):
    return ElementGroup(
        group_id=f'TEST-{index}',
        kind=kind,
        semantic_layer=layer,
        subsystem=subsystem,
        category='public',
        program='structure',
        material_profile='steel',
        reason='Dependency graph test fixture.',
        instances=[instance],
    )


def _structural_chain():
    return [
        _group(
            1, 'footing', 'structure', 'foundation',
            _instance('STR-FOT-L00-001',
                      BoxGeometry(center=v3(0.0, 0.0, -1.0), size=v3(1.0, 1.0, 0.2))),
        ),
        _group(
            2, 'column', 'structure', 'frame',
            _instance(
                'STR-COL-L01-001',
                MemberGeometry(path=[v3(0.0, 0.0, -0.9), v3(0.0, 0.0, 0.0)],
                               profile='TEST'),
                supports=['STR-FOT-L00-001'],
            ),
        ),
        _group(
            3, 'floor_slab', 'structure', 'slabs',
            _instance(
                'STR-SLB-L01',
                BoxGeometry(center=v3(0.0, 0.0, 0.1), size=v3(4.0, 4.0, 0.2)),
                supports=['STR-COL-L01-001'],
            ),
        ),
    ]


def _high_tech_groups():
    return _structural_chain() + [
        _group(
            4, 'external_strut', 'envelope', 'expressed_frame',
            _instance(
                'ENV-BKT-L01-S000',
                MemberGeometry(path=[v3(1.5, 0.0, 0.2), v3(2.0, 0.0, 0.2)],
                               profile='TEST'),
                supports=['STR-SLB-L01'], assembly_id='HTA-L01-S000',
            ),
        ),
        _group(
            5, 'frame_expression', 'envelope', 'expressed_frame',
            _instance(
                'ENV-FRM-L01-S000',
                MemberGeometry(path=[v3(2.0, 0.0, 0.2), v3(2.0, 0.0, 3.0)],
                               profile='TEST'),
                supports=['ENV-BKT-L01-S000'], assembly_id='HTA-L01-S000',
            ),
        ),
        _group(
            6, 'external_strut', 'envelope', 'expressed_frame',
            _instance(
                'ENV-STR-L01-S000-N00',
                MemberGeometry(path=[v3(2.0, 0.0, 1.5), v3(2.5, 0.0, 1.5)],
                               profile='TEST'),
                supports=['ENV-FRM-L01-S000'], assembly_id='HTA-L01-S000',
            ),
        ),
    ]


def _high_tech_infill_groups():
    return _high_tech_groups() + [
        _group(
            7, 'spandrel_panel', 'envelope', 'expressed_frame',
            _instance(
                'ENV-SPD-L01-S000',
                QuadGeometry(corners=[
                    v3(2.0, 0.0, 0.2), v3(3.0, 0.0, 0.2),
                    v3(3.0, 0.0, 0.8), v3(2.0, 0.0, 0.8),
                ]),
                supports=['ENV-BKT-L01-S000'], assembly_id='HTA-L01-S000',
            ),
        ),
        _group(
            8, 'solid_wall_panel', 'envelope', 'expressed_frame',
            _instance(
                'ENV-CAS-L01-S000-C00',
                BoxGeometry(center=v3(2.5, 0.0, 1.5), size=v3(1.0, 0.1, 1.0)),
                supports=['ENV-STR-L01-S000-N00'], assembly_id='HTA-L01-S000',
            ),
        ),
        _group(
            9, 'glazing_panel', 'envelope', 'expressed_frame',
            _instance(
                'ENV-GLZ-L01-S000-C01',
                QuadGeometry(corners=[
                    v3(2.0, 0.0, 0.8), v3(3.0, 0.0, 0.8),
                    v3(3.0, 0.0, 2.2), v3(2.0, 0.0, 2.2),
                ]),
                supports=['ENV-STR-L01-S000-N00'], assembly_id='HTA-L01-S000',
            ),
        ),
    ]


def _relations_for(report, identifier):
    return [relation for relation in report.relations
            if relation.dependent_id == identifier]


def test_high_tech_declared_carriers_keep_the_frame_bracket_slab_chain():
    report = compile_dependency_graph(_high_tech_groups())

    assert {relation.host_id for relation in _relations_for(report, 'ENV-BKT-L01-S000')} \
        == {'STR-SLB-L01'}
    assert {relation.host_id for relation in _relations_for(report, 'ENV-FRM-L01-S000')} \
        == {'ENV-BKT-L01-S000'}
    assert {relation.host_id for relation in _relations_for(report, 'ENV-STR-L01-S000-N00')} \
        == {'ENV-FRM-L01-S000'}
    assert all(
        relation.topology_status == 'geometry_checked'
        for identifier in ('ENV-BKT-L01-S000', 'ENV-FRM-L01-S000',
                           'ENV-STR-L01-S000-N00')
        for relation in _relations_for(report, identifier)
    )


def test_high_tech_declared_infill_keeps_cassette_glazing_and_spandrel_hosts():
    report = compile_dependency_graph(_high_tech_infill_groups())

    expected = {
        'ENV-SPD-L01-S000': {'ENV-BKT-L01-S000'},
        'ENV-CAS-L01-S000-C00': {'ENV-STR-L01-S000-N00'},
        'ENV-GLZ-L01-S000-C01': {'ENV-STR-L01-S000-N00'},
    }
    for identifier, hosts in expected.items():
        relations = _relations_for(report, identifier)
        assert {relation.host_id for relation in relations} == hosts
        assert all(relation.topology_status == 'geometry_checked'
                   for relation in relations)


def test_legacy_undeclared_carrier_still_uses_floor_host_fallback():
    groups = _structural_chain() + [
        _group(
            4, 'external_strut', 'envelope', 'legacy_frame',
            _instance(
                'ENV-LEGACY-STRUT',
                MemberGeometry(path=[v3(1.0, 0.0, 0.2), v3(1.5, 0.0, 0.2)],
                               profile='TEST'),
            ),
        ),
    ]

    report = compile_dependency_graph(groups)
    relations = _relations_for(report, 'ENV-LEGACY-STRUT')

    assert [(relation.host_id, relation.topology_status) for relation in relations] \
        == [('STR-SLB-L01', 'rule_checked')]


def test_declared_high_tech_relation_is_downgraded_when_geometry_does_not_contact():
    groups = _high_tech_groups()
    frame = next(instance for group in groups if group.kind == 'frame_expression'
                 for instance in group.instances)
    frame.geometry = MemberGeometry(
        path=[v3(3.0, 0.0, 0.2), v3(3.0, 0.0, 3.0)], profile='TEST')

    report = compile_dependency_graph(groups)
    relation = _relations_for(report, 'ENV-FRM-L01-S000')[0]

    assert relation.host_id == 'ENV-BKT-L01-S000'
    assert relation.topology_status == 'rule_checked'
    geometry_check = next(check for check in report.checks
                          if check.id == 'DEP-GEOMETRY-CLAIMS')
    assert geometry_check.status == 'passed'
    assert 'ENV-FRM-L01-S000' in geometry_check.affected_ids
