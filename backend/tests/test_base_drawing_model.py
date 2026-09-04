"""What the model must carry for a cut plane to produce a base drawing.

These are not drawing tests -- `test_drawings.py` covers the sheet. They lock the
things a plan or a section needs to *find* in the model, each of which was missing and
each of which was found by looking at a drawing rather than at a number.

The recurring shape: a quantity was in the model as a figure and not as a thing. The
tectonic declared a 450 mm bearing wall that no emitter read, so the wall went into
every drawing as a line with no width. The partitions declared a 150 mm head clearance
with nothing at the top of it, so they ended in mid-air. The site declared a ground
plane 400 mm below the top of every footing, so the building stood on its foundations
instead of in them. All three passed every count in the pipeline.
"""

import json

import pytest

from backend.app.compiler_v3 import compile_building_model_v3
from backend.app.models import ArchitecturalScore, AudioFeatures
from backend.app.tectonics import ENVELOPE_TECTONICS

from backend.tests.test_differentiation import DEMO, V2_DEMO


CASES = [
    ('library', 'MAS-SLAB'), ('museum', 'MAS-COURTYARD'),
    ('theater', 'MAS-BAR-PODIUM'), ('library', 'MAS-TOWER'),
    ('library', 'MAS-ZIGGURAT'), ('theater', 'MAS-SPLIT'),
    ('pavilion', 'MAS-PAVILION'),
]


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


def _instances(model, kind):
    return [instance for group in model.element_groups if group.kind == kind
            for instance in group.instances]


def _groups(model, kind):
    return [group for group in model.element_groups if group.kind == kind]


# --- a sheet element has a body ---------------------------------------------------

def test_every_tectonic_states_a_construction_depth():
    """A wall assembly, a cladding panel and a glazing unit all have one."""
    for tectonic in ENVELOPE_TECTONICS.values():
        assert tectonic.cladding_depth_m > 0.0, tectonic.id
        assert tectonic.glazing_depth_m > 0.0, tectonic.id
        if tectonic.opening_logic == 'subtract':
            # A wall you cut a hole in is a wall; it has a thickness to show at the
            # reveal, and the reveal is the whole point of the family.
            assert tectonic.wall_thickness_m > 0.2, tectonic.id


@pytest.mark.parametrize('massing', [massing for _typology, massing in CASES])
def test_no_panel_is_a_surface_with_no_thickness(models, massing):
    """A quad cannot be cut. Six hundred and fifty-six of them had no depth at all, so
    the exterior wall could not produce a poche band however the weights were set."""
    model = models[massing]
    for group in model.element_groups:
        if getattr(group.instances[0].geometry, 'type', '') != 'quad':
            continue
        assert group.thickness_m, f'{massing}: {group.kind} has no construction depth'
        assert 0.01 < group.thickness_m < 1.0, (massing, group.kind, group.thickness_m)


# --- a storey has a build-up ------------------------------------------------------

@pytest.mark.parametrize('massing', [massing for _typology, massing in CASES])
def test_every_occupied_level_has_a_ceiling(models, massing):
    model = models[massing]
    occupied = {level.id for level in model.lattice.levels
                if level.kind == 'occupied'}
    ceilings = {instance.level_id for instance in _instances(model, 'ceiling')}
    assert ceilings == occupied, (massing, sorted(occupied - ceilings))


@pytest.mark.parametrize('massing', [massing for _typology, massing in CASES])
def test_a_partition_meets_the_ceiling_rather_than_stopping_below_it(models, massing):
    """The head clearance was a number with nothing at the top of it.

    Partitions stopped 150 mm short of the structure and there was no ceiling, so in
    section every wall in the building ended in mid-air. The defect is stopping
    *short*: a wall may also run past the ceiling plane, because a carved room's
    enclosure (decision 0016) rises to its own claimed clear height and the
    suspended ceiling abuts it at the hole cut for the carve. Most walls still stop
    inside the ceiling band, and the count of those is asserted so a change that
    made every wall tall would still be noticed.
    """
    model = models[massing]
    ceilings = {instance.level_id: instance.geometry
                for instance in _instances(model, 'ceiling')}
    checked = 0
    flush = 0
    for instance in _instances(model, 'partition'):
        ceiling = ceilings.get(instance.level_id)
        if ceiling is None:
            continue
        top = instance.geometry.center.z + instance.geometry.size.z / 2.0
        assert top >= ceiling.z_base - 0.001, (
            f'{massing}: {instance.id} tops at {top:.3f}, below the ceiling at '
            f'{ceiling.z_base:.3f}')
        if top <= ceiling.z_top + 0.001:
            flush += 1
        checked += 1
    assert checked > 0, f'{massing}: no partition to check'
    assert flush >= checked * 0.5, (
        f'{massing}: only {flush} of {checked} partitions stop at the ceiling; '
        f'the rest overshoot, which is no longer an enclosure detail, it is the '
        f'head clearance failing the other way')


@pytest.mark.parametrize('massing', [massing for _typology, massing in CASES])
def test_a_ceiling_hangs_from_above_and_never_bears_on_the_floor(models, massing):
    """`floor_host` would return the slab underneath -- the one relation a suspended
    ceiling definitely does not have."""
    model = models[massing]
    heights = {instance.id: instance.geometry
               for instance in _instances(model, 'floor_slab')}
    for group in model.dependency_graph.relation_groups:
        for relation in group.expand():
            if not relation.dependent_id.startswith('ARC-CLG-'):
                continue
            assert relation.relation == 'hangs_from', relation.dependent_id
            slab = heights.get(relation.host_id)
            assert slab is not None, relation.host_id
            ceiling = next(instance for instance in _instances(model, 'ceiling')
                           if instance.id == relation.dependent_id)
            top = ceiling.geometry.z_top
            assert slab.z_base >= top - 0.01, (
                f'{massing}: {relation.dependent_id} hangs from a slab below it')


# --- the building can be entered and is founded in ground -------------------------

@pytest.mark.parametrize('massing', [massing for _typology, massing in CASES])
def test_the_envelope_has_a_way_through_it(models, massing):
    """Twenty-six doors and every one between two rooms: the entry canopy stood
    outside an unbroken wall and no plan could show how anyone gets in."""
    model = models[massing]
    leaves = _instances(model, 'entrance_door')
    assert leaves, f'{massing}: the envelope has no entrance'
    lowest = min(level.z for level in model.lattice.levels if level.kind == 'occupied')
    for leaf in leaves:
        base = min(corner.z for corner in leaf.geometry.corners)
        assert abs(base - lowest) < 0.6, (
            f'{massing}: {leaf.id} is not at the entrance level')


@pytest.mark.parametrize('massing', [massing for _typology, massing in CASES])
def test_the_entrance_introduces_no_material_the_family_does_not_use(models, massing):
    """The Deconstructivist guide caps the visible material count at three, and a
    hard-coded glass leaf with a trim head made four. The gate caught it."""
    model = models[massing]
    entrance = {group.material_profile for group in model.element_groups
                if group.kind in ('entrance_door', 'entrance_head')}
    envelope = {group.material_profile for group in model.element_groups
                if group.semantic_layer == 'envelope'
                and group.kind not in ('entrance_door', 'entrance_head')}
    assert entrance <= envelope, (massing, sorted(entrance - envelope))


@pytest.mark.parametrize('massing', [massing for _typology, massing in CASES])
def test_the_footings_are_in_the_ground_and_the_podium_sits_on_it(models, massing):
    """Grade used to be 400 mm below the top of every footing and 50 mm below the
    podium, so the building floated above its own foundations."""
    model = models[massing]
    ground = _instances(model, 'site_ground')
    assert ground, f'{massing}: no ground'
    box = ground[0].geometry
    grade = box.center.z + box.size.z / 2.0
    base = box.center.z - box.size.z / 2.0

    podium = _instances(model, 'podium_slab')
    if podium:
        assert abs(podium[0].geometry.z_base - grade) < 0.01, (
            f'{massing}: podium underside {podium[0].geometry.z_base:.3f} does not '
            f'meet grade {grade:.3f}')

    for footing in _instances(model, 'footing'):
        bottom = footing.geometry.center.z - footing.geometry.size.z / 2.0
        assert bottom > base, f'{massing}: {footing.id} is below the drawn earth'
        assert bottom < grade, f'{massing}: {footing.id} does not reach below grade'
