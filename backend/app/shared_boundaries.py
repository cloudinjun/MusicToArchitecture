"""Split room edges where explicitly shared public routes cross them."""

from .program_volume_contracts import PLAN_IDENTITY_TOLERANCE_M


def split_shared_route_boundary(lattice, level_id, space_id, coords):
    """Partition an axis-aligned edge, retaining its direction and full extent.

    Only an opted-in circulation program owner can share an edge. A named route
    must extend onto both sides of that edge; a tangent carrier opens nothing.
    This function changes no geometry and makes no fire/acoustic boundary decision.
    """
    coords = tuple(coords)
    x0, y0, x1, y1 = coords
    epsilon = PLAN_IDENTITY_TOLERANCE_M
    horizontal = abs(y1-y0) <= epsilon
    vertical = abs(x1-x0) <= epsilon
    if horizontal == vertical:
        raise ValueError('Shared route boundary must be a nonempty axis-aligned edge')
    regions = getattr(lattice, 'program_volume_regions', ())
    owners = [region for region in regions
              if region.level_id == level_id and region.role == 'program'
              and region.category == 'circulation' and space_id in region.space_ids
              and region.shared_route_volume_ids]
    registry = {region.id: region for region in regions}
    start, end = (x0, x1) if horizontal else (y0, y1)
    low, high = min(start, end), max(start, end)
    boundary = y0 if horizontal else x0
    intervals = []
    for owner in owners:
        for identifier in owner.shared_route_volume_ids:
            route = registry.get(identifier)
            if (route is None or route.level_id != level_id
                    or route.role not in ('circulation_spine', 'connector')):
                continue
            rx0, ry0, rx1, ry1 = route.resolve_bounds(lattice)
            across0, across1 = (ry0, ry1) if horizontal else (rx0, rx1)
            if not across0 < boundary-epsilon or not across1 > boundary+epsilon:
                continue
            along0, along1 = (rx0, rx1) if horizontal else (ry0, ry1)
            a, b = max(low, along0), min(high, along1)
            if b-a > epsilon:
                intervals.append((a, b))
    if not intervals:
        return [(coords, False)]

    merged = []
    for a, b in sorted(intervals):
        if merged and a <= merged[-1][1]+epsilon:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    pieces, cursor = [], low
    for a, b in merged:
        if cursor < a:
            pieces.append((cursor, a, False))
        pieces.append((a, b, True))
        cursor = b
    if cursor < high:
        pieces.append((cursor, high, False))
    if end < start:
        pieces = [(b, a, shared) for a, b, shared in reversed(pieces)]

    def point(value):
        # Retain original endpoints even with floating registration arithmetic.
        t = (value-start)/(end-start)
        return x0+(x1-x0)*t, y0+(y1-y0)*t

    return [((*point(a), *point(b)), shared) for a, b, shared in pieces]
