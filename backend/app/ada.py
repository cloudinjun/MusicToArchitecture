"""ADA ramp geometry, and the decision to build a stair instead.

The accessible approach in this project was one box, `rise * 6.0` long. That is a 1:6
slope: exactly twice the maximum the 2010 ADA Standards allow, on every one of the
fourteen corpus models. It had no intermediate landings, no handrails and no edge
protection, and it climbed four to six metres in a single run where the standard caps a
run at 760 mm of rise.

An approach that steep is not a marginal violation. At 1:6 a wheelchair user cannot get
up it and can lose control coming down; it is a ramp in name and a hazard in fact. So
this module computes what §405 actually requires and returns one of two answers:

- a **plan** -- runs, landings and handrails that comply -- when one fits, or
- **nothing**, when the site cannot hold a compliant ramp, in which case the caller
  builds a stair and records that the accessible route is unresolved.

The second answer is the point of the goal this module was written for. A ramp that does
not comply is worse than no ramp: it occupies the place an accessible route should be,
and it tells a reader the problem is solved. A stair with a stated reason tells the truth
and leaves the problem visible.

Every constant below cites the section it comes from. Where the standard gives inches
they are converted once, here, so no other module has to.
"""

from __future__ import annotations

import math

from pydantic import BaseModel

# --- 2010 ADA Standards for Accessible Design, §405 Ramps --------------------
# 405.2 Slope: running slope shall not be steeper than 1:12.
MAX_SLOPE = 1.0 / 12.0
# 405.3 Cross Slope: not steeper than 1:48. Recorded rather than modelled: this
# compiler builds no cross fall, so a run is drawn level across its width.
MAX_CROSS_SLOPE = 1.0 / 48.0
# 405.5 Clear Width: 36 in minimum, measured between handrails.
MIN_CLEAR_WIDTH_M = 0.915
# 405.6 Rise: 30 in maximum for any ramp run.
MAX_RUN_RISE_M = 0.760
# 405.7.3 Landings: 60 in clear length minimum.
MIN_LANDING_LENGTH_M = 1.525
# 405.7.4 Change in Direction: landings at a turn are 60 x 60 in minimum.
MIN_TURN_LANDING_M = 1.525
# 405.8 Handrails: required where a ramp run rises more than 6 in.
HANDRAIL_RISE_THRESHOLD_M = 0.150
# 505.4 Handrail height above the walking surface, 34-38 in; the middle of the band.
HANDRAIL_HEIGHT_M = 0.915
# 505.10 Handrail Extensions: 12 in beyond the top and bottom of each run.
HANDRAIL_EXTENSION_M = 0.305
# 405.9.2 Edge Protection: a 4 in curb is the option modelled here.
CURB_HEIGHT_M = 0.100

RAMP_THICKNESS_M = 0.24


class RampRun(BaseModel):
    """One sloping run, between two landings."""

    index: int
    # Centre-line, ground plane. `direction` is +1 travelling east, -1 west.
    x_start: float
    x_end: float
    y: float
    z_start: float
    z_end: float
    direction: int

    @property
    def rise(self) -> float:
        return self.z_end - self.z_start

    @property
    def length(self) -> float:
        return abs(self.x_end - self.x_start)

    @property
    def slope(self) -> float:
        return self.rise / self.length if self.length else 0.0


class RampLanding(BaseModel):
    """A landing at the bottom, the top, or a turn between two runs."""

    index: int
    x: float
    y: float
    z: float
    size_x: float
    size_y: float
    kind: str  # 'bottom' | 'turn' | 'top'


class RampPlan(BaseModel):
    """A compliant accessible route, with the numbers that make it compliant."""

    rise_m: float
    width_m: float
    runs: list[RampRun]
    landings: list[RampLanding]
    footprint_x_m: float
    footprint_y_m: float
    handrails_required: bool
    citations: list[str]
    # The route as one continuous polyline, bottom landing to top: the line a person
    # actually walks. Runs and landings are both read off it, which is the only way
    # they cannot disagree -- they used to be computed separately, and every run began
    # 3.4 m from the landing that was supposed to feed it.
    centre_line: list[tuple[float, float, float]] = []

    @property
    def total_run_length_m(self) -> float:
        return sum(run.length for run in self.runs)

    @property
    def steepest_slope(self) -> float:
        return max((abs(run.slope) for run in self.runs), default=0.0)

    def compliance(self) -> list[str]:
        """Every check, as text. Empty means nothing was violated."""
        problems: list[str] = []
        if self.steepest_slope > MAX_SLOPE + 1e-6:
            problems.append(
                f'405.2 running slope 1:{1 / self.steepest_slope:.1f} exceeds 1:12')
        for run in self.runs:
            if run.rise > MAX_RUN_RISE_M + 1e-6:
                problems.append(
                    f'405.6 run {run.index} rises {run.rise * 1000:.0f} mm, over 760 mm')
        if self.width_m < MIN_CLEAR_WIDTH_M - 1e-6:
            problems.append(
                f'405.5 clear width {self.width_m * 1000:.0f} mm is under 915 mm')
        turns = [landing for landing in self.landings if landing.kind == 'turn']
        if len(turns) != max(0, len(self.runs) - 1):
            problems.append('405.7 a landing is missing between two runs')
        for landing in self.landings:
            shortest = min(landing.size_x, landing.size_y)
            limit = (MIN_TURN_LANDING_M if landing.kind == 'turn'
                     else MIN_LANDING_LENGTH_M)
            if shortest < limit - 1e-6:
                problems.append(
                    f'405.7.{4 if landing.kind == "turn" else 3} landing '
                    f'{landing.index} is {shortest * 1000:.0f} mm, under '
                    f'{limit * 1000:.0f} mm')
        return problems


def plan_switchback_ramp(
    *, rise_m: float, width_m: float, x_min: float, x_max: float, y_start: float,
    y_available: float, z_base: float, direction_y: float = -1.0,
) -> RampPlan | None:
    """Lay out an ADA-compliant switchback ramp, or return nothing if none fits.

    The switchback is not a stylistic choice. At 1:12 with runs capped at 760 mm of
    rise, a five-metre podium needs eight runs and roughly sixty-five metres of ramp;
    nothing in front of these buildings is sixty-five metres long, so the route has to
    fold. Each run travels the full available width, the direction alternates, and a
    1525 mm square landing sits at every turn.

    `y_available` is how far the route may reach away from the building. Returning
    `None` when it does not fit is deliberate and is the whole reason this function has
    a nullable return: the caller then builds a stair rather than a ramp that would
    have to break §405 to fit.
    """
    if rise_m <= 0.01:
        return None
    width = max(width_m, MIN_CLEAR_WIDTH_M)
    span = abs(x_max - x_min)
    if span < MIN_LANDING_LENGTH_M * 2.0 + width:
        return None

    # A run may travel the span less a landing at each end of the leg.
    run_length = span - MIN_TURN_LANDING_M * 2.0
    if run_length <= 0.5:
        return None

    # 405.2 and 405.6 together: the run is limited by whichever binds first.
    rise_by_slope = run_length * MAX_SLOPE
    rise_per_run = min(MAX_RUN_RISE_M, rise_by_slope)
    if rise_per_run <= 0.01:
        return None
    run_count = max(1, math.ceil(rise_m / rise_per_run))
    actual_rise = rise_m / run_count
    # keep the geometry honest: shorten the run to the rise it actually carries
    actual_length = min(run_length, actual_rise / MAX_SLOPE)
    if actual_length < 0.9:
        return None

    # The legs stack away from the building. The pitch is also the depth of every turn
    # landing, so it cannot be narrower than a landing is allowed to be: at a clear
    # width of 915 mm the old `width + 0.25` gave a 1.17 m turn, which 405.7.4 forbids.
    # The legs abut. `width + 0.25` left a 250 mm slot down the length of every
    # switchback: from above the ramp read as a stack of separate planks, and the slot
    # itself is the worse half -- two legs of a switchback sit at different heights
    # along most of their length, so a gap between them is a drop you can put a foot
    # through. Edge protection belongs on the deck edges, not either side of a void.
    pitch = max(width, MIN_TURN_LANDING_M)
    needed_y = run_count * pitch + MIN_TURN_LANDING_M
    if needed_y > y_available:
        return None

    sign = 1.0 if direction_y >= 0 else -1.0

    # --- the centre line ------------------------------------------------------
    # Walked once, as a route: start on the bottom landing, climb a leg, cross the
    # turn, climb back. Everything else is read off this. The previous version placed
    # each run against the plan's own x extents instead of against the landing before
    # it, so whenever a run was shorter than its leg -- which is whenever the 760 mm
    # rise binds before the slope does -- the two ends of the switchback stopped
    # meeting and every westward run started in mid-air.
    # Laid out from the arrival, not from an offset. `y_start` is where the route has
    # to *end up* -- the edge of the floor it serves -- and the legs march away from it.
    # Positioned the other way round, from a setback the caller chose, the top landing
    # came to rest 2.14 m short of the building: the route was compliant, complete, and
    # arrived nowhere.
    top_half = max(width, MIN_LANDING_LENGTH_M) / 2.0
    x_cursor = x_min + MIN_LANDING_LENGTH_M
    # The bottom landing sits on the first leg's own line, reached along it rather than
    # across it. Set half a pitch further out, as it was, the landing did not span the
    # traverse onto the leg and the first run began 890 mm off the end of it.
    y_cursor = y_start + sign * ((run_count - 1) * pitch + top_half)
    z_cursor = z_base
    path: list[tuple[float, float, float]] = [(x_cursor, y_cursor, z_cursor)]

    runs: list[RampRun] = []
    landings: list[RampLanding] = []

    landings.append(RampLanding(
        index=0, x=x_cursor - MIN_LANDING_LENGTH_M / 2.0, y=y_cursor, z=z_cursor,
        size_x=MIN_LANDING_LENGTH_M, size_y=max(width, MIN_LANDING_LENGTH_M),
        kind='bottom'))

    for index in range(run_count):
        east = index % 2 == 0
        step = actual_length if east else -actual_length
        leg_y = y_start + sign * ((run_count - index - 1) * pitch + top_half)
        # Cross onto this leg first, then climb it: the traverse happens on the
        # landing, at the level the previous run arrived at.
        if abs(leg_y - y_cursor) > 1e-9:
            y_cursor = leg_y
            path.append((x_cursor, y_cursor, z_cursor))
        x_end = x_cursor + step
        runs.append(RampRun(
            index=index, x_start=x_cursor, x_end=x_end, y=leg_y,
            z_start=z_cursor, z_end=z_cursor + actual_rise,
            direction=1 if east else -1))
        x_cursor, z_cursor = x_end, z_cursor + actual_rise
        path.append((x_cursor, y_cursor, z_cursor))

        if index < run_count - 1:
            # The turn sits beyond the run end, and the next run starts back at that
            # same x. Both decks abut the landing on the same side, which is what makes
            # the switchback fold instead of drift.
            next_y = y_start + sign * ((run_count - index - 2) * pitch + top_half)
            landings.append(RampLanding(
                index=index + 1,
                x=x_cursor + (MIN_TURN_LANDING_M / 2.0 if east
                              else -MIN_TURN_LANDING_M / 2.0),
                y=(y_cursor + next_y) / 2.0, z=z_cursor,
                size_x=MIN_TURN_LANDING_M,
                size_y=pitch,
                kind='turn'))

    landings.append(RampLanding(
        index=run_count,
        x=x_cursor + (MIN_LANDING_LENGTH_M / 2.0 if runs[-1].direction > 0
                      else -MIN_LANDING_LENGTH_M / 2.0),
        y=y_cursor, z=z_cursor,
        size_x=MIN_LANDING_LENGTH_M, size_y=max(width, MIN_LANDING_LENGTH_M),
        kind='top'))
    path.append((landings[-1].x, y_cursor, z_cursor))

    plan = RampPlan(
        rise_m=round(rise_m, 4), width_m=round(width, 4), runs=runs, landings=landings,
        centre_line=[(round(x, 4), round(y, 4), round(z, 4)) for x, y, z in path],
        footprint_x_m=round(span, 3), footprint_y_m=round(needed_y, 3),
        handrails_required=rise_m > HANDRAIL_RISE_THRESHOLD_M,
        citations=[
            '405.2 running slope not steeper than 1:12',
            '405.5 clear width 915 mm minimum',
            '405.6 rise 760 mm maximum per run',
            '405.7.3 landing length 1525 mm minimum',
            '405.7.4 turn landings 1525 x 1525 mm',
            '405.8 handrails where a run rises more than 150 mm',
            '405.9.2 edge protection by a 100 mm curb',
            '505.4 handrail height 915 mm; 505.10 extensions 305 mm',
        ])
    return plan if not plan.compliance() else None
