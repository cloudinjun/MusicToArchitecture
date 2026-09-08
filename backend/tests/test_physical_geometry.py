from math import pi

import pytest
from shapely.geometry import Polygon

from backend.app.geometry import BoxGeometry, ExtrusionGeometry, MemberGeometry, ProfileSpec, v2, v3
from backend.app.physical_geometry import physical_projection


def test_vertical_i_member_uses_real_section_instead_of_convex_hull():
    profile = ProfileSpec(
        id='I-400x400x400x400',
        shape='i_section',
        depth_m=4.0,
        width_m=4.0,
        web_m=0.4,
        flange_m=0.4,
    )
    member = MemberGeometry(
        path=[v3(0.0, 0.0, 0.0), v3(0.0, 0.0, 8.0)],
        profile=profile.id,
    )

    projection = physical_projection(member, profiles={profile.id: profile})

    assert projection.z_interval == pytest.approx((0.0, 8.0))
    assert projection.footprint.area == pytest.approx(4.48, abs=1.0e-6)
    assert projection.footprint.area < projection.footprint.convex_hull.area * 0.5


def test_box_projection_preserves_rotation():
    box = BoxGeometry(
        center=v3(10.0, -3.0, 2.0),
        size=v3(4.0, 2.0, 1.0),
        rotation_z=pi / 4.0,
    )
    projection = physical_projection(box)
    half_x, half_y = 2.0, 1.0
    expected_points = []
    for local_x, local_y in ((-half_x, -half_y), (half_x, -half_y),
                             (half_x, half_y), (-half_x, half_y)):
        expected_points.append((
            10.0 + (local_x - local_y) / 2**0.5,
            -3.0 + (local_x + local_y) / 2**0.5,
        ))

    assert projection.z_interval == pytest.approx((1.5, 2.5))
    assert projection.footprint.symmetric_difference(Polygon(expected_points)).area < 1.0e-10
    assert projection.footprint.area == pytest.approx(8.0)


def test_extrusion_projection_preserves_holes():
    outer = [v2(0.0, 0.0), v2(10.0, 0.0), v2(10.0, 8.0), v2(0.0, 8.0)]
    hole = [v2(2.0, 2.0), v2(4.0, 2.0), v2(4.0, 5.0), v2(2.0, 5.0)]
    extrusion = ExtrusionGeometry(boundary=outer, holes=[hole], z_base=-1.0, z_top=3.0)

    projection = physical_projection(extrusion)

    assert projection.z_interval == pytest.approx((-1.0, 3.0))
    assert projection.footprint.area == pytest.approx(80.0 - 6.0)
    assert len(projection.footprint.interiors) == 1
    hole_polygon = Polygon([(point.x, point.y) for point in hole])
    assert not projection.footprint.contains(hole_polygon.representative_point())


def test_profile_dicts_are_accepted_and_missing_mesh_inputs_fail_clearly():
    profile = ProfileSpec(
        id='POST', shape='box', depth_m=0.2, width_m=0.2,
    )
    member = MemberGeometry(
        path=[v3(1.0, 2.0, 0.0), v3(1.0, 2.0, 2.0)], profile='POST',
    )
    assert physical_projection(member, profiles={'POST': profile.model_dump()}).footprint.area == pytest.approx(0.04)

    with pytest.raises(ValueError, match='profile'):
        physical_projection(member)
    with pytest.raises(ValueError, match='thickness_m'):
        physical_projection({
            'type': 'quad',
            'corners': [
                {'x': 0.0, 'y': 0.0, 'z': 0.0},
                {'x': 2.0, 'y': 0.0, 'z': 0.0},
                {'x': 2.0, 'y': 1.0, 'z': 0.0},
                {'x': 0.0, 'y': 1.0, 'z': 0.0},
            ],
        })
