"""Geometric sanity checks for sampled west-apse floor plates."""

import json
from pathlib import Path

import pytest

from backend.app.datums import build_lattice, compile_datum_set
from backend.app.massing import MASSING_FAMILIES
from backend.app.models import ArchitecturalScore


ROOT = Path(__file__).parents[2]
SCORE_PATH = ROOT / "artifacts" / "v3_demo" / "architectural_score.json"
WEST_APSE_FAMILIES = ("MAS-SLAB", "MAS-ZIGGURAT", "MAS-PAVILION")
SCORE_LEVELS = (0.0, 0.5, 1.0)


@pytest.fixture(scope="module")
def score() -> ArchitecturalScore:
    return ArchitecturalScore.model_validate(
        json.loads(SCORE_PATH.read_text(encoding="utf-8")))


def _score_at(score: ArchitecturalScore, value: float) -> ArchitecturalScore:
    return score.model_copy(update={
        "dimensions": [
            dimension.model_copy(update={"value": value})
            for dimension in score.dimensions
        ]
    })


def _cross(a, b, c) -> float:
    return ((b.x - a.x) * (c.y - a.y)
            - (b.y - a.y) * (c.x - a.x))


def _on_segment(a, b, point, epsilon: float = 1e-7) -> bool:
    return (min(a.x, b.x) - epsilon <= point.x <= max(a.x, b.x) + epsilon
            and min(a.y, b.y) - epsilon <= point.y <= max(a.y, b.y) + epsilon)


def _segments_intersect(a, b, c, d, epsilon: float = 1e-7) -> bool:
    """Return true for crossings and collinear overlaps, including endpoints."""
    ab_c, ab_d = _cross(a, b, c), _cross(a, b, d)
    cd_a, cd_b = _cross(c, d, a), _cross(c, d, b)

    if (((ab_c > epsilon and ab_d < -epsilon)
         or (ab_c < -epsilon and ab_d > epsilon)) and
            ((cd_a > epsilon and cd_b < -epsilon)
             or (cd_a < -epsilon and cd_b > epsilon))):
        return True
    return ((abs(ab_c) <= epsilon and _on_segment(a, b, c, epsilon))
            or (abs(ab_d) <= epsilon and _on_segment(a, b, d, epsilon))
            or (abs(cd_a) <= epsilon and _on_segment(c, d, a, epsilon))
            or (abs(cd_b) <= epsilon and _on_segment(c, d, b, epsilon)))


def _non_adjacent_intersections(polygon):
    """List intersections between edges that should have no shared endpoint."""
    intersections = []
    edge_count = len(polygon)
    for first in range(edge_count):
        first_edge = (polygon[first], polygon[(first + 1) % edge_count])
        for second in range(first + 1, edge_count):
            # Consecutive edges meet by design, including the closing edge.
            if second == first + 1 or (first == 0 and second == edge_count - 1):
                continue
            second_edge = (polygon[second], polygon[(second + 1) % edge_count])
            if _segments_intersect(*first_edge, *second_edge):
                intersections.append((first, second))
    return intersections


def _absolute_area(polygon) -> float:
    return abs(sum(
        point.x * polygon[(index + 1) % len(polygon)].y
        - polygon[(index + 1) % len(polygon)].x * point.y
        for index, point in enumerate(polygon)
    )) / 2.0


@pytest.mark.parametrize("family_id", WEST_APSE_FAMILIES)
@pytest.mark.parametrize("score_level", SCORE_LEVELS)
def test_west_apse_plate_rings_are_simple_and_positive(
        score: ArchitecturalScore, family_id: str, score_level: float):
    lattice = build_lattice(
        compile_datum_set(_score_at(score, score_level)),
        MASSING_FAMILIES[family_id],
        cutaway=False,
    )

    assert len(lattice.levels) >= 3
    for level in lattice.levels:
        intersections = _non_adjacent_intersections(level.plate)
        assert not intersections, (family_id, score_level, level.index, intersections)
        assert _absolute_area(level.plate) > 0.0

        # The apse must still project west of the rectangular plan edge. This checks
        # the intended rounded end without depending on its sampling formula.
        outward = [point for point in level.plate
                   if point.x < lattice.plan.x_min - 1e-3]
        assert len(outward) >= 3, (family_id, score_level, level.index)


def test_west_apse_score_levels_produce_different_stack_heights(
        score: ArchitecturalScore):
    heights = {
        len(build_lattice(
            compile_datum_set(_score_at(score, score_level)),
            MASSING_FAMILIES["MAS-SLAB"],
            cutaway=False,
        ).levels)
        for score_level in SCORE_LEVELS
    }
    assert len(heights) >= 2
