"""Run-level evidence for the proposed Revit/Dynamo handoff.

The repository contract is static, but the useful question is run-specific: how many
of this building's emitted kinds and instances have a declared BIM delivery path?  This
module joins the schema 3.0 model to the mapping registry and publishes that answer.

It plans no Revit geometry and imports no Autodesk API.  `ready_for_dry_run` means the
portable package is internally mapped; live Revit/Dynamo validation remains a separate
gate and stays visible on every report.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Literal, get_args
from uuid import UUID

from pydantic import BaseModel, Field

from .materials import REVIT_MATERIAL_CLASS, used_by as materials_used_by
from .models_v3 import BuildingModelV3, ElementKind


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / 'docs' / 'contracts' / 'revit_dynamo_mapping.v1.json'

BimStrategy = Literal[
    'native_candidate', 'room_candidate', 'direct_shape_preview',
    'omit_presentation_only',
]


class BimStrategySummary(BaseModel):
    strategy: BimStrategy
    label: str
    mapping_rule_count: int
    taxonomy_kind_count: int
    emitted_kind_count: int
    element_count: int


class BimCategorySummary(BaseModel):
    revit_category: str
    built_in_category: str | None = None
    strategy: BimStrategy
    mapping_rule_ids: list[str] = Field(default_factory=list)
    taxonomy_kind_count: int
    emitted_kind_count: int
    element_count: int
    review_gate: str
    # The materials that land in this category, so a takeoff can be scoped to the part
    # of the model that will actually schedule.
    material_profiles: list[str] = Field(default_factory=list)


class BimReceivingSummary(BaseModel):
    """What the receiving team gets, in the terms they price the work in.

    The strategy counts already existed; this says what they cost. A firm's first
    question about generated geometry is not how many elements there are, it is how
    much of it arrives as Revit elements they can schedule, tag and dimension -- and
    how much arrives as DirectShape solids that look right, cannot be scheduled, and
    have to be remodelled by hand before the model is worth anything to them.

    Nothing here is a new measurement. It is the same mapping, said in the sentence a
    BIM lead would say it in.
    """

    native_element_count: int
    room_element_count: int
    direct_shape_element_count: int
    omitted_element_count: int
    mapped_element_count: int
    # Native plus rooms over everything mapped. The one number a receiving team wants.
    schedulable_share: float
    remodel_note: str
    takeoff_note: str


class BimIdentityParameter(BaseModel):
    name: str
    guid: str
    purpose: str


class BimMaterialBinding(BaseModel):
    """One source material, and what the host has to make of it.

    Every element already names a material profile; nothing in the handoff said what
    that profile *is*. A coordination model arrived knowing an element's taxonomy, its
    level, its provenance and its validation status, and not what it was made of --
    which is the one thing a material takeoff, a fire-rating review and any render
    downstream of Revit all need first.

    Carried once per material rather than per element, which is also how Revit models
    it: a Material is an element in its own right and instances refer to it. The
    appearance values travel here for the same reason -- they belong to the material,
    not to the wall.
    """

    profile: str
    family: str
    finish: str
    # The Revit categories this material lands in, and how many of its elements arrive
    # as schedulable ones. A material takeoff over DirectShape solids is a takeoff of
    # things Revit cannot count.
    categories: list[str] = Field(default_factory=list)
    schedulable_element_count: int = 0
    base_color: str
    roughness: float
    metallic: float
    transmission: float
    ior: float
    element_count: int
    revit_class: str
    reason: str


class BimEvidenceCheck(BaseModel):
    id: str
    label: str
    status: Literal['passed', 'failed', 'pending']
    detail: str


class BimHandoffReport(BaseModel):
    """What one generated model can honestly claim about its BIM handoff."""

    schema_version: Literal['mta.revit_dynamo_handoff_report/0.1'] = \
        'mta.revit_dynamo_handoff_report/0.1'
    report_id: str
    source_model_id: str
    source_model_sha256: str
    source_schema_version: str
    source_units: str
    source_coordinate_system: str
    contract_version: str
    contract_sha256: str
    contract_status: str
    target_host: str
    orchestrator: str
    handoff_readiness: Literal['ready_for_dry_run', 'blocked']
    live_validation_status: Literal['pending'] = 'pending'

    taxonomy_kind_count: int
    mapped_taxonomy_kind_count: int
    contract_coverage: float
    emitted_kind_count: int
    mapped_emitted_kind_count: int
    emitted_element_count: int
    mapped_element_count: int
    target_element_count: int
    omitted_element_count: int
    emitted_coverage: float
    mapping_rule_count: int

    strategy_summaries: list[BimStrategySummary] = Field(default_factory=list)
    category_summaries: list[BimCategorySummary] = Field(default_factory=list)
    parameter_count: int
    required_parameter_count: int
    identity_parameters: list[BimIdentityParameter] = Field(default_factory=list)
    material_bindings: list[BimMaterialBinding] = Field(default_factory=list)
    receiving: BimReceivingSummary | None = None
    # Categories ordered by how much of the model sits behind each review gate: the
    # order a BIM lead would work through them in, rather than alphabetically.
    review_queue: list[BimCategorySummary] = Field(default_factory=list)
    sync_operations: list[str] = Field(default_factory=list)
    safeguards: list[str] = Field(default_factory=list)
    evidence_checks: list[BimEvidenceCheck] = Field(default_factory=list)
    live_validation_blockers: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


# The strategies that produce a real Revit element -- one that schedules, tags,
# dimensions and joins. A DirectShape is a solid: it renders, it does not schedule, and
# somebody remodels it by hand before the model is worth anything to a project.
_SCHEDULABLE_STRATEGIES = frozenset({'native_candidate', 'room_candidate'})

_STRATEGY_LABELS: dict[str, str] = {
    'native_candidate': 'Native candidates',
    'room_candidate': 'Room candidates',
    'direct_shape_preview': 'DirectShape previews',
    'omit_presentation_only': 'Presentation only',
}

_IDENTITY_PARAMETER_NAMES = {
    'MTA_ElementId', 'MTA_ModelId', 'MTA_SourceSchema', 'MTA_SourceHash',
    'MTA_Authority', 'MTA_ValidationStatus', 'MTA_DeliveryStatus',
    'MTA_LastSyncRunId',
}


def _read_registry() -> tuple[dict, bytes]:
    raw = REGISTRY_PATH.read_bytes()
    return json.loads(raw.decode('utf-8')), raw


def _evidence(
    check_id: str, label: str, passed: bool, pass_detail: str, fail_detail: str,
) -> BimEvidenceCheck:
    return BimEvidenceCheck(
        id=check_id,
        label=label,
        status='passed' if passed else 'failed',
        detail=pass_detail if passed else fail_detail,
    )


def compile_bim_handoff_report(model: BuildingModelV3) -> BimHandoffReport:
    """Join a schema 3.0 model to the repository-owned BIM mapping registry."""
    registry, registry_bytes = _read_registry()
    rules = registry.get('mapping_rules', [])
    parameters = registry.get('shared_parameters', [])

    rule_for_kind: dict[str, dict] = {}
    duplicate_kinds: set[str] = set()
    for rule in rules:
        for kind in rule.get('source_kinds', []):
            if kind in rule_for_kind:
                duplicate_kinds.add(kind)
            rule_for_kind[kind] = rule

    taxonomy_kinds = set(get_args(ElementKind))
    mapped_taxonomy = taxonomy_kinds & set(rule_for_kind)
    taxonomy_complete = mapped_taxonomy == taxonomy_kinds and not duplicate_kinds

    emitted_by_kind: dict[str, int] = defaultdict(int)
    materials_by_kind: dict[str, set[str]] = defaultdict(set)
    for group in model.element_groups:
        emitted_by_kind[group.kind] += len(group.instances)
        materials_by_kind[group.kind].add(group.material_profile)
    emitted_kinds = set(emitted_by_kind)
    mapped_emitted = emitted_kinds & set(rule_for_kind)
    emitted_complete = mapped_emitted == emitted_kinds

    strategy_accumulator: dict[str, dict[str, object]] = defaultdict(
        lambda: {'rules': set(), 'taxonomy': set(), 'emitted': set(), 'elements': 0})
    category_accumulator: dict[tuple[str, str, str | None], dict[str, object]] = defaultdict(
        lambda: {'rules': set(), 'taxonomy': set(), 'emitted': set(), 'elements': 0,
                 'gates': [], 'materials': set()})


    for rule in rules:
        strategy = rule['strategy']
        source_kinds = set(rule.get('source_kinds', []))
        strategy_row = strategy_accumulator[strategy]
        strategy_row['rules'].add(rule['id'])
        strategy_row['taxonomy'].update(source_kinds)

        category = rule.get('revit_category') or 'Omitted from BIM'
        category_key = (category, strategy, rule.get('built_in_category'))
        category_row = category_accumulator[category_key]
        category_row['rules'].add(rule['id'])
        category_row['taxonomy'].update(source_kinds)
        category_row['gates'].append(rule['review_gate'])

        for kind in source_kinds & emitted_kinds:
            count = emitted_by_kind[kind]
            strategy_row['emitted'].add(kind)
            strategy_row['elements'] += count
            category_row['emitted'].add(kind)
            category_row['elements'] += count
            for profile in materials_by_kind[kind]:
                category_row['materials'].add(profile)

    strategy_order = tuple(_STRATEGY_LABELS)
    strategy_summaries = [
        BimStrategySummary(
            strategy=strategy,
            label=_STRATEGY_LABELS[strategy],
            mapping_rule_count=len(strategy_accumulator[strategy]['rules']),
            taxonomy_kind_count=len(strategy_accumulator[strategy]['taxonomy']),
            emitted_kind_count=len(strategy_accumulator[strategy]['emitted']),
            element_count=int(strategy_accumulator[strategy]['elements']),
        )
        for strategy in strategy_order
    ]

    category_summaries = [
        BimCategorySummary(
            revit_category=category,
            built_in_category=built_in_category,
            strategy=strategy,
            mapping_rule_ids=sorted(row['rules']),
            taxonomy_kind_count=len(row['taxonomy']),
            emitted_kind_count=len(row['emitted']),
            element_count=int(row['elements']),
            review_gate='; '.join(dict.fromkeys(row['gates'])),
            material_profiles=sorted(row['materials']),
        )
        for (category, strategy, built_in_category), row in category_accumulator.items()
    ]
    category_summaries.sort(key=lambda row: (-row.element_count, row.revit_category))

    parameter_names = [parameter.get('name', '') for parameter in parameters]
    parameter_guids = [parameter.get('guid', '') for parameter in parameters]
    valid_guids = True
    for guid in parameter_guids:
        try:
            valid_guids = valid_guids and str(UUID(guid)) == guid
        except (ValueError, AttributeError, TypeError):
            valid_guids = False
    parameter_identity_valid = (
        len(parameter_names) == len(set(parameter_names))
        and len(parameter_guids) == len(set(parameter_guids))
        and valid_guids
        and _IDENTITY_PARAMETER_NAMES <= set(parameter_names)
    )
    identity_parameters = [
        BimIdentityParameter(
            name=parameter['name'], guid=parameter['guid'], purpose=parameter['purpose'])
        for parameter in parameters if parameter.get('name') in _IDENTITY_PARAMETER_NAMES
    ]
    identity_parameters.sort(key=lambda parameter: parameter.name)

    source_contract = registry.get('source_contract', {})
    source_matches = (
        source_contract.get('schema_version') == model.schema_version
        and source_contract.get('units') == model.units
        and source_contract.get('coordinate_system') == model.coordinate_system
        and source_contract.get('geometry_authority') == 'tagged_geometry'
    )

    # The materials this model uses, counted by the elements that carry them. One
    # binding per material rather than per element, which is how Revit models it too.
    used = materials_used_by(model)
    # Counted from the groups themselves, which is the only place an element's kind
    # and its material are known together. Summing per rule and kind instead added a
    # kind's whole population to *every* material it appears in, and a material's
    # schedulable count came out larger than its total.
    counts: dict[str, int] = defaultdict(int)
    material_categories: dict[str, set[str]] = defaultdict(set)
    material_schedulable: dict[str, int] = defaultdict(int)
    for group in model.element_groups:
        population = len(group.instances)
        counts[group.material_profile] += population
        rule = rule_for_kind.get(group.kind)
        if rule is None:
            continue
        material_categories[group.material_profile].add(
            rule.get('revit_category') or 'Omitted from BIM')
        if rule['strategy'] in _SCHEDULABLE_STRATEGIES:
            material_schedulable[group.material_profile] += population
    # A profile with no specification is an element that would arrive in Revit with no
    # material and silently take a template default -- the kind of gap that only shows
    # up in a takeoff months later, so it is a check rather than a comment.
    unbound_profiles = {group.material_profile for group in model.element_groups
                        if group.material_profile not in used}
    unbound_elements = sum(len(group.instances) for group in model.element_groups
                           if group.material_profile in unbound_profiles)
    materials_bound = not unbound_profiles

    material_bindings = [
        BimMaterialBinding(
            profile=profile, family=spec.family, finish=spec.finish,
            base_color=spec.base_color, roughness=spec.roughness,
            metallic=spec.metallic, transmission=spec.transmission, ior=spec.ior,
            element_count=counts.get(profile, 0),
            categories=sorted(material_categories.get(profile, ())),
            schedulable_element_count=material_schedulable.get(profile, 0),
            revit_class=REVIT_MATERIAL_CLASS[spec.family], reason=spec.reason)
        for profile, spec in sorted(used.items())
    ]

    # What the receiving team gets, in the terms they price the work in.
    by_strategy = {summary.strategy: summary.element_count
                   for summary in strategy_summaries}
    native = by_strategy.get('native_candidate', 0)
    rooms = by_strategy.get('room_candidate', 0)
    shapes = by_strategy.get('direct_shape_preview', 0)
    omitted = by_strategy.get('omit_presentation_only', 0)
    mapped_total = native + rooms + shapes + omitted
    receiving = BimReceivingSummary(
        native_element_count=native,
        room_element_count=rooms,
        direct_shape_element_count=shapes,
        omitted_element_count=omitted,
        mapped_element_count=mapped_total,
        schedulable_share=round((native + rooms) / mapped_total, 4) if mapped_total else 0.0,
        remodel_note=(
            f'{shapes} instances arrive as DirectShape solids. They render and they do '
            f'not schedule, tag or dimension; each category behind them names what has '
            f'to be rebuilt natively and on whose review.'),
        takeoff_note=(
            f'{sum(b.schedulable_element_count for b in material_bindings)} of '
            f'{sum(b.element_count for b in material_bindings)} instances carry a '
            f'material into a category Revit can schedule, so a material takeoff over '
            f'them is a real one.'),
    )
    # The order a BIM lead would work through the gates in: most of the model first.
    review_queue = sorted(
        (summary for summary in category_summaries
         if summary.strategy != 'omit_presentation_only'),
        key=lambda summary: (summary.strategy in _SCHEDULABLE_STRATEGIES,
                             -summary.element_count))

    evidence_checks = [
        _evidence(
            'BIM-CONTRACT-TAXONOMY', 'Taxonomy coverage', taxonomy_complete,
            f'{len(mapped_taxonomy)}/{len(taxonomy_kinds)} schema 3.0 kinds mapped exactly once.',
            f'Missing: {sorted(taxonomy_kinds - mapped_taxonomy)}; duplicates: {sorted(duplicate_kinds)}.',
        ),
        _evidence(
            'BIM-RUN-MAPPING', 'Run mapping', emitted_complete,
            f'{len(mapped_emitted)}/{len(emitted_kinds)} emitted kinds have a delivery strategy.',
            f'Unmapped emitted kinds: {sorted(emitted_kinds - mapped_emitted)}.',
        ),
        _evidence(
            'BIM-PARAMETER-IDENTITY', 'Parameter identity', parameter_identity_valid,
            f'{len(parameters)} parameter definitions have unique names and GUIDs.',
            'The shared-parameter registry contains a duplicate, invalid GUID, or missing identity field.',
        ),
        _evidence(
            'BIM-MATERIAL-BINDING', 'Material binding', materials_bound,
            f'{len(material_bindings)} materials cover all '
            f'{sum(b.element_count for b in material_bindings)} emitted elements, each '
            f'with a family, a Revit class and its appearance values.',
            f'{unbound_elements} elements name a material profile that resolves to no '
            f'specification: {sorted(unbound_profiles)}. Those elements would arrive in '
            f'the host with no material and take a template default.',
        ),
        _evidence(
            'BIM-SOURCE-CONTRACT', 'Source contract', source_matches,
            f'{model.schema_version} · {model.units} · {model.coordinate_system}.',
            'The model schema, units, coordinate system, or geometry authority does not match the registry.',
        ),
        BimEvidenceCheck(
            id='BIM-LIVE-REVIT-DYNAMO', label='Live Revit/Dynamo proof', status='pending',
            detail='A tested .dyn/.rvt, version matrix, rerun, conflict, retirement, and rollback record are still required.',
        ),
    ]
    static_passed = all(check.status == 'passed' for check in evidence_checks[:-1])

    omitted_elements = next(
        (summary.element_count for summary in strategy_summaries
         if summary.strategy == 'omit_presentation_only'), 0)
    emitted_element_count = sum(emitted_by_kind.values())
    mapped_element_count = sum(
        count for kind, count in emitted_by_kind.items() if kind in rule_for_kind)

    target = registry.get('target_contract', {})
    return BimHandoffReport(
        report_id=f'bim-handoff-{model.model_id}',
        source_model_id=model.model_id,
        source_model_sha256=hashlib.sha256(
            model.model_dump_json().encode('utf-8')).hexdigest(),
        source_schema_version=model.schema_version,
        source_units=model.units,
        source_coordinate_system=model.coordinate_system,
        contract_version=registry['schema_version'],
        contract_sha256=hashlib.sha256(registry_bytes).hexdigest(),
        contract_status=registry['status'],
        target_host=target.get('host', 'Autodesk Revit'),
        orchestrator=target.get('orchestrator', 'Dynamo for Revit'),
        handoff_readiness='ready_for_dry_run' if static_passed else 'blocked',
        taxonomy_kind_count=len(taxonomy_kinds),
        mapped_taxonomy_kind_count=len(mapped_taxonomy),
        contract_coverage=round(len(mapped_taxonomy) / len(taxonomy_kinds), 4),
        emitted_kind_count=len(emitted_kinds),
        mapped_emitted_kind_count=len(mapped_emitted),
        emitted_element_count=emitted_element_count,
        mapped_element_count=mapped_element_count,
        target_element_count=mapped_element_count - omitted_elements,
        omitted_element_count=omitted_elements,
        emitted_coverage=round(
            mapped_element_count / emitted_element_count, 4) if emitted_element_count else 0.0,
        mapping_rule_count=len(rules),
        strategy_summaries=strategy_summaries,
        category_summaries=category_summaries,
        parameter_count=len(parameters),
        required_parameter_count=sum(1 for parameter in parameters if parameter.get('required')),
        identity_parameters=identity_parameters,
        material_bindings=material_bindings,
        receiving=receiving,
        review_queue=review_queue,
        sync_operations=list(registry.get('sync_operations', [])),
        safeguards=[
            'Stable MTA source ID; Revit UniqueId is the host binding.',
            'Dry-run operation plan before any Revit write transaction.',
            'Explicit metre conversion, origin transform, and level mapping.',
            'Host-only edits are preserved and reported.',
            'Concurrent source and host edits become review conflicts.',
            'Missing source IDs retire for review; hard delete stays off.',
            'Blocking failures roll back the transaction group.',
        ],
        evidence_checks=evidence_checks,
        live_validation_blockers=[
            'Installed Revit, Dynamo, package, and project-template versions are unverified.',
            'Reviewed family/type mappings do not exist yet.',
            'No .dyn/.rvt unchanged-rerun, conflict, retirement, or rollback evidence exists yet.',
        ],
        limitations=list(registry.get('limitations', [])),
    )

