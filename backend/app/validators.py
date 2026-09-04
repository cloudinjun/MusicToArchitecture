"""Material-specific code validators: every clause a member is checked against.

`sizing.py` computed capacities and returned a ratio. That is enough to size a member
and not enough to permit one, because a plan checker does not ask "is the ratio under
one" -- they ask which clause governed, what the demand was under which load
combination, and which clauses were not evaluated at all.

So a validator returns a list of `ClauseCheck`, one per clause, each naming its section
of its standard. The result is a calculation record rather than a verdict, and the
things it does **not** check are as explicit as the things it does: `unevaluated`
clauses appear in the record with the reason, because a permit set that silently omits
lateral-torsional buckling is worse than one that says it was omitted.

**The clause that was missing.** The steel beam check assumed a continuously braced
compression flange and said so in a docstring -- `steel_flexural_capacity` computed
`phi * Fy * Zx` outright. A girder braced only where the joists land is not continuously
braced, and AISC F2.2 is the clause that decides whether that matters. It does here: on
the spans this project produces the girder's unbraced length is the joist spacing, which
is usually inside Lp, but the check has to run to know that rather than be assumed.

Each validator is material-specific because the standards are. AISC 360 is LRFD with phi
factors on nominal strength; NDS is ASD with adjustment factors on reference values; ACI
318 is LRFD with its own phi factors and a reinforcement ratio the section does not carry
on its own. Merging them into one function is how a timber formula ends up applied to
concrete, which is exactly what this project did until the ACI checks were written.
"""

from __future__ import annotations

import math
from contextvars import ContextVar
from typing import Literal

from pydantic import BaseModel

from .sections import Material, SectionProperties

Status = Literal['pass', 'fail', 'unevaluated']


class ClauseCheck(BaseModel):
    """One code clause, evaluated or explicitly not."""

    clause: str
    standard: str
    label: str
    status: Status
    demand: float | None = None
    capacity: float | None = None
    unit: str = ''
    basis: str = ''

    @property
    def ratio(self) -> float | None:
        if self.demand is None or not self.capacity:
            return None
        return round(self.demand / self.capacity, 4)


class MemberValidation(BaseModel):
    """Every clause one member was checked against, and what governed."""

    member_id: str
    role: str
    designation: str
    material_id: str
    load_combination: str
    checks: list[ClauseCheck]

    @property
    def evaluated(self) -> list[ClauseCheck]:
        return [c for c in self.checks if c.status != 'unevaluated']

    @property
    def unevaluated(self) -> list[ClauseCheck]:
        return [c for c in self.checks if c.status == 'unevaluated']

    @property
    def governing(self) -> ClauseCheck | None:
        rated = [c for c in self.evaluated if c.ratio is not None]
        return max(rated, key=lambda c: c.ratio) if rated else None

    @property
    def max_ratio(self) -> float:
        governing = self.governing
        return governing.ratio if governing and governing.ratio else 0.0

    @property
    def passes(self) -> bool:
        return not any(c.status == 'fail' for c in self.checks)

    def summary(self) -> str:
        governing = self.governing
        return (f'{self.designation}: {len(self.evaluated)} clauses checked, '
                f'{len(self.unevaluated)} not evaluated, '
                + (f'{governing.clause} governs at {governing.ratio:.2f}'
                   if governing else 'nothing governs'))


# ---------------------------------------------------------------------------
# ASCE 7-16 load combinations
# ---------------------------------------------------------------------------

class Actions(BaseModel):
    """Unfactored actions on one member, in consistent units."""

    dead: float = 0.0
    live: float = 0.0
    roof_live: float = 0.0
    snow: float = 0.0
    wind: float = 0.0
    seismic: float = 0.0


def lrfd_combinations(actions: Actions) -> list[tuple[str, float]]:
    """ASCE 7-16 2.3.1, the strength combinations, all of them.

    The pipeline used combination 2 alone -- 1.2D + 1.6L + 0.5Lr -- which is usually the
    governing one for a gravity floor and is not always. On a lightly loaded roof
    combination 3 governs, and on anything where wind or seismic exist the last four do.
    Evaluating one and calling it the design is the difference between a sizing exercise
    and a calculation a reviewer can accept.
    """
    a = actions
    roof = max(a.roof_live, a.snow)
    return [
        ('1.4D', 1.4 * a.dead),
        ('1.2D + 1.6L + 0.5Lr', 1.2 * a.dead + 1.6 * a.live + 0.5 * roof),
        ('1.2D + 1.6Lr + 1.0L', 1.2 * a.dead + 1.6 * roof + 1.0 * a.live),
        ('1.2D + 1.0W + 1.0L + 0.5Lr',
         1.2 * a.dead + 1.0 * a.wind + 1.0 * a.live + 0.5 * roof),
        ('1.2D + 1.0E + 1.0L + 0.2S',
         1.2 * a.dead + 1.0 * a.seismic + 1.0 * a.live + 0.2 * a.snow),
        ('0.9D + 1.0W', 0.9 * a.dead + 1.0 * a.wind),
        ('0.9D + 1.0E', 0.9 * a.dead + 1.0 * a.seismic),
    ]


def governing_combination(actions: Actions) -> tuple[str, float]:
    return max(lrfd_combinations(actions), key=lambda pair: pair[1])


def flat_roof_snow_kpa(ground_snow_kpa: float, *, exposure_ce: float = 1.0,
                       thermal_ct: float = 1.0, importance_is: float = 1.0) -> float:
    """ASCE 7-16 7.3.1: pf = 0.7 * Ce * Ct * Is * pg.

    Snow was absent from this project and a roof live load of 0.96 kPa stood in for it.
    Those are different actions with different combination factors, and in any climate
    that has snow the substitution is not conservative.
    """
    return 0.7 * exposure_ce * thermal_ct * importance_is * ground_snow_kpa


# ---------------------------------------------------------------------------
# Steel, AISC 360-16 LRFD
# ---------------------------------------------------------------------------

PHI_B = 0.90    # F1, flexure
PHI_V = 0.90    # G1, shear
PHI_C = 0.90    # E1, compression


def _i_plate_dimensions(section: SectionProperties) -> tuple[float, float]:
    """Recover (tw, tf) from the stored geometry of an I shape."""
    tw = section.web_area_mm2 / section.depth_mm
    flange_area = section.area_mm2 - section.depth_mm * tw
    tf = flange_area / (2.0 * max(section.width_mm - tw, 1e-6))
    return tw, tf


def steel_ltb_capacity(
    section: SectionProperties, material: Material, unbraced_length_m: float,
    cb: float = 1.0,
) -> tuple[float, str]:
    """AISC F2: nominal flexural strength including lateral-torsional buckling.

    Returns phi*Mn in kN*m and the branch that governed. This is the clause the project
    previously assumed away: `steel_flexural_capacity` returned phi*Fy*Zx and its
    docstring said "continuously braced compression flange assumed". A girder braced at
    its joists is not continuously braced, and whether that reduces its capacity is a
    question with an answer rather than a premise.

    A closed section -- an HSS -- does not buckle this way and returns the plastic
    moment directly, which is why `cw_mm6` being zero is a branch and not a bug.
    """
    fy = material.strength_mpa
    e = material.elastic_modulus_mpa
    mp = fy * section.zx_mm3 / 1e6            # kN*m
    if section.cw_mm6 <= 0.0 or section.rts_mm <= 0.0:
        return PHI_B * mp, 'F7 closed section, no lateral-torsional buckling'

    lb = unbraced_length_m * 1000.0
    ry, rts, ho = section.ry_mm, section.rts_mm, section.ho_mm
    sx, j = section.sx_mm3, section.j_mm4
    lp = 1.76 * ry * math.sqrt(e / fy)
    c = 1.0                                    # doubly symmetric I, F2-8a
    term = j * c / (sx * ho)
    lr = (1.95 * rts * (e / (0.7 * fy))
          * math.sqrt(term + math.sqrt(term ** 2 + 6.76 * (0.7 * fy / e) ** 2)))

    if lb <= lp:
        return PHI_B * mp, f'F2.1 yielding, Lb {lb:.0f} <= Lp {lp:.0f} mm'
    if lb <= lr:
        mn = cb * (mp - (mp - 0.7 * fy * sx / 1e6) * (lb - lp) / (lr - lp))
        return PHI_B * min(mn, mp), (
            f'F2.2 inelastic LTB, Lp {lp:.0f} < Lb {lb:.0f} <= Lr {lr:.0f} mm, '
            f'Cb {cb:.2f}')
    fcr = (cb * math.pi ** 2 * e / (lb / rts) ** 2
           * math.sqrt(1.0 + 0.078 * term * (lb / rts) ** 2))
    mn = fcr * sx / 1e6
    return PHI_B * min(mn, mp), (
        f'F2.2 elastic LTB, Lb {lb:.0f} > Lr {lr:.0f} mm, Fcr {fcr:.0f} MPa')


def steel_compactness(section: SectionProperties,
                      material: Material) -> tuple[bool, str]:
    """AISC Table B4.1b, flexure."""
    if section.shape not in ('i_section', 'box'):
        return True, 'B4.1 not applicable to this shape'
    ratio = math.sqrt(material.elastic_modulus_mpa / material.strength_mpa)
    if section.shape == 'i_section':
        tw, tf = _i_plate_dimensions(section)
        flange_lambda = section.width_mm / (2.0 * tf)
        web_lambda = (section.depth_mm - 2.0 * tf) / tw
        flange_limit, web_limit = 0.38 * ratio, 3.76 * ratio
    else:
        t = section.web_area_mm2 / (2.0 * section.depth_mm)
        flange_lambda = (section.width_mm - 3.0 * t) / t
        web_lambda = (section.depth_mm - 3.0 * t) / t
        flange_limit, web_limit = 1.12 * ratio, 2.42 * ratio
    compact = flange_lambda <= flange_limit and web_lambda <= web_limit
    return compact, (f'flange {flange_lambda:.1f} vs {flange_limit:.1f}, '
                     f'web {web_lambda:.1f} vs {web_limit:.1f}')


def validate_steel_beam(
    *, member_id: str, role: str, section: SectionProperties, material: Material,
    span_m: float, unbraced_length_m: float, moment_kn_m: float, shear_kn: float,
    live_deflection_mm: float, total_deflection_mm: float,
    live_limit: int, total_limit: int, combination: str, cb: float = 1.0,
) -> MemberValidation:
    """Every AISC clause a gravity beam is checked against here."""
    checks: list[ClauseCheck] = []
    compact, compact_note = steel_compactness(section, material)
    checks.append(ClauseCheck(
        clause='B4.1b', standard='AISC 360-16', label='Local buckling classification',
        status='pass' if compact else 'fail', basis=compact_note))

    modulus = section.zx_mm3 if compact else section.sx_mm3
    yielding = PHI_B * material.strength_mpa * modulus / 1e6
    checks.append(ClauseCheck(
        clause='F2.1', standard='AISC 360-16', label='Flexural yielding',
        status='pass' if moment_kn_m <= yielding else 'fail',
        demand=round(moment_kn_m, 2), capacity=round(yielding, 2), unit='kN*m',
        basis=f'phi*Fy*{"Zx" if compact else "Sx"}, phi = {PHI_B}'))

    ltb, ltb_basis = steel_ltb_capacity(section, material, unbraced_length_m, cb)
    checks.append(ClauseCheck(
        clause='F2.2', standard='AISC 360-16',
        label='Lateral-torsional buckling',
        status='pass' if moment_kn_m <= ltb else 'fail',
        demand=round(moment_kn_m, 2), capacity=round(ltb, 2), unit='kN*m',
        basis=ltb_basis))

    shear = PHI_V * 0.6 * material.strength_mpa * section.web_area_mm2 / 1e3
    checks.append(ClauseCheck(
        clause='G2.1', standard='AISC 360-16', label='Shear yielding of the web',
        status='pass' if shear_kn <= shear else 'fail',
        demand=round(shear_kn, 2), capacity=round(shear, 2), unit='kN',
        basis=f'phi*0.6*Fy*Aw with Cv = 1.0, phi = {PHI_V}'))

    span_mm = span_m * 1000.0
    for label, value, limit, clause in (
        ('Live load deflection', live_deflection_mm, live_limit, 'Table 1604.3'),
        ('Total load deflection', total_deflection_mm, total_limit, 'Table 1604.3'),
    ):
        allowed = span_mm / limit
        checks.append(ClauseCheck(
            clause=clause, standard='IBC 2021', label=label,
            status='pass' if value <= allowed else 'fail',
            demand=round(value, 2), capacity=round(allowed, 2), unit='mm',
            basis=f'L/{limit} on a {span_m:.2f} m span'))

    checks.extend(_unevaluated_common())
    checks.append(ClauseCheck(
        clause='J', standard='AISC 360-16', label='Connections',
        status='unevaluated',
        basis='No connection is designed. Bolt groups, welds, and the shear tab that '
              'delivers this reaction are outside the model.'))
    return MemberValidation(
        member_id=member_id, role=role, designation=section.id,
        material_id=material.id, load_combination=combination, checks=checks)


def validate_steel_column(
    *, member_id: str, section: SectionProperties, material: Material,
    unbraced_length_m: float, axial_kn: float, effective_length_factor: float,
    combination: str,
) -> MemberValidation:
    """AISC E: compression, with the slenderness limit E2 recommends."""
    checks: list[ClauseCheck] = []
    fy, e = material.strength_mpa, material.elastic_modulus_mpa
    radius = min(section.rx_mm, section.ry_mm)
    klr = effective_length_factor * unbraced_length_m * 1000.0 / radius
    fe = math.pi ** 2 * e / klr ** 2
    if klr <= 4.71 * math.sqrt(e / fy):
        fcr = 0.658 ** (fy / fe) * fy
        branch = 'E3-2 inelastic buckling'
    else:
        fcr = 0.877 * fe
        branch = 'E3-3 elastic buckling'
    capacity = PHI_C * fcr * section.area_mm2 / 1e3
    checks.append(ClauseCheck(
        clause='E3', standard='AISC 360-16', label='Flexural buckling',
        status='pass' if axial_kn <= capacity else 'fail',
        demand=round(axial_kn, 2), capacity=round(capacity, 2), unit='kN',
        basis=f'{branch}, KL/r = {klr:.0f}, Fcr = {fcr:.0f} MPa, phi = {PHI_C}'))
    checks.append(ClauseCheck(
        clause='E2', standard='AISC 360-16', label='Slenderness',
        status='pass' if klr <= 200.0 else 'fail',
        demand=round(klr, 1), capacity=200.0, unit='KL/r',
        basis='AISC E2 recommends KL/r <= 200 for compression members'))
    compact, note = steel_compactness(section, material)
    checks.append(ClauseCheck(
        clause='B4.1a', standard='AISC 360-16', label='Element slenderness',
        status='pass' if compact else 'fail', basis=note))
    checks.append(ClauseCheck(
        clause='E4', standard='AISC 360-16',
        label='Torsional and flexural-torsional buckling', status='unevaluated',
        basis='Doubly symmetric shapes rarely govern on E4 below the flexural mode, '
              'but the check is not run and a singly symmetric section would need it.'))
    checks.append(ClauseCheck(
        clause='H1', standard='AISC 360-16', label='Combined axial and flexure',
        status='unevaluated',
        basis='The frame is analysed for gravity only, so columns carry no moment in '
              'this model. Any lateral load makes H1 govern.'))
    checks.extend(_unevaluated_common())
    return MemberValidation(
        member_id=member_id, role='column', designation=section.id,
        material_id=material.id, load_combination=combination, checks=checks)


# ---------------------------------------------------------------------------
# Glulam, NDS 2018 ASD
# ---------------------------------------------------------------------------

NDS_CD = 1.0     # load duration, occupancy live
NDS_CM = 1.0     # wet service; dry assumed and recorded
NDS_CT = 1.0     # temperature


def glulam_volume_factor(section: SectionProperties, span_m: float,
                         x: float = 10.0) -> float:
    """NDS 5.3.6 volume factor CV for structural glued laminated timber.

    CV = (21/L)^(1/x) * (300/d)^(1/x) * (130/b)^(1/x) <= 1.0, in imperial units; the
    conversion is folded in here. It reduces the reference bending value on deep, long
    members, and omitting it -- as this project did -- overstates a glulam girder.
    """
    length_ft = span_m * 3.28084
    depth_in = section.depth_mm / 25.4
    width_in = section.width_mm / 25.4
    if length_ft <= 0 or depth_in <= 0 or width_in <= 0:
        return 1.0
    cv = ((21.0 / length_ft) ** (1.0 / x) * (12.0 / depth_in) ** (1.0 / x)
          * (5.125 / width_in) ** (1.0 / x))
    return min(1.0, cv)


def validate_glulam_beam(
    *, member_id: str, role: str, section: SectionProperties, material: Material,
    span_m: float, unbraced_length_m: float, moment_kn_m: float, shear_kn: float,
    live_deflection_mm: float, total_deflection_mm: float,
    live_limit: int, total_limit: int, combination: str,
) -> MemberValidation:
    """NDS bending, shear, stability and deflection, with the factors named."""
    checks: list[ClauseCheck] = []
    fb = material.strength_mpa * NDS_CD * NDS_CM * NDS_CT
    cv = glulam_volume_factor(section, span_m)

    # NDS 3.3.3 beam stability factor CL
    le = 1.63 * unbraced_length_m * 1000.0 + 3.0 * section.depth_mm
    rb = math.sqrt(le * section.depth_mm / section.width_mm ** 2)
    emin = material.modulus_min_mpa or material.elastic_modulus_mpa * 0.53
    fbe = 1.20 * emin / rb ** 2 if rb > 0 else fb * 10.0
    ratio = fbe / (fb * cv) if fb * cv > 0 else 10.0
    cl = ((1.0 + ratio) / 1.9
          - math.sqrt(((1.0 + ratio) / 1.9) ** 2 - ratio / 0.95))
    cl = max(0.0, min(1.0, cl))
    checks.append(ClauseCheck(
        clause='3.3.3', standard='NDS 2018', label='Beam stability factor CL',
        status='pass' if cl > 0.0 else 'fail',
        demand=round(rb, 2), capacity=50.0, unit='RB',
        basis=f'CL = {cl:.3f}, RB = {rb:.1f} (NDS caps RB at 50), '
              f'le = {le / 1000.0:.2f} m'))
    checks.append(ClauseCheck(
        clause='5.3.6', standard='NDS 2018', label='Volume factor CV',
        status='pass', demand=round(cv, 4), capacity=1.0, unit='CV',
        basis='CV and CL are not applied together; NDS 5.3.6 takes the lesser.'))

    # NDS 5.3.6: CV and CL are not cumulative; the lesser applies.
    fb_prime = fb * min(cv, cl)
    capacity = fb_prime * section.sx_mm3 / 1e6
    checks.append(ClauseCheck(
        clause='3.3.1', standard='NDS 2018', label='Bending',
        status='pass' if moment_kn_m <= capacity else 'fail',
        demand=round(moment_kn_m, 2), capacity=round(capacity, 2), unit='kN*m',
        basis=f"Fb' = Fb * CD {NDS_CD} * CM {NDS_CM} * Ct {NDS_CT} * "
              f'min(CV {cv:.3f}, CL {cl:.3f})'))

    shear_capacity = (2.0 / 3.0) * material.shear_strength_mpa * NDS_CD \
        * section.area_mm2 / 1e3
    checks.append(ClauseCheck(
        clause='3.4.3', standard='NDS 2018', label='Horizontal shear',
        status='pass' if shear_kn <= shear_capacity else 'fail',
        demand=round(shear_kn, 2), capacity=round(shear_capacity, 2), unit='kN',
        basis="Fv' * 2/3 * A for a rectangular section"))

    span_mm = span_m * 1000.0
    for label, value, limit in (('Live load deflection', live_deflection_mm, live_limit),
                                ('Total load deflection', total_deflection_mm,
                                 total_limit)):
        allowed = span_mm / limit
        checks.append(ClauseCheck(
            clause='Table 1604.3', standard='IBC 2021', label=label,
            status='pass' if value <= allowed else 'fail',
            demand=round(value, 2), capacity=round(allowed, 2), unit='mm',
            basis=f'L/{limit} on a {span_m:.2f} m span'))
    checks.append(ClauseCheck(
        clause='3.5.2', standard='NDS 2018', label='Long-term creep deflection',
        status='unevaluated',
        basis='NDS applies Kcr = 1.5 to the dead-load part for glulam. Not computed, '
              'and it is the check that usually governs a long timber span.'))
    checks.append(ClauseCheck(
        clause='Chapter 12', standard='NDS 2018', label='Connections',
        status='unevaluated',
        basis='No fastener, plate or bearing check. Timber connections commonly govern '
              'the member size, so this absence matters more here than in steel.'))
    checks.extend(_unevaluated_common())
    return MemberValidation(
        member_id=member_id, role=role, designation=section.id,
        material_id=material.id, load_combination=combination, checks=checks)


# ---------------------------------------------------------------------------
# Reinforced concrete, ACI 318-19
# ---------------------------------------------------------------------------

PHI_FLEXURE = 0.90
PHI_SHEAR = 0.75
PHI_AXIAL_TIED = 0.65
REBAR_FY_MPA = 420.0
BEAM_STEEL_RATIO = 0.012
COLUMN_STEEL_RATIO = 0.020
COVER_TO_CENTROID_MM = 65.0


def validate_concrete_beam(
    *, member_id: str, role: str, section: SectionProperties, material: Material,
    span_m: float, moment_kn_m: float, shear_kn: float,
    live_deflection_mm: float, total_deflection_mm: float,
    live_limit: int, total_limit: int, combination: str,
) -> MemberValidation:
    checks: list[ClauseCheck] = []
    b = section.width_mm
    d = max(0.35 * section.depth_mm, section.depth_mm - COVER_TO_CENTROID_MM)
    fc = material.strength_mpa
    steel_area = BEAM_STEEL_RATIO * b * d
    a = steel_area * REBAR_FY_MPA / (0.85 * fc * b)
    beta1 = max(0.65, min(0.85, 0.85 - 0.05 * (fc - 28.0) / 7.0))
    c = a / beta1
    strain = 0.003 * (d - c) / c if c > 0 else 1.0
    phi = PHI_FLEXURE if strain >= 0.005 else 0.65
    capacity = phi * steel_area * REBAR_FY_MPA * (d - a / 2.0) / 1e6

    checks.append(ClauseCheck(
        clause='21.2.2', standard='ACI 318-19', label='Tension-controlled section',
        status='pass' if strain >= 0.005 else 'fail',
        demand=round(strain, 5), capacity=0.005, unit='strain',
        basis=f'eps_t at nominal strength; phi taken as {phi:.2f}'))
    checks.append(ClauseCheck(
        clause='22.2', standard='ACI 318-19', label='Flexure',
        status='pass' if moment_kn_m <= capacity else 'fail',
        demand=round(moment_kn_m, 2), capacity=round(capacity, 2), unit='kN*m',
        basis=f'Whitney stress block, rho = {BEAM_STEEL_RATIO}, '
              f'As = {steel_area:.0f} mm2, a = {a:.0f} mm'))

    minimum = max(0.25 * math.sqrt(fc) / REBAR_FY_MPA, 1.4 / REBAR_FY_MPA) * b * d
    checks.append(ClauseCheck(
        clause='9.6.1.2', standard='ACI 318-19', label='Minimum flexural reinforcement',
        status='pass' if steel_area >= minimum else 'fail',
        demand=round(minimum, 0), capacity=round(steel_area, 0), unit='mm2',
        basis='As,min = max(0.25*sqrt(fc)/fy, 1.4/fy) * bw * d'))

    vc = PHI_SHEAR * 0.17 * math.sqrt(fc) * b * d / 1000.0
    checks.append(ClauseCheck(
        clause='22.5.5.1', standard='ACI 318-19', label='Shear, concrete alone',
        status='pass' if shear_kn <= vc else 'fail',
        demand=round(shear_kn, 2), capacity=round(vc, 2), unit='kN',
        basis='phi*0.17*lambda*sqrt(fc)*bw*d. No stirrups are designed, so Vs = 0 and '
              'the result is conservative.'))

    span_mm = span_m * 1000.0
    for label, value, limit in (('Live load deflection', live_deflection_mm, live_limit),
                                ('Total load deflection', total_deflection_mm,
                                 total_limit)):
        allowed = span_mm / limit
        checks.append(ClauseCheck(
            clause='Table 1604.3', standard='IBC 2021', label=label,
            status='pass' if value <= allowed else 'fail',
            demand=round(value, 2), capacity=round(allowed, 2), unit='mm',
            basis=f'L/{limit}, cracked stiffness 0.35*Ig per ACI 6.6.3.1.1'))
    checks.append(ClauseCheck(
        clause='24.2.4', standard='ACI 318-19', label='Long-term deflection',
        status='unevaluated',
        basis='Sustained-load multiplier for creep and shrinkage is not applied.'))
    checks.append(ClauseCheck(
        clause='25.4', standard='ACI 318-19', label='Development and splices',
        status='unevaluated',
        basis='Bar development length, cut-off points and lap splices are not laid out.'))
    checks.extend(_unevaluated_common())
    return MemberValidation(
        member_id=member_id, role=role, designation=section.id,
        material_id=material.id, load_combination=combination, checks=checks)


def validate_concrete_column(
    *, member_id: str, section: SectionProperties, material: Material,
    unbraced_length_m: float, axial_kn: float, combination: str,
) -> MemberValidation:
    checks: list[ClauseCheck] = []
    gross = section.area_mm2
    steel = COLUMN_STEEL_RATIO * gross
    fc = material.strength_mpa
    short = 0.80 * PHI_AXIAL_TIED * (
        0.85 * fc * (gross - steel) + REBAR_FY_MPA * steel) / 1000.0
    slenderness = unbraced_length_m * 1000.0 / max(section.ry_mm, 1e-6)
    factor = 1.0 if slenderness <= 22.0 else max(0.35, 1.0 - (slenderness - 22.0) / 100.0)
    capacity = short * factor

    checks.append(ClauseCheck(
        clause='22.4.2', standard='ACI 318-19', label='Axial compression, tied column',
        status='pass' if axial_kn <= capacity else 'fail',
        demand=round(axial_kn, 2), capacity=round(capacity, 2), unit='kN',
        basis=f'0.80*phi*(0.85 fc (Ag - Ast) + fy Ast), rho_g = {COLUMN_STEEL_RATIO}, '
              f'phi = {PHI_AXIAL_TIED}'))
    checks.append(ClauseCheck(
        clause='10.6.1.1', standard='ACI 318-19', label='Longitudinal reinforcement ratio',
        status='pass' if 0.01 <= COLUMN_STEEL_RATIO <= 0.08 else 'fail',
        demand=COLUMN_STEEL_RATIO, capacity=0.08, unit='rho_g',
        basis='ACI 318 permits 0.01 to 0.08 in a tied column'))
    checks.append(ClauseCheck(
        clause='6.6.4', standard='ACI 318-19', label='Slenderness, moment magnification',
        status='unevaluated' if slenderness > 22.0 else 'pass',
        demand=round(slenderness, 1), capacity=22.0, unit='kLu/r',
        basis=('Below 22 the column is short and no magnification is required.'
               if slenderness <= 22.0 else
               f'kLu/r = {slenderness:.0f} exceeds 22, so ACI requires the moment '
               f'magnifier, which needs end moments this gravity-only run does not '
               f'compute. A linear reduction to {factor:.2f} stands in and is stated '
               f'rather than hidden.')))
    checks.append(ClauseCheck(
        clause='25.7.2', standard='ACI 318-19', label='Transverse reinforcement',
        status='unevaluated',
        basis='Tie size and spacing are not designed.'))
    checks.extend(_unevaluated_common())
    return MemberValidation(
        member_id=member_id, role='column', designation=section.id,
        material_id=material.id, load_combination=combination, checks=checks)


# ---------------------------------------------------------------------------
# What no material check covers
# ---------------------------------------------------------------------------

# Set by the compiler once a site exists, so every member record can report the
# environmental actions rather than say they are absent. Held out of band because a
# member check is called from deep inside the sizing loop and threading a site through
# every signature would be a wide change for one read.
#
# A context variable rather than a plain module global: the API compiles runs on worker
# threads (`main.generate` hands `compile_generation` to `asyncio.to_thread`), and a
# global would be shared by every concurrent upload -- so two runs in flight could
# report each other's wind and seismic figures, on member records that look entirely
# ordinary. Each thread carries its own context, so a run's loads stay inside the run
# that computed them, and a run that fails before setting them cannot leave a stale
# site behind for the next one.
_SITE_LOADS: ContextVar = ContextVar('site_loads', default=None)


def set_site_loads(loads) -> None:
    """Give the member checks a site. Passing `None` restores the siteless behaviour."""
    _SITE_LOADS.set(loads)


def _environmental_clauses() -> list[ClauseCheck]:
    """The three actions that need a place, reported against the place there is.

    Without a site these say so. With one they carry the computed figure -- and stay
    `unevaluated` until a person has stood behind the parameters behind it, because a
    base shear derived from a language model's recollection of a seismic map is a number
    with a citation attached to a guess. `design_ready` is that distinction, and it is
    the site module's `SourcedValue` provenance arriving here intact.
    """
    loads = _SITE_LOADS.get()
    if loads is None:
        return [
            ClauseCheck(
                clause='Chapters 26-30', standard='ASCE 7-16', label='Wind load',
                status='unevaluated',
                basis='No site. Wind needs a basic wind speed, an exposure category '
                      'and a topographic factor, and `site.py` supplies all three once '
                      'a location is resolved.'),
            ClauseCheck(
                clause='Chapters 11-12', standard='ASCE 7-16', label='Seismic load',
                status='unevaluated',
                basis='No site. Seismic needs mapped spectral accelerations and a site '
                      'class, and it governs the lateral system this model draws.'),
            ClauseCheck(
                clause='Chapter 7', standard='ASCE 7-16', label='Snow load',
                status='unevaluated',
                basis='No site. A roof live load of 0.96 kPa stands in, which is a '
                      'different action with different combination factors.'),
        ]

    def clause(result, code: str, label: str) -> ClauseCheck:
        return ClauseCheck(
            clause=code, standard='ASCE 7-16', label=label,
            status='pass' if result.design_ready else 'unevaluated',
            demand=result.value, unit=result.unit,
            basis=(f'{result.clause}: {result.basis} '
                   + ('Every input is human-set or human-verified.'
                      if result.design_ready else
                      'At least one input is still a lookup or a proposal, so this is '
                      'an indicative figure and not a design value.')))

    return [
        clause(loads.wind, 'Chapters 26-30', 'Wind load'),
        clause(loads.seismic, 'Chapters 11-12', 'Seismic load'),
        clause(loads.snow, 'Chapter 7', 'Snow load'),
    ]


def _unevaluated_common() -> list[ClauseCheck]:
    """Clauses listed on every member check, evaluated or not.

    Repeating them per member is deliberate. A reviewer reads one member's calculation,
    not a preamble, and a gap that appears only in a project-level note is a gap that
    gets missed.
    """
    return [
        *_environmental_clauses(),
        ClauseCheck(
            clause='Table 601', standard='IBC 2021', label='Fire-resistance rating',
            status='unevaluated',
            basis='No fire protection is designed. The construction type is screened '
                  'in `codes.py`; the protection that delivers the rating is not.'),
        ClauseCheck(
            clause='Appendix L', standard='AISC Design Guide 11', label='Floor vibration',
            status='unevaluated',
            basis='Walking-excitation serviceability is not checked, and it commonly '
                  'governs long-span office and library floors.'),
    ]
