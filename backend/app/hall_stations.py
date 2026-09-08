"""Hall supports derived from the volume, independent of the World XY pitch.

Regular station keys retain their world-grid index. Boundary keys follow the end
of that axis array and resolve only through this registry, never through x/y_lines.
The registered inset reserves the largest admitted pier profile, not a new grid.
"""
from pydantic import BaseModel, Field
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union


class HallSupportGrid(BaseModel):
    x: dict[int, float]
    y: dict[int, float]
    source_volume_ids: list[str]
    pier_envelope_m: float = Field(gt=0)
    basis: str = 'Program Volume hall perimeter inset by half the admitted catalogue pier envelope; interior World XY stations remain unchanged.'

    def indices(self, axis):
        values = getattr(self, axis)
        return sorted(values, key=values.get)


def volume_section(lattice, z):
    return unary_union([box(*r.resolve_bounds(lattice))
                        for r in lattice.program_volume_regions
                        if r.z_base-1e-7 <= z <= r.z_top+1e-7])


def register_hall_grid(lattice, footprint, pier_envelope_m):
    regions = getattr(lattice, 'program_volume_regions', ())
    if not regions:
        return None
    bounds = footprint.bounds
    axes = {}
    for axis, low, high in (('x', bounds[0], bounds[2]), ('y', bounds[1], bounds[3])):
        lines = getattr(lattice, axis+'_lines')
        a, c = low+ pier_envelope_m/2, high-pier_envelope_m/2
        if c <= a:
            raise ValueError('Hall cannot contain its admitted pier envelope')
        values = {i: v for i, v in enumerate(lines) if a+1e-7 < v < c-1e-7}
        values[len(lines)], values[len(lines)+1] = a, c
        axes[axis] = values
    return HallSupportGrid(**axes, pier_envelope_m=pier_envelope_m,
        source_volume_ids=[r.id for r in regions if r.role in {'archetype', 'sectional_clearance'}
                           and box(*r.resolve_bounds(lattice)).intersection(footprint).area > 1e-6])


def hall_axes(b):
    grid = getattr(b.lattice, 'hall_support_grid', None)
    return ((grid.x, grid.y) if grid is not None
            else (b.lattice.x_lines, b.lattice.y_lines))


def retained_edge_stations(lattice, x, y0, y1, top_index, breadth):
    """One continuous perimeter support run through the actual stacked volumes.

    A shorter upper plate relocates the edge's end pier, independently of the
    hall roof grid. Disconnected runs stay unresolved instead of spanning a gap.
    """
    common = Polygon([(p.x,p.y) for p in lattice.occupied[0].plate])
    for a,c in zip(lattice.levels[1:top_index],lattice.levels[2:top_index+1]):
        common = common.intersection(volume_section(lattice,(a.z+c.z)/2))
    segment = common.buffer(-breadth/2,join_style=2).intersection(
        LineString([(x,y0),(x,y1)]))
    if segment.is_empty or segment.geom_type != 'LineString' or segment.length < breadth:
        return {}
    low,high = segment.bounds[1],segment.bounds[3]
    lines = lattice.y_lines
    values = {i:v for i,v in enumerate(lines) if low+1e-7 < v < high-1e-7}
    values[len(lines)],values[len(lines)+1] = low,high
    return values
