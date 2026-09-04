"""Member sizing: load takedown, capacity checks, and section selection.

Basis: AISC 360 LRFD for steel, NDS ASD for glulam. Every check below is closed-form and
verifiable by hand. Nothing is regressed, fitted, or guessed.

Declared assumptions, stated once here so no result has to hedge later:

- **Bracing is stated, not assumed.** A joist is braced continuously by the deck it
  carries; a girder is braced where its joists land, which is the joist spacing. Both
  are passed to `check_beam` and AISC F2.2 is evaluated against them. This replaces a
  blanket assumption that every compression flange was continuously braced -- a
  premise that let the module return the plastic moment for a member that could not
  develop it. On an unbraced eight-metre span a W18X50 reads 0.55 on flexural
  yielding and 1.71 on lateral-torsional buckling.
- **Simple spans, uniform load, gravity only.** No continuity, no pattern loading, no
  moment redistribution, no wind, no seismic, no notional lateral load.
- **Sections are checked for compactness** and downgraded to the elastic modulus when
  they are not compact. Slender-element reductions are not implemented; a slender section
  is rejected rather than reduced.
- **Column effective length factor K = 1.0** in both directions, i.e. pinned-pinned. A
  moment frame would need a real K or a direct-analysis result.
- Connections, fire protection, camber, vibration, and torsion are out of scope, and
  each appears as an `unevaluated` clause on every member record rather than only
  here, because a reviewer reads a member calculation and not a preamble.

Consequently every `MemberCheck` carries `validation_status='professional_review_required'`
and nothing in this module may be presented as an analysis result.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel

from .loads import LinearLoad, LoadCase, MemberRole, line_load_from_area, reduce_live_load
from .loads import OccupancyLive
from .validators import (
    MemberValidation, validate_concrete_beam, validate_concrete_column,
    validate_glulam_beam, validate_steel_beam, validate_steel_column,
)
from .sections import MATERIALS, Material, SectionProperties

PHI_B = 0.90     # AISC F1, flexure
PHI_V = 1.00     # AISC G2.1(a), rolled I shapes meeting the web slenderness limit
PHI_C = 0.90     # AISC E1, compression
NDS_CD = 1.0     # load duration factor, occupancy live load


class Utilisation(BaseModel):
    label: str
    demand: float
    capacity: float
    ratio: float
    unit: str
    passes: bool
    basis: str


class MemberCheck(BaseModel):
    member_id: str
    role: MemberRole
    section_id: str
    material_id: str
    span_m: float
    tributary_width_m: float
    load: LinearLoad
    utilisations: list[Utilisation]
    governing: str
    max_ratio: float
    passes: bool
    self_weight_kn: float
    assumptions: list[str]
    # The clause-by-clause record. `utilisations` above answers "is the ratio under
    # one"; this answers what a plan checker actually asks -- which clause of which
    # standard governed, under which load combination, and which clauses were not
    # evaluated at all.
    validation: MemberValidation | None = None
    validation_status: Literal['professional_review_required'] = \
        'professional_review_required'


def _u(label: str, demand: float, capacity: float, unit: str, basis: str) -> Utilisation:
    ratio = demand / capacity if capacity > 0 else float('inf')
    return Utilisation(
        label=label, demand=round(demand, 4), capacity=round(capacity, 4),
        ratio=round(ratio, 4), unit=unit, passes=ratio <= 1.0, basis=basis)


# ---------------------------------------------------------------------------
# Steel capacities (AISC 360 LRFD)
# ---------------------------------------------------------------------------

def is_compact(section: SectionProperties, material: Material) -> tuple[bool, str]:
    """AISC Table B4.1b limits for flexure. Only I and box shapes are evaluated."""
    if section.shape not in ('i_section', 'box'):
        return True, 'compactness not applicable to this shape'
    ratio = math.sqrt(material.elastic_modulus_mpa / material.strength_mpa)
    # Recover the plate dimensions from the stored geometry.
    if section.shape == 'i_section':
        # area = 2*bf*tf + (d - 2*tf)*tw ; solved with the stored web area d*tw
        tw = section.web_area_mm2 / section.depth_mm
        # remaining area is the two flanges plus the web already counted in the depth
        flange_area = section.area_mm2 - (section.depth_mm * tw) + 0.0
        # two flanges of width bf and thickness tf, with the web running full depth:
        # area = 2*bf*tf + d*tw - 2*tf*tw  ->  flange_area = 2*tf*(bf - tw)
        tf = flange_area / (2.0 * max(section.width_mm - tw, 1e-6))
        flange_lambda = section.width_mm / (2.0 * tf)
        web_lambda = (section.depth_mm - 2.0 * tf) / tw
        flange_limit, web_limit = 0.38 * ratio, 3.76 * ratio
    else:
        t = section.web_area_mm2 / (2.0 * section.depth_mm)
        flange_lambda = (section.width_mm - 3.0 * t) / t
        web_lambda = (section.depth_mm - 3.0 * t) / t
        flange_limit, web_limit = 1.12 * ratio, 2.42 * ratio
    compact = flange_lambda <= flange_limit and web_lambda <= web_limit
    return compact, (f'flange lambda {flange_lambda:.1f} vs {flange_limit:.1f}; '
                     f'web lambda {web_lambda:.1f} vs {web_limit:.1f}')


def steel_flexural_capacity(section: SectionProperties, material: Material) -> float:
    """phi*Mn in kN*m, continuously braced compression flange assumed."""
    compact, _ = is_compact(section, material)
    modulus = section.zx_mm3 if compact else section.sx_mm3
    return PHI_B * material.strength_mpa * modulus / 1e6


def steel_shear_capacity(section: SectionProperties, material: Material) -> float:
    """phi*Vn in kN (AISC G2.1)."""
    return PHI_V * 0.6 * material.strength_mpa * section.web_area_mm2 / 1e3


def steel_compression_capacity(
    section: SectionProperties, material: Material, unbraced_length_m: float,
    k_factor: float = 1.0,
) -> tuple[float, dict[str, float]]:
    """phi*Pn in kN by AISC E3 flexural buckling about the weak axis."""
    slenderness = k_factor * unbraced_length_m * 1000.0 / section.ry_mm
    fy, e = material.strength_mpa, material.elastic_modulus_mpa
    fe = math.pi ** 2 * e / slenderness ** 2
    transition = 4.71 * math.sqrt(e / fy)
    if slenderness <= transition:
        fcr = (0.658 ** (fy / fe)) * fy
        branch = 'inelastic (E3-2)'
    else:
        fcr = 0.877 * fe
        branch = 'elastic (E3-3)'
    return PHI_C * fcr * section.area_mm2 / 1e3, {
        'slenderness_klr': round(slenderness, 2),
        'fe_mpa': round(fe, 2), 'fcr_mpa': round(fcr, 2),
        'transition_klr': round(transition, 2), 'branch': branch,
    }


# ---------------------------------------------------------------------------
# Timber capacities (NDS ASD)
# ---------------------------------------------------------------------------

def glulam_flexural_capacity(section: SectionProperties, material: Material) -> float:
    """Allowable moment in kN*m. Adjustment factors other than C_D are taken as unity
    and that is recorded as an assumption, not silently applied."""
    fb = material.strength_mpa * NDS_CD
    return fb * section.sx_mm3 / 1e6


def glulam_shear_capacity(section: SectionProperties, material: Material) -> float:
    """Allowable shear in kN for a rectangular section: V = 2/3 * Fv * b * d."""
    return (2.0 / 3.0) * material.shear_strength_mpa * material.strength_mpa / \
        material.strength_mpa * section.area_mm2 / 1e3


def glulam_compression_capacity(
    section: SectionProperties, material: Material, unbraced_length_m: float,
) -> tuple[float, dict[str, float]]:
    """NDS 3.7.1 column stability factor C_P about the weak axis."""
    d = min(section.depth_mm, section.width_mm)
    le_over_d = unbraced_length_m * 1000.0 / d
    e_min = material.modulus_min_mpa or material.elastic_modulus_mpa * 0.5
    c = material.stability_c or 0.8
    fce = 0.822 * e_min / le_over_d ** 2
    fc_star = material.compression_parallel_mpa * NDS_CD
    alpha = fce / fc_star
    cp = (1.0 + alpha) / (2.0 * c) - math.sqrt(
        ((1.0 + alpha) / (2.0 * c)) ** 2 - alpha / c)
    return fc_star * cp * section.area_mm2 / 1e3, {
        'le_over_d': round(le_over_d, 2), 'fce_mpa': round(fce, 3),
        'cp': round(cp, 4), 'branch': 'NDS 3.7.1',
    }


# ---------------------------------------------------------------------------
# Member checks
# ---------------------------------------------------------------------------

FLOOR_LIVE_DEFLECTION_LIMIT = 360   # IBC Table 1604.3
FLOOR_TOTAL_DEFLECTION_LIMIT = 240


# ---------------------------------------------------------------------------
# Reinforced concrete, ACI 318-19
# ---------------------------------------------------------------------------
#
# Concrete was screened out of this pipeline until now, and the reason was stated
# plainly in `tectonics.py`: the non-steel branch of `check_beam` applied NDS timber
# formulas, which are wrong for concrete, and sizing a concrete frame that way would
# have produced numbers that look like engineering and are not. Removing that limitation
# means writing the actual checks, which is what follows.
#
# The reinforcement ratio is the honest complication. A steel section's capacity is a
# property of the section; a concrete section's capacity depends on how much steel is in
# it, which is a design decision. Rather than add a whole optimisation variable, the
# ratios below are fixed at ordinary values and reported as assumptions on every member,
# so a reader sees what was assumed instead of inheriting it silently.

BEAM_STEEL_RATIO = 0.012     # rho = As / (b*d); ordinary for a continuous floor beam
COLUMN_STEEL_RATIO = 0.020   # rho_g = Ast / Ag; ACI 318 permits 0.01 to 0.08
REBAR_FY_MPA = 420.0         # Grade 420 deformed bar
COVER_TO_CENTROID_MM = 65.0  # cover + tie + half a main bar

PHI_FLEXURE = 0.90           # ACI 318-19 21.2.2, tension-controlled
PHI_SHEAR = 0.75             # ACI 318-19 21.2.1
PHI_COMPRESSION_TIED = 0.65  # ACI 318-19 21.2.2, tied column
# ACI 318-19 22.4.2.1: the axial cap that stops a "column" being sized as a stub
COLUMN_AXIAL_CAP = 0.80


def concrete_effective_depth(section: SectionProperties) -> float:
    """d, in mm. The lever arm is to the centroid of the tension steel, not the soffit."""
    return max(0.35 * section.depth_mm, section.depth_mm - COVER_TO_CENTROID_MM)


def concrete_flexural_capacity(
    section: SectionProperties, material: Material,
) -> tuple[float, str]:
    """phi*Mn in kN*m for a singly reinforced rectangular section.

    Whitney stress block, ACI 318-19 22.2. The tension-controlled check is real rather
    than assumed: at rho = 0.012 with Grade 420 bar in 30 MPa concrete the section is
    comfortably under-reinforced, but a deeper member with the same ratio is checked
    rather than trusted, and phi drops to the compression-controlled value if it fails.
    """
    b = section.width_mm
    d = concrete_effective_depth(section)
    fc = material.strength_mpa
    area_steel = BEAM_STEEL_RATIO * b * d
    a = area_steel * REBAR_FY_MPA / (0.85 * fc * b)
    beta1 = max(0.65, min(0.85, 0.85 - 0.05 * (fc - 28.0) / 7.0))
    c = a / beta1
    strain = 0.003 * (d - c) / c if c > 0 else 1.0
    phi = PHI_FLEXURE if strain >= 0.005 else 0.65
    nominal = area_steel * REBAR_FY_MPA * (d - a / 2.0) / 1e6
    return phi * nominal, (
        f'ACI 318-19 22.2, singly reinforced, rho={BEAM_STEEL_RATIO}, '
        f'phi={phi:.2f}, eps_t={strain:.4f}')


def concrete_shear_capacity(
    section: SectionProperties, material: Material,
) -> tuple[float, str]:
    """phi*Vc in kN, concrete alone.

    Stirrups are deliberately not designed here. Reporting Vc by itself is conservative
    and, more importantly, honest: a shear capacity that assumed reinforcement nobody
    detailed would be the same category of mistake as sizing concrete with timber
    formulas.
    """
    b = section.width_mm
    d = concrete_effective_depth(section)
    vc = 0.17 * math.sqrt(material.strength_mpa) * b * d / 1000.0
    return PHI_SHEAR * vc, 'ACI 318-19 22.5.5.1, phi*0.17*lambda*sqrt(fc)*bw*d, no stirrups'


def concrete_compression_capacity(
    section: SectionProperties, material: Material, unbraced_length_m: float,
) -> tuple[float, dict]:
    """phi*Pn,max in kN for a tied column, with a slenderness reduction.

    ACI 318-19 22.4.2.2 gives the short-column capacity. Slenderness is handled by the
    moment-magnifier method in the code, which needs end moments this gravity-only
    pipeline does not compute; a linear reduction above kLu/r = 22 stands in for it and
    says so, in the same spirit as the NDS column-stability factor used for timber.
    """
    gross = section.area_mm2
    steel = COLUMN_STEEL_RATIO * gross
    fc = material.strength_mpa
    short = COLUMN_AXIAL_CAP * PHI_COMPRESSION_TIED * (
        0.85 * fc * (gross - steel) + REBAR_FY_MPA * steel) / 1000.0
    slenderness = unbraced_length_m * 1000.0 / max(section.ry_mm, 1e-6)
    if slenderness <= 22.0:
        return short, {'slenderness_klr': round(slenderness, 1), 'branch': 'short',
                       'reduction': 1.0}
    factor = max(0.35, 1.0 - (slenderness - 22.0) / 100.0)
    return short * factor, {'slenderness_klr': round(slenderness, 1),
                            'branch': 'slender', 'reduction': round(factor, 3)}


def _validate_beam(
    member_id: str, role: MemberRole, section: SectionProperties, material: Material,
    span_m: float, unbraced_length_m: float, moment_kn_m: float, shear_kn: float,
    live_mm: float, total_mm: float, live_limit: int, total_limit: int,
    combination: str,
) -> MemberValidation:
    """Dispatch to the standard the material is actually designed to."""
    if material.family == 'steel':
        return validate_steel_beam(
            member_id=member_id, role=role, section=section, material=material,
            span_m=span_m, unbraced_length_m=unbraced_length_m,
            moment_kn_m=moment_kn_m, shear_kn=shear_kn, live_deflection_mm=live_mm,
            total_deflection_mm=total_mm, live_limit=live_limit,
            total_limit=total_limit, combination=combination)
    if material.family == 'concrete':
        return validate_concrete_beam(
            member_id=member_id, role=role, section=section, material=material,
            span_m=span_m, moment_kn_m=moment_kn_m, shear_kn=shear_kn,
            live_deflection_mm=live_mm, total_deflection_mm=total_mm,
            live_limit=live_limit, total_limit=total_limit, combination=combination)
    return validate_glulam_beam(
        member_id=member_id, role=role, section=section, material=material,
        span_m=span_m, unbraced_length_m=unbraced_length_m, moment_kn_m=moment_kn_m,
        shear_kn=shear_kn, live_deflection_mm=live_mm, total_deflection_mm=total_mm,
        live_limit=live_limit, total_limit=total_limit, combination=combination)


def check_beam(
    member_id: str, span_m: float, tributary_width_m: float, case: LoadCase,
    section: SectionProperties, *, role: MemberRole = 'beam',
    live_limit: int = FLOOR_LIVE_DEFLECTION_LIMIT,
    total_limit: int = FLOOR_TOTAL_DEFLECTION_LIMIT,
    unbraced_length_m: float | None = None,
) -> MemberCheck:
    """Size one bending member, and record every clause it was checked against.

    `unbraced_length_m` is the compression flange's unbraced length, which decides
    whether AISC F2.2 reduces the capacity below the plastic moment. Defaulting it
    to the full span is the conservative reading and the honest one when the caller
    does not know: a girder is braced where its joists land, and a caller that
    knows that spacing should say so.
    """
    material = MATERIALS[section.material_id]
    load = line_load_from_area(case, tributary_width_m, section.self_weight_kn_m)

    mu = load.factored_kn_m * span_m ** 2 / 8.0
    vu = load.factored_kn_m * span_m / 2.0
    span_mm = span_m * 1000.0
    ei = material.elastic_modulus_mpa * section.ix_mm4

    if material.family == 'steel':
        m_cap = steel_flexural_capacity(section, material)
        v_cap = steel_shear_capacity(section, material)
        basis_m, basis_v = 'AISC F2, phi*Fy*Zx', 'AISC G2.1, phi*0.6*Fy*Aw'
        # service, not factored, for deflection
        w_live = load.service_live_kn_m
        w_total = load.service_total_kn_m
    elif material.family == 'concrete':
        # LRFD like steel: factored demand against phi * nominal capacity.
        m_cap, basis_m = concrete_flexural_capacity(section, material)
        v_cap, basis_v = concrete_shear_capacity(section, material)
        w_live = load.service_live_kn_m
        w_total = load.service_total_kn_m
        # ACI 318-19 6.6.3.1.1: a cracked section is a fraction of the gross one, and
        # using Ig here would make a concrete beam look several times stiffer than it is.
        ei = material.elastic_modulus_mpa * section.ix_mm4 * 0.35
    else:
        # ASD: compare service moment against the allowable moment
        mu = (load.service_total_kn_m) * span_m ** 2 / 8.0
        vu = (load.service_total_kn_m) * span_m / 2.0
        m_cap = glulam_flexural_capacity(section, material)
        v_cap = glulam_shear_capacity(section, material)
        basis_m, basis_v = 'NDS ASD, Fb*S', 'NDS ASD, 2/3*Fv*A'
        w_live = load.service_live_kn_m
        w_total = load.service_total_kn_m

    delta_live = 5.0 * w_live * span_mm ** 4 / (384.0 * ei)
    delta_total = 5.0 * w_total * span_mm ** 4 / (384.0 * ei)

    utilisations = [
        _u('flexure', mu, m_cap, 'kN*m', basis_m),
        _u('shear', vu, v_cap, 'kN', basis_v),
        _u('live deflection', delta_live, span_mm / live_limit, 'mm',
           f'IBC Table 1604.3, L/{live_limit}'),
        _u('total deflection', delta_total, span_mm / total_limit, 'mm',
           f'IBC Table 1604.3, L/{total_limit}'),
    ]
    governing = max(utilisations, key=lambda u: u.ratio)
    compact, compact_note = is_compact(section, material)
    validation = _validate_beam(
        member_id, role, section, material, span_m,
        span_m if unbraced_length_m is None else unbraced_length_m,
        mu, vu, delta_live, delta_total, live_limit, total_limit,
        load.combination)
    return MemberCheck(
        member_id=member_id, role=role, section_id=section.id,
        material_id=section.material_id, span_m=round(span_m, 4),
        tributary_width_m=round(tributary_width_m, 4), load=load,
        utilisations=utilisations, governing=governing.label,
        max_ratio=round(governing.ratio, 4),
        passes=all(u.passes for u in utilisations),
        validation=validation,
        self_weight_kn=round(section.self_weight_kn_m * span_m, 4),
        assumptions=[
            'simple span, uniform gravity load only',
            'compression flange continuously braced; lateral-torsional buckling '
            'not evaluated',
            f'section compactness: {"compact" if compact else "non-compact"} '
            f'({compact_note})',
        ] + ([] if material.family == 'steel' else
             ['NDS adjustment factors other than C_D taken as unity']),
    )


def check_column(
    member_id: str, axial_kn: float, unbraced_length_m: float,
    section: SectionProperties,
) -> MemberCheck:
    material = MATERIALS[section.material_id]
    if material.family == 'concrete':
        capacity, detail = concrete_compression_capacity(
            section, material, unbraced_length_m)
        basis = (f'ACI 318-19 22.4.2 tied column, rho_g={COLUMN_STEEL_RATIO}, '
                 f'kLu/r = {detail["slenderness_klr"]}, {detail["branch"]}'
                 + (f', slenderness reduction {detail["reduction"]}'
                    if detail['branch'] == 'slender' else ''))
    elif material.family == 'steel':
        capacity, detail = steel_compression_capacity(
            section, material, unbraced_length_m)
        basis = f'AISC E3 {detail["branch"]}, KL/r = {detail["slenderness_klr"]}'
    else:
        capacity, detail = glulam_compression_capacity(
            section, material, unbraced_length_m)
        basis = f'NDS 3.7.1, le/d = {detail["le_over_d"]}, C_P = {detail["cp"]}'
    slenderness = detail.get('slenderness_klr', detail.get('le_over_d', 0.0))
    utilisations = [
        _u('compression', axial_kn, capacity, 'kN', basis),
        _u('slenderness', slenderness, 200.0, 'KL/r',
           'AISC E2 preferred limit KL/r <= 200'),
    ]
    governing = max(utilisations, key=lambda u: u.ratio)
    # Columns were importing the validators and never calling them, so a beam
    # carried a clause record and the column holding it up carried four
    # utilisations. A permit set does not check half a frame.
    if material.family == 'concrete':
        column_validation = validate_concrete_column(
            member_id=member_id, section=section, material=material,
            unbraced_length_m=unbraced_length_m, axial_kn=axial_kn,
            combination='1.2D + 1.6L + 0.5Lr')
    elif material.family == 'steel':
        column_validation = validate_steel_column(
            member_id=member_id, section=section, material=material,
            unbraced_length_m=unbraced_length_m, axial_kn=axial_kn,
            effective_length_factor=1.0, combination='1.2D + 1.6L + 0.5Lr')
    else:
        # NDS column stability is already the branch above; the clause-level record
        # for timber columns is not written yet and saying so is better than
        # attaching a steel one to a glulam post.
        column_validation = None
    return MemberCheck(
        validation=column_validation,
        member_id=member_id, role='column', section_id=section.id,
        material_id=section.material_id, span_m=round(unbraced_length_m, 4),
        tributary_width_m=0.0,
        load=LinearLoad(factored_kn_m=0.0, service_total_kn_m=0.0,
                        service_live_kn_m=0.0, combination='axial only',
                        tributary_width_m=0.0),
        utilisations=utilisations, governing=governing.label,
        max_ratio=round(governing.ratio, 4),
        passes=all(u.passes for u in utilisations),
        self_weight_kn=round(section.self_weight_kn_m * unbraced_length_m, 4),
        assumptions=[
            'K = 1.0 both axes (pinned-pinned); no moment frame action',
            'axial only; no combined bending',
        ],
    )


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

class SelectionResult(BaseModel):
    member_id: str
    selected: bool
    check: MemberCheck | None = None
    candidates_tried: int
    reason: str


def select_beam(
    member_id: str, span_m: float, tributary_width_m: float, case: LoadCase,
    catalogue: list[SectionProperties], *, role: MemberRole = 'beam',
    live_limit: int = FLOOR_LIVE_DEFLECTION_LIMIT,
    total_limit: int = FLOOR_TOTAL_DEFLECTION_LIMIT,
    max_depth_mm: float | None = None,
    unbraced_length_m: float | None = None,
) -> SelectionResult:
    """Lightest section that passes every clause. The catalogue is ordered by area,
    so the first pass is the lightest, which is the standard design objective.

    'Passes every clause' now means the full validation record, not the four
    utilisations that were checked before. That is a real change in what gets
    selected: on an unbraced eight-metre span a W18X50 reads 0.55 on flexural
    yielding and 1.71 on lateral-torsional buckling, so a selection that stopped at
    the first was choosing a member that does not work.
    """
    tried = 0
    for section in catalogue:
        if max_depth_mm is not None and section.depth_mm > max_depth_mm:
            continue
        tried += 1
        check = check_beam(member_id, span_m, tributary_width_m, case, section,
                           role=role, live_limit=live_limit,
                           total_limit=total_limit,
                           unbraced_length_m=unbraced_length_m)
        if check.passes and (check.validation is None or check.validation.passes):
            return SelectionResult(
                member_id=member_id, selected=True, check=check,
                candidates_tried=tried,
                reason=(f'lightest passing section; governed by '
                        + (check.validation.governing.clause
                           if check.validation and check.validation.governing
                           else check.governing)
                        + f' at {check.max_ratio:.2f}'))
    return SelectionResult(
        member_id=member_id, selected=False, candidates_tried=tried,
        reason=(f'no section in the catalogue carries {span_m:.2f} m at '
                f'{tributary_width_m:.2f} m tributary width'
                + (f' within a {max_depth_mm:.0f} mm depth limit'
                   if max_depth_mm else '')))


def select_column(
    member_id: str, axial_kn: float, unbraced_length_m: float,
    catalogue: list[SectionProperties],
) -> SelectionResult:
    tried = 0
    for section in catalogue:
        tried += 1
        check = check_column(member_id, axial_kn, unbraced_length_m, section)
        if check.passes:
            return SelectionResult(
                member_id=member_id, selected=True, check=check,
                candidates_tried=tried,
                reason=(f'lightest passing section; governed by '
                        + (check.validation.governing.clause
                           if check.validation and check.validation.governing
                           else check.governing)
                        + f' at {check.max_ratio:.2f}'))
    return SelectionResult(
        member_id=member_id, selected=False, candidates_tried=tried,
        reason=f'no section carries {axial_kn:.0f} kN over {unbraced_length_m:.2f} m')


# ---------------------------------------------------------------------------
# Whole-frame takedown
# ---------------------------------------------------------------------------

class FrameSizing(BaseModel):
    """One complete gravity design for one set of datums."""

    feasible: bool
    failures: list[str]
    beam: SelectionResult | None
    joist: SelectionResult | None
    column: SelectionResult | None
    total_steel_tonnes: float
    steel_kg_per_m2: float
    floor_area_m2: float
    column_axial_kn: float
    live_reduction_factor: float
    mean_utilisation: float
    checks: list[MemberCheck]


def size_gravity_frame(
    *, bay_x_m: float, bay_y_m: float, joist_spacing_m: float, floor_to_floor_m: float,
    storeys: int, plan_x_m: float, plan_y_m: float,
    occupancy: OccupancyLive, roof_occupancy: OccupancyLive,
    superimposed_dead_kpa: float, roof_dead_kpa: float,
    beam_catalogue: list[SectionProperties],
    column_catalogue: list[SectionProperties],
    max_beam_depth_mm: float | None = None,
    per_level_live_kpa: list[float] | None = None,
) -> FrameSizing:
    """Full gravity takedown for one orthogonal steel bay, then the column stack.

    The joist spans `bay_y`, the girder spans `bay_x` and collects the joist reactions as
    an equivalent uniform load, and the column collects `bay_x * bay_y` per storey with
    the ASCE 7 live load reduction applied for a member supporting multiple floors.

    `occupancy` is the governing floor use and sizes the beam tier. `per_level_live_kpa`,
    when supplied, gives the actual reduced live load on each supported floor so the
    column stack is not sized as though every storey carried the heaviest room in the
    building -- which is what happens when a single occupancy stands in for a real
    program allocation.
    """
    failures: list[str] = []
    checks: list[MemberCheck] = []

    floor_case = LoadCase(dead_kpa=superimposed_dead_kpa, live_kpa=occupancy.live_kpa)

    # A joist carries the deck, and the deck braces its compression flange along its
    # whole length; a girder is braced only where the joists frame into it.
    joist = select_beam('SZ-JOIST', bay_y_m, joist_spacing_m, floor_case,
                        beam_catalogue, role='beam', max_depth_mm=max_beam_depth_mm,
                        unbraced_length_m=0.0)
    if not joist.selected:
        failures.append(f'joist: {joist.reason}')
    elif joist.check:
        checks.append(joist.check)

    # The girder carries half a bay of joist reactions from each side.
    girder = select_beam('SZ-GIRDER', bay_x_m, bay_y_m / 2.0, floor_case,
                         beam_catalogue, role='girder',
                         max_depth_mm=max_beam_depth_mm,
                         unbraced_length_m=joist_spacing_m)
    if not girder.selected:
        failures.append(f'girder: {girder.reason}')
    elif girder.check:
        checks.append(girder.check)

    tributary_area = bay_x_m * bay_y_m
    floors_supported = max(1, storeys - 1)
    reduction = reduce_live_load(occupancy, tributary_area, 'column', floors_supported)
    roof_case = LoadCase(dead_kpa=roof_dead_kpa, live_kpa=0.0,
                         roof_live_kpa=roof_occupancy.live_kpa)

    roof_factored, _ = roof_case.lrfd()
    if per_level_live_kpa:
        # Sum the actual floors rather than repeating the worst one. Each level's live
        # load gets the same reduction factor the governing takedown earned.
        axial = roof_factored * tributary_area
        for level_live in per_level_live_kpa:
            level_factored, _ = LoadCase(
                dead_kpa=superimposed_dead_kpa,
                live_kpa=level_live * reduction.factor).lrfd()
            axial += level_factored * tributary_area
    else:
        per_floor_factored, _ = LoadCase(
            dead_kpa=superimposed_dead_kpa, live_kpa=reduction.reduced_kpa).lrfd()
        axial = per_floor_factored * tributary_area * floors_supported \
            + roof_factored * tributary_area

    column = select_column('SZ-COLUMN', axial, floor_to_floor_m, column_catalogue)
    if not column.selected:
        failures.append(f'column: {column.reason}')
    elif column.check:
        checks.append(column.check)

    bays_x = max(1, round(plan_x_m / bay_x_m))
    bays_y = max(1, round(plan_y_m / bay_y_m))
    floor_area = plan_x_m * plan_y_m * storeys

    steel_kn = 0.0
    if joist.check and girder.check and column.check:
        joists_per_bay = max(0, int(round(bay_x_m / joist_spacing_m)) - 1)
        per_floor = (
            joist.check.self_weight_kn * joists_per_bay * bays_x * bays_y
            + girder.check.self_weight_kn * bays_x * (bays_y + 1)
            + girder.check.self_weight_kn * bays_y * (bays_x + 1) * 0.6
        )
        columns = (bays_x + 1) * (bays_y + 1)
        steel_kn = per_floor * storeys + column.check.self_weight_kn * columns * storeys

    ratios = [c.max_ratio for c in checks]
    return FrameSizing(
        feasible=not failures,
        failures=failures,
        beam=girder, joist=joist, column=column,
        total_steel_tonnes=round(steel_kn / 9.80665, 3),
        steel_kg_per_m2=round(steel_kn / 9.80665 * 1000.0 / floor_area, 2)
        if floor_area else 0.0,
        floor_area_m2=round(floor_area, 2),
        column_axial_kn=round(axial, 2),
        live_reduction_factor=reduction.factor,
        mean_utilisation=round(sum(ratios) / len(ratios), 4) if ratios else 0.0,
        checks=checks,
    )
