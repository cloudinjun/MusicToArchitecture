"""The BIM handoff report must describe the contract and the current run honestly."""

from __future__ import annotations

from types import SimpleNamespace

from backend.app.bim_handoff import compile_bim_handoff_report


def _group(kind: str, count: int, material: str = 'steel_white'):
    return SimpleNamespace(kind=kind, instances=[object()] * count,
                           material_profile=material)


def _model(*groups):
    return SimpleNamespace(
        model_id='building-v3-bim-proof',
        schema_version='3.0',
        units='meters',
        coordinate_system='right_handed_z_up',
        element_groups=list(groups),
        model_dump_json=lambda: '{"model_id":"building-v3-bim-proof"}',
    )


def test_report_joins_the_registry_to_the_emitted_run() -> None:
    report = compile_bim_handoff_report(_model(
        _group('column', 6), _group('glazing_panel', 12),
        _group('program_zone', 2), _group('figure', 3)))

    # 73 kinds: the archetype layer (decision 0016) added the riser, the stage
    # platform and the proscenium wall.
    assert report.mapped_taxonomy_kind_count == report.taxonomy_kind_count == 73
    assert report.contract_coverage == 1.0
    assert report.mapped_emitted_kind_count == report.emitted_kind_count == 4
    assert report.mapped_element_count == report.emitted_element_count == 23
    assert report.target_element_count == 20
    assert report.omitted_element_count == 3
    assert report.handoff_readiness == 'ready_for_dry_run'


def test_report_keeps_live_revit_validation_pending() -> None:
    report = compile_bim_handoff_report(_model(_group('column', 1)))
    checks = {check.id: check for check in report.evidence_checks}

    assert all(check.status == 'passed' for check in report.evidence_checks[:-1])
    assert checks['BIM-LIVE-REVIT-DYNAMO'].status == 'pending'
    assert report.live_validation_status == 'pending'
    assert report.live_validation_blockers


def test_report_carries_stable_identity_and_conservative_sync_rules() -> None:
    report = compile_bim_handoff_report(_model(_group('column', 1)))
    names = {parameter.name for parameter in report.identity_parameters}

    assert {'MTA_ElementId', 'MTA_SourceHash', 'MTA_DeliveryStatus'} <= names
    assert {'review_conflict', 'retire'} <= set(report.sync_operations)
    assert any('hard delete' in safeguard.lower() for safeguard in report.safeguards)



def test_every_element_reaches_the_host_knowing_what_it_is_made_of() -> None:
    """A coordination model that does not carry material is one nobody can take off.

    The handoff described an element's taxonomy, level, program, provenance and
    validation status, and said nothing about its substance. Eighteen shared parameters
    and not one of them a material.
    """
    report = compile_bim_handoff_report(
        _model(_group('column', 12, 'steel_dark'),
               _group('glazing_panel', 30, 'glass'),
               _group('floor_slab', 4, 'concrete')))

    bound = {binding.profile: binding for binding in report.material_bindings}
    assert set(bound) == {'steel_dark', 'glass', 'concrete'}
    assert sum(binding.element_count for binding in report.material_bindings) == 46

    # Each binding says what the host has to make, not only what to call it.
    assert bound['steel_dark'].revit_class == 'Metal'
    assert bound['glass'].revit_class == 'Glass'
    assert bound['concrete'].revit_class == 'Concrete'
    assert bound['glass'].transmission > 0.5
    assert bound['steel_dark'].metallic > 0.0
    assert all(binding.base_color.startswith('#') for binding in bound.values())

    material_check = next(check for check in report.evidence_checks
                          if check.id == 'BIM-MATERIAL-BINDING')
    assert material_check.status == 'passed'


def test_an_element_whose_material_resolves_to_nothing_fails_the_check() -> None:
    """Otherwise it arrives in Revit with a template default and nobody is told."""
    report = compile_bim_handoff_report(
        _model(_group('column', 12, 'steel_dark'),
               _group('brace', 7, 'unobtanium')))

    assert 'unobtanium' not in {b.profile for b in report.material_bindings}
    material_check = next(check for check in report.evidence_checks
                          if check.id == 'BIM-MATERIAL-BINDING')
    assert material_check.status == 'failed'
    assert 'unobtanium' in material_check.detail
    assert '7 elements' in material_check.detail
    assert report.handoff_readiness == 'blocked'


def test_the_contract_asks_the_host_for_the_material_parameters() -> None:
    """The bindings say what the host must create; these say what each instance
    points at. Both halves are needed: a material table nothing refers to furnishes a
    project with unused materials, and a profile name with no table behind it is a
    string."""
    import json
    from pathlib import Path

    registry = json.loads(
        (Path(__file__).parents[2] / 'docs' / 'contracts'
         / 'revit_dynamo_mapping.v1.json').read_text(encoding='utf-8'))
    parameters = {p['name']: p for p in registry['shared_parameters']}

    assert 'MTA_MaterialProfile' in parameters
    assert parameters['MTA_MaterialProfile']['required'] is True
    assert parameters['MTA_MaterialProfile']['source'] == 'group.material_profile'
    assert parameters['MTA_MaterialFamily']['required'] is True
    assert 'MTA_MaterialFinish' in parameters


def test_the_receiving_summary_adds_up_and_never_over_counts() -> None:
    """The numbers a BIM lead would price the work from.

    The first version of the material counts summed per mapping rule and kind, which
    added a kind's whole population to *every* material it appears in: `concrete` came
    out with 163 schedulable instances against 82 in total. A takeoff that reports more
    of a material than exists is worse than no takeoff, so both counts are taken from
    the element groups, where a kind and its material are known together.
    """
    report = compile_bim_handoff_report(
        _model(_group('column', 12, 'steel_dark'),
               _group('glazing_panel', 30, 'glass'),
               _group('floor_slab', 4, 'concrete'),
               _group('scale_figure', 9, 'accent_red')))

    receiving = report.receiving
    assert receiving is not None
    assert (receiving.native_element_count + receiving.room_element_count
            + receiving.direct_shape_element_count + receiving.omitted_element_count
            == receiving.mapped_element_count)
    assert 0.0 <= receiving.schedulable_share <= 1.0

    for binding in report.material_bindings:
        assert binding.schedulable_element_count <= binding.element_count, binding.profile

    # A material that only lands in an omitted category schedules nothing, and says so
    # rather than being left out of the takeoff.
    figures = next(b for b in report.material_bindings if b.profile == 'accent_red')
    assert figures.element_count == 9
    assert figures.schedulable_element_count == 0


def test_the_review_queue_puts_the_rebuild_work_first() -> None:
    """Alphabetical order is how a review misses the category with four hundred
    elements behind it and catches the one with one."""
    report = compile_bim_handoff_report(
        _model(_group('column', 12, 'steel_dark'),
               _group('stair_tread', 200, 'white'),
               _group('scale_figure', 9, 'accent_red')))

    queue = report.review_queue
    assert queue, 'nothing to review, which cannot be right for a model with elements'
    # Presentation-only categories are not review work; they are not being handed over.
    assert all(item.strategy != 'omit_presentation_only' for item in queue)
    strategies = [item.strategy for item in queue]
    rebuilds = [i for i, s in enumerate(strategies) if s == 'direct_shape_preview']
    natives = [i for i, s in enumerate(strategies) if s in ('native_candidate',
                                                           'room_candidate')]
    if rebuilds and natives:
        assert max(rebuilds) < min(natives), (
            'a native category was queued ahead of one needing a rebuild')
