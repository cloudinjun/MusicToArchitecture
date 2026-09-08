"""Shared architectural approach planning, in a boundary station's local frame.

The authoring grammar and building compiler use this same feasibility calculation.
ADA dimensions remain in ada.py; the dimensions here are project planning choices.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pydantic import BaseModel

from .ada import (
    MAX_RUN_RISE_M, MIN_CLEAR_WIDTH_M, MIN_TURN_LANDING_M, RampPlan, plan_switchback_ramp,
)

# Project planning allowances, not adopted site or code limits.
APRON_DEPTH_M = 21.0
LANDING_OVERLAP_M = 0.9
ENTRANCE_MIN_WIDTH_M = 2.4
PUBLIC_STAIR_TREAD_M = .3  # studio planning choice; adopted stair rules remain reviewable


def entry_landing_rect(flight_width):
    """One threshold allowance shared by the author and emitter, in local UV."""
    from .envelope import ENTRANCE_REVEAL_DEPTH_M
    from .portals import APPROACH_DEPTH_M
    reach = ENTRANCE_REVEAL_DEPTH_M/2 + APPROACH_DEPTH_M
    half = max(flight_width*1.9,ENTRANCE_MIN_WIDTH_M)/2
    return (-half,-reach,half,reach)


class ArrivalAssembly(BaseModel):
    """Frozen arrival in the PV boundary station's frame; U tangent, V outward."""
    entry_rect: tuple[float,float,float,float]
    stair_width_m: float
    stair_start_v: float
    stair_end_v: float
    stair_family: str = 'broad_straight'
    facade_allowance_m: float
    ramp: RampPlan
    link_rect: tuple[float,float,float,float]
    reserved_rects: list[tuple[float,float,float,float]]
    basis: str

    def reserved_footprint(self, origin, tangent, outward, *, landing_clearance_m=0.):
        """Physical claim, optionally including room-side landing wall allowance.

        Site paving reads the physical claim. Room authoring also reserves the
        same landing clearance that downstream public-circulation allocation
        subtracts; that clearance is not extra physical arrival geometry.
        """
        from shapely.geometry import box
        from shapely.ops import unary_union
        parts = [box(*r) for r in self.reserved_rects]
        if landing_clearance_m:
            top = next(p for p in self.ramp.landings if p.kind == 'top')
            parts += [shape.buffer(landing_clearance_m,join_style=2) for shape in (
                box(*self.entry_rect),box(top.x-top.size_x/2,top.y-top.size_y/2,
                                         top.x+top.size_x/2,top.y+top.size_y/2))]
        return local_region_to_world(unary_union(parts),
                                     origin,tangent,outward)


def local_region_to_world(region, origin, tangent, outward):
    from shapely.affinity import affine_transform
    return affine_transform(region,[tangent[0],outward[0],tangent[1],outward[1],*origin])


def plan_compact_arrival(*, parcel, origin, tangent, outward, rise_m,
                         flight_width_m, riser_m, tread_m, weather_reach_m,
                         protected=None, landing_clearance_m=0.):
    """Reserve a complete low-rise stair + accessible route before rooms.

    Only a single-flight public stair is offered here. Taller expressive families
    retain their existing path; a failed compact plan returns no assembly. The
    selected grammar's desired family remains separately recorded on the intent.
    ``protected`` is existing world-XY program/core/route floor. Both ramp sides
    must avoid it, including the downstream landing allowance supplied by authoring.
    """
    from shapely.affinity import affine_transform
    from shapely.geometry import box
    from shapely.ops import unary_union
    from .portals import APPROACH_DEPTH_M
    if not 0 < rise_m <= MAX_RUN_RISE_M:
        return None
    local = affine_transform(parcel,[*tangent,*outward,
        -sum(a*b for a,b in zip(origin,tangent)),
        -sum(a*b for a,b in zip(origin,outward))])
    u0,_,u1,v1 = local.bounds
    entry = entry_landing_rect(flight_width_m)
    stair_width = flight_width_m*1.3
    stair_end = entry[3]
    stair_start = stair_end + math.ceil(rise_m/riser_m)*tread_m
    margin = .1  # body/guard planning allowance, not a code clearance
    ramp_width = max(MIN_CLEAR_WIDTH_M,min(flight_width_m*.62,MIN_TURN_LANDING_M))
    start_v = weather_reach_m+margin
    gap = entry[2]+MIN_TURN_LANDING_M
    for low,high in ((u0+margin,-gap),(gap,u1-margin)):
        if high<=low:
            continue
        # Solve toward the entry on the canonical negative side, then mirror the
        # whole ramp for the opposite side. Starting both sides at their low U
        # coordinate put the positive-side bottom beside the entrance and made
        # its elevated return gallery cross the sloping run and bottom landing.
        mirrored = low > 0
        ramp = plan_switchback_ramp(rise_m=rise_m,width_m=ramp_width,
            x_min=-high if mirrored else low,x_max=-low if mirrored else high,
            y_start=start_v,y_available=v1-start_v-margin,
            z_base=0.,direction_y=1.)
        if ramp is None:
            continue
        if mirrored:
            ramp = ramp.model_copy(update={
                'runs':[run.model_copy(update={'x_start':-run.x_start,'x_end':-run.x_end,
                                               'direction':-run.direction}) for run in ramp.runs],
                'landings':[p.model_copy(update={'x':-p.x}) for p in ramp.landings],
                'centre_line':[(-x,y,z) for x,y,z in ramp.centre_line]})
        top = next(p for p in ramp.landings if p.kind=='top')
        join = entry[0]+margin if top.x<0 else entry[2]-margin
        link = (min(top.x,join)-margin,entry[3]-APPROACH_DEPTH_M,
                max(top.x,join)+margin,top.y+top.size_y/2)
        rects = [entry,(-stair_width/2,stair_end,stair_width/2,stair_start),link]
        rects += [(p.x-p.size_x/2,p.y-p.size_y/2,p.x+p.size_x/2,p.y+p.size_y/2)
                  for p in ramp.landings]
        rects += [(min(r.x_start,r.x_end),r.y-ramp.pitch_m/2,
                   max(r.x_start,r.x_end),r.y+ramp.pitch_m/2) for r in ramp.runs]
        if not local.buffer(1e-7).covers(unary_union([box(*r) for r in rects]).buffer(margin,join_style=2)):
            continue
        assembly = ArrivalAssembly(entry_rect=entry,stair_width_m=stair_width,
            facade_allowance_m=weather_reach_m,
            stair_start_v=stair_start,stair_end_v=stair_end,ramp=ramp,
            link_rect=link,reserved_rects=rects,
            basis='Low-rise whole-arrival choice before room placement: one public '
                  'flight plus checked ramp, complete landings and a shared threshold '
                  'gallery; exact parcel and weather reach constrain the reservation. '
                  'Existing protected floor, when supplied, also constrains the side choice. '
                  'Capacity, grading and adopted-code approval remain unresolved.')
        if protected is not None and assembly.reserved_footprint(
                origin,tangent,outward,landing_clearance_m=landing_clearance_m
                ).intersection(protected).area > 1e-7:
            continue
        return assembly
    return None


@dataclass(frozen=True)
class BoundaryApproach:
    ramp: RampPlan | None
    ramp_width_m: float
    landing_width_m: float
    sides: dict[str, tuple[float, float]]
    order: tuple[str, ...]


def plan_boundary_switchback(
    *, edge_length_m: float, fraction: float, flight_width_m: float,
    rise_m: float, approach_depth_m: float, preference: str,
    z_base: float = 0.0, apron_depth_m: float = APRON_DEPTH_M,
) -> BoundaryApproach:
    """Try the declared edge's two sides; retain the fallback station if neither fits."""
    ramp_width = max(MIN_CLEAR_WIDTH_M,
                     min(flight_width_m * 0.62, MIN_TURN_LANDING_M))
    landing_width = max(flight_width_m * 1.9, ENTRANCE_MIN_WIDTH_M)
    margin = max(0.3, min(1.5, edge_length_m * 0.06))
    clearance = landing_width / 2.0 + ramp_width
    sides = {
        'negative': (-edge_length_m * fraction + margin, -clearance),
        'positive': (clearance, edge_length_m * (1.0 - fraction) - margin),
    }
    if preference == 'edge_parallel':
        order = ('negative', 'positive')
    elif preference == 'terrace_return':
        order = ('positive', 'negative')
    else:
        order = tuple(sorted(sides, key=lambda side:
                             sides[side][1] - sides[side][0], reverse=True))
    ramp = None
    for side in order:
        low, high = sides[side]
        if high <= low:
            continue
        ramp = plan_switchback_ramp(
            rise_m=rise_m, width_m=ramp_width, x_min=low, x_max=high,
            y_start=-LANDING_OVERLAP_M,
            y_available=min(apron_depth_m, approach_depth_m),
            z_base=z_base, direction_y=1.0)
        if ramp is not None:
            break
    return BoundaryApproach(ramp, ramp_width, landing_width, sides, order)


def site_approach_finding(builder, element_ids):
    """The exterior PV exception still belongs inside the actual parcel.

    Measure full emitted bodies, including handrails. No clipping of a stair or
    ramp is allowed here, and an absent assembly cannot count as a fitted route.
    """
    from shapely.ops import unary_union
    from .physical_geometry import physical_projection
    from .plan_regions import polygon
    from .program_volume_contracts import CirculationFinding

    parcel = polygon(builder.lattice.site_boundary)
    emitted = {instance.id: instance.geometry for group in builder.groups.values()
               for instance in group.instances if instance.id in element_ids}
    missing = sorted(set(element_ids)-emitted.keys())
    outside = {}
    for ident,geometry in emitted.items():
        footprint = physical_projection(geometry,profiles=builder.profiles).footprint
        excess = footprint.difference(parcel.buffer(1e-7))
        if excess.area > 1e-8:
            outside[ident] = excess
    status = 'failed' if outside else 'unevaluated' if missing or not emitted else 'passed'
    detail = (f'{len(outside)} approach parts leave the parcel; '
              f'{unary_union(list(outside.values())).area:.3f} m2 union outside. '
              + ', '.join(sorted(outside)) if outside else
              'No complete emitted approach is available to measure.' if missing or not emitted else
              'Every emitted exterior approach body is inside the brief parcel. '
              'This checks containment only, not route continuity or accessible operation.')
    return CirculationFinding(id='PV-CIRC-SITE-CONTAINMENT',status=status,
                              subject='exterior approach within parcel',detail=detail)
