"""Library transfer through the shared bounded PV authoring path, not native QA."""
import pytest
from shapely.geometry import box, Polygon
from shapely.ops import unary_union

from backend.app.briefs import BRIEFS
from backend.app.legacy_program_layout import LegacyLayoutControls, LayoutRejected, _registered_capacity_size
from backend.app.project_brief import ProjectBrief
from backend.app.program_volumes import organize_program_volumes
from backend.app.program_massing import prepare_massing
from backend.tests.test_legacy_program_layout import _brief, _score


def library_brief():
    sizes = {'SP-ADULT':48, 'SP-LOBBY':22, 'SP-STACKS':30,
             'SP-CHILDREN':28, 'SP-SEMINAR':24, 'SP-STAFF':12}
    spaces = []
    for template in BRIEFS['library']:
        if template.id not in sizes:
            continue
        raw = template.model_dump(mode='json')
        raw.update(area_m2=sizes[template.id], min_dimension_m=3,
                   adjacency=[s for s in template.adjacency if s in sizes],
                   reason='Compact library test requirement; not an audio-generated brief')
        spaces.append(raw)
    raw = _brief().model_dump(mode='json')
    raw.update(typology='library', spaces=spaces, brief_id='compact-library-test')
    return ProjectBrief.model_validate(raw)


def test_library_preserves_owners_clearance_and_exact_level_unions():
    brief = library_brief()
    model = organize_program_volumes(_score(), 'library', project_brief=brief,
        legacy_controls=LegacyLayoutControls(iterations=120, layout_max_nodes=128))
    assert model.typology == 'library'
    owners = [s for v in model.volumes for s in v.space_ids]
    assert set(owners) == {s.id for s in brief.resolved_spaces()}
    assert len(owners) == len(set(owners))
    assert not {'SP-AUDITORIUM','SP-STAGE'} & set(owners)
    reading = next(v for v in model.volumes if 'SP-ADULT' in v.space_ids)
    clearance = next(v for v in model.volumes if 'READING-CLEARANCE' in v.id)
    assert reading.role == 'archetype'
    assert clearance.level_index == reading.level_index + 1
    assert model.rect_of(clearance) == model.rect_of(reading)
    assert not clearance.space_ids
    for volume in model.volumes:
        rect = box(*model.rect_of(volume))
        assert brief.massing_limit_shape.buffer(1e-4).covers(rect)
        if volume.level_index == clearance.level_index and volume.id != clearance.id:
            assert rect.intersection(box(*model.rect_of(clearance))).area < 1e-6
    for level in model.level_unions:
        actual = unary_union([box(*model.rect_of(v)) for v in model.volumes
                              if v.level_index == level.level_index])
        assert actual.symmetric_difference(Polygon(level.boundary, holes=level.voids)).area < 1e-6
    assert model.world_xy_grid.origin == (0, 0)
    prepared = prepare_massing(model.to_program_massing(), score=_score())
    assert prepared.allocation.fits
    assert not prepared.allocation.unplaced
    assert not prepared.allocation.public_circulation.unresolved


def test_library_rejects_theater_shared_foyer_controls():
    with pytest.raises(LayoutRejected, match='Theater root/shared-foyer'):
        organize_program_volumes(_score(), 'library', project_brief=library_brief(),
            legacy_controls=LegacyLayoutControls(foyer_layout='hall_front_shared'))


@pytest.mark.parametrize('origin', [(8.436,11.9496), (0.000049,0.000051), (-4.3,-2.7)])
def test_registered_room_dimensions_do_not_lose_required_capacity(origin):
    width = 8.097
    w,d = _registered_capacity_size(width,48 / width)
    a,b = (round(v,4) for v in origin)
    c,e = round(origin[0]+w,4),round(origin[1]+d,4)
    assert (c-a)*(e-b) >= 48
    assert (c-a)*(e-b) - 48 < 0.002
