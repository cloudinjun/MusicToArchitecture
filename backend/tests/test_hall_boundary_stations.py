"""A small hall must not borrow supports outside its volume from a larger grid."""
from types import SimpleNamespace as NS

import pytest
from shapely.geometry import box

from backend.app.geometry import v2
from backend.app.hall_enclosure import prepare_hall
from backend.app.hall_stations import HallSupportGrid, hall_axes, retained_edge_stations, volume_section
from backend.app.loads import OCCUPANCY_LIVE
from backend.app.program_volume_contracts import ProgramVolumeRegion
from backend.app.transfer_structure import _pier_inside_volume, edge_column_id


def small_hall():
    extent = (1.4, 1.4, 23.6, 18.6)
    plate = [v2(*p) for p in list(box(*extent).exterior.coords)[:-1]]
    levels = [NS(index=i,id=f'L{i:02d}',z=.3+(i-1)*4.1 if i else 0.,
                 plate=plate,voids=[],kind='occupied' if i else 'podium') for i in range(5)]
    # Cap floor retains only a strip; the hall roof must cover the remainder.
    levels[-1].plate = [v2(*p) for p in list(box(1.4,10,23.6,18.6).exterior.coords)[:-1]]
    region = ProgramVolumeRegion(id='HALL',level_id='L01',category='public',
        role='sectional_clearance',grid_rect=(0,0,1,1),z_base=.3,z_top=levels[-1].z)
    lattice = NS(levels=levels,occupied=levels[1:],
        x_lines=[0.,6.7,13.4,20.1,26.8],y_lines=[0.,7.3,14.6,21.9],
        program_volume_x_lines=[1.4,23.6],program_volume_y_lines=[1.4,18.6],
        program_volume_regions=[region])
    carve = NS(house=(6.9,1.4,17.6,8.9),stage=(17.6,1.4,21.6,8.9),
               clear_house_m=7.,clear_stage_m=8.)
    b = NS(lattice=lattice,datums=NS(value=lambda k:{'slab_thickness_m':.3,'joist_spacing_m':1.8}[k]))
    return b, carve


def test_boundary_registry_preserves_world_pitch_and_owns_roof_reaction_coordinates():
    b, carve = small_hall()
    original = (list(b.lattice.x_lines),list(b.lattice.y_lines))
    geometry = prepare_hall(b,OCCUPANCY_LIVE['stage'],carve)
    grid = b.lattice.hall_support_grid
    assert (b.lattice.x_lines,b.lattice.y_lines) == original
    assert HallSupportGrid.model_validate_json(grid.model_dump_json()) == grid
    assert grid.source_volume_ids == ['HALL']
    assert grid.y[geometry.y_indices[0]] > carve.house[1]
    assert grid.y[geometry.y_indices[-1]] < carve.house[3]
    assert not b.hall_enclosure.findings
    assert geometry.missing.difference(volume_section(b.lattice,geometry.roof_bottom_z)).area < 1e-9
    live = OCCUPANCY_LIVE['roof_ordinary'].live_kpa
    total = live*geometry.missing.area
    assert sum(v[1] for v in b.hall_reactions.values()) == pytest.approx(total)
    for axis,lines in enumerate(hall_axes(b)):
        measured = sum(lines[key[axis]]*value[1] for key,value in b.hall_reactions.items())
        center = geometry.missing.centroid.x if axis==0 else geometry.missing.centroid.y
        assert measured == pytest.approx(total*center, abs=1e-8)


def test_pier_checks_its_whole_section_not_just_an_inboard_center():
    b,carve = small_hall()
    prepare_hall(b,OCCUPANCY_LIVE['stage'],carve)
    lower,upper = b.lattice.levels[1:3]
    check = NS(section_id='HSS16X16X5/8')
    grid = b.lattice.hall_support_grid
    x,y = grid.x[grid.indices('x')[0]],grid.y[grid.indices('y')[0]]
    assert _pier_inside_volume(b.lattice,x,y,lower,upper,check)
    assert not _pier_inside_volume(b.lattice,x,1.41,lower,upper,check)


def test_retained_edge_endpoints_follow_upper_retreat_without_rephasing_hall_grid():
    b,carve = small_hall()
    prepare_hall(b,OCCUPANCY_LIVE['stage'],carve)
    before = b.lattice.hall_support_grid.model_dump_json()
    b.lattice.program_volume_y_lines = [1.4,5.,18.6]
    b.lattice.program_volume_regions = [
        ProgramVolumeRegion(id='LOW',level_id='L01',category='public',role='program',
            grid_rect=(0,0,1,2),z_base=.3,z_top=b.lattice.levels[2].z),
        ProgramVolumeRegion(id='UP',level_id='L02',category='public',role='program',
            grid_rect=(0,1,1,2),z_base=b.lattice.levels[2].z,z_top=b.lattice.levels[4].z)]
    stations = retained_edge_stations(b.lattice,6.,1.6,8.7,4,.3)
    assert min(stations.values()) == pytest.approx(5.15)
    assert stations[1] == 7.3  # original regular station survives
    assert b.lattice.hall_support_grid.model_dump_json() == before


def test_retained_edge_reuses_real_world_station_identity_only_at_matching_coordinates():
    b,_ = small_hall()
    edge = NS(regular_x_index=1,x_bay_index=1,y_coordinates={1:7.3,4:5.15})
    assert edge_column_id(edge,1,1,b.lattice) == 'STR-COL-X01-Y01-L01'
    assert edge_column_id(edge,4,1,b.lattice) == 'STR-TRF-EDGE-X01-Y04-L01'
    edge.y_coordinates[1] = 7.4
    assert edge_column_id(edge,1,1,b.lattice) == 'STR-TRF-EDGE-X01-Y01-L01'
