"""The Blender adapter preserves portable holes and building-scale depth precision."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


@pytest.fixture(scope='module')
def adapter():
    spec = importlib.util.spec_from_file_location(
        'mta_camera_test', Path(__file__).resolve().parents[2]
        / 'blender/import_building_model_v3.py')
    module = importlib.util.module_from_spec(spec)
    # The depth-range calculation is pure; no Blender scene or operator is mocked.
    with patch.dict('sys.modules', {'bpy': SimpleNamespace()}):
        spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('scale', [.01, 1, 100])
def test_review_clip_range_preserves_geometry_and_relative_precision(adapter, scale):
    depths = [80 * scale, 125 * scale, 260 * scale]
    near, far = adapter._review_clip_distances(depths)
    assert 0 < near < min(depths) < max(depths) < far
    assert far / near == pytest.approx(16.25)
    assert near == pytest.approx(20 * scale)


@pytest.mark.parametrize('depths', [[0, 1], [-1, 3], [float('nan')], [1, float('inf')]])
def test_review_clip_range_rejects_invalid_camera_placement(adapter, depths):
    with pytest.raises(ValueError, match='in front'):
        adapter._review_clip_distances(depths)


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('height', [.005, 2.7])
def test_blender_extrusion_matches_portable_concave_body_with_two_holes(adapter, reverse, height):
    from backend.app.mesh_primitives import extrusion_mesh, triangulate_faces
    from shapely.geometry import Polygon
    import trimesh

    outer = [(0, 0), (18, 0), (18, 12), (12, 12), (12, 7), (6, 7), (6, 12), (0, 12)]
    holes = [[(1, 1), (4, 1), (4, 5), (1, 5)],
             [(14, 2), (17, 2), (17, 6), (14, 6)]]
    rings = [outer, *holes]
    if reverse:
        rings = [list(reversed(ring)) for ring in rings]
    geometry = {'type': 'extrusion',
        'boundary': [dict(x=x, y=y) for x, y in rings[0]],
        'holes': [[dict(x=x, y=y) for x, y in ring] for ring in rings[1:]],
        'z_base': 24., 'z_top': 24. + height}
    bucket = adapter.MeshBucket()
    adapter.add_extrusion(bucket, geometry)
    vertices, faces = extrusion_mesh(geometry)
    assert bucket.verts == vertices
    assert bucket.faces == faces
    expected = Polygon(outer, holes)
    for face in faces:
        if len(face) == 3:
            assert expected.covers(Polygon([(vertices[i][0], vertices[i][1]) for i in face]))
    solid = trimesh.Trimesh(vertices=vertices, faces=triangulate_faces(vertices, faces), process=True)
    assert solid.is_volume
    assert solid.volume == pytest.approx(expected.area * height)
