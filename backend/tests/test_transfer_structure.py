"""Mechanics and support-topology counterexamples for theatre transfers."""
from types import SimpleNamespace as NS

import numpy as np
import pytest

from backend.app.geometry import v2
from backend.app.registry import catalogue
from backend.app.transfer_structure import (
    TransferFrame, TransferLoad, analyse_transfer, reserve_transfer_zone,
    solve_plane_truss, truss_topology,
    retained_edge_segments,
)


def test_symmetric_point_load_has_exact_reactions_and_axial_equilibrium():
    nodes, members = truss_topology([0.,5.,10.],0.,-2.)
    loads = np.zeros((6,2)); loads[1,1] = -100.
    forces, displacement, reactions, error = solve_plane_truss(
        nodes,[(a,b) for a,b,_ in members],[1000.]*len(members),loads)
    assert reactions[0,1] == pytest.approx(50.)
    assert reactions[2,1] == pytest.approx(50.)
    assert error < 1e-8
    assert displacement[1,1] < 0
    top = [forces[i] for i,m in enumerate(members) if m[2]=='top_chord']
    assert top == pytest.approx([-125.,-125.])
    assert forces[[i for i,m in enumerate(members) if m==(1,4,'vertical')][0]] == pytest.approx(-100.)


def test_missing_diagonal_is_a_mechanism_and_never_reports_a_solution():
    nodes, members = truss_topology([0.,5.,10.],0.,-2.)
    members = [m for m in members if m!=(0,4,'diagonal')]
    with pytest.raises(ValueError,match='mechanism'):
        solve_plane_truss(nodes,[(a,b) for a,b,_ in members],[1000.]*len(members),np.zeros((6,2)))


def test_catalogue_failure_keeps_every_unselected_member_identifiable():
    frame = TransferFrame(id='TRANSFER',x_index=1,x=5.,level_index=3,level_id='L03',
        y_indices=[0,1,2],span_m=10.,top_z=8.,bottom_z=6.,clear_top_z=5.,
        node_loads=[TransferLoad(node=i,y=y,dead_kn=1e6 if i==1 else 0.,live_kn=0.,roof_live_kn=0.)
                    for i,y in enumerate([0.,5.,10.])])
    analyse_transfer(frame,catalogue('steel_hss_square'))
    assert frame.status == 'failed' and not frame.activated
    assert any(not member.selected and member.section_id is None for member in frame.members)
    assert all(member.analysis_section_id for member in frame.members)
    assert any('No catalogue' in finding for finding in frame.findings)


def test_selected_member_self_weight_reaches_the_actual_support_reactions():
    frame = TransferFrame(id='TRANSFER',x_index=1,x=5.,level_index=3,level_id='L03',
        y_indices=[0,1,2],span_m=10.,top_z=8.,bottom_z=6.,clear_top_z=5.,
        node_loads=[TransferLoad(node=i,y=y,dead_kn=100. if i==1 else 0.,
                    live_kn=40. if i==1 else 0.,roof_live_kn=20. if i==1 else 0.)
                    for i,y in enumerate([0.,5.,10.])])
    sections = catalogue('steel_hss_square')
    analyse_transfer(frame,sections)
    assert frame.status=='review_required'
    by_id = {section.id:section for section in sections}
    self_weight = sum(by_id[m.section_id].self_weight_kn_m*m.length_m for m in frame.members)
    assert sum(frame.reactions_kn['D']) == pytest.approx(100.+self_weight)
    assert sum(frame.reactions_kn['L']) == pytest.approx(40.)
    assert sum(frame.reactions_kn['Lr']) == pytest.approx(20.)
    assert all(set(m.axial_kn)=={'1.4D','1.2D+1.6L+0.5Lr','1.2D+1.0L+1.6Lr'} for m in frame.members)


@pytest.mark.parametrize('depth, load, expected', [
    (.5, 40., 'review_required'), (.1, 1., 'failed')])
def test_stiffness_selection_resolves_actual_products_or_reports_catalogue_ceiling(depth, load, expected):
    frame = TransferFrame(id='STIFF', x_index=1, x=5., level_index=3, level_id='L03',
        y_indices=[0, 1, 2], span_m=10., top_z=8., bottom_z=8.-depth, clear_top_z=7.,
        node_loads=[TransferLoad(node=i, y=y, dead_kn=load if i == 1 else 0.,
                                live_kn=load if i == 1 else 0., roof_live_kn=0.)
                    for i, y in enumerate([0., 5., 10.])])
    sections = catalogue('steel_hss_square')
    analyse_transfer(frame, sections)
    assert frame.status == expected
    assert all(m.selected for m in frame.members)  # Axial strength alone is insufficient.
    if expected == 'failed':
        assert any('deflection' in finding for finding in frame.findings)
        assert frame.total_deflection_mm > frame.span_m * 1000 / 240
    else:
        assert frame.total_deflection_mm <= frame.span_m * 1000 / 240
        assert frame.live_deflection_mm <= frame.span_m * 1000 / 360
    by_id = {s.id: s for s in sections}
    products = [by_id[m.section_id] for m in frame.members]
    loads = np.zeros((len(frame.nodes), 2))
    loads[1, 1] = -2 * load
    for member, product in zip(frame.members, products):
        loads[[member.node_a, member.node_b], 1] -= product.self_weight_kn_m * member.length_m / 2
    _, displacement, reactions, _ = solve_plane_truss(frame.nodes,
        [(m.node_a, m.node_b) for m in frame.members], [s.area_mm2 for s in products], loads)
    assert np.max(np.abs(displacement[:, 1])) * 1000 == pytest.approx(frame.total_deflection_mm)
    assert sum(reactions[:, 1]) == pytest.approx(
        sum(sum(frame.reactions_kn[case]) for case in ('D', 'L', 'Lr')))


def test_reservation_uses_registered_level_and_does_not_mutate_voids():
    plate = [v2(0,0),v2(20,0),v2(20,20),v2(0,20)]
    levels = [NS(index=i,id=f'L{i:02d}',z=z,plate=plate,voids=[])
              for i,z in enumerate([0.,4.,8.,12.,16.])]
    lattice = NS(levels=levels,occupied=levels[1:-1])
    carve = NS(house=(2.,2.,12.,18.),stage=(12.,2.,20.,18.),
               clear_house_m=7.,clear_stage_m=8.,removed={})
    level = reserve_transfer_zone(lattice,carve,.3)
    assert level.id == 'L04'
    assert set(carve.removed)=={2,3}
    assert all(not lv.voids for lv in levels)
    assert reserve_transfer_zone(lattice,carve,.3).id=='L04'
    assert all(len(cuts)==2 for cuts in carve.removed.values())


def test_unavailable_registered_transfer_depth_leaves_reservation_unchanged():
    levels = [NS(index=i,id=f'L{i:02d}',z=float(i*3),voids=[]) for i in range(4)]
    lattice = NS(levels=levels,occupied=levels[1:])
    carve = NS(house=(0,0,5,5),stage=(5,0,10,5),clear_house_m=8.,clear_stage_m=8.,removed={})
    assert reserve_transfer_zone(lattice,carve,.3) is None
    assert not carve.removed


def test_fascia_is_split_at_real_removed_floor_and_not_left_floating():
    hole = [v2(4,-2),v2(8,-2),v2(8,2),v2(4,2)]
    assert retained_edge_segments(v2(0,0),v2(10,0),[hole]) == [((0.,0.),(4.,0.)),((8.,0.),(10.,0.))]
    assert retained_edge_segments(v2(5,0),v2(7,0),[hole]) == []
