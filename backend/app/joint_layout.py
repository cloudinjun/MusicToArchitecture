"""Whole-root proposals in free XY, registered by the existing PV author.

These are spatial relationships, not building silhouettes. Every proposal is
rejected or accepted with its complete rooms, routes, arrival and facade reserve.
"""
from pydantic import BaseModel
from typing import Literal


class JointRoot(BaseModel):
    relation: str
    hall_bounds: tuple[float, float, float, float]
    hall_placement: Literal['exact', 'residual_domain'] = 'exact'
    foyer_placement: Literal['hall_front', 'between_cores'] = 'hall_front'
    secondary_run_axis: Literal['x', 'y'] = 'y'
    primary_left: float
    primary_top: float
    secondary_right: float
    secondary_bottom: float
    arrival_top: float
    basis: str


def root_proposals(brief, datums, controls, relation):
    """Fit hall/core stations to the remaining parcel field, never scale rooms.

    Concentrated terminals gather at the rear public threshold. Separated
    terminals move the second complete stair to the hall's opposite end.
    The stair landing, corridor and lift dimensions define the feasible field.
    Exact polygon and full-building feasibility are evaluated by the PV author.
    """
    from .compiler_v3 import _core_box, LIFT_SHAFT_M, CORE_CLEARANCE_M
    from .datums import flight_run
    from .legacy_program_layout import hall_depth_for, LayoutRejected
    from .approach import ENTRANCE_MIN_WIDTH_M, entry_landing_rect
    from .portals import APPROACH_WIDTH_M
    from .envelope import ENTRANCE_REVEAL_DEPTH_M
    from .partitions import PARTITION_TYPES
    if relation not in ('concentrated_threshold', 'separated_terminals'):
        raise ValueError('Unknown joint root relationship')
    if controls.backbone_layout != 'distributed_cores' or controls.stair_run_axis != 'x':
        raise ValueError('Joint roots currently require the distributed X/Y stair adapter')
    x0,y0,x1,y1 = brief.massing_limit_shape.bounds
    a,b,c,d = _core_box(0,0,controls.flight_width_m,flight_run(controls.flight_width_m),run_axis='x')
    cw,cd = c-a,d-b
    corridor = controls.corridor_width_m
    lift = LIFT_SHAFT_M + 2*CORE_CLEARANCE_M
    spaces = {s.id:s for s in brief.resolved_spaces()}
    house,stage = spaces['SP-AUDITORIUM'],spaces['SP-STAGE']
    # The secondary stair and its full-width approach spend the side field.
    # Hall proposals may not borrow either reservation even provisionally.
    hall_right = x1-cd-corridor
    wall = max(p.thickness_mm for p in PARTITION_TYPES)/1000.
    entry_depth = max(corridor,-entry_landing_rect(controls.flight_width_m)[1]+wall)
    shared_depth = max(entry_depth,lift/2+APPROACH_WIDTH_M/2)
    frontage = max(max(corridor,ENTRANCE_MIN_WIDTH_M)+2*wall,
                   ENTRANCE_MIN_WIDTH_M+2*(ENTRANCE_REVEAL_DEPTH_M+controls.arrival_facade_allowance_m))
    arrival_top = y1-cd
    hall_top = arrival_top-frontage
    foyer_placement = 'hall_front'
    secondary_run_axis = 'y'
    residual_depth_proposal = False
    try:
        preferred = hall_depth_for(house,stage,available_width=hall_right-x0,
            available_depth=hall_top-y0,position=controls.hall_depth_position)
    except LayoutRejected:
        # Rotate the complete secondary core into the rear band, releasing the
        # east landing strip. Its end gallery and full-area rear commons are
        # rebuilt by the author; neither a flight nor a room is scaled to fit.
        if relation == 'concentrated_threshold':
            foyer_placement = 'between_cores'
            secondary_run_axis = 'x'
            hall_right = x1
        try:
            preferred = hall_depth_for(house,stage,available_width=hall_right-x0,
                available_depth=hall_top-y0,position=controls.hall_depth_position)
        except LayoutRejected:
            # The entrance is a local obstacle, not a parcel-wide exclusion band.
            # Propose proportions up to the rear corridor; the PV author must
            # still place them in the exact residual domain and validate all
            # arrival, core, room and connector intersections. This is not fit.
            hall_top = arrival_top-corridor
            preferred = hall_depth_for(house,stage,available_width=hall_right-x0,
                available_depth=hall_top-y0,position=controls.hall_depth_position)
            residual_depth_proposal = True
    depths = [preferred, hall_depth_for(house,stage,available_width=hall_right-x0,
        available_depth=hall_top-y0,position=1.)]
    for depth in dict.fromkeys(depths):
        width = (house.area_m2+stage.area_m2)/depth
        hall = (hall_right-width,y0,hall_right,y0+depth)
        yield JointRoot(relation=relation,hall_bounds=hall,hall_placement='residual_domain',
            foyer_placement=foyer_placement,
            secondary_run_axis=secondary_run_axis,
            primary_left=x0+lift+shared_depth-entry_depth,primary_top=y1,secondary_right=x1,
            arrival_top=arrival_top,
            secondary_bottom=(y1-cd if secondary_run_axis=='x' else
                y1-cw if relation=='concentrated_threshold' else hall[1]+corridor),
            basis='Hall area and proportion are proposed from the parcel field; its position is solved '
                  'in the exact residual polygon after the complete arrival reservation. '
                  'secondary terminal follows the selected hall-end relationship. '
                  'Primary stair/lift use the remaining rear threshold; all geometry remains provisional. '
                  + ('Local entrance exclusion deferred to exact residual placement; '
                     'the former full-width frontage band had no feasible hall interval. '
                     if residual_depth_proposal else '')
                  + ('Empty hall interval triggers a complete X-axis secondary core and rear commons; '
                     'geometric feasibility repair, not a new music decision.'
                     if secondary_run_axis=='x' else ''))
