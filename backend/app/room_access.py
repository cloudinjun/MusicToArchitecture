"""Shared owner-face and theatre-front geometry for room access."""


def owner_terminal_points(bounds, radius, *, front_x=None, boundary_clearance_m=1e-5):
    """Return south, north, west, east terminals outside the exact owner bounds."""
    x0, y0, x1, y1 = bounds
    x, y = (x0+x1)/2, (y0+y1)/2
    if front_x is not None and x0 <= front_x <= x1:
        x = front_x
    return [(x, y0-radius-boundary_clearance_m),
            (x, y1+radius+boundary_clearance_m),
            (x0-radius-boundary_clearance_m, y),
            (x1+radius+boundary_clearance_m, y)]


def front_cross_aisle_bounds(first_row_x, audience_direction, aisle_width):
    """The front cross aisle ends at the first seating row in either direction."""
    front_start = first_row_x-audience_direction*aisle_width
    return min(first_row_x, front_start), max(first_row_x, front_start)
