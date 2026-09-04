"""The program constitution: what a building must contain before it is a building.

`docs/guidelines/program_constitution_guideline.md` sets out a base-building support
constitution and a relationship vocabulary, and neither reached the code. The briefs in
`briefs.py` list the rooms a client asks for -- galleries, reading rooms, an auditorium --
and none of the rooms a building needs in order to open: no public restrooms, no
accessible restroom, no janitor's closet, no electrical or IT room, no fire service
entry, no refuse holding, no riser zones. A model with 2,770 m2 of library and nowhere to
wash your hands is a schematic diagram of a library.

Three things the guideline asks for that the data model could not express:

- **Four distinct fields, not two.** §2 separates `program_category` (the visual and
  operational layer), `space_type` (the room's identity), `access_class` (who may enter)
  and `occupancy_use` (the code classification). `SpaceRequirement` carried category,
  type and occupancy and had no way to say that a staff workroom is staff-only while a
  gallery is public -- which is the field every service-route and egress question turns
  on.
- **Typed relationships.** §7 gives eight relations with different validators.
  `adjacency` was an untyped list of ids, so "the conservation studio must reach the
  store without crossing a public route" and "the cafe would be nice near the lobby"
  were the same statement.
- **A support constitution to check against.** §5 lists what is required, what is
  conditional and on what. Without it there is nothing to fail.

This module supplies all three and validates a brief against them. It does not invent
areas: where the guideline delegates a quantity to an adopted code profile -- restroom
fixture counts, mechanical area -- the requirement is recorded with its derivation
unresolved rather than filled in with a plausible number.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field

AccessClass = Literal['public', 'ticketed', 'staff', 'restricted', 'service']

# §7 relationship vocabulary. Each relation has a different validator, which is the
# reason they are not one list of neighbours.
Relation = Literal[
    'must_connect',        # direct door or open threshold
    'preferred_near',      # weighted proximity, not a hard requirement
    'must_separate',       # acoustic, security, hazard or operational separation
    'service_connect',     # continuous back-of-house route
    'public_connect',      # continuous public route
    'accessible_connect',  # continuous accessible route
    'vertical_align',      # wet stack, core or riser alignment
    'visual_connect',      # sightline or orientation
]

Necessity = Literal['required', 'conditional', 'optional']


class SupportRequirement(BaseModel):
    """One line of the base-building support constitution, §5."""

    id: str
    label: str
    space_type: str
    necessity: Necessity
    access_class: AccessClass
    condition: str = ''
    # Where the guideline hands a quantity to an adopted code profile rather than
    # publishing one, that is recorded here and the area stays unresolved.
    quantity_basis: str
    minimum_area_m2: float | None = None
    relations: list[tuple[Relation, str]] = Field(default_factory=list)
    reason: str


# §5. Every entry cites what the guideline says about it; nothing here is a number this
# project invented, and where a quantity belongs to a code profile the area is None.
BASE_BUILDING_SUPPORT: tuple[SupportRequirement, ...] = (
    SupportRequirement(
        id='SUP-ENTRY', label='Entry, vestibule and lobby', space_type='entry_lobby',
        necessity='required', access_class='public',
        quantity_basis='typology brief',
        reason='Legible arrival connected to the public way and to the primary public '
               'circulation. Required for any occupied public building.'),
    SupportRequirement(
        id='SUP-WC-PUBLIC', label='Public restrooms', space_type='public_restroom',
        necessity='required', access_class='public',
        condition='occupancy and fixture calculation',
        quantity_basis='adopted plumbing code fixture count; IPC Table 403.1 by '
                       'occupancy and occupant load. Not computed here.',
        relations=[('public_connect', 'SUP-ENTRY'), ('accessible_connect', 'SUP-ENTRY')],
        reason='Quantity and distribution derive from the adopted plumbing and '
               'accessibility rules, which this project does not carry. The requirement '
               'is recorded; the count is not invented.'),
    SupportRequirement(
        id='SUP-WC-STAFF', label='Staff or all-user restroom',
        space_type='staff_restroom', necessity='conditional', access_class='staff',
        condition='a staff or restricted zone exists',
        quantity_basis='adopted plumbing code',
        relations=[('must_separate', 'SUP-WC-PUBLIC')],
        reason='Serves staff and restricted zones without routing through controlled '
               'public space.'),
    SupportRequirement(
        id='SUP-JANITOR', label='Janitor and custodial closet', space_type='janitor',
        necessity='required', access_class='service', minimum_area_m2=8.0,
        quantity_basis='one per floor, service sink requirement delegated to the code '
                       'profile',
        relations=[('service_connect', 'SUP-REFUSE')],
        reason='Normally required. Without it the cleaning of every other room has no '
               'place to happen.'),
    SupportRequirement(
        id='SUP-ELEC', label='Electrical and IT room', space_type='electrical_it',
        necessity='required', access_class='restricted', minimum_area_m2=18.0,
        quantity_basis='distribution assumption; riser alignment required',
        relations=[('vertical_align', 'SUP-RISER'), ('service_connect', 'SUP-LOADING')],
        reason='Restricted access with a serviceable route. Equipment has to arrive and '
               'be replaced.'),
    SupportRequirement(
        id='SUP-MECH', label='Mechanical room and shafts', space_type='mechanical',
        necessity='required', access_class='restricted',
        quantity_basis='derived from the system assumption, with a replacement path '
                       'noted. No system is selected here, so no area is asserted.',
        relations=[('vertical_align', 'SUP-RISER')],
        reason='Area and distribution follow the mechanical system, which this project '
               'does not choose.'),
    SupportRequirement(
        id='SUP-FIRE', label='Fire and sprinkler service', space_type='fire_service',
        necessity='conditional', access_class='service', minimum_area_m2=12.0,
        condition='required by the adopted fire and building rules',
        quantity_basis='adopted fire code; reserved when required',
        reason='Reserved rather than sized, because whether it is required and how large '
               'both depend on a jurisdiction this run does not resolve.'),
    SupportRequirement(
        id='SUP-STORE', label='General storage', space_type='general_storage',
        necessity='required', access_class='staff',
        quantity_basis='typology and operations; explicitly separate from egress width',
        relations=[('service_connect', 'SUP-LOADING')],
        reason='Sized from operations. The guideline is explicit that it must not be '
               'taken out of egress width.'),
    SupportRequirement(
        id='SUP-REFUSE', label='Refuse and recycling', space_type='refuse',
        necessity='required', access_class='service', minimum_area_m2=14.0,
        quantity_basis='operations; service route to the exterior',
        relations=[('service_connect', 'SUP-LOADING'),
                   ('must_separate', 'SUP-ENTRY')],
        reason='Needs a service route out that does not cross the primary public '
               'sequence where practical.'),
    SupportRequirement(
        id='SUP-CIRC', label='Horizontal circulation', space_type='circulation',
        necessity='required', access_class='public',
        quantity_basis='continuous graph, not an area target',
        relations=[('public_connect', 'SUP-ENTRY'),
                   ('accessible_connect', 'SUP-ENTRY')],
        reason='A continuous graph connecting occupied spaces, exits, the accessible '
               'route and the service zones. It is a connectivity requirement first and '
               'an area second.'),
    SupportRequirement(
        id='SUP-EXITS', label='Protected stairs and exits', space_type='exit_stair',
        necessity='required', access_class='public',
        condition='number, remoteness, width and enclosure by storeys, occupant load '
                  'and travel distance',
        quantity_basis='IBC Chapter 10; computed in `life_safety.py`',
        relations=[('public_connect', 'SUP-CIRC')],
        reason='The one support requirement this project does compute rather than '
               'delegate.'),
    SupportRequirement(
        id='SUP-LIFT', label='Elevator or lift', space_type='elevator',
        necessity='conditional', access_class='public',
        condition='more than one occupied storey, or an accessible route that needs it',
        quantity_basis='accessible route and operational service need, tracked '
                       'separately',
        relations=[('accessible_connect', 'SUP-ENTRY'), ('vertical_align', 'SUP-RISER')],
        reason='A multi-storey accessible route needs one. ADA 206.2.3 is the trigger, '
               'not a preference.'),
    SupportRequirement(
        id='SUP-LOADING', label='Loading and receiving', space_type='loading',
        necessity='conditional', access_class='service', minimum_area_m2=30.0,
        condition='typology and scale',
        relations=[('service_connect', 'SUP-STORE')],
        quantity_basis='typology and operations',
        reason='A direct service route to storage, stage, collection or back-of-house.'),
    SupportRequirement(
        id='SUP-STAFF', label='Staff support', space_type='staff_support',
        necessity='conditional', access_class='staff',
        condition='the operating model has resident staff',
        quantity_basis='brief and operating model',
        relations=[('must_separate', 'SUP-ENTRY')],
        reason='Workroom, break, lockers and staff storage.'),
    SupportRequirement(
        id='SUP-RISER', label='Vertical riser zones', space_type='riser',
        necessity='required', access_class='restricted', minimum_area_m2=6.0,
        quantity_basis='aligned wet, mechanical, electrical and fire-service '
                       'distribution',
        reason='Normally required, and the one support space whose whole purpose is to '
               'line up on every floor.'),
)

SUPPORT_BY_ID: dict[str, SupportRequirement] = {s.id: s for s in BASE_BUILDING_SUPPORT}


# ---------------------------------------------------------------------------
# Validation, guideline §10
# ---------------------------------------------------------------------------

class ConstitutionFinding(BaseModel):
    """One requirement, and whether the brief satisfies it."""

    requirement_id: str
    label: str
    necessity: Necessity
    status: Literal['satisfied', 'missing', 'unresolved']
    matched_space_id: str | None = None
    detail: str


class ConstitutionReport(BaseModel):
    typology: str
    findings: list[ConstitutionFinding]

    @property
    def missing_required(self) -> list[ConstitutionFinding]:
        return [f for f in self.findings
                if f.status == 'missing' and f.necessity == 'required']

    @property
    def unresolved(self) -> list[ConstitutionFinding]:
        return [f for f in self.findings if f.status == 'unresolved']

    @property
    def satisfied(self) -> list[ConstitutionFinding]:
        return [f for f in self.findings if f.status == 'satisfied']

    @property
    def complete(self) -> bool:
        return not self.missing_required

    def summary(self) -> str:
        return (f'{self.typology}: {len(self.satisfied)}/{len(self.findings)} support '
                f'requirements satisfied, {len(self.missing_required)} required ones '
                f'missing, {len(self.unresolved)} delegated to a code profile this run '
                f'does not carry')


# Which brief space types stand in for which support requirement. Recorded rather than
# guessed at match time, so a brief that renames a room does not silently satisfy a
# requirement it does not meet.
_SATISFIED_BY: dict[str, tuple[str, ...]] = {
    # A theatre foyer is the entry lobby -- it is where the public way meets the
    # building. Listed rather than matched loosely, so a brief that renames a room
    # cannot silently satisfy a requirement it does not meet; that is also why the
    # rename cost a `missing` finding here until this line was added, which is the
    # check doing its job.
    'SUP-ENTRY': ('lobby_welcome_checkout', 'entry_lobby', 'theatre_foyer'),
    'SUP-WC-PUBLIC': ('public_restroom',),
    'SUP-WC-STAFF': ('staff_restroom',),
    'SUP-JANITOR': ('janitor',),
    'SUP-ELEC': ('electrical_it',),
    'SUP-MECH': ('plant', 'mechanical'),
    'SUP-FIRE': ('fire_service',),
    'SUP-STORE': ('general_storage', 'closed_stack'),
    'SUP-REFUSE': ('refuse',),
    'SUP-CIRC': ('circulation',),
    'SUP-EXITS': ('exit_stair',),
    'SUP-LIFT': ('elevator',),
    'SUP-LOADING': ('loading',),
    'SUP-STAFF': ('staff_workroom', 'staff_support'),
    'SUP-RISER': ('riser',),
}


def validate_brief(typology: str, brief, *, storeys: int = 1) -> ConstitutionReport:
    """Check one brief against the base-building support constitution.

    `unresolved` is a distinct verdict from `missing` and the distinction matters: a
    public restroom whose fixture count belongs to a plumbing code this project does not
    carry is not the same problem as a janitor's closet nobody thought of. One needs a
    code profile; the other needs a room.
    """
    present: dict[str, str] = {}
    for space in brief:
        for requirement_id, types in _SATISFIED_BY.items():
            if space.space_type in types and requirement_id not in present:
                present[requirement_id] = space.id

    findings: list[ConstitutionFinding] = []
    for requirement in BASE_BUILDING_SUPPORT:
        if requirement.id == 'SUP-LIFT' and storeys <= 1:
            findings.append(ConstitutionFinding(
                requirement_id=requirement.id, label=requirement.label,
                necessity=requirement.necessity, status='satisfied',
                detail='Single storey: no vertical accessible route is required.'))
            continue
        if (requirement.id == 'SUP-LOADING'
                and typology not in ('museum', 'theater')):
            findings.append(ConstitutionFinding(
                requirement_id=requirement.id, label=requirement.label,
                necessity=requirement.necessity, status='satisfied',
                detail='Conditional on typology and scale; a library or a pavilion '
                       'does not receive collections or scenery by lorry.'))
            continue
        matched = present.get(requirement.id)
        if matched:
            findings.append(ConstitutionFinding(
                requirement_id=requirement.id, label=requirement.label,
                necessity=requirement.necessity, status='satisfied',
                matched_space_id=matched,
                detail=f'Provided by {matched}.'))
        elif requirement.minimum_area_m2 is None and 'code' in requirement.quantity_basis:
            findings.append(ConstitutionFinding(
                requirement_id=requirement.id, label=requirement.label,
                necessity=requirement.necessity, status='unresolved',
                detail=f'{requirement.quantity_basis} The requirement stands; the '
                       f'quantity is not invented.'))
        else:
            findings.append(ConstitutionFinding(
                requirement_id=requirement.id, label=requirement.label,
                necessity=requirement.necessity, status='missing',
                detail=requirement.reason))
    return ConstitutionReport(typology=typology, findings=findings)


# ---------------------------------------------------------------------------
# Occupant load, IBC Table 1004.5
# ---------------------------------------------------------------------------
#
# Square metres of floor area per occupant, the published values converted once.
# Occupant load is the input to almost everything downstream -- fixture counts, exit
# numbers, egress width -- so taking it from a table rather than a guess is what makes
# the rest of the chain checkable.

OCCUPANT_LOAD_FACTOR_M2: dict[str, float] = {
    'assembly_concentrated_chairs': 0.65,   # 7 ft2 net
    'assembly_unconcentrated': 1.39,        # 15 ft2 net
    'assembly_standing': 0.46,              # 5 ft2 net
    'business': 13.94,                      # 150 ft2 gross
    'educational_classroom': 1.86,          # 20 ft2 net
    'exhibit_gallery_museum': 2.79,         # 30 ft2 gross
    'library_reading': 4.65,                # 50 ft2 net
    'library_stacks': 9.29,                 # 100 ft2 gross
    'mercantile': 5.57,                     # 60 ft2 gross
    'stage': 1.39,                          # 15 ft2 net
    'kitchen_commercial': 18.58,            # 200 ft2 gross
    'mechanical_equipment': 27.87,          # 300 ft2 gross
    'storage': 27.87,                       # 300 ft2 gross
}

# Which factor a brief space type uses. A type with no entry falls back to business, and
# that fallback is reported on the record rather than applied silently.
_OCCUPANT_FACTOR_BY_TYPE: dict[str, str] = {
    'lobby_welcome_checkout': 'assembly_unconcentrated',
    'entry_lobby': 'assembly_unconcentrated',
    'exhibition_foyer': 'exhibit_gallery_museum',
    # The theatre. These carried a gallery's factor while they carried a gallery's
    # type; with their own types they would have fallen back to `business` at
    # 13.94 m2 per person -- an auditorium counted as an open-plan office, which is a
    # tenth of the people and therefore a tenth of the egress. Occupant load is the
    # input to exit counts and widths, so a wrong factor here is wrong stairs.
    'auditorium': 'assembly_concentrated_chairs',
    'stage': 'stage',
    # The foyer keeps the factor a lobby already had. Standing space at 0.46 m2 is
    # arguably what an interval is, but renaming a room is not a reason to change its
    # occupant load: only the two whose previous factor was wrong for what they are
    # move here.
    'theatre_foyer': 'assembly_unconcentrated',
    'cafe': 'assembly_unconcentrated',
    'children_reading': 'library_reading',
    'adult_reading': 'library_reading',
    'reading_room': 'library_reading',
    'periodicals': 'library_reading',
    'open_stack': 'library_stacks',
    'closed_stack': 'library_stacks',
    'general_storage': 'storage',
    'seminar': 'educational_classroom',
    'staff_workroom': 'business',
    'staff_support': 'business',
    'plant': 'mechanical_equipment',
    'mechanical': 'mechanical_equipment',
    'electrical_it': 'mechanical_equipment',
    'riser': 'mechanical_equipment',
    'janitor': 'storage',
    'refuse': 'storage',
    'loading': 'storage',
    'fire_service': 'mechanical_equipment',
    'public_restroom': 'business',
    'staff_restroom': 'business',
}


class OccupantLoad(BaseModel):
    space_id: str
    label: str
    area_m2: float
    factor_key: str
    factor_m2: float
    occupants: int
    defaulted: bool
    basis: str


def occupant_load(brief) -> list[OccupantLoad]:
    """Occupant load per space, IBC 1004.5, from the brief areas."""
    out: list[OccupantLoad] = []
    for space in brief:
        key = _OCCUPANT_FACTOR_BY_TYPE.get(space.space_type)
        defaulted = key is None
        key = key or 'business'
        factor = OCCUPANT_LOAD_FACTOR_M2[key]
        out.append(OccupantLoad(
            space_id=space.id, label=space.label, area_m2=space.area_m2,
            factor_key=key, factor_m2=factor,
            occupants=max(1, math.ceil(space.area_m2 / factor)),
            defaulted=defaulted,
            basis=(f'IBC Table 1004.5, {key} at {factor:.2f} m2 per occupant'
                   + (' (no entry for this space type; business assumed and reported)'
                      if defaulted else ''))))
    return out


def total_occupant_load(brief) -> int:
    return sum(entry.occupants for entry in occupant_load(brief))


# ---------------------------------------------------------------------------
# Generating the support a brief omits
# ---------------------------------------------------------------------------

def support_spaces(typology: str, brief, *, storeys: int) -> list:
    """The base-building support the constitution requires and the brief leaves out.

    Generated rather than typed into each brief, so adding a requirement to the
    constitution reaches every typology at once instead of three out of four.

    The areas are the honest part. Where the guideline delegates a quantity to a code
    profile -- restroom fixtures to the adopted plumbing code, mechanical area to the
    system selection -- the area here is a **placeholder sized to hold the function**,
    and the space says so in its own reason. A placeholder that announces itself is
    usable; one that does not is a fabricated compliance.
    """
    from .program import SpaceRequirement

    occupants = total_occupant_load(brief)
    present = {space.space_type for space in brief}
    out: list = []

    def add(space_id: str, space_type: str, label: str, category: str, area: float,
            min_dim: float, level: str, occupancy: str, reason: str) -> None:
        if space_type in present:
            return
        out.append(SpaceRequirement(
            id=space_id, space_type=space_type, label=label, category=category,
            area_m2=round(area, 1), min_dimension_m=min_dim,
            level_preference=level, daylight='none', occupancy_id=occupancy,
            adjacency=[], reason=reason))

    add('SP-WC-PUBLIC', 'public_restroom', 'Public restrooms', 'public',
        max(28.0, occupants * 0.09), 4.0, 'any', 'lobby_first_corridor',
        f'Constitution SUP-WC-PUBLIC. Placeholder area at 0.09 m2 per occupant for '
        f'{occupants} occupants. The fixture count that actually sizes this comes from '
        f'the adopted plumbing code, which this project does not carry.')
    add('SP-WC-STAFF', 'staff_restroom', 'Staff restroom', 'private',
        14.0, 3.0, 'any', 'office',
        'Constitution SUP-WC-STAFF. Serves the staff zone without routing through '
        'controlled public space. Fixture count delegated to the plumbing code.')
    add('SP-JANITOR', 'janitor', 'Janitor closet', 'service',
        10.0, 2.4, 'any', 'office',
        'Constitution SUP-JANITOR. The service sink requirement is delegated to the '
        'code profile; the room itself is required.')
    add('SP-ELEC', 'electrical_it', 'Electrical and IT', 'service',
        22.0, 3.5, 'any', 'library_stacks',
        'Constitution SUP-ELEC. Restricted access with a route wide enough to replace '
        'the equipment. Loaded as a heavy floor.')
    add('SP-RISER', 'riser', 'Vertical riser zone', 'service',
        8.0, 1.8, 'any', 'library_stacks',
        'Constitution SUP-RISER. Aligned wet, mechanical, electrical and fire-service '
        'distribution. Vertical alignment is required by the constitution and is not '
        'yet enforced by the allocator, which is a gap rather than a decision.')
    add('SP-MECH', 'mechanical', 'Mechanical plant', 'service',
        max(60.0, occupants * 0.16), 5.0, 'any', 'library_stacks',
        'Constitution SUP-MECH. Placeholder at 0.16 m2 per occupant. The area that '
        'actually sizes this follows the mechanical system, which this project does '
        'not select, and the replacement path the guideline asks for is not modelled.')
    add('SP-FIRE', 'fire_service', 'Fire service entry', 'service',
        12.0, 2.5, 'ground', 'library_stacks',
        'Constitution SUP-FIRE. Reserved rather than sized: whether it is required and '
        'how large both depend on a jurisdiction this run does not resolve.')
    add('SP-REFUSE', 'refuse', 'Refuse and recycling', 'service',
        16.0, 3.0, 'ground', 'library_stacks',
        'Constitution SUP-REFUSE. Needs a service route to the exterior that does not '
        'cross the primary public sequence.')
    add('SP-GENSTORE', 'general_storage', 'General storage', 'service',
        max(40.0, occupants * 0.08), 4.0, 'any', 'library_stacks',
        'Constitution SUP-STORE. Sized from operations and explicitly separate from '
        'egress width, which the guideline calls out because taking one from the other '
        'is a common and dangerous shortcut.')
    # Whether a typology needs a dock is a typology fact, so the kit states it; a
    # membership test here was one of the four scattered places a new typology had to
    # know to edit, and the one that failed silently when it was missed.
    from .typology import kit_for
    if kit_for(typology).requires_loading_dock:
        add('SP-LOADING', 'loading', 'Loading and receiving', 'service',
            36.0, 5.0, 'ground', 'library_stacks',
            'Constitution SUP-LOADING. A direct service route to the store, the stage '
            'or the collection.')
    return out


# Support requirements that no brief satisfies because they are not brief spaces. A
# client does not ask for a stair; the building needs one. `compiler_v3` emits all three
# as geometry, so they are checked against the model rather than against the room list.
_SATISFIED_BY_GEOMETRY: dict[str, tuple[str, ...]] = {
    'SUP-CIRC': ('stair_tread', 'stair_landing', 'ramp'),
    'SUP-EXITS': ('stair_landing', 'stair_tread'),
    'SUP-LIFT': ('elevator_shaft',),
}


def validate_model(typology: str, brief, model) -> ConstitutionReport:
    """Check the constitution against the brief *and* the geometry that was built.

    Splitting it this way is not bookkeeping. Circulation, protected stairs and the lift
    are required of every building and are absent from every brief, because a client
    does not ask for a stair -- they ask for reading rooms and assume the stair. Checking
    them against the room list would report three permanent failures on a building that
    has all three, and a validator that always fails is a validator nobody reads.
    """
    report = validate_brief(typology, brief,
                            storeys=len(model.lattice.occupied))
    built = set(model.element_counts)
    findings: list[ConstitutionFinding] = []
    for finding in report.findings:
        kinds = _SATISFIED_BY_GEOMETRY.get(finding.requirement_id)
        if kinds and finding.status != 'satisfied':
            present = [k for k in kinds if model.element_counts.get(k, 0) > 0]
            if present:
                findings.append(finding.model_copy(update={
                    'status': 'satisfied',
                    'detail': ('Built as geometry rather than briefed as a room: '
                               + ', '.join(f'{k} x{model.element_counts[k]}'
                                           for k in present) + '.')}))
                continue
        findings.append(finding)
    return ConstitutionReport(typology=typology, findings=findings)
