"""Site parameters: propose a location, look up the code, hand over to a human.

Five clauses in `validators.py` return `unevaluated` for the same reason -- wind, seismic
and snow all need a site, and this project had none. `codes.UNRESOLVED_JURISDICTION` says
the same thing from the other end: every code gate runs against placeholder tables
because nobody told it where the building is.

The chain here is three steps, and the third one is the point:

1. **A location is proposed.** By an LLM, by a random provider, or by a person. It is a
   guess about where the building sits, and it is labelled as one.
2. **The code parameters are looked up from that location.** Basic wind speed, mapped
   spectral accelerations, ground snow load, the adopted code edition.
3. **Any value can be replaced by a human, one field at a time**, and the replacement
   records who set it.

Step three is what the structure is for. Every value is a `SourcedValue` carrying where
it came from, so `override(params, basic_wind_speed_ms=51.4, by='structural engineer')`
replaces one number, marks that one number `manual`, and leaves the rest alone with their
provenance intact. Nothing has to be re-derived and nothing silently inherits authority
it does not have.

**What these numbers are and are not.** The lookup table below holds values recalled by a
language model, not values read from ASCE 7's maps or a jurisdiction's amendments. They
are the right order of magnitude and they are **not authoritative**: every one carries
`needs_review=True` until a person clears it, and `SiteParameters.authoritative` is False
while any of them does. A design decision made on an unreviewed value is a design
decision made on a guess with a citation attached to it, which is more dangerous than a
guess without one -- so the flag travels with the number and the reports print it.
"""

from __future__ import annotations

from typing import Any, Callable, Literal, Protocol

from pydantic import BaseModel

# Where a value came from. The order is roughly increasing authority, and only `manual`
# and `verified_lookup` are strong enough to design on.
ValueSource = Literal[
    'default_placeholder',  # nobody chose it; a conservative stand-in
    'llm_proposed',         # a language model suggested it
    'code_lookup',          # read from this module's table, itself LLM-recalled
    'verified_lookup',      # a person checked it against the published source
    'manual',               # a person supplied it
]

STRONG_SOURCES: frozenset[str] = frozenset({'verified_lookup', 'manual'})


class SourcedValue(BaseModel):
    """One parameter, and the honest account of where it came from."""

    value: float | int | str | bool | None
    source: ValueSource
    basis: str
    set_by: str | None = None
    needs_review: bool = True

    @property
    def authoritative(self) -> bool:
        return self.source in STRONG_SOURCES and not self.needs_review

    def replaced_with(self, value: Any, *, by: str, basis: str = '') -> 'SourcedValue':
        """A human value in place of this one. The only way to reach `manual`."""
        return SourcedValue(
            value=value, source='manual', set_by=by, needs_review=False,
            basis=basis or f'Set by {by}, replacing a {self.source} value of '
                           f'{self.value}.')

    def verified(self, *, by: str, basis: str = '') -> 'SourcedValue':
        """The same number, but somebody has now checked it against the source."""
        return self.model_copy(update={
            'source': 'verified_lookup', 'set_by': by, 'needs_review': False,
            'basis': basis or f'{self.basis} Checked against the published source by '
                              f'{by}.'})


class SiteLocation(BaseModel):
    """Where the building is proposed to be."""

    country: str
    region: str
    city: str
    latitude: float | None = None
    longitude: float | None = None
    source: ValueSource = 'llm_proposed'
    set_by: str | None = None
    rationale: str = ''

    @property
    def key(self) -> str:
        return f'{self.country}/{self.region}/{self.city}'.lower()


class SiteParameters(BaseModel):
    """Everything the load standards and the code gates need from a place.

    Each field is a `SourcedValue` rather than a number, because the question a reviewer
    asks about a basic wind speed is not what it is -- it is who says so.
    """

    location: SiteLocation

    # ASCE 7-16 Chapter 26, wind
    basic_wind_speed_ms: SourcedValue
    wind_exposure_category: SourcedValue
    topographic_factor_kzt: SourcedValue

    # ASCE 7-16 Chapters 11-12, seismic
    mapped_ss: SourcedValue
    mapped_s1: SourcedValue
    site_class: SourcedValue
    seismic_design_category: SourcedValue

    # ASCE 7-16 Chapter 7, snow
    ground_snow_kpa: SourcedValue
    snow_exposure_ce: SourcedValue
    thermal_factor_ct: SourcedValue

    # Code administration
    adopted_building_code: SourcedValue
    adopted_load_standard: SourcedValue
    risk_category: SourcedValue
    sprinklered: SourcedValue

    @property
    def values(self) -> dict[str, SourcedValue]:
        return {name: value for name, value in self
                if isinstance(value, SourcedValue)}

    @property
    def needing_review(self) -> list[str]:
        return sorted(name for name, value in self.values.items()
                      if value.needs_review)

    @property
    def authoritative(self) -> bool:
        """True only when a person has stood behind every value."""
        return not self.needing_review

    def summary(self) -> str:
        strong = sum(1 for v in self.values.values() if v.authoritative)
        return (f'{self.location.city}, {self.location.region}: {strong}/'
                f'{len(self.values)} parameters are human-set or human-verified; '
                f'{len(self.needing_review)} still need review')


# ---------------------------------------------------------------------------
# Proposing a location
# ---------------------------------------------------------------------------

class LocationProvider(Protocol):
    """Anything that can name a site. The seam a human replaces."""

    def propose(self) -> SiteLocation:
        ...


class StaticLocationProvider:
    """A location somebody chose. The provider a real project uses."""

    def __init__(self, location: SiteLocation) -> None:
        self._location = location.model_copy(update={
            'source': 'manual', 'set_by': location.set_by or 'project'})

    def propose(self) -> SiteLocation:
        return self._location


class LlmLocationProvider:
    """A location a language model proposes, normalised into the schema.

    `generate` returns a mapping; anything it omits is filled with the default and the
    whole result is marked `llm_proposed`. Normalising here rather than trusting the
    model's shape is the same rule the brief providers already follow: the pipeline
    accepts one schema, and where the value came from is recorded rather than implied.
    """

    def __init__(self, generate: Callable[[], dict[str, Any]],
                 fallback: SiteLocation | None = None) -> None:
        self._generate = generate
        self._fallback = fallback or DEFAULT_LOCATION

    def propose(self) -> SiteLocation:
        try:
            raw = self._generate() or {}
        except Exception as error:  # pragma: no cover - provider-specific
            return self._fallback.model_copy(update={
                'rationale': f'The language model provider failed ({error}); the '
                             f'default location stands in and is marked as such.'})
        return SiteLocation(
            country=str(raw.get('country') or self._fallback.country),
            region=str(raw.get('region') or self._fallback.region),
            city=str(raw.get('city') or self._fallback.city),
            latitude=raw.get('latitude'), longitude=raw.get('longitude'),
            source='llm_proposed', set_by=str(raw.get('model') or 'language model'),
            rationale=str(raw.get('rationale') or
                          'Proposed by a language model; not a site selection.'))


DEFAULT_LOCATION = SiteLocation(
    country='US', region='California', city='Los Angeles',
    latitude=34.05, longitude=-118.24, source='default_placeholder',
    rationale='The stand-in when no provider names a site. Chosen because it exercises '
              'a high-seismic, low-snow case rather than because the building belongs '
              'there.')


# ---------------------------------------------------------------------------
# Looking the code up from the location
# ---------------------------------------------------------------------------
#
# Recalled values, not read values. Every one of them leaves this table with
# `needs_review=True`, and the honest use of the table is to get a run moving and to
# show a reviewer exactly which numbers to go and check.

_LOOKUP: dict[str, dict[str, Any]] = {
    'us/california/los angeles': {
        'wind_ms': 42.5, 'exposure': 'B', 'ss': 1.75, 's1': 0.65,
        'site_class': 'D', 'sdc': 'D', 'snow_kpa': 0.0,
        'code': 'California Building Code 2022 (IBC 2021 with amendments)',
        'standard': 'ASCE 7-16',
    },
    'us/new york/new york': {
        'wind_ms': 51.4, 'exposure': 'B', 'ss': 0.28, 's1': 0.07,
        'site_class': 'D', 'sdc': 'B', 'snow_kpa': 1.20,
        'code': 'NYC Building Code 2022 (IBC 2015 with amendments)',
        'standard': 'ASCE 7-16',
    },
    'us/illinois/chicago': {
        'wind_ms': 47.8, 'exposure': 'B', 'ss': 0.12, 's1': 0.06,
        'site_class': 'D', 'sdc': 'A', 'snow_kpa': 1.20,
        'code': 'Chicago Building Code 2022 (IBC 2018 with amendments)',
        'standard': 'ASCE 7-16',
    },
    'us/washington/seattle': {
        'wind_ms': 43.4, 'exposure': 'B', 'ss': 1.42, 's1': 0.49,
        'site_class': 'D', 'sdc': 'D', 'snow_kpa': 0.96,
        'code': 'Washington State Building Code 2021 (IBC 2021)',
        'standard': 'ASCE 7-16',
    },
    'us/massachusetts/boston': {
        'wind_ms': 56.3, 'exposure': 'B', 'ss': 0.22, 's1': 0.07,
        'site_class': 'D', 'sdc': 'B', 'snow_kpa': 1.92,
        'code': 'Massachusetts State Building Code 9th ed. (IBC 2015)',
        'standard': 'ASCE 7-16',
    },
    'us/florida/miami': {
        'wind_ms': 76.0, 'exposure': 'C', 'ss': 0.05, 's1': 0.02,
        'site_class': 'D', 'sdc': 'A', 'snow_kpa': 0.0,
        'code': 'Florida Building Code 2023 (IBC 2021 with HVHZ amendments)',
        'standard': 'ASCE 7-16',
    },
}

# Where the location is not in the table, these stand in. They are deliberately not
# conservative in the useful sense -- a made-up wind speed is not safe just because it
# is large -- so they are marked as placeholders and every gate that reads them says so.
_UNKNOWN = {
    'wind_ms': 51.4, 'exposure': 'B', 'ss': 0.50, 's1': 0.20,
    'site_class': 'D', 'sdc': 'C', 'snow_kpa': 1.00,
    'code': 'unresolved', 'standard': 'ASCE 7-16',
}


def lookup(location: SiteLocation) -> SiteParameters:
    """Code parameters for a location, every one of them flagged for review."""
    known = _LOOKUP.get(location.key)
    data = known or _UNKNOWN
    source: ValueSource = 'code_lookup' if known else 'default_placeholder'
    where = f'{location.city}, {location.region}'
    note = ('' if known else
            f' No entry for {where} in this table, so a generic value stands in and '
            f'must be replaced before any result is used.')

    def sourced(value: Any, basis: str) -> SourcedValue:
        return SourcedValue(value=value, source=source, basis=basis + note,
                            needs_review=True)

    return SiteParameters(
        location=location,
        basic_wind_speed_ms=sourced(
            data['wind_ms'],
            f'ASCE 7-16 Figure 26.5-1B basic wind speed for Risk Category II at '
            f'{where}, recalled rather than read from the map.'),
        wind_exposure_category=sourced(
            data['exposure'],
            'ASCE 7-16 26.7.3 surface roughness category; an urban site is normally B.'),
        topographic_factor_kzt=sourced(
            1.0, 'ASCE 7-16 26.8.2. Kzt is 1.0 on level terrain; a hill or escarpment '
                 'needs the real topography.'),
        mapped_ss=sourced(
            data['ss'], f'ASCE 7-16 Figure 22-1 mapped short-period acceleration at '
                        f'{where}, recalled rather than read from the USGS tool.'),
        mapped_s1=sourced(
            data['s1'], f'ASCE 7-16 Figure 22-2 mapped one-second acceleration at '
                        f'{where}, recalled rather than read.'),
        site_class=sourced(
            data['site_class'],
            'ASCE 7-16 Table 20.3-1. Site Class D is the default where no geotechnical '
            'report exists, which is the case here.'),
        seismic_design_category=sourced(
            data['sdc'], 'ASCE 7-16 Tables 11.6-1 and 11.6-2, from Ss, S1 and the risk '
                         'category.'),
        ground_snow_kpa=sourced(
            data['snow_kpa'],
            f'ASCE 7-16 Figure 7.2-1 ground snow load at {where}, recalled rather than '
            f'read.'),
        snow_exposure_ce=sourced(
            1.0, 'ASCE 7-16 Table 7.3-1, partially exposed roof in Terrain Category B.'),
        thermal_factor_ct=sourced(
            1.0, 'ASCE 7-16 Table 7.3-2 for a heated building.'),
        adopted_building_code=sourced(
            data['code'], 'The edition and amendments the jurisdiction has adopted, '
                          'which is the field a plan checker looks at first.'),
        adopted_load_standard=sourced(
            data['standard'], 'The load standard the adopted code references.'),
        risk_category=sourced(
            2, 'IBC Table 1604.5. Risk Category II covers ordinary assembly and '
               'business occupancies; an assembly space over 300 people can push a '
               'building to III.'),
        sprinklered=sourced(
            True, 'Assumed sprinklered throughout, which every egress width and travel '
                  'distance in `life_safety.py` depends on. Turning it off changes '
                  'them.'))


def override(parameters: SiteParameters, *, by: str, **values: Any) -> SiteParameters:
    """Replace named parameters with human-supplied ones, leaving the rest alone.

    This is the handover the whole module exists for. A structural engineer who has the
    real wind speed replaces one field:

        parameters = override(site, by='J. Ito, SE', basic_wind_speed_ms=51.4)

    and that field alone becomes `manual`. Everything else keeps its own provenance, so
    a report can still show which numbers a person stood behind and which are still a
    language model's recollection.
    """
    updates: dict[str, Any] = {}
    for name, value in values.items():
        current = getattr(parameters, name, None)
        if not isinstance(current, SourcedValue):
            raise KeyError(f'{name} is not a sourced site parameter')
        updates[name] = current.replaced_with(value, by=by)
    return parameters.model_copy(update=updates)


def mark_verified(parameters: SiteParameters, *, by: str,
                  names: list[str] | None = None) -> SiteParameters:
    """Record that a person has checked values against the published source."""
    targets = names or list(parameters.values)
    updates = {name: getattr(parameters, name).verified(by=by) for name in targets}
    return parameters.model_copy(update=updates)


def resolve_site(provider: LocationProvider | None = None) -> SiteParameters:
    """Propose a location and look it up. The normal entry point."""
    location = (provider or StaticLocationProvider(DEFAULT_LOCATION)).propose()
    return lookup(location)


def to_jurisdiction(parameters: SiteParameters) -> 'JurisdictionProfile':
    """Hand the site to the code-gate layer.

    `codes.py` has run every gate against placeholder tables since it was written,
    because `UNRESOLVED_JURISDICTION` was the only profile that existed. A site supplies
    the four fields those gates actually need. It is marked `resolved` only when a
    person has stood behind the values -- an LLM-recalled code edition is not a resolved
    jurisdiction, and a gate that returned `pass` on one would be worse than the
    placeholder it replaced.
    """
    from .codes import JurisdictionProfile

    resolved = parameters.authoritative
    return JurisdictionProfile(
        id=f'SITE-{parameters.location.key.replace("/", "-").replace(" ", "-")}',
        status='resolved' if resolved else 'unresolved',
        adopted_building_code=str(parameters.adopted_building_code.value),
        adopted_load_standard=str(parameters.adopted_load_standard.value),
        sprinklered=bool(parameters.sprinklered.value),
        risk_category=int(parameters.risk_category.value or 2),
        seismic_design_category=str(parameters.seismic_design_category.value),
        local_amendments=[
            f'{name}: {getattr(parameters, name).source}'
            for name in parameters.needing_review],
        source_urls=['https://ascehazardtool.org/',
                     'https://codes.iccsafe.org/'])
