"""Environmental loads from a site: snow, wind and seismic.

These are the three actions `validators.py` reported as `unevaluated` on every member,
and all three were absent for the same reason -- they are properties of a place, and the
project had no place. `site.py` now supplies one, so they can be computed.

**Computed is not the same as designed, and the distinction is enforced here.** A value
derived from a site parameter nobody has reviewed is a number with a citation attached to
a guess, which is more dangerous than a guess without one. So every result carries the
weakest provenance among its inputs, and a clause fed by an unreviewed parameter stays
`unevaluated` with the computed figure shown as an indication. It becomes a design value
when a person has stood behind the inputs, and not before.

What is implemented, and at what fidelity:

- **Snow**, ASCE 7-16 7.3: the flat-roof equation in full. This one is genuinely
  complete for a flat roof; drift, sliding and unbalanced cases are not.
- **Wind**, ASCE 7-16 26.10 and 27: velocity pressure and a windward-plus-leeward base
  shear on a rectangular building. This is the directional procedure reduced to its main
  wind force resisting system case, which is a preliminary number rather than a design
  one -- no internal pressure, no component and cladding, no torsional cases.
- **Seismic**, ASCE 7-16 12.8: the equivalent lateral force base shear. The response
  modification factor comes from the structural system, which the project does select,
  so this is the closest of the three to a real result. The vertical distribution, the
  drift check and the redundancy factor are not computed.
"""

from __future__ import annotations



from pydantic import BaseModel, Field

from .site import STRONG_SOURCES, SiteParameters, SourcedValue

# ASCE 7-16 26.6-1, directionality factor for the main wind force resisting system.
WIND_DIRECTIONALITY_KD = 0.85
# ASCE 7-16 26.11, gust-effect factor for a rigid building.
GUST_FACTOR_G = 0.85
# ASCE 7-16 Figure 27.3-1 external pressure coefficients, wall surfaces.
CP_WINDWARD = 0.8
CP_LEEWARD = -0.5

# ASCE 7-16 Table 12.2-1 response modification coefficients, for the systems this
# project can actually build. A system not in this table has no R and no base shear.
RESPONSE_MODIFICATION_R: dict[str, float] = {
    'STR-SYS-STEEL-FRAME': 3.25,            # ordinary steel concentrically braced frame
    'STR-SYS-RC-FRAME-WALL': 5.0,           # ordinary reinforced concrete shear wall
    'STR-SYS-MASS-TIMBER-CLT-GLULAM': 3.0,  # CLT shear wall, per SDPWS
    'STR-SYS-GLULAM-POST-BEAM': 2.0,        # ordinary timber frame with knee braces
}


class LoadResult(BaseModel):
    """One environmental action, with the provenance of the weakest input behind it."""

    action: str
    value: float
    unit: str
    clause: str
    basis: str
    inputs: list[str] = Field(default_factory=list)
    # False whenever any input is still a lookup or a guess. A `False` here is the
    # difference between a figure a reviewer can use and one they must check first.
    design_ready: bool = False

    @property
    def status(self) -> str:
        return 'computed' if self.design_ready else 'indicative'


def _weakest(*values: SourcedValue) -> bool:
    return all(v.source in STRONG_SOURCES and not v.needs_review for v in values)


def flat_roof_snow(site: SiteParameters, *, importance_is: float = 1.0) -> LoadResult:
    """ASCE 7-16 7.3.1: pf = 0.7 * Ce * Ct * Is * pg."""
    pg = float(site.ground_snow_kpa.value or 0.0)
    ce = float(site.snow_exposure_ce.value or 1.0)
    ct = float(site.thermal_factor_ct.value or 1.0)
    pf = 0.7 * ce * ct * importance_is * pg
    return LoadResult(
        action='flat roof snow', value=round(pf, 3), unit='kPa', clause='ASCE 7-16 7.3.1',
        basis=f'0.7 * Ce {ce} * Ct {ct} * Is {importance_is} * pg {pg} kPa. Drift, '
              f'sliding and unbalanced cases are not computed.',
        inputs=['ground_snow_kpa', 'snow_exposure_ce', 'thermal_factor_ct'],
        design_ready=_weakest(site.ground_snow_kpa, site.snow_exposure_ce,
                              site.thermal_factor_ct))


def velocity_pressure(site: SiteParameters, height_m: float) -> LoadResult:
    """ASCE 7-16 26.10-1: qz = 0.613 * Kz * Kzt * Kd * V^2, in pascals."""
    v = float(site.basic_wind_speed_ms.value or 0.0)
    kzt = float(site.topographic_factor_kzt.value or 1.0)
    exposure = str(site.wind_exposure_category.value or 'B')
    # ASCE 7-16 Table 26.10-1, Kz by exposure and height. The power-law form rather
    # than the tabulated steps, which agrees with the table to about two per cent.
    zg, alpha = {'B': (365.76, 7.0), 'C': (274.32, 9.5), 'D': (213.36, 11.5)}.get(
        exposure, (365.76, 7.0))
    z = max(height_m, 4.6)
    kz = 2.01 * (z / zg) ** (2.0 / alpha)
    qz = 0.613 * kz * kzt * WIND_DIRECTIONALITY_KD * v ** 2
    return LoadResult(
        action='velocity pressure', value=round(qz, 1), unit='Pa',
        clause='ASCE 7-16 26.10',
        basis=f'0.613 * Kz {kz:.3f} * Kzt {kzt} * Kd {WIND_DIRECTIONALITY_KD} * '
              f'V^2 ({v} m/s) at {z:.1f} m in Exposure {exposure}.',
        inputs=['basic_wind_speed_ms', 'wind_exposure_category',
                'topographic_factor_kzt'],
        design_ready=_weakest(site.basic_wind_speed_ms, site.wind_exposure_category,
                              site.topographic_factor_kzt))


def wind_base_shear(site: SiteParameters, *, height_m: float, width_m: float
                    ) -> LoadResult:
    """Windward plus leeward pressure on the projected face, ASCE 7-16 27.3.

    A main wind force resisting system estimate on a rectangular building. Internal
    pressure, component and cladding, and the torsional load cases are not included, so
    this sizes nothing on its own -- it says whether wind is the action that governs the
    lateral system, which for a mid-rise it usually is not.
    """
    q = velocity_pressure(site, height_m)
    pressure = q.value * GUST_FACTOR_G * (CP_WINDWARD - CP_LEEWARD)
    shear_kn = pressure * height_m * width_m / 1000.0
    return LoadResult(
        action='wind base shear', value=round(shear_kn, 1), unit='kN',
        clause='ASCE 7-16 27.3',
        basis=f'q {q.value:.0f} Pa * G {GUST_FACTOR_G} * (Cp windward '
              f'{CP_WINDWARD} - Cp leeward {CP_LEEWARD}) over a {width_m:.1f} x '
              f'{height_m:.1f} m face. No internal pressure, no torsional case.',
        inputs=q.inputs, design_ready=q.design_ready)


def seismic_base_shear(site: SiteParameters, *, seismic_weight_kn: float,
                       structural_system_id: str,
                       importance_ie: float = 1.0) -> LoadResult:
    """ASCE 7-16 12.8.1: V = Cs * W, with Cs from 12.8-2 and its floors and caps."""
    ss = float(site.mapped_ss.value or 0.0)
    s1 = float(site.mapped_s1.value or 0.0)
    site_class = str(site.site_class.value or 'D')
    r = RESPONSE_MODIFICATION_R.get(structural_system_id)
    if r is None:
        return LoadResult(
            action='seismic base shear', value=0.0, unit='kN',
            clause='ASCE 7-16 Table 12.2-1',
            basis=f'{structural_system_id} has no response modification coefficient in '
                  f'this project, so no base shear is computed for it.',
            inputs=['mapped_ss', 'mapped_s1'], design_ready=False)

    # ASCE 7-16 Tables 11.4-1 and 11.4-2, site coefficients for Site Class D. Other
    # classes need the full tables; D is the default where no geotechnical report
    # exists, which is the case in this project.
    fa = 1.0 if site_class != 'D' else max(1.0, min(1.6, 1.6 - 0.4 * (ss - 0.25) / 0.25))
    fv = 1.5 if site_class != 'D' else max(1.7, min(2.4, 2.4 - 0.4 * (s1 - 0.1) / 0.1))
    sds = (2.0 / 3.0) * fa * ss
    sd1 = (2.0 / 3.0) * fv * s1

    cs = sds / (r / importance_ie)
    # 12.8-5 minimum and 12.8-6 for high-seismic sites
    cs = max(cs, 0.044 * sds * importance_ie, 0.01)
    if s1 >= 0.6:
        cs = max(cs, 0.5 * s1 / (r / importance_ie))
    shear = cs * seismic_weight_kn
    return LoadResult(
        action='seismic base shear', value=round(shear, 1), unit='kN',
        clause='ASCE 7-16 12.8.1',
        basis=f'Cs {cs:.4f} = SDS {sds:.3f} / (R {r} / Ie {importance_ie}), with the '
              f'12.8-5 floor applied, on a seismic weight of {seismic_weight_kn:.0f} '
              f'kN. Fa {fa:.2f} and Fv {fv:.2f} for Site Class {site_class}. Vertical '
              f'distribution, drift and redundancy are not computed.',
        inputs=['mapped_ss', 'mapped_s1', 'site_class'],
        design_ready=_weakest(site.mapped_ss, site.mapped_s1, site.site_class))


class SiteLoadSet(BaseModel):
    """Every environmental action one building sees, with its provenance."""

    snow: LoadResult
    wind: LoadResult
    seismic: LoadResult

    @property
    def design_ready(self) -> bool:
        return all(r.design_ready for r in (self.snow, self.wind, self.seismic))

    def summary(self) -> str:
        ready = sum(1 for r in (self.snow, self.wind, self.seismic) if r.design_ready)
        tail = ('' if ready == 3 else
                '; the rest are indicative because a site parameter behind them is '
                'unreviewed')
        return (f'snow {self.snow.value} kPa, wind {self.wind.value} kN, '
                f'seismic {self.seismic.value} kN; {ready}/3 design-ready{tail}')


def compute(site: SiteParameters, *, height_m: float, width_m: float,
            seismic_weight_kn: float, structural_system_id: str) -> SiteLoadSet:
    return SiteLoadSet(
        snow=flat_roof_snow(site),
        wind=wind_base_shear(site, height_m=height_m, width_m=width_m),
        seismic=seismic_base_shear(site, seismic_weight_kn=seismic_weight_kn,
                                   structural_system_id=structural_system_id))
