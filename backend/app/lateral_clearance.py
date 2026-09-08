"""Keep lateral frame bays outside registered architectural clear volumes.

The frame still owns its member selection and capacity. This placement gate reads
the same carved-room and void geometry used by floors and circulation; it never
replaces a refused diagonal with an unanalysed moment connection.
"""
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union


def lateral_bay_clear(lattice, lower_index, x0, x1, y, member_radius):
    level = lattice.levels[lower_index]
    keep_out = [Polygon([(p.x, p.y) for p in ring]) for ring in level.voids]
    keep_out.extend(box(*rect) for rect in lattice.carved.get(lower_index, ()))
    if not keep_out:
        return True
    if any(not region.is_valid for region in keep_out):
        return False
    footprint = LineString([(x0, y), (x1, y)]).buffer(member_radius, cap_style='flat')
    return footprint.intersection(unary_union(keep_out)).area <= 1e-7
