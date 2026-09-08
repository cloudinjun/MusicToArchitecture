"""The authored public corridor primitive stays rectilinear and in-domain."""

from shapely.geometry import LineString, Polygon, box

import backend.app.navigation as navigation
from backend.app.navigation import WalkMesh, orthogonal_route


def _axis_aligned(path):
    return all(a[0] == b[0] or a[1] == b[1]
               for a, b in zip(path, path[1:]))


def test_clear_rectangle_returns_shortest_l_route_and_reuses_mesh():
    domain = box(0, 0, 12, 10)
    mesh = WalkMesh(domain)
    path = orthogonal_route(domain, (1, 1), (10, 8), mesh=mesh,
                            orthogonal_only=True)

    assert path == [(1, 1), (1, 8), (10, 8)]
    assert _axis_aligned(path)
    assert all(domain.covers(LineString([a, b]))
               for a, b in zip(path, path[1:]))


def _mesh_must_not_be_built(*_args, **_kwargs):
    raise AssertionError('orthogonal route unexpectedly built a WalkMesh')


def test_orthogonal_only_success_does_not_build_mesh(monkeypatch):
    monkeypatch.setattr(navigation, 'WalkMesh', _mesh_must_not_be_built)

    path = orthogonal_route(box(0, 0, 12, 10), (1, 1), (10, 8),
                            orthogonal_only=True)

    assert path == [(1, 1), (1, 8), (10, 8)]


def test_orthogonal_only_failure_does_not_build_mesh(monkeypatch):
    monkeypatch.setattr(navigation, 'WalkMesh', _mesh_must_not_be_built)
    domain = box(0, 0, 12, 10).difference(box(5, 0, 7, 10))

    assert orthogonal_route(domain, (2, 5), (10, 5),
                            orthogonal_only=True) is None


def test_successful_ordinary_orthogonal_route_does_not_build_mesh(monkeypatch):
    monkeypatch.setattr(navigation, 'WalkMesh', _mesh_must_not_be_built)

    path = orthogonal_route(box(0, 0, 12, 10), (1, 1), (10, 8))

    assert path == [(1, 1), (1, 8), (10, 8)]


def test_notch_uses_an_in_domain_orthogonal_detour():
    domain = box(0, 0, 12, 10).difference(box(4, 4, 8, 10))
    path = orthogonal_route(domain, (2, 2), (10, 8),
                            orthogonal_only=True)

    assert path is not None
    assert _axis_aligned(path)
    assert LineString(path).length > 10.0
    assert all(domain.covers(LineString([a, b]))
               for a, b in zip(path, path[1:]))


def test_blocked_domain_has_no_orthogonal_route():
    domain = box(0, 0, 12, 10).difference(box(5, 0, 7, 10))

    assert orthogonal_route(domain, (2, 5), (10, 5),
                            orthogonal_only=True) is None


def test_orthogonal_only_does_not_use_mesh_diagonal_fallback():
    # The only connection in this narrow diagonal domain is a direct diagonal
    # segment.  The public planner may still use its measured mesh fallback,
    # while authored program circulation must reject it.
    domain = Polygon([(-.5, 0), (10, 10.5), (10.5, 10), (0, -.5)])

    assert orthogonal_route(domain, (1, 1), (9, 9),
                            orthogonal_only=True) is None
    assert orthogonal_route(domain, (1, 1), (9, 9)) == [(1, 1), (9, 9)]
