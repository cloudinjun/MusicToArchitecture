"""Named foyer/public-floor sharing keeps cores, holes and other rooms exclusive."""
from types import SimpleNamespace
import pytest
from shapely.geometry import box

from backend.app.program import allocate_program, PublicCirculationPlanner
from backend.app.program_volume_contracts import ProgramVolumeRegion
from backend.tests.test_exact_owner_allocation import _lattice, _brief, _empty_datums, _ring


def _case(shared=True, obstruction=None):
    owner = (.3,.7,.3+22/3,3.7)
    grid = _lattice(owner=owner)
    grid.program_volume_x_lines = [0.,owner[0],owner[2],8.]
    grid.program_volume_y_lines = [.7,1.5,3.,3.7]
    carrier = (0.,1.5,8.,3.)
    grid.level(1).reserved = [carrier]
    grid.program_volume_regions = [ProgramVolumeRegion(id='FOYER',level_id='L01',
        category='circulation',role='program',space_ids=['SP-OWNER'],grid_rect=(1,0,2,3),
        z_base=0.,z_top=4.,shared_route_volume_ids=['ROUTE'] if shared else []),
        ProgramVolumeRegion(id='ROUTE',level_id='L01',category='circulation',
            role='connector',grid_rect=(0,1,3,2),z_base=0.,z_top=4.)]
    core = (2.,2.,3.,3.)
    if obstruction == 'void':
        grid.level(1).voids = [_ring(box(*core))]
    public = PublicCirculationPlanner(grid,obstacles={1:[box(*core)] if obstruction=='core' else []},
        terminals={1:[('STAIR-A',[(7.,5.)])]},protected={1:{'SP-OWNER':box(*owner)}})
    brief = (_brief(22.)[0].model_copy(update={'category':'circulation','min_dimension_m':3.}),)
    result = allocate_program(grid,_empty_datums(),brief,
        reserved=[core] if obstruction=='core' else (),public_circulation=public)
    return result,public,owner,carrier


def test_exact_shared_foyer_retains_area_and_reaches_a_real_stair():
    allocation,public,owner,carrier = _case()
    assert allocation.fits
    zone = allocation.zones[0]
    assert (zone.x0,zone.y0,zone.x1,zone.y1) == pytest.approx(owner)
    assert zone.area_delivered_m2 == 22.
    assert box(*owner).intersection(box(*carrier)).area > 0
    path = next(p for p in public.plan.paths if p.target_id=='SP-OWNER')
    assert path.points[-1] == (7.,5.)
    # It stays public floor after the room claim; subsequent routes can cross it.
    assert not public.rooms[1]
    assert public.room_connection(SimpleNamespace(space_id='OTHER',level_index=1,
        x0=.1,y0=4.5,x1=2.,y1=5.9)) is not None


@pytest.mark.parametrize('obstruction',['core','void'])
def test_shared_foyer_cannot_waive_core_or_void(obstruction):
    allocation,*_ = _case(obstruction=obstruction)
    assert not allocation.fits
    assert not allocation.zones


def test_circulation_category_without_named_sharing_keeps_reservations():
    allocation,*_ = _case(shared=False)
    assert not allocation.fits
    assert not allocation.zones
