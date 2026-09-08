"""The normalized generated-site and program contract.

The brief provider is deliberately kept upstream of the massing compiler.  A random
provider, an agent model, a local model, or a real project brief can all produce raw
data, but the rest of the pipeline receives one small, typed record.  In particular,
the program contains requirements and areas, never rectangles or room coordinates.

The site area limit in this module is a *measured polygon* limit.  A bounding box is
reported for comparison only; it is never used to decide whether a site is allowed.
The gross-area check is likewise only a necessary capacity check.  It does not claim
that an allocator has placed the rooms or that a building is code compliant.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any, Literal, Mapping, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator
from shapely.geometry import Polygon

from .program import SpaceRequirement


MAX_SITE_AREA_M2 = 500.0
MAX_OCCUPIED_STOREYS = 12
AREA_EPSILON_M2 = 1e-6
MIN_ACCEPTED_AREA_TOLERANCE = 0.9

ProjectTypology = Literal['library', 'theater', 'museum']
ProviderType = Literal[
    'random', 'agent_llm', 'local_llm', 'openai', 'external', 'manual',
]


class SiteBoundary(BaseModel):
    """A simple, valid, metre-based site polygon.

    ``polygon`` is a closed sequence of ``(x, y)`` points in world XY.  The
    corresponding Shapely object is exposed through ``shape`` for geometry code, while
    the serialised contract stays independent of Shapely.
    """

    model_config = ConfigDict(extra='forbid')

    polygon: tuple[tuple[float, float], ...] = Field(min_length=4)
    units: Literal['m'] = 'm'

    @model_validator(mode='before')
    @classmethod
    def _coerce_and_measure(cls, values: Any) -> Any:
        if isinstance(values, Polygon):
            if values.interiors:
                raise ValueError('site polygon must not contain holes')
            values = {'polygon': list(values.exterior.coords)}
        elif isinstance(values, Mapping):
            # Accept the common GeoJSON-like spelling at the provider boundary while
            # keeping the normalized field name singular and explicit.
            values = dict(values)
            if 'polygon' not in values and 'coordinates' in values:
                values['polygon'] = values.pop('coordinates')
            coordinates = values.get('polygon')
            if isinstance(coordinates, Mapping):
                coordinates = coordinates.get('coordinates')
                values['polygon'] = coordinates
        if not isinstance(values, Mapping):
            raise TypeError('site must be a mapping or a Shapely Polygon')

        raw_points = values.get('polygon')
        if raw_points is None:
            raise ValueError('site polygon is required')
        points: list[tuple[float, float]] = []
        try:
            for point in raw_points:
                if len(point) != 2:
                    raise ValueError('each site point must contain x and y')
                x, y = float(point[0]), float(point[1])
                if not (math.isfinite(x) and math.isfinite(y)):
                    raise ValueError('site coordinates must be finite')
                points.append((x, y))
        except TypeError as exc:
            raise ValueError('site polygon must be a sequence of x/y points') from exc
        if len(points) >= 2 and points[0] != points[-1]:
            points.append(points[0])
        values = dict(values)
        values['polygon'] = tuple(points)
        return values

    @model_validator(mode='after')
    def _valid_simple_polygon(self) -> 'SiteBoundary':
        poly = Polygon(self.polygon)
        if poly.is_empty or poly.geom_type != 'Polygon':
            raise ValueError('site polygon must resolve to one polygon')
        if not poly.is_valid or not poly.boundary.is_simple:
            raise ValueError('site polygon must be valid and simple')
        if poly.area <= AREA_EPSILON_M2:
            raise ValueError('site polygon must have positive area')
        if poly.area > MAX_SITE_AREA_M2 + AREA_EPSILON_M2:
            raise ValueError(
                f'site polygon area {poly.area:.3f} m2 exceeds the hard limit of '
                f'{MAX_SITE_AREA_M2:.3f} m2')
        return self

    @property
    def shape(self) -> Polygon:
        """Return a fresh Shapely polygon for geometry consumers."""
        return Polygon(self.polygon)

    @property
    def area_m2(self) -> float:
        """Measured polygon area in square metres."""
        return float(self.shape.area)

    @property
    def bbox_area_m2(self) -> float:
        """Bounding-box area, reported for diagnostics and never for admission."""
        min_x, min_y, max_x, max_y = self.shape.bounds
        return float((max_x - min_x) * (max_y - min_y))


class SiteSetbacks(BaseModel):
    """A project-proposed envelope reserve, not a jurisdictional code rule.

    ``setback_m`` is applied inward to the site first.  ``facade_projection_m`` is
    then applied inward to the resulting buildable shape to reserve room for an
    offset/projecting facade system.  The source, reason, and review state travel with
    the numbers so a later site or architect can replace them without pretending they
    came from a code lookup.
    """

    model_config = ConfigDict(extra='forbid')

    setback_m: float = Field(ge=0.0)
    facade_projection_m: float = Field(ge=0.0)
    provenance: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    needs_review: bool

    @model_validator(mode='after')
    def _finite_distances(self) -> 'SiteSetbacks':
        if not (math.isfinite(self.setback_m) and
                math.isfinite(self.facade_projection_m)):
            raise ValueError('site setback distances must be finite')
        return self


class BriefProvenance(BaseModel):
    """How the normalized brief was proposed and normalized."""

    model_config = ConfigDict(extra='forbid')

    provider_type: ProviderType
    model: str | None = None
    seed: str | int | None = None
    prompt_template_version: str | None = None
    raw_response_hash: str | None = None
    source_ref: str | None = None
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat())
    normalizer_version: str = 'project-brief.v1'


class BriefValidationReport(BaseModel):
    """Auditable accounting for a validated brief.

    ``placement_status`` is intentionally fixed to ``not_evaluated`` here.  Site-area
    and gross-area accounting are useful preflight gates, but they cannot stand in for
    Program Volume placement, circulation, structural, or code checks.
    """

    model_config = ConfigDict(extra='forbid')

    valid: bool = True
    site_area_m2: float
    site_bbox_area_m2: float
    buildable_area_m2: float
    massing_limit_area_m2: float
    buildable_geometry_type: Literal['Polygon', 'MultiPolygon']
    massing_limit_geometry_type: Literal['Polygon', 'MultiPolygon']
    buildable_boundary: tuple[tuple[tuple[float, float], ...], ...]
    massing_limit_boundary: tuple[tuple[tuple[float, float], ...], ...]
    target_gross_area_m2: float
    net_program_area_m2: float
    circulation_area_m2: float
    gross_program_area_m2: float
    capacity_m2: float
    support_space_ids: tuple[str, ...]
    placement_status: Literal['not_evaluated'] = 'not_evaluated'
    warnings: tuple[str, ...] = (
        'Gross area versus site area times occupied storeys is a necessary capacity '
        'check only; Program Volume placement remains unevaluated.',
    )


def _inset_shape(shape, distance: float, label: str):
    """Inset a polygonal envelope while retaining every polygonal piece."""
    if distance <= AREA_EPSILON_M2:
        result = shape
    else:
        result = shape.buffer(-distance, join_style=2)
    if result.is_empty:
        raise ValueError(f'{label} leaves an empty site envelope')
    if result.geom_type not in {'Polygon', 'MultiPolygon'}:
        raise ValueError(
            f'{label} leaves an invalid {result.geom_type} site envelope')
    if not result.is_valid or result.area <= AREA_EPSILON_M2:
        raise ValueError(f'{label} leaves an invalid or zero-area site envelope')
    return result


def _boundary_coordinates(shape) -> tuple[tuple[tuple[float, float], ...], ...]:
    """Serialize all exterior rings without collapsing a MultiPolygon to its bbox."""
    geometries = ([shape] if shape.geom_type == 'Polygon'
                  else sorted(shape.geoms,
                              key=lambda item: (item.bounds[0], item.bounds[1],
                                                -item.area)))
    return tuple(tuple((float(x), float(y)) for x, y in geometry.exterior.coords)
                 for geometry in geometries)


class SupportSpaceSize(BaseModel):
    """A provisional upstream requirement, never an allocator fit adjustment."""
    model_config = ConfigDict(extra='forbid')
    area_m2: float = Field(gt=0)
    min_dimension_m: float = Field(gt=0)

    @model_validator(mode='after')
    def _possible_rectangle(self):
        if self.min_dimension_m**2 > self.area_m2 + AREA_EPSILON_M2:
            raise ValueError('support area cannot contain its declared minimum dimensions')
        return self


class SupportProgramSizing(BaseModel):
    """Project-scale premises replace only named automatic support placeholders."""
    model_config = ConfigDict(extra='forbid')
    source: ProviderType
    basis: str = Field(min_length=1)
    needs_review: Literal[True] = True
    sizes: dict[str, SupportSpaceSize] = Field(min_length=1)


class ProjectBrief(BaseModel):
    """Normalized input shared by site, program, and massing stages."""

    model_config = ConfigDict(extra='forbid')

    schema_version: Literal['project-brief.v1'] = 'project-brief.v1'
    brief_id: str
    typology: ProjectTypology
    site: SiteBoundary
    site_setbacks: SiteSetbacks | None = None
    occupied_storeys: int = Field(ge=1, le=MAX_OCCUPIED_STOREYS)
    target_gross_area_m2: float = Field(gt=0)
    spaces: tuple[SpaceRequirement, ...] = Field(min_length=1)
    support_sizing: SupportProgramSizing | None = None
    # Exactly one of these makes the circulation reserve visible and prevents callers
    # from adding a second hidden allowance downstream.
    circulation_fraction: float | None = Field(default=None, gt=0.0, lt=0.5)
    circulation_budget_m2: float | None = Field(default=None, gt=0.0)
    provenance: BriefProvenance
    assumptions: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode='before')
    @classmethod
    def _reject_room_coordinates(cls, values: Any) -> Any:
        """Reject geometry at the raw provider boundary instead of dropping it.

        ``SpaceRequirement`` intentionally has no coordinate fields.  Pydantic's
        default nested parsing would otherwise ignore an accidental ``x0`` or ``rect``
        in a raw LLM response, making the loss invisible.  The normalized contract
        rejects those fields before the nested model is built.
        """
        if not isinstance(values, Mapping):
            return values
        values = dict(values)
        raw_spaces = values.get('spaces')
        if isinstance(raw_spaces, (list, tuple)):
            forbidden = {
                'x', 'y', 'z', 'x0', 'y0', 'x1', 'y1', 'z_base', 'z_top',
                'rect', 'rectangle', 'geometry', 'coordinates', 'polygon',
            }
            for index, raw_space in enumerate(raw_spaces):
                if isinstance(raw_space, Mapping):
                    found = sorted(forbidden.intersection(raw_space))
                    if found:
                        raise ValueError(
                            f'spaces[{index}] contains geometry fields {found}; '
                            'requirements must remain coordinate-free')
        return values

    @model_validator(mode='after')
    def _validate_budget(self) -> 'ProjectBrief':
        if not self.brief_id.strip():
            raise ValueError('brief_id must not be empty')
        ids = [space.id for space in self.spaces]
        if any(not identifier.strip() for identifier in ids):
            raise ValueError('space ids must not be empty')
        if len(ids) != len(set(ids)):
            raise ValueError('space ids must be unique')
        if (self.circulation_fraction is None) == (self.circulation_budget_m2 is None):
            raise ValueError(
                'provide exactly one circulation_fraction or circulation_budget_m2')

        for space in self.spaces:
            if space.area_tolerance < MIN_ACCEPTED_AREA_TOLERANCE:
                raise ValueError(
                    f'{space.id} area_tolerance {space.area_tolerance:.3f} is below '
                    f'the new-brief minimum {MIN_ACCEPTED_AREA_TOLERANCE:.3f}; '
                    'the field is a delivered-area tolerance, not a budget fraction')

        # An inward reserve is a design input, so reject it at the contract boundary
        # when it leaves no valid geometry.  The source model and its pieces remain
        # available through the properties below; no bounding-box replacement occurs.
        self.buildable_shape
        self.massing_limit_shape

        # Calling this here makes support spaces part of the budget before any
        # allocator sees the brief.  It also preserves the existing constitution's
        # provenance and placeholder wording; this contract does not invent code data.
        resolved = self.resolved_spaces()
        resolved_ids = [space.id for space in resolved]
        if len(resolved_ids) != len(set(resolved_ids)):
            raise ValueError('resolved space ids must be unique, including support spaces')

        net_area = sum(space.area_m2 for space in resolved
                       if space.category != 'circulation')
        listed_circulation_area = sum(space.area_m2 for space in resolved
                                      if space.category == 'circulation')
        circulation_area = self._circulation_area_for(
            net_area, listed_circulation_area)
        gross_area = net_area + circulation_area
        capacity = self.capacity_m2
        if self.target_gross_area_m2 + AREA_EPSILON_M2 < gross_area:
            raise ValueError(
                f'target gross area {self.target_gross_area_m2:.3f} m2 is below the '
                f'unchanged program plus circulation budget {gross_area:.3f} m2; '
                'rooms are never silently shrunk')
        if gross_area > capacity + AREA_EPSILON_M2:
            raise ValueError(
                f'program gross area {gross_area:.3f} m2 exceeds necessary site '
                f'capacity {capacity:.3f} m2 (site area {self.site.area_m2:.3f} m2 x '
                f'{self.occupied_storeys} storeys)')
        if self.target_gross_area_m2 > capacity + AREA_EPSILON_M2:
            raise ValueError(
                f'target gross area {self.target_gross_area_m2:.3f} m2 exceeds '
                f'necessary site capacity {capacity:.3f} m2')
        return self

    def resolved_spaces(self) -> tuple[SpaceRequirement, ...]:
        """Return client spaces plus constitution-generated support spaces.

        Support requirements are generated from the project's typology and exact
        client brief by the existing constitution.  The returned tuple still contains
        no placement coordinates.
        """
        from .constitution import support_spaces

        generated = support_spaces(self.typology,self.spaces,storeys=self.occupied_storeys)
        if self.support_sizing is None:
            return tuple(self.spaces) + tuple(generated)
        premise = self.support_sizing
        unknown = set(premise.sizes)-{space.id for space in generated}
        if unknown:
            raise ValueError('support sizing may only replace automatically generated '
                             f'placeholders, not explicit rooms: {sorted(unknown)}')
        result = []
        for space in generated:
            size = premise.sizes.get(space.id)
            if size is None:
                result.append(space)
                continue
            result.append(space.model_copy(update={
                'area_m2':size.area_m2, 'min_dimension_m':size.min_dimension_m,
                'reason':f'Project support sizing ({premise.source}, needs_review=True): '
                         f'{premise.basis} This explicitly replaces the automatic '
                         f'{space.area_m2:g} m2 / {space.min_dimension_m:g} m placeholder '
                         f'with {size.area_m2:g} m2 / {size.min_dimension_m:g} m before '
                         'placement. Function, access and level requirements are retained. '
                         'Equipment, fixtures, operations and adopted-code sizing remain '
                         f'professional_review_required. Superseded basis: {space.reason}'}))
        return tuple(self.spaces) + tuple(result)

    def _circulation_area_for(self, net_area: float,
                              listed_circulation_area: float | None = None) -> float:
        listed_circulation_area = (
            self.listed_circulation_area_m2
            if listed_circulation_area is None else listed_circulation_area)
        if self.circulation_budget_m2 is not None:
            if self.circulation_budget_m2 + AREA_EPSILON_M2 < listed_circulation_area:
                raise ValueError(
                    f'circulation budget {self.circulation_budget_m2:.3f} m2 is '
                    f'below explicitly listed circulation spaces '
                    f'{listed_circulation_area:.3f} m2')
            return float(self.circulation_budget_m2)
        assert self.circulation_fraction is not None
        # The fraction is a fraction of gross area and is solved against only the
        # non-circulation net.  Explicit foyer/entry spaces still consume the reserve,
        # so the total circulation allocation is whichever requirement is larger.
        reserve = float(net_area * self.circulation_fraction /
                        (1.0 - self.circulation_fraction))
        return max(reserve, float(listed_circulation_area))

    @property
    def buildable_shape(self):
        """The site after the optional symmetric project setback."""
        distance = self.site_setbacks.setback_m if self.site_setbacks else 0.0
        return _inset_shape(self.site.shape, distance, 'buildable setback')

    @property
    def massing_limit_shape(self):
        """The buildable shape after the optional facade projection reserve."""
        distance = (self.site_setbacks.facade_projection_m
                    if self.site_setbacks else 0.0)
        return _inset_shape(self.buildable_shape, distance, 'facade projection')

    @property
    def net_program_area_m2(self) -> float:
        """Resolved non-circulation area; circulation is accounted for separately."""
        return float(sum(space.area_m2 for space in self.resolved_spaces()
                         if space.category != 'circulation'))

    @property
    def resolved_space_area_m2(self) -> float:
        """Raw sum of all resolved room requirements, including circulation rooms."""
        return float(sum(space.area_m2 for space in self.resolved_spaces()))

    @property
    def listed_circulation_area_m2(self) -> float:
        """Area of explicit brief spaces already tagged as circulation."""
        return float(sum(space.area_m2 for space in self.resolved_spaces()
                         if space.category == 'circulation'))

    @property
    def circulation_area_m2(self) -> float:
        return self._circulation_area_for(self.net_program_area_m2)

    @property
    def gross_program_area_m2(self) -> float:
        return self.net_program_area_m2 + self.circulation_area_m2

    @property
    def capacity_m2(self) -> float:
        """Necessary upper bound from the massing envelope, not a placement result."""
        return float(self.massing_limit_shape.area * self.occupied_storeys)

    def validation_report(self) -> BriefValidationReport:
        supplied_ids = {space.id for space in self.spaces}
        support_ids = tuple(space.id for space in self.resolved_spaces()
                            if space.id not in supplied_ids)
        return BriefValidationReport(
            site_area_m2=self.site.area_m2,
            site_bbox_area_m2=self.site.bbox_area_m2,
            buildable_area_m2=float(self.buildable_shape.area),
            massing_limit_area_m2=float(self.massing_limit_shape.area),
            buildable_geometry_type=self.buildable_shape.geom_type,
            massing_limit_geometry_type=self.massing_limit_shape.geom_type,
            buildable_boundary=_boundary_coordinates(self.buildable_shape),
            massing_limit_boundary=_boundary_coordinates(self.massing_limit_shape),
            target_gross_area_m2=self.target_gross_area_m2,
            net_program_area_m2=self.net_program_area_m2,
            circulation_area_m2=self.circulation_area_m2,
            gross_program_area_m2=self.gross_program_area_m2,
            capacity_m2=self.capacity_m2,
            support_space_ids=support_ids,
        )

    def report(self) -> dict[str, Any]:
        """JSON-compatible validation report for provider/run manifests."""
        return self.validation_report().model_dump(mode='json')

    def normalized_json(self) -> dict[str, Any]:
        """Return the normalized JSON payload, including measured area accounting."""
        payload = self.model_dump(mode='json')
        payload['site']['area_m2'] = self.site.area_m2
        payload['site']['bbox_area_m2'] = self.site.bbox_area_m2
        payload['resolved_spaces'] = [
            space.model_dump(mode='json') for space in self.resolved_spaces()
        ]
        payload['area_accounting'] = self.report()
        payload['area_accounting']['resolved_space_area_m2'] = self.resolved_space_area_m2
        payload['area_accounting']['listed_circulation_area_m2'] = \
            self.listed_circulation_area_m2
        return payload

    def normalized_json_text(self) -> str:
        return json.dumps(self.normalized_json(), ensure_ascii=False, sort_keys=True)


class ProjectBriefProvider(Protocol):
    """Minimal provider seam required by Decision 0004."""

    def generate(self, request: Mapping[str, Any], seed: str | int | None = None) -> Mapping[str, Any]:
        ...

    def normalize(self, raw_brief: Mapping[str, Any]) -> ProjectBrief:
        ...

    def validate(self, project_brief: ProjectBrief) -> BriefValidationReport:
        ...


def normalize_project_brief(
    raw_brief: Mapping[str, Any],
    *,
    provenance: BriefProvenance | Mapping[str, Any] | None = None,
) -> ProjectBrief:
    """Normalize one provider payload through the single validated contract.

    This helper does no repair that could change the requested program.  Missing
    provenance is rejected so a run cannot look deterministic or external without
    recording who proposed it.
    """
    if isinstance(raw_brief, ProjectBrief):
        return raw_brief
    values = dict(raw_brief)
    # ``normalized_json`` deliberately carries measured and resolved read-outs.  They
    # are derived evidence, not authoring inputs, so accept a round-trip while keeping
    # them out of the typed source contract.
    if isinstance(values.get('site'), Mapping):
        site = dict(values['site'])
        site.pop('area_m2', None)
        site.pop('bbox_area_m2', None)
        values['site'] = site
    values.pop('resolved_spaces', None)
    values.pop('area_accounting', None)
    if provenance is not None:
        values['provenance'] = provenance
    if 'provenance' not in values:
        raise ValueError('brief provenance is required for normalization')
    return ProjectBrief.model_validate(values)


def raw_response_hash(raw_brief: Mapping[str, Any]) -> str:
    """Stable SHA-256 for a provider response without retaining unrestricted prose."""
    encoded = json.dumps(raw_brief, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':'), default=str).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()
