"""Propose a location, look up the code, hand the numbers to a person.

The chain exists so the third step is cheap. Every site parameter carries where it came
from, so a structural engineer with the real wind speed replaces one field and that field
alone becomes `manual` -- nothing is re-derived, and nothing silently inherits authority
it does not have.

The rule these tests hold: **a value nobody has reviewed cannot become a design value.**
Wind, seismic and snow are computed as soon as a site exists, and they stay `unevaluated`
with the figure shown until a human stands behind the parameters behind them. A base
shear derived from a language model's recollection of a seismic map is a guess with a
citation attached, which is more dangerous than a guess without one.
"""

import json
from pathlib import Path

import pytest

from backend.app import site_loads
from backend.app.compiler_v3 import compile_building_model_v3
from backend.app.models import ArchitecturalScore, AudioFeatures
from backend.app.site import (
    DEFAULT_LOCATION, STRONG_SOURCES, LlmLocationProvider, SiteLocation,
    StaticLocationProvider, lookup, mark_verified, override, resolve_site,
    to_jurisdiction,
)

ROOT = Path(__file__).parents[2]
DEMO = ROOT / 'artifacts' / 'v3_demo'
V2_DEMO = (ROOT / 'artifacts' / 'integrated_demo'
           / 'building-b7ad95fa45a6-library-steel-international-v1')


@pytest.fixture(scope='module')
def features() -> AudioFeatures:
    return AudioFeatures.model_validate(
        json.loads((V2_DEMO / 'music_features.json').read_text(encoding='utf-8')))


@pytest.fixture(scope='module')
def template() -> ArchitecturalScore:
    return ArchitecturalScore.model_validate(
        json.loads((DEMO / 'architectural_score.json').read_text(encoding='utf-8')))


def _chicago() -> LlmLocationProvider:
    return LlmLocationProvider(lambda: {
        'country': 'US', 'region': 'Illinois', 'city': 'Chicago',
        'model': 'test-model', 'rationale': 'a cold, windy, low-seismic case'})


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

def test_a_looked_up_value_is_never_authoritative_on_its_own():
    site = resolve_site(_chicago())
    assert not site.authoritative
    assert len(site.needing_review) == len(site.values)
    for value in site.values.values():
        assert value.source not in STRONG_SOURCES
        assert value.needs_review
        assert value.basis


def test_an_llm_proposed_location_says_so():
    site = resolve_site(_chicago())
    assert site.location.source == 'llm_proposed'
    assert site.location.set_by == 'test-model'
    assert site.location.rationale


def test_a_provider_that_fails_falls_back_and_records_it():
    def broken() -> dict:
        raise RuntimeError('no model available')

    location = LlmLocationProvider(broken).propose()
    assert location.city == DEFAULT_LOCATION.city
    assert 'failed' in location.rationale


def test_a_location_somebody_chose_is_manual():
    chosen = SiteLocation(country='US', region='Oregon', city='Portland',
                          set_by='project team')
    site = resolve_site(StaticLocationProvider(chosen))
    assert site.location.source == 'manual'
    assert site.location.set_by == 'project team'


def test_overriding_one_field_leaves_the_others_alone():
    """The handover the whole module exists for."""
    site = resolve_site(_chicago())
    revised = override(site, by='J. Ito, SE', basic_wind_speed_ms=49.2)

    assert revised.basic_wind_speed_ms.value == 49.2
    assert revised.basic_wind_speed_ms.source == 'manual'
    assert revised.basic_wind_speed_ms.set_by == 'J. Ito, SE'
    assert not revised.basic_wind_speed_ms.needs_review
    # everything else keeps its own provenance
    assert revised.mapped_ss.source == site.mapped_ss.source
    assert revised.mapped_ss.needs_review
    assert revised.needing_review == [
        name for name in site.needing_review if name != 'basic_wind_speed_ms']


def test_overriding_something_that_is_not_a_parameter_is_an_error():
    site = resolve_site(_chicago())
    with pytest.raises(KeyError):
        override(site, by='someone', not_a_parameter=1.0)


def test_verifying_every_value_makes_the_site_authoritative():
    site = mark_verified(resolve_site(_chicago()), by='AHJ review')
    assert site.authoritative
    assert not site.needing_review
    for value in site.values.values():
        assert value.source == 'verified_lookup'
        assert value.set_by == 'AHJ review'


def test_an_unknown_location_gets_a_placeholder_that_says_so():
    site = lookup(SiteLocation(country='NZ', region='Otago', city='Dunedin'))
    assert site.basic_wind_speed_ms.source == 'default_placeholder'
    assert 'No entry' in site.basic_wind_speed_ms.basis
    assert 'must be replaced' in site.basic_wind_speed_ms.basis


# ---------------------------------------------------------------------------
# The code lookup reaches the jurisdiction gate
# ---------------------------------------------------------------------------

def test_an_unreviewed_site_does_not_resolve_the_jurisdiction():
    """An LLM-recalled code edition is not a resolved jurisdiction.

    A code gate that returned `pass` on one would be worse than the placeholder it
    replaced, because it would look like a check that had happened.
    """
    jurisdiction = to_jurisdiction(resolve_site(_chicago()))
    assert not jurisdiction.resolved
    assert jurisdiction.local_amendments  # names every field still under review


def test_a_verified_site_resolves_the_jurisdiction():
    site = mark_verified(resolve_site(_chicago()), by='AHJ review')
    jurisdiction = to_jurisdiction(site)
    assert jurisdiction.resolved
    assert jurisdiction.adopted_building_code
    assert jurisdiction.seismic_design_category


# ---------------------------------------------------------------------------
# Loads follow the place
# ---------------------------------------------------------------------------

def test_the_governing_environmental_action_changes_with_the_location():
    """Miami is a wind problem and Los Angeles is a seismic one.

    If the loads did not flip between them the lookup would be decoration.
    """
    def at(city: str, region: str):
        provider = LlmLocationProvider(
            lambda: {'country': 'US', 'region': region, 'city': city})
        return site_loads.compute(
            resolve_site(provider), height_m=24.0, width_m=44.0,
            seismic_weight_kn=42000.0,
            structural_system_id='STR-SYS-STEEL-FRAME')

    miami = at('Miami', 'Florida')
    angeles = at('Los Angeles', 'California')
    chicago = at('Chicago', 'Illinois')

    assert miami.wind.value > miami.seismic.value
    assert angeles.seismic.value > angeles.wind.value
    assert chicago.snow.value > 0.0
    assert miami.snow.value == 0.0


def test_a_load_is_only_design_ready_when_its_inputs_are():
    provider = _chicago()
    raw = site_loads.compute(resolve_site(provider), height_m=24.0, width_m=44.0,
                             seismic_weight_kn=42000.0,
                             structural_system_id='STR-SYS-STEEL-FRAME')
    assert not raw.design_ready
    for result in (raw.snow, raw.wind, raw.seismic):
        assert result.status == 'indicative'
        assert not result.design_ready

    verified = site_loads.compute(
        mark_verified(resolve_site(provider), by='J. Ito, SE'), height_m=24.0,
        width_m=44.0, seismic_weight_kn=42000.0,
        structural_system_id='STR-SYS-STEEL-FRAME')
    assert verified.design_ready
    assert all(r.status == 'computed'
               for r in (verified.snow, verified.wind, verified.seismic))


def test_a_system_with_no_response_modification_factor_gets_no_base_shear():
    """A system absent from Table 12.2-1 has no R, and inventing one would be worse."""
    result = site_loads.seismic_base_shear(
        resolve_site(_chicago()), seismic_weight_kn=10000.0,
        structural_system_id='STR-SYS-TENSILE-MEMBRANE')
    assert result.value == 0.0
    assert not result.design_ready
    assert 'no response modification coefficient' in result.basis


def test_snow_follows_the_published_equation():
    site = resolve_site(_chicago())
    result = site_loads.flat_roof_snow(site)
    pg = float(site.ground_snow_kpa.value)
    assert result.value == pytest.approx(0.7 * pg, abs=1e-6)
    assert result.clause == 'ASCE 7-16 7.3.1'


# ---------------------------------------------------------------------------
# The pipeline carries it through
# ---------------------------------------------------------------------------

def test_a_compiled_model_carries_its_site_and_its_loads(features, template):
    model = compile_building_model_v3(features, template, massing_id='MAS-SLAB',
                                      typology='library')
    assert model.site is not None
    assert model.site_loads is not None
    assert model.site.needing_review  # the default site is not reviewed


def test_the_environmental_clauses_are_evaluated_once_a_site_is_verified(
        features, template):
    """The three clauses that were `unevaluated` on every member for want of a place."""
    site = mark_verified(resolve_site(_chicago()), by='J. Ito, SE')
    model = compile_building_model_v3(features, template, massing_id='MAS-SLAB',
                                      typology='library', site=site)
    checks = model.sizing[0]
    assert checks  # the member schedule exists

    from backend.app.registry import spec_for
    from backend.app.loads import LoadCase
    from backend.app.sizing import check_beam

    section = spec_for(model.sizing[1].section_id).to_section()
    record = check_beam('B', 8.0, 3.0, LoadCase(dead_kpa=3.0, live_kpa=4.79), section,
                        role='girder', unbraced_length_m=2.5).validation
    environmental = {c.label: c for c in record.checks
                     if c.label in ('Wind load', 'Seismic load', 'Snow load')}
    assert len(environmental) == 3
    for check in environmental.values():
        assert check.status == 'pass', check.label
        assert check.demand is not None
    # the clauses that do not depend on a site are still honestly absent
    absent = {c.label for c in record.unevaluated}
    assert {'Connections', 'Floor vibration', 'Fire-resistance rating'} <= absent


def test_passing_a_site_replaces_the_proposal(features, template):
    miami = resolve_site(LlmLocationProvider(
        lambda: {'country': 'US', 'region': 'Florida', 'city': 'Miami'}))
    model = compile_building_model_v3(features, template, massing_id='MAS-SLAB',
                                      typology='library', site=miami)
    assert model.site.location.city == 'Miami'
    assert model.site_loads.wind.value > model.site_loads.seismic.value
