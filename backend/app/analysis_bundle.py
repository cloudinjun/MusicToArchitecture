"""Everything the schema 3.0 compile worked out, in one payload a client can read.

The compiler produces far more than geometry. It selects a typology, a massing family,
a facade grammar and a structural system and records why; it sizes members against a
load combination; it runs the grammar's own validation gates, the ADA route, the
constitution, the IBC Chapter 10 egress graph, the dependency topology and the axis
skeleton; it resolves a site and derives three load cases from it. Until now every one
of those results was computed on the request path and then discarded, because the
response carried only the massing contract, the reports, and the GLB.

This module is the seam that stops that happening. It is a *view* over
`BuildingModelV3` -- it computes nothing new except the roll-up at the end, which is a
count and not a verdict -- and it deliberately omits one thing: the per-instance
geometry. Several thousand instance records are a megabyte of numbers the browser
already has in the GLB, so groups travel with their descriptive fields and an instance
count, and the geometry stays where geometry belongs.

Authority note: nothing here upgrades a status. A gate that reported `unevaluated`
is counted as unevaluated, never as passed, and the roll-up publishes the three
buckets separately for exactly that reason.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from .ada import RampPlan
from .archetypes import ArchetypeReport
from .bim_handoff import BimHandoffReport
from .constitution import ConstitutionReport
from .datums import DatumSet, Lattice
from .facade_gates import FacadeGateReport
from .geometry import ProfileSpec
from .materials import MaterialSpec
from .life_safety import LifeSafetyGraph
from .spatial_rules import RULES, SpatialReport
from .models_v3 import (
    AxisReport,
    BuildingModelV3,
    DependencyGraph,
    DerivationChain,
    MemberSizingRecord,
    SelectionRecord,
)
from .program import ProgramAllocation
from .site import SiteParameters
from .site_loads import SiteLoadSet

if TYPE_CHECKING:  # pragma: no cover - import cycle guard, typing only
    from .models import ArchitecturalScore, AudioFeatures, PipelineGateState, ValidationCheck


class ElementGroupSummary(BaseModel):
    """One element group as a record, without its instance geometry.

    Everything a reader needs to interrogate a group -- what it is, which layer it
    belongs to, which datums drove it, which section it carries, whether a load
    calculation governed that section, and the sentence the emitter wrote about why it
    exists -- travels here. The instances themselves do not: the browser draws them
    from the GLB, and repeating their coordinates in JSON would triple the payload to
    say the same thing twice.
    """

    group_id: str
    kind: str
    semantic_layer: str
    subsystem: str
    category: str
    program: str
    material_profile: str | None = None
    section_id: str | None = None
    thickness_m: float | None = None
    sizing_status: str
    utilisation: float | None = None
    governing_check: str | None = None
    datum_refs: list[str] = Field(default_factory=list)
    rule_refs: list[str] = Field(default_factory=list)
    reason: str = ''
    validation_status: str | None = None
    instance_count: int
    level_ids: list[str] = Field(default_factory=list)


class StatusTally(BaseModel):
    """One family of checks, counted in three buckets and never in two.

    `unevaluated` is its own column because a check the pipeline could not run is not
    a check that passed, and a summary that folds the two together is the specific
    dishonesty this project's gate rules exist to prevent.
    """

    source: str
    label: str
    authority: str
    # The building these checks describe, when it is not the model in view. None means
    # this model; a string names the other building, and the roll-up keeps such a
    # tally out of its totals.
    building: str | None = None
    passed: int = 0
    failed: int = 0
    unevaluated: int = 0
    blockers: list[str] = Field(default_factory=list)

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.unevaluated


class ComplianceRollup(BaseModel):
    """Every check family the run produced, counted. Not a verdict, and never one.

    The project rule is that placeholder code tables may return `fail` or
    `code_inputs_incomplete` but never `pass`, so this object publishes counts and
    the failing subjects, and deliberately has no field that could read as approval.
    """

    schema_version: Literal['mta.compliance_rollup/1.0'] = 'mta.compliance_rollup/1.0'
    tallies: list[StatusTally] = Field(default_factory=list)
    # Checks the run also ran, on a building that is not the one this bundle
    # describes -- the v2 massing contract when its typed identity diverges from the
    # v3 selection. Carried so the work is visible, excluded from every total so the
    # status bar never sums two buildings into one number.
    foreign_tallies: list[StatusTally] = Field(default_factory=list)
    passed_total: int = 0
    failed_total: int = 0
    unevaluated_total: int = 0
    blockers: list[str] = Field(default_factory=list)

    @property
    def checked_total(self) -> int:
        return self.passed_total + self.failed_total + self.unevaluated_total


class AnalysisBundle(BaseModel):
    """The whole schema 3.0 result set, minus instance geometry.

    Fields mirror `BuildingModelV3` one for one so a reader can move between the two
    without a translation table. `element_groups` is the single exception and says so
    in its own type name.
    """

    schema_version: Literal['mta.analysis_bundle/1.0'] = 'mta.analysis_bundle/1.0'

    # identity, and the four decisions the score was allowed to make
    model_id: str
    score_id: str
    typology: str
    tectonic_system: str
    structural_system_id: str
    facade_grammar_id: str
    envelope_tectonic_id: str
    selection: SelectionRecord | None = None

    # how the building was set out
    datum_set: DatumSet
    lattice: Lattice
    program_allocation: ProgramAllocation

    # what it is made of
    profiles: dict[str, ProfileSpec] = Field(default_factory=dict)
    sizing: list[MemberSizingRecord] = Field(default_factory=list)
    element_groups: list[ElementGroupSummary] = Field(default_factory=list)
    element_counts: dict[str, int] = Field(default_factory=dict)
    layer_counts: dict[str, int] = Field(default_factory=dict)
    element_count: int = 0
    sized_element_count: int = 0

    # what was checked
    facade_gates: FacadeGateReport | None = None
    accessible_route: RampPlan | None = None
    accessible_route_unresolved: str | None = None
    constitution: ConstitutionReport | None = None
    # What the spatial archetype promised and what the built geometry measures back —
    # sightlines, clearances, and the findings where the two disagree. None on
    # typologies that carry no archetype.
    archetype: ArchetypeReport | None = None
    life_safety: LifeSafetyGraph | None = None
    dependency_graph: DependencyGraph | None = None
    axis_report: AxisReport | None = None
    spatial: SpatialReport | None = None
    # The registry the element groups' `material_profile` ids resolve against, exactly
    # as `profiles` serves their section ids. Without it a client holds the name of a
    # finish and no way to render it.
    materials: dict[str, MaterialSpec] = Field(default_factory=dict)

    # where it is, and what that place asks of it
    site: SiteParameters | None = None
    site_loads: SiteLoadSet | None = None

    # A separately compiled downstream translation report. It joins this model to the
    # repository mapping registry but never imports Revit or upgrades model authority.
    bim_handoff: BimHandoffReport | None = None

    # One assembled reasoning chain per element group, keyed by `group_id`, so a
    # reader who picks a family in the model can see how it was reasoned rather than
    # only what was recorded. Per group and not per element: the chains for 3,362
    # elements are 9 MB, and the instances of one family differ in their indices, not
    # in their reasoning. `derivation_element_ids` names the instance each chain was
    # assembled from, so the sample is stated rather than implied.
    derivation: dict[str, DerivationChain] = Field(default_factory=dict)
    derivation_element_ids: dict[str, str] = Field(default_factory=dict)

    compliance: ComplianceRollup = Field(default_factory=ComplianceRollup)
    limitations: list[str] = Field(default_factory=list)


def _summarise_groups(model: BuildingModelV3) -> list[ElementGroupSummary]:
    summaries: list[ElementGroupSummary] = []
    for group in model.element_groups:
        levels: list[str] = []
        for instance in group.instances:
            level = instance.level_id
            if level and level not in levels:
                levels.append(level)
        summaries.append(ElementGroupSummary(
            group_id=group.group_id,
            kind=group.kind,
            semantic_layer=group.semantic_layer,
            subsystem=group.subsystem,
            category=group.category,
            program=group.program,
            material_profile=group.material_profile,
            section_id=group.section_id,
            thickness_m=group.thickness_m,
            sizing_status=group.sizing_status,
            utilisation=group.utilisation,
            governing_check=group.governing_check,
            datum_refs=list(group.datum_refs),
            rule_refs=list(group.rule_refs),
            reason=group.reason or '',
            validation_status=group.validation_status,
            instance_count=len(group.instances),
            level_ids=sorted(levels),
        ))
    return summaries


def _tally_facade_gates(report: FacadeGateReport | None) -> StatusTally | None:
    if report is None:
        return None
    tally = StatusTally(
        source='facade_gates',
        label='Facade grammar gates',
        authority=f'{report.grammar_label} guide ({report.guide_ref})',
    )
    for gate in report.gates:
        if gate.verdict == 'passed':
            tally.passed += 1
        elif gate.verdict == 'failed':
            tally.failed += 1
            tally.blockers.append(f'{gate.id}: {gate.detail}')
        else:
            tally.unevaluated += 1
    return tally


# The two halves of a run name the same grammar in different vocabularies: the v2
# facade contract carries the one id it is typed to, and the v3 selection carries the
# style guides'. This pair cites one guide --
# `docs/style_guides/facade/01_international_style.md` -- from both `models.py` and
# `grammar_specs.py`, so the ids denote one grammar and must compare equal.
V2_GRAMMAR_ALIASES = {'international_style_informed': 'FCD-01-INTERNATIONAL-STYLE'}


def _canonical_grammar(grammar_id: str) -> str:
    return V2_GRAMMAR_ALIASES.get(grammar_id, grammar_id)


def _summarise_derivation(
    model: BuildingModelV3, features, score,
) -> tuple[dict[str, DerivationChain], dict[str, str]]:
    """One reasoning chain per element family, assembled from what the model carries.

    `derivation.build_chains` returns a chain per *element*, which is what a click on a
    solid would want and what the module was written for. It is also 9 MB on a theatre,
    against 1.7 MB for the whole model, so shipping it whole would make the reasoning
    the largest thing in the response by a factor of five.

    The instances of one family differ in their lattice indices and their coordinates,
    not in why they exist, so one chain per family carries the reasoning at a size the
    wire can hold. The instance it was assembled from is returned alongside rather than
    left implicit -- a sample presented as a summary is the kind of claim this project
    does not make.
    """
    from .derivation import build_chain

    by_dependent: dict[str, list] = {}
    graph = model.dependency_graph
    if graph is not None:
        for relation_group in graph.relation_groups:
            for relation in relation_group.expand():
                by_dependent.setdefault(relation.dependent_id, []).append(relation)

    chains: dict[str, DerivationChain] = {}
    sampled: dict[str, str] = {}
    for group in model.element_groups:
        elements = group.expand()
        if not elements:
            continue
        element = elements[0]
        chains[group.group_id] = build_chain(
            element, model.lattice, model.datum_set,
            by_dependent.get(element.id, ()), features=features, score=score)
        sampled[group.group_id] = element.id
    return chains, sampled


def _same_building(model: BuildingModelV3, companion: str | None) -> bool:
    """Whether the v2 companion chain built the building this bundle describes.

    The v2 massing contract is typed to one building -- a library in the International
    Style -- while the v3 selection follows the score. The day the score first chose a
    theatre, the status bar summed the theatre's checks with a library's and reported
    the total as one building's compliance: 57 passed, 1 failed, 12 unevaluated, of
    which a third belonged to a building not on screen.

    Comparing the raw ids was the mirror error, and it hid for as long because it fails
    in the safe direction: the two vocabularies never spell a grammar the same way, so
    *every* run reported two buildings and the v2 checks were dropped from the roll-up
    even on the runs where the score did choose a library in the International Style.
    The grammar halves are therefore compared canonically, not literally.
    """
    if companion is None:
        return True
    typology, _, grammar = companion.partition('/')
    return (typology == model.typology
            and _canonical_grammar(grammar)
            == _canonical_grammar(model.facade_grammar_id))


def _tally_life_safety(graph: LifeSafetyGraph | None) -> StatusTally | None:
    if graph is None:
        return None
    tally = StatusTally(
        source='life_safety',
        label='Egress and occupancy',
        authority=f'IBC Chapter 10, occupancy {graph.occupancy_group}',
    )
    for finding in graph.findings:
        if finding.status == 'pass':
            tally.passed += 1
        elif finding.status == 'fail':
            tally.failed += 1
            tally.blockers.append(f'{finding.clause} {finding.label} — {finding.subject}')
        else:
            tally.unevaluated += 1
    return tally


def _tally_constitution(report: ConstitutionReport | None) -> StatusTally | None:
    if report is None:
        return None
    tally = StatusTally(
        source='constitution',
        label='Base-building support',
        authority=f'Constitution for {report.typology}',
    )
    for finding in report.findings:
        if finding.status == 'satisfied':
            tally.passed += 1
        elif finding.status == 'missing':
            tally.failed += 1
            tally.blockers.append(f'{finding.requirement_id} {finding.label} — {finding.detail}')
        else:
            tally.unevaluated += 1
    return tally


def _tally_dependency(graph: DependencyGraph | None) -> StatusTally | None:
    if graph is None:
        return None
    tally = StatusTally(
        source='dependency_graph',
        label='Dependency topology',
        authority='Generated graph; connection capacity not checked',
    )
    for check in graph.checks:
        if check.status == 'passed':
            tally.passed += 1
        elif check.status == 'failed':
            tally.failed += 1
            tally.blockers.append(f'{check.id}: {check.message}')
        else:
            tally.unevaluated += 1
    return tally


def _tally_program(allocation) -> StatusTally | None:
    """Every briefed space, counted as delivered or not.

    The roll-up had no program family at all, so a theatre whose auditorium arrived
    134 m2 short -- a fifth of the one room the building exists for -- reported zero
    failures. Area is a requirement like any other and it belongs in the same three
    columns as the code checks: a space is delivered when it meets its own tolerance,
    failed when it is placed and short, and failed when it could not be placed at all.
    Nothing here is unevaluated: every line of the brief was either given floor or not.
    """
    if allocation is None:
        return None
    tally = StatusTally(
        source='program_area',
        label='Brief delivered',
        authority='The typology brief, per space',
    )
    for zone in allocation.zones:
        if zone.area_satisfied:
            tally.passed += 1
        else:
            tally.failed += 1
            tally.blockers.append(
                f'{zone.space_id} {zone.label}: {zone.area_delivered_m2:.0f} m2 '
                f'delivered against {zone.area_required_m2:.0f} asked for '
                f'({zone.area_delivered_m2 / zone.area_required_m2:.0%}, tolerance '
                f'{zone.area_tolerance:.0%})')
    for space in allocation.unplaced:
        tally.failed += 1
        tally.blockers.append(
            f'{space.space_id} {space.label}: not placed -- {space.reason}')
    return tally


def _tally_spatial(report: SpatialReport | None) -> StatusTally | None:
    """The constraints that stand in for looking at the model.

    Counted per rule rather than per finding: a rule that found nothing is a check that
    passed, and it is the thing worth reporting. Warnings are neither -- a consequence
    the pipeline named and could not design away is not a blocker and is not a clean
    bill either, so it is carried as unevaluated with the reason on the finding.
    """
    if report is None:
        return None
    tally = StatusTally(
        source='spatial',
        label='Spatial common sense',
        authority='Constraints standing in for what a person would see',
    )
    warned = {finding.rule_id for finding in report.findings
              if finding.severity == 'warning'}
    for rule in RULES:
        blocking = [finding for finding in report.findings
                    if finding.rule_id == rule.id and finding.severity == 'violation']
        if blocking:
            tally.failed += 1
            worst = max(blocking, key=lambda finding: finding.measure)
            tally.blockers.append(
                f'{rule.id}: {rule.sees} {len(blocking)} found, worst is '
                f'{worst.detail}')
        elif rule.id in warned:
            tally.unevaluated += 1
        else:
            tally.passed += 1
    return tally


def _tally_axis(report: AxisReport | None) -> StatusTally | None:
    if report is None:
        return None
    tally = StatusTally(
        source='axis_report',
        label='Centre-line joints',
        authority='Axis skeleton the emitters registered to',
    )
    for check in report.checks:
        if check.status == 'passed':
            tally.passed += 1
        elif check.status == 'failed':
            tally.failed += 1
            tally.blockers.append(f'{check.id}: {check.message}')
        else:
            tally.unevaluated += 1
    return tally


def _tally_route(model: BuildingModelV3) -> StatusTally:
    """The accessible route is one check with exactly two outcomes, by design.

    `ada.plan_switchback_ramp` returns a compliant plan or nothing, so this reports a
    pass or the reason a stair was built instead. There is no partial credit.
    """
    tally = StatusTally(
        source='accessible_route',
        label='Accessible route',
        authority='ADA §405',
    )
    if model.accessible_route is not None:
        tally.passed = 1
    elif model.accessible_route_unresolved:
        tally.failed = 1
        tally.blockers.append(f'accessible_route: {model.accessible_route_unresolved}')
    else:
        tally.unevaluated = 1
    return tally


def _tally_site_loads(loads: SiteLoadSet | None) -> StatusTally | None:
    """Load cases counted by whether their inputs are strong enough to design on.

    A result computed from a `code_lookup` nobody reviewed is not a design value, so
    it lands in `unevaluated` and carries the reason. Widening this to call such a
    figure `passed` is the thing `site.py` was written to prevent.
    """
    if loads is None:
        return None
    tally = StatusTally(
        source='site_loads',
        label='Site load cases',
        authority='ASCE 7-16, from resolved site parameters',
    )
    for result in (loads.snow, loads.wind, loads.seismic):
        if result.design_ready:
            tally.passed += 1
        else:
            tally.unevaluated += 1
            tally.blockers.append(
                f'{result.action}: computed from unreviewed inputs, not a design value')
    return tally


def _tally_validation(checks: 'list[ValidationCheck] | None') -> StatusTally | None:
    if not checks:
        return None
    tally = StatusTally(
        source='massing_validation',
        label='Massing validation',
        authority='v2 massing contract',
    )
    for check in checks:
        if check.status == 'pass':
            tally.passed += 1
        elif check.status == 'fail':
            tally.failed += 1
            tally.blockers.append(f'{check.id}: {check.message}')
        else:
            tally.unevaluated += 1
            tally.blockers.append(f'{check.id}: {check.message}')
    return tally


def _tally_pipeline(gates: 'list[PipelineGateState] | None') -> StatusTally | None:
    if not gates:
        return None
    tally = StatusTally(
        source='pipeline_gates',
        label='Handoff gates',
        authority='Facade host handoff',
    )
    for gate in gates:
        if gate.status == 'pass':
            tally.passed += 1
        elif gate.status in ('fail', 'blocked'):
            tally.failed += 1
            tally.blockers.append(f'{gate.id}: {gate.message}')
        else:
            tally.unevaluated += 1
    return tally


def compile_analysis_bundle(
    model: BuildingModelV3,
    *,
    validation: 'list[ValidationCheck] | None' = None,
    pipeline_gates: 'list[PipelineGateState] | None' = None,
    bim_handoff: BimHandoffReport | None = None,
    companion_identity: str | None = None,
    features: 'AudioFeatures | None' = None,
    score: 'ArchitecturalScore | None' = None,
) -> AnalysisBundle:
    """Gather one run's schema 3.0 results into the payload the client reads.

    `validation` and `pipeline_gates` come from the v2 acceptance chain, and
    `companion_identity` names the building that chain built, as `typology/grammar`.
    When it matches this model the v2 checks join the roll-up, so the status bar
    covers every check the run ran; when it does not -- the v2 contract is typed to
    one building and the v3 selection follows the score -- they are carried beside
    the totals, labelled with the building they belong to, and never summed into a
    building they do not describe.
    """
    same = _same_building(model, companion_identity)
    companion_tallies = [tally for tally in (
        _tally_validation(validation),
        _tally_pipeline(pipeline_gates),
    ) if tally is not None]
    foreign: list[StatusTally] = []
    if not same:
        for tally in companion_tallies:
            tally.building = companion_identity
        foreign = companion_tallies
        companion_tallies = []

    tallies = companion_tallies + [tally for tally in (
        _tally_facade_gates(model.facade_gates),
        _tally_life_safety(model.life_safety),
        _tally_constitution(model.constitution),
        _tally_route(model),
        _tally_dependency(model.dependency_graph),
        _tally_axis(model.axis_report),
        _tally_spatial(model.spatial),
        _tally_program(model.program_allocation),
        _tally_site_loads(model.site_loads),
    ) if tally is not None]

    # The reasoning behind each element family. Assembled here rather than by a caller
    # so every consumer of a bundle -- the API, the frozen demo, a stored run reopened
    # months later -- carries the same chains as the run that produced it.
    _derivation, _derivation_ids = _summarise_derivation(model, features, score)

    rollup = ComplianceRollup(
        tallies=tallies,
        foreign_tallies=foreign,
        passed_total=sum(tally.passed for tally in tallies),
        failed_total=sum(tally.failed for tally in tallies),
        unevaluated_total=sum(tally.unevaluated for tally in tallies),
        blockers=[blocker for tally in tallies for blocker in tally.blockers],
    )

    return AnalysisBundle(
        model_id=model.model_id,
        score_id=model.score_id,
        typology=model.typology,
        tectonic_system=model.tectonic_system,
        structural_system_id=model.structural_system_id,
        facade_grammar_id=model.facade_grammar_id,
        envelope_tectonic_id=model.envelope_tectonic_id,
        selection=model.selection,
        datum_set=model.datum_set,
        lattice=model.lattice,
        program_allocation=model.program_allocation,
        profiles=model.profiles,
        sizing=model.sizing,
        element_groups=_summarise_groups(model),
        derivation=_derivation, derivation_element_ids=_derivation_ids,
        element_counts=model.element_counts,
        layer_counts=model.layer_counts,
        element_count=model.element_count,
        sized_element_count=model.sized_element_count,
        facade_gates=model.facade_gates,
        accessible_route=model.accessible_route,
        accessible_route_unresolved=model.accessible_route_unresolved,
        constitution=model.constitution,
        archetype=model.archetype,
        life_safety=model.life_safety,
        dependency_graph=model.dependency_graph,
        axis_report=model.axis_report,
        spatial=model.spatial,
        materials=model.materials,
        site=model.site,
        site_loads=model.site_loads,
        bim_handoff=bim_handoff,
        compliance=rollup,
        limitations=list(model.limitations),
    )
