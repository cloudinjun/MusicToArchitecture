"""Shared lift approach geometry for PV floor, column clearance and door checks."""
from shapely.geometry import box


def lift_approach_bounds(cx, cy, shaft_width, face, width, depth):
    half = shaft_width/2
    if face == 'south':
        return cx-width/2,cy-half-depth,cx+width/2,cy-half
    if face == 'north':
        return cx-width/2,cy+half,cx+width/2,cy+half+depth
    if face == 'east':
        return cx+half,cy-width/2,cx+half+depth,cy+width/2
    if face == 'west':
        return cx-half-depth,cy-width/2,cx-half,cy+width/2
    raise ValueError('Unknown lift access face')


def lift_access_regions(lattice, level_id):
    from .compiler_v3 import LIFT_SHAFT_M, LIFT_DOOR_W_M
    from .portals import APPROACH_WIDTH_M, APPROACH_DEPTH_M
    return [box(*lift_approach_bounds(core.x,core.y,LIFT_SHAFT_M,core.access_face,
                max(LIFT_DOOR_W_M,APPROACH_WIDTH_M),APPROACH_DEPTH_M))
            for core in lattice.given_cores if core.kind=='lift'
            and getattr(core,'access_face',None) is not None
            and (not core.serves or level_id in core.serves)]


def column_access_regions(lattice, datums, approach):
    """Shared full-section column keep-outs, before either column emitter runs.

    Read the actual entrance recipe used by the envelope; a column must avoid
    the aperture and both approach sides, not merely the door centre line.
    """
    from .envelope import planned_entrance
    regions = {level.id: lift_access_regions(lattice, level.id) for level in lattice.levels}
    entrance = planned_entrance(lattice, datums, approach)
    if entrance is not None:
        regions[entrance.level_id].extend([
            entrance.aperture, entrance.inside_approach, entrance.outside_approach])
    return regions
