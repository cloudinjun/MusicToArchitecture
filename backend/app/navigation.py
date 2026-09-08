"""Measured same-storey walking paths through emitted geometry.

The 0.60 m body and 2.00 m head envelope are project review probes, not code
widths. A constrained triangulation keeps holes and disconnected floor islands;
every published segment is checked against the eroded free domain. Distances are
sampled routes, not the maximum natural path or proof of independent exits.
"""
from __future__ import annotations

import heapq
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field
from shapely import constrained_delaunay_triangles, set_precision
from shapely.geometry import LineString, MultiPoint, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

from .geometry_review import _polygon, _z_interval
from .mesh_primitives import primitive_mesh

BODY_WIDTH_M = 0.60
HEAD_HEIGHT_M = 2.00
EPS_M = 1e-6
FLOOR_TOLERANCE_M = .005
STEP_REVIEW_M = .18
FLOOR_KINDS = {'floor_slab', 'podium_slab', 'stair_landing', 'ramp_landing'}
THEATRE_FLOOR_KINDS = {'auditorium_riser', 'auditorium_aisle', 'stage_platform'}
NON_SOLID_KINDS = {'program_zone', 'figure', 'earth', 'site_context'}


class RouteSample(BaseModel):
    id: str
    space_id: str
    level_id: str
    point: tuple[float, float]
    floor_z_m: float = 0.0
    origin: Literal['floor', 'seat_row_access', 'stage'] = 'floor'
    source_surface_ids: list[str] = Field(default_factory=list)
    reachable_exits: list[str] = Field(default_factory=list)


class WalkRoute(BaseModel):
    sample_id: str
    source: str
    target: str
    level_id: str
    distance_m: float
    points: list[tuple[float, float]]
    points_3d: list[tuple[float, float, float]] = Field(default_factory=list)
    step_count: int = 0
    source_surface_ids: list[str] = Field(default_factory=list)


class NavigationFinding(BaseModel):
    id: str
    status: Literal['passed', 'failed', 'unevaluated']
    subject: str
    detail: str


class NavigationReport(BaseModel):
    schema_version: Literal['mta.navigation/1.0'] = 'mta.navigation/1.0'
    body_width_m: float = BODY_WIDTH_M
    head_height_m: float = HEAD_HEIGHT_M
    step_review_m: float = STEP_REVIEW_M
    basis: str = 'Project geometry probe; adopted-code clear width and headroom unverified.'
    samples: list[RouteSample] = Field(default_factory=list)
    routes: list[WalkRoute] = Field(default_factory=list)
    findings: list[NavigationFinding] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=lambda: [
        'Theatre steps use emitted top surfaces and physical edge contacts; ramps and inter-storey flights remain unverified.',
        'The 0.60 m body and 0.18 m step probes do not establish an accessible route or adopted-code compliance.',
        'Room components and extremal points are sampled; maximum travel and independent route branches are unverified.',
        'Member and panel projections are conservative over the probe height; closed leaves open only at verified portals.',
        'Stair candidates do not establish rated exits or discharge to a public way.',
    ])


def polygons(geometry):
    if isinstance(geometry, Polygon):
        return [geometry] if geometry.area > EPS_M**2 else []
    return [piece for part in getattr(geometry, 'geoms', []) for piece in polygons(part)]


def _projection(element, profiles):
    geometry = getattr(element, 'geometry', None)
    if geometry is None:
        raise ValueError(f'{element.id}: missing primitive')
    polygon, interval = _polygon(geometry), _z_interval(geometry)
    if polygon is not None and interval:
        return polygon, interval
    vertices, _ = primitive_mesh(geometry.model_dump(), profiles,
                                 getattr(element, 'thickness_m', None))
    footprint = MultiPoint([(x, y) for x, y, _ in vertices]).convex_hull
    if not isinstance(footprint, Polygon) or not footprint.is_valid:
        raise ValueError(f'{element.id}: invalid or zero-width obstacle')
    return footprint, (min(p[2] for p in vertices), max(p[2] for p in vertices))


def free_floor(model, level, open_door_ids=()):
    """Return supported floor minus physical obstructions, plus missing evidence."""
    profiles = {k: v.model_dump() if hasattr(v, 'model_dump') else v
                for k, v in getattr(model, 'profiles', {}).items()}
    floors, obstacles, unresolved = [], [], []
    for element in model.elements:
        if element.kind in NON_SOLID_KINDS or element.id in open_door_ids:
            continue
        # Context and entourage are not a walkable floor or a building obstacle.
        if getattr(element, 'semantic_layer', '') == 'site' and element.kind not in FLOOR_KINDS:
            continue
        try:
            polygon, (bottom, top) = _projection(element, profiles)
        except (ValueError, KeyError, TypeError) as exc:
            # A semantic level does not bound a multi-storey member. Unknown
            # geometry has no measured extent proving it harmless on other floors.
            unresolved.append(str(exc))
            continue
        if element.kind in FLOOR_KINDS and abs(top - level.z) <= FLOOR_TOLERANCE_M:
            floors.append(polygon)
        elif top > level.z + EPS_M and bottom < level.z + HEAD_HEIGHT_M - EPS_M:
            obstacles.append(polygon)
    if not floors:
        return Polygon(), [*unresolved, 'No emitted floor surface at the level elevation.']
    surface = unary_union(floors)
    if obstacles:
        surface = surface.difference(unary_union(obstacles))
    return surface.buffer(-BODY_WIDTH_M / 2, join_style='mitre'), unresolved


class WalkMesh:
    """Triangle adjacency with an actual crossing point on each shared edge."""
    def __init__(self, domain):
        self.domain = domain
        self.triangles = list(constrained_delaunay_triangles(domain).geoms)
        self.centers = [tuple(t.centroid.coords[0]) for t in self.triangles]
        self.tree = STRtree(self.triangles)
        self.adj = defaultdict(list)
        shared = {}
        for i, triangle in enumerate(self.triangles):
            coords = list(triangle.exterior.coords)
            for a, b in zip(coords, coords[1:]):
                key = tuple(sorted((a, b)))
                if key not in shared:
                    shared[key] = i
                    continue
                j = shared[key]
                crossing = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                cost = math.dist(self.centers[i], crossing) + math.dist(crossing, self.centers[j])
                self.adj[i].append((j, cost, crossing))
                self.adj[j].append((i, cost, crossing))

    def locate(self, point):
        found = self.tree.query(Point(point), predicate='intersects')
        return int(min(found)) if len(found) else None

    def destination(self, point):
        target = self.locate(point)
        if target is None:
            return {}, {}
        costs, onward = {target: math.dist(self.centers[target], point)}, {}
        queue = [(costs[target], target)]
        while queue:
            cost, node = heapq.heappop(queue)
            if cost != costs[node]:
                continue
            for neighbor, weight, crossing in self.adj[node]:
                candidate = cost + weight
                if candidate < costs.get(neighbor, math.inf):
                    costs[neighbor], onward[neighbor] = candidate, (node, crossing)
                    heapq.heappush(queue, (candidate, neighbor))
        return costs, onward

    def route(self, start, target, destination=None):
        if self.locate(start) is None or self.locate(target) is None:
            return None
        if self.domain.covers(LineString([start, target])):
            return [start, target]
        costs, onward = destination or self.destination(target)
        node = self.locate(start)
        if node not in costs:
            return None
        points = [start, self.centers[node]]
        while node in onward:
            node, crossing = onward[node]
            points.extend([crossing, self.centers[node]])
        points.append(target)
        # Remove triangle detours only when the complete shortcut stays inside.
        simple, i = [points[0]], 0
        while i < len(points) - 1:
            j = len(points) - 1
            while j > i + 1 and not self.domain.covers(LineString([points[i], points[j]])):
                j -= 1
            simple.append(points[j])
            i = j
        if not all(self.domain.covers(LineString([a, b])) for a, b in zip(simple, simple[1:])):
            raise ValueError('Navigation produced a segment outside the free floor.')
        return simple


def orthogonal_route(domain, start, target, *, mesh=None, corners=None,
                     orthogonal_only=False):
    """Find the shortest currently-supported axis-aligned route.

    The first pass follows the public-circulation convention: try the two
    one-corner L routes, then route through every x/y coordinate exposed by the
    free-domain boundary.  When those routes do not fit, the ordinary
    :class:`WalkMesh` route remains the fallback for the public planner.
    ``orthogonal_only`` is the stricter authoring contract: it returns ``None``
    instead of accepting that mesh fallback, so a caller cannot quietly add a
    diagonal corridor.

    ``mesh`` and ``corners`` can be supplied when several connections share a
    domain.  The mesh must have been built from ``domain`` (or an equivalent
    geometry); its eroded domain is the surface used by all coverage checks.
    """
    if domain is None or getattr(domain, 'is_empty', False):
        return None
    route_domain = mesh.domain if mesh is not None else domain
    if route_domain.is_empty:
        return None

    if corners is None:
        corners = [point for poly in polygons(route_domain)
                   for ring in [poly.exterior, *poly.interiors]
                   for point in ring.coords]
    else:
        corners = list(corners)

    # Orthogonal corridors preserve useful room strips. Every candidate is
    # checked in the eroded floor; the mesh handles harder plans when the
    # caller permits its measured fallback.
    sx, sy = start
    tx, ty = target
    choices = [[start, (sx, ty), target], [start, (tx, sy), target]]
    legal = [path for path in choices
             if route_domain.covers(LineString(path))]
    if not legal:
        choices = (
            [[start, (x, sy), (x, ty), target]
             for x in sorted({point[0] for point in corners})] +
            [[start, (sx, y), (tx, y), target]
             for y in sorted({point[1] for point in corners})]
        )
        legal = [path for path in choices
                 if route_domain.covers(LineString(path))]
    if legal:
        path = min(legal,
                   key=lambda candidate: sum(
                       math.dist(a, b) for a, b in zip(candidate, candidate[1:])))
        compact = [point for index, point in enumerate(path)
                   if index == 0 or point != path[index - 1]]
        # The generated choices are axis-aligned by construction. Keep the
        # final predicates explicit so a future corner provider cannot widen
        # the route class accidentally.
        if (all(abs(a[0] - b[0]) <= EPS_M or abs(a[1] - b[1]) <= EPS_M
                for a, b in zip(compact, compact[1:])) and
                all(route_domain.covers(LineString([a, b]))
                    for a, b in zip(compact, compact[1:]))):
            return compact
        if orthogonal_only:
            return None

    if orthogonal_only:
        return None
    # Rectilinear authoring never uses triangle navigation. Build that graph
    # only for the public planner's permitted non-orthogonal fallback.
    return (mesh if mesh is not None else WalkMesh(route_domain)).route(start, target)


def _lines(geometry):
    if geometry.is_empty:
        return []
    if isinstance(geometry, LineString):
        return [geometry]
    return [line for part in getattr(geometry, 'geoms', []) for line in _lines(part)]


def _path_length(points):
    return sum(math.dist(a,b) for a,b in zip(points,points[1:]))


@dataclass
class _WalkSurface:
    ids: list[str]
    kind: str
    bottom: float
    top: float
    region: object
    mesh: WalkMesh | None = None


def _theatre_surface(element, level):
    return element.level_id == level.id and (
        element.kind in THEATRE_FLOOR_KINDS or
        (getattr(element, 'subsystem', '') == 'stage_access' and
         element.kind in {'stair_tread', 'stair_landing'}))


class SteppedWalkMesh:
    """Small portal graph over measured horizontal theatre surfaces.

    A tread may be shorter than the body diameter. Its width envelope therefore
    includes physically contacting neighbour treads, while graph crossings still
    occur only on their shared edge. Every within-surface leg uses WalkMesh.
    """
    def __init__(self, model, level, open_door_ids=()):
        self.surfaces = []
        self.unknown = []
        self.adj = defaultdict(list)
        self.nodes = []
        self.by_surface = defaultdict(list)
        profiles = {key: value.model_dump() if hasattr(value, 'model_dump') else value
                    for key,value in getattr(model, 'profiles', {}).items()}
        measured = []
        for element in model.elements:
            if (element.kind in NON_SOLID_KINDS or element.id in open_door_ids or
                (getattr(element, 'semantic_layer', '') == 'site' and element.kind not in FLOOR_KINDS)):
                continue
            try:
                polygon, interval = _projection(element, profiles)
                # Shared box edges differ by machine round-off after center/size
                # reconstruction. A 0.1 micrometre grid is below the contact probe
                # tolerance and cannot bridge a missing tread or a visible gap.
                measured.append((element, set_precision(set_precision(polygon,EPS_M/10),0), *interval))
            except (ValueError, KeyError, TypeError) as error:
                self.unknown.append(str(error))
        if self.unknown:
            return
        floors, raised, ordinary = [], [], []
        for element, polygon, bottom, top in measured:
            theatre = _theatre_surface(element, level)
            at_floor = (abs(top-level.z)<=EPS_M and bottom<=level.z+EPS_M if theatre
                        else element.kind in FLOOR_KINDS and abs(top-level.z)<=FLOOR_TOLERANCE_M)
            if at_floor:
                floors.append((element.id,polygon,bottom))
            elif theatre:
                # Only exact planar horizontal tops are admitted. A projected
                # member/quad bounding box is not evidence of a walking surface.
                if _polygon(element.geometry) is None or _z_interval(element.geometry) is None:
                    self.unknown.append(f'{element.id}: no measured horizontal top surface')
                    continue
                raised.append(_WalkSurface([element.id],element.kind,bottom,top,polygon))
            else:
                ordinary.append((polygon,bottom,top))
        if not floors:
            self.unknown.append('No emitted floor surface at the level elevation.')
        if self.unknown:
            return
        floor = _WalkSurface([item[0] for item in floors], 'floor',
            min(item[2] for item in floors), level.z, unary_union([item[1] for item in floors]))
        self.surfaces = [floor,*raised]
        # A lower slab cannot be walked through the solid stage or bowl above it.
        originals = [surface.region for surface in self.surfaces]
        for surface in self.surfaces:
            above = [polygon for other,polygon in zip(self.surfaces,originals)
                     if other.top > surface.top+EPS_M and polygon.intersects(surface.region)]
            if above:
                surface.region = surface.region.difference(unary_union(above))
        tree = STRtree([surface.region for surface in self.surfaces])
        contacts = []
        neighbors = defaultdict(set)
        for i,a in enumerate(self.surfaces):
            for hit in tree.query(a.region):
                j = int(hit)
                b = self.surfaces[j]
                if (j <= i or abs(a.top-b.top) > STEP_REVIEW_M+EPS_M or
                    max(a.bottom,b.bottom) > min(a.top,b.top)+EPS_M):
                    continue
                for line in _lines(a.region.boundary.intersection(b.region.boundary)):
                    if line.length >= BODY_WIDTH_M-EPS_M:
                        contacts.append((i,j,line))
                        neighbors[i].add(j)
                        neighbors[j].add(i)
        obstacle_tree = STRtree([item[0] for item in ordinary])
        for i,surface in enumerate(self.surfaces):
            envelope = unary_union([surface.region,*[self.surfaces[j].region for j in neighbors[i]]])
            blockers = [ordinary[int(hit)][0] for hit in obstacle_tree.query(envelope)
                        if ordinary[int(hit)][2] > surface.top+EPS_M and
                        ordinary[int(hit)][1] < surface.top+HEAD_HEIGHT_M-EPS_M]
            if blockers:
                envelope = envelope.difference(unary_union(blockers))
            # One micrometre numerical tolerance retains the center line of an
            # exactly 0.60 m passage; it cannot admit a narrower planning lane.
            domain = surface.region.intersection(envelope.buffer(-BODY_WIDTH_M/2+EPS_M,join_style='mitre'))
            surface.mesh = WalkMesh(domain)
        for i,j,line in contacts:
            shared = line.intersection(self.surfaces[i].mesh.domain).intersection(self.surfaces[j].mesh.domain)
            pieces = _lines(shared)
            if shared.geom_type == 'Point' and not shared.is_empty:
                pieces = [shared]
            for piece in pieces:
                xy = tuple((piece.interpolate(.5,normalized=True) if isinstance(piece,LineString) else piece).coords[0])
                a,b = len(self.nodes),len(self.nodes)+1
                for index in (i,j):
                    self.by_surface[index].append(len(self.nodes))
                    self.nodes.append((index,(*xy,self.surfaces[index].top)))
                self._edge(a,b,[self.nodes[a][1],self.nodes[b][1]])
        # Within-surface portal connections are measured paths, including detours
        # around emitted chairs, rails, walls and equipment at this elevation.
        for index, nodes in self.by_surface.items():
            surface = self.surfaces[index]
            for offset,a in enumerate(nodes):
                for b in nodes[offset+1:]:
                    path = surface.mesh.route(self.nodes[a][1][:2],self.nodes[b][1][:2])
                    if path is not None:
                        self._edge(a,b,[(*point,surface.top) for point in path])

    def _edge(self, a, b, path):
        length = _path_length(path)
        self.adj[a].append((b,length,path))
        self.adj[b].append((a,length,list(reversed(path))))

    def destination(self, target):
        if not self.surfaces:
            return {},{},{}
        floor = self.surfaces[0]
        costs,onward,tails = {},{},{}
        for node in self.by_surface[0]:
            path = floor.mesh.route(self.nodes[node][1][:2],target)
            if path is not None:
                tails[node] = [(*point,floor.top) for point in path]
                costs[node] = _path_length(path)
        queue = [(cost,node) for node,cost in costs.items()]
        heapq.heapify(queue)
        while queue:
            cost,node = heapq.heappop(queue)
            if cost != costs[node]:
                continue
            for neighbor,weight,path in self.adj[node]:
                candidate = cost+weight
                if candidate < costs.get(neighbor,math.inf):
                    costs[neighbor] = candidate
                    onward[neighbor] = node,list(reversed(path))
                    heapq.heappush(queue,(candidate,neighbor))
        return costs,onward,tails

    def route(self, start, elevation, target, destination=None):
        if not self.surfaces:
            return None
        floor = self.surfaces[0]
        if abs(elevation-floor.top)<=EPS_M:
            direct = floor.mesh.route(start,target)
            if direct is not None:
                return [(*point,floor.top) for point in direct],floor.ids
        costs,onward,tails = destination or self.destination(target)
        best = None
        for index,surface in enumerate(self.surfaces):
            if abs(surface.top-elevation)>EPS_M or surface.mesh.locate(start) is None:
                continue
            for node in self.by_surface[index]:
                if node not in costs:
                    continue
                path = surface.mesh.route(start,self.nodes[node][1][:2])
                if path is None:
                    continue
                total = _path_length(path)+costs[node]
                if best is None or total < best[0]:
                    best = total,node,[(*point,surface.top) for point in path],list(surface.ids)
        if best is None:
            return None
        _,node,path,source_ids = best
        while node in onward:
            node,segment = onward[node]
            path.extend(segment)
            source_ids.extend(self.surfaces[self.nodes[node][0]].ids)
        path.extend(tails[node])
        compact = [path[0]]
        for point in path[1:]:
            if math.dist(point,compact[-1])>EPS_M:
                compact.append(point)
        return compact,list(dict.fromkeys(source_ids))


def _sample_points(region):
    for component in polygons(region):
        center = tuple(component.representative_point().coords[0])
        yield center
        vertices = list(component.exterior.coords)[:-1]
        for dx, dy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
            yield max(vertices, key=lambda p: dx*p[0] + dy*p[1])


def _theatre_samples(model, space, zone, graph, report):
    if getattr(zone, 'space_type', '') == 'auditorium':
        reservations = [reservation for reservation in getattr(getattr(model,'room_layout_plan',None),'reservations',[])
                        if reservation.space_id == zone.space_id and reservation.level_id == zone.level_id
                        and reservation.purpose == 'seat_row_access']
        if not reservations and any(surface.kind=='auditorium_riser' for surface in graph.surfaces):
            report.findings.append(NavigationFinding(id='NAV-SEAT-ACCESS-UNKNOWN',status='unevaluated',
                subject=space.id,detail='Raised seat floors have no located seat-row passage evidence to sample.'))
        for reservation in reservations:
            candidates = [surface for surface in graph.surfaces
                          if abs(surface.top-reservation.floor_z_m)<=EPS_M]
            region = Polygon(reservation.polygon).intersection(unary_union([surface.mesh.domain for surface in candidates]))
            points = list(dict.fromkeys(_sample_points(region.buffer(-EPS_M/100,join_style='mitre'))))
            if not points:
                report.findings.append(NavigationFinding(id='NAV-SEAT-SURFACE',status='failed',subject=space.id,
                    detail=f'{reservation.id}: no emitted clear walking surface at the declared row elevation.'))
            for point in points:
                ids = [identifier for surface in candidates if surface.mesh.locate(point) is not None for identifier in surface.ids]
                yield point,reservation.floor_z_m,'seat_row_access',ids
    if getattr(zone, 'space_type', '') == 'stage':
        found = False
        for surface in graph.surfaces:
            if surface.kind != 'stage_platform':
                continue
            region = surface.mesh.domain.intersection(box(zone.x0,zone.y0,zone.x1,zone.y1))
            for point in dict.fromkeys(_sample_points(region.buffer(-EPS_M/100,join_style='mitre'))):
                found = True
                yield point,surface.top,'stage',surface.ids
        if not found:
            report.findings.append(NavigationFinding(id='NAV-STAGE-SURFACE',status='failed',subject=space.id,
                detail='No emitted stage top has a clear supported area fitting the planning body envelope.'))


def build_navigation(model, nodes, portal_report=None):
    report = NavigationReport()
    open_ids = {name for portal in getattr(portal_report, 'portals', [])
                if portal.passable for name in portal.door_ids}
    zones = {f'SP-{z.level_id}-{z.space_id}': z for z in model.program_allocation.zones}
    for level in model.lattice.levels:
        spaces = [n for n in nodes if n.level_id == level.id and n.kind == 'space']
        if not spaces:
            continue
        stepped = (SteppedWalkMesh(model,level,open_ids)
                   if any(_theatre_surface(element,level) for element in model.elements) else None)
        if stepped is not None:
            unresolved = stepped.unknown
            domain = stepped.surfaces[0].mesh.domain if stepped.surfaces else Polygon()
        else:
            domain, unresolved = free_floor(model, level, open_ids)
        if unresolved:
            report.findings.append(NavigationFinding(id='NAV-GEOMETRY-UNKNOWN',
                status='unevaluated', subject=level.id, detail='; '.join(unresolved)))
            # Unknown solids could wall off an apparently good route.
            continue
        mesh = stepped.surfaces[0].mesh if stepped is not None else WalkMesh(domain)
        exits = [n for n in nodes if n.level_id == level.id and n.kind != 'space']
        destinations = {n.id: (stepped or mesh).destination((n.x,n.y)) for n in exits}
        for space in spaces:
            zone = zones[space.id]
            region = domain.intersection(box(zone.x0, zone.y0, zone.x1, zone.y1))
            points = [(point,level.z,'floor',[]) for point in dict.fromkeys(_sample_points(region))]
            if stepped is not None:
                points.extend(_theatre_samples(model,space,zone,stepped,report))
            if not points:
                report.findings.append(NavigationFinding(id='NAV-NO-WALKING-SPACE',
                    status='failed', subject=space.id,
                    detail='No supported obstacle-free area fits the body envelope at this storey elevation.'))
            for i, (point,elevation,origin,surface_ids) in enumerate(points):
                sample = RouteSample(id=f'{space.id}-P{i:03}', space_id=space.id,
                    level_id=level.id,point=point,floor_z_m=elevation,origin=origin,source_surface_ids=surface_ids)
                for target in exits:
                    if stepped is not None:
                        result = stepped.route(point,elevation,(target.x,target.y),destinations[target.id])
                        if result is None:
                            continue
                        path_3d,used_ids = result
                        path = [item[:2] for item in path_3d]
                    else:
                        path = mesh.route(point,(target.x,target.y),destinations[target.id])
                        if path is None:
                            continue
                        path_3d,used_ids = [(*item,level.z) for item in path],[]
                    sample.reachable_exits.append(target.id)
                    report.routes.append(WalkRoute(sample_id=sample.id, source=space.id,
                        target=target.id, level_id=level.id,
                        distance_m=round(_path_length(path_3d),5),
                        points=path,points_3d=path_3d,source_surface_ids=used_ids,
                        step_count=sum(abs(a[2]-b[2])>EPS_M for a,b in zip(path_3d,path_3d[1:]))))
                report.samples.append(sample)
                if not sample.reachable_exits:
                    report.findings.append(NavigationFinding(id='NAV-UNREACHABLE', status='failed',
                        subject=sample.id, detail='No measured path from this room sample to a stair candidate.'))
        report.findings.append(NavigationFinding(id='NAV-CODE-BASIS', status='unevaluated',
            subject=level.id, detail='Measured geometry routes use a planning body envelope; code width, '
            'maximum travel, rated protection, route independence and discharge are not verified.'))
    return report
