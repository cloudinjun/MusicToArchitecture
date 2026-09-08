"""Gravity transfer around a theatre clear volume, within the selected steel frame.

The plan is calculated before any existing support is removed.  Loads remain split
into D/L/Lr; a pin-jointed, linear-elastic plane truss is actually solved, including
member self weight.  Catalogue failure leaves the original support in place.
This is a limited gravity calculation, not a structural approval.  Connection,
foundation and the stiffness/strength of the drawn lateral restraints remain named
review items.  AISC 360-16 D2 gross yielding and E3 use the same material/product
library as sizing.py (https://www.aisc.org/globalassets/aisc/publications/standards/
a360-16w-rev-june-2019.pdf).
"""
from __future__ import annotations

import math
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

from .geometry import BoxGeometry, v3
from .loads import LoadCase, OCCUPANCY_LIVE, composite_steel_deck, flat_roof_assembly
from .registry import catalogue, profile_for
from .sections import MATERIALS
from .sizing import MemberCheck, SelectionResult, check_column, select_beam
from .hall_enclosure import HallEnclosureReport
from .hall_stations import hall_axes, retained_edge_stations, volume_section

# These are geometric/detailing review allowances, not code clearances.
WALL_ZONE_M = .30
SOFFIT_RESERVE_M = .05
MIN_TRUSS_DEPTH_M = .80
COMBINATIONS = {'1.4D': (1.4, 0., 0.),
                '1.2D+1.6L+0.5Lr': (1.2, 1.6, .5),
                '1.2D+1.0L+1.6Lr': (1.2, 1., 1.6)}
REVIEW_ITEMS = [
    'Connection/gusset, net-section rupture, block shear and local bearing are unevaluated.',
    'Second-order, imperfection, seismic/wind and combined axial/bending effects are unevaluated.',
    'Drawn transverse restraint ties and crosses are required at both chord planes; '
    'their lateral strength/stiffness and diaphragm anchorage are unevaluated.',
    'Footings carry reported reactions; soil bearing, punching and reinforcement are unevaluated.',
    'Uniform live-load arrangements only; adverse patterned occupancy loads are unevaluated.',
]


class TransferLoad(BaseModel):
    node: int
    y: float
    dead_kn: float
    live_kn: float
    roof_live_kn: float
    tributary_area_by_level: dict[str, float] = Field(default_factory=dict)


class TransferMember(BaseModel):
    id: str
    role: str
    node_a: int
    node_b: int
    length_m: float
    unbraced_length_m: float
    section_id: str | None = None
    analysis_section_id: str
    axial_kn: dict[str, float] = Field(default_factory=dict)
    tension_capacity_kn: float = 0.
    compression_capacity_kn: float = 0.
    utilisation: float | None = None
    compression_check: MemberCheck | None = None
    selected: bool = False


class TransferPier(BaseModel):
    id: str
    x_index: int
    y_index: int
    level_index: int
    dead_kn: float
    live_kn: float
    roof_live_kn: float
    check: MemberCheck | None = None


class TransferFrame(BaseModel):
    id: str
    x_index: int
    x: float
    level_index: int
    level_id: str
    y_indices: list[int]
    span_m: float
    top_z: float
    bottom_z: float
    clear_top_z: float
    nodes: list[tuple[float, float]] = Field(default_factory=list)  # y,z
    node_loads: list[TransferLoad] = Field(default_factory=list)
    beam_trial: SelectionResult | None = None
    members: list[TransferMember] = Field(default_factory=list)
    reactions_kn: dict[str, list[float]] = Field(default_factory=dict)
    piers: list[TransferPier] = Field(default_factory=list)
    equilibrium_residual_kn: float | None = None
    total_deflection_mm: float | None = None
    live_deflection_mm: float | None = None
    status: Literal['failed', 'review_required'] = 'failed'
    activated: bool = False
    findings: list[str] = Field(default_factory=list)


class TransferEdge(BaseModel):
    x: float
    x_bay_index: int
    y_indices: list[int]
    y_coordinates: dict[int, float] = Field(default_factory=dict)
    regular_x_index: int | None = None
    level_index: int
    check: MemberCheck | None = None
    dead_kn: float
    live_kn: float
    roof_live_kn: float


class TransferReport(BaseModel):
    status: Literal['not_required', 'failed', 'review_required'] = 'not_required'
    method: str = 'linear elastic pin-jointed plane truss; catalogue axial selection'
    basis: str = ('D from emitted floor/roof assemblies and selected frame member weights; '
                  'L from the governing allocated occupancy without reduction; Lr from roof '
                  'occupancy. Tributary polygons are clipped to plates minus actual voids. '
                  'Resized pier self weight is added conservatively to the original frame-weight allowance.')
    frames: list[TransferFrame] = Field(default_factory=list)
    edges: list[TransferEdge] = Field(default_factory=list)
    boundary_piers: list[TransferPier] = Field(default_factory=list)
    hall_enclosure: HallEnclosureReport | None = None
    findings: list[str] = Field(default_factory=list)
    unevaluated: list[str] = Field(default_factory=lambda: list(REVIEW_ITEMS))


def solve_plane_truss(nodes, connections, areas_mm2, loads_kn, modulus_mpa=200_000.):
    """2D stiffness solution (m,kN). Positive axial force denotes tension.

    Node 0 is pinned; node n/2-1 is a vertical roller. The first half of the
    nodes are the top chord, so those restraints bear on real boundary piers.
    Returns forces, displacement, full nodal reactions and free-DOF residual.
    Invalid geometry or a mechanism raises ValueError; no synthetic solution.
    """
    xy = np.asarray(nodes, dtype=float)
    count = len(xy)
    if count < 4 or count % 2 or len(connections) != len(areas_mm2):
        raise ValueError('invalid transfer node/member arrays')
    force = np.asarray(loads_kn, dtype=float)
    if force.shape != (count, 2) or not np.isfinite(force).all():
        raise ValueError('invalid transfer nodal loading')
    k = np.zeros((count * 2, count * 2))
    rows = []
    for (a, b), area in zip(connections, areas_mm2):
        delta = xy[b] - xy[a]
        length = float(np.linalg.norm(delta))
        if length < 1e-8 or area <= 0:
            raise ValueError('zero-length or nonpositive-area transfer member')
        c, s = delta / length
        direction = np.array([-c, -s, c, s])
        dofs = [2*a, 2*a+1, 2*b, 2*b+1]
        ea_l = modulus_mpa * area / (1000. * length)
        k[np.ix_(dofs, dofs)] += ea_l * np.outer(direction, direction)
        rows.append((dofs, direction, ea_l))
    fixed = [0, 1, 2*(count//2-1)+1]
    free = [i for i in range(count*2) if i not in fixed]
    reduced = k[np.ix_(free, free)]
    if not np.isfinite(reduced).all() or np.linalg.matrix_rank(reduced) < len(free):
        raise ValueError('transfer topology is a mechanism')
    u = np.zeros(count * 2)
    try:
        u[free] = np.linalg.solve(reduced, force.ravel()[free])
    except np.linalg.LinAlgError as exc:
        raise ValueError('transfer stiffness solution failed') from exc
    residual = k @ u - force.ravel()
    axial = np.array([ea_l * np.dot(direction, u[dofs])
                      for dofs, direction, ea_l in rows])
    error = float(np.max(np.abs(residual[free])))
    if not np.isfinite(u).all() or error > max(1e-6, np.max(np.abs(force))*1e-7):
        raise ValueError('transfer equilibrium residual exceeds numerical tolerance')
    return axial, u.reshape(count, 2), residual.reshape(count, 2), error


def truss_topology(stations, top_z, bottom_z):
    n = len(stations)
    if n < 3 or top_z <= bottom_z or any(b <= a for a,b in zip(stations, stations[1:])):
        raise ValueError('invalid transfer stations/depth')
    nodes = [(y, top_z) for y in stations] + [(y, bottom_z) for y in stations]
    members = []
    for i in range(n-1):
        members.extend([(i, i+1, 'top_chord'), (n+i, n+i+1, 'bottom_chord')])
    members.extend((i, n+i, 'vertical') for i in range(n))
    # Pratt-type gravity diagonals incline toward the span centre.
    members.extend((i, n+i+1, 'diagonal') if i < (n-1)/2
                   else (n+i, i+1, 'diagonal') for i in range(n-1))
    return nodes, members


def _axial_choice(identifier, forces, length, sections):
    compression = max(0., -min(forces.values()))
    tension = max(0., max(forces.values()))
    for section in sections:
        check = check_column(identifier, compression, length, section)
        tensile = .9 * MATERIALS[section.material_id].strength_mpa * section.area_mm2 / 1000.
        if (check.passes and (check.validation is None or check.validation.passes)
                and tension <= tensile):
            return section, check, tensile
    return None, None, 0.


def analyse_transfer(frame, sections):
    """Select catalogue strength/stiffness, re-solving weight and service drift.

    Uniform EA growth predicts an inverse drift change for this linear truss.
    It only supplies a minimum-area trial; discrete products and their increased
    self weight are solved again before any serviceability status is earned.
    """
    topology = truss_topology([load.y for load in frame.node_loads], frame.top_z, frame.bottom_z)
    nodes, members = topology
    frame.nodes = nodes
    n = len(nodes)//2
    connections = [(a,b) for a,b,_ in members]
    lengths = [math.dist(nodes[a], nodes[b]) for a,b in connections]
    chosen = [sections[0]] * len(members)
    results = None
    stable = False
    for iteration in range(12):
        load_vectors = {name: np.zeros((2*n, 2)) for name in ('D','L','Lr')}
        for load in frame.node_loads:
            for name, value in zip(('D','L','Lr'), (load.dead_kn,load.live_kn,load.roof_live_kn)):
                load_vectors[name][load.node,1] -= value
        for (a,b), length, section in zip(connections,lengths,chosen):
            load_vectors['D'][[a,b],1] -= section.self_weight_kn_m * length / 2.
        areas = [section.area_mm2 for section in chosen]
        results = {name: solve_plane_truss(nodes,connections,areas,load)
                   for name,load in load_vectors.items()}
        factored = {name: sum(factor * results[case][0]
                             for factor,case in zip(factors,('D','L','Lr')))
                    for name,factors in COMBINATIONS.items()}
        total_mm, live_mm = _service_deflections(results)
        stiffness_scale = max(1., total_mm / (frame.span_m*1000./240.),
                              live_mm / (frame.span_m*1000./360.))
        records, next_sections = [], []
        for j, ((a,b,role),length) in enumerate(zip(members,lengths)):
            forces = {name: float(value[j]) for name,value in factored.items()}
            minimum_area = chosen[j].area_mm2 * stiffness_scale
            trials = [s for s in sections if s.area_mm2 >= minimum_area - 1e-8]
            # Reaching the catalogue ceiling is an evaluated trial, never proof
            # that drift fits. The final displacement check still fails it.
            section, check, tensile = _axial_choice(
                f'{frame.id}-{j:03d}', forces, length, trials or [sections[-1]])
            selected = section is not None
            section = section or sections[-1]
            # Do not reduce sections between weight iterations: convergence stays
            # conservative and a light/heavy two-cycle cannot claim success.
            if selected and section.area_mm2 < chosen[j].area_mm2:
                section = chosen[j]
                _,check,tensile = _axial_choice(f'{frame.id}-{j:03d}',forces,length,[section])
            next_sections.append(section)
            capacity = check.utilisations[0].capacity if check else 0.
            ratio = (max(max(forces.values(),default=0)/max(tensile,1e-9),
                         -min(forces.values(),default=0)/max(capacity,1e-9),
                         check.max_ratio if check else 0.) if selected else None)
            records.append(TransferMember(id=f'{frame.id}-{j:03d}',role=role,node_a=a,node_b=b,
                length_m=length,unbraced_length_m=length,
                section_id=section.id if selected else None,analysis_section_id=section.id,
                axial_kn=forces,tension_capacity_kn=tensile,compression_capacity_kn=capacity,
                utilisation=ratio,compression_check=check,selected=selected))
        same = all(a.id == b.id for a,b in zip(chosen,next_sections))
        chosen = next_sections
        frame.members = records
        if same:
            stable = True
            break
    if not stable:
        frame.findings.append('Member/self-weight iteration did not converge; replacement disabled.')
    # Refresh using precisely the selected sections, including on a failure; the
    # analysis_section_id distinguishes a trial section from a selected product.
    frame.equilibrium_residual_kn = max(result[3] for result in results.values())
    frame.reactions_kn = {name:[float(result[2][0,1]),float(result[2][n-1,1])]
                          for name,result in results.items()}
    frame.total_deflection_mm, frame.live_deflection_mm = _service_deflections(results)
    missing = [m.id for m in frame.members if not m.selected]
    if missing:
        frame.findings.append('No catalogue axial section for: '+', '.join(missing))
    if frame.total_deflection_mm > frame.span_m*1000./240.:
        frame.findings.append('Service total vertical deflection exceeds project L/240 review limit.')
    if frame.live_deflection_mm > frame.span_m*1000./360.:
        frame.findings.append('Service live vertical deflection exceeds project L/360 review limit.')
    if not frame.findings:
        frame.status = 'review_required'
    return frame


def _service_deflections(results):
    total = sum(results[name][1] for name in ('D', 'L', 'Lr'))
    live = results['L'][1] + results['Lr'][1]
    return (float(np.max(np.abs(total[:, 1])) * 1000.),
            float(np.max(np.abs(live[:, 1])) * 1000.))


def _tributary(lines, i):
    a = (lines[i-1]+lines[i])/2 if i else lines[i]-(lines[1]-lines[0])/2
    b = (lines[i]+lines[i+1])/2 if i+1<len(lines) else lines[i]+(lines[-1]-lines[-2])/2
    return a,b


def tributary_load(lattice, region, start_index, live_kpa, sizing):
    """Service load above an actual support, with openings removed geometrically."""
    d = l = lr = 0.
    areas = {}
    joist = next(s for s in catalogue('steel_w_shape') if s.id == sizing.joist.check.section_id)
    beam = next(s for s in catalogue('steel_w_shape') if s.id == sizing.beam.check.section_id)
    column = next(s for s in catalogue('steel_w_shape')+catalogue('steel_hss_square')
                  if s.id == sizing.column.check.section_id)
    bx = abs(lattice.x_lines[1]-lattice.x_lines[0])
    by = abs(lattice.y_lines[1]-lattice.y_lines[0])
    # Two orthogonal primary tiers plus the selected secondary tier.  Density uses
    # the compiled frame spacing stored by the caller on this narrow context.
    steel_kpa = beam.self_weight_kn_m*(1/bx+1/by)+joist.self_weight_kn_m/sizing.transfer_joist_spacing
    for level in lattice.levels:
        if level.index < start_index or level.kind == 'podium':
            continue
        plate = Polygon([(p.x,p.y) for p in level.plate])
        for hole in level.voids:
            plate = plate.difference(Polygon([(p.x,p.y) for p in hole]))
        area = float(plate.intersection(region).area)
        areas[level.id] = area
        roof = level.kind == 'roof'
        assembly = flat_roof_assembly() if roof else composite_steel_deck()
        d += area*(assembly.superimposed_dead_kpa()+steel_kpa)
        if roof:
            lr += area*OCCUPANCY_LIVE['roof_ordinary'].live_kpa
        else:
            l += area*live_kpa
    levels = [lv for lv in lattice.levels if lv.index >= start_index]
    if levels and any(area>1e-6 for area in areas.values()):
        d += column.self_weight_kn_m * max(0.,levels[-1].z-levels[0].z)
    return d,l,lr,areas


def _pier_choice(identifier, components, length, sections, *, self_weight_height_m=0.):
    for section in sections:
        loads = (components[0]+section.self_weight_kn_m*self_weight_height_m,*components[1:])
        demand = max(sum(f*v for f,v in zip(combo,loads)) for combo in COMBINATIONS.values())
        check = check_column(identifier,demand,length,section)
        if check.passes and (check.validation is None or check.validation.passes):
            return check
    return None


def _restraint_intervals(lattice, point, top_level):
    elevations = [lattice.levels[0].z]
    for level in lattice.levels[1:top_level.index]:
        plate = Polygon([(v.x,v.y) for v in level.plate])
        for hole in level.voids:
            plate = plate.difference(Polygon([(v.x,v.y) for v in hole]))
        if plate.buffer(.002).covers(point):
            elevations.append(level.z)
    elevations.append(top_level.z)
    return list(zip(elevations,elevations[1:]))


def _station_tributary(lines, index):
    if not isinstance(lines, dict):
        return _tributary(lines, index)
    keys = sorted(lines, key=lines.get)
    return _tributary([lines[k] for k in keys], keys.index(index))


def _pier_inside_volume(lattice, x, y, lower, upper, check):
    """Measure the whole selected section through every changing volume section."""
    if check is None or not getattr(lattice, 'hall_support_grid', None):
        return True
    section = next(s for s in catalogue('steel_hss_square') if s.id == check.section_id)
    half = max(section.width_mm, section.depth_mm)/2000.
    body = box(x-half, y-half, x+half, y+half)
    base = lattice.occupied[0].z
    cuts = sorted({max(base, lower.z), upper.z} | {
        z for r in lattice.program_volume_regions for z in (r.z_base, r.z_top)
        if max(base, lower.z) < z < upper.z})
    # Below the occupied datum the pier is registered on the base footprint.
    if lower.z < base and not Polygon([(p.x,p.y) for p in lattice.occupied[0].plate]).buffer(1e-7).covers(body):
        return False
    return all(volume_section(lattice, (a+c)/2).buffer(1e-7).covers(body)
               for a,c in zip(cuts,cuts[1:]) if c > a)


def reserve_transfer_zone(lattice, carve, slab_thickness_m):
    """Reserve the calculated geometry envelope before program allocation.

    Returns the first possible registered transfer level, or None. The caller
    applies carve.removed through its normal void/allocation chain.
    """
    if not hasattr(carve,'clear_house_m'):
        return None
    sections = catalogue('steel_w_shape')+catalogue('steel_hss_square')
    envelope = max(max(s.depth_mm,s.width_mm) for s in sections)/1000.
    clear_top = lattice.occupied[0].z+max(carve.clear_house_m,carve.clear_stage_m)
    level = next((lv for lv in lattice.levels
                  if lv.z-slab_thickness_m-envelope-clear_top >= MIN_TRUSS_DEPTH_M),None)
    if level is None:
        return None
    for lower in lattice.occupied[1:]:
        if lower.index >= level.index:
            continue
        cuts = carve.removed.setdefault(lower.index,[])
        for rect in (carve.house,carve.stage):
            if rect not in cuts:
                cuts.append(rect)
    return level


def frame_clear_top(lattice,carve,xi):
    """Raised stage plus its adjacent frame keeps crossing restraints clear."""
    from .archetypes import STAGE_RISE_M
    base=lattice.occupied[0].z
    common=base+max(carve.clear_house_m,carve.clear_stage_m)
    stage_left,_,stage_right,_=carve.stage
    adjacent=(lattice.x_lines[max(0,xi-1)] < stage_right
              and lattice.x_lines[min(len(lattice.x_lines)-1,xi+1)] > stage_left)
    return max(common,base+STAGE_RISE_M+carve.clear_stage_m) if adjacent else common


def _interrupted_support_stations(lattice, carve) -> list[tuple[int, int]]:
    """Actual registered support nodes inside the successful theatre clear volume."""
    if not hasattr(carve, 'clear_house_m'):
        return []
    rooms = (carve.house, carve.stage)
    x0, y0 = min(room[0] for room in rooms), min(room[1] for room in rooms)
    x1, y1 = max(room[2] for room in rooms), max(room[3] for room in rooms)
    return [(i, j) for i, x in enumerate(lattice.x_lines)
            for j, y in enumerate(lattice.y_lines)
            if x0 + WALL_ZONE_M < x < x1 - WALL_ZONE_M
            and y0 + WALL_ZONE_M < y < y1 - WALL_ZONE_M]


def required_structural_capabilities(lattice, carve):
    """Demand an implemented transfer emitter only where geometry interrupts supports.

    This is compiler eligibility. The physical/code domain remains unchanged and the
    selected emitter must still calculate and validate every replacement frame.
    """
    return (('theatre_gravity_transfer',)
            if _interrupted_support_stations(lattice, carve) else ())


def prepare_transfer(b, sizing, frame, occupancy, carve):
    """Make a complete replacement plan before the compiler emits any columns."""
    from types import SimpleNamespace
    report = TransferReport()
    b.transfer_structure = report
    if not hasattr(carve,'clear_house_m'):
        return report
    lattice = b.lattice
    interrupted = _interrupted_support_stations(lattice, carve)
    if not interrupted:
        return report
    base = lattice.occupied[0]
    report.status = 'failed'
    if frame.column_material != 'steel_white':
        report.findings.append('Theatre transfer is implemented only for the existing steel frame; original supports retained.')
        return report
    from .hall_enclosure import prepare_hall
    hall = prepare_hall(b, occupancy, carve)
    xl, yl = hall_axes(b)
    registered = getattr(lattice, 'hall_support_grid', None) is not None
    report.hall_enclosure = getattr(b, 'hall_enclosure', None)
    if report.hall_enclosure is not None and report.hall_enclosure.findings:
        report.findings.extend(report.hall_enclosure.findings)
        return report
    sections = sorted(catalogue('steel_w_shape')+catalogue('steel_hss_square'),key=lambda s:s.area_mm2)
    if registered:
        # Square products fit the registered, orientation-independent pier reserve.
        sections = sorted(catalogue('steel_hss_square'), key=lambda s:s.area_mm2)
    envelope = max(max(s.depth_mm,s.width_mm) for s in sections)/1000.
    clear_top = base.z+max(carve.clear_house_m,carve.clear_stage_m)
    slab = b.datums.value('slab_thickness_m')
    levels = [lv for lv in lattice.levels if lv.z-slab-envelope-clear_top >= MIN_TRUSS_DEPTH_M]
    if not levels:
        report.findings.append('No registered level provides a transfer depth above the complete theatre clear volume.')
        return report
    level = levels[0]
    top_z = level.z-slab-envelope/2
    bottom_z = clear_top+SOFFIT_RESERVE_M+envelope/2
    if top_z-bottom_z < MIN_TRUSS_DEPTH_M:
        report.findings.append('Actual hall beam and joist depths leave insufficient registered transfer depth; original support retained.')
        return report
    rect = (min(carve.house[0],carve.stage[0]),min(carve.house[1],carve.stage[1]),
            max(carve.house[2],carve.stage[2]),max(carve.house[3],carve.stage[3]))
    x0,y0,x1,y1 = rect
    south = [j for j,y in enumerate(lattice.y_lines) if y <= y0+.002]
    north = [j for j,y in enumerate(lattice.y_lines) if y >= y1-.002]
    if not south or not north:
        report.findings.append('No registered north/south boundary piers bound the theatre.')
        return report
    js = list(range(max(south),min(north)+1))
    if registered:
        js = hall.y_indices
    if len(js)<3:
        report.findings.append('Transfer needs at least one interior column station between its boundary piers.')
        return report
    context = SimpleNamespace(joist=sizing.joist,beam=sizing.beam,column=sizing.column,
                              transfer_joist_spacing=b.datums.value('joist_spacing_m'))
    xs = sorted({i for i, _j in interrupted})
    for xi in xs:
        x = lattice.x_lines[xi]
        # Keep the full eight-metre stage clearance above its raised deck. The
        # adjacent house frame rises too so transverse bottom restraints reach
        # the stage at the required height instead of cutting its upper corner.
        candidate_clear = frame_clear_top(lattice,carve,xi)
        candidate_bottom = candidate_clear+SOFFIT_RESERVE_M+envelope/2
        candidate = TransferFrame(id=f'STR-TRF-X{xi:02d}-{level.id}',x_index=xi,x=x,
            level_index=level.index,level_id=level.id,y_indices=js,
            span_m=yl[js[-1]]-yl[js[0]],
            top_z=top_z,bottom_z=candidate_bottom,clear_top_z=candidate_clear)
        for j in (js[0],js[-1]):
            p = Point(x,yl[j])
            if not Polygon([(v.x,v.y) for v in base.plate]).buffer(.002).covers(p):
                candidate.findings.append('Boundary pier has no ground-floor/foundation registration.')
        for n,j in enumerate(js):
            xa,xb = _station_tributary(xl,xi)
            ya,yb = _station_tributary(yl,j)
            values = tributary_load(lattice,box(xa,ya,xb,yb),level.index,occupancy.live_kpa,context)
            # End-station loads stay on their existing piers, never double counted
            # as transferred interior-column loads.
            if j in (js[0],js[-1]):
                values = (0.,0.,0.,{})
            if hall is not None:
                roof_d,roof_lr = b.hall_reactions.get((xi,j),(0.,0.))
                values = (values[0]+roof_d,values[1],values[2]+roof_lr,values[3])
            candidate.node_loads.append(TransferLoad(node=n,y=yl[j],
                dead_kn=values[0],live_kn=values[1],roof_live_kn=values[2],tributary_area_by_level=values[3]))
        if sum(load.dead_kn+load.live_kn+load.roof_live_kn for load in candidate.node_loads)<1e-6:
            continue  # No upper support to replace; no decorative transfer frame.
        span = candidate.span_m
        # For any nonnegative point-load placement, w=2*sum(P)/L bounds maximum
        # reaction, moment and elastic displacement. Roof live is included at the
        # full floor-live factor to envelope all three implemented combinations.
        d = 2*sum(load.dead_kn for load in candidate.node_loads)/span
        l = 2*sum(load.live_kn+load.roof_live_kn for load in candidate.node_loads)/span
        beams = catalogue('steel_w_shape')
        # Existing check_beam adds 1.2 self weight; adding 1/7 of the heaviest
        # candidate to D envelopes its missing .2 self-weight factor in 1.4D.
        d += max(s.self_weight_kn_m for s in beams)/7.
        candidate.beam_trial = select_beam(candidate.id+'-BEAM',span,1.,LoadCase(dead_kpa=d,live_kpa=l),
            beams,role='girder',unbraced_length_m=span,max_depth_mm=(level.z-slab-clear_top)*1000)
        try:
            analyse_transfer(candidate,sections)
        except ValueError as exc:
            candidate.findings.append(str(exc))
        if candidate.reactions_kn:
            for side,j in enumerate((js[0],js[-1])):
                xa,xb = _station_tributary(xl,xi)
                ya,yb = _station_tributary(yl,j)
                point = Point(x,yl[j])
                restraint_intervals = _restraint_intervals(lattice,point,level)
                for k in range(level.index):
                    lower,upper = lattice.levels[k:k+2]
                    values = tributary_load(lattice,box(xa,ya,xb,yb),k+1,occupancy.live_kpa,context)
                    force = [values[i]+candidate.reactions_kn[case][side] for i,case in enumerate(('D','L','Lr'))]
                    identifier = column_id(xi,j,k,lattice)
                    # A datum plane without floor geometry supplies no lateral
                    # restraint: use the complete interval between real floor
                    # restraints, including exposed piers above a retreating plate.
                    unbraced = next((c-a for a,c in restraint_intervals
                                     if a-1e-6<=lower.z<c-1e-6),upper.z-lower.z)
                    weight_height = level.z-lower.z
                    check = _pier_choice(identifier,force,unbraced,sections,self_weight_height_m=weight_height)
                    if check is not None:
                        section = next(s for s in sections if s.id==check.section_id)
                        force[0] += section.self_weight_kn_m*weight_height
                    candidate.piers.append(TransferPier(id=identifier,x_index=xi,y_index=j,level_index=k,
                        dead_kn=force[0],live_kn=force[1],roof_live_kn=force[2],check=check))
                    if check is None:
                        candidate.findings.append(f'No catalogue pier carries {identifier} plus its transfer reaction.')
                    elif not _pier_inside_volume(lattice,x,yl[j],lower,upper,check):
                        candidate.findings.append(f'Complete pier {identifier} leaves its Program Volume.')
        candidate.status = 'failed' if candidate.findings else 'review_required'
        report.frames.append(candidate)
    # A carve through a bay needs its own perimeter post line; otherwise omitting
    # the old column also strands the remaining strip of upper floor.
    bay = next((i for i in range(len(lattice.x_lines)-1)
                if lattice.x_lines[i]+.01 < x0 < lattice.x_lines[i+1]-.01),None)
    if bay is not None:
        # Pick a catalogue column, then derive its centre from its actual half
        # width. Repeat once if the shifted tributary width changes the selection.
        section = sections[-1]
        check = None
        edge_yl, edge_js = yl, js
        regular_x_index = None
        for _ in range(3):
            edge_x = x0-SOFFIT_RESERVE_M-section.width_mm/2000.
            if registered:
                # A near-coincident existing World XY axis owns the pier. Its
                # complete tributary load is then sized below; no second post is
                # emitted through it merely to give the floor edge another ID.
                regular_x = lattice.x_lines[bay]
                regular_x_index = (bay if abs(edge_x-regular_x) < section.width_mm/1000.
                    and regular_x+section.width_mm/2000. <= x0-SOFFIT_RESERVE_M else None)
                if regular_x_index is not None:
                    edge_x = regular_x
                edge_yl = retained_edge_stations(lattice,edge_x,yl[js[0]],yl[js[-1]],
                    level.index,max(section.width_mm,section.depth_mm)/1000.)
                edge_js = sorted(edge_yl,key=edge_yl.get)
                if len(edge_js)<2:
                    report.findings.append('No continuous volume-contained retained-floor edge support run.')
                    return report
            edge_west = (lattice.x_lines[bay]+edge_x)/2.
            edge_east = x0
            if regular_x_index is not None:
                edge_west,edge_east = _tributary(lattice.x_lines,regular_x_index)
            # Envelope every real y-station independently; a southmost strip may
            # carry less area than a central one on a tapering/rotating plate.
            station_loads = []
            for j in edge_js:
                ya,yb = _station_tributary(edge_yl,j)
                station_loads.append(tributary_load(lattice,box(edge_west,ya,edge_east,yb),
                                                   base.index,occupancy.live_kpa,context))
            force = [max(values[i] for values in station_loads) for i in range(3)]
            unbraced = max(c-a for j in edge_js for a,c in
                           _restraint_intervals(lattice,Point(edge_x,edge_yl[j]),level))
            check = _pier_choice('STR-TRF-EDGE',force,unbraced,sections,
                                 self_weight_height_m=level.z-lattice.levels[0].z)
            if check is None:
                break
            next_section = next(s for s in sections if s.id==check.section_id)
            if next_section.id == section.id:
                break
            section = next_section
        if check is not None:
            force[0] += section.self_weight_kn_m*(level.z-lattice.levels[0].z)
        report.edges.append(TransferEdge(x=edge_x,x_bay_index=bay,y_indices=edge_js,
            y_coordinates=dict(edge_yl) if registered else {},regular_x_index=regular_x_index,
            level_index=level.index,
            check=check,dead_kn=force[0],live_kn=force[1],roof_live_kn=force[2]))
        if check is None:
            report.findings.append('No catalogue section supports the west retained-floor edge.')
        elif registered:
            for j in edge_js:
                for lower,upper in zip(lattice.levels[:level.index],lattice.levels[1:level.index+1]):
                    if not _pier_inside_volume(lattice,edge_x,edge_yl[j],lower,upper,check):
                        report.findings.append('Retained-floor edge pier leaves its Program Volume; separate boundary support required.')
                        break
    if hall is not None:
        # The outer roof-grid lines are supported directly, including where the
        # upper tower retreats. Their actual reactions must reach real piers.
        for xi in (hall.x_indices[0],hall.x_indices[-1]):
            for j in hall.y_indices:
                xa,xb = _station_tributary(xl,xi)
                ya,yb = _station_tributary(yl,j)
                p = Point(xl[xi],yl[j])
                if not Polygon([(v.x,v.y) for v in base.plate]).buffer(.002).covers(p):
                    report.findings.append('Hall boundary pier has no base plate registration.')
                    continue
                intervals = _restraint_intervals(lattice,p,level)
                for k in range(level.index):
                    lower,upper = lattice.levels[k:k+2]
                    values = tributary_load(lattice,box(xa,ya,xb,yb),k+1,occupancy.live_kpa,context)
                    roof_d,roof_lr = b.hall_reactions[xi,j]
                    force = [values[0]+roof_d,values[1],values[2]+roof_lr]
                    unbraced = next((c-a for a,c in intervals if a-1e-6<=lower.z<c-1e-6),upper.z-lower.z)
                    identifier = column_id(xi,j,k,lattice)
                    weight_height = level.z-lower.z
                    check = _pier_choice(identifier,force,unbraced,sections,self_weight_height_m=weight_height)
                    if check is not None:
                        section = next(s for s in sections if s.id==check.section_id)
                        force[0] += section.self_weight_kn_m*weight_height
                    else:
                        report.findings.append(f'No catalogue boundary pier carries {identifier} and its hall roof reaction.')
                    report.boundary_piers.append(TransferPier(id=identifier,x_index=xi,y_index=j,
                        level_index=k,dead_kn=force[0],live_kn=force[1],roof_live_kn=force[2],check=check))
                    if check is not None and not _pier_inside_volume(lattice,xl[xi],yl[j],lower,upper,check):
                        report.findings.append(f'Complete hall pier {identifier} leaves its Program Volume.')
    if len(report.frames)<2:
        report.findings.append('A single plane has no paired transverse restraint frame; replacement disabled.')
    if any(f.status=='failed' for f in report.frames):
        report.findings.append('At least one transfer frame or reaction pier fails catalogue/geometry checks; original support paths retained.')
    if not report.findings:
        report.status = 'review_required'
        for candidate in report.frames:
            candidate.activated = True
    return report


def column_id(xi,yj,k,lattice):
    return f'STR-{"PIL" if k==0 else "COL"}-X{xi:02d}-Y{yj:02d}-{lattice.levels[k].id}'


def post_id(candidate,yj):
    return f'{candidate.id}-POST-Y{yj:02d}'


def edge_column_id(edge,j,k,lattice):
    if (edge.regular_x_index is not None and j < len(lattice.y_lines)
            and abs(edge.y_coordinates[j]-lattice.y_lines[j]) < 1e-7):
        return column_id(edge.regular_x_index,j,k,lattice)
    return f'STR-TRF-EDGE-X{edge.x_bay_index:02d}-Y{j:02d}-{lattice.levels[k].id}'


def retained_edge_segments(a, c, holes):
    """A slab edge cannot survive across a portion of floor that was removed."""
    line = LineString([(a.x,a.y),(c.x,c.y)])
    if holes:
        line = line.difference(unary_union([Polygon([(p.x,p.y) for p in hole]) for hole in holes]))
    parts = [line] if line.geom_type=='LineString' else list(getattr(line,'geoms',()))
    return [(tuple(part.coords[0]),tuple(part.coords[-1])) for part in parts
            if part.geom_type=='LineString' and part.length>.01]


def emit_transfer(b,report,beam_material):
    """Emit only an activated plan; every support reference names actual geometry."""
    if report.status != 'review_required':
        return
    lattice = b.lattice
    xl, yl = hall_axes(b)
    if getattr(lattice, 'hall_support_grid', None) is not None:
        piers = [p for f in report.frames for p in f.piers] + report.boundary_piers
        for pier in sorted(piers, key=lambda p:(p.level_index,p.x_index,p.y_index)):
            if pier.id in b.element_ids:
                continue
            x,y,k = xl[pier.x_index],yl[pier.y_index],pier.level_index
            lower,upper = lattice.levels[k:k+2]
            footing = f'STR-HALL-FDN-X{pier.x_index:02d}-Y{pier.y_index:02d}'
            index = {'hall_x':pier.x_index,'hall_y':pier.y_index,'level':k}
            if k == 0:
                b.add(footing,'footing','structure','foundations',
                    BoxGeometry(center=v3(x,y,lower.z-.45),size=v3(1.6,1.6,.9)),
                    'concrete',level_id=lower.id,lattice_index=index,
                    datum_refs=['bay_x_m','bay_y_m'],rule_refs=['STR-HALL-STATION-001'],
                    reason='Foundation at the registered hall boundary station; pad capacity and soil remain unverified.')
            b.add(pier.id,'piloti_column' if k==0 else 'column','structure','columns',
                b.member([v3(x,y,lower.z),v3(x,y,upper.z)],b.profile(profile_for(pier.check.section_id))),
                beam_material,level_id=lower.id,lattice_index=index,
                datum_refs=['floor_to_floor_m'],supports=[footing if k==0 else column_id(pier.x_index,pier.y_index,k-1,lattice)],
                section_id=pier.check.section_id,sizing_status='sized_by_calculation',
                utilisation=pier.check.max_ratio,governing_check=pier.check.governing,
                rule_refs=['STR-HALL-STATION-001'],
                reason='Registered volume-boundary pier with actual transfer/roof reaction and whole-profile containment; connection and foundation capacity require review.')
    for candidate in report.frames:
        # The report names the supported cap datum. Its framing occupies the
        # storey below that datum, which may have a different Program Volume.
        storey = lattice.levels[candidate.level_index - 1]
        js = candidate.y_indices
        n = len(js)
        end_supports = [column_id(candidate.x_index,j,candidate.level_index-1,lattice)
                        for j in (js[0],js[-1])]
        support_map = {}
        pending = list(candidate.members)
        while pending:
            progressed = []
            for member in pending:
                endpoints = {member.node_a,member.node_b}
                supports = [end_supports[i] for i,node in enumerate((0,n-1)) if node in endpoints]
                if not supports:
                    supports = [other.id for other in candidate.members
                                if other.id in support_map and {other.node_a,other.node_b}&endpoints][:1]
                if supports:
                    support_map[member.id] = supports
                    progressed.append(member)
            if not progressed:
                raise ValueError('activated transfer has no connected path to its piers')
            pending = [m for m in pending if m not in progressed]
        for member in candidate.members:
            a,c = candidate.nodes[member.node_a],candidate.nodes[member.node_b]
            supports = support_map[member.id]
            b.add(member.id,'transfer_'+member.role,'structure','transfer_frame',
                b.member([v3(candidate.x,*a),v3(candidate.x,*c)],b.profile(profile_for(member.section_id))),
                beam_material,level_id=storey.id,
                lattice_index={'x':candidate.x_index,'level':storey.index,'transfer':1},
                datum_refs=['bay_y_m','floor_to_floor_m','slab_thickness_m'],supports=supports,
                section_id=member.section_id,sizing_status='sized_by_calculation',
                utilisation=member.utilisation,governing_check='plane truss axial envelope',
                rule_refs=['STR-TRANSFER-GRAVITY-001'],
                reason='Calculated plane-truss gravity axial force and catalogue section. '
                       'Panel-node restraints are drawn; lateral brace capacity, connections and foundation design require review.')
        for j in js[1:-1]:
            node = js.index(j)
            support = next(m.id for m in candidate.members if m.role=='top_chord' and node in (m.node_a,m.node_b))
            pier_check = candidate.piers[0].check
            b.add(post_id(candidate,j),'transfer_post','structure','columns',
                b.member([v3(candidate.x,yl[j],min(candidate.top_z,getattr(b,'hall_primary_z',candidate.top_z))),
                          v3(candidate.x,yl[j],lattice.levels[candidate.level_index].z)],
                         b.profile(profile_for(pier_check.section_id))),beam_material,
                level_id=storey.id,lattice_index={'x':candidate.x_index,'y':j,'level':storey.index},
                datum_refs=['slab_thickness_m','floor_to_floor_m'],supports=[support],
                section_id=pier_check.section_id,sizing_status='architectural_convention',
                rule_refs=['STR-TRANSFER-GRAVITY-001'],
                reason='Short bearing/hanger post physically connects the transfer top-chord node, hall girders and upper column; local bearing, tension connection and joint design remain unevaluated.')
    # Perimeter posts and edge beams support the retained west floor strips.
    for edge in report.edges:
        profile = b.profile(profile_for(edge.check.section_id))
        for j in edge.y_indices:
            y = (edge.y_coordinates or yl)[j]
            if edge_column_id(edge,j,0,lattice) in b.element_ids:
                # The regular emitter owns this complete, reaction-sized stack.
                continue
            footing = f'STR-TRF-EDGE-FDN-X{edge.x_bay_index:02d}-Y{j:02d}'
            b.add(footing,'footing','structure','foundations',
                BoxGeometry(center=v3(edge.x,y,lattice.levels[0].z-.45),size=v3(1.6,1.6,.9)),
                'concrete',level_id=lattice.levels[0].id,
                lattice_index={'x':edge.x_bay_index,'y':j,'transfer_edge':1},
                datum_refs=['bay_x_m','bay_y_m'],rule_refs=['STR-TRANSFER-EDGE-001'],
                reason='Foundation under the derived theatre perimeter column; capacity, soil bearing and reinforcement are unevaluated.')
            for k in range(edge.level_index):
                lower,upper = lattice.levels[k:k+2]
                b.add(edge_column_id(edge,j,k,lattice),'column','structure','columns',
                    b.member([v3(edge.x,y,lower.z),v3(edge.x,y,upper.z)],profile),beam_material,
                    level_id=lower.id,lattice_index={'x':edge.x_bay_index,'y':j,'level':k,'transfer_edge':1},
                    datum_refs=['bay_x_m','floor_to_floor_m'],
                    supports=[footing if k==0 else edge_column_id(edge,j,k-1,lattice)],
                    section_id=edge.check.section_id,sizing_status='sized_by_calculation',
                    utilisation=edge.check.max_ratio,governing_check=edge.check.governing,
                    rule_refs=['STR-TRANSFER-EDGE-001'],reason='Catalogue column carries the retained floor strip; its centre is derived from the west carve face minus actual section half-width and a 50 mm geometric allowance.')
    # Required physical transverse restraint topology. No lateral sizing claim.
    brace_section = catalogue('steel_hss_square')[-1]
    brace_profile = b.profile(profile_for(brace_section.id))
    for left,right in zip(report.frames,report.frames[1:]):
        storey = lattice.levels[left.level_index - 1]
        for plane in ('top','bottom'):
            offset = 0 if plane=='top' else len(left.y_indices)
            for i in range(len(left.y_indices)):
                a = left.nodes[offset+i]; c = right.nodes[offset+i]
                pairs = [(a,c,i,i,'TIE')]
                if i+1 < len(left.y_indices):
                    pairs += [(a,right.nodes[offset+i+1],i,i+1,'XA'),
                              (left.nodes[offset+i+1],c,i+1,i,'XB')]
                for a,c,ia,ic,tag in pairs:
                    supports = [next(m.id for m in frame.members if offset+node in (m.node_a,m.node_b))
                                for frame,node in ((left,ia),(right,ic))]
                    b.add(f'{left.id}-BR-{right.x_index}-{plane}-{i}-{tag}',
                        'transfer_restraint','structure','transfer_restraints',
                        b.member([v3(left.x,*a),v3(right.x,*c)],brace_profile),beam_material,
                        level_id=storey.id,lattice_index={'x':left.x_index,'level':storey.index,'transfer':1},
                        datum_refs=['bay_x_m','bay_y_m','floor_to_floor_m'],supports=supports,
                        section_id=brace_section.id,sizing_status='architectural_convention',
                        rule_refs=['STR-TRANSFER-RESTRAINT-001'],
                        reason='Required physical transverse tie/cross at chord panel nodes. Lateral restraint forces, stiffness and anchorage remain unevaluated; this bar has no calculated utilisation.')
