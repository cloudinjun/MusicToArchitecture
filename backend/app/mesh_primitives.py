"""Portable tessellation for the four v3 primitives (metres, no scene authority).

Box/member vertices are also read by spatial checks and the Blender adapter. Polygon
holes are triangulated with Shapely's constrained Delaunay implementation, never filled
by a bounding box or a nearest-vertex keyhole. No automatic mesh repair lives here.
"""
from __future__ import annotations

import math
from typing import Mapping, Sequence

Point = tuple[float, float, float]
Face = tuple[int, ...]


def _xyz(point: Mapping) -> Point:
    value = tuple(float(point[k]) for k in 'xyz')
    if not all(math.isfinite(v) for v in value):
        raise ValueError('Non-finite geometry coordinate')
    return value


def _unit(v: Sequence[float]) -> Point:
    length = math.sqrt(sum(x * x for x in v))
    if not math.isfinite(length) or length <= 1e-12:
        raise ValueError('Degenerate direction or repeated member path point')
    return tuple(x / length for x in v)


def _cross(a: Sequence[float], b: Sequence[float]) -> Point:
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def profile_outline(profile: Mapping) -> list[tuple[float, float]]:
    d, b = float(profile['depth_m']), float(profile['width_m'])
    if not all(math.isfinite(x) and x > 0 for x in (d, b)):
        raise ValueError('Profile dimensions must be finite and positive')
    shape = profile['shape']
    if shape == 'i_section':
        tw, tf = float(profile['web_m']), float(profile['flange_m'])
        if not (0 < tw < b and 0 < tf < d / 2):
            raise ValueError('Invalid I-section web/flange dimensions')
        hb, hd, hw = b/2, d/2, tw/2
        return [(-hb,-hd),(hb,-hd),(hb,-hd+tf),(hw,-hd+tf),
                (hw,hd-tf),(hb,hd-tf),(hb,hd),(-hb,hd),
                (-hb,hd-tf),(-hw,hd-tf),(-hw,-hd+tf),(-hb,-hd+tf)]
    if shape == 'chs':
        # Match the current presentation outline, not a newly invented section.
        return [(d/2*math.cos(2*math.pi*k/10), d/2*math.sin(2*math.pi*k/10))
                for k in range(10)]
    if shape not in ('box', 'rectangle', 'plate'):
        raise ValueError(f'Unsupported profile shape: {shape}')
    return [(-b/2,-d/2),(b/2,-d/2),(b/2,d/2),(-b/2,d/2)]


def box_mesh(geometry: Mapping) -> tuple[list[Point], list[Face]]:
    c = _xyz(geometry['center']); s = _xyz(geometry['size'])
    angle = float(geometry.get('rotation_z', 0))
    if not math.isfinite(angle) or any(v <= 0 for v in s):
        raise ValueError('Box sizes must be positive and its angle finite')
    hx,hy,hz = (v/2 for v in s); co,si = math.cos(angle),math.sin(angle)
    local = [(-hx,-hy,-hz),(hx,-hy,-hz),(hx,hy,-hz),(-hx,hy,-hz),
             (-hx,-hy,hz),(hx,-hy,hz),(hx,hy,hz),(-hx,hy,hz)]
    vertices = [(c[0]+x*co-y*si,c[1]+x*si+y*co,c[2]+z) for x,y,z in local]
    return vertices, [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]


def member_mesh(geometry: Mapping, profiles: Mapping) -> tuple[list[Point], list[Face]]:
    path = [_xyz(p) for p in geometry['path']]
    if len(path) < 2:
        raise ValueError('A member needs at least two points')
    for a,b in zip(path,path[1:]):
        _unit(tuple(y-x for x,y in zip(a,b)))
    outline = profile_outline(profiles[geometry['profile']]); n = len(outline)
    up = _unit(_xyz(geometry.get('roll') or {'x':0,'y':0,'z':1}))
    vertices = []
    for index,point in enumerate(path):
        a,b = path[max(0,index-1)],path[min(len(path)-1,index+1)]
        axis = _unit(tuple(y-x for x,y in zip(a,b)))
        dot = sum(x*y for x,y in zip(axis,up))
        v = tuple(up[k]-axis[k]*dot for k in range(3))
        if sum(x*x for x in v) < 1e-12:
            # A caller may choose any roll parallel to the path, not just Z.
            seed = min(((1.,0.,0.),(0.,1.,0.),(0.,0.,1.)),
                       key=lambda e: abs(sum(x*y for x,y in zip(e,axis))))
            dot = sum(x*y for x,y in zip(seed,axis))
            v = tuple(seed[k]-axis[k]*dot for k in range(3))
        v = _unit(v); u = _unit(_cross(v,axis))
        vertices.extend(tuple(point[k]+u[k]*pu+v[k]*pv for k in range(3))
                        for pu,pv in outline)
    faces = [tuple(range(n-1,-1,-1)), tuple(range((len(path)-1)*n,len(path)*n))]
    for segment in range(len(path)-1):
        a,b = segment*n,(segment+1)*n
        faces.extend((a+k,a+(k+1)%n,b+(k+1)%n,b+k) for k in range(n))
    return vertices, faces


def _polygon_mesh(ring, holes, z0: float, z1: float):
    from shapely import constrained_delaunay_triangles
    from shapely.geometry import Polygon
    from shapely.geometry.polygon import orient
    if not (math.isfinite(z0) and math.isfinite(z1) and z1 > z0):
        raise ValueError('Extrusion top must be above its base')
    polygon = Polygon(ring, holes)
    if polygon.is_empty or not polygon.is_valid or polygon.area <= 1e-12:
        raise ValueError('Invalid polygon or holes; automatic fill/repair is forbidden')
    polygon = orient(polygon, sign=1.0)
    rings = [list(polygon.exterior.coords)[:-1]] + [list(r.coords)[:-1] for r in polygon.interiors]
    vertices: list[Point] = []; ids = {}
    def vertex(x,y,z):
        key = (float(x),float(y),float(z))
        if key not in ids:
            ids[key] = len(vertices); vertices.append(key)
        return ids[key]
    faces = []
    for triangle in constrained_delaunay_triangles(polygon).geoms:
        points = list(orient(triangle, sign=1.0).exterior.coords)[:-1]
        top = tuple(vertex(x,y,z1) for x,y in points)
        bottom = tuple(vertex(x,y,z0) for x,y in reversed(points))
        faces.extend((top,bottom))
    for boundary in rings:
        for a,b in zip(boundary,boundary[1:]+boundary[:1]):
            faces.append((vertex(*a,z0),vertex(*b,z0),vertex(*b,z1),vertex(*a,z1)))
    return vertices,faces


def extrusion_mesh(geometry: Mapping) -> tuple[list[Point], list[Face]]:
    ring = [(float(p['x']),float(p['y'])) for p in geometry['boundary']]
    holes = [[(float(p['x']),float(p['y'])) for p in r] for r in geometry.get('holes',[])]
    if not all(math.isfinite(v) for r in [ring,*holes] for p in r for v in p):
        raise ValueError('Non-finite polygon coordinate')
    return _polygon_mesh(ring,holes,float(geometry['z_base']),float(geometry['z_top']))


def quad_mesh(geometry: Mapping, thickness_m: float | None) -> tuple[list[Point], list[Face]]:
    if thickness_m is None or not math.isfinite(thickness_m) or thickness_m <= 0:
        raise ValueError('A printable quad needs a declared positive thickness_m')
    points = [_xyz(p) for p in geometry['corners']]
    if len(points) != 4:
        raise ValueError('A quad needs four corners')
    p = points[0]; u = _unit(tuple(points[1][i]-p[i] for i in range(3)))
    n = _unit(_cross(u,tuple(points[2][i]-p[i] for i in range(3))))
    v = _cross(n,u)
    if any(abs(sum((q[i]-p[i])*n[i] for i in range(3))) > 1e-6 for q in points):
        raise ValueError('Non-planar quad requires a reviewed panel construction')
    ring = [(sum((q[i]-p[i])*u[i] for i in range(3)),
             sum((q[i]-p[i])*v[i] for i in range(3))) for q in points]
    local,faces = _polygon_mesh(ring,[], -thickness_m/2, thickness_m/2)
    return [tuple(p[i]+x*u[i]+y*v[i]+z*n[i] for i in range(3)) for x,y,z in local],faces


def primitive_mesh(geometry: Mapping, profiles: Mapping, thickness_m=None):
    kind = geometry['type']
    if kind == 'box': return box_mesh(geometry)
    if kind == 'member': return member_mesh(geometry,profiles)
    if kind == 'extrusion': return extrusion_mesh(geometry)
    if kind == 'quad': return quad_mesh(geometry,thickness_m)
    raise ValueError(f'Unknown primitive: {kind}')


def triangulate_faces(vertices: Sequence[Point], faces: Sequence[Face]) -> list[tuple[int,int,int]]:
    """Triangulate concave caps without a fan across the empty web/flange corners."""
    from shapely import constrained_delaunay_triangles
    from shapely.geometry import Polygon
    out = []
    for face in faces:
        if len(face) == 3:
            out.append(tuple(face)); continue
        if len(face) == 4:
            out.extend(((face[0],face[1],face[2]),(face[0],face[2],face[3]))); continue
        points = [vertices[i] for i in face]
        normal = tuple(sum((a[(k+1)%3]-b[(k+1)%3])*(a[(k+2)%3]+b[(k+2)%3])
                           for a,b in zip(points,points[1:]+points[:1])) for k in range(3))
        axis = max(range(3), key=lambda k:abs(normal[k])); keep = [k for k in range(3) if k!=axis]
        coords = [(p[keep[0]],p[keep[1]]) for p in points]
        polygon = Polygon(coords)
        if not polygon.is_valid or polygon.area <= 1e-14:
            raise ValueError('Invalid mesh cap; no automatic polygon repair is allowed')
        lookup = {q:index for q,index in zip(coords,face)}
        orientation = sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(coords,coords[1:]+coords[:1]))
        for triangle in constrained_delaunay_triangles(polygon).geoms:
            ring = list(triangle.exterior.coords)[:-1]
            signed = sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(ring,ring[1:]+ring[:1]))
            if signed*orientation < 0:
                ring.reverse()
            out.append(tuple(lookup[q] for q in ring))
    return out
