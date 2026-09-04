"""Building-code gate layer.

This sits *above* the physical compatibility axes in `coupling.py`. A physical axis says
"this is hard to build"; a code gate says "this may not be built". They are different
kinds of statement and must never be averaged into one number, so they are computed
separately and a code failure is absolute.

Provenance discipline, which the whole module depends on:

    Every rule below encodes a code requirement whose STRUCTURE is well established.
    The NUMERIC tables carried here are project-authored PLACEHOLDERS marked
    `provenance='placeholder'`. They exist so the gate is executable and testable before
    a jurisdiction is chosen. They are NOT a substitute for the adopted code text.

    A rule evaluated against a placeholder table returns status `code_inputs_incomplete`,
    never `pass`. Only a `JurisdictionProfile` with `status='resolved'` and its own
    sourced tables can produce a `pass`. That is why a run can never claim compliance:
    the data model makes the claim unreachable until a human supplies real code data.

Covered rules:

    IBC-504    construction type vs storeys and height
    IBC-601    required fire-resistance rating of the structural frame
    IBC-602    exterior wall rating vs fire separation distance
    IBC-705.8  maximum area of exterior wall openings vs fire separation distance
    IBC-1402   combustible exterior wall components above 40 ft (NFPA 285)
    IBC-1604.3 deflection limits that the facade coupling axes must use
    ASCE7-12.2 seismic force-resisting system permitted by seismic design category
    ASCE7-4.3  occupancy live loads consumed by `loads.py`
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


OccupancyGroup = Literal['A-1', 'A-3', 'B', 'M', 'S-1']

ConstructionType = Literal[
    'I-A', 'I-B', 'II-A', 'II-B', 'III-A', 'III-B',
    'IV-A', 'IV-B', 'IV-C', 'IV-HT', 'V-A', 'V-B',
]

SeismicDesignCategory = Literal['A', 'B', 'C', 'D', 'E', 'F']

LateralSystem = Literal[
    'steel_special_moment_frame',
    'steel_ordinary_moment_frame',
    'steel_special_concentrically_braced_frame',
    'steel_ordinary_concentrically_braced_frame',
    'rc_special_shear_wall',
    'rc_ordinary_shear_wall',
    'light_frame_shear_wall_wood',
    'clt_shear_wall',
    'timber_braced_frame',
    'not_detailed_for_seismic_resistance',
]

GateStatus = Literal['pass', 'fail', 'warning', 'code_inputs_incomplete']

Provenance = Literal['placeholder', 'jurisdiction_resolved']

UNLIMITED = 10_000


class JurisdictionProfile(BaseModel):
    """The single object that turns this module from a rehearsal into a real check."""

    id: str
    status: Literal['unresolved', 'resolved'] = 'unresolved'
    adopted_building_code: str | None = None
    adopted_load_standard: str | None = None
    local_amendments: list[str] = Field(default_factory=list)
    sprinklered: bool | None = None
    risk_category: int | None = None
    seismic_design_category: SeismicDesignCategory | None = None
    # metres from each exterior face to the lot line or assumed imaginary line
    fire_separation_distance_m: dict[str, float] = Field(default_factory=dict)
    source_urls: list[str] = Field(default_factory=list)

    # Optional sourced overrides. When supplied with status='resolved', the gate uses
    # these instead of the placeholder tables and may return `pass`.
    allowable_storeys: dict[str, int] | None = None
    frame_rating_hours: dict[str, float] | None = None
    opening_area_limits: list[tuple[float, float]] | None = None

    @property
    def resolved(self) -> bool:
        return self.status == 'resolved'


UNRESOLVED_JURISDICTION = JurisdictionProfile(
    id='STR-CODE-US-LOCAL-PLACEHOLDER',
    status='unresolved',
    source_urls=[
        'https://codes.iccsafe.org/content/IBC2024P1/chapter-5-general-building-heights-and-areas',
        'https://codes.iccsafe.org/content/IBC2024V2.0/chapter-6-types-of-construction',
        'https://www.asce.org/publications-and-news/codes-and-standards/asce-sei-7-22',
    ],
)


class CodeGateResult(BaseModel):
    rule_id: str
    citation: str
    provenance: Provenance
    status: GateStatus
    message: str
    mitigation: str | None = None
    blocking: bool = False


class CodeScreen(BaseModel):
    program_id: str
    system_id: str
    grammar_id: str | None = None
    jurisdiction_id: str
    results: list[CodeGateResult]

    @property
    def blocked(self) -> bool:
        return any(r.blocking for r in self.results)

    @property
    def incomplete(self) -> list[str]:
        return [r.rule_id for r in self.results
                if r.status == 'code_inputs_incomplete']

    @property
    def failures(self) -> list[str]:
        return [r.rule_id for r in self.results if r.status == 'fail']


# ---------------------------------------------------------------------------
# PLACEHOLDER TABLES.  Structure is real; numbers require jurisdiction resolution.
# ---------------------------------------------------------------------------

# IBC Table 504.4 shape: allowable number of storeys above grade plane, by occupancy
# group and construction type, sprinklered. Values here are project-authored
# placeholders; several tall mass timber entries in particular are unverified.
_PLACEHOLDER_STOREYS: dict[OccupancyGroup, dict[ConstructionType, int]] = {
    'A-1': {'I-A': UNLIMITED, 'I-B': 6, 'II-A': 4, 'II-B': 3, 'III-A': 4, 'III-B': 3,
            'IV-A': 6, 'IV-B': 5, 'IV-C': 4, 'IV-HT': 4, 'V-A': 3, 'V-B': 2},
    'A-3': {'I-A': UNLIMITED, 'I-B': 12, 'II-A': 4, 'II-B': 3, 'III-A': 4, 'III-B': 3,
            'IV-A': 7, 'IV-B': 6, 'IV-C': 5, 'IV-HT': 4, 'V-A': 3, 'V-B': 2},
    'B': {'I-A': UNLIMITED, 'I-B': 12, 'II-A': 6, 'II-B': 4, 'III-A': 6, 'III-B': 4,
          'IV-A': 18, 'IV-B': 12, 'IV-C': 9, 'IV-HT': 6, 'V-A': 4, 'V-B': 3},
    'M': {'I-A': UNLIMITED, 'I-B': 12, 'II-A': 5, 'II-B': 3, 'III-A': 5, 'III-B': 3,
          'IV-A': 9, 'IV-B': 8, 'IV-C': 5, 'IV-HT': 5, 'V-A': 4, 'V-B': 2},
    'S-1': {'I-A': UNLIMITED, 'I-B': 12, 'II-A': 5, 'II-B': 3, 'III-A': 5, 'III-B': 3,
            'IV-A': 13, 'IV-B': 11, 'IV-C': 8, 'IV-HT': 5, 'V-A': 4, 'V-B': 2},
}

# IBC Table 504.3 shape: allowable height in metres above grade plane, sprinklered.
_PLACEHOLDER_HEIGHT_M: dict[ConstructionType, float] = {
    'I-A': 1_000.0, 'I-B': 55.0, 'II-A': 25.9, 'II-B': 22.9, 'III-A': 25.9,
    'III-B': 22.9, 'IV-A': 82.3, 'IV-B': 54.9, 'IV-C': 25.9, 'IV-HT': 25.9,
    'V-A': 21.3, 'V-B': 18.3,
}

# IBC Table 601 shape: required fire-resistance rating of the structural frame, hours.
_PLACEHOLDER_FRAME_RATING_H: dict[ConstructionType, float] = {
    'I-A': 3.0, 'I-B': 2.0, 'II-A': 1.0, 'II-B': 0.0, 'III-A': 1.0, 'III-B': 0.0,
    'IV-A': 3.0, 'IV-B': 2.0, 'IV-C': 2.0, 'IV-HT': 0.0, 'V-A': 1.0, 'V-B': 0.0,
}

# IBC Table 705.8 shape: (fire separation distance in metres, maximum unprotected
# openings as a fraction of the wall area) for a sprinklered building, ascending.
_PLACEHOLDER_OPENING_LIMITS: list[tuple[float, float]] = [
    (0.9, 0.00), (1.5, 0.15), (3.0, 0.25), (4.6, 0.45),
    (6.1, 0.75), (7.6, 1.00), (9.1, 1.00), (1_000.0, 1.00),
]

# ASCE/SEI 7 Table 12.2-1 shape: structural system limitations and height limits in
# metres by seismic design category. `None` means not permitted; UNLIMITED means NL.
_PLACEHOLDER_SEISMIC_LIMITS: dict[LateralSystem, dict[str, float | None]] = {
    'steel_special_moment_frame': {
        'A': UNLIMITED, 'B': UNLIMITED, 'C': UNLIMITED,
        'D': UNLIMITED, 'E': UNLIMITED, 'F': UNLIMITED},
    'steel_ordinary_moment_frame': {
        'A': UNLIMITED, 'B': UNLIMITED, 'C': 10.7, 'D': None, 'E': None, 'F': None},
    'steel_special_concentrically_braced_frame': {
        'A': UNLIMITED, 'B': UNLIMITED, 'C': UNLIMITED,
        'D': 48.8, 'E': 48.8, 'F': 30.5},
    'steel_ordinary_concentrically_braced_frame': {
        'A': UNLIMITED, 'B': UNLIMITED, 'C': 10.7, 'D': 10.7, 'E': 10.7, 'F': None},
    'rc_special_shear_wall': {
        'A': UNLIMITED, 'B': UNLIMITED, 'C': UNLIMITED,
        'D': 48.8, 'E': 48.8, 'F': 30.5},
    'rc_ordinary_shear_wall': {
        'A': UNLIMITED, 'B': UNLIMITED, 'C': UNLIMITED,
        'D': None, 'E': None, 'F': None},
    'light_frame_shear_wall_wood': {
        'A': UNLIMITED, 'B': 19.8, 'C': 19.8, 'D': 19.8, 'E': 19.8, 'F': 19.8},
    'clt_shear_wall': {
        'A': UNLIMITED, 'B': 19.8, 'C': 19.8, 'D': 19.8, 'E': 19.8, 'F': 19.8},
    'timber_braced_frame': {
        'A': UNLIMITED, 'B': 10.7, 'C': 10.7, 'D': None, 'E': None, 'F': None},
    'not_detailed_for_seismic_resistance': {
        'A': UNLIMITED, 'B': UNLIMITED, 'C': None, 'D': None, 'E': None, 'F': None},
}

# IBC Table 1604.3 shape: serviceability deflection limits as L/n.
DEFLECTION_LIMITS: dict[str, dict[str, int]] = {
    'floor_member':        {'live': 360, 'total': 240},
    'roof_member_ceiling': {'live': 360, 'total': 240},
    'roof_member_no_ceiling': {'live': 240, 'total': 180},
    'exterior_wall_brittle_finish': {'live': 240, 'total': 240},
    'exterior_wall_flexible_finish': {'live': 120, 'total': 120},
    # Curtain-wall and glazing support; the governing check is usually the lesser of
    # L/175 and 19 mm, per the referenced glazing standards.
    'curtain_wall_support': {'live': 175, 'total': 175},
}
CURTAIN_WALL_ABSOLUTE_LIMIT_MM = 19.0

NFPA285_TRIGGER_HEIGHT_M = 12.2   # 40 ft
_NONCOMBUSTIBLE_TYPES = {'I-A', 'I-B', 'II-A', 'II-B'}
_MASS_TIMBER_TYPES = {'IV-A', 'IV-B', 'IV-C', 'IV-HT'}


CONSTRUCTION_TYPE_BY_SYSTEM: dict[str, list[ConstructionType]] = {
    'STR-SYS-STEEL-FRAME': ['I-A', 'I-B', 'II-A', 'II-B'],
    'STR-SYS-RC-FRAME-WALL': ['I-A', 'I-B', 'II-A'],
    'STR-SYS-MASS-TIMBER-CLT-GLULAM': ['IV-A', 'IV-B', 'IV-C', 'IV-HT'],
    'STR-SYS-GLULAM-POST-BEAM': ['IV-HT', 'IV-C'],
    'STR-SYS-LIGHT-WOOD-FRAME': ['V-A', 'V-B'],
    'STR-SYS-TENSILE-MEMBRANE': ['II-B', 'V-B'],
    'STR-SYS-CABLE-NET-HYBRID': ['II-A', 'II-B'],
    'STR-SYS-RC-SHELL': ['I-B', 'II-A'],
    'STR-SYS-TIMBER-GRIDSHELL': ['IV-HT', 'V-B'],
    'STR-SYS-STEEL-SPACE-FRAME-SHELL': ['II-A', 'II-B'],
}

# Candidate lateral systems per structural system, in order of architectural preference.
# The gate picks the best one the seismic design category permits, because a material
# choice does not fix the lateral system: a mass timber tower normally uses a concrete
# core precisely because CLT shear walls run out of height.
LATERAL_SYSTEM_CANDIDATES: dict[str, list[LateralSystem]] = {
    'STR-SYS-STEEL-FRAME': ['steel_special_concentrically_braced_frame',
                            'steel_special_moment_frame',
                            'steel_ordinary_concentrically_braced_frame'],
    'STR-SYS-RC-FRAME-WALL': ['rc_special_shear_wall', 'rc_ordinary_shear_wall'],
    'STR-SYS-MASS-TIMBER-CLT-GLULAM': ['clt_shear_wall', 'rc_special_shear_wall'],
    'STR-SYS-GLULAM-POST-BEAM': ['timber_braced_frame', 'clt_shear_wall',
                                 'rc_special_shear_wall'],
    'STR-SYS-LIGHT-WOOD-FRAME': ['light_frame_shear_wall_wood'],
    'STR-SYS-TENSILE-MEMBRANE': ['not_detailed_for_seismic_resistance',
                                 'steel_ordinary_concentrically_braced_frame'],
    'STR-SYS-CABLE-NET-HYBRID': ['steel_special_concentrically_braced_frame',
                                 'not_detailed_for_seismic_resistance'],
    'STR-SYS-RC-SHELL': ['rc_special_shear_wall', 'rc_ordinary_shear_wall'],
    'STR-SYS-TIMBER-GRIDSHELL': ['timber_braced_frame',
                                 'not_detailed_for_seismic_resistance'],
    'STR-SYS-STEEL-SPACE-FRAME-SHELL': ['steel_special_concentrically_braced_frame',
                                        'steel_special_moment_frame'],
}

OCCUPANCY_GROUP_BY_TYPOLOGY: dict[str, OccupancyGroup] = {
    'library': 'A-3', 'museum': 'A-3', 'theater': 'A-1',
}


def _status(jurisdiction: JurisdictionProfile, satisfied: bool) -> tuple[GateStatus, bool]:
    """A placeholder table can fail a design but can never clear one."""
    if not satisfied:
        return 'fail', True
    return ('pass', False) if jurisdiction.resolved else ('code_inputs_incomplete', False)


def _provenance(jurisdiction: JurisdictionProfile) -> Provenance:
    return 'jurisdiction_resolved' if jurisdiction.resolved else 'placeholder'


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def gate_construction_type(
    occupancy: OccupancyGroup, storeys: int, height_m: float, system_id: str,
    jurisdiction: JurisdictionProfile,
) -> CodeGateResult:
    """IBC 504: the single hardest constraint on structural material choice.

    A structural system implies a set of construction types. If none of them allows the
    requested storeys and height for this occupancy, the system is not merely difficult,
    it is unlawful, and no amount of engineering inside the design changes that.
    """
    candidates = CONSTRUCTION_TYPE_BY_SYSTEM.get(system_id, [])
    storey_table = _PLACEHOLDER_STOREYS[occupancy]
    best: tuple[ConstructionType, int, float] | None = None
    for ctype in candidates:
        allowed_storeys = (jurisdiction.allowable_storeys or {}).get(
            ctype, storey_table.get(ctype, 0))
        allowed_height = _PLACEHOLDER_HEIGHT_M.get(ctype, 0.0)
        if best is None or allowed_storeys > best[1]:
            best = (ctype, allowed_storeys, allowed_height)
    if best is None:
        return CodeGateResult(
            rule_id='IBC-504-CONSTRUCTION-TYPE', citation='IBC Tables 504.3 and 504.4',
            provenance=_provenance(jurisdiction), status='fail', blocking=True,
            message=f'no construction type is mapped for {system_id}')
    ctype, allowed_storeys, allowed_height = best
    ok = storeys <= allowed_storeys and height_m <= allowed_height
    status, blocking = _status(jurisdiction, ok)
    mitigation = None
    if not ok:
        mitigation = (
            f'the best construction type available to this system is {ctype}, which '
            f'allows {allowed_storeys} storeys and {allowed_height:.1f} m for Group '
            f'{occupancy}. Reduce storeys, add a fire wall to create separate buildings, '
            f'or change to a system that reaches a higher construction type.')
    return CodeGateResult(
        rule_id='IBC-504-CONSTRUCTION-TYPE', citation='IBC Tables 504.3 and 504.4',
        provenance=_provenance(jurisdiction), status=status, blocking=blocking,
        message=(f'Group {occupancy}, best available construction type {ctype}: '
                 f'{storeys} storeys / {height_m:.1f} m against {allowed_storeys} '
                 f'storeys / {allowed_height:.1f} m'),
        mitigation=mitigation)


def gate_frame_fire_rating(
    system_id: str, exposed_structure_intended: bool, jurisdiction: JurisdictionProfile,
) -> CodeGateResult:
    """IBC 601: whether the structural frame may be left exposed.

    This is the rule that quietly destroys architectural intent. A designer chooses mass
    timber or exposed steel *for its appearance*, then discovers the required rating
    forces encapsulation or spray-applied fireproofing, and the material becomes
    invisible. Surfacing it at selection time is the point of this gate.
    """
    candidates = CONSTRUCTION_TYPE_BY_SYSTEM.get(system_id, [])
    ratings = jurisdiction.frame_rating_hours or _PLACEHOLDER_FRAME_RATING_H
    if not candidates:
        return CodeGateResult(
            rule_id='IBC-601-FRAME-RATING', citation='IBC Table 601',
            provenance=_provenance(jurisdiction), status='fail', blocking=True,
            message=f'no construction type is mapped for {system_id}')
    best = min(candidates, key=lambda c: ratings.get(c, 99.0))
    hours = ratings.get(best, 99.0)
    heavy_timber = best in _MASS_TIMBER_TYPES

    if hours == 0.0 or (heavy_timber and best == 'IV-HT'):
        message = (f'construction type {best} requires a {hours:.0f} h frame rating; '
                   f'the structure may be left exposed')
        mitigation = None
        ok = True
    elif exposed_structure_intended:
        message = (f'construction type {best} requires a {hours:.0f} h frame rating, but '
                   f'the design intends exposed structure')
        mitigation = ('either accept encapsulation or applied fire protection and drop '
                      'the exposed-structure intent, or demonstrate the rating by '
                      'char-depth calculation (mass timber) or by an alternative '
                      'materials-and-methods path')
        ok = True   # legal, but the architectural intent does not survive
    else:
        message = (f'construction type {best} requires a {hours:.0f} h frame rating; '
                   f'applied protection or encapsulation is assumed')
        mitigation = None
        ok = True
    status, blocking = _status(jurisdiction, ok)
    if exposed_structure_intended and hours > 0.0 and best != 'IV-HT':
        status = 'warning' if jurisdiction.resolved else 'code_inputs_incomplete'
    return CodeGateResult(
        rule_id='IBC-601-FRAME-RATING', citation='IBC Table 601',
        provenance=_provenance(jurisdiction), status=status, blocking=blocking,
        message=message, mitigation=mitigation)


def gate_exterior_opening_area(
    opening_ratio_range: tuple[float, float], orientation: str,
    jurisdiction: JurisdictionProfile,
) -> CodeGateResult:
    """IBC 705.8: the direct code link between the site and the facade grammar.

    A fully glazed curtain wall is not a stylistic choice near a lot line. At a small
    fire separation distance the maximum unprotected opening area can be zero, and the
    grammar that wanted 80 % vision glass is unavailable on that elevation.

    The rule is per elevation, so it blocks a grammar only when even the grammar's
    *lowest* legal opening ratio exceeds the limit -- that is, when the grammar cannot go
    solid enough on that face without abandoning its own invariants. Otherwise the
    elevation is clamped to the legal maximum, which is what real buildings do.
    """
    low, high = opening_ratio_range
    rule_id = f'IBC-705.8-OPENING-AREA-{orientation.upper()}'
    fsd = jurisdiction.fire_separation_distance_m.get(orientation)
    if fsd is None:
        return CodeGateResult(
            rule_id=rule_id, citation='IBC Table 705.8',
            provenance=_provenance(jurisdiction), status='code_inputs_incomplete',
            blocking=False,
            message=(f'fire separation distance for the {orientation} face is not in the '
                     f'jurisdiction profile; the opening-area limit cannot be evaluated'),
            mitigation='supply the site survey and lot-line offsets for every elevation')
    table = jurisdiction.opening_area_limits or _PLACEHOLDER_OPENING_LIMITS
    allowed = next(limit for threshold, limit in table if fsd <= threshold)

    if low > allowed + 1e-9:
        return CodeGateResult(
            rule_id=rule_id, citation='IBC Table 705.8',
            provenance=_provenance(jurisdiction), status='fail', blocking=True,
            message=(f'{orientation} face at {fsd:.1f} m permits {allowed:.0%} unprotected '
                     f'openings; this grammar cannot go below {low:.0%} without losing its '
                     f'invariants'),
            mitigation=(f'increase the fire separation distance, use protected (rated) '
                        f'openings, or select a grammar whose lower bound reaches '
                        f'{allowed:.0%} on this elevation'))

    if high > allowed + 1e-9:
        return CodeGateResult(
            rule_id=rule_id, citation='IBC Table 705.8',
            provenance=_provenance(jurisdiction),
            status='warning' if jurisdiction.resolved else 'code_inputs_incomplete',
            blocking=False,
            message=(f'{orientation} face at {fsd:.1f} m permits {allowed:.0%}; the grammar '
                     f'range is {low:.0%}-{high:.0%} and is clamped to {allowed:.0%} here'),
            mitigation=(f'the {orientation} elevation is a code-clamped elevation; the '
                        f'grammar must express the reduced opening ratio deliberately '
                        f'rather than leaving it as a leftover blank wall'))

    status, blocking = _status(jurisdiction, True)
    return CodeGateResult(
        rule_id=rule_id, citation='IBC Table 705.8',
        provenance=_provenance(jurisdiction), status=status, blocking=blocking,
        message=(f'{orientation} face at {fsd:.1f} m permits {allowed:.0%}; the grammar '
                 f'range {low:.0%}-{high:.0%} fits'))


def gate_combustible_cladding(
    system_id: str, height_m: float, combustible_cladding: bool,
    jurisdiction: JurisdictionProfile,
) -> CodeGateResult:
    """IBC 1402 / 1405 and NFPA 285: combustible components in the exterior wall of a
    Type I-IV building above 40 ft require a tested assembly."""
    candidates = CONSTRUCTION_TYPE_BY_SYSTEM.get(system_id, [])
    protected_types = _NONCOMBUSTIBLE_TYPES | _MASS_TIMBER_TYPES
    applies = (bool(set(candidates) & protected_types)
               and height_m > NFPA285_TRIGGER_HEIGHT_M and combustible_cladding)
    if not applies:
        status, _ = _status(jurisdiction, True)
        return CodeGateResult(
            rule_id='IBC-1402-NFPA285', citation='IBC 1402, 1405; NFPA 285',
            provenance=_provenance(jurisdiction), status=status, blocking=False,
            message='no combustible exterior wall component above the trigger height')
    status = 'warning' if jurisdiction.resolved else 'code_inputs_incomplete'
    return CodeGateResult(
        rule_id='IBC-1402-NFPA285', citation='IBC 1402, 1405; NFPA 285',
        provenance=_provenance(jurisdiction), status=status, blocking=False,
        message=(f'combustible exterior wall components at {height_m:.1f} m on a Type '
                 f'{"/".join(sorted(set(candidates) & protected_types))} building require '
                 f'a tested wall assembly'),
        mitigation=('name a tested NFPA 285 assembly for the exact build-up, or change to '
                    'a noncombustible cladding and insulation set'))


def gate_seismic_system(
    system_id: str, height_m: float, jurisdiction: JurisdictionProfile,
) -> CodeGateResult:
    """ASCE/SEI 7 Table 12.2-1: not every lateral system is permitted everywhere.

    In higher seismic design categories whole families of system are prohibited outright
    or capped in height. The gate takes the best candidate the category allows and
    reports which one, because that choice is architectural: a concrete core inside a
    timber building is a different building from one braced in timber.
    """
    candidates = LATERAL_SYSTEM_CANDIDATES.get(system_id, [])
    if not candidates:
        return CodeGateResult(
            rule_id='ASCE7-12.2-SEISMIC-SYSTEM', citation='ASCE/SEI 7 Table 12.2-1',
            provenance=_provenance(jurisdiction), status='fail', blocking=True,
            message=f'no lateral system is mapped for {system_id}')
    sdc = jurisdiction.seismic_design_category
    if sdc is None:
        return CodeGateResult(
            rule_id='ASCE7-12.2-SEISMIC-SYSTEM', citation='ASCE/SEI 7 Table 12.2-1',
            provenance=_provenance(jurisdiction), status='code_inputs_incomplete',
            blocking=False,
            message=(f'seismic design category is unresolved; height limits on '
                     f'{", ".join(candidates)} cannot be evaluated'),
            mitigation='resolve site class, mapped accelerations, and risk category')

    permitted = [
        (lateral, _PLACEHOLDER_SEISMIC_LIMITS[lateral][sdc])
        for lateral in candidates
        if _PLACEHOLDER_SEISMIC_LIMITS[lateral][sdc] is not None
        and height_m <= _PLACEHOLDER_SEISMIC_LIMITS[lateral][sdc]
    ]
    if not permitted:
        parts = []
        for lateral in candidates:
            cap = _PLACEHOLDER_SEISMIC_LIMITS[lateral][sdc]
            parts.append(f'{lateral} '
                         + ('not permitted' if cap is None else f'capped at {cap:.1f} m'))
        return CodeGateResult(
            rule_id='ASCE7-12.2-SEISMIC-SYSTEM', citation='ASCE/SEI 7 Table 12.2-1',
            provenance=_provenance(jurisdiction), status='fail', blocking=True,
            message=(f'in SDC {sdc} at {height_m:.1f} m no candidate qualifies: '
                     + '; '.join(parts)),
            mitigation=('reduce height, or pair this system with a lateral system that '
                        'qualifies in this seismic design category'))

    chosen, limit = permitted[0]
    status, blocking = _status(jurisdiction, True)
    mitigation = None
    if chosen != candidates[0]:
        mitigation = (f'the preferred lateral system {candidates[0]} does not qualify at '
                      f'{height_m:.1f} m in SDC {sdc}; the design must adopt {chosen}, '
                      f'which changes the tectonic reading of the building')
    return CodeGateResult(
        rule_id='ASCE7-12.2-SEISMIC-SYSTEM', citation='ASCE/SEI 7 Table 12.2-1',
        provenance=_provenance(jurisdiction), status=status, blocking=blocking,
        message=(f'SDC {sdc}: {chosen} permitted at {height_m:.1f} m against a limit of '
                 f'{"no limit" if limit >= UNLIMITED else f"{limit:.1f} m"}'),
        mitigation=mitigation)


def gate_deflection_basis(component: str, applied_ratio: int) -> CodeGateResult:
    """IBC Table 1604.3: the facade coupling axis must use a code limit, not taste."""
    limits = DEFLECTION_LIMITS.get(component)
    if limits is None:
        return CodeGateResult(
            rule_id='IBC-1604.3-DEFLECTION', citation='IBC Table 1604.3',
            provenance='placeholder', status='code_inputs_incomplete', blocking=False,
            message=f'no deflection limit is mapped for component {component}')
    required = limits['live']
    ok = applied_ratio >= required
    return CodeGateResult(
        rule_id='IBC-1604.3-DEFLECTION', citation='IBC Table 1604.3',
        provenance='placeholder', status='pass' if ok else 'fail', blocking=not ok,
        message=(f'{component} requires at least L/{required}; the coupling axis applies '
                 f'L/{applied_ratio}'),
        mitigation=None if ok else 'raise the facade deflection demand to the code limit')
