"""Independent spatial checks for generated cores, stairs, and plan regions."""

import json
import math
import re
from pathlib import Path

import pytest
from shapely.affinity import rotate
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from backend.app.compiler_v3 import (
    _Builder,
    _core_layout,
    _emit_circulation,
    compile_building_model_v3,
    core_anchors,
    core_reservations,
)
from backend.app.datums import LevelDatum, Lattice, PlanBounds
from backend.app.geometry import BoxGeometry, ExtrusionGeometry, v2
from backend.app.massing import MASSING_FAMILIES
from backend.app.models import ArchitecturalScore, AudioFeatures
from backend.app.plan_regions import extrusions


ROOT = Path(__file__).parents[2]
FEATURES_PATH = (
    ROOT / "artifacts" / "integrated_demo"
    / "building-b7ad95fa45a6-library-steel-international-v1"
    / "music_features.json"
)
SCORE_PATH = ROOT / "artifacts" / "v3_demo" / "architectural_score.json"
PINNED_TYPOLOGY = "library"
PINNED_GRAMMAR = "FCD-01-INTERNATIONAL-STYLE"
REPRESENTATIVE_MASSINGS = ("MAS-SLAB", "MAS-BAR-PODIUM", "MAS-TOWER")
CORE_FLIGHT_RE = re.compile(r"^CIR-TRD-([A-Z]\d{2})-S\d+$")
EXTERNAL_FLIGHTS = {"F01", "R01"}
EPS = 1e-8


@pytest.fixture(scope="module")
def features() -> AudioFeatures:
    return AudioFeatures.model_validate(
        json.loads(FEATURES_PATH.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def score() -> ArchitecturalScore:
    return ArchitecturalScore.model_validate(
        json.loads(SCORE_PATH.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def models(features: AudioFeatures, score: ArchitecturalScore):
    return {
        massing_id: compile_building_model_v3(
            features, score,
            massing_id=massing_id,
            typology=PINNED_TYPOLOGY,
            grammar_id=PINNED_GRAMMAR,
            cutaway=False,
        )
        for massing_id in REPRESENTATIVE_MASSINGS
    }


def _xy_shape(geometry):
    if isinstance(geometry, BoxGeometry):
        center, size = geometry.center, geometry.size
        footprint = box(
            center.x - size.x / 2.0,
            center.y - size.y / 2.0,
            center.x + size.x / 2.0,
            center.y + size.y / 2.0,
        )
        return rotate(
            footprint,
            math.degrees(geometry.rotation_z),
            origin=(center.x, center.y),
        )
    if isinstance(geometry, ExtrusionGeometry):
        boundary = [(point.x, point.y) for point in geometry.boundary]
        holes = [[(point.x, point.y) for point in ring]
                 for ring in geometry.holes]
        return Polygon(boundary, holes)
    raise AssertionError(f"expected a solid geometry, got {type(geometry).__name__}")


def _z_interval(geometry) -> tuple[float, float]:
    if isinstance(geometry, BoxGeometry):
        centre = geometry.center.z
        half_height = geometry.size.z / 2.0
        return centre - half_height, centre + half_height
    if isinstance(geometry, ExtrusionGeometry):
        return geometry.z_base, geometry.z_top
    raise AssertionError(f"expected a solid geometry, got {type(geometry).__name__}")


def _solids_overlap(first, second) -> bool:
    first_bottom, first_top = _z_interval(first.geometry)
    second_bottom, second_top = _z_interval(second.geometry)
    if min(first_top, second_top) - max(first_bottom, second_bottom) <= EPS:
        return False
    return _xy_shape(first.geometry).intersection(_xy_shape(second.geometry)).area > EPS


def _core_treads(model):
    return [
        element for element in model.elements
        if element.kind == "stair_tread"
        and (match := CORE_FLIGHT_RE.match(element.id))
        and match.group(1) not in EXTERNAL_FLIGHTS
    ]


def test_core_treads_clear_floor_slabs_and_ceilings(models):
    """A tread can pass through a host only if the plan opening missed it."""
    for massing_id, model in models.items():
        hosts = [element for element in model.elements
                 if element.kind in {"floor_slab", "ceiling"}]
        collisions = [
            (tread.id, host.id)
            for tread in _core_treads(model)
            for host in hosts
            if _solids_overlap(tread, host)
        ]
        assert not collisions, (massing_id, collisions[:8])


def test_core_treads_clear_lift_walls(models):
    for massing_id, model in models.items():
        treads = _core_treads(model)
        shafts = [element for element in model.elements
                  if element.kind == "elevator_shaft"]
        collisions = [
            (tread.id, shaft.id)
            for tread in treads
            for shaft in shafts
            if _solids_overlap(tread, shaft)
        ]
        assert not collisions, (massing_id, collisions[:8])


def test_core_reservation_regions_are_pairwise_disjoint(models):
    for massing_id, model in models.items():
        rectangles = core_reservations(model.lattice, model.datum_set)
        regions = [box(*rectangle) for rectangle in rectangles]
        collisions = [
            (first, second)
            for first in range(len(regions))
            for second in range(first + 1, len(regions))
            if regions[first].intersection(regions[second]).area > EPS
        ]
        assert not collisions, (massing_id, rectangles, collisions)


def test_emitted_core_flights_and_landings_match_actual_service_coverage(models):
    """Check the stairs that exist, while retaining any honest coverage gap."""
    for massing_id, model in models.items():
        anchors = core_anchors(model.lattice, model.datum_set)
        layout = _core_layout(anchors)
        expected_flights = {
            f"{tag}{index:02d}"
            for _point, served, tags, _label, _facing in layout
            for index in range(max(0, len(served) - 1))
            for tag in tags
        }
        actual_flights = {
            match.group(1)
            for tread in model.elements
            if tread.kind == "stair_tread"
            if (match := CORE_FLIGHT_RE.match(tread.id))
            if match.group(1) not in EXTERNAL_FLIGHTS
        }
        assert actual_flights == expected_flights, (
            massing_id, sorted(expected_flights), sorted(actual_flights))

        served_occupied = {
            level.id
            for _point, served, _tags, _label, _facing in layout
            for level in served
            if level.kind == "occupied"
        }
        unreached = {level.id for level in model.lattice.occupied} - served_occupied
        notes = " ".join(model.limitations)
        if unreached:
            assert "no single stair core" in notes, (massing_id, unreached)
            assert unreached <= set(re.findall(r"L\d{2}", notes)), (
                massing_id, unreached, notes)
        else:
            assert "no single stair core" not in notes


def test_floor_landings_overlap_real_plate_and_are_flush(models):
    for massing_id, model in models.items():
        by_level = {level.id: level for level in model.lattice.levels}
        slabs_by_level = {}
        for element in model.elements:
            if element.kind == "floor_slab":
                slabs_by_level.setdefault(element.level_id, []).append(
                    _xy_shape(element.geometry))
        landings = [element for element in model.elements
                    if element.kind == "stair_landing"]
        assert landings, massing_id
        failures = []
        for landing in landings:
            level = by_level[landing.level_id]
            top = landing.position.z + landing.dimensions.z / 2.0
            footprint = _xy_shape(landing.geometry)
            plate = Polygon([(point.x, point.y) for point in level.plate])
            slab = unary_union(slabs_by_level.get(landing.level_id, ()))
            if abs(top - level.z) > 1e-6:
                failures.append((landing.id, "not_flush", top, level.z))
            if footprint.intersection(plate).area <= EPS:
                failures.append((landing.id, "outside_plate"))
            # The slab gives the landing its footprint (one surface owns each square
            # metre), so contact is the shared edge: the landing's footprint, grown
            # by a hand's width, must reach slab along a real length of boundary.
            if slab.is_empty:
                failures.append((landing.id, "no_slab_contact"))
            else:
                shared = footprint.buffer(0.05).intersection(slab).area
                if footprint.intersection(slab).area <= EPS and shared <= 0.05:
                    failures.append((landing.id, "no_slab_contact", shared))
        assert not failures, (massing_id, failures[:8])


def _tiny_lattice() -> Lattice:
    plan = PlanBounds(x_min=-2.0, x_max=2.0, y_min=-2.0, y_max=2.0)
    plate = [v2(-2.0, -2.0), v2(2.0, -2.0), v2(2.0, 2.0), v2(-2.0, 2.0)]
    levels = [
        LevelDatum(index=0, id="L00", z=0.0, kind="podium", plate=plate, voids=[]),
        LevelDatum(index=1, id="L01", z=4.0, kind="occupied", plate=plate, voids=[]),
        LevelDatum(index=2, id="L02", z=8.0, kind="roof", plate=plate, voids=[]),
    ]
    return Lattice(
        levels=levels,
        x_lines=[-2.0, 0.0, 2.0],
        y_lines=[-2.0, 0.0, 2.0],
        apse_nodes=[],
        plan=plan,
        massing_id="MAS-TOWER",
        cutaway=False,
        plan_x_m=4.0,
        plan_y_m=4.0,
    )


def test_tiny_plan_has_no_centroid_stair_and_records_unreached_levels(score):
    from backend.app.datums import compile_datum_set

    datums = compile_datum_set(score)
    lattice = _tiny_lattice()
    builder = _Builder(datums, lattice)
    assert builder.cores["primary"] is None

    _emit_circulation(builder)
    emitted_core_treads = [
        instance.id
        for group in builder.groups.values()
        for instance in group.instances
        if group.kind == "stair_tread"
        and (match := CORE_FLIGHT_RE.match(instance.id))
        and match.group(1) not in EXTERNAL_FLIGHTS
    ]
    assert not emitted_core_treads
    assert builder.unreached_levels == ["L01"]


def _ring(points):
    return [v2(x, y) for x, y in points]


def test_plan_regions_unions_overlapping_holes():
    boundary = _ring([(0, 0), (10, 0), (10, 10), (0, 10)])
    holes = [
        _ring([(2, 2), (6, 2), (6, 6), (2, 6)]),
        _ring([(4, 4), (8, 4), (8, 8), (4, 8)]),
    ]
    parts = extrusions(boundary, holes, 0.0, 0.3)
    result = unary_union([Polygon([(point.x, point.y) for point in part.boundary])
                          for part in parts])
    expected = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]).difference(
        unary_union([Polygon([(point.x, point.y) for point in hole])
                     for hole in holes]))
    assert all(not part.holes for part in parts)
    assert result.area == pytest.approx(expected.area)
    assert result.symmetric_difference(expected).area < 1e-8
    assert sum(Polygon([(p.x, p.y) for p in part.boundary]).area for part in parts) == pytest.approx(result.area)


def test_plan_regions_preserves_all_components_when_hole_crosses_boundary():
    boundary = _ring([(0, 0), (10, 0), (10, 4), (0, 4)])
    crossing_hole = _ring([(4, -2), (6, -2), (6, 6), (4, 6)])
    parts = extrusions(boundary, [crossing_hole], 1.0, 2.0)
    regions = [
        Polygon([(point.x, point.y) for point in part.boundary],
                [[(point.x, point.y) for point in ring] for ring in part.holes])
        for part in parts
    ]
    assert len(parts) == 2
    assert sorted(round(region.area, 6) for region in regions) == [16.0, 16.0]
    assert sorted(round(region.bounds[0], 6) for region in regions) == [0.0, 6.0]
    assert all(part.z_base == 1.0 and part.z_top == 2.0 for part in parts)


def test_plan_regions_rejects_invalid_ring():
    invalid_boundary = _ring([(0, 0), (4, 4), (0, 4), (4, 0)])
    with pytest.raises(ValueError, match="Invalid plan ring"):
        extrusions(invalid_boundary, [], 0.0, 1.0)
