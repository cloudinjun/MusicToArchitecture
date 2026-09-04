"""Static checks for the proposed Revit/Dynamo handoff registry.

These tests prove that the documentation covers the portable schema. They do not imply
that Revit, Dynamo, families, transactions, or native geometry have been exercised.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import get_args
from uuid import UUID

from backend.app.models_v3 import ElementKind


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / 'docs' / 'contracts' / 'revit_dynamo_mapping.v1.json'


def _registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding='utf-8'))


def test_revit_mapping_covers_every_element_kind_once() -> None:
    registry = _registry()
    covered = [
        kind
        for rule in registry['mapping_rules']
        for kind in rule['source_kinds']
    ]

    assert len(covered) == len(set(covered)), 'a source kind has multiple Revit rules'
    assert set(covered) == set(get_args(ElementKind))


def test_revit_mapping_uses_explicit_bounded_strategies() -> None:
    registry = _registry()
    allowed = {
        'native_candidate', 'room_candidate', 'direct_shape_preview',
        'omit_presentation_only',
    }
    ids = [rule['id'] for rule in registry['mapping_rules']]

    assert len(ids) == len(set(ids))
    for rule in registry['mapping_rules']:
        assert rule['strategy'] in allowed
        assert rule['review_gate'].strip()
        if rule['strategy'] != 'omit_presentation_only':
            assert rule['built_in_category'].startswith('OST_')


def test_revit_parameter_registry_has_stable_unique_guids() -> None:
    parameters = _registry()['shared_parameters']
    names = [parameter['name'] for parameter in parameters]
    guids = [parameter['guid'] for parameter in parameters]

    assert len(names) == len(set(names))
    assert len(guids) == len(set(guids))
    assert all(str(UUID(guid)) == guid for guid in guids)
    assert {parameter['storage_type'] for parameter in parameters} <= {'text', 'number'}
    assert {parameter['scope'] for parameter in parameters} == {'instance'}

    required_identity = {
        'MTA_ElementId', 'MTA_ModelId', 'MTA_SourceSchema', 'MTA_SourceHash',
        'MTA_Authority', 'MTA_ValidationStatus', 'MTA_DeliveryStatus',
        'MTA_LastSyncRunId',
    }
    required_names = {
        parameter['name'] for parameter in parameters if parameter['required']
    }
    assert required_identity <= required_names


def test_revit_contract_keeps_source_units_identity_and_deletion_explicit() -> None:
    registry = _registry()
    source = registry['source_contract']
    identity = registry['identity_contract']

    assert source['schema_version'] == '3.0'
    assert source['units'] == 'meters'
    assert source['coordinate_system'] == 'right_handed_z_up'
    assert source['geometry_authority'] == 'tagged_geometry'
    assert identity['external_key'] == 'MTA_ElementId'
    assert identity['host_binding_key'] == 'Revit Element.UniqueId'
    assert identity['forbidden_cross_run_key'] == 'Revit ElementId'
    assert identity['hard_delete_default'] is False
    assert identity['conflict_policy'] == 'preserve_and_review'

