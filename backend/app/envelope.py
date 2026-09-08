"""Envelope emitters, one per tectonic family.

`compiler_v3._emit_envelope` used to be a single function that built a curtain wall,
because a curtain wall was the only envelope the project had. Everything it could vary
-- module, transom rows, spandrel height, opaque share, fin depth, standoff -- moved
quantities inside that one wall, so fourteen recordings produced fourteen curtain walls
of slightly different grain. This module is where the wall stops being a constant.

The families differ in the **operation** they perform on an elevation, not in the size
of the result, and that is what the eye reads:

    subdivide   draw a frame; the openings are the cells left between members
    subtract    draw a wall; the openings are holes cut out of it
    overlay     draw a plain skin; stand a second structure in front of it
    recess      push the skin back inside the structural bay so the frame reads

A note on the punched wall, because the obvious implementation is wrong: an opening in a
wall is a hole in a *vertical* plane, and `ExtrusionGeometry` extrudes a plan polygon
upward, so it cannot express one. The wall is built instead as four quads around each
opening -- sill band, head band, two jambs -- with the reveal drawn as real boxes. That
is more honest than faking the hole and better for a study model besides, because a
reveal with thickness casts the shadow that makes masonry read as masonry.

Every element still carries the datums that placed it, so the translation report keeps
working across all eight families.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from shapely import set_precision
from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import nearest_points, unary_union

from .geometry import (
    BoxGeometry, ExtrusionGeometry, MemberGeometry, QuadGeometry, Vector3,
    convention_profile, inset, v2, v3,
)
from .grammar_specs import GrammarSpec, spec_for
from .plan_regions import _ring, _simple_parts, extrusions, polygon
from .tectonics import EnvelopeTectonic
from .approach import ENTRANCE_MIN_WIDTH_M
from .facade_control import facade_band_levels

PLATE_DATUMS = ('cantilever_m', 'plate_step_m', 'plate_rotation_deg', 'apse_radius_m')

# Conceptual folded enclosure and its supporting edge brackets. These dimensions
# describe a planning assembly; drainage, waterproofing and attachment design remain
# unverified. They do not change the structural slab or cover its internal openings.
EDGE_RETURN_THICKNESS_M = 0.075
EDGE_BRACKET_PROFILE = 'TRAN-75x140'
GEOMETRY_EPS_M = 1.0e-5

# Shared entrance planning recipe; adopted-code capacity and door hardware remain
# review items. The platform and its stair use these same physical dimensions.
ENTRANCE_REVEAL_DEPTH_M = 0.45
ENTRANCE_EDGE_MARGIN_M = 0.15
ENTRANCE_HEAD_M = 2.6


@dataclass(frozen=True)
class EntrancePlan:
    level_id: str
    floor_z: float
    center: tuple[float, float]
    width_m: float
    edge: int
    fraction: float
    tangent: tuple[float, float]
    inward: tuple[float, float]
    aperture: Polygon
    inside_approach: Polygon
    outside_approach: Polygon


def planned_entrance(lattice, datums, approach) -> EntrancePlan | None:
    """One actual slab-edge threshold, shared by envelope and public allocation."""
    from .portals import APPROACH_DEPTH_M, APPROACH_WIDTH_M
    intent = getattr(lattice, 'circulation_intent', None)
    level_id = (intent.entry_station.level_id if intent is not None else
                approach.get('podium_id') if approach else None)
    level = next((lv for lv in lattice.levels if lv.id == level_id), None)
    rect = approach.get('entry') if approach else None
    if level is None or (intent is None and rect is None):
        return None

    if intent is not None:
        # Program Volume authored one oriented boundary station.  Resolve it on the
        # immutable authoring grid, then locate that same physical point on the actual
        # plate ring.  Polygon cleanup may merge collinear grid edges, so edge indices
        # themselves are deliberately not shared across the seam.
        expected, expected_tangent, expected_outward = (
            intent.entry_station.resolve(lattice))
        candidates = []
        for edge, (a, c) in enumerate(
                zip(level.plate, level.plate[1:] + level.plate[:1])):
            dx, dy = c.x - a.x, c.y - a.y
            length_sq = dx * dx + dy * dy
            if length_sq <= GEOMETRY_EPS_M ** 2:
                continue
            fraction = ((expected[0] - a.x) * dx
                        + (expected[1] - a.y) * dy) / length_sq
            if fraction < -GEOMETRY_EPS_M or fraction > 1.0 + GEOMETRY_EPS_M:
                continue
            fraction = min(1.0, max(0.0, fraction))
            x = a.x + dx * fraction
            y = a.y + dy * fraction
            length = math.sqrt(length_sq)
            alignment = abs((dx / length) * expected_tangent[0]
                            + (dy / length) * expected_tangent[1])
            distance = math.hypot(x - expected[0], y - expected[1])
            if alignment >= 1.0 - 1e-5 and distance <= 1e-4:
                candidates.append((distance, edge, fraction, x, y, length))
        if not candidates:
            return None
        _distance, edge, fraction, x, y, length = min(candidates)
        tangent = expected_tangent
        inward = (-expected_outward[0], -expected_outward[1])
    else:
        x = (rect[0] + rect[2]) / 2.0
        candidates = []
        for edge, (a, c) in enumerate(
                zip(level.plate, level.plate[1:] + level.plate[:1])):
            if abs(c.x - a.x) <= GEOMETRY_EPS_M:
                continue
            fraction = (x - a.x) / (c.x - a.x)
            if 0.0 <= fraction <= 1.0:
                candidates.append((a.y + fraction * (c.y - a.y), edge, fraction))
        if not candidates:
            return None
        y, edge, fraction = min(candidates)
        a, c = level.plate[edge], level.plate[(edge + 1) % len(level.plate)]
        length = math.hypot(c.x - a.x, c.y - a.y)
        tangent = ((c.x - a.x) / length, (c.y - a.y) / length)
        winding = sum(p.x * q.y - q.x * p.y
                      for p, q in zip(level.plate, level.plate[1:] + level.plate[:1]))
        sign = -1.0 if winding < 0.0 else 1.0
        inward = (-tangent[1] * sign, tangent[0] * sign)

    width = ENTRANCE_MIN_WIDTH_M
    if min(fraction, 1.0 - fraction) * length < width / 2.0:
        return None

    def region(half_width, low, high):
        return Polygon([(x + tangent[0] * u + inward[0] * v,
                         y + tangent[1] * u + inward[1] * v)
                        for u, v in ((-half_width, low), (half_width, low),
                                     (half_width, high), (-half_width, high))])

    depth = ENTRANCE_REVEAL_DEPTH_M / 2.0
    half_width = max(width, APPROACH_WIDTH_M) / 2.0
    return EntrancePlan(level.id, level.z, (x, y), width, edge, fraction,
        tangent, inward, region(width / 2.0, -depth, depth),
        region(half_width, depth, depth + APPROACH_DEPTH_M),
        region(half_width, -depth - APPROACH_DEPTH_M, -depth))


def registered_bays(plate, module, minimum_span=0.0, *, stagger=False):
    """Divide each real edge, retaining corners and distributing every remainder.

    Global arclength stations joined across a corner leave a triangular hole. Deleting
    their short final bay leaves a second hole. An edge owns its complete interval;
    if even one opening cannot fit, the emitter supplies a declared solid closure.
    """
    result = []
    for edge, (a, c) in enumerate(zip(plate, plate[1:] + plate[:1])):
        length = math.hypot(c.x - a.x, c.y - a.y)
        if length <= GEOMETRY_EPS_M:
            continue
        count = max(1, round(length / module))
        if minimum_span > 0.0:
            count = min(count, max(1, int(length / minimum_span)))
        fractions = [i / count for i in range(count + 1)]
        if stagger and count > 1:
            # Stagger the joints inside this edge; its end panels still reach both
            # corners. Moving an entire panel by half a bay opens the first corner.
            fractions = [0.0] + [(i + 0.5) / count for i in range(count)] + [1.0]
        for lo, hi in zip(fractions, fractions[1:]):
            result.append((edge, lo, hi))
    return result


def _point_on_edge(plate, edge, fraction):
    a, c = plate[edge], plate[(edge + 1) % len(plate)]
    return v2(a.x + (c.x - a.x) * fraction, a.y + (c.y - a.y) * fraction)


def _parallel_boundary_station(boundary, center, tangent):
    """Locate an entrance again after a true polygon offset changed edge indices.

    Shapely is allowed to remove collinear vertices while offsetting a concave plate,
    so an edge number from the source ring is not an edge number on the outboard ring.
    The threshold still has a physical centre and tangent.  Projecting those onto the
    closest parallel outboard segment preserves that architectural datum without
    relying on polygon serialization order.
    """
    tx, ty = tangent
    candidates = []
    for edge, (a, c) in enumerate(zip(boundary, boundary[1:] + boundary[:1])):
        dx, dy = c.x - a.x, c.y - a.y
        length = math.hypot(dx, dy)
        if length <= GEOMETRY_EPS_M:
            continue
        ux, uy = dx / length, dy / length
        alignment = abs(ux * tx + uy * ty)
        if alignment < 0.95:
            continue
        raw = ((center[0] - a.x) * dx
               + (center[1] - a.y) * dy) / (length * length)
        fraction = min(1.0, max(0.0, raw))
        x = a.x + dx * fraction
        y = a.y + dy * fraction
        distance = math.hypot(x - center[0], y - center[1])
        candidates.append((distance + (1.0 - alignment) * length,
                           edge, fraction))
    if not candidates:
        raise ValueError('the entrance tangent has no parallel outboard facade edge')
    _distance, edge, fraction = min(candidates)
    return edge, fraction


def entrance_frontage_interval(boundary, center, tangent, clear_width, jamb_width):
    """Capacity at the named station on an actual ring, without relocating it.

    Both volume authoring and facade registration measure the nearest parallel
    face. A short face cannot redirect the doorway to another part of the building.
    """
    edge, fraction = _parallel_boundary_station(boundary, center, tangent)
    a,c = boundary[edge],boundary[(edge+1)%len(boundary)]
    length = math.hypot(c.x-a.x,c.y-a.y)
    half = (clear_width/2+jamb_width)/length
    low,high = fraction-half,fraction+half
    epsilon = GEOMETRY_EPS_M/length
    return (edge,max(0.,low),min(1.,high)) if low >= -epsilon and high <= 1.+epsilon else None


def _project_to_skin(skin_boundary, point):
    """Project an outboard panel station back to the authoritative plate edge."""
    projected = nearest_points(skin_boundary, Point(point.x, point.y))[0]
    return v2(float(projected.x), float(projected.y))


def _register_entrance(spans, plate, outboard, entrance, module, minimum_span,
                       jamb_width, *, force_remapped=False):
    """Re-module the entry edge around one full opening and two solid jambs."""
    source = Polygon([(point.x, point.y) for point in plate])
    remapped = force_remapped or not source.equals(source.convex_hull)
    if remapped:
        interval = entrance_frontage_interval(outboard,entrance.center,entrance.tangent,
                                              entrance.width_m,jamb_width)
        if interval is None:
            return spans,None
        edge,low,high = interval
    else:
        edge, fraction = entrance.edge, entrance.fraction
        a, c = plate[edge], plate[(edge + 1) % len(plate)]
        half = (entrance.width_m / 2.0 + jamb_width) / math.hypot(c.x-a.x, c.y-a.y)
        low, high = fraction - half, fraction + half
        if low < 0.0 or high > 1.0:
            return spans, None
    p, q = outboard[edge], outboard[(edge + 1) % len(outboard)]
    length = math.hypot(q.x-p.x, q.y-p.y)
    replacement = []
    for lo, hi in ((0.0, low), (high, 1.0)):
        if hi - lo <= GEOMETRY_EPS_M:
            continue
        span = (hi - lo) * length
        count = max(1, min(round(span/module), int(span/minimum_span)))
        replacement.extend((edge, lo + (hi-lo)*i/count, lo + (hi-lo)*(i+1)/count)
                           for i in range(count))
    entry_span = (edge, low, high)
    return sorted([item for item in spans if item[0] != edge]
                  + replacement + [entry_span]), entry_span


def _slabs(b, level_id):
    return [(instance.id, instance.geometry) for group in b.groups.values()
            if group.kind == 'floor_slab' for instance in group.instances
            if instance.level_id == level_id
            and isinstance(instance.geometry, ExtrusionGeometry)]


def _closure_surfaces(b, level):
    """Actual slabs and registered caps that end at this interface datum."""
    return _slabs(b,level.id) + [
        (instance.id,instance.geometry) for group in b.groups.values()
        if group.kind == 'roof_deck' for instance in group.instances
        if isinstance(instance.geometry,ExtrusionGeometry)
        and abs(instance.geometry.z_top-level.z) <= GEOMETRY_EPS_M]


def _solid_surface_views(geometry, profiles):
    """Plan/z views of real roof solids for the existing return-bearing solver."""
    if isinstance(geometry, ExtrusionGeometry):
        return [geometry]
    from .physical_geometry import physical_projection
    projection = physical_projection(geometry, profiles)
    parts = ([projection.footprint] if projection.footprint.geom_type == 'Polygon'
             else projection.footprint.geoms)
    return [ExtrusionGeometry(
        boundary=_ring(part.exterior.coords),
        holes=[_ring(ring.coords) for ring in part.interiors],
        z_base=projection.z_bottom, z_top=projection.z_top)
        for part in parts if not part.is_empty]


def _roof_interface_surfaces(b, z):
    """Only emitted roof substrate/frame/coping may support the added facade band."""
    return [(instance.id, surface) for group in b.groups.values()
            for instance in group.instances
            if _roof_return_host(group, instance)
            for surface in _solid_surface_views(instance.geometry, b.profiles)
            if surface.z_base-GEOMETRY_EPS_M <= z <= surface.z_top+GEOMETRY_EPS_M]


def _roof_return_host(group, instance):
    return (group.subsystem == 'roof_closure'
            or (group.subsystem == 'roof' and instance.part_role in {
                'coping', 'parapet_substrate'}))


def _slab_region(geometry):
    return polygon(geometry.boundary).difference(
        unary_union([polygon(hole) for hole in geometry.holes]))


def _surface_polygon(exterior, holes=()):
    """Build a plan surface while retaining every declared courtyard ring.

    FacadeControl carries the weather plane as an exterior ring plus holes.  The
    older return emitter converted that pair to ``polygon(exterior)`` at several
    seams, which silently capped a courtyard as soon as the return was split into
    panels.  Keep this conversion in one small adapter so every collar operation
    uses the same physical surface.
    """
    def xy(point):
        return (float(point.x), float(point.y)) if hasattr(point, 'x') else (
            float(point[0]), float(point[1]))

    return Polygon([xy(point) for point in exterior],
                   holes=[[xy(point) for point in ring] for ring in holes])


def _skin_base_hosts(b, bay, *, authoritative_skin=False):
    a, c = ((bay.skin_point, bay.skin_nxt) if authoritative_skin
            else (bay.point, bay.nxt))
    line = LineString([(a.x, a.y), (c.x, c.y)])
    result = []
    for group in b.groups.values():
        if group.kind != 'floor_slab' and group.subsystem != 'edge_closure':
            continue
        for instance in group.instances:
            geometry = instance.geometry
            if (not isinstance(geometry, ExtrusionGeometry)
                    or not (geometry.z_base <= bay.z_base <= geometry.z_top)):
                continue
            if _slab_region(geometry).distance(line) <= GEOMETRY_EPS_M:
                result.append(instance.id)
    return result


def _nearest_slab_anchor(b, level_id: str, point, z: float):
    """Return the nearest point on actual slab material at the interface height.

    A Program Volume edge may pass a stair/hall notch, so the facade station itself is
    not always slab material. The bracket must then show the route to the nearest real
    slab piece; naming the nominal level slab while leaving a geometric gap would make
    the interface look resolved when it is not.
    """
    probe = Point(point.x, point.y)
    candidates = []
    for ident, geometry in _slabs(b, level_id):
        if not (geometry.z_base - GEOMETRY_EPS_M
                <= z <= geometry.z_top + GEOMETRY_EPS_M):
            continue
        material = _slab_region(geometry)
        if material.is_empty:
            continue
        anchor = nearest_points(material, probe)[0]
        candidates.append((anchor.distance(probe), ident, geometry,
                           v2(float(anchor.x), float(anchor.y))))
    return min(candidates, key=lambda item: item[0]) if candidates else None


def _member_path(*points: Vector3) -> list[Vector3]:
    """Remove consecutive coincident nodes before a polyline becomes a member."""
    clean: list[Vector3] = []
    for point in points:
        if (not clean or math.dist(
                (clean[-1].x, clean[-1].y, clean[-1].z),
                (point.x, point.y, point.z)) > GEOMETRY_EPS_M):
            clean.append(point)
    return clean


def _visible_bearing_anchor(bearing, probe, *, domain=None, blocked=None):
    """Choose a visible bearing station without discarding a whole concave slab.

    Try the nearest point first. If that route is occluded, register candidates at
    each real edge's perpendicular projection and ends, then choose the shortest
    legal route among those stations. This is a finite geometric station search,
    not a cantilever capacity check or a continuous visibility optimisation.
    """
    def visible(anchor):
        line = LineString([anchor, probe])
        return ((domain is None or domain.covers(line))
                and (blocked is None
                     or line.intersection(blocked).length <= GEOMETRY_EPS_M))

    closest = nearest_points(bearing, probe)[0]
    if visible(closest):
        return closest
    candidates = {}
    parts = [bearing] if bearing.geom_type == 'Polygon' else bearing.geoms
    for part in parts:
        for ring in (part.exterior, *part.interiors):
            coordinates = list(ring.coords)
            for start, end in zip(coordinates, coordinates[1:]):
                edge = LineString([start, end])
                for anchor in (Point(start), nearest_points(edge, probe)[0]):
                    candidates[(anchor.x, anchor.y)] = anchor
    for anchor in sorted(candidates.values(),
                         key=lambda p: (p.distance(probe), p.x, p.y)):
        if visible(anchor):
            return anchor
    return None


def closure_solid_bearings(b):
    """Measured closure terminals on solids, which have no member centre-line.

    An actual member endpoint must meet the declared slab polygon minus every hole,
    inside its actual vertical interval. A nearby slab's bounding box is insufficient.
    This does not introduce a fictitious slab axis or verify attachment strength.
    """
    records = {instance.id: (group, instance) for group in b.groups.values()
               for instance in group.instances}
    connected, failed = set(), set()
    for ident, (group, instance) in records.items():
        if (group.subsystem, group.kind) not in {
                ('edge_closure', 'external_strut'), ('roof_closure', 'truss_web'),
                ('entrance', 'external_strut')}:
            continue
        member = instance.geometry
        if not isinstance(member, MemberGeometry):
            continue
        meets = False
        for host_id in instance.supports:
            host = records.get(host_id)
            if not host or (host[0].kind not in {'floor_slab','roof_deck'}
                            and not _roof_return_host(*host)):
                continue
            if any(slab.z_base-GEOMETRY_EPS_M <= endpoint.z <= slab.z_top+GEOMETRY_EPS_M
                   and _slab_region(slab).distance(Point(endpoint.x, endpoint.y)) <= GEOMETRY_EPS_M
                   for slab in _solid_surface_views(host[1].geometry, b.profiles)
                   for endpoint in (member.path[0], member.path[-1])):
                meets = True
                break
        (connected if meets else failed).add(ident)
    return connected, failed


def _registered_return_solids(region, z_base, z_top):
    """Register return pieces at model precision, refusing real polygon defects."""
    if not region.is_valid:
        raise ValueError('Invalid facade return region before coordinate registration')
    # Register topology at the same 10 µm resolution as its vertices. Rounding
    # vertices alone turns arithmetic hairpins into self-crossing rings. This is
    # fixed precision registration, not a buffer repair of invalid source geometry.
    region = set_precision(region,GEOMETRY_EPS_M)
    solids = []
    for part in _simple_parts(region):
        geometry = ExtrusionGeometry(
            boundary=_ring(part.exterior.coords),
            holes=[_ring(interior.coords) for interior in part.interiors],
            z_base=z_base, z_top=z_top)
        registered = _surface_polygon(geometry.boundary, geometry.holes)
        if not registered.is_valid:
            # Opening a hole can isolate a <10-micrometre strip at its split line.
            # A zero-area registered strip has no representable solid. Discard only
            # that below-resolution degeneracy; do not fill or repair other defects.
            if registered.area == 0.0 and part.buffer(-GEOMETRY_EPS_M / 2).is_empty:
                continue
            raise ValueError('Facade return polygon invalid after coordinate registration')
        solids.append(geometry)
    return solids


def _direct_return_hosts(geometry, surfaces, reach):
    """A short return can fasten along an actual slab/cap edge without a strut.

    Require a shared vertical face and keep the entire panel within the declared
    collar reach of those hosts. A remote touching corner or one end of a long
    unsupported return cannot certify the panel. Fixing capacity remains unchecked.
    """
    footprint = _surface_polygon(geometry.boundary,geometry.holes)
    touching = [(ident,region) for ident,solid,region in surfaces
        if min(geometry.z_top,solid.z_top)-max(geometry.z_base,solid.z_base) > GEOMETRY_EPS_M
        and footprint.boundary.intersection(region.boundary).length > GEOMETRY_EPS_M]
    if not touching:
        return []
    supported = unary_union([region for _,region in touching]).buffer(reach,join_style=2)
    return ([ident for ident,_ in touching] if
            footprint.difference(supported.buffer(GEOMETRY_EPS_M)).area <= GEOMETRY_EPS_M**2 else [])


def _emit_level_returns(b, level, upper, skin, stations, env, *, high_tech=False,
                        weather_voids=()):
    """Close only the edge difference, with brackets touching actual slab pieces.

    The top return joins a stepped/turned slab soffit to the facade head; the bottom
    return joins the floor edge to its offset skin. Neither fills internal slab holes.
    Every panel and bracket names a contacting host instead of a nominal slab ID.
    """
    roof_band = upper is None
    lower_slabs = _closure_surfaces(b, level)
    if roof_band:
        head = b.lattice.roof_control.physical_top_z
        lower_slabs += _roof_interface_surfaces(b, level.z)
        upper_slabs = _roof_interface_surfaces(b, head)
        upper = level  # same roof boundary, with no invented upper floor
    else:
        upper_slabs = _closure_surfaces(b, upper)
        head = min((g.z_base for _, g in upper_slabs), default=upper.z)
    refs = ['envelope_offset_m', 'slab_thickness_m', *PLATE_DATUMS]
    # Keep the controlled weather ring as a polygon-with-holes for every collar
    # operation below. A courtyard is a real absence of enclosure, including at
    # the horizontal return; it must not become a solid panel during decomposition.
    skin_shape = _surface_polygon(skin, weather_voids)
    controlled = getattr(b.lattice, 'facade_control', None) is not None
    for tag, host_level, host_slabs, z0, z1 in (
            ('BASE', level, lower_slabs, level.z - EDGE_RETURN_THICKNESS_M, level.z),
            ('HEAD', upper, upper_slabs,
             head-EDGE_RETURN_THICKNESS_M if roof_band else head,
             head if roof_band else head+EDGE_RETURN_THICKNESS_M)):
        host_shape = _surface_polygon(
            host_level.plate,
            getattr(host_level, 'voids', ()) if controlled else ())
        if controlled:
            # Boundary intent and actual bearing are distinct. Missing slab pieces
            # must not turn their whole nominal floor into a facade return. Real
            # caps can complete this boundary; anchors still use actual solids only.
            host_shape = host_shape.union(unary_union([_slab_region(g) for _,g in host_slabs]))
        region = skin_shape.difference(host_shape)
        if controlled and tag == 'HEAD':
            # An upper-level authored opening is absent by intent, not an edge
            # setback to close. Subtracting a polygon-with-holes from the lower
            # weather region otherwise manufactures a panel inside each hole.
            host_control = next((item for item in
                getattr(b.lattice.facade_control, 'levels', ())
                if item.level_id == host_level.id), None)
            source_voids = host_control.source_voids if host_control is not None else ()
            upper_openings = unary_union([
                _surface_polygon(ring) for ring in
                [*getattr(host_level, 'voids', ()), *source_voids]])
            region = region.difference(upper_openings)
        hall = getattr(b, 'hall_geometry', None)
        blocked = None
        approach = getattr(b, 'approach', {})
        if tag == 'BASE' and approach.get('podium_id') == level.id:
            # The entry, accessible arrival and ramp landing are intentional breaks
            # through the horizontal edge return.  A bracket crossing either stair's
            # last treads leaves only centimetres of headroom even when the vertical
            # facade opening is correct. Remove the real walking footprints from both
            # the closure sheet and its possible bearing/path domain.
            approach_rects = [rect for rect in (
                approach.get('entry'), approach.get('access'),
                approach.get('ramp_top')) if rect is not None]
            if approach_rects:
                approach_clear = unary_union([box(*rect) for rect in approach_rects])
                region = region.difference(approach_clear)
                bracket = b.profiles[EDGE_BRACKET_PROFILE]
                blocked = approach_clear.buffer(
                    max(bracket.width_m, bracket.depth_m) / 2.0,
                    join_style=2)
        # Gross-envelope airspace is not missing floor to be filled by a return.
        # Read the host storey's authored clearance for both BASE and HEAD; the
        # ground room reservation alone cannot describe consecutive tall storeys.
        claims = [item.resolve_bounds(b.lattice)
                  for item in b.lattice.program_volume_regions
                  if item.level_id == host_level.id and item.role == 'sectional_clearance']
        if tag == 'HEAD':
            claims += list(getattr(b.lattice, 'carved', {}).get(level.index, ()))
        if claims:
            carve_clear = unary_union([box(*rect) for rect in claims])
            if controlled:
                # A real slab/cap terminates this airspace at the interface. The
                # lower storey's clear-volume label cannot erase that bearing.
                carve_clear = carve_clear.difference(host_shape)
            # Separate panel edges by geometry tolerance and bracket paths by their
            # actual half-section so neither solid intrudes into the clear volume.
            region = region.difference(carve_clear.buffer(GEOMETRY_EPS_M, join_style=2))
            profile = b.profiles[EDGE_BRACKET_PROFILE]
            carve_blocked = carve_clear.buffer(
                max(profile.width_m, profile.depth_m) / 2.0, join_style=2)
            blocked = (carve_blocked if blocked is None
                       else unary_union([blocked, carve_blocked]))
        if tag == 'HEAD' and hall is not None and z0 < hall.clear_top_z:
            # The emitted tall walls and their registered cap now enclose this
            # volume. An old low return must not cut across it to reach a remote
            # slab. Remove its exterior skin collar too, without taking ordinary
            # floor-side returns on the public side of an internal hall wall.
            plate = _surface_polygon(
                level.plate, getattr(level, 'voids', ()) if controlled else ())
            collar_depth = skin_shape.boundary.hausdorff_distance(plate.boundary)
            exterior_collar = skin_shape.difference(plate).intersection(
                hall.footprint.buffer(collar_depth + GEOMETRY_EPS_M, join_style=2))
            caps = [_slab_region(item.geometry) for group in b.groups.values()
                    if group.kind in {'floor_slab','roof_deck'} for item in group.instances
                    if isinstance(item.geometry,ExtrusionGeometry)
                    and abs(item.geometry.z_base-hall.roof_bottom_z) <= GEOMETRY_EPS_M]
            if unary_union(caps).buffer(GEOMETRY_EPS_M).covers(hall.footprint):
                region = region.difference(hall.footprint.union(exterior_collar))
            profile = b.profiles[EDGE_BRACKET_PROFILE]
            hall_blocked = hall.footprint.buffer(
                max(profile.width_m, profile.depth_m) / 2, join_style=2)
            blocked = (hall_blocked if blocked is None
                       else unary_union([blocked, hall_blocked]))
        if region.is_empty or region.area <= GEOMETRY_EPS_M ** 2:
            continue
        bracket_records = []
        concealed = controlled and not high_tech
        # A setback collar is exposed from above as well as below. Represent its
        # complete conceptual enclosure depth, registered to the real upper floor,
        # rather than leaving a soffit-only sheet below visible support brackets.
        # This is an assembly envelope, not a homogeneous construction build-up.
        enclosure_top = upper.z if concealed and tag == 'HEAD' and not roof_band else z1
        pieces = _registered_return_solids(region, z0, enclosure_top)
        bracket_depth = b.profiles[EDGE_BRACKET_PROFILE].depth_m
        bracket_z = (z1 + bracket_depth / 2.0
                     if tag == 'HEAD' and not roof_band
                     else z0 - bracket_depth / 2.0)
        bearing_slabs = ([*host_slabs, *_roof_interface_surfaces(b, bracket_z)]
                         if concealed and roof_band else host_slabs)
        surfaces = [(ident, geom, _slab_region(geom)) for ident, geom in bearing_slabs]
        return_domain = skin_shape.union(host_shape).buffer(GEOMETRY_EPS_M)
        # One bracket at every panel joint, anchored to the actual slab material.
        for si, point in enumerate(stations):
            if not b.lattice.encloses(point.x, point.y):
                continue
            probe = Point(point.x, point.y)
            if not surfaces or region.distance(probe) > GEOMETRY_EPS_M:
                continue
            anchors = []
            for host_id, host_geom, host_region in surfaces:
                if concealed and not (host_geom.z_base-GEOMETRY_EPS_M <= bracket_z
                                      <= host_geom.z_top+GEOMETRY_EPS_M):
                    continue
                bearing = host_region.difference(blocked) if blocked is not None else host_region
                if bearing.is_empty:
                    continue
                anchor = _visible_bearing_anchor(
                    bearing, probe, domain=return_domain if controlled else None,
                    blocked=blocked)
                if anchor is None:
                    # Refuse this slab only after checking its other real edges.
                    # Unresolved closure geometry keeps the missing-support marker.
                    continue
                anchors.append((anchor.distance(probe),host_id,host_geom,anchor))
            if not anchors:
                continue
            _,host_id,host_geom,anchor = min(anchors,key=lambda item:item[0])
            if anchor.distance(probe) <= GEOMETRY_EPS_M:
                continue
            bracket_id = f'ENV-RET-{level.id}-{tag}-S{si:03d}'
            special_assembly = f'HTS-{level.id}-EDGE-{tag}' if high_tech else None
            # The base return is a floor surface. Its support must finish at the
            # panel underside: centring a 140 mm bracket in a 75 mm panel raised
            # the real section 32.5 mm through entrance thresholds and approaches.
            # Head brackets remain embedded at the actual upper slab edge.
            z = (z0 - bracket_depth / 2.0 if tag == 'BASE' and not roof_band else
                 min(host_geom.z_top, max(host_geom.z_base, (z0 + z1) / 2.0)))
            if concealed:
                # Keep the whole section behind the finish surface. A centre-line
                # at the finish datum exposes half the member above/below it.
                attachment_z = ((head + bracket_depth / 2.0)
                                if tag == 'HEAD' and not roof_band
                                else (head if tag == 'HEAD' else level.z)
                                - bracket_depth / 2.0)
                path = [v3(anchor.x, anchor.y, bracket_z),
                        v3(point.x, point.y, attachment_z)]
            elif controlled:
                # The controlled bracket's weather end turns vertically into the
                # mullion datum. Its final node is exactly at the base/head z of the
                # facade member, which makes slab -> return -> mullion measurable in
                # section. Legacy emitters retain their historical below-floor edge
                # return geometry.
                mullion_z = level.z if tag == 'BASE' else head
                path = _member_path(
                    v3(anchor.x, anchor.y, z),
                    v3(point.x, point.y, z),
                    v3(point.x, point.y, mullion_z))
                if abs(mullion_z-z) <= bracket_depth:
                    # A turn shorter than its section depth folds the station
                    # rings through one another. Use one direct tie between the
                    # same registered slab anchor and mullion attachment instead.
                    # This remains a conceptual connection, not a bend detail.
                    path = [path[0], path[-1]]
            else:
                path = [v3(anchor.x, anchor.y, z), v3(point.x, point.y, z)]
            b.add(bracket_id, 'external_strut', 'envelope', 'edge_closure',
                  MemberGeometry(path=path, profile=EDGE_BRACKET_PROFILE),
                  env.trim_material, level_id=level.id,
                  lattice_index={'level': level.index, 'station': si}, datum_refs=refs,
                  supports=[host_id], assembly_id=special_assembly,
                  part_role='support' if high_tech else None,
                  rule_refs=['ENVELOPE-EDGE-RETURN'] + (
                      ['HT-INV-01', 'HT-INV-03', 'HT-INV-04',
                       'HT-STANDARD-COMPONENT'] if high_tech else []),
                  reason='Conceptual enclosure bracket from the actual slab piece to '
                         'the skin edge. Connection and cantilever capacity are not checked.')
            bracket_records.append((bracket_id, LineString([(p.x, p.y) for p in path])))
        for pi, geometry in enumerate(pieces):
            footprint = _surface_polygon(geometry.boundary, geometry.holes)
            hosts = [ident for ident, line in bracket_records if footprint.intersects(line)]
            direct_hosts = []
            if controlled and not hosts:
                reach = getattr(b.lattice.facade_control,'resolved_offset_m',
                    abs(b.datums.value('envelope_offset_m')*env.setback_multiplier))
                direct_hosts = _direct_return_hosts(geometry,surfaces,reach)
                hosts.extend(direct_hosts)
            # A diagnostic cut removes the same outside faces as the original skin.
            centre = footprint.representative_point()
            if not b.lattice.encloses(centre.x, centre.y):
                continue
            b.add(f'ENV-RET-{level.id}-{tag}-P{pi:03d}', 'spandrel_panel',
                  'envelope', 'edge_closure', geometry, env.trim_material,
                  level_id=level.id, lattice_index={'level': level.index, 'piece': pi},
                  datum_refs=refs, supports=hosts,
                  assembly_id=(f'HTS-{level.id}-EDGE-{tag}' if high_tech else None),
                  part_role='enclosure' if high_tech else None,
                  rule_refs=['ENVELOPE-EDGE-RETURN'] + (
                      ['ENVELOPE-RETURN-DIRECT-EDGE'] if direct_hosts else []) + (
                      [] if hosts else ['ENVELOPE-CLOSURE-UNRESOLVED-SUPPORT']) + (
                      ['HT-INV-01', 'HT-INV-03', 'HT-INV-04',
                       'HT-STANDARD-COMPONENT'] if high_tech else []),
                  reason='Conceptual floor-edge return closes the measured difference '
                         'between skin and slab boundary. Internal slab openings remain '
                         'open; waterproofing and attachment design are not evaluated.' + (
                         ' Full-depth assembly envelope reaches the upper floor datum; '
                         'internal layers and cavities are not resolved.'
                         if enclosure_top != z1 else '') + (
                         ' Direct edge attachment is measured along a shared slab/cap face; '
                         'the entire panel remains within the declared collar reach.' if direct_hosts else ''))
    return head


class _Bay:
    """One module of elevation, and everything an emitter needs to place it."""

    __slots__ = ('point', 'nxt', 'z_base', 'z_head', 'angle', 'roll', 'index',
                 'level_id', 'si', 'is_principal', 'normal_sign', 'skin_point', 'skin_nxt')

    def __init__(self, point, nxt, z_base, z_head, angle, index, level_id, si,
                 is_principal, *, normal_sign=-1.0, skin_point=None, skin_nxt=None):
        self.point, self.nxt = point, nxt
        self.z_base, self.z_head = z_base, z_head
        self.angle = angle
        self.roll = v3(math.cos(angle), math.sin(angle), 0.0)
        self.index, self.level_id, self.si = index, level_id, si
        self.is_principal = is_principal
        self.normal_sign = normal_sign
        self.skin_point = skin_point if skin_point is not None else point
        self.skin_nxt = skin_nxt if skin_nxt is not None else nxt

    @property
    def width(self) -> float:
        return math.hypot(self.nxt.x - self.point.x, self.nxt.y - self.point.y)

    @property
    def height(self) -> float:
        return self.z_head - self.z_base

    def at(self, t: float, z: float, *, skin=False) -> Vector3:
        """A point across the bay, `t` from 0 at `point` to 1 at `nxt`."""
        a, c = (self.skin_point, self.skin_nxt) if skin else (self.point, self.nxt)
        return v3(a.x + (c.x - a.x) * t, a.y + (c.y - a.y) * t, z)

    def outward(self, distance: float) -> tuple[float, float]:
        """An offset normal to the bay, pointing away from the building."""
        return (math.cos(self.angle + math.pi / 2.0) * self.normal_sign * distance,
                math.sin(self.angle + math.pi / 2.0) * self.normal_sign * distance)

    def quad(self, t0: float, t1: float, z0: float, z1: float,
             push: float = 0.0, *, skin=False) -> QuadGeometry:
        dx, dy = self.outward(push) if push else (0.0, 0.0)
        a, bb = self.at(t0, z0, skin=skin), self.at(t1, z0, skin=skin)
        return QuadGeometry(corners=(
            v3(a.x + dx, a.y + dy, z0), v3(bb.x + dx, bb.y + dy, z0),
            v3(bb.x + dx, bb.y + dy, z1), v3(a.x + dx, a.y + dy, z1)))


@dataclass(frozen=True)
class _BayProgram:
    """The programme immediately behind one facade bay.

    Program Volumes are the first authority.  The detailed allocation is a compatible
    fallback for older/non-volume runs.  A final explicit fallback keeps legacy test
    builders usable while making the missing upstream contract visible in the element
    reason rather than silently inventing a room.
    """

    category: str
    program: str
    source: str


def _field(record, name, default=None):
    return record.get(name, default) if isinstance(record, dict) else getattr(
        record, name, default)


def _xy(point) -> tuple[float, float]:
    if isinstance(point, dict):
        return float(point['x']), float(point['y'])
    if hasattr(point, 'x'):
        return float(point.x), float(point.y)
    return float(point[0]), float(point[1])


def _region_shape(record, lattice, *, volume_model=None) -> Polygon | None:
    """Read a Program Volume/allocation region without coupling to either schema.

    The Program Volume bridge may carry a polygon, a physical rectangle, or the source
    grid rectangle.  Supporting all three keeps the facade contract portable while the
    root compiler wires the semantic regions into the lattice.
    """
    boundary = _field(record, 'boundary')
    if boundary:
        try:
            return Polygon([_xy(point) for point in boundary])
        except (KeyError, TypeError, ValueError):
            return None
    values = tuple(_field(record, name) for name in ('x0', 'y0', 'x1', 'y1'))
    if all(value is not None for value in values):
        x0, y0, x1, y1 = map(float, values)
        return Polygon(((x0, y0), (x1, y0), (x1, y1), (x0, y1)))
    rect = _field(record, 'rect')
    if rect and len(rect) == 4:
        x0, y0, x1, y1 = map(float, rect)
        return Polygon(((x0, y0), (x1, y0), (x1, y1), (x0, y1)))
    grid_rect = _field(record, 'grid_rect')
    grid = _field(volume_model, 'grid') if volume_model is not None else lattice
    if grid_rect and hasattr(grid, 'x_lines') and hasattr(grid, 'y_lines'):
        i0, j0, i1, j1 = map(int, grid_rect)
        # Program Volume rectangles index the authoring grid.  The structural pass
        # later adds core faces to ``lattice.x_lines/y_lines``; reading those mutable
        # arrays here would silently move the programme behind a facade bay.
        x_lines = (getattr(grid, 'program_volume_x_lines', None)
                   or grid.x_lines)
        y_lines = (getattr(grid, 'program_volume_y_lines', None)
                   or grid.y_lines)
        return Polygon(((x_lines[i0], y_lines[j0]),
                        (x_lines[i1], y_lines[j0]),
                        (x_lines[i1], y_lines[j1]),
                        (x_lines[i0], y_lines[j1])))
    return None


def _bay_program(b, bay: _Bay, fraction: float = 0.5) -> _BayProgram:
    """Resolve the closest declared programme on the inside face of a bay."""
    mid = bay.at(fraction, (bay.z_base + bay.z_head) / 2.0, skin=True)
    dx, dy = bay.outward(-0.60)
    probe = Point(mid.x + dx, mid.y + dy)
    volume_model = getattr(b, 'program_volume_model', None)
    sources = (
        ('program_volume', getattr(b.lattice, 'program_volume_regions', ()), None),
        ('program_volume', getattr(b, 'program_volume_regions', ()), None),
        ('program_volume', getattr(volume_model, 'volumes', ()), volume_model),
        ('program_allocation', getattr(getattr(b, 'program_allocation', None),
                                       'zones', ()), None),
    )
    candidates = []
    for source, records, owner in sources:
        for record in records or ():
            if _field(record, 'level_id') != bay.level_id:
                continue
            if source == 'program_volume':
                # A level id alone is insufficient evidence: stacked Program Volumes
                # may deliberately share it.  Resolve the facade submodule in 3D so
                # list order cannot assign a panel to a volume above or below it.
                z_base = _field(record, 'z_base')
                z_top = _field(record, 'z_top')
                try:
                    covers_height = (z_base is not None and z_top is not None
                                     and float(z_base) - 1.0e-5 <= mid.z
                                     <= float(z_top) + 1.0e-5)
                except (TypeError, ValueError):
                    covers_height = False
                if not covers_height:
                    continue
            shape = _region_shape(record, b.lattice, volume_model=owner)
            category = _field(record, 'category')
            if shape is None or shape.is_empty or category not in {
                    'public', 'private', 'circulation', 'service'}:
                continue
            space_ids = _field(record, 'space_ids', ()) or ()
            program = (_field(record, 'space_id') or _field(record, 'program')
                       or (space_ids[0] if space_ids else None) or category)
            # A covering Program Volume always wins.  Distance resolves a boundary
            # shared by two rooms and also lets an allocation set back from the skin
            # describe the facade bay it serves.
            distance = 0.0 if shape.covers(probe) else shape.distance(probe)
            candidates.append((0 if shape.covers(probe) else 1, distance,
                               0 if source == 'program_volume' else 1,
                               _BayProgram(category, str(program), source)))
        if candidates and any(item[0] == 0 and item[2] == 0 for item in candidates):
            break
    if candidates:
        return min(candidates, key=lambda item: item[:3])[3]
    return _BayProgram(
        'public', 'unassigned_facade_program', 'explicit_fallback:no_program_region')


def _high_tech_assembly_id(bay: _Bay, *, special: str | None = None) -> str:
    prefix = 'HTS' if special else 'HTA'
    suffix = f'-{special}' if special else ''
    return f'{prefix}-{bay.level_id}-S{bay.si:03d}{suffix}'


def _high_tech_edge_target(plate, edge: int, datums, spec: GrammarSpec) -> float:
    """Read the structural datum aligned with one facade edge."""
    low, high = spec.primary_assembly_bay_range_m or (3.0, 9.0)
    a, c = plate[edge], plate[(edge + 1) % len(plate)]
    datum_id = 'bay_x_m' if abs(c.x - a.x) >= abs(c.y - a.y) else 'bay_y_m'
    try:
        target = float(datums.value(datum_id))
    except (AttributeError, KeyError):
        target = low
    return min(high, max(low, target))


def _high_tech_registered_bays(plate, datums, spec: GrammarSpec):
    """Divide the authoritative Program Volume skin by its structural bay datums.

    The primary grid is chosen first.  Enclosure modules are derived inside each
    realised span later, so a 1.2 m panel cannot pull a 7.0 m structural bay off its
    datum.  Width bounds constrain the integer bay count on each complete edge.
    """
    low, high = spec.primary_assembly_bay_range_m or (3.0, 9.0)
    result = []
    for edge, (a, c) in enumerate(zip(plate, plate[1:] + plate[:1])):
        length = math.hypot(c.x - a.x, c.y - a.y)
        if length <= GEOMETRY_EPS_M:
            continue
        target = _high_tech_edge_target(plate, edge, datums, spec)
        minimum_count = max(1, math.ceil(length / high - GEOMETRY_EPS_M))
        maximum_count = max(1, math.floor(length / low + GEOMETRY_EPS_M))
        count = max(minimum_count, min(maximum_count, int(round(length / target))))
        result.extend((edge, index / count, (index + 1) / count)
                      for index in range(count))
    return result


def _high_tech_submodules(width_m: float, target_m: float,
                          spec: GrammarSpec) -> list[tuple[float, float]]:
    """Return complete 0..1 cells whose realised widths stay in the guide band."""
    low, high = (spec.enclosure_submodule_range_m or spec.module_range_m)
    minimum_count = max(1, math.ceil(width_m / high - GEOMETRY_EPS_M))
    maximum_count = math.floor(width_m / low + GEOMETRY_EPS_M)
    if minimum_count > maximum_count:
        return []
    count = max(minimum_count, min(maximum_count,
                                  int(round(width_m / target_m))))
    return [(index / count, (index + 1) / count) for index in range(count)]


def _intersection_endpoints(geometry) -> list[Point]:
    """Return stationable endpoints from any Shapely boundary intersection."""
    if geometry.is_empty:
        return []
    if geometry.geom_type == 'Point':
        return [geometry]
    if geometry.geom_type in {'LineString', 'LinearRing'}:
        coords = list(geometry.coords)
        return [Point(coords[0]), Point(coords[-1])] if coords else []
    if hasattr(geometry, 'geoms'):
        return [point for part in geometry.geoms
                for point in _intersection_endpoints(part)]
    return []


def _high_tech_program_submodules(
        b, bay: _Bay, target_m: float,
        spec: GrammarSpec) -> tuple[list[tuple[float, float]], bool, bool]:
    """Split legal enclosure cells at every authored Program Volume boundary.

    A midpoint can label a panel even when half of that panel belongs to another
    programme.  Program boundaries therefore enter the enclosure station set before
    the 0.75-1.80 m submodule count is chosen.  A boundary sliver too short to accept
    one legal module is retained for geometric closure and explicitly marked special;
    its programme gate remains unevaluated until a designer resolves the junction.
    """
    volume_model = getattr(b, 'program_volume_model', None)
    sources = (
        (getattr(b.lattice, 'program_volume_regions', ()), None),
        (getattr(b, 'program_volume_regions', ()), None),
        (getattr(volume_model, 'volumes', ()), volume_model),
    )
    records, owner = next(((records, owner) for records, owner in sources
                           if records), ((), None))
    skin = LineString([(bay.skin_point.x, bay.skin_point.y),
                       (bay.skin_nxt.x, bay.skin_nxt.y)])
    breaks = {0.0, 1.0}
    for record in records:
        if _field(record, 'level_id') != bay.level_id:
            continue
        shape = _region_shape(record, b.lattice, volume_model=owner)
        if shape is None or shape.is_empty:
            continue
        for point in _intersection_endpoints(skin.intersection(shape.boundary)):
            station = skin.project(point, normalized=True)
            if GEOMETRY_EPS_M < station < 1.0 - GEOMETRY_EPS_M:
                breaks.add(round(float(station), 10))

    cells: list[tuple[float, float]] = []
    unresolved = False
    unresolved_at_program_break = False
    ordered = sorted(breaks)
    for start, finish in zip(ordered, ordered[1:]):
        width = bay.width * (finish - start)
        local = _high_tech_submodules(width, target_m, spec)
        if not local:
            cells.append((start, finish))
            unresolved = True
            unresolved_at_program_break = len(ordered) > 2
            continue
        cells.extend((start + (finish - start) * low,
                      start + (finish - start) * high)
                     for low, high in local)
    return cells, unresolved, unresolved_at_program_break


def _high_tech_system_depth(datums, spec: GrammarSpec) -> tuple[float, str, str]:
    """Resolve the exposed-frame to enclosure depth without overstating score reach."""
    low, high = spec.depth_range_m
    try:
        requested = abs(float(datums.value('envelope_offset_m')))
    except (AttributeError, KeyError):
        requested = low
    depth = min(high, max(low, requested))
    if not math.isclose(depth, requested, abs_tol=GEOMETRY_EPS_M):
        return (
            depth,
            'HT-TECTONIC-DEPTH-CLAMP',
            f'The score requested {requested:.3f} m; the High-Tech assembly uses the '
            f'{depth:.3f} m published tectonic limit, so the clipped travel is not '
            'credited as score authority.',
        )
    return (
        depth,
        'POLYPHONY_TO_ENVELOPE_OFFSET',
        f'The {depth:.3f} m score-derived stand-off lies inside the published '
        'High-Tech facade-system interval.',
    )


def _true_outboard_boundary(plate, depth_m: float):
    """A parallel facade boundary whose measured stand-off is the requested depth."""
    source = Polygon([(point.x, point.y) for point in plate])
    shifted = source.buffer(depth_m, join_style=2)
    if shifted.is_empty or shifted.geom_type != 'Polygon':
        raise ValueError('High-Tech facade depth produced no single outboard boundary')
    shifted = orient(shifted, sign=1.0)
    return [v2(round(float(x), 6), round(float(y), 6))
            for x, y in list(shifted.exterior.coords)[:-1]]


def _high_tech_program_refs(use: _BayProgram) -> list[str]:
    if use.source == 'program_volume':
        return ['PROGRAM_VOLUME_TO_FACADE']
    if use.source == 'program_allocation':
        return ['PROGRAM_ALLOCATION_TO_FACADE']
    return ['FACADE_PROGRAM_FALLBACK_UNEVALUATED']


def _high_tech_secondary_count(datums, spec: GrammarSpec | None) -> int:
    """Map score density onto the guide's complete 1-5 member interval."""
    low, high = ((spec.visible_secondary_members_per_bay
                  if spec and spec.visible_secondary_members_per_bay else (1, 5)))
    position = None
    try:
        datum = datums.by_id('transom_rows')
        position = datum.applied_position
        if position is None:
            position = datum.dimension_value
    except (AttributeError, KeyError):
        pass
    if position is None:
        # Legacy/test datum sets expose only the already-derived 2-4 transom count.
        rows = max(2, min(4, datums.integer('transom_rows')))
        position = (rows - 2) / 2.0
    position = min(1.0, max(0.0, float(position)))
    return max(low, min(high, int(round(low + (high - low) * position))))


_HT_SPECIAL_PART_ROLES = {
    ('edge_closure', 'external_strut'): 'support',
    ('edge_closure', 'spandrel_panel'): 'enclosure',
    ('edge_closure', 'wall_panel'): 'enclosure',
    ('entrance', 'wall_panel'): 'enclosure',
    ('entrance', 'entrance_head'): 'enclosure',
    ('entrance', 'entrance_door'): 'glazing',
    ('entrance', 'window_reveal'): 'enclosure',
}


def _finalize_high_tech_metadata(b) -> None:
    """Complete only explicitly mapped special pieces; expose every unknown.

    Normal High-Tech emitters author their metadata at creation time.  This final pass
    exists only for the small set of edge/entry pieces shared with other grammars.  An
    unknown kind remains unclassified so the gate can fail it; assigning a generic
    ``enclosure`` role here would turn missing evidence into a pass.
    """
    for group in b.groups.values():
        if group.semantic_layer != 'envelope' or group.subsystem in {
                'roof', 'roof_closure', 'parapet', 'canopy'}:
            continue
        mapped_role = _HT_SPECIAL_PART_ROLES.get((group.subsystem, group.kind))
        for instance in group.instances:
            if instance.assembly_id and instance.part_role:
                continue
            if mapped_role is None:
                continue
            instance.part_role = instance.part_role or mapped_role
            if instance.assembly_id is None:
                token = ''.join(ch if ch.isalnum() else '-' for ch in instance.id)
                instance.assembly_id = f'HTS-{instance.level_id}-{token}'
        if mapped_role is not None and 'HT-INV-01' not in group.rule_refs:
            group.rule_refs.extend(['HT-INV-01', 'HT-INV-03'])



def effective_opening_width(env: EnvelopeTectonic, bay_width: float,
                           min_fragment: float) -> float:
    """The opening width a bay of this size will actually get.

    A slot is narrow on purpose; it is not narrower than a window can be built. At
    9 % of a 1.2 m bay the blank-plane grammar was cutting sixty-millimetre openings,
    which the facade gate caught as slivers -- correctly, because that is a drawn
    line rather than an opening anyone could make.

    Defined once and shared, because the first version widened the opening in the
    emitter while the sliver guard upstream still tested the declared ratio, and a
    guard measuring a different number from the one the emitter uses is not a guard.
    """
    if env.opening_width_ratio <= 0.0 or bay_width <= 0.0:
        return env.opening_width_ratio
    return min(0.85, max(env.opening_width_ratio, min_fragment / bay_width))


# ---------------------------------------------------------------------------
# subtract: a wall with holes cut in it
# ---------------------------------------------------------------------------

def _bay_punched(b, bay: _Bay, env: EnvelopeTectonic, datums,
                 min_fragment: float = 0.30) -> None:
    """A wall plane with an opening subtracted, drawn as the four bands around it.

    `ENV-PUNCHED-WALL` and `ENV-BLANK-SLOT` share this emitter and differ only in the
    proportions the tectonic declares: a punched wall takes roughly half the bay and
    half the storey, a blank plane takes a ninth of the bay and three quarters of the
    storey. That single pair of numbers is the whole difference between a masonry
    facade and an incision in a monolith, which is why they are declared data rather
    than branches.
    """
    # A slot is narrow on purpose; it is not narrower than a window can be built.
    # At 9 % of a 1.2 m bay the blank-plane grammar was cutting sixty-millimetre
    # openings, which the facade gate caught as slivers -- correctly, because that
    # is a drawn line rather than an opening anyone could make.
    width_ratio = effective_opening_width(env, bay.width, min_fragment)
    height_ratio = env.opening_height_ratio
    material = env.wall_material
    refs = ['opaque_fraction', 'mullion_module_m', 'envelope_offset_m', *PLATE_DATUMS]

    # The opening is centred in the bay and sits on a sill proportioned off the storey.
    t0 = (1.0 - width_ratio) / 2.0
    t1 = t0 + width_ratio
    sill_z = bay.z_base + bay.height * (1.0 - height_ratio) * 0.62
    head_z = min(bay.z_head, sill_z + bay.height * height_ratio)

    parts = (
        ('SILL', 0.0, 1.0, bay.z_base, sill_z),
        ('HEAD', 0.0, 1.0, head_z, bay.z_head),
        ('JAMBL', 0.0, t0, sill_z, head_z),
        ('JAMBR', t1, 1.0, sill_z, head_z),
    )
    for tag, a, c, z0, z1 in parts:
        if z1 - z0 < 0.04 or c - a < 0.01:
            continue
        b.add(f'ENV-WAL-{bay.level_id}-S{bay.si:03d}-{tag}', 'wall_panel', 'envelope',
              'bearing_wall', bay.quad(a, c, z0, z1), material,
              level_id=bay.level_id, lattice_index=bay.index, datum_refs=refs,
              rule_refs=['MASS_TO_PUNCHED_WALL'],
              thickness_m=env.wall_thickness_m or env.cladding_depth_m,
              reason='Wall plane. The opening is a subtraction from it, not a panel '
                     'that happens to be transparent.')

    if head_z - sill_z < 0.04:
        return

    # The reveal is what gives the mass its shadow; it is drawn, not implied.
    depth = env.reveal_depth_m
    facade_control = getattr(b.lattice, 'facade_control', None)
    if facade_control is not None:
        # The reveal begins at the controlled weather plane and returns toward the
        # Program Volume boundary.  A fixed tectonic depth larger than the resolved
        # collar used to push the glass and the back of the reveal into occupied
        # volume; the collar is the governing available assembly depth on this path.
        depth = min(depth, facade_control.resolved_offset_m)
    if depth > 0.01:
        for tag, t in (('RVL', t0), ('RVR', t1)):
            dx, dy = bay.outward(depth / 2.0)
            centre = bay.at(t, (sill_z + head_z) / 2.0)
            b.add(f'ENV-RVL-{bay.level_id}-S{bay.si:03d}-{tag}', 'window_reveal',
                  'envelope', 'bearing_wall',
                  BoxGeometry(center=v3(centre.x - dx, centre.y - dy, centre.z),
                              size=v3(max(0.12, bay.width * 0.03), depth,
                                      head_z - sill_z), rotation_z=bay.angle),
                  material, level_id=bay.level_id, lattice_index=bay.index,
                  datum_refs=refs,
                  reason='Reveal: the wall thickness shown at the opening edge.')
        dx, dy = bay.outward(depth / 2.0)
        for tag, z in (('HD', head_z), ('SL', sill_z)):
            centre = bay.at((t0 + t1) / 2.0, z)
            b.add(f'ENV-{tag}-{bay.level_id}-S{bay.si:03d}',
                  'window_head' if tag == 'HD' else 'sill', 'envelope', 'bearing_wall',
                  BoxGeometry(center=v3(centre.x - dx, centre.y - dy, z),
                              size=v3(bay.width * width_ratio, depth, 0.16),
                              rotation_z=bay.angle),
                  material, level_id=bay.level_id, lattice_index=bay.index,
                  datum_refs=refs,
                  reason='Head and sill close the reveal and read as one course.')

    b.add(f'ENV-GLZ-{bay.level_id}-S{bay.si:03d}', 'glazing_panel', 'envelope',
          'bearing_wall', bay.quad(t0, t1, sill_z, head_z, push=-depth * 0.8),
          env.infill_material, level_id=bay.level_id, lattice_index=bay.index,
          datum_refs=refs, thickness_m=env.glazing_depth_m,
          reason='Glazing set back within the reveal so the wall reads in front of it.')


# ---------------------------------------------------------------------------
# subdivide: a frame whose cells are the openings
# ---------------------------------------------------------------------------

def _bay_subdivided(b, bay: _Bay, env: EnvelopeTectonic, datums, *, opaque: bool,
                    row_z: list[float], spandrel_height: float, mullion_profile: str,
                    course: int) -> None:
    """A mullion-and-transom grid, or the same grid cut by seams.

    `ENV-CURTAIN-WALL` and `ENV-FACETED-PANEL` both subdivide, and the difference is
    what the subdivision answers to. The curtain wall answers to the module; the faceted
    skin staggers its joints course by course and lets two diagonal seams cut across the
    whole elevation, ignoring the structural grid entirely. That conflict between the
    panel geometry and the frame behind it is the grammar, not a decoration on it.
    """
    refs = ['mullion_module_m', 'fin_depth_m', 'envelope_offset_m', *PLATE_DATUMS]
    # Staggering lives in registered_bays, where both corner panels are retained.
    stagger = 0.0
    # The level-return brackets are emitted before this bay. Reuse the exact
    # same-station bracket IDs as mullion supports, preserving the visible slab ->
    # return -> mullion chain in a section instead of relying on a nearest-carrier
    # inference downstream.
    return_supports = [
        f'ENV-RET-{bay.level_id}-{tag}-S{bay.si:03d}'
        for tag in ('BASE', 'HEAD')
        if f'ENV-RET-{bay.level_id}-{tag}-S{bay.si:03d}' in b.element_ids
    ]
    return_rules = ['ENVELOPE-RETURN-TO-MULLION'] if return_supports else []
    if getattr(b.lattice, 'facade_control', None) is not None:
        return_rules.append('PV-FACADE-DECLARED-SUPPORT')

    if opaque:
        b.add(f'ENV-SWP-{bay.level_id}-S{bay.si:03d}',
              'facet_panel' if env.stagger_panels else 'solid_wall_panel', 'envelope',
              'opaque_wall', bay.quad(stagger, 1.0 + stagger, bay.z_base, bay.z_head),
              env.wall_material if env.stagger_panels else env.trim_material,
              level_id=bay.level_id, lattice_index=bay.index,
              datum_refs=[*refs, 'opaque_fraction'],
              rule_refs=['GENRE_TO_OPAQUE_FRACTION'],
              thickness_m=env.wall_thickness_m or env.cladding_depth_m,
              reason='Opaque panel. The share of solid to glazed is proposed by the '
                     'timbral position and requires human acceptance.')
        if env.draws_mullions:
            b.add(f'ENV-MUL-{bay.level_id}-S{bay.si:03d}', 'mullion', 'envelope',
                  'opaque_wall',
                  MemberGeometry(path=[v3(bay.point.x, bay.point.y, bay.z_base),
                                       v3(bay.point.x, bay.point.y, bay.z_head)],
                                 profile=mullion_profile, roll=bay.roll),
                  env.trim_material, level_id=bay.level_id,
                  lattice_index=bay.index, datum_refs=refs,
                  supports=return_supports,
                  rule_refs=return_rules,
                  reason='Panel joint expressed at the envelope module.')
        return

    if env.draws_mullions:
        b.add(f'ENV-MUL-{bay.level_id}-S{bay.si:03d}', 'mullion', 'envelope',
              'curtain_wall',
              MemberGeometry(path=[v3(bay.point.x, bay.point.y, bay.z_base),
                                   v3(bay.point.x, bay.point.y, bay.z_head)],
                             profile=mullion_profile, roll=bay.roll),
              env.trim_material, level_id=bay.level_id,
              lattice_index=bay.index, datum_refs=refs,
              supports=return_supports,
              rule_refs=['IS-INV-01', 'IS-INV-03', 'REPETITION_TO_MULLION',
                         *return_rules],
              reason='Vertical mullion at the envelope module the score set, with a '
                     'projection the timbral position proposed.')

    for r in range(len(row_z) - 1):
        za, zb = row_z[r], row_z[r + 1]
        if r == 0 and spandrel_height > 0.02:
            b.add(f'ENV-SPD-{bay.level_id}-S{bay.si:03d}', 'spandrel_panel', 'envelope',
                  'curtain_wall',
                  bay.quad(stagger, 1.0 + stagger, za, za + spandrel_height),
                  env.trim_material, level_id=bay.level_id,
                  lattice_index=bay.index,
                  datum_refs=['spandrel_height_m', 'mullion_module_m'],
                  rule_refs=['REPETITION_TO_SPANDREL'],
                  thickness_m=env.cladding_depth_m,
                  reason='Spandrel band closes the floor zone at the repeated height '
                         'the score set.')
            za += spandrel_height
        if zb - za < 0.05:
            continue
        b.add(f'ENV-GLZ-{bay.level_id}-S{bay.si:03d}-R{r:02d}',
              'facet_glazing' if env.stagger_panels else 'glazing_panel', 'envelope',
              'curtain_wall', bay.quad(stagger, 1.0 + stagger, za, zb),
              env.infill_material if env.stagger_panels else 'glass',
              level_id=bay.level_id, lattice_index={**bay.index, 'row': r},
              datum_refs=['transom_rows', 'mullion_module_m', 'envelope_offset_m'],
              thickness_m=env.glazing_depth_m,
              reason='Vision panel between adjacent mullions and transoms.')

    if env.draws_mullions:
        for r, zr in enumerate(row_z):
            b.add(f'ENV-TRN-{bay.level_id}-S{bay.si:03d}-R{r:02d}', 'transom',
                  'envelope', 'curtain_wall',
                  MemberGeometry(path=[v3(bay.point.x, bay.point.y, zr),
                                       v3(bay.nxt.x, bay.nxt.y, zr)],
                                 profile='TRAN-75x140'),
                  env.trim_material, level_id=bay.level_id,
                  lattice_index={**bay.index, 'row': r},
                  datum_refs=['transom_rows', 'mullion_module_m'],
                  reason='Horizontal transom at a declared row.')

    # The seams that make a faceted skin faceted. Two of them, running at a fixed rake
    # across the whole elevation, so they cross the structural grid rather than follow
    # it. A seam is drawn only where it passes through this bay.
    for s in range(env.diagonal_seams):
        rake = 0.55 + 0.35 * s
        t = (bay.si * 0.17 + s * 0.5) % 1.0
        z = bay.z_base + bay.height * ((t * rake) % 1.0)
        if not (bay.z_base + 0.15 < z < bay.z_head - 0.15):
            continue
        b.add(f'ENV-SEAM-{bay.level_id}-S{bay.si:03d}-D{s}', 'seam_edge', 'envelope',
              'facet_seam',
              MemberGeometry(path=[v3(bay.point.x, bay.point.y, z),
                                   v3(bay.nxt.x, bay.nxt.y,
                                      min(bay.z_head - 0.05, z + bay.height * 0.28))],
                             profile='EDGEBEAM-160'),
              env.trim_material, level_id=bay.level_id, lattice_index=bay.index,
              datum_refs=['mullion_module_m', 'plate_rotation_deg'],
              reason='Seam cutting across the panel courses at a rake that ignores the '
                     'structural grid.')


# ---------------------------------------------------------------------------
# recess: the frame is the elevation
# ---------------------------------------------------------------------------

def _bay_recessed(
        b, bay: _Bay, env: EnvelopeTectonic, datums, row_z: list[float],
        mullion_profile: str, system_depth: float, *, use: _BayProgram,
        secondary_count: int, submodule_target: float, spec: GrammarSpec,
        depth_rule: str, depth_reason: str, standard: bool) -> None:
    """One inspectable High-Tech kit: primary, carriers and replaceable infill.

    A primary assembly bay follows the structural rhythm.  It is then divided into
    independently replaceable enclosure submodules.  Programme decides cassette versus
    glazing for each submodule; score density changes only the number of visible
    secondary carriers.
    """
    refs = ['mullion_module_m', *PLATE_DATUMS]
    if depth_rule == 'POLYPHONY_TO_ENVELOPE_OFFSET':
        refs.append('envelope_offset_m')
    primary_is_standard = standard
    submodules, unresolved_module, unresolved_program_break = (
        _high_tech_program_submodules(b, bay, submodule_target, spec))
    standard = standard and not unresolved_module
    assembly_id = _high_tech_assembly_id(
        bay, special=None if standard else (
            'PROGRAM' if unresolved_program_break else 'EDGE'))
    common_rules = ['HT-INV-01', 'HT-INV-02', 'HT-INV-03', 'HT-INV-04', depth_rule]
    if not standard:
        common_rules.append('HT-SPECIAL-COMPONENT')
    if not primary_is_standard:
        common_rules.append('HT-PRIMARY-BAY-UNRESOLVED')
    if unresolved_module:
        common_rules.append(
            'HT-SUBMODULE-PROGRAM-BOUNDARY-UNRESOLVED'
            if unresolved_program_break else 'HT-SUBMODULE-UNRESOLVED')

    # A countable base bracket makes the frame's route to a real slab explicit.  The
    # path starts inside the slab depth, rises to the facade datum and then reaches the
    # exposed frame.  A missing slab host stays missing for the interface gate.
    slab_anchor = _nearest_slab_anchor(
        b, bay.level_id, bay.skin_point, bay.z_base - EDGE_RETURN_THICKNESS_M)
    slab_hosts = [slab_anchor[1]] if slab_anchor else []
    slab_point = slab_anchor[3] if slab_anchor else bay.skin_point
    bracket_id = f'ENV-BKT-{bay.level_id}-S{bay.si:03d}'
    b.add(
        bracket_id, 'external_strut', 'envelope', 'expressed_frame',
        MemberGeometry(path=_member_path(
            v3(slab_point.x, slab_point.y,
               bay.z_base - EDGE_RETURN_THICKNESS_M),
            v3(slab_point.x, slab_point.y, bay.z_base),
            bay.at(0.0, bay.z_base, skin=True),
            bay.at(0.0, bay.z_base),
        ), profile=EDGE_BRACKET_PROFILE, roll=bay.roll),
        env.trim_material, category=use.category, program=use.program,
        level_id=bay.level_id, lattice_index={**bay.index, 'interface': 0},
        datum_refs=refs, supports=slab_hosts[:1], assembly_id=assembly_id,
        part_role='support', rule_refs=common_rules,
        reason=('Primary facade-to-slab bracket. Its first node lies on the nearest '
                'real slab material and its last node meets the exposed frame; connection '
                f'capacity remains professional_review_required. {depth_reason}'))

    frame_id = f'ENV-FRM-{bay.level_id}-S{bay.si:03d}'
    b.add(frame_id, 'frame_expression', 'envelope', 'expressed_frame',
          MemberGeometry(path=[v3(bay.point.x, bay.point.y, bay.z_base),
                               v3(bay.point.x, bay.point.y, bay.z_head)],
                         profile=mullion_profile, roll=bay.roll),
          env.wall_material, category=use.category, program=use.program,
          level_id=bay.level_id, lattice_index=bay.index, datum_refs=refs,
          supports=[bracket_id],
          assembly_id=assembly_id, part_role='frame',
          rule_refs=common_rules,
          reason='Primary expressed facade frame. Its stable bay assembly ID keeps the '
                 'frame separately inspectable from supports and infill. The frame '
                 f'stands {system_depth:.3f} m from the recessed enclosure; connection '
                 'capacity remains professional_review_required.')
    b.add(f'{frame_id}-TOP', 'frame_expression', 'envelope', 'expressed_frame',
          MemberGeometry(path=[v3(bay.point.x, bay.point.y, bay.z_head),
                               v3(bay.nxt.x, bay.nxt.y, bay.z_head)],
                         profile=mullion_profile, roll=v3(0.0, 0.0, 1.0)),
          env.wall_material, category=use.category, program=use.program,
          level_id=bay.level_id,
          lattice_index={**bay.index, 'primary_span': 1}, datum_refs=refs,
          supports=[frame_id], assembly_id=assembly_id, part_role='frame',
          rule_refs=common_rules,
          reason='Horizontal member makes the complete primary assembly bay '
                 'measurable as emitted geometry and meets its vertical frame.')

    # These are real secondary carrier/tie members, not decorative exposed services.
    # Each begins on the emitted frame and returns to the recessed skin at the far
    # side, so its declared support is a real emitted ID and its geometry shows the
    # interface a student detail section needs to explain.
    support_ids = []
    for index in range(secondary_count):
        z = bay.z_base + bay.height * (index + 1) / (secondary_count + 1)
        support_id = f'ENV-STR-{bay.level_id}-S{bay.si:03d}-N{index:02d}'
        support_ids.append(support_id)
        b.add(support_id, 'external_strut', 'envelope', 'expressed_frame',
              MemberGeometry(path=[bay.at(0.0, z), bay.at(0.0, z, skin=True),
                                   bay.at(1.0, z, skin=True)],
                             profile='TRAN-75x140', roll=bay.roll),
              env.trim_material, category=use.category, program=use.program,
              level_id=bay.level_id,
              lattice_index={**bay.index, 'secondary': index},
              datum_refs=[*refs, 'transom_rows'], supports=[frame_id],
              assembly_id=assembly_id, part_role='support',
              rule_refs=[*common_rules, 'DENSITY_TO_FACADE'],
              reason=f'Score-selected secondary carrier {index + 1} of '
                     f'{secondary_count}. It brackets from the primary frame to a '
                     'continuous carrier line behind every enclosure submodule; '
                     'member capacity is not checked.')

    spandrel = min(
        0.9, max(0.25, datums.value('spandrel_height_m'))
    ) if len(row_z) > 1 else 0.0
    if spandrel > 0.05:
        b.add(f'ENV-SPD-{bay.level_id}-S{bay.si:03d}', 'spandrel_panel', 'envelope',
              'expressed_frame',
              bay.quad(0.0, 1.0, bay.z_base, bay.z_base + spandrel, skin=True),
              env.trim_material, category=use.category, program=use.program,
              level_id=bay.level_id, lattice_index=bay.index,
              datum_refs=['spandrel_height_m', *refs],
              supports=[bracket_id], assembly_id=assembly_id,
              part_role='enclosure',
              rule_refs=[*common_rules, 'HT-INV-05'],
              thickness_m=env.cladding_depth_m,
              reason='Replaceable floor-edge enclosure unit on the common carrier '
                     f'interface. Programme authority: {use.source}.')

    za, zb = bay.z_base + spandrel, bay.z_head
    if zb - za < 0.05:
        return
    if not submodules:
        submodules = [(0.0, 1.0)]
    for column, (t0, t1) in enumerate(submodules):
        sub_use = _bay_program(b, bay, (t0 + t1) / 2.0)
        opaque = sub_use.category in {'service', 'private'}
        program_rules = _high_tech_program_refs(sub_use)
        unresolved_rules = ([
            'HT-SUBMODULE-PROGRAM-BOUNDARY-UNRESOLVED'
            if unresolved_program_break else 'HT-SUBMODULE-UNRESOLVED'
        ] if unresolved_module else [])
        if opaque:
            b.add(f'ENV-CAS-{bay.level_id}-S{bay.si:03d}-C{column:02d}',
                  'solid_wall_panel', 'envelope', 'expressed_frame',
                  bay.quad(t0, t1, za, zb, skin=True), 'steel_light',
                  category=sub_use.category, program=sub_use.program,
                  level_id=bay.level_id,
                  lattice_index={**bay.index, 'submodule': column},
                  datum_refs=refs, supports=support_ids,
                  assembly_id=assembly_id, part_role='cassette',
                  rule_refs=[*common_rules, 'HT-INV-05', *program_rules,
                             *unresolved_rules],
                  thickness_m=max(0.20, env.cladding_depth_m),
                  reason='Opaque replaceable insulated/service cassette selected by '
                         f'the adjacent {sub_use.category} programme '
                         f'({sub_use.program}); evidence source: {sub_use.source}. '
                         'Thermal, fire and weathering performance remain unverified.')
        else:
            b.add(f'ENV-GLZ-{bay.level_id}-S{bay.si:03d}-C{column:02d}',
                  'glazing_panel', 'envelope', 'expressed_frame',
                  bay.quad(t0, t1, za, zb, skin=True), 'glass',
                  category=sub_use.category, program=sub_use.program,
                  level_id=bay.level_id,
                  lattice_index={**bay.index, 'submodule': column},
                  datum_refs=refs, supports=support_ids,
                  assembly_id=assembly_id, part_role='glazing',
                  rule_refs=[*common_rules, 'HT-INV-05', *program_rules,
                             *unresolved_rules],
                  thickness_m=env.glazing_depth_m,
                  reason='Replaceable vision unit on the same carrier ports as the '
                         f'cassette family, selected by {sub_use.category} programme; '
                         f'evidence source: {sub_use.source}. Glazing specification '
                         'and thermal breaks remain unverified.')


# ---------------------------------------------------------------------------
# overlay: a second structure in front of the skin
# ---------------------------------------------------------------------------

def _bay_backing(b, bay: _Bay, env: EnvelopeTectonic, row_z: list[float],
                 opaque_fraction: float = 0.0) -> None:
    """The plain skin that an overlay tectonic stands its second structure in front of.

    The opaque share is honoured here and not only on the framed families. It was not,
    at first: the backing skin made row zero solid and everything above it glass, so an
    overlay grammar's opening ratio was a function of the transom count alone. That made
    it unresponsive to the score *and* impossible for the facade gate to correct, since
    the one lever the gate can pull was not connected to anything. Solid rows are taken
    from the bottom so the skin reads as a wall the screen stands on.
    """
    rows = max(1, len(row_z) - 1)
    solid_rows = int(round(rows * min(1.0, max(0.0, opaque_fraction))))
    for r in range(rows):
        za, zb = row_z[r], row_z[r + 1]
        if zb - za < 0.05:
            continue
        opaque = r < max(1, solid_rows)
        b.add(f'ENV-BCK-{bay.level_id}-S{bay.si:03d}-R{r:02d}',
              'backing_panel' if opaque else 'glazing_panel', 'envelope', 'backing_skin',
              bay.quad(0.0, 1.0, za, zb),
              env.wall_material if opaque else env.infill_material,
              level_id=bay.level_id, lattice_index={**bay.index, 'row': r},
              datum_refs=['transom_rows', 'envelope_offset_m'],
              thickness_m=env.cladding_depth_m,
              reason='Backing skin. It is deliberately plain: the layer in front of it '
                     'is what the elevation is.')


def _bay_lattice(b, bay: _Bay, env: EnvelopeTectonic, cells: int) -> None:
    """A deep grid of cells standing off the skin.

    Depth is the whole point. A shallow grid is a pattern; a grid deep enough to shade
    itself reads as shadow, which is why `outboard_depth_m` is large and the cell
    members are drawn as boxes rather than as lines.
    """
    depth = env.outboard_depth_m
    dx, dy = bay.outward(depth / 2.0)
    if not b.lattice.encloses(bay.point.x + dx, bay.point.y + dy):
        return
    refs = ['mullion_module_m', 'envelope_offset_m', 'envelope_layer_count',
            *PLATE_DATUMS]
    thickness = max(0.07, bay.width / 14.0)

    for c in range(cells + 1):
        z = bay.z_base + bay.height * c / cells
        centre = bay.at(0.5, z)
        b.add(f'ENV-LTT-{bay.level_id}-S{bay.si:03d}-H{c:02d}', 'lattice_transom',
              'envelope', 'lattice_screen',
              BoxGeometry(center=v3(centre.x + dx, centre.y + dy, z),
                          size=v3(bay.width, depth, thickness), rotation_z=bay.angle),
              env.outboard_material, level_id=bay.level_id,
              lattice_index={**bay.index, 'cell': c}, datum_refs=refs,
              rule_refs=['LAYERING_TO_LATTICE'],
              reason='Lattice course. The screen is deep enough that its openings read '
                     'as shadow rather than as glass.')

    verticals = 2
    for vpos in range(verticals + 1):
        t = vpos / verticals
        centre = bay.at(t, (bay.z_base + bay.z_head) / 2.0)
        b.add(f'ENV-LTV-{bay.level_id}-S{bay.si:03d}-V{vpos:02d}', 'lattice_mullion',
              'envelope', 'lattice_screen',
              BoxGeometry(center=v3(centre.x + dx, centre.y + dy, centre.z),
                          size=v3(thickness, depth, bay.height), rotation_z=bay.angle),
              env.outboard_material, level_id=bay.level_id,
              lattice_index={**bay.index, 'cell': vpos}, datum_refs=refs,
              reason='Lattice pier between cells.')


def _bay_field(b, bay: _Bay, env: EnvelopeTectonic, rows: int, columns: int,
               level_t: float) -> None:
    """A field of small panels whose depth varies along an axis.

    An even field of one panel is a rainscreen. What makes this a field is that the
    depth is a function of position, so the wall reads as a gradient. The axis comes
    from the grammar: Parametricism varies it vertically from the ground, Organic blooms
    it radially around the entrance.
    """
    lo, hi = env.field_depth_range_m
    refs = ['mullion_module_m', 'envelope_offset_m', 'shading_depth_m', *PLATE_DATUMS]

    for r in range(rows):
        for c in range(columns):
            u = (c + 0.5) / columns
            v = (r + 0.5) / rows
            if env.field_axis == 'radial':
                # distance from the entrance, which sits at the middle of the base
                d = math.hypot((u - 0.5) * 1.4, (v + level_t) * 0.9)
                weight = max(0.0, 1.0 - d)
            else:
                weight = max(0.0, 1.0 - (v * 0.45 + level_t * 0.75))
            depth = lo + (hi - lo) * weight
            if depth < lo + (hi - lo) * 0.06:
                continue
            dx, dy = bay.outward(depth / 2.0)
            z = bay.z_base + bay.height * v
            centre = bay.at(u, z)
            if not b.lattice.encloses(centre.x + dx, centre.y + dy):
                continue
            b.add(f'ENV-FLD-{bay.level_id}-S{bay.si:03d}-R{r:02d}C{c:02d}',
                  'field_panel', 'envelope', 'panel_field',
                  BoxGeometry(center=v3(centre.x + dx, centre.y + dy, z),
                              size=v3(bay.width / columns * 0.86, depth,
                                      bay.height / rows * 0.86), rotation_z=bay.angle),
                  env.outboard_material, level_id=bay.level_id,
                  lattice_index={**bay.index, 'row': r, 'col': c}, datum_refs=refs,
                  rule_refs=['LAYERING_TO_PANEL_FIELD'],
                  reason='Field panel. Its projection is a function of where it sits, '
                         'so the wall reads as a gradient rather than a pattern.')


def _emit_applied_order(b, env: EnvelopeTectonic, lattice, datums) -> None:
    """One giant frame applied to the principal elevation, centred on the entrance.

    This is scenography stuck to the front of a building and the emitter does not
    pretend otherwise: the order carries no load, is not tied to the frame, and is
    recorded as `architectural_convention` like every other member here that a
    calculation did not govern.
    """
    occupied = lattice.occupied
    if not occupied:
        return
    south = min(p.y for p in occupied[0].plate)
    xs = [p.x for p in occupied[0].plate]
    centre_x = (min(xs) + max(xs)) / 2.0
    top = occupied[min(len(occupied) - 1, max(1, int(len(occupied) * 0.8)))].z
    base = occupied[0].z
    width = (max(xs) - min(xs)) * 0.52
    depth = env.outboard_depth_m
    jamb = max(0.8, width * 0.11)
    refs = ['entry_canopy_span_m', 'floor_to_floor_m', *PLATE_DATUMS]

    for side, sign in (('L', -1.0), ('R', 1.0)):
        b.add(f'ENV-ORD-JAMB-{side}', 'order_jamb', 'envelope', 'applied_order',
              BoxGeometry(
                  center=v3(centre_x + sign * (width / 2.0 - jamb / 2.0),
                            south - depth / 2.0, (base + top) / 2.0),
                  size=v3(jamb, depth, top - base)),
              env.outboard_material, level_id=occupied[0].id, datum_refs=refs,
              rule_refs=['INCIDENT_TO_APPLIED_ORDER'],
              reason='Pier of the applied order. It carries no load and is recorded as '
                     'convention, because that is what it is.')

    b.add('ENV-ORD-LINTEL', 'order_lintel', 'envelope', 'applied_order',
          BoxGeometry(center=v3(centre_x, south - depth / 2.0, top - jamb / 2.0),
                      size=v3(width, depth, jamb)),
          env.outboard_material, level_id=occupied[0].id, datum_refs=refs,
          reason='Lintel closing the applied order over the entrance.')


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

def emit_envelope(b, env: EnvelopeTectonic, spec: GrammarSpec | None = None,
                  opacity_override: float | None = None) -> None:
    """Build the envelope for one tectonic family, under its grammar's own spec.

    `env` says what operation the elevation performs; `spec` says how far the music
    is allowed to push it and within what bounds the guide expects the result to
    land. Passing `None` runs the tectonic at full score authority, which is what
    the older tests expect and what a grammar with no published limits would get.
    """
    lattice, datums = b.lattice, b.datums
    high_tech = env.id == 'ENV-EXPRESSED-FRAME' and (
        spec is None or spec.grammar_id == 'FCD-05-HIGH-TECH')
    high_tech_spec = (spec or spec_for('FCD-05-HIGH-TECH')) if high_tech else None
    facade_control = getattr(lattice, 'facade_control', None)
    module = datums.value('mullion_module_m')
    if spec:
        # The guide publishes the module range the grammar is set out on. Brutalism
        # runs 1.8-4.8 m inhabited bays; Bauhaus runs a 0.6-1.5 m standard unit.
        # Clamping here is what stops a score from handing one grammar the other's
        # grain while keeping its name.
        low, high = spec.module_range_m
        module = min(high, max(low, module))
    registration_module = module
    system_depth = abs(datums.value('envelope_offset_m') * env.setback_multiplier)
    depth_rule = 'POLYPHONY_TO_ENVELOPE_OFFSET'
    depth_reason = ''
    if facade_control is not None:
        system_depth = facade_control.resolved_offset_m
        depth_rule = ('FACADE-CONTROL-PROVISIONAL'
                      if facade_control.resolution_status == 'provisional_unevaluated'
                      else 'FACADE-CONTROL-OFFSET')
        depth_reason = facade_control.resolution_reason
    elif high_tech_spec is not None:
        system_depth, depth_rule, depth_reason = _high_tech_system_depth(
            datums, high_tech_spec)
    rows = max(1, datums.integer('transom_rows'))
    spandrel_height = datums.value('spandrel_height_m')
    offset = (-system_depth if high_tech else system_depth)
    layers = max(1, datums.integer('envelope_layer_count'))
    shading_rows = max(0, datums.integer('shading_rows'))
    secondary_count = _high_tech_secondary_count(datums, spec) if high_tech else 0

    # The tectonic sets the floor on how solid the wall is; the score moves it upward
    # from there, but only as far as the grammar's own guide permits. Minimalism caps
    # score-driven dimensional variation at 12 % in writing, so a minimalist elevation
    # under a loud recording must stay a minimalist elevation; Parametricism allows 70 %
    # and expects the field to swing. Applying that authority here is the difference
    # between implementing the guides and citing them.
    authority = spec.score_authority if spec else 1.0
    score_opacity = min(0.9, max(0.0, datums.value('opaque_fraction')))
    headroom = 1.0 - env.base_opacity
    opaque_fraction = min(
        0.96, env.base_opacity + score_opacity * headroom * authority)
    if opacity_override is not None:
        # The facade gate measured an opening ratio outside the band the grammar's
        # guide publishes and asked for one specific number back. Honouring it here
        # rather than clamping the datum keeps the correction visible: the datum
        # still records what the music asked for, and the model records that a gate
        # overrode it.
        opaque_fraction = min(0.96, max(0.0, opacity_override))

    mullion_profile = b.profile(convention_profile(
        f'MULL-{env.mullion_profile_depth_m * 1000:.0f}x75', 'box',
        env.mullion_profile_depth_m, 0.075))

    occupied = list(lattice.occupied)
    entrance = planned_entrance(lattice, datums, getattr(b, 'approach', None))
    for course, level in enumerate(facade_band_levels(lattice)):
        if level.is_terrace:
            continue
        z_base = level.z
        plate_shape = Polygon([(point.x, point.y) for point in level.plate])
        project_skin = not plate_shape.equals(plate_shape.convex_hull)
        skin_boundary = plate_shape.boundary
        level_control = (facade_control.level(level.id)
                         if facade_control is not None else None)
        outboard = (
            [v2(x, y) for x, y in level_control.weather_boundary]
            if level_control is not None else
            _true_outboard_boundary(level.plate, abs(offset))
            if high_tech else inset(level.plate, -abs(offset)))
        # 300 mm is the pipeline's geometric closure guard when a guide publishes no
        # material limit.  The facade gate keeps that distinction visible and does not
        # award a grammar pass for this project-level fallback.
        min_fragment = (spec.minimum_fragment_m
                        if spec and spec.minimum_fragment_m is not None else 0.30)
        minimum_span = ((high_tech_spec.primary_assembly_bay_range_m or (3.0, 9.0))[0]
                        if high_tech_spec is not None else min_fragment)
        if env.opening_logic == 'subtract' and env.opening_width_ratio > 0.0:
            minimum_span = max(3.0 * min_fragment,
                               2.0 * min_fragment / max(0.01, 1.0 - env.opening_width_ratio))
        spans = (_high_tech_registered_bays(level.plate, datums, high_tech_spec)
                 if high_tech_spec is not None else
                 registered_bays(outboard, registration_module, minimum_span,
                                 stagger=env.stagger_panels and bool(course % 2)))
        entry_span = None
        if entrance is not None and entrance.level_id == level.id:
            entrance_boundary = level.plate if high_tech else outboard
            entrance_module = (_high_tech_edge_target(
                level.plate, entrance.edge, datums, high_tech_spec)
                if high_tech_spec is not None else registration_module)
            spans, entry_span = _register_entrance(
                spans, level.plate, entrance_boundary, entrance, entrance_module, minimum_span,
                max(min_fragment, ENTRANCE_REVEAL_DEPTH_M,
                    env.mullion_profile_depth_m / 2.0 + ENTRANCE_EDGE_MARGIN_M),
                force_remapped=False)
        if not spans:
            continue
        if high_tech:
            source_winding = sum(
                a.x * c.y - c.x * a.y
                for a, c in zip(level.plate, level.plate[1:] + level.plate[:1]))
            source_normal_sign = 1.0 if source_winding < 0.0 else -1.0
            stations = []
            controlled_boundary = (
                Polygon([(point.x, point.y) for point in outboard]).boundary
                if level_control is not None else None)
            for edge, lo, hi in spans:
                skin_point = _point_on_edge(level.plate, edge, lo)
                skin_nxt = _point_on_edge(level.plate, edge, hi)
                angle = math.atan2(skin_nxt.y - skin_point.y,
                                   skin_nxt.x - skin_point.x)
                dx = (math.cos(angle + math.pi / 2.0)
                      * source_normal_sign * system_depth)
                dy = (math.sin(angle + math.pi / 2.0)
                      * source_normal_sign * system_depth)
                station_point = Point(skin_point.x + dx, skin_point.y + dy)
                station_nxt = Point(skin_nxt.x + dx, skin_nxt.y + dy)
                if controlled_boundary is not None:
                    # A normal-shifted concave corner can terminate inside the exact
                    # mitred offset even though the middle of its edge is parallel.
                    # Snap only those derived endpoints to the FacadeControl ring; the
                    # source points below remain on their authored Program Volume edge.
                    station_point = nearest_points(
                        station_point, controlled_boundary)[1]
                    station_nxt = nearest_points(station_nxt, controlled_boundary)[1]
                stations.append((v2(station_point.x, station_point.y),
                                 v2(station_nxt.x, station_nxt.y),
                                 edge, lo, hi))
        else:
            stations = [(_point_on_edge(outboard, edge, lo),
                         _point_on_edge(outboard, edge, hi), edge, lo, hi)
                        for edge, lo, hi in spans]
        # Courtyard rings are weather boundaries too. They share the same grammar,
        # return station register and emitter tail, with the normal facing the void.
        # Their source points are projected onto the complete authoritative source
        # boundary; offsetting can split a hole, so positional ring pairing is invalid.
        inner_context = {}
        if level_control is not None:
            source_boundary = _surface_polygon(
                level_control.source_boundary,level_control.source_voids).boundary
            edge_offset = len(outboard)
            for ring_index, ring in enumerate(level_control.weather_voids, start=1):
                weather_ring = [v2(*point) for point in ring]
                winding = sum(a.x*c.y-c.x*a.y for a,c in zip(
                    weather_ring,weather_ring[1:]+weather_ring[:1]))
                inner_normal = -1.0 if winding < 0.0 else 1.0
                for edge,lo,hi in registered_bays(weather_ring,registration_module,minimum_span,
                        stagger=env.stagger_panels and bool(course % 2)):
                    point,nxt = (_point_on_edge(weather_ring,edge,t) for t in (lo,hi))
                    inner_context[len(stations)] = (
                        _project_to_skin(source_boundary,point),
                        _project_to_skin(source_boundary,nxt),inner_normal,ring_index)
                    stations.append((point,nxt,edge_offset+edge,lo,hi))
                edge_offset += len(weather_ring)
        upper = None if level.kind == 'roof' else lattice.levels[level.index + 1]
        z_head = _emit_level_returns(
            b, level, upper, outboard, [item[0] for item in stations], env,
            high_tech=high_tech,
            weather_voids=(level_control.weather_voids
                           if level_control is not None else ()))
        winding = sum(a.x * c.y - c.x * a.y
                      for a, c in zip(level.plate if high_tech else outboard,
                                      (level.plate if high_tech else outboard)[1:]
                                      + (level.plate if high_tech else outboard)[:1]))
        normal_sign = 1.0 if winding < 0.0 else -1.0
        row_z = [z_base + (z_head - z_base) * r / rows for r in range(rows + 1)]
        level_t = min(1.0, course / max(1, len(occupied) - 1))

        # The narrowest panel a bay of this family contains, as a share of the bay.
        # A punched wall's jamb is the slenderest thing on it; a curtain wall's panels
        # span the whole bay.
        narrowest_share = 1.0

        visible = [i for i, (point, *_rest) in enumerate(stations)
                   if lattice.encloses(point.x, point.y)]
        opaque_count = int(round(len(visible) * opaque_fraction))
        south_y = min(p.y for p in outboard)

        def make_bay(si: int) -> _Bay:
            point, nxt, edge, lo, hi = stations[si]
            angle = math.atan2(nxt.y - point.y, nxt.x - point.x)
            inner = inner_context.get(si)
            return _Bay(
                point, nxt, z_base, z_head, angle,
                {'level': level.index, 'station': si, 'edge': edge,
                 'boundary_ring': inner[3] if inner else 0}, level.id, si,
                point.y < south_y + 0.8 and inner is None,
                normal_sign=inner[2] if inner else normal_sign,
                skin_point=(inner[0] if inner else _point_on_edge(level.plate, edge, lo)
                            if high_tech else
                            _project_to_skin(skin_boundary, point)
                            if project_skin else
                            _point_on_edge(level.plate, edge, lo)),
                skin_nxt=(inner[1] if inner else _point_on_edge(level.plate, edge, hi)
                          if high_tech else
                          _project_to_skin(skin_boundary, nxt)
                          if project_skin else
                          _point_on_edge(level.plate, edge, hi)))

        uses = {si: _bay_program(b, make_bay(si)) for si in visible} \
            if high_tech else {}
        if high_tech:
            # High-Tech transparency is a programme decision at each enclosure
            # submodule.  The score's opaque datum has no authority in this grammar,
            # and the emitter does not manufacture one of each family to satisfy a
            # checklist.
            opaque_set = set()
        else:
            opaque_set = set(sorted(
                visible, key=lambda i: -stations[i][0].x)[:opaque_count])

        for si, (point, nxt, edge, lo, hi) in enumerate(stations):
            if si not in visible:
                continue
            span = math.hypot(nxt.x - point.x, nxt.y - point.y)
            if env.opening_logic == 'subtract' and env.opening_width_ratio > 0.0:
                opening = effective_opening_width(env, span, min_fragment)
                narrowest_share = max(0.02, min(opening, (1.0 - opening) / 2.0))
            bay = make_bay(si)
            primary_low, primary_high = (
                high_tech_spec.primary_assembly_bay_range_m
                if high_tech_spec is not None
                and high_tech_spec.primary_assembly_bay_range_m is not None
                else (3.0, 9.0))
            standard_high_tech_bay = (
                high_tech and primary_low - GEOMETRY_EPS_M <= span
                <= primary_high + GEOMETRY_EPS_M)
            high_tech_assembly = (_high_tech_assembly_id(
                bay, special=None if standard_high_tech_bay else 'EDGE')
                if high_tech else None)
            if (edge, lo, hi) == entry_span:
                _emit_entrance(
                    b, bay, env, entrance,
                    assembly_id=(_high_tech_assembly_id(bay, special='ENTRY')
                                 if high_tech else None),
                    use=uses.get(si))
                continue
            if span * narrowest_share < min_fragment - GEOMETRY_EPS_M:
                closure_assembly = (
                    _high_tech_assembly_id(bay, special='CLOSE')
                    if high_tech else None)
                if high_tech:
                    # The closure stands on the weather plane while the slab ends at
                    # the source skin. Give the exceptional panel a real, inspectable
                    # carrier between those two datums instead of naming two bodies
                    # that each satisfy only half of the interface contract.
                    target = bay.at(0.5, bay.z_base, skin=True)
                    slab_anchor = _nearest_slab_anchor(
                        b, bay.level_id, target,
                        bay.z_base - EDGE_RETURN_THICKNESS_M)
                    slab_hosts = [slab_anchor[1]] if slab_anchor else []
                    slab_point = slab_anchor[3] if slab_anchor else target
                    bracket_id = f'ENV-CLOSE-BKT-{level.id}-S{si:03d}'
                    b.add(
                        bracket_id, 'external_strut', 'envelope', 'edge_closure',
                        MemberGeometry(path=_member_path(
                            v3(slab_point.x, slab_point.y,
                               bay.z_base - EDGE_RETURN_THICKNESS_M),
                            v3(slab_point.x, slab_point.y, bay.z_base),
                            target,
                            bay.at(0.5, bay.z_base),
                        ), profile=EDGE_BRACKET_PROFILE, roll=bay.roll),
                        env.trim_material, level_id=level.id,
                        lattice_index={**bay.index, 'interface': 0},
                        datum_refs=['mullion_module_m', 'envelope_offset_m',
                                    *PLATE_DATUMS],
                        supports=slab_hosts, assembly_id=closure_assembly,
                        part_role='support',
                        rule_refs=['HT-INV-01', 'HT-INV-03', 'HT-INV-04'],
                        reason=('Short-edge closure bracket from actual slab material '
                                'through the source skin to the weather plane. '
                                'Connection and cantilever capacity remain unchecked.'))
                    closure_hosts = [bracket_id]
                else:
                    closure_hosts = _skin_base_hosts(b, bay)
                b.add(f'ENV-CLOSE-{level.id}-S{si:03d}', 'wall_panel', 'envelope',
                      'edge_closure', bay.quad(0.0, 1.0, z_base, z_head),
                      env.wall_material, level_id=level.id, lattice_index=bay.index,
                      datum_refs=['mullion_module_m', 'envelope_offset_m', *PLATE_DATUMS],
                      thickness_m=env.wall_thickness_m or env.cladding_depth_m,
                      supports=closure_hosts,
                      assembly_id=closure_assembly,
                      part_role='enclosure' if high_tech else None,
                      rule_refs=['ENVELOPE-CLOSURE-UNRESOLVED-GRAMMAR'] + (
                          ['HT-INV-01', 'HT-INV-03', 'HT-INV-04']
                          if high_tech else []),
                      reason=f'Conceptual solid closure of a {span:.3f} m boundary '
                             f'fragment: an opening and both jambs cannot retain the '
                             f'{min_fragment:.3f} m guide minimum. Local grammar fit '
                             'requires review; omitting the wall would leave a real hole.')
                continue

            if env.opening_logic == 'subtract':
                _bay_punched(b, bay, env, datums, min_fragment)
            elif env.opening_logic == 'recess':
                _bay_recessed(
                    b, bay, env, datums, row_z, mullion_profile, system_depth,
                    use=uses.get(si, _BayProgram(
                        'public', 'unassigned_facade_program',
                        'explicit_fallback:no_program_region')),
                    secondary_count=max(1, secondary_count),
                    submodule_target=module, spec=high_tech_spec,
                    depth_rule=depth_rule, depth_reason=depth_reason,
                    standard=standard_high_tech_bay)
            elif env.opening_logic == 'overlay':
                _bay_backing(b, bay, env, row_z, opaque_fraction)
                if env.outboard == 'lattice':
                    _bay_lattice(b, bay, env, max(2, env.outboard_rows_per_storey))
                elif env.outboard == 'field':
                    # A field is made of small panels, but not of offcuts. The
                    # column and row counts are capped so no panel face falls below
                    # the minimum the grammar's guide publishes.
                    columns = max(1, min(int(round(module / 0.9)),
                                         int(bay.width / (min_fragment * 1.15))))
                    rows = max(1, min(env.outboard_rows_per_storey,
                                      int(bay.height / (min_fragment * 1.15))))
                    _bay_field(b, bay, env, rows, columns, level_t)
            else:
                _bay_subdivided(b, bay, env, datums,
                                opaque=si in opaque_set, row_z=row_z,
                                spandrel_height=spandrel_height,
                                mullion_profile=mullion_profile, course=course)

            # Polyphony's second voice. An overlay family already has one -- the
            # lattice or the field *is* the second voice -- so adding a fin there
            # would be saying the same thing twice. A framed or punched elevation has
            # no second layer of its own, so the fin is what keeps polyphony reaching
            # geometry in those families instead of quietly dropping out of the model.
            if layers >= 2 and env.outboard == 'none':
                _emit_screen_fin(
                    b, bay, env, abs(offset),
                    use=uses.get(si) if high_tech else None,
                    assembly_id=high_tech_assembly)

            # The shading comb survives from the original emitter, on the families
            # whose skin has room for it. A punched wall or a lattice already does this
            # work with its own depth, and adding a comb would be saying it twice.
            if (layers >= 3 and bay.is_principal
                    and env.opening_logic in ('subdivide', 'recess')):
                _emit_shading(
                    b, bay, datums, shading_rows, module, env,
                    use=uses.get(si) if high_tech else None,
                    assembly_id=high_tech_assembly)

    if env.outboard == 'order':
        _emit_applied_order(b, env, lattice, datums)
    if high_tech:
        _finalize_high_tech_metadata(b)


def _emit_entrance(
        b, bay: _Bay, env: EnvelopeTectonic, entrance: EntrancePlan, *,
        assembly_id: str | None = None, use: _BayProgram | None = None) -> None:
    """One paired screen on the actual slab edge, with a closed offset-skin reveal."""
    skin_width = math.hypot(bay.skin_nxt.x-bay.skin_point.x,
                            bay.skin_nxt.y-bay.skin_point.y)
    jamb = (skin_width - entrance.width_m) / 2.0
    low, high = jamb / skin_width, 1.0 - jamb / skin_width
    head_z = min(bay.z_head, bay.z_base + ENTRANCE_HEAD_M)
    refs = ['flight_width_m', 'mullion_module_m', *PLATE_DATUMS]
    category = use.category if use else 'public'
    program = use.program if use else 'structure'
    ht_rules = [
        'HT-INV-01', 'HT-INV-03', 'HT-INV-04', 'HT-SPECIAL-COMPONENT',
        'HT-PROGRAM-HUMAN-EXEMPT'
    ] if assembly_id else []
    skin_angle = math.atan2(bay.skin_nxt.y-bay.skin_point.y,
                            bay.skin_nxt.x-bay.skin_point.x)
    jamb_ids = []
    for index, t in enumerate((low / 2.0, (1.0 + high) / 2.0)):
        jamb_id = f'ENV-ENT-{bay.level_id}-S{bay.si:03d}-J{index}'
        jamb_ids.append(jamb_id)
        jamb_foot = bay.at(t, bay.z_base, skin=True)
        bracket_supports = []
        if assembly_id:
            slab_anchor = _nearest_slab_anchor(
                b, bay.level_id, jamb_foot,
                bay.z_base - EDGE_RETURN_THICKNESS_M)
            if slab_anchor:
                _distance, slab_id, _slab_geometry, anchor = slab_anchor
                bracket_id = f'ENV-ENT-{bay.level_id}-S{bay.si:03d}-B{index}'
                b.add(
                    bracket_id, 'external_strut', 'envelope', 'entrance',
                    MemberGeometry(path=_member_path(
                        v3(anchor.x, anchor.y,
                           bay.z_base - EDGE_RETURN_THICKNESS_M),
                        v3(anchor.x, anchor.y, bay.z_base),
                        jamb_foot,
                    ), profile=EDGE_BRACKET_PROFILE, roll=bay.roll),
                    env.trim_material, level_id=bay.level_id,
                    lattice_index={**bay.index, 'entry_interface': index},
                    category=category, program=program, datum_refs=refs,
                    supports=[slab_id], assembly_id=assembly_id,
                    part_role='support',
                    rule_refs=['MTA-ENTRANCE-SHARED-THRESHOLD', *ht_rules],
                    reason=('Entrance jamb bracket routed from the nearest actual slab '
                            'material to the jamb foot. Connection capacity remains '
                            'professional_review_required.'))
                bracket_supports = [bracket_id]
        b.add(jamb_id, 'wall_panel',
              'envelope', 'entrance', BoxGeometry(
                  center=bay.at(t, (bay.z_base+bay.z_head)/2.0, skin=True),
                  size=v3(jamb, ENTRANCE_REVEAL_DEPTH_M, bay.height), rotation_z=skin_angle),
              env.wall_material, level_id=bay.level_id, lattice_index=bay.index,
              category=category, program=program, datum_refs=refs,
              supports=bracket_supports,
              assembly_id=assembly_id, part_role='enclosure' if assembly_id else None,
              rule_refs=['MTA-ENTRANCE-SHARED-THRESHOLD', *ht_rules],
              reason='Solid entry jamb outside the shared clear opening; conceptual '
                     '450 mm reveal assembly, with hardware and weather joints unverified.')
    for index, (t0, t1) in enumerate(((low, 0.5), (0.5, high))):
        b.add(f'ENV-ENT-{bay.level_id}-S{bay.si:03d}-L{index}', 'entrance_door',
              'envelope', 'entrance', bay.quad(t0, t1, bay.z_base, head_z, skin=True),
              env.infill_material, level_id=bay.level_id, lattice_index=bay.index,
              category=category, program=program, datum_refs=refs,
              thickness_m=env.glazing_depth_m,
              supports=([jamb_ids[index]] if assembly_id else ()),
              assembly_id=assembly_id,
              part_role='glazing' if assembly_id else None,
              rule_refs=['MTA-ENTRANCE-SHARED-THRESHOLD', *ht_rules],
              reason=f'Paired entry leaf, {entrance.width_m * 500:.0f} mm, on the '
                     'actual slab edge and shared approach centre. Door capacity and '
                     'operating hardware remain review items.')
    if bay.z_head - head_z > 0.05:
        b.add(f'ENV-ENT-{bay.level_id}-S{bay.si:03d}-HD', 'entrance_head', 'envelope',
              'entrance', bay.quad(0.0, 1.0, head_z, bay.z_head, skin=True),
              env.wall_material, level_id=bay.level_id, lattice_index=bay.index,
              category=category, program=program, datum_refs=refs,
              thickness_m=env.cladding_depth_m,
              supports=jamb_ids if assembly_id else (), assembly_id=assembly_id,
              part_role='enclosure' if assembly_id else None,
              rule_refs=ht_rules,
              reason='Panel over the entrance head: the wall resumes above the '
                     'opening rather than the opening running to the soffit.')
    for index, fraction in enumerate((0.0, 1.0)):
        inner, outer = bay.at(fraction, bay.z_base, skin=True), bay.at(fraction, bay.z_base)
        if math.hypot(inner.x-outer.x, inner.y-outer.y) <= GEOMETRY_EPS_M:
            continue
        b.add(f'ENV-ENT-{bay.level_id}-S{bay.si:03d}-RV{index}', 'window_reveal',
              'envelope', 'entrance', QuadGeometry(corners=[inner, outer,
                  v3(outer.x, outer.y, bay.z_head), v3(inner.x, inner.y, bay.z_head)]),
              env.trim_material, level_id=bay.level_id, lattice_index=bay.index,
              category=category, program=program,
              thickness_m=env.cladding_depth_m, datum_refs=refs,
              supports=([jamb_ids[index]] if assembly_id else ()),
              assembly_id=assembly_id,
              part_role='enclosure' if assembly_id else None,
              rule_refs=ht_rules,
              reason='Side return joins the re-registered entrance jamb to the '
                     'actual offset facade edge; no adjacent infill spans the opening.')


def _emit_screen_fin(
        b, bay: _Bay, env: EnvelopeTectonic, offset: float, *,
        use: _BayProgram | None = None,
        assembly_id: str | None = None) -> None:
    """The second envelope voice on a family that has no outboard layer of its own.

    The standoff is checked against the sectional cut, not just the station it hangs
    from. A fin on the last visible bay of the south face projects sideways at the
    corner and can land a few centimetres into the cut region, which reads in a
    render as one stray member floating past the end of the wall.
    """
    depth = max(0.12, offset * 0.55)
    dx, dy = bay.outward(depth)
    if not b.lattice.encloses(bay.point.x + dx, bay.point.y + dy):
        return
    # What holds the fin out there. A fin stands off the skin by `depth`, so its
    # centre-line never crosses the carrier's and no amount of geometry inspection
    # will pair the two -- the relation has to be declared. Emitted without one, the
    # fin was the largest floating population in the model: a rule downstream guessed
    # a host for it afterwards, which reads as an answer while resting on nothing.
    # It brackets back to the carrier standing at the same bay station.
    # A mullion at the same bay station where the family has one. Several families
    # have none -- a punched wall carries its skin in the wall itself -- and there the
    # fin brackets back to the floor-edge fascia running along the plate at its base,
    # which is the member a bracket would reach in the built version too.
    controlled = getattr(b.lattice, 'facade_control', None) is not None
    high_tech = assembly_id is not None
    station_candidates = (
        f'ENV-MUL-{bay.level_id}-S{bay.si:03d}',
        f'ENV-FRM-{bay.level_id}-S{bay.si:03d}',
        f'ENV-STR-{bay.level_id}-S{bay.si:03d}',
    )
    # A controlled Program Volume facade owns the station. Prefer the mullion at
    # that exact station, so a fin's return is visible in section and shares an axis
    # node with the enclosure. High-Tech keeps its expressed frame priority when no
    # curtain-wall mullion exists at that station.
    carrier = next((candidate for candidate in station_candidates
                    if candidate in b.element_ids), None)
    if carrier is None:
        carrier = b.axis.nearest_owner(
            v3(bay.point.x + dx, bay.point.y + dy, bay.z_base),
            f'STR-FAS-{bay.level_id}-')
    if carrier is None:
        return
    fin_base = v3(bay.point.x + dx, bay.point.y + dy, bay.z_base)
    # ``Builder.add`` may inject a stable FACADE assembly_id after this function
    # returns. Tie-back geometry therefore follows the controlled-facade contract,
    # not the presence of the optional High-Tech assembly argument.
    fin_path = ([v3(bay.point.x, bay.point.y, bay.z_base), fin_base,
                 v3(fin_base.x, fin_base.y, bay.z_head)]
                if controlled or high_tech else
                [fin_base, v3(fin_base.x, fin_base.y, bay.z_head)])
    b.add(f'ENV-SCR-{bay.level_id}-S{bay.si:03d}', 'screen_fin', 'envelope', 'screen',
          MemberGeometry(
              path=fin_path,
              profile=b.profile(convention_profile(
                  f'SCREEN-{depth * 1000 * 0.75:.0f}x50', 'box', depth * 0.75, 0.050)),
              roll=bay.roll),
          env.trim_material, level_id=bay.level_id, lattice_index=bay.index,
          category=use.category if use else 'public',
          program=use.program if use else 'structure',
          datum_refs=['envelope_layer_count', 'envelope_offset_m'],
          supports=[carrier],
          assembly_id=assembly_id,
          part_role='support' if high_tech else None,
          rule_refs=['POLYPHONY_TO_ENVELOPE_LAYERS'] + (
              ['PV-FACADE-DECLARED-SUPPORT'] if controlled else []) + (
              ['HT-INV-01', 'HT-INV-03', 'HT-INV-04'] if high_tech else []),
          reason='Screen fin: the second envelope voice, standing off the skin so both '
                 'layers stay readable. Bracketed back to the carrier at its bay.')


def _emit_shading(
        b, bay: _Bay, datums, shading_rows: int, module: float,
        env: EnvelopeTectonic | None = None, *, use: _BayProgram | None = None,
        assembly_id: str | None = None) -> None:
    depth = datums.value('shading_depth_m')
    for k in range(shading_rows):
        z = bay.z_base + bay.height * (0.40 + 0.26 * k)
        if z > bay.z_head - 0.1:
            break
        centre = bay.at(0.5, z)
        dx, dy = bay.outward(depth / 2.0)
        b.add(f'ENV-BRS-{bay.level_id}-S{bay.si:03d}-R{k:02d}', 'brise_soleil',
              'envelope', 'shading',
              BoxGeometry(center=v3(centre.x + dx, centre.y + dy, z),
                          size=v3(bay.width, depth, 0.06), rotation_z=bay.angle),
              env.trim_material if env else 'white_soft',
              category=use.category if use else 'public',
              program=use.program if use else 'structure',
              level_id=bay.level_id, lattice_index={**bay.index, 'row': k},
              datum_refs=['shading_rows', 'shading_depth_m'],
              supports=([f'ENV-FRM-{bay.level_id}-S{bay.si:03d}']
                        if assembly_id else ()),
              assembly_id=assembly_id, part_role='support' if assembly_id else None,
              rule_refs=['TENSION_TO_SHADING_DEPTH'] + (
                  ['HT-INV-01', 'HT-INV-03', 'HT-INV-04'] if assembly_id else []),
              reason='Shading comb: the third envelope voice, at the projection the '
                     'release set.')
