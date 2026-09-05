"""What the API hands the client, and what it must never quietly improve.

The bundle exists because a dozen reports were computed on the request path and then
discarded. These tests hold the two properties that made it worth extracting: it
carries every report the model holds, and it does not upgrade a status on the way out.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.analysis_bundle import _tally_spatial, compile_analysis_bundle
from backend.app.audio import extract_audio_features
from backend.app.bim_handoff import compile_bim_handoff_report
from backend.app.compiler import compile_building_model
from backend.app.compiler_v3 import compile_building_model_v3
from backend.app.integration import compile_facade_host_handoff
from backend.app.main import app
from backend.app.models import ArchitecturalScore, AudioFeatures
from backend.app.pipeline import drawing_sheet_refs, render_refs
from backend.app.run_store import list_runs, load_run, run_path
from backend.app.score import compile_architectural_score

MP3 = (Path(__file__).parents[2] / 'fixtures' / 'audio'
       / 'gemini_music_to_architecture_44s.mp3')


@pytest.fixture(scope='module')
def features() -> AudioFeatures:
    return extract_audio_features(MP3, MP3.name)


@pytest.fixture(scope='module')
def score(features) -> ArchitecturalScore:
    return compile_architectural_score(features)


@pytest.fixture(scope='module')
def model_v3(features, score):
    return compile_building_model_v3(features, score)


@pytest.fixture(scope='module')
def bundle(model_v3):
    return compile_analysis_bundle(model_v3)


# Fields the bundle deliberately does not carry, each for a stated reason. Anything
# else the model holds has to reach the payload, and the test derives that from the
# model rather than from a list somebody has to remember to extend.
NOT_CARRIED = {
    'units': 'an invariant literal; the payload is always in metres',
    'coordinate_system': 'an invariant literal; always right-handed Z-up',
}
# Present in both and not expected to match, each for a stated reason.
NOT_COMPARED = {
    'element_groups': 'the browser draws instances from the GLB, so the groups travel '
                      'as records without their geometry',
    'schema_version': 'the payload versions itself, not the model it was built from',
}


def test_every_report_the_model_holds_reaches_the_bundle(bundle, model_v3) -> None:
    """A report the compiler produced but the payload drops is invisible work.

    This used to check a hard-coded list of eight field names, which is a test that
    passes for every report nobody added to it. The spatial rules were computed on every
    model, attached to it, and dropped by the bundle -- a whole constraint system the
    client could not see -- and this test said the payload carried every report the model
    held. The registry that resolves each element group's material to something
    renderable went the same way. So the list is derived now, and a new report on the
    model is covered the moment it exists.
    """
    missing = set(type(model_v3).model_fields) - set(type(bundle).model_fields)
    assert missing <= set(NOT_CARRIED), (
        f'the model holds {sorted(missing - set(NOT_CARRIED))} and the bundle has no '
        f'field for it; add it, or name it in NOT_CARRIED with the reason')

    for field in set(type(bundle).model_fields) & set(type(model_v3).model_fields):
        if field in NOT_COMPARED:
            continue
        assert getattr(bundle, field) == getattr(model_v3, field), (
            f'{field} reached the bundle changed')

    # The reports specifically: present, not merely equal to a model that has none.
    for field in ('selection', 'facade_gates', 'constitution', 'life_safety',
                  'dependency_graph', 'axis_report', 'spatial', 'site', 'site_loads'):
        assert getattr(bundle, field) is not None, f'{field} did not reach the bundle'
    assert bundle.materials, 'the material registry did not reach the bundle'


def test_groups_travel_as_records_and_instances_do_not(bundle, model_v3) -> None:
    assert len(bundle.element_groups) == len(model_v3.element_groups)
    assert sum(group.instance_count for group in bundle.element_groups) == model_v3.element_count
    payload = bundle.model_dump_json()
    # The browser draws instances from the GLB. Repeating their coordinates here would
    # triple the response to say the same thing twice.
    assert '"geometry"' not in payload
    assert '"instances"' not in payload


def test_a_group_keeps_the_sentence_that_explains_it(bundle) -> None:
    sized = [group for group in bundle.element_groups
             if group.sizing_status == 'sized_by_calculation']
    assert sized, 'no group was sized by calculation'
    assert all(group.utilisation is not None for group in sized)
    assert all(group.governing_check for group in sized)
    assert all(group.reason for group in bundle.element_groups)


def test_unevaluated_is_its_own_bucket_and_never_a_pass(bundle, model_v3) -> None:
    tallies = {tally.source: tally for tally in bundle.compliance.tallies}
    findings = model_v3.life_safety.findings
    life = tallies['life_safety']
    assert life.passed == sum(1 for f in findings if f.status == 'pass')
    assert life.failed == sum(1 for f in findings if f.status == 'fail')
    assert life.unevaluated == sum(1 for f in findings if f.status == 'unevaluated')
    assert life.total == len(findings)
    assert bundle.compliance.unevaluated_total == sum(
        tally.unevaluated for tally in bundle.compliance.tallies)


def test_a_load_computed_from_unreviewed_inputs_is_not_reported_as_a_pass(bundle) -> None:
    """`site.py` refuses to design on a recalled code value; the roll-up must agree."""
    tally = next(t for t in bundle.compliance.tallies if t.source == 'site_loads')
    assert tally.passed == 0
    assert tally.unevaluated == 3
    assert len(tally.blockers) == 3


def test_the_rollup_covers_the_v2_chain_when_it_is_handed_in(features, score, model_v3) -> None:
    model_v2 = compile_building_model(features, score)
    handoff = compile_facade_host_handoff(score, model_v2)
    joined = compile_analysis_bundle(
        model_v3, validation=model_v2.validation, pipeline_gates=handoff.gates)
    sources = {tally.source for tally in joined.compliance.tallies}
    assert {'massing_validation', 'pipeline_gates'} <= sources
    alone = compile_analysis_bundle(model_v3)
    assert joined.compliance.checked_total > alone.compliance.checked_total


def test_bim_handoff_report_reaches_the_bundle(model_v3) -> None:
    report = compile_bim_handoff_report(model_v3)
    joined = compile_analysis_bundle(model_v3, bim_handoff=report)

    assert joined.bim_handoff == report
    assert joined.bim_handoff.mapped_element_count == model_v3.element_count


def test_the_accessible_route_has_two_outcomes_and_not_three(bundle, model_v3) -> None:
    tally = next(t for t in bundle.compliance.tallies if t.source == 'accessible_route')
    if model_v3.accessible_route is not None:
        assert (tally.passed, tally.failed) == (1, 0)
    else:
        assert (tally.passed, tally.failed) == (0, 1)
        assert tally.blockers, 'a stair was built and no reason was recorded'


def test_sheet_references_carry_their_audit_and_refuse_a_malformed_id() -> None:
    index = {'sheets': [
        {'id': 'DWG-PLAN-L00', 'title': 'Floor plan', 'kind': 'plan', 'scale': '1:100',
         'subtitle': 'podium', 'sheet_mm': [691.1, 502.0], 'marks': 449,
         'elements_cut': 72, 'elements_drawn': 568, 'omitted_by_scale': {'seat': 276}},
        {'id': '../../secrets', 'title': 'nope', 'kind': 'plan', 'scale': '1:100'},
    ]}
    sheets = drawing_sheet_refs('building-v3-abc', index)
    assert [sheet.id for sheet in sheets] == ['DWG-PLAN-L00']
    assert sheets[0].url == '/api/models/building-v3-abc/drawings/DWG-PLAN-L00.svg'
    assert sheets[0].omitted_by_scale == {'seat': 276}
    assert drawing_sheet_refs('building-v3-abc', None) == []
    assert render_refs('../escape') == []


def test_run_ids_that_did_not_come_from_this_pipeline_resolve_to_nothing() -> None:
    assert run_path('run-b7ad95fa45a6') is not None
    for bad in ('../../etc/passwd', 'run-../../x', 'run-ZZZZZZZZZZZZ', 'nope'):
        assert run_path(bad) is None
        assert load_run(bad) is None


def test_an_entry_written_by_an_older_schema_is_skipped_not_raised(monkeypatch, tmp_path) -> None:
    from backend.app import run_store

    monkeypatch.setattr(run_store, 'RUN_DIRECTORY', tmp_path)
    # One entry a newer schema can no longer validate, one that is not JSON at all.
    # A library that raises on either is a library nobody can open.
    (tmp_path / 'run-000000000000.json').write_text(
        json.dumps({'run_id': 'run-000000000000'}), encoding='utf-8')
    (tmp_path / 'run-111111111111.json').write_text('{not json', encoding='utf-8')
    assert list_runs() == []
    assert load_run('run-000000000000') is None


def test_artifact_routes_refuse_to_walk_out_of_the_artifact_tree() -> None:
    client = TestClient(app)
    assert client.get('/api/models/..%2F..%2Fetc/drawings/passwd').status_code in (400, 404)
    assert client.get('/api/models/ok/drawings/..%2F..%2Fpasswd').status_code in (400, 404)
    assert client.get('/api/models/building-v3-missing/renders/none.png').status_code == 404


def _finding(rule_id: str, severity: str, measure: float):
    from backend.app.spatial_rules import Finding
    return Finding(rule_id=rule_id, severity=severity, elements=('A', 'B'),
                   measure=measure, unit='of the host',
                   detail=f'{rule_id} at {measure}')


def test_the_spatial_tally_counts_rules_and_names_the_worst_of_each() -> None:
    """The failing branch of the spatial tally, which no compiled model reaches.

    Every massing passes, so the blocker path is only ever exercised here. It is worth
    exercising: it used to call the first finding of a rule its worst one, and the
    findings are in the order the index walked them, not in order of severity.
    """
    from backend.app.spatial_rules import RULES, SpatialReport

    findings = [
        _finding('SP-SUBSYSTEM-OVERLAP', 'violation', 0.08),
        _finding('SP-SUBSYSTEM-OVERLAP', 'violation', 0.41),
        _finding('SP-FALL-GAP', 'warning', 0.2),
    ]
    report = SpatialReport(
        status='failed', findings=findings,
        counts={rule.id: 0 for rule in RULES},
        watches={rule.id: rule.sees for rule in RULES})

    tally = _tally_spatial(report)
    assert tally is not None
    # One entry per rule, in exactly one bucket each.
    assert tally.passed + tally.failed + tally.unevaluated == len(RULES)
    assert tally.failed == 1               # the rule with violations
    assert tally.unevaluated == 1          # the rule with only a warning
    assert len(tally.blockers) == 1
    assert '0.41' in tally.blockers[0], (
        f'the tally named the wrong finding as the worst: {tally.blockers[0]}')
    assert _tally_spatial(None) is None


# ---------------------------------------------------------------------------
# One building per number
# ---------------------------------------------------------------------------

def _v2_checks():
    from backend.app.models import ValidationCheck
    return [
        ValidationCheck(id='V2-A', status='pass', message='held'),
        ValidationCheck(id='V2-B', status='fail', message='did not hold'),
    ]


# Both tests below hand over an identity spelled the way `pipeline.py` spells it -- the
# v2 vocabulary. An identity synthesised from the v3 model under test would pass
# whatever the comparison did, which is how a comparison that never once returned True
# in production sat under a green test.
V2_IDENTITY = 'library/international_style_informed'


def test_checks_from_another_building_stay_out_of_the_totals(model_v3):
    """The v2 chain is typed to one building -- a library in the International
    Style -- while the v3 selection follows the score. The day the score first chose
    a theatre, the status bar summed the theatre's checks with a library's and
    called the total one building's compliance."""
    other = model_v3.model_copy(update={
        'typology': 'theater', 'facade_grammar_id': 'FCD-05-HIGH-TECH'})
    bundle = compile_analysis_bundle(
        other, validation=_v2_checks(), companion_identity=V2_IDENTITY)
    rollup = bundle.compliance
    assert rollup.foreign_tallies, 'the mismatched checks vanished instead of '\
        'being carried beside the totals'
    assert all(tally.building for tally in rollup.foreign_tallies)
    assert not any(tally.source == 'massing_validation' for tally in rollup.tallies)
    own_failed = sum(tally.failed for tally in rollup.tallies)
    assert rollup.failed_total == own_failed, (
        'a failure from another building leaked into this one\'s total')


def test_checks_from_the_same_building_join_the_totals(model_v3):
    """One grammar, two spellings, and the roll-up has to see through the difference.

    `international_style_informed` and `FCD-01-INTERNATIONAL-STYLE` cite the same style
    guide. Compared literally they never match, so the v2 checks were carried as
    another building's on every run this project has ever compiled -- including the
    ones where both halves genuinely built a library in the International Style.
    """
    twin = model_v3.model_copy(update={
        'typology': 'library', 'facade_grammar_id': 'FCD-01-INTERNATIONAL-STYLE'})
    bundle = compile_analysis_bundle(
        twin, validation=_v2_checks(), companion_identity=V2_IDENTITY)
    rollup = bundle.compliance
    assert not rollup.foreign_tallies
    assert any(tally.source == 'massing_validation' for tally in rollup.tallies)


# ---------------------------------------------------------------------------
# The identity a run is stored under
# ---------------------------------------------------------------------------

def test_the_model_identity_hears_every_input(features, score, monkeypatch):
    """The id was the audio hash alone, which stopped being an identity the day
    anything else began to shape the building: a re-run after a compiler change
    replaced the GLB an older stored run still pointed at, and one MP3 could not
    keep two pinned variants side by side."""
    import backend.app.compiler_v3 as c3
    compiler_version = c3.COMPILER_VERSION

    free = compile_building_model_v3(features, score)
    again = compile_building_model_v3(features, score)
    assert free.model_id == again.model_id, 'the identity is not deterministic'
    assert free.model_dump_json() == again.model_dump_json(), (
        'the identity stayed equal while the portable model content changed')

    pinned = compile_building_model_v3(features, score, massing_id='MAS-SLAB')
    assert pinned.model_id != free.model_id, 'a pin left the identity unchanged'

    monkeypatch.setattr(c3, 'COMPILER_VERSION', '0.0.0-test')
    bumped = compile_building_model_v3(features, score)
    assert bumped.model_id != free.model_id, (
        'a compiler version bump left the identity unchanged, so a new compiler '
        'would overwrite the artifacts of runs made by the old one')

    monkeypatch.setattr(c3, 'COMPILER_VERSION', compiler_version)
    monkeypatch.setattr(c3, 'compiler_source_fingerprint', lambda: 'changed-source')
    changed_source = compile_building_model_v3(features, score)
    assert changed_source.model_id != free.model_id, (
        'a source edit left the identity unchanged before the declared version bump')


# ---------------------------------------------------------------------------
# Derivation chains
# ---------------------------------------------------------------------------

def test_every_element_family_carries_its_reasoning(model_v3, features, score):
    """A chain per family, keyed so the workbench can look one up.

    `derivation.py` was written to answer "how did this come to be" and then went two
    releases without a caller -- 408 lines nothing imported outside its own test. The
    bundle publishes it now, so the reasoning travels with every run the API stores and
    every frozen demo, rather than existing only as a function somebody could call.
    """
    bundle = compile_analysis_bundle(model_v3, features=features, score=score)
    assert bundle.derivation, 'the run published no reasoning at all'
    assert set(bundle.derivation) == {g.group_id for g in bundle.element_groups}, (
        'a family in the model has no chain, or a chain names no family')

    # The sample is stated, not implied: each chain says which instance it was read off.
    instances = {element.id for group in model_v3.element_groups
                 for element in group.expand()}
    assert set(bundle.derivation_element_ids) == set(bundle.derivation)
    assert set(bundle.derivation_element_ids.values()) <= instances

    for chain in bundle.derivation.values():
        assert chain.steps, f'{chain.element_id} has a chain with no steps'


def test_a_chain_reaches_the_recording_only_when_the_run_hands_over_the_music(
        model_v3, features, score):
    """Handing over the features is what lets a chain reach back past the datums.

    Without them the chains still assemble -- the datums are what an element is a
    function of either way -- but none of them can honestly claim a musical cause, and
    the pipeline forgetting to pass them would be invisible without this.
    """
    with_music = compile_analysis_bundle(model_v3, features=features, score=score)
    without = compile_analysis_bundle(model_v3)

    reached = sum(1 for chain in with_music.derivation.values() if chain.reaches_audio)
    assert reached > 0, 'no family reached the recording even with the music supplied'
    assert all(not chain.reaches_audio for chain in without.derivation.values()), (
        'a chain claimed a musical cause on a run that was handed no music')

    # And the ones that do not reach it say so rather than inventing a cause -- a fire
    # stair is required by code whatever the piece sounds like.
    assert reached < len(with_music.derivation), (
        'every family claims a musical driver, which no building has')
