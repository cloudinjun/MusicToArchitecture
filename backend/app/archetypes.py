"""Type-specific space the band allocator cannot invent, carved before it runs.

`allocate_program` differentiates typologies by room list, area and adjacency, and
then lays every one of them out the same way: strips cut from the plate, rectangles
filled left to right. That machinery cannot produce the room a theatre *is* -- a floor
that rakes so a fifth row sees the stage over the fourth, plates removed above it so
the volume exists, a stage joined to it through one opening and walled everywhere
else. Decision 0016 names this layer the spatial archetype and has the theatre build
it first, because the theatre stresses every part of the interface.

The contract with the allocator is deliberately small. A carver runs on the lattice
before allocation and returns three things: the archetype's own rooms as finished
zones (`preplaced`), the floor they stand on as reservations the allocator must lay
out around (`carved`), and the plates they remove above themselves (`removed`, applied
to the lattice as voids -- the same mechanism an atrium already uses, so every
downstream consumer that respects a void respects the archetype without being taught
to). A carver that cannot fit refuses with a reason instead of degrading: the refused
rooms are reported unplaced, `fits` goes false, and the plate fit grows toward a plate
the archetype can stand on -- rather than quietly housing an auditorium as the flat
rectangle the archetype exists to replace.

Sectional sovereignty, as 0016 decides it: the numbers here that describe *what a
theatre is* -- eye height, row depth, the sightline clearance -- are the typology's and
are constants; the music goes on owning everything the typology leaves open. Every
constant cites practice, is derived into geometry by arithmetic a person can check,
and is then *measured back* off the emitted geometry by `evaluate_archetype`, because
a status must be earned by a measurement, not by the derivation that promised it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .datums import DatumSet, Lattice
from .geometry import point_inside
from .program import AllocatedZone, UnplacedSpace, plate_x_runs


# --- what a theatre is, in numbers a person can check -------------------------------

# Seated eye above the row floor. Anthropometric practice (Neufert gives 1.10-1.25).
SEATED_EYE_M = 1.20
# Row-to-row depth for fixed seating with reasonable legroom.
ROW_DEPTH_M = 0.95
# The rake is derived to this clearance -- the vertical gap between one spectator's
# sightline to the focal point and the eye of the spectator in front. 60 mm is the
# accepted minimum for every-row vision; deriving to 90 leaves the gate real margin.
C_VALUE_DESIGN_M = 0.09
C_VALUE_MIN_M = 0.06
# Flat floor between the proscenium line and the first row: forestage edge and the
# front cross-aisle.
FIRST_ROW_OFFSET_M = 2.7
# Cross-aisle behind the last row.
BACK_AISLE_M = 1.2
# Stage floor above the house floor at row one. Practice: 0.8-1.1 m.
STAGE_RISE_M = 0.9
# Clear height over the back row: sightline to a proscenium header, acoustic volume
# and services. Practice, not code, and labelled as such.
BACK_CLEARANCE_M = 4.0
# Clear height over the stage without a fly tower. The tower is its own phase in
# decision 0016; until it exists the stage gets a working-grid height, not a claim
# that scenery can fly.
STAGE_CLEAR_M = 8.0
# Proscenium opening: practice for a mid-size house.
PROSCENIUM_MAX_W_M = 14.0

Rect = tuple[float, float, float, float]


class BowlRow(BaseModel):
    """One row of the derived rake, before it is geometry.

    Offsets are unsigned distances from the proscenium line; the carve's
    `audience_dx` says which way they run in plan.
    """

    index: int
    offset_front_m: float
    offset_back_m: float
    distance_m: float          # eye to the focal point, in plan
    floor_m: float             # row floor above the house slab
    eye_m: float               # floor + seated eye


class Carve(BaseModel):
    """What every archetype hands the compiler, whatever its typology.

    The theatre built this interface (decision 0016) and the other typologies now
    speak it: rooms placed as finished zones, the floor they stand on reserved, the
    plates their section removes, the walls that must run their full height. The
    compiler's plumbing -- voids, core keep-out, stranding refusal, preplacement --
    reads only these fields, so a new archetype is a new carver and its gates, not
    new plumbing.
    """

    archetype_id: str
    # space id -> the rectangle the archetype gave it. What the gates measure.
    rooms: dict[str, Rect]
    zones: list[AllocatedZone]
    # Floor the allocator must lay out around, per level index.
    reservations: dict[int, list[Rect]]
    # Plates removed over the carved volumes, per level index, applied as voids.
    removed: dict[int, list[Rect]] = Field(default_factory=dict)
    # Enclosure walls that must run the full carved height, keyed by space id.
    tall_walls_m: dict[str, float] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class TheatreCarve(Carve):
    """The theatre's carve: the bowl, the stage, and the wall between them."""

    archetype_id: Literal['ARCH-THEATRE-BOWL'] = 'ARCH-THEATRE-BOWL'
    house: Rect
    stage: Rect
    # Which way the audience extends from the proscenium line: +1 means the rake
    # climbs toward +x (stage at the west end), -1 the reverse.
    audience_dx: int
    proscenium_x: float
    proscenium_w_m: float
    focal_h_m: float           # above the house slab
    clear_house_m: float
    clear_stage_m: float
    rows: list[BowlRow]


class MuseumCarve(Carve):
    """The museum's carve: an enfilade of top-lit galleries on the top plate."""

    archetype_id: Literal['ARCH-GALLERY-SEQUENCE'] = 'ARCH-GALLERY-SEQUENCE'
    level_index: int
    # The party wall between the galleries, and the portal through it that makes
    # the pair a sequence rather than two rooms. Straight pairs share a wall
    # running along y ('y'); a pair wrapped around a courtyard corner shares one
    # running along x ('x').
    party_axis: Literal['x', 'y']
    party_pos: float
    party_lo: float
    party_hi: float
    portal_w_m: float
    wall_h_m: float


class LibraryCarve(Carve):
    """The library's carve: the reading room as a daylit double-height volume."""

    archetype_id: Literal['ARCH-READING-ROOM'] = 'ARCH-READING-ROOM'
    level_index: int
    clear_m: float


class PavilionCarve(Carve):
    """The pavilion's carve: the hall as the full-height volume the type is."""

    archetype_id: Literal['ARCH-HALL'] = 'ARCH-HALL'
    level_index: int
    clear_m: float


class CarveRefusal(BaseModel):
    """The archetype could not stand here, and the reason it could not."""

    archetype_id: str
    precluded: list[UnplacedSpace]
    reason: str


def derive_bowl(house_w_m: float, focal_h_m: float = STAGE_RISE_M) -> list[BowlRow]:
    """The rake, from the sightline recurrence and nothing else.

    Row one sits on the flat slab. Each next eye is placed so its sightline to the
    focal point passes `C_VALUE_DESIGN_M` above the eye in front:

        h[i+1] = hf + (h[i] + C - hf) * d[i+1] / d[i]

    which is the similar-triangles statement of that sentence, solvable by hand for
    any row. Distances are measured to the row's seat line, half a row behind its
    front edge.
    """
    usable = house_w_m - FIRST_ROW_OFFSET_M - BACK_AISLE_M
    count = int(usable // ROW_DEPTH_M)
    rows: list[BowlRow] = []
    eye = SEATED_EYE_M
    for index in range(count):
        distance = FIRST_ROW_OFFSET_M + (index + 0.5) * ROW_DEPTH_M
        if index > 0:
            previous = rows[-1].distance_m
            eye = focal_h_m + (rows[-1].eye_m + C_VALUE_DESIGN_M - focal_h_m) \
                * distance / previous
        rows.append(BowlRow(
            index=index,
            offset_front_m=round(FIRST_ROW_OFFSET_M + index * ROW_DEPTH_M, 4),
            offset_back_m=round(FIRST_ROW_OFFSET_M + (index + 1) * ROW_DEPTH_M, 4),
            distance_m=round(distance, 4),
            floor_m=round(eye - SEATED_EYE_M, 4),
            eye_m=round(eye, 4)))
    return rows


def _refuse(archetype_id: str, brief_spaces, reason: str) -> CarveRefusal:
    return CarveRefusal(
        archetype_id=archetype_id,
        precluded=[UnplacedSpace(
            space_id=space.id, label=space.label, area_required_m2=space.area_m2,
            reason=f'the {archetype_id} archetype could not carve this plate: '
                   f'{reason}')
            for space in brief_spaces],
        reason=reason)


def _polygon_area(polygon) -> float:
    total = 0.0
    for index in range(len(polygon)):
        a, b = polygon[index], polygon[(index + 1) % len(polygon)]
        total += a.x * b.y - b.x * a.y
    return abs(total) / 2.0


def _row_index(y_lines: list[float], y: float) -> int:
    for index in range(len(y_lines) - 1):
        if y_lines[index] - 0.01 <= y <= y_lines[index + 1] + 0.01:
            return index
    return 0


def _rect_clear_of(level, rect: Rect) -> bool:
    """Whether a room can actually stand here: on the plate, over no hole.

    A notched or split plate can satisfy the bounding box and still not own these
    corners, and an atrium void is floor that is not there -- standing a gallery
    over either is exactly the error a person catches by looking. Probes are inset
    50 mm so a corner exactly on the plate edge does not fail the boundary test.
    """
    x0, y0, x1, y1 = rect
    probes = ((x0 + 0.05, y0 + 0.05), (x0 + 0.05, y1 - 0.05),
              (x1 - 0.05, y0 + 0.05), (x1 - 0.05, y1 - 0.05),
              ((x0 + x1) / 2.0, y0 + 0.05),
              ((x0 + x1) / 2.0, y1 - 0.05),
              (x0 + 0.05, (y0 + y1) / 2.0),
              (x1 - 0.05, (y0 + y1) / 2.0),
              ((x0 + x1) / 2.0, (y0 + y1) / 2.0))
    if not all(point_inside(level.plate, x, y) for x, y in probes):
        return False
    # A hole wholly inside a large room misses every probe above. Compare the
    # rectangles as well, so a room cannot count absent floor as delivered area.
    for void in level.voids:
        vx0, vx1 = min(p.x for p in void), max(p.x for p in void)
        vy0, vy1 = min(p.y for p in void), max(p.y for p in void)
        if min(x1, vx1) - max(x0, vx0) > 0.01 \
                and min(y1, vy1) - max(y0, vy0) > 0.01:
            return False
    return True


def _plate_x_span(level, y0: float, y1: float) -> tuple[float, float] | None:
    """The common horizontal run an axis-aligned room owns over its full depth."""
    inset = min(0.05, max(0.0, (y1 - y0) / 4.0))
    ys = (y0 + inset, (y0 + y1) / 2.0, y1 - inset)
    runs = []
    for y in ys:
        row = plate_x_runs(level.plate, y, [])
        if not row:
            return None
        runs.append(max(row, key=lambda run: run[1] - run[0]))
    x0 = max(run[0] for run in runs)
    x1 = min(run[1] for run in runs)
    return (x0, x1) if x1 - x0 > 0.1 else None


def _gutted(lattice: Lattice,
            removed: dict[int, list[Rect]]) -> tuple[str, float, float] | None:
    """The level a claim would demolish rather than section, if there is one.

    Gutted means what remains cannot hold a room and the way to it: under a quarter
    of the plate, or under 120 m2, whichever accusation is worse. The loss is
    measured against the plate's bounding box, which overstates it on a rounded
    plate -- a conservative error, in the direction of refusing.
    """
    for level in lattice.occupied[1:]:
        cuts = removed.get(level.index)
        if not cuts:
            continue
        pxs = [p.x for p in level.plate]
        pys = [p.y for p in level.plate]
        area = _polygon_area(level.plate)
        lost = 0.0
        for rx0, ry0, rx1, ry1 in cuts:
            dx = min(rx1, max(pxs)) - max(rx0, min(pxs))
            dy = min(ry1, max(pys)) - max(ry0, min(pys))
            lost += max(0.0, dx) * max(0.0, dy)
        remaining = max(0.0, area - lost)
        share = remaining / area if area > 1.0 else 1.0
        if area > 1.0 and (share < 0.25 or remaining < 120.0):
            return level.id, share, remaining
    return None


def _place_zone(ask, rect: Rect, level, y_lines, *,
                daylight_satisfied: bool = True) -> AllocatedZone:
    """One archetype room as the finished zone the allocator would have made."""
    x0, y0, x1, y1 = rect
    delivered = (x1 - x0) * (y1 - y0)
    return AllocatedZone(
        space_id=ask.id, space_type=ask.space_type, label=ask.label,
        category=ask.category, occupancy_id=ask.occupancy_id,
        level_index=level.index, level_id=level.id,
        band_index=_row_index(y_lines, y0),
        x0=round(x0, 3), y0=round(y0, 3), x1=round(x1, 3), y1=round(y1, 3),
        area_required_m2=ask.area_m2,
        area_delivered_m2=round(delivered, 2),
        area_satisfied=delivered >= ask.area_m2 * ask.area_tolerance,
        area_tolerance=ask.area_tolerance,
        daylight_satisfied=daylight_satisfied,
        level_preference_satisfied=True)


def carve_theatre(lattice: Lattice, datums: DatumSet,
                  brief) -> TheatreCarve | CarveRefusal:
    """Place the house and the stage on the ground plate, and claim their section.

    The pair takes the full depth of the plate with the stage at the east end; the
    foyer, the bar and everything else land west of the house, in the same rows,
    because the band allocator already lays out along the free run of a row. Taking
    the depth whole keeps the house near square -- the first version pinned it to a
    16 m strip and asked a 57 m plate for a 42 m house with the last row 40 m from
    the proscenium, which is not a theatre, it is a corridor facing one. The carve
    runs before the cores are placed and the core search keeps out of it, which is
    the right order of authority: the house is what the building is for, and a
    stair serves it. Deterministic rather than searched: the plate fit already
    searches, and it searches over plates this carver either accepts or refuses.
    """
    house_ask = next((s for s in brief if s.space_type == 'auditorium'), None)
    stage_ask = next((s for s in brief if s.space_type == 'stage'), None)
    if house_ask is None or stage_ask is None:
        return _refuse('ARCH-THEATRE-BOWL',
                       [s for s in (house_ask, stage_ask) if s is not None],
                       'the brief names no auditorium and stage to carve')
    asks = [house_ask, stage_ask]

    def refuse(reason: str) -> CarveRefusal:
        return _refuse('ARCH-THEATRE-BOWL', asks, reason)

    ground = lattice.occupied[0]
    px0 = min(p.x for p in ground.plate)
    px1 = max(p.x for p in ground.plate)
    py1 = max(p.y for p in ground.plate)

    # Depth: whole structural rows from the north edge, snapped to the band grid so
    # the rooms beside the carve sit flush against its wall. Deepest first -- depth
    # is the audience's width and length is its distance from the stage -- capped at
    # 33 m, past which a 680 m2 house is wider than it is deep by more than the
    # fan-shaped precedents this rake is derived from.
    py0 = min(p.y for p in ground.plate)
    candidates = [y for y in lattice.y_lines
                  if y >= py0 - 0.01
                  and house_ask.min_dimension_m <= py1 - y <= 33.0]
    if not candidates:
        return refuse(f'no run of rows offers the house its '
                      f'{house_ask.min_dimension_m:.0f} m minimum dimension '
                      f'on this plate')
    y0 = min(candidates)
    depth = py1 - y0

    stage_w = max(stage_ask.area_m2 / depth, stage_ask.min_dimension_m)
    house_w = max(house_ask.area_m2 / depth, house_ask.min_dimension_m)
    if px1 - px0 < stage_w + house_w + 0.5:
        need = stage_w + house_w
        return refuse(f'house and stage need {need:.1f} m along the plate at '
                      f'{depth:.1f} m deep; this plate offers {px1 - px0:.1f} m')

    # Stage at the east end, audience raking west toward the entry side.
    audience_dx = -1
    stage_x1 = px1
    stage_x0 = house_x1 = stage_x1 - stage_w
    house_x0 = house_x1 - house_w
    proscenium_x = house_x1
    house = (house_x0, y0, house_x1, py1)
    stage = (stage_x0, y0, stage_x1, py1)

    if not (_rect_clear_of(ground, house) and _rect_clear_of(ground, stage)):
        return refuse('the ground plate is notched or holed where the house or '
                      'stage would stand')

    rows = derive_bowl(house_w)
    if len(rows) < 4:
        return refuse(f'a {house_w:.1f} m deep house holds {len(rows)} rows; '
                      f'a bowl needs at least four')
    clear_house = rows[-1].floor_m + BACK_CLEARANCE_M
    clear_stage = STAGE_CLEAR_M

    ground_z = ground.z
    removed: dict[int, list[Rect]] = {}
    for level in lattice.occupied[1:]:
        rise = level.z - ground_z
        cut: list[Rect] = []
        # The plate is cut while any part of its build-up sits inside the claimed
        # clear height; 0.3 m stands in for the slab and its structure.
        if rise < clear_house + 0.3:
            cut.append((house_x0, y0, house_x1, py1))
        if rise < clear_stage + 0.3:
            cut.append((stage_x0, y0, stage_x1, py1))
        if cut:
            removed[level.index] = cut

    # A claim that erases a storey is not a section, it is a demolition. On a bar
    # over a podium the bar stands centred exactly where the house must, so cutting
    # the house's clear height out of it leaves the bar's levels with no floor at
    # all -- and every room allocated up there with no stair that can reach it. That
    # massing needs the tall volume built *for* the stage, which is the fly-tower
    # phase decision 0016 defers; until it exists the carver refuses the pairing
    # rather than gutting it.
    demolished = _gutted(lattice, removed)
    if demolished is not None:
        level_id, share, remaining = demolished
        return refuse(f'the house\'s clear height would leave {level_id} with '
                      f'{share:.0%} of its floor ({remaining:.0f} m2): this '
                      f'massing stands its upper storeys where the house must be, '
                      f'and the tall stage volume that resolves it is the '
                      f'fly-tower phase decision 0016 defers')

    zones = [_place_zone(house_ask, house, ground, lattice.y_lines),
             _place_zone(stage_ask, stage, ground, lattice.y_lines)]

    return TheatreCarve(
        rooms={house_ask.id: (round(house_x0, 3), round(y0, 3),
                              round(house_x1, 3), round(py1, 3)),
               stage_ask.id: (round(stage_x0, 3), round(y0, 3),
                              round(stage_x1, 3), round(py1, 3))},
        house=(round(house_x0, 3), round(y0, 3), round(house_x1, 3), round(py1, 3)),
        stage=(round(stage_x0, 3), round(y0, 3), round(stage_x1, 3), round(py1, 3)),
        audience_dx=audience_dx,
        proscenium_x=round(proscenium_x, 3),
        proscenium_w_m=round(min(PROSCENIUM_MAX_W_M, depth - 3.0), 3),
        focal_h_m=STAGE_RISE_M,
        clear_house_m=round(clear_house, 3), clear_stage_m=round(clear_stage, 3),
        rows=rows, zones=zones,
        reservations={ground.index: [
            (house_x0, y0, house_x1, py1), (stage_x0, y0, stage_x1, py1)]},
        removed=removed,
        tall_walls_m={house_ask.id: round(clear_house, 3),
                      stage_ask.id: round(clear_stage, 3)},
        notes=[
            f'{len(rows)} rows at {ROW_DEPTH_M} m, derived to C = '
            f'{C_VALUE_DESIGN_M * 1000:.0f} mm against a focal point '
            f'{STAGE_RISE_M} m up at the proscenium',
            f'house claims {clear_house:.1f} m clear, stage {clear_stage:.1f} m; '
            f'the fly tower is its own phase (decision 0016)'])


# Enfilade portal: wide enough to move a crated work through and to read as the
# axis of the sequence. Practice, not code.
PORTAL_W_M = 3.0
PORTAL_H_M = 3.6
# Gallery depth past which the room stops being one room under one roof-light zone.
GALLERY_MAX_DEPTH_M = 24.0
# Reading-room depth cap: past this, the far tables are a different room.
READING_MAX_DEPTH_M = 20.0
# Keeps room-edge partitions, doors and their heads on sound floor beside a void.
VOID_EDGE_CLEARANCE_M = 0.30


def carve_museum(lattice: Lattice, datums: DatumSet,
                 brief) -> MuseumCarve | CarveRefusal:
    """The galleries as an enfilade on the top plate, lit from above.

    A museum's type-space is not a room, it is a *sequence* of them: the permanent
    and temporary galleries stand side by side on the topmost plate -- the one place
    daylight can be taken from above and controlled -- joined through one portal in
    a real party wall. The band allocator could put two rectangles somewhere; what
    it cannot do is put them on the roof-lit floor, against each other, with the
    opening that makes them a route. Both galleries ask for `daylight='none'`
    because gallery light is *controlled* light: the top-light this placement earns
    is a claim about the roof over them, stated in the notes and measured by the
    ARCH-TOPLIGHT gate as their standing on the last occupied plate.
    """
    galleries = sorted((s for s in brief if s.space_type == 'exhibition_foyer'),
                       key=lambda s: -s.area_m2)[:2]
    if len(galleries) < 2:
        return _refuse('ARCH-GALLERY-SEQUENCE', galleries,
                       'the brief names fewer than two galleries to sequence')
    a_ask, b_ask = galleries

    def refuse(reason: str) -> CarveRefusal:
        return _refuse('ARCH-GALLERY-SEQUENCE', galleries, reason)

    # The topmost plate that holds the pair. The roof-lit plate is the first choice;
    # where the top plate has stepped or tapered too small -- a slab's upper storeys
    # narrow toward the roof -- the pair takes the highest plate that fits and the
    # plates above it are opened over the galleries, so the light still comes from
    # the roof. Refusing the whole building because its top plate was small is what
    # left a museum with no galleries in the twenty-track audit.
    for host_index in range(len(lattice.occupied) - 1, -1, -1):
        placement = _place_galleries(lattice, lattice.occupied[host_index], a_ask, b_ask)
        if placement is None:
            continue
        rect_a, rect_b, figure = placement
        above = lattice.occupied[host_index + 1:]
        removed = {level.index: [rect_a, rect_b] for level in above}
        demolished = _gutted(lattice, removed)
        if demolished is not None:
            continue
        top = lattice.occupied[host_index]
        break
    else:
        return refuse(f'no plate from {lattice.occupied[-1].id} down holds both '
                      f'galleries at their minimum dimensions clear of the plate edge '
                      f'and its voids, straight or wrapped around the court, without '
                      f'gutting a plate above')

    zones = [_place_zone(a_ask, rect_a, top, lattice.y_lines),
             _place_zone(b_ask, rect_b, top, lattice.y_lines)]
    wall_h = max(2.4, datums.value('floor_to_floor_m')
                 - datums.value('slab_thickness_m') - 0.15)
    if abs(rect_a[0] - rect_b[2]) <= 0.1:
        party_axis, party_pos = 'y', (rect_a[0] + rect_b[2]) / 2.0
        party_lo, party_hi = max(rect_a[1], rect_b[1]), min(rect_a[3], rect_b[3])
    elif abs(rect_a[2] - rect_b[0]) <= 0.1:
        party_axis, party_pos = 'y', (rect_a[2] + rect_b[0]) / 2.0
        party_lo, party_hi = max(rect_a[1], rect_b[1]), min(rect_a[3], rect_b[3])
    elif abs(rect_a[1] - rect_b[3]) <= 0.1:
        party_axis, party_pos = 'x', (rect_a[1] + rect_b[3]) / 2.0
        party_lo, party_hi = max(rect_a[0], rect_b[0]), min(rect_a[2], rect_b[2])
    else:
        party_axis, party_pos = 'x', (rect_a[3] + rect_b[1]) / 2.0
        party_lo, party_hi = max(rect_a[0], rect_b[0]), min(rect_a[2], rect_b[2])
    opened = (f', with {", ".join(level.id for level in above)} opened over them'
              if above else '')
    return MuseumCarve(
        rooms={a_ask.id: rect_a, b_ask.id: rect_b},
        zones=zones,
        reservations={top.index: [rect_a, rect_b]},
        removed=removed,
        level_index=top.index,
        party_axis=party_axis, party_pos=round(party_pos, 3),
        party_lo=round(party_lo, 3), party_hi=round(party_hi, 3),
        portal_w_m=PORTAL_W_M,
        wall_h_m=round(wall_h, 3),
        notes=[f'galleries in enfilade {figure} on {top.id}{opened}, under the roof, '
               f'joined through a {PORTAL_W_M:.1f} m portal in the party wall',
               'gallery light is controlled light: the rooms stand under the roof '
               'and their walls carry no glazing, which is what daylight="none" '
               'means for a collection'])


def _place_galleries(lattice: Lattice, top, a_ask, b_ask):
    """Both galleries on one plate, in line or wrapped around its court, or None."""
    py1 = max(p.y for p in top.plate)
    # Anchor on the northernmost structural row line, not the bounding box: a
    # cantilevered fringe or a rounded corner reaches past the rows along part of
    # the boundary only, and a room anchored to it fails its own corners.
    ny1 = min(py1, lattice.y_lines[-1])

    need = max(a_ask.min_dimension_m, b_ask.min_dimension_m)
    candidates = sorted(
        (y for y in lattice.y_lines
         if need <= ny1 - y <= GALLERY_MAX_DEPTH_M))
    # Deepest cut that actually stands on the plate: a courtyard ring holds a
    # shallow band and a slab holds a deep one, and the difference is measured
    # against the plate and its voids rather than assumed from the family name.
    # The pair starts at the east end and slides west in steps to get clear of an
    # atrium void the music punched into the band.
    straight = None
    for y0 in candidates:
        depth = ny1 - y0
        a_w = max(a_ask.area_m2 / depth, a_ask.min_dimension_m)
        b_w = max(b_ask.area_m2 / depth, b_ask.min_dimension_m)
        span = _plate_x_span(top, y0, ny1)
        if span is None or span[1] - span[0] < a_w + b_w + 0.5:
            continue
        for slide in (0.0, 3.0, 6.0, 9.0, 12.0):
            x1 = span[1] - slide
            if x1 - a_w - b_w < span[0]:
                break
            rect_a = (x1 - a_w, y0, x1, ny1)
            rect_b = (x1 - a_w - b_w, y0, x1 - a_w, ny1)
            if _rect_clear_of(top, rect_a) and _rect_clear_of(top, rect_b):
                straight = (rect_a, rect_b)
                break
        if straight:
            break

    wrapped = None
    if straight is None and top.voids:
        # The courtyard figure uses two sides of the court. Try both assignments:
        # one gallery occupies the long west band and the other turns along the
        # south band, sharing the west gallery's east wall as the enfilade wall.
        void_west = min(min(p.x for p in void) for void in top.voids) \
            - VOID_EDGE_CLEARANCE_M
        void_south = min(min(p.y for p in void) for void in top.voids) \
            - VOID_EDGE_CLEARANCE_M
        y_boundaries = sorted(set(
            round(value, 6)
            for value in (*lattice.y_lines, *(p.y for p in top.plate))))

        for west_ask, south_ask in ((a_ask, b_ask), (b_ask, a_ask)):
            # Solve the south room first. Its available east edge changes as its
            # depth grows down the sloping plate, so converge depth and width.
            south_depth = south_ask.min_dimension_m
            south_rect = None
            for _ in range(5):
                span = _plate_x_span(top, void_south - south_depth, void_south)
                if span is None:
                    break
                available = span[1] - void_west
                if available < south_ask.min_dimension_m:
                    break
                south_depth = max(south_ask.area_m2 / available,
                                  south_ask.min_dimension_m)
                width = south_ask.area_m2 / south_depth
                south_rect = (void_west, void_south - south_depth,
                              void_west + width, void_south)
            if south_rect is None or not _rect_clear_of(top, south_rect):
                continue

            west_rect = None
            for y0 in y_boundaries:
                if y0 > south_rect[1] + 0.01:
                    continue
                for y1 in reversed(y_boundaries):
                    height = y1 - y0
                    if height < west_ask.min_dimension_m \
                            or y1 < south_rect[3] - 0.01:
                        continue
                    span = _plate_x_span(top, y0, y1)
                    if span is None:
                        continue
                    width = max(west_ask.area_m2 / height,
                                west_ask.min_dimension_m)
                    if width > GALLERY_MAX_DEPTH_M \
                            or void_west - width < span[0]:
                        continue
                    candidate = (void_west - width, y0, void_west, y1)
                    if _rect_clear_of(top, candidate):
                        west_rect = candidate
                        break
                if west_rect is not None:
                    break
            if west_rect is None:
                continue
            by_id = {west_ask.id: west_rect, south_ask.id: south_rect}
            wrapped = (by_id[a_ask.id], by_id[b_ask.id])
            break

    if straight is None and wrapped is None:
        return None
    rect_a, rect_b = straight or wrapped
    return rect_a, rect_b, ('in line' if straight is not None else 'around the court')


def carve_library(lattice: Lattice, datums: DatumSet,
                  brief) -> LibraryCarve | CarveRefusal:
    """The reading room as a daylit double-height volume, not another band.

    The reading room is the library's principal room -- its clear span is the
    governing structural episode and its daylight is a constitution requirement --
    and the band allocator delivered it as one more strip under a 2.7 m ceiling.
    The carve stands it against the south edge of an upper plate, where its long
    side is glazing, and removes the plate above it so the room has the volume the
    type promises. One claim, reusing the section machinery the theatre built.
    """
    ask = next((s for s in brief if s.space_type == 'adult_reading'), None)
    if ask is None:
        return _refuse('ARCH-READING-ROOM', [],
                       'the brief names no reading room to carve')

    def refuse(reason: str) -> CarveRefusal:
        return _refuse('ARCH-READING-ROOM', [ask], reason)

    if len(lattice.occupied) < 2:
        return refuse('a double-height room needs a plate above it to remove, and '
                      'this massing has one occupied level')
    # High enough to be the quiet end, low enough that a plate remains above to
    # remove: the second occupied level from the top hosts the room and the top
    # plate is opened over it.
    host = lattice.occupied[-2]
    above = lattice.occupied[-1]

    px0 = min(p.x for p in host.plate)
    px1 = max(p.x for p in host.plate)
    py0 = min(p.y for p in host.plate)
    # Anchor on the southernmost structural row line, not the bounding box: the
    # projecting levels cantilever south along part of the boundary only, and a
    # room anchored to the overhang fails its corners where the overhang is not.
    sy0 = max(py0, lattice.y_lines[0])
    candidates = sorted(
        (y for y in lattice.y_lines
         if ask.min_dimension_m <= y - sy0 <= READING_MAX_DEPTH_M),
        reverse=True)
    placed = None
    for y1 in candidates:
        depth = y1 - sy0
        width = max(ask.area_m2 / depth, ask.min_dimension_m)
        if width > px1 - px0 - 0.5:
            continue
        # East end first, sliding inward -- several families round or step their
        # ends, and a rectangular room over a rounded plate fails its own corners.
        # Only the host plate is probed: where the plate above has already stepped
        # away, the room simply opens higher, which is more volume, not an error.
        anchors = [px1 - slide for slide in (0.0, 3.0, 6.0)]
        anchors += [px0 + width + slide for slide in (0.0, 3.0, 6.0)]
        for void in host.voids:
            vx0, vx1 = min(p.x for p in void), max(p.x for p in void)
            anchors.extend((vx0 - VOID_EDGE_CLEARANCE_M,
                            vx1 + VOID_EDGE_CLEARANCE_M + width))
        for x1 in anchors:
            rect = (x1 - width, sy0, x1, y1)
            if rect[0] >= px0 - 0.01 and rect[2] <= px1 + 0.01 \
                    and _rect_clear_of(host, rect):
                placed = (rect, depth)
                break
        if placed:
            break
    if placed is None:
        # A deep plate may put the atrium across every south/north strip. Rotate
        # the room: its long dimension still spans whole y bays, while its short
        # dimension remains the capped daylight depth and sits beside the void.
        spans = [(y0, y1) for y0 in lattice.y_lines for y1 in lattice.y_lines
                 if y1 - y0 >= ask.min_dimension_m]
        for y0, y1 in sorted(spans, key=lambda pair: pair[1] - pair[0],
                             reverse=True):
            length = y1 - y0
            width = max(ask.area_m2 / length, ask.min_dimension_m)
            if width > READING_MAX_DEPTH_M:
                continue
            span = _plate_x_span(host, y0, y1)
            if span is None or span[1] - span[0] < width:
                continue
            anchors = [span[1], span[0] + width]
            for void in host.voids:
                vx0, vx1 = min(p.x for p in void), max(p.x for p in void)
                anchors.extend((vx0 - VOID_EDGE_CLEARANCE_M,
                                vx1 + VOID_EDGE_CLEARANCE_M + width))
            for x1 in anchors:
                rect = (x1 - width, y0, x1, y1)
                if rect[0] >= span[0] - 0.01 and rect[2] <= span[1] + 0.01 \
                        and _rect_clear_of(host, rect):
                    placed = (rect, width)
                    break
            if placed:
                break
    if placed is None:
        return refuse(f'no span of grid bays at the perimeter of {host.id} holds '
                      f'{ask.area_m2:.0f} m2 at {ask.min_dimension_m:.0f} m clear '
                      f'of the plate edge and its voids across '
                      f'{len(lattice.occupied)} occupied levels')
    rect, depth = placed

    removed = {above.index: [rect]}
    demolished = _gutted(lattice, removed)
    if demolished is not None:
        level_id, share, remaining = demolished
        return refuse(f'opening the reading room through {level_id} would leave it '
                      f'{share:.0%} of its floor ({remaining:.0f} m2)')

    clear = round(above.z - host.z
                  + max(2.4, datums.value('floor_to_floor_m')
                        - datums.value('slab_thickness_m') - 0.15), 3)
    zone = _place_zone(ask, rect, host, lattice.y_lines)
    return LibraryCarve(
        rooms={ask.id: rect},
        zones=[zone],
        reservations={host.index: [rect]},
        removed=removed,
        tall_walls_m={ask.id: clear},
        level_index=host.index,
        clear_m=clear,
        notes=[f'reading room on {host.id} against a perimeter glazing line, open '
               f'through {above.id} to {clear:.1f} m clear'])


def carve_pavilion(lattice: Lattice, datums: DatumSet,
                   brief) -> PavilionCarve | CarveRefusal:
    """The hall as the full-height volume a pavilion is.

    A pavilion is a room, not a stack of them: the main hall takes the east end of
    the ground plate through the full depth, and every plate above it is opened, so
    the one daylit volume the brief describes is the volume that gets built.
    """
    halls = sorted((s for s in brief
                    if s.category == 'public' and s.level_preference == 'ground'),
                   key=lambda s: -s.area_m2)
    if not halls:
        return _refuse('ARCH-HALL', [],
                       'the brief names no ground-floor public hall to carve')
    ask = halls[0]

    def refuse(reason: str) -> CarveRefusal:
        return _refuse('ARCH-HALL', [ask], reason)

    ground = lattice.occupied[0]
    px0 = min(p.x for p in ground.plate)
    px1 = max(p.x for p in ground.plate)
    py0 = min(p.y for p in ground.plate)
    py1 = max(p.y for p in ground.plate)
    depth = py1 - py0
    if depth < ask.min_dimension_m:
        return refuse(f'the plate is {depth:.1f} m deep against the hall\'s '
                      f'{ask.min_dimension_m:.0f} m minimum dimension')
    width = max(ask.area_m2 / depth, ask.min_dimension_m)
    if width > px1 - px0 - 0.5:
        return refuse(f'the hall needs {width:.1f} m of a {px1 - px0:.1f} m plate')
    # East end: the west end carries the apse this family rounds, and a rectangular
    # room over a rounded plate fails its own corners.
    rect = (px1 - width, py0, px1, py1)
    if not _rect_clear_of(ground, rect):
        return refuse('the ground plate is notched or holed where the hall '
                      'would stand')

    removed = {level.index: [rect] for level in lattice.occupied[1:]}
    demolished = _gutted(lattice, removed)
    if demolished is not None:
        level_id, share, remaining = demolished
        return refuse(f'opening the hall through {level_id} would leave it '
                      f'{share:.0%} of its floor ({remaining:.0f} m2)')

    roof_z = lattice.levels[-1].z
    clear = round(roof_z - ground.z - 0.3, 3)
    zone = _place_zone(ask, rect, ground, lattice.y_lines)
    return PavilionCarve(
        rooms={ask.id: rect},
        zones=[zone],
        reservations={ground.index: [rect]},
        removed=removed,
        tall_walls_m={ask.id: clear},
        level_index=ground.index,
        clear_m=clear,
        notes=[f'hall open through every plate to {clear:.1f} m under the roof, '
               f'daylit on three sides at the east end of the plate'])


_CARVERS = {
    'ARCH-THEATRE-BOWL': carve_theatre,
    'ARCH-GALLERY-SEQUENCE': carve_museum,
    'ARCH-READING-ROOM': carve_library,
    'ARCH-HALL': carve_pavilion,
}


def carve_for(typology: str, lattice: Lattice, datums: DatumSet,
              brief) -> Carve | CarveRefusal | None:
    """The typology's carver, or None for a typology that is all the allocator's."""
    from .typology import kit_for

    archetype = kit_for(typology).archetype
    if archetype is None:
        return None
    carver = _CARVERS.get(archetype)
    if carver is None:
        raise LookupError(f'typology {typology!r} names archetype {archetype!r}, '
                          f'which has no carver')
    return carver(lattice, datums, brief)


# ---------------------------------------------------------------------------
# Measured back off the model
# ---------------------------------------------------------------------------

class ArchetypeFinding(BaseModel):
    gate_id: str
    severity: Literal['violation', 'warning']
    elements: tuple[str, ...]
    measure: float
    unit: str
    detail: str


class SightlineRecord(BaseModel):
    """One row's sightline, measured from the emitted geometry."""

    row: int
    distance_m: float
    floor_m: float
    c_measured_m: float | None   # None on the front row: nobody sits before it


class ArchetypeReport(BaseModel):
    """What the archetype claimed, and what the built model measures back.

    Carried on the model like the constitution and the spatial report: the carve is
    the promise, this is the audit of it, and a reader gets both.
    """

    archetype_id: str
    typology: str
    refused: str | None = None
    # Every carved room by space id, whatever the typology.
    rooms: dict[str, Rect] = Field(default_factory=dict)
    house: Rect | None = None
    stage: Rect | None = None
    clear_house_m: float | None = None
    clear_stage_m: float | None = None
    clear_m: float | None = None
    sightlines: list[SightlineRecord] = Field(default_factory=list)
    findings: list[ArchetypeFinding] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @property
    def violations(self) -> list[ArchetypeFinding]:
        return [f for f in self.findings if f.severity == 'violation']


def _rects_touch(a: Rect, b: Rect, gap: float = 0.35) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    share_x = min(ax1, bx1) - max(ax0, bx0)
    share_y = min(ay1, by1) - max(ay0, by0)
    return ((share_x > 1.0 and -gap <= max(ay0 - by1, by0 - ay1) <= gap)
            or (share_y > 1.0 and -gap <= max(ax0 - bx1, bx0 - ax1) <= gap))


def _gate_claims_cut(model, carve: Carve) -> list[ArchetypeFinding]:
    """Every claimed plate removal, checked against the lattice the model carries."""
    findings: list[ArchetypeFinding] = []
    for level_index, rects in carve.removed.items():
        level = model.lattice.level(level_index)
        for rect in rects:
            rx0, ry0, rx1, ry1 = rect
            probes = [((rx0 + rx1) / 2.0, (ry0 + ry1) / 2.0),
                      (rx0 + 0.3, ry0 + 0.3), (rx1 - 0.3, ry1 - 0.3),
                      (rx0 + 0.3, ry1 - 0.3), (rx1 - 0.3, ry0 + 0.3)]
            covered = all(
                not point_inside(level.plate, x, y)
                or any(point_inside(void, x, y) for void in level.voids)
                for x, y in probes)
            if not covered:
                findings.append(ArchetypeFinding(
                    gate_id='ARCH-CLAIM-UNCUT', severity='violation',
                    elements=(level.id,), measure=0.0, unit='',
                    detail=f'the carve claims the plate at {level.id} removed over '
                           f'({rx0:.1f}, {ry0:.1f})-({rx1:.1f}, {ry1:.1f}) and the '
                           f'lattice still has floor there'))
    return findings


def _gate_colonnade(model, rooms: dict[str, Rect], clear_m: float,
                    base_z: float, ask: str) -> list[ArchetypeFinding]:
    """Columns standing inside a volume whose type demands none.

    Reported as the violation it is: the frame is not re-framed over the carved
    rooms, the long-span transfer their demand row asks for is the phase decision
    0016 owes, and a red light that is true beats a colonnade nothing mentions.
    """
    inside = []
    for element in model.elements:
        if element.kind not in ('column', 'piloti_column'):
            continue
        x, y = element.position.x, element.position.y
        z0 = element.position.z - element.dimensions.z / 2.0
        if z0 >= base_z + clear_m:
            continue
        for rx0, ry0, rx1, ry1 in rooms.values():
            if rx0 + 0.3 < x < rx1 - 0.3 and ry0 + 0.3 < y < ry1 - 0.3:
                inside.append(element.id)
                break
    if not inside:
        return []
    return [ArchetypeFinding(
        gate_id='ARCH-CLEAR-SPAN', severity='violation',
        elements=tuple(sorted(inside)[:8]), measure=float(len(inside)),
        unit='columns',
        detail=f'{len(inside)} columns stand inside the carved volumes. The frame '
               f'is not yet re-framed over them: the long-span transfer this '
               f'typology\'s demand row asks for ({ask}) is the phase decision '
               f'0016 owes. Reported rather than hidden.')]


def _gate_perimeter_daylight(model, carve: Carve,
                             space_ids: tuple[str, ...]) -> list[ArchetypeFinding]:
    """A room that asked for daylight stands on the glazing line, measured.

    Measured against the plate polygon, not its bounding box: a step or a
    cantilever bulges the box past the enclosed floor, and a room can stand hard
    on the real envelope while sitting metres inside the box. An edge faces the
    envelope when a point just beyond it has left the plate.
    """
    findings: list[ArchetypeFinding] = []
    by_index = {level.index: level for level in model.lattice.levels}
    for space_id in space_ids:
        rect = carve.rooms.get(space_id)
        zone = next((z for z in carve.zones if z.space_id == space_id), None)
        if rect is None or zone is None:
            continue
        level = by_index[zone.level_index]
        rx0, ry0, rx1, ry1 = rect
        intervals = [b - a for lines in (model.lattice.x_lines,
                                         model.lattice.y_lines)
                     for a, b in zip(lines, lines[1:]) if b - a > 0.01]
        # Rooms sit on structural lines while a slab may cantilever or rotate past
        # them. Half the smallest bay is the measured perimeter zone; a fixed 450 mm
        # wrongly called the intended glazing line an interior wall on those plates.
        reach = max(0.45, min(intervals, default=0.9) / 2.0)
        beyond = []
        for t in (0.25, 0.5, 0.75):
            x = rx0 + (rx1 - rx0) * t
            y = ry0 + (ry1 - ry0) * t
            beyond += [(x, ry0 - reach), (x, ry1 + reach),
                       (rx0 - reach, y), (rx1 + reach, y)]
        if not any(not point_inside(level.plate, x, y) for x, y in beyond):
            findings.append(ArchetypeFinding(
                gate_id='ARCH-DAYLIGHT', severity='violation',
                elements=(space_id,), measure=0.0, unit='',
                detail=f'{space_id} asked for daylight and no edge of it faces '
                       f'the envelope: an interior room lit through other rooms '
                       f'is not a daylit room'))
    return findings


def _theatre_gates(model, carve: TheatreCarve,
                   findings: list[ArchetypeFinding]) -> list[SightlineRecord]:
    """The theatre's own gates: sightlines, the colonnade, front against back."""
    ground = model.lattice.occupied[0]
    ground_z = ground.z
    focal_h = ground_z + carve.focal_h_m

    def plan_distance(e) -> float:
        return (e.position.x - carve.proscenium_x) * carve.audience_dx

    risers = sorted((e for e in model.elements if e.kind == 'auditorium_riser'),
                    key=plan_distance)
    records: list[SightlineRecord] = []
    previous: tuple[float, float] | None = None   # (distance, eye z)
    for index, riser in enumerate(risers):
        top = riser.position.z + riser.dimensions.z / 2.0
        distance = plan_distance(riser)
        eye = top + SEATED_EYE_M
        c_measured: float | None = None
        if previous is not None:
            d_near, eye_near = previous
            sight_at_near = focal_h + (eye - focal_h) * d_near / distance
            c_measured = round(sight_at_near - eye_near, 4)
            if c_measured < C_VALUE_MIN_M - 0.001:
                findings.append(ArchetypeFinding(
                    gate_id='ARCH-SIGHTLINE', severity='violation',
                    elements=(riser.id,), measure=c_measured, unit='m',
                    detail=f'row {index} clears the row in front by '
                           f'{c_measured * 1000:.0f} mm; the minimum for every-row '
                           f'vision is {C_VALUE_MIN_M * 1000:.0f} mm'))
        records.append(SightlineRecord(
            row=index, distance_m=round(distance, 3),
            floor_m=round(top - ground_z, 3), c_measured_m=c_measured))
        previous = (distance, eye)
    if not risers:
        findings.append(ArchetypeFinding(
            gate_id='ARCH-SIGHTLINE', severity='violation', elements=(),
            measure=0.0, unit='rows',
            detail='the carve derived a bowl and the model contains no risers'))

    findings.extend(_gate_colonnade(
        model, carve.rooms, carve.clear_house_m, ground_z, 'max_clear_span_m'))

    for zone in model.program_allocation.zones_on(ground.index):
        if zone.space_type not in ('theatre_foyer', 'cafe'):
            continue
        if _rects_touch((zone.x0, zone.y0, zone.x1, zone.y1), carve.stage):
            findings.append(ArchetypeFinding(
                gate_id='ARCH-FOH-BOH', severity='violation',
                elements=(zone.space_id,), measure=0.0, unit='',
                detail=f'{zone.label} shares a wall with the stage: the audience '
                       f'side and the working side meet only at the proscenium and '
                       f'the pass door'))
    return records


def _museum_gates(model, carve: MuseumCarve,
                  findings: list[ArchetypeFinding]) -> None:
    """The sequence is the type: touching galleries, a real portal, the top plate."""
    rects = list(carve.rooms.values())
    if len(rects) == 2 and not _rects_touch(rects[0], rects[1], gap=0.1):
        findings.append(ArchetypeFinding(
            gate_id='ARCH-ENFILADE', severity='violation',
            elements=tuple(carve.rooms), measure=0.0, unit='',
            detail='the galleries do not share a party wall; two rooms apart is '
                   'a corridor plan, not a sequence'))

    jambs = [e for e in model.elements
             if e.kind == 'partition' and e.id.startswith('PRG-ENF-')]
    if len(jambs) < 2:
        findings.append(ArchetypeFinding(
            gate_id='ARCH-ENFILADE', severity='violation',
            elements=tuple(e.id for e in jambs), measure=float(len(jambs)),
            unit='wall pieces',
            detail='the party wall between the galleries was not built'))
    else:
        if carve.party_axis == 'y':
            before = min(jambs, key=lambda e: e.position.y)
            after = max(jambs, key=lambda e: e.position.y)
            gap = ((after.position.y - after.dimensions.y / 2.0)
                   - (before.position.y + before.dimensions.y / 2.0))
        else:
            before = min(jambs, key=lambda e: e.position.x)
            after = max(jambs, key=lambda e: e.position.x)
            gap = ((after.position.x - after.dimensions.x / 2.0)
                   - (before.position.x + before.dimensions.x / 2.0))
        if not (2.4 <= gap <= carve.portal_w_m + 0.5):
            findings.append(ArchetypeFinding(
                gate_id='ARCH-ENFILADE', severity='violation',
                elements=(before.id, after.id), measure=round(gap, 3), unit='m',
                detail=f'the portal between the galleries measures {gap:.1f} m '
                       f'against a {carve.portal_w_m:.1f} m ask; a sequence needs '
                       f'an opening a crated work and a crowd pass through'))

    # Top-light means nothing but roof over the gallery: either it stands on the
    # last occupied plate, or every plate above it is opened over its footprint --
    # which the claims gate has already probed against the lattice voids.
    top_index = model.lattice.occupied[-1].index
    for zone in carve.zones:
        above = [level for level in model.lattice.occupied
                 if level.index > zone.level_index]
        opened = all(level.index in carve.removed for level in above)
        if zone.level_index != top_index and not opened:
            findings.append(ArchetypeFinding(
                gate_id='ARCH-TOPLIGHT', severity='violation',
                elements=(zone.space_id,), measure=float(zone.level_index), unit='',
                detail=f'{zone.label} stands on level {zone.level_index} with a plate '
                       f'still above it: controlled top-light is the one daylight a '
                       f'collection accepts, and it only exists under the roof'))

    ground_z = model.lattice.level(carve.level_index).z
    findings.extend(_gate_colonnade(
        model, carve.rooms, carve.wall_h_m, ground_z, 'max_clear_span_m = 20 m'))


def evaluate_archetype(model, carve: Carve | CarveRefusal | None,
                       typology: str) -> ArchetypeReport | None:
    """Measure the promises the carve made, off the geometry that was built.

    The gates are measurements, never restatements of the derivation: claimed plate
    removals are probed against the lattice, sightlines are recomputed from the
    emitted riser tops, daylight is the distance from the room to the glazing line,
    the enfilade is the gap between the built wall pieces. Each typology adds its
    own gates on top of the shared ones, which is the kit doing what decision 0016
    says a kit is for.
    """
    if carve is None:
        return None
    if isinstance(carve, CarveRefusal):
        return ArchetypeReport(
            archetype_id=carve.archetype_id, typology=typology,
            refused=carve.reason,
            findings=[ArchetypeFinding(
                gate_id='ARCH-CARVED', severity='violation',
                elements=tuple(space.space_id for space in carve.precluded),
                measure=float(len(carve.precluded)), unit='rooms refused',
                detail=carve.reason)])

    findings = _gate_claims_cut(model, carve)
    records: list[SightlineRecord] = []

    if isinstance(carve, TheatreCarve):
        records = _theatre_gates(model, carve, findings)
    elif isinstance(carve, MuseumCarve):
        _museum_gates(model, carve, findings)
    elif isinstance(carve, LibraryCarve):
        findings.extend(_gate_perimeter_daylight(model, carve,
                                                 tuple(carve.rooms)))
    elif isinstance(carve, PavilionCarve):
        findings.extend(_gate_perimeter_daylight(model, carve,
                                                 tuple(carve.rooms)))
        ground_z = model.lattice.level(carve.level_index).z
        findings.extend(_gate_colonnade(
            model, carve.rooms, carve.clear_m, ground_z,
            'a covered single volume at 40 m'))

    return ArchetypeReport(
        archetype_id=carve.archetype_id, typology=typology,
        rooms=dict(carve.rooms),
        house=getattr(carve, 'house', None),
        stage=getattr(carve, 'stage', None),
        clear_house_m=getattr(carve, 'clear_house_m', None),
        clear_stage_m=getattr(carve, 'clear_stage_m', None),
        clear_m=getattr(carve, 'clear_m', None),
        sightlines=records, findings=findings, notes=list(carve.notes))
