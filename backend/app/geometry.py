"""The four geometry primitives of decision 0008, plus the section-profile bridge.

The v2 contract had one primitive: an oriented bounding box. Thirty-two of the
thirty-eight element kinds in the target taxonomy cannot be expressed with it. This
module supplies the missing three and the profile library that makes a `member` read as
steel rather than as a rectangular bar.

    box        centre + size + one rotation      (already possible in v2)
    member     a path of two or more points, swept with a named section profile
    extrusion  an arbitrary closed polygon with holes, between two levels
    quad       a free four-point panel in space

The profile bridge is the point where the load calculation becomes visible geometry:
`sizing.py` selects a section, `SectionProperties.id` names it, and
`profile_from_section_id` turns that name back into the outline Blender sweeps. A member
drawn here is the member that was checked.
"""

from __future__ import annotations

import math
import re
from typing import Literal

from pydantic import BaseModel, Field


class Vector2(BaseModel):
    x: float
    y: float


class Vector3(BaseModel):
    x: float
    y: float
    z: float

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


def v3(x: float, y: float, z: float) -> Vector3:
    return Vector3(x=round(x, 5), y=round(y, 5), z=round(z, 5))


def v2(x: float, y: float) -> Vector2:
    return Vector2(x=round(x, 5), y=round(y, 5))


# ---------------------------------------------------------------------------
# Section profiles
# ---------------------------------------------------------------------------

ProfileShape = Literal['i_section', 'box', 'chs', 'rectangle', 'plate']


class ProfileSpec(BaseModel):
    """A drawable section. Dimensions in metres, matching the geometry they appear in.

    `source` records where the size came from: `sized` means a load calculation chose
    it, `convention` means it is an architectural dimension that no check governs (a
    railing, a mullion, a tread). Nothing may present a `convention` member as verified.
    """

    id: str
    shape: ProfileShape
    depth_m: float = Field(gt=0)
    width_m: float = Field(gt=0)
    web_m: float = Field(default=0.0, ge=0)
    flange_m: float = Field(default=0.0, ge=0)
    source: Literal['sized', 'convention'] = 'convention'

    def outline(self) -> list[tuple[float, float]]:
        """Section outline in the member's local (u, v) plane, closed, counter-clockwise."""
        d, b = self.depth_m, self.width_m
        if self.shape == 'i_section':
            tw, tf = self.web_m / 2.0, self.flange_m
            hb, hd = b / 2.0, d / 2.0
            return [(-hb, -hd), (hb, -hd), (hb, -hd + tf), (tw, -hd + tf),
                    (tw, hd - tf), (hb, hd - tf), (hb, hd), (-hb, hd),
                    (-hb, hd - tf), (-tw, hd - tf), (-tw, -hd + tf), (-hb, -hd + tf)]
        if self.shape == 'box':
            hb, hd = b / 2.0, d / 2.0
            return [(-hb, -hd), (hb, -hd), (hb, hd), (-hb, hd)]
        if self.shape == 'chs':
            r, sides = d / 2.0, 10
            return [(math.cos(2 * math.pi * k / sides) * r,
                     math.sin(2 * math.pi * k / sides) * r) for k in range(sides)]
        hb, hd = b / 2.0, d / 2.0
        return [(-hb, -hd), (hb, -hd), (hb, hd), (-hb, hd)]


_I_ID = re.compile(r'^I-(\d+)x(\d+)x(\d+)x(\d+)$')
_SHS_ID = re.compile(r'^SHS-(\d+)x(\d+)x([\d.]+)$')
_CHS_ID = re.compile(r'^CHS-(\d+)x([\d.]+)$')
_GL_ID = re.compile(r'^GL-(\d+)x(\d+)$')
# Cast rectangular concrete, `RC-<depth>x<width>` in millimetres. Same shape as a
# glulam member and deliberately a separate pattern: the id has to say which
# material was checked, because the capacity equations behind them are different
# codes entirely.
_RC_ID = re.compile(r'^RC-(\d+)x(\d+)$')


def profile_from_section_id(section_id: str) -> ProfileSpec:
    """Turn a section chosen by `sizing.py` into a drawable profile.

    This is the bridge that makes the load calculation visible: the member rendered is
    the member that was checked, at the size the check produced.
    """
    match = _I_ID.match(section_id)
    if match:
        d, bf, tw, tf = (float(g) / 1000.0 for g in match.groups())
        return ProfileSpec(id=section_id, shape='i_section', depth_m=d, width_m=bf,
                           web_m=tw, flange_m=tf, source='sized')
    match = _SHS_ID.match(section_id)
    if match:
        h, b, t = (float(g) / 1000.0 for g in match.groups())
        return ProfileSpec(id=section_id, shape='box', depth_m=h, width_m=b,
                           web_m=t, source='sized')
    match = _CHS_ID.match(section_id)
    if match:
        od, t = (float(g) / 1000.0 for g in match.groups())
        return ProfileSpec(id=section_id, shape='chs', depth_m=od, width_m=od,
                           web_m=t, source='sized')
    match = _GL_ID.match(section_id)
    if match:
        d, b = (float(g) / 1000.0 for g in match.groups())
        return ProfileSpec(id=section_id, shape='rectangle', depth_m=d, width_m=b,
                           source='sized')
    match = _RC_ID.match(section_id)
    if match:
        d, b = (float(g) / 1000.0 for g in match.groups())
        return ProfileSpec(id=section_id, shape='rectangle', depth_m=d, width_m=b,
                           source='sized')
    raise ValueError(f'unrecognised section id: {section_id}')


def convention_profile(
    profile_id: str, shape: ProfileShape, depth_m: float, width_m: float,
    web_m: float = 0.0, flange_m: float = 0.0,
) -> ProfileSpec:
    return ProfileSpec(id=profile_id, shape=shape, depth_m=depth_m, width_m=width_m,
                       web_m=web_m, flange_m=flange_m, source='convention')


# Architectural dimensions that no structural check governs. They are declared here as
# conventions so that a report can separate them from sized members without guessing.
CONVENTION_PROFILES: dict[str, ProfileSpec] = {
    profile.id: profile for profile in (
        convention_profile('MULL-75x240', 'box', 0.240, 0.075),
        convention_profile('TRAN-75x140', 'box', 0.140, 0.075),
        convention_profile('FASCIA-200x550', 'box', 0.550, 0.200),
        convention_profile('PARAPET-200x580', 'box', 0.580, 0.200),
        convention_profile('RAIL-CHS64', 'chs', 0.064, 0.064, web_m=0.006),
        convention_profile('POST-45x45', 'box', 0.045, 0.045),
        convention_profile('STRINGER-180x450', 'box', 0.450, 0.180),
        convention_profile('PURLIN-120x200', 'box', 0.200, 0.120),
        convention_profile('TRUSSWEB-130', 'box', 0.130, 0.130),
        convention_profile('TRUSSCHORD-200x260', 'box', 0.260, 0.200),
        convention_profile('STRUT-CHS180', 'chs', 0.180, 0.180, web_m=0.010),
        convention_profile('EDGEBEAM-160', 'box', 0.160, 0.160),
    )
}


# ---------------------------------------------------------------------------
# The four primitives
# ---------------------------------------------------------------------------

class BoxGeometry(BaseModel):
    type: Literal['box'] = 'box'
    center: Vector3
    size: Vector3
    rotation_z: float = 0.0


class MemberGeometry(BaseModel):
    """A path of two or more points swept with a named profile.

    Two points give a straight member. More than two give a curved one, which the timber
    gridshell system needs and which no v2 element could express.
    """

    type: Literal['member'] = 'member'
    path: list[Vector3] = Field(min_length=2)
    profile: str
    roll: Vector3 = Field(default_factory=lambda: Vector3(x=0.0, y=0.0, z=1.0))


class ExtrusionGeometry(BaseModel):
    type: Literal['extrusion'] = 'extrusion'
    boundary: list[Vector2] = Field(min_length=3)
    holes: list[list[Vector2]] = Field(default_factory=list)
    z_base: float
    z_top: float


class QuadGeometry(BaseModel):
    type: Literal['quad'] = 'quad'
    corners: tuple[Vector3, Vector3, Vector3, Vector3]


Geometry = BoxGeometry | MemberGeometry | ExtrusionGeometry | QuadGeometry


# ---------------------------------------------------------------------------
# Derived bounding data, so v2 consumers keep working
# ---------------------------------------------------------------------------

def bounds(geometry: Geometry) -> tuple[Vector3, Vector3]:
    """Axis-aligned centre and size. Read-only compatibility data for the viewport
    filters, the Grasshopper reader, and the mapping report -- never the authority."""
    if isinstance(geometry, BoxGeometry):
        return geometry.center, geometry.size
    if isinstance(geometry, MemberGeometry):
        points = [p.as_tuple() for p in geometry.path]
        profile = CONVENTION_PROFILES.get(geometry.profile)
        pad = max(profile.depth_m, profile.width_m) / 2.0 if profile else 0.15
    elif isinstance(geometry, ExtrusionGeometry):
        points = [(p.x, p.y, geometry.z_base) for p in geometry.boundary] + \
                 [(p.x, p.y, geometry.z_top) for p in geometry.boundary]
        pad = 0.0
    else:
        points = [p.as_tuple() for p in geometry.corners]
        pad = 0.0
    lows = [min(p[i] for p in points) - pad for i in range(3)]
    highs = [max(p[i] for p in points) + pad for i in range(3)]
    return (
        v3(*[(lows[i] + highs[i]) / 2.0 for i in range(3)]),
        v3(*[max(highs[i] - lows[i], 0.01) for i in range(3)]),
    )


# ---------------------------------------------------------------------------
# Polygon helpers shared by the datum layer and the emitters
# ---------------------------------------------------------------------------

def inset(polygon: list[Vector2], amount: float) -> list[Vector2]:
    cx = sum(p.x for p in polygon) / len(polygon)
    cy = sum(p.y for p in polygon) / len(polygon)
    out: list[Vector2] = []
    for point in polygon:
        dx, dy = point.x - cx, point.y - cy
        distance = math.hypot(dx, dy) or 1.0
        out.append(v2(point.x - dx / distance * amount, point.y - dy / distance * amount))
    return out


def point_inside(polygon: list[Vector2], x: float, y: float) -> bool:
    hit = False
    count = len(polygon)
    for index in range(count):
        a, b = polygon[index], polygon[(index + 1) % count]
        if (a.y > y) != (b.y > y):
            crossing = a.x + (y - a.y) / (b.y - a.y) * (b.x - a.x)
            if x < crossing:
                hit = not hit
    return hit


def polyline_stations(
    polygon: list[Vector2], spacing: float,
) -> list[tuple[Vector2, float]]:
    """Evenly spaced points along a closed polyline, with the local tangent angle.

    This is the envelope's registration: mullions, transoms, and panels all index into
    the station list, so the module stays constant however the plan changes shape.
    """
    out: list[tuple[Vector2, float]] = []
    count = len(polygon)
    carry = 0.0
    for index in range(count):
        a, b = polygon[index], polygon[(index + 1) % count]
        segment = math.hypot(b.x - a.x, b.y - a.y)
        if segment < 1e-9:
            continue
        distance = carry
        while distance < segment:
            f = distance / segment
            out.append((v2(a.x + (b.x - a.x) * f, a.y + (b.y - a.y) * f),
                        math.atan2(b.y - a.y, b.x - a.x)))
            distance += spacing
        carry = distance - segment
    return out


def superellipse(
    half_x: float, half_y: float, exponent: float, samples: int = 240,
) -> list[Vector2]:
    points: list[Vector2] = []
    for index in range(samples):
        angle = 2.0 * math.pi * index / samples
        c, s = math.cos(angle), math.sin(angle)
        points.append(v2(half_x * math.copysign(abs(c) ** (2.0 / exponent), c),
                         half_y * math.copysign(abs(s) ** (2.0 / exponent), s)))
    return points


def resample_by_arclength(polygon: list[Vector2], count: int) -> list[Vector2]:
    lengths = [0.0]
    for index in range(len(polygon)):
        a, b = polygon[index], polygon[(index + 1) % len(polygon)]
        lengths.append(lengths[-1] + math.hypot(b.x - a.x, b.y - a.y))
    total = lengths[-1]
    out: list[Vector2] = []
    cursor = 0
    for step in range(count):
        target = total * step / count
        while lengths[cursor + 1] < target:
            cursor += 1
        span = lengths[cursor + 1] - lengths[cursor]
        f = 0.0 if span <= 0 else (target - lengths[cursor]) / span
        a, b = polygon[cursor], polygon[(cursor + 1) % len(polygon)]
        out.append(v2(a.x + (b.x - a.x) * f, a.y + (b.y - a.y) * f))
    return out
