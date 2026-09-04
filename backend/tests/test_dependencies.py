import json
from pathlib import Path

import pytest

from backend.app.compiler_v3 import compile_building_model_v3
from backend.app.dependencies import compile_dependency_graph
from backend.app.models import ArchitecturalScore, AudioFeatures


DEMO = (Path(__file__).parents[2] / 'artifacts' / 'integrated_demo'
        / 'building-b7ad95fa45a6-library-steel-international-v1')


@pytest.fixture(scope='module')
def model():
    features = AudioFeatures.model_validate_json(
        (DEMO / 'music_features.json').read_text(encoding='utf-8'))
    score = ArchitecturalScore.model_validate_json(
        (DEMO / 'architectural_score.json').read_text(encoding='utf-8'))
    return compile_building_model_v3(
        features, score, massing_id='MAS-SLAB', typology='library')


def test_every_constructed_element_has_a_typed_dependency_or_exemption(model):
    graph = model.dependency_graph
    assert graph is not None
    assert graph.status == 'passed'
    assert graph.connected_element_count == graph.required_element_count
    assert all(check.status != 'failed' for check in graph.checks)


def test_every_structural_element_reaches_the_external_soil_root(model):
    graph = model.dependency_graph
    structural_count = model.layer_counts['structure']
    assert graph.gravity_path_count == structural_count
    check = next(item for item in graph.checks if item.id == 'DEP-STRUCTURE-TO-SOIL')
    assert check.status == 'passed'
    assert not check.affected_ids


def test_spanning_members_and_treads_declare_both_hosts(model):
    minimum = {
        'primary_beam': 2, 'secondary_joist': 2, 'heavy_joist': 2,
        'clt_panel': 2, 'purlin': 2, 'stair_tread': 2,
    }
    by_dependent: dict[str, list] = {}
    for relation in model.dependency_graph.relations:
        by_dependent.setdefault(relation.dependent_id, []).append(relation)
    for element in model.elements:
        if element.kind in minimum:
            assert len(by_dependent[element.id]) >= minimum[element.kind], element.id


def test_facade_circulation_and_interior_assemblies_reach_structure(model):
    graph = model.dependency_graph
    check = next(item for item in graph.checks
                 if item.id == 'DEP-ASSEMBLY-TO-STRUCTURE')
    assert check.status == 'passed'
    exempt = {item.element_id for item in graph.exemptions}
    for element in model.elements:
        if element.semantic_layer in {'envelope', 'circulation'}:
            assert element.id not in exempt
            assert element.supports, element.id
        if element.kind in {'partition', 'partition_head', 'door',
                            'shelving_run', 'desk', 'seat'}:
            assert element.supports, element.id


def test_dependency_targets_resolve_and_relation_groups_round_trip(model):
    graph = model.dependency_graph
    element_ids = {element.id for element in model.elements}
    root_ids = {root.id for root in graph.roots}
    assert graph.relation_groups
    for relation in graph.relations:
        assert relation.dependent_id in element_ids
        assert relation.host_id in element_ids | root_ids
        assert relation.capacity_status == 'not_checked'
    dumped = json.loads(model.model_dump_json())['dependency_graph']
    assert 'relation_groups' in dumped
    assert 'relations' not in dumped


def test_connection_topology_does_not_claim_connection_design(model):
    graph = model.dependency_graph
    assert graph.connection_design_status == 'not_checked'
    capacity = next(item for item in graph.checks if item.id == 'DEP-CONNECTION-CAPACITY')
    assert capacity.status == 'not_checked'
    soil = next(root for root in graph.roots if root.id == 'ROOT-SOIL')
    assert soil.topology_status == 'unresolved'
    assert soil.capacity_status == 'not_checked'


def test_graph_validator_rejects_a_beam_with_no_declared_support(model):
    groups = [group.model_copy(deep=True) for group in model.element_groups]
    beam = next(instance for group in groups if group.kind == 'primary_beam'
                for instance in group.instances)
    beam.supports = []
    report = compile_dependency_graph(groups)
    assert report.status == 'failed'
    failed = {check.id for check in report.checks if check.status == 'failed'}
    assert {'DEP-REQUIRED-COVERAGE', 'DEP-STRUCTURE-TO-SOIL',
            'DEP-MINIMUM-SUPPORTS'} <= failed


def test_dependency_compilation_is_deterministic(model):
    first = model.dependency_graph.model_dump(mode='json')
    groups = [group.model_copy(deep=True) for group in model.element_groups]
    second = compile_dependency_graph(groups).model_dump(mode='json')
    assert first == second


@pytest.mark.parametrize('massing_id', ['MAS-TOWER', 'MAS-ZIGGURAT'])
def test_offset_roofs_register_two_trusses_and_connect_the_roof_deck(massing_id):
    features = AudioFeatures.model_validate_json(
        (DEMO / 'music_features.json').read_text(encoding='utf-8'))
    score = ArchitecturalScore.model_validate_json(
        (DEMO / 'architectural_score.json').read_text(encoding='utf-8'))
    built = compile_building_model_v3(
        features, score, massing_id=massing_id, typology='library')
    graph = built.dependency_graph
    relations = [relation for relation in graph.relations
                 if relation.dependent_id == 'ENV-DECK-ROOF']
    assert graph.status == 'passed'
    assert len([element for element in built.elements if element.kind == 'truss_chord']) >= 4
    assert len([element for element in built.elements if element.kind == 'purlin']) >= 1
    assert relations
    assert all(relation.host_id.startswith('STR-PRL-') for relation in relations)


def test_a_geometry_checked_relation_was_actually_measured(model):
    """The status has to be earned, not written.

    `topology='geometry_checked'` was a literal at every call site, so around eight
    thousand relations per model asserted a check that no code performed -- and several
    were wrong by metres: a floor-edge guard hosted on a stair tread twenty-four metres
    away, a canopy post bearing on the floor above it. A status that reports itself is
    worth less than no status, because a reader stops looking.
    """
    from backend.app.dependencies import CONTACT_M, _Record, _contact_gap

    records = {instance.id: _Record(group, instance)
               for group in model.element_groups for instance in group.instances}
    offenders = []
    for group in model.dependency_graph.relation_groups:
        for relation in group.expand():
            if relation.topology_status != 'geometry_checked':
                continue
            dependent = records.get(relation.dependent_id)
            host = records.get(relation.host_id)
            if dependent is None or host is None:
                continue
            gap = _contact_gap(dependent, host)
            if gap > CONTACT_M:
                offenders.append((relation.dependent_id, relation.host_id, gap))
    assert not offenders, offenders[:5]


def test_claims_the_geometry_did_not_support_are_reported_not_hidden(model):
    """Downgrading is the mechanism working; silence would be the defect."""
    check = next(item for item in model.dependency_graph.checks
                 if item.id == 'DEP-GEOMETRY-CLAIMS')
    assert check.status == 'passed'
    # Whatever could not be confirmed is named, and named elements are real.
    ids = {instance.id for group in model.element_groups
           for instance in group.instances}
    assert set(check.affected_ids) <= ids
