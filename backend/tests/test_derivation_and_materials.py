"""What an element can say about itself: where it came from, and what it is made of.

Both were already implicit. Every element carried the datums it read, the lattice it
sits on, what it bears on and the clause that sized it -- and a palette key. What was
missing in each case was the thing that makes the record usable: an *order* for the
first, and a *definition* for the second.

The chain matters because this project's whole claim is traceability from a recording
to a building. A list of facts does not carry that claim; a sequence does, and it lets
a reader find the step they disagree with -- which is almost always the mapping rule,
where the range and the direction are the design decision and the music only chooses a
position within them.

The materials matter because a key with no definition behind it is a name. Two
renderers holding their own tables were free to disagree about what `steel_white` meant
and neither could be wrong, there being nothing to be wrong against.
"""

import json

import pytest

from backend.app.compiler_v3 import compile_building_model_v3
from backend.app.derivation import build_chains
from backend.app.materials import MATERIALS, MaterialSpec
from backend.app.models import ArchitecturalScore, AudioFeatures
from backend.app.tectonics import FRAME_TECTONICS

from backend.tests.test_differentiation import DEMO, V2_DEMO


CASES = [
    ('library', 'MAS-SLAB'), ('museum', 'MAS-COURTYARD'),
    ('theater', 'MAS-BAR-PODIUM'), ('library', 'MAS-TOWER'),
    ('library', 'MAS-ZIGGURAT'), ('theater', 'MAS-SPLIT'),
    ('pavilion', 'MAS-PAVILION'),
]
MASSINGS = [massing for _typology, massing in CASES]

# The musical half of the chain, in the order it has to appear.
MUSIC_ORDER = ['feature', 'dimension', 'rule', 'datum']

# Members whose section was chosen by a material's own capacity equations.
FRAME_KINDS = {
    'column', 'piloti_column', 'primary_beam', 'secondary_joist', 'heavy_joist',
    'brace', 'knee_brace', 'outrigger_strut',
}


@pytest.fixture(scope='module')
def score():
    return ArchitecturalScore.model_validate(
        json.loads((DEMO / 'architectural_score.json').read_text(encoding='utf-8')))


@pytest.fixture(scope='module')
def features():
    return AudioFeatures.model_validate(
        json.loads((V2_DEMO / 'music_features.json').read_text(encoding='utf-8')))


@pytest.fixture(scope='module')
def models(score, features):
    return {massing: compile_building_model_v3(features, score,
                                               massing_id=massing, typology=typology)
            for typology, massing in CASES}


# --- the chain --------------------------------------------------------------------

@pytest.mark.parametrize('massing', MASSINGS)
def test_every_element_can_say_where_it_came_from(models, massing, features, score):
    model = models[massing]
    chains = build_chains(model, features=features, score=score)
    ids = {instance.id for group in model.element_groups
           for instance in group.instances}
    assert set(chains) == ids, sorted(ids - set(chains))[:5]
    for chain in chains.values():
        assert chain.steps, chain.element_id
        assert chain.reaches_solid or chain.kind in ('program_zone',), chain.element_id


@pytest.mark.parametrize('massing', MASSINGS)
def test_a_chain_that_reaches_the_recording_reaches_it_in_order(
        models, massing, features, score):
    """feature, then dimension, then rule, then datum -- and never backwards.

    Out of order the chain still contains every fact and stops being an argument: a
    datum quoted before the measurement that produced it reads as a coincidence.
    """
    chains = build_chains(models[massing], features=features, score=score)
    checked = 0
    for chain in chains.values():
        if not chain.reaches_audio:
            continue
        checked += 1
        musical = [step.stage for step in chain.steps if step.stage in MUSIC_ORDER]
        assert musical[0] == 'feature', (chain.element_id, musical[:4])
        # Within each pass the order holds; a second driver starts a new pass.
        rank = [MUSIC_ORDER.index(stage) for stage in musical]
        for previous, current in zip(rank, rank[1:]):
            assert current >= previous or current == 0, (chain.element_id, musical)
    assert checked > 100, f'{massing}: only {checked} chains reach the recording'


@pytest.mark.parametrize('massing', MASSINGS)
def test_the_chain_opens_on_the_music_where_there_is_any(models, massing,
                                                         features, score):
    """A chain that opens on a tectonic constant buries what it exists to show."""
    chains = build_chains(models[massing], features=features, score=score)
    for chain in chains.values():
        if chain.reaches_audio:
            assert chain.steps[0].stage == 'feature', (
                chain.element_id, chain.steps[0].stage)


@pytest.mark.parametrize('massing', MASSINGS)
def test_an_element_the_music_did_not_drive_says_so(models, massing, features, score):
    """A fire stair is required by code whatever the piece sounds like. Inventing a
    musical cause for it would be worse than having none."""
    chains = build_chains(models[massing], features=features, score=score)
    silent = [chain for chain in chains.values() if not chain.reaches_audio]
    assert silent, f'{massing}: every element claims a musical cause, which is unlikely'
    for chain in silent:
        assert not any(step.stage in ('feature', 'dimension', 'rule')
                       for step in chain.steps), chain.element_id


def test_the_chain_names_the_rule_as_the_place_to_argue(models, features, score):
    """The mapping rule carries its range and direction, because that pair is the
    design decision -- the music only chooses a position inside it."""
    chains = build_chains(models['MAS-SLAB'], features=features, score=score)
    rules = [step for chain in chains.values() for step in chain.steps
             if step.stage == 'rule']
    assert rules
    for step in rules[:40]:
        assert '->' in step.value and ('into [' in step.value)
        assert 'priority' in step.source


# --- the materials ----------------------------------------------------------------

def test_every_material_defines_what_it_is_and_what_it_looks_like():
    for key, spec in MATERIALS.items():
        assert isinstance(spec, MaterialSpec)
        assert spec.base_color.startswith('#') and len(spec.base_color) == 7, key
        red, green, blue, alpha = spec.rgba
        assert all(0.0 <= channel <= 1.0 for channel in (red, green, blue)), key
        assert alpha == 1.0
        assert spec.finish and spec.reason, key


@pytest.mark.parametrize('massing', MASSINGS)
def test_the_model_carries_a_definition_for_every_key_it_uses(models, massing):
    """A key the model uses and does not define is a name a renderer has to guess at."""
    model = models[massing]
    used = {group.material_profile for group in model.element_groups}
    assert used <= set(model.materials), sorted(used - set(model.materials))


@pytest.mark.parametrize('massing', MASSINGS)
def test_the_frame_looks_like_the_material_it_was_sized_in(models, massing):
    """A member checked to NDS timber capacities that renders as painted steel tells a
    viewer the wrong thing about the building, and no care in the palette catches it.

    One steel raker in a mass-timber frame is how this was found: hard-coded, not
    decided.
    """
    model = models[massing]
    frame = next((tectonic for tectonic in FRAME_TECTONICS.values()
                  if model.tectonic_system.endswith(
                      tectonic.id.replace('FRM-', ''))), None)
    if frame is None:
        pytest.skip(f'{massing}: {model.tectonic_system} is not a frame tectonic')
    expected = MATERIALS[frame.column_material].family

    families = set()
    for group in model.element_groups:
        if group.kind not in FRAME_KINDS:
            continue
        spec = model.materials.get(group.material_profile)
        assert spec is not None, (massing, group.material_profile)
        families.add(spec.family)
    assert families == {expected}, (massing, sorted(families), expected)


def test_a_glazing_material_actually_transmits():
    """Transmission is what makes glass glass rather than a pale blue panel."""
    assert MATERIALS['glass'].transmission > 0.5
    opaque = [spec for key, spec in MATERIALS.items()
              if spec.family != 'glass']
    assert all(spec.transmission == 0.0 for spec in opaque)


def test_the_program_overlay_is_not_pretending_to_be_a_material():
    """It is a diagram drawn in the same scene. A renderer that treats it as a surface
    will light it like one."""
    for key, spec in MATERIALS.items():
        if key.startswith('prog_'):
            assert spec.family == 'diagram', key
            assert not spec.is_structural, key
