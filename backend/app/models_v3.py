"""Schema 3.0: member-level building model.

What changes from v2, and why:

- **Geometry is a tagged union**, not a bounding box. `position` and `dimensions` remain
  as derived read-only data so the Grasshopper reader, the viewport filters, and the
  mapping report keep working, but they are no longer the authority.
- **Elements are located by lattice index**, and the index is visible in the ID:
  `STR-COL-X03-Y02-L04` is self-locating. Any consumer holding the lattice can recompute
  the position without reading the geometry, which is what makes diffing between runs
  and honest mapping reports possible.
- **Score bindings live on datums, not on elements.** A mullion did not individually
  negotiate with the music. Elements carry `datum_refs`; the report joins them. Coverage
  then means something real: the fraction of geometry reachable from a datum that a
  score dimension actually moved.
- **Sizing provenance is explicit.** `sizing_status` separates a member whose section
  came from a load calculation from one carried at an architectural convention.
- **The payload is grouped, not flat.** A member-level model repeats the same fifteen
  descriptive fields across hundreds of identical mullions. `ElementGroup` states them
  once and carries only the geometry and the lattice index per instance. `elements`
  expands the groups on demand, so every consumer still sees flat records while the JSON
  on the wire stays a fraction of the size.
"""

from __future__ import annotations

from functools import cached_property
from typing import Literal

from pydantic import BaseModel, Field

from .datums import DatumSet, Lattice
from .materials import MaterialSpec
from .spatial_rules import SpatialReport
from .geometry import BoxGeometry, ExtrusionGeometry, MemberGeometry, ProfileSpec, QuadGeometry, Vector3
from .program import ProgramAllocation

ElementKind = Literal[
    # structure
    'footing', 'piloti_column', 'column', 'primary_beam', 'secondary_joist',
    'brace', 'outrigger_strut', 'truss_chord', 'truss_web', 'purlin',
    'floor_slab', 'slab_fascia', 'podium_slab', 'roof_deck',
    # structure, by frame tectonic. A flat slab has no secondary tier and a drop panel
    # instead; a mass-timber floor is panel bands; a post-and-beam frame triangulates
    # every joint. These are different members, not the same member resized, which is
    # why the taxonomy has to name them separately.
    'drop_panel', 'shear_wall', 'clt_panel', 'core_wall', 'heavy_joist', 'knee_brace',
    # envelope
    'mullion', 'transom', 'glazing_panel', 'spandrel_panel', 'solid_wall_panel',
    'brise_soleil', 'parapet', 'screen_fin', 'entry_canopy',
    # envelope, by facade grammar. Each of these belongs to a drawing operation the
    # curtain wall does not perform: subtracting an opening from a wall, standing a
    # second structure in front of a skin, or applying an order to a flat elevation.
    'wall_panel', 'window_reveal', 'window_head', 'sill', 'slot_opening',
    'backing_panel', 'lattice_cell', 'lattice_mullion', 'lattice_transom',
    'field_panel', 'field_carrier', 'facet_panel', 'facet_glazing', 'seam_edge',
    'order_jamb', 'order_lintel', 'order_field',
    'frame_expression', 'external_strut',
    # circulation
    # A floor landing is flush with a plate and overlaps it; a half-landing is the
    # turn between two flights and is flush with nothing. They were one kind, which
    # made 'does this landing meet a floor' unaskable.
    'stair_tread', 'stair_stringer', 'stair_landing', 'stair_half_landing',
    'ceiling',
    'entrance_door',
    'entrance_head',
    'railing',
    'elevator_shaft', 'ramp',
    # A compliant ramp is not one object. It is runs, the landings between them,
    # and the edge protection along them, and a taxonomy that cannot name the parts
    # cannot record which one violated a clause.
    'ramp_landing', 'ramp_curb',
    # program
    'program_zone', 'partition', 'shelving_run', 'desk', 'seat', 'figure',
    # program, by spatial archetype (decision 0016). A riser is a walking surface a
    # seat row stands on; a stage platform is a raised working floor; a proscenium
    # wall is the one wall between house and stage, carrying the opening.
    'auditorium_riser', 'stage_platform', 'proscenium_wall',
    # A partition without an opening is a box. `door` is the opening, and
    # `partition_head` is the strip over it that carries the rating across the
    # doorway -- which is the part a rated wall lives or dies on.
    'door', 'partition_head',
    # site
    'site_ground', 'site_step',
]

SemanticLayer = Literal['structure', 'envelope', 'circulation', 'program', 'site']

SizingStatus = Literal[
    'sized_by_calculation',   # a member the load path check actually governed
    'architectural_convention',  # a dimension no structural check governs
    'not_applicable',
]

DependencyRelationType = Literal[
    'bears_on', 'anchors_to', 'fastens_to', 'hangs_from', 'hosts', 'abuts',
]

DependencyRole = Literal['gravity', 'lateral', 'assembly', 'containment', 'context']


class DependencyRoot(BaseModel):
    """An external end of a dependency path that is not generated geometry.

    Soil is deliberately a root rather than a fake building element.  The topology can
    therefore terminate explicitly while its bearing capacity remains visibly unchecked.
    """

    id: str
    kind: Literal['soil', 'grade']
    topology_status: Literal['verified', 'unresolved']
    capacity_status: Literal['not_checked', 'not_applicable']
    reason: str


class ElementDependency(BaseModel):
    """One directed construction relationship: dependent -> host."""

    id: str
    dependent_id: str
    host_id: str
    relation: DependencyRelationType
    role: DependencyRole
    connection_family: str
    topology_status: Literal['geometry_checked', 'rule_checked', 'unresolved']
    capacity_status: Literal['not_checked', 'not_applicable']
    basis: str


class DependencyEdge(BaseModel):
    """The only fields that differ inside one dependency relation family."""

    dependent_id: str
    host_id: str


class AxisReport(BaseModel):
    """What the centre-line skeleton found: joints by identity, not by proximity.

    Kept separate from `DependencyGraph` on purpose. The dependency graph is a pure
    function of the element groups -- recompiling it from them reproduces it exactly,
    and a test holds that line. These findings are not: they read the skeleton the
    emitters registered to as they ran, including the supports they declared before
    the dependency stage cleared and re-derived them. Folding the two together would
    have cost the graph its reproducibility to gain nothing.
    """

    schema_version: Literal['1.0'] = '1.0'
    status: Literal['passed', 'failed']
    node_count: int
    segment_count: int
    checks: list[DependencyCheck]


class DependencyRelationGroup(BaseModel):
    """Shared dependency semantics stated once for many element-to-host edges."""

    group_id: str
    relation: DependencyRelationType
    role: DependencyRole
    connection_family: str
    topology_status: Literal['geometry_checked', 'rule_checked', 'unresolved']
    capacity_status: Literal['not_checked', 'not_applicable']
    basis: str
    edges: list[DependencyEdge]

    def expand(self) -> list[ElementDependency]:
        return [ElementDependency(
            id=f'DEP-{edge.dependent_id}-TO-{edge.host_id}-{self.relation}',
            dependent_id=edge.dependent_id, host_id=edge.host_id,
            relation=self.relation, role=self.role,
            connection_family=self.connection_family,
            topology_status=self.topology_status,
            capacity_status=self.capacity_status, basis=self.basis)
            for edge in self.edges]


class DependencyExemption(BaseModel):
    """Why an object in the scene is not required to join the construction graph."""

    element_id: str
    reason: str


class DependencyCheck(BaseModel):
    id: str
    status: Literal['passed', 'failed', 'not_checked']
    message: str
    affected_ids: list[str] = Field(default_factory=list)


class DependencyGraph(BaseModel):
    """Machine-checkable support, host and assembly graph for one generated model.

    `status` certifies graph topology only.  It never certifies connection capacity,
    anchors, fasteners, soil bearing, or permit/code compliance.
    """

    schema_version: Literal['1.0'] = '1.0'
    status: Literal['passed', 'failed']
    roots: list[DependencyRoot]
    relation_groups: list[DependencyRelationGroup]
    exemptions: list[DependencyExemption]
    checks: list[DependencyCheck]
    required_element_count: int
    connected_element_count: int
    gravity_path_count: int
    connection_design_status: Literal['not_checked'] = 'not_checked'

    @cached_property
    def relations(self) -> list[ElementDependency]:
        return [relation for group in self.relation_groups for relation in group.expand()]


class ElementV3(BaseModel):
    id: str
    kind: ElementKind
    semantic_layer: SemanticLayer
    subsystem: str
    category: Literal['public', 'private', 'circulation', 'service', 'context']
    program: str = 'structure'
    level_id: str
    lattice_index: dict[str, int] = Field(default_factory=dict)
    geometry: BoxGeometry | MemberGeometry | ExtrusionGeometry | QuadGeometry = \
        Field(discriminator='type')
    material_profile: str
    # derived, read-only compatibility data for v2 consumers
    position: Vector3
    dimensions: Vector3
    datum_refs: list[str] = Field(default_factory=list)
    supports: list[str] = Field(default_factory=list)
    section_id: str | None = None
    # Construction depth of a sheet element, in metres. Members carry their section in
    # `section_id` and solids carry their own size; a quad has neither, so without this
    # a panel is a surface with no body -- it renders, and it cannot be cut. Set on the
    # envelope groups whose geometry is a quad; None everywhere else.
    thickness_m: float | None = None
    sizing_status: SizingStatus = 'not_applicable'
    utilisation: float | None = None
    governing_check: str | None = None
    rule_refs: list[str] = Field(default_factory=list)
    reason: str
    validation_status: Literal[
        'geometry_valid', 'professional_review_required', 'code_inputs_incomplete',
    ] = 'professional_review_required'


class ElementInstance(BaseModel):
    """What actually differs between two members of the same family."""

    id: str
    level_id: str
    lattice_index: dict[str, int] = Field(default_factory=dict)
    geometry: BoxGeometry | MemberGeometry | ExtrusionGeometry | QuadGeometry = \
        Field(discriminator='type')
    position: Vector3
    dimensions: Vector3
    supports: list[str] = Field(default_factory=list)


class DerivationStep(BaseModel):
    """One move in the reasoning that produced an element."""

    stage: Literal['feature', 'dimension', 'rule', 'datum',
                   'point', 'line', 'surface', 'solid', 'host', 'check']
    label: str
    value: str
    source: str
    why: str


class DerivationChain(BaseModel):
    """An element's reasoning, in the order a person would have reasoned it.

    Assembled rather than authored: every step is read off what the element already
    carries -- the datums it declared, the lattice indices it sits on, what it bears
    on, the section and the clause that fixed it. The value is the ordering. A panel of
    loose fields says what was recorded; a chain shows how the decision was made, and
    lets a reader find the step they disagree with.
    """

    schema_version: Literal['mta.derivation/1.0'] = 'mta.derivation/1.0'
    element_id: str
    kind: str
    level_id: str
    steps: list[DerivationStep]
    # A chain that never reaches a solid is incomplete; one that starts at a solid
    # skipped the reasoning. Both are stated rather than hidden.
    reaches_solid: bool
    starts_located: bool
    # Whether the chain reaches back to the recording. Not every element is driven by
    # the music -- a fire stair is required by code whatever the piece sounds like --
    # and the honest answer for those is no, not a fabricated musical cause.
    reaches_audio: bool = False
    rule_refs: list[str] = Field(default_factory=list)
    summary: str = ''


class ElementGroup(BaseModel):
    """One element family: the description once, the geometry per instance."""

    group_id: str
    kind: ElementKind
    semantic_layer: SemanticLayer
    subsystem: str
    category: Literal['public', 'private', 'circulation', 'service', 'context']
    program: str
    material_profile: str
    datum_refs: list[str] = Field(default_factory=list)
    section_id: str | None = None
    # Construction depth of a sheet element. A member carries its section and a solid
    # carries its own size; a quad has neither, so a panel without this is a surface
    # with no body -- it renders, and a cut plane cannot make anything of it.
    thickness_m: float | None = None
    sizing_status: SizingStatus = 'not_applicable'
    utilisation: float | None = None
    governing_check: str | None = None
    rule_refs: list[str] = Field(default_factory=list)
    reason: str
    validation_status: Literal[
        'geometry_valid', 'professional_review_required', 'code_inputs_incomplete',
    ] = 'professional_review_required'
    instances: list[ElementInstance]

    def expand(self) -> list[ElementV3]:
        return [
            ElementV3(
                id=instance.id, kind=self.kind, semantic_layer=self.semantic_layer,
                subsystem=self.subsystem, category=self.category, program=self.program,
                level_id=instance.level_id, lattice_index=instance.lattice_index,
                geometry=instance.geometry, material_profile=self.material_profile,
                position=instance.position, dimensions=instance.dimensions,
                datum_refs=self.datum_refs, supports=instance.supports,
                section_id=self.section_id, thickness_m=self.thickness_m,
                sizing_status=self.sizing_status,
                utilisation=self.utilisation, governing_check=self.governing_check,
                rule_refs=self.rule_refs, reason=self.reason,
                validation_status=self.validation_status)
            for instance in self.instances
        ]


class MemberSizingRecord(BaseModel):
    """One structural selection, kept beside the elements it produced."""

    role: str
    section_id: str
    material_id: str
    span_m: float
    tributary_width_m: float
    governing_check: str
    utilisation: float
    load_combination: str
    factored_load_kn_m: float
    element_count: int
    assumptions: list[str]


class AxisReading(BaseModel):
    """One architectural axis, and the musical evidence that placed the project on it."""

    axis: str
    value: float = Field(ge=0.0, le=1.0)
    sources: list[str]
    reason: str


class RankedOption(BaseModel):
    system_id: str
    grammar_id: str
    affinity: float


class SelectionRecord(BaseModel):
    """What was chosen, what the music asked for, and whether those agree.

    `preferred_grammar_id` is the music's answer with no screening applied;
    `grammar_id` is the answer after the screen. When they differ, `overruled_by_screen`
    is true and `overrule_reason` names the gate, so a reader is never left to infer
    that the building expresses a preference it was in fact denied.
    """

    program_id: str
    typology: str
    # The silhouette, chosen from the score before the lattice is built, because a
    # footprint cannot be decided after the levels are already standing in one.
    massing_id: str = 'MAS-SLAB'
    massing_label: str = 'Stacked slab'
    massing_reason: list[str] = Field(default_factory=list)
    system_id: str
    grammar_id: str
    frame_tectonic_id: str
    envelope_tectonic_id: str

    preferred_system_id: str
    preferred_grammar_id: str
    overruled_by_screen: bool
    overrule_reason: str | None = None

    axes: list[AxisReading]
    grammar_affinity: float
    system_affinity: float
    runner_up_grammar_id: str | None = None
    runner_up_margin: float | None = None

    # Every admissible pair this compiler can build, in the order the music prefers
    # them. The compiler walks this list when a preferred frame turns out not to be
    # sizeable: a glulam column that cannot carry 4000 kN is a correct engineering
    # result, and the run should record the fallback rather than crash on it.
    ranked_options: list[RankedOption] = Field(default_factory=list)
    # Set when the first choice failed its gravity check and a later option was
    # built instead. Names the member and the load, so the reason is legible.
    sizing_fallback: str | None = None
    admissible_systems: list[str]
    admissible_grammars: list[str]
    unbuildable_systems: dict[str, str]
    jurisdiction_resolved: bool
    note: str


class BuildingModelV3(BaseModel):
    schema_version: Literal['3.0'] = '3.0'
    model_id: str
    score_id: str
    typology: str
    tectonic_system: str
    structural_system_id: str
    # The facade grammar and the drawing operation its guide specifies. These were
    # implicit -- one grammar, one wall -- until the corpus test showed fourteen
    # recordings producing one elevation. They are recorded on the model because a
    # reader looking at a render needs to know which of the ten style guides governs
    # what they are seeing.
    facade_grammar_id: str = 'FCD-01-INTERNATIONAL-STYLE'
    envelope_tectonic_id: str = 'ENV-CURTAIN-WALL'
    # How the pair above was arrived at: what the music asked for, what the screen
    # allowed, and whether those agreed.
    selection: SelectionRecord | None = None
    units: Literal['meters'] = 'meters'
    coordinate_system: Literal['right_handed_z_up'] = 'right_handed_z_up'
    datum_set: DatumSet
    lattice: Lattice
    program_allocation: ProgramAllocation
    profiles: dict[str, ProfileSpec]
    sizing: list[MemberSizingRecord]
    element_groups: list[ElementGroup]
    element_counts: dict[str, int]
    layer_counts: dict[str, int]
    # What the grammar's own written guide asks of the elevation, checked against
    # what was actually emitted. A model that fails a gate is still returned; the
    # report is how a reader finds out.
    facade_gates: 'FacadeGateReport | None' = None
    # The accessible route, as the geometry that was checked rather than as a
    # claim about it. Exactly one of these is set: a plan whose `compliance()` is
    # empty, or the reason no compliant ramp fits and a stair was built instead.
    accessible_route: 'RampPlan | None' = None
    accessible_route_unresolved: str | None = None
    # Whether the building contains what a building must contain, and whether
    # everyone in it can get out. Both are reports rather than verdicts: they carry
    # what was checked, what failed, and what could not be evaluated at all.
    # Where the building is proposed to be, and what that place asks of it. Every
    # parameter carries its own provenance, so a reader can see which numbers a
    # person stood behind and which are still a proposal.
    site: 'SiteParameters | None' = None
    site_loads: 'SiteLoadSet | None' = None
    constitution: 'ConstitutionReport | None' = None
    life_safety: 'LifeSafetyGraph | None' = None
    # Every physical element either joins this typed graph or carries an explicit
    # exemption.  This is the cross-system seam between structure, envelope,
    # circulation, interior assemblies and site roots.
    dependency_graph: DependencyGraph | None = None
    # What each material key means, travelling with the model instead of being invented
    # by whichever renderer reads it. Carries the construction family as well as the
    # appearance, so a timber frame rendering as steel is a contradiction that can be
    # checked rather than a styling choice nobody notices.
    materials: dict[str, 'MaterialSpec'] = Field(default_factory=dict)
    # Where the members actually meet. The dependency graph says every element names
    # a host; this says the members that name each other share a node, which is a
    # different question and the one a tolerance kept answering wrongly.
    axis_report: 'AxisReport | None' = None
    # What the spatial archetype promised and what the built geometry measures back:
    # the rake's sightlines row by row, the plates its section claimed, the columns
    # still standing in the bowl. None on typologies that have no archetype.
    archetype: 'ArchetypeReport | None' = None
    # The things a person would have seen: two systems in one place, a surface that is
    # not level with the one you step onto it from, a gap you could fall through. The
    # other reports check relations and compliance; this one checks whether the model
    # is physically sensible, which nothing did before.
    spatial: 'SpatialReport | None' = None
    limitations: list[str]

    @cached_property
    def elements(self) -> list[ElementV3]:
        """Flat records, expanded from the groups. Consumers never see the compaction."""
        return [element for group in self.element_groups for element in group.expand()]

    @property
    def element_count(self) -> int:
        return sum(len(group.instances) for group in self.element_groups)

    @property
    def sized_element_count(self) -> int:
        return sum(len(group.instances) for group in self.element_groups
                   if group.sizing_status == 'sized_by_calculation')


# Imported at the foot for the same reason `models.py` imports its report there:
# `facade_gates` reads `grammar_specs`, which must not pull this module back in
# while it is still being defined.
from .ada import RampPlan  # noqa: E402
from .constitution import ConstitutionReport  # noqa: E402
from .site import SiteParameters  # noqa: E402
from .site_loads import SiteLoadSet  # noqa: E402
from .life_safety import LifeSafetyGraph  # noqa: E402
from .facade_gates import FacadeGateReport  # noqa: E402
from .archetypes import ArchetypeReport  # noqa: E402

BuildingModelV3.model_rebuild()
