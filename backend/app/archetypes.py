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
from .program import AllocatedZone, UnplacedSpace


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


class TheatreCarve(BaseModel):
    """Everything the theatre archetype decided, for the compiler and the gates."""

    archetype_id: Literal['ARCH-THEATRE-BOWL'] = 'ARCH-THEATRE-BOWL'
    house: Rect
    stage: Rect
    # Which way the audience extends from the proscenium line: +1 means the rake
    # climbs toward +x (stage at the west end), -1 the reverse. The pair tries the
    # east end first and swaps rather than overlap a stair core.
    audience_dx: int
    proscenium_x: float
    proscenium_w_m: float
    focal_h_m: float           # above the house slab
    clear_house_m: float
    clear_stage_m: float
    rows: list[BowlRow]
    zones: list[AllocatedZone]
    # Ground-plate floor the allocator must lay out around.
    reservations: dict[int, list[Rect]]
    # Plates removed over the carved volumes, per level index, applied as voids.
    removed: dict[int, list[Rect]]
    # Enclosure walls that must run the full carved height, keyed by space id.
    tall_walls_m: dict[str, float]
    notes: list[str] = Field(default_factory=list)


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


def _refuse(brief_spaces, reason: str) -> CarveRefusal:
    return CarveRefusal(
        archetype_id='ARCH-THEATRE-BOWL',
        precluded=[UnplacedSpace(
            space_id=space.id, label=space.label, area_required_m2=space.area_m2,
            reason=f'the theatre archetype could not carve this plate: {reason}')
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
        return _refuse([s for s in (house_ask, stage_ask) if s is not None],
                       'the brief names no auditorium and stage to carve')
    asks = [house_ask, stage_ask]

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
        return _refuse(asks, f'no run of rows offers the house its '
                             f'{house_ask.min_dimension_m:.0f} m minimum dimension '
                             f'on this plate')
    y0 = min(candidates)
    depth = py1 - y0

    stage_w = max(stage_ask.area_m2 / depth, stage_ask.min_dimension_m)
    house_w = max(house_ask.area_m2 / depth, house_ask.min_dimension_m)
    if px1 - px0 < stage_w + house_w + 0.5:
        need = stage_w + house_w
        return _refuse(asks, f'house and stage need {need:.1f} m along the plate at '
                             f'{depth:.1f} m deep; this plate offers '
                             f'{px1 - px0:.1f} m')

    # Stage at the east end, audience raking west toward the entry side.
    audience_dx = -1
    stage_x1 = px1
    stage_x0 = house_x1 = stage_x1 - stage_w
    house_x0 = house_x1 - house_w
    proscenium_x = house_x1
    house = (house_x0, y0, house_x1, py1)
    stage = (stage_x0, y0, stage_x1, py1)

    # A notched or split plate can satisfy the bounding box and still not own these
    # corners; standing the house over a notch is exactly the kind of error a person
    # would catch by looking. Probes are inset 50 mm so a corner exactly on the plate
    # edge does not fail on the boundary test.
    lo_x = min(house_x0, stage_x0)
    hi_x = max(house_x1, stage_x1)
    probes = ((lo_x + 0.05, y0 + 0.05), (lo_x + 0.05, py1 - 0.05),
              (hi_x - 0.05, y0 + 0.05), (hi_x - 0.05, py1 - 0.05),
              ((lo_x + hi_x) / 2.0, (y0 + py1) / 2.0))
    if not all(point_inside(ground.plate, x, y) for x, y in probes):
        return _refuse(asks, 'the ground plate is notched where the house or stage '
                             'would stand')

    rows = derive_bowl(house_w)
    if len(rows) < 4:
        return _refuse(asks, f'a {house_w:.1f} m deep house holds {len(rows)} rows; '
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
        # Gutted means what remains cannot hold a room and the way to it: a quarter
        # of the plate, or 120 m2, whichever accusation is worse. The loss is
        # measured against the plate's bounding box, which overstates it on a
        # rounded plate -- a conservative error, in the direction of refusing.
        if area > 1.0 and (share < 0.25 or remaining < 120.0):
            return _refuse(asks, f'the house\'s clear height would leave {level.id} '
                                 f'with {share:.0%} of its floor '
                                 f'({remaining:.0f} m2): this massing stands its '
                                 f'upper storeys where the house must be, and the '
                                 f'tall stage volume that resolves it is the '
                                 f'fly-tower phase decision 0016 defers')

    band = _row_index(lattice.y_lines, y0)
    common = dict(
        category='public', level_index=ground.index, level_id=ground.id,
        band_index=band, y0=round(y0, 3), y1=round(py1, 3),
        daylight_satisfied=True, level_preference_satisfied=True)
    zones = [
        AllocatedZone(
            space_id=house_ask.id, space_type='auditorium', label=house_ask.label,
            occupancy_id=house_ask.occupancy_id,
            x0=round(house_x0, 3), x1=round(house_x1, 3),
            area_required_m2=house_ask.area_m2,
            area_delivered_m2=round(house_w * depth, 2),
            area_satisfied=house_w * depth
            >= house_ask.area_m2 * house_ask.area_tolerance,
            area_tolerance=house_ask.area_tolerance, **common),
        AllocatedZone(
            space_id=stage_ask.id, space_type='stage', label=stage_ask.label,
            occupancy_id=stage_ask.occupancy_id,
            x0=round(stage_x0, 3), x1=round(stage_x1, 3),
            area_required_m2=stage_ask.area_m2,
            area_delivered_m2=round(stage_w * depth, 2),
            area_satisfied=stage_w * depth
            >= stage_ask.area_m2 * stage_ask.area_tolerance,
            area_tolerance=stage_ask.area_tolerance, **{
                **common, 'category': 'private'}),
    ]

    return TheatreCarve(
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


def carve_for(typology: str, lattice: Lattice, datums: DatumSet,
              brief) -> TheatreCarve | CarveRefusal | None:
    """The typology's carver, or None for a typology that is all the allocator's."""
    from .typology import kit_for

    archetype = kit_for(typology).archetype
    if archetype is None:
        return None
    if archetype == 'ARCH-THEATRE-BOWL':
        return carve_theatre(lattice, datums, brief)
    raise LookupError(f'typology {typology!r} names archetype {archetype!r}, '
                      f'which has no carver')


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
    house: Rect | None = None
    stage: Rect | None = None
    clear_house_m: float | None = None
    clear_stage_m: float | None = None
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


def evaluate_archetype(model, carve: TheatreCarve | CarveRefusal | None,
                       typology: str) -> ArchetypeReport | None:
    """Measure the promises the carve made, off the geometry that was built.

    Four gates, each a measurement:
    - every row's C-value, recomputed from the emitted riser tops;
    - every claimed plate removal, checked against the lattice voids;
    - columns standing inside the carved volumes -- reported as the violation it is,
      because the frame is not yet re-framed over the house (the long-span phase 0016
      owes) and a red light that is true beats a bowl with a colonnade through it
      that nothing mentions;
    - front-of-house rooms against the stage wall, which is the audience standing in
      the get-in.
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

    findings: list[ArchetypeFinding] = []
    ground = model.lattice.occupied[0]
    ground_z = ground.z
    hx0, hy0, hx1, hy1 = carve.house
    sx0, sy0, sx1, sy1 = carve.stage
    focal_h = ground_z + carve.focal_h_m

    # --- sightlines, from the riser tops actually emitted ---------------------
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

    # --- the claimed section, from the lattice the model carries --------------
    for level_index, rects in carve.removed.items():
        level = model.lattice.level(level_index)
        for rect in rects:
            rx0, ry0, rx1, ry1 = rect
            probes = [((rx0 + rx1) / 2.0, (ry0 + ry1) / 2.0),
                      (rx0 + 0.3, ry0 + 0.3), (rx1 - 0.3, ry1 - 0.3),
                      (rx0 + 0.3, ry1 - 0.3), (rx1 - 0.3, ry0 + 0.3)]
            covered = all(
                any(point_inside(void, x, y) for void in level.voids)
                for x, y in probes)
            if not covered:
                findings.append(ArchetypeFinding(
                    gate_id='ARCH-CLAIM-UNCUT', severity='violation',
                    elements=(level.id,), measure=0.0, unit='',
                    detail=f'the carve claims the plate at {level.id} removed over '
                           f'({rx0:.1f}, {ry0:.1f})-({rx1:.1f}, {ry1:.1f}) and the '
                           f'lattice still has floor there'))

    # --- columns in the bowl ---------------------------------------------------
    inside = []
    for element in model.elements:
        if element.kind not in ('column', 'piloti_column'):
            continue
        x, y = element.position.x, element.position.y
        z0 = element.position.z - element.dimensions.z / 2.0
        in_house = hx0 + 0.3 < x < hx1 - 0.3 and hy0 + 0.3 < y < hy1 - 0.3
        in_stage = sx0 + 0.3 < x < sx1 - 0.3 and sy0 + 0.3 < y < sy1 - 0.3
        tall = z0 < ground_z + carve.clear_house_m
        if (in_house or in_stage) and tall:
            inside.append(element.id)
    if inside:
        findings.append(ArchetypeFinding(
            gate_id='ARCH-CLEAR-SPAN', severity='violation',
            elements=tuple(sorted(inside)[:8]), measure=float(len(inside)),
            unit='columns',
            detail=f'{len(inside)} columns stand inside the carved volumes. The '
                   f'frame is not yet re-framed over the house: the long-span '
                   f'transfer this typology\'s demand row asks for '
                   f'(max_clear_span_m) is the phase decision 0016 owes. Reported '
                   f'rather than hidden.'))

    # --- front of house against the stage wall --------------------------------
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

    return ArchetypeReport(
        archetype_id=carve.archetype_id, typology=typology,
        house=carve.house, stage=carve.stage,
        clear_house_m=carve.clear_house_m, clear_stage_m=carve.clear_stage_m,
        sightlines=records, findings=findings, notes=list(carve.notes))
