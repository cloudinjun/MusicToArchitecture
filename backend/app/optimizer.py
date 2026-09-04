"""Genetic search for a relative optimum inside the legal datum domain.

The search does **not** design the building. It moves the datums -- bay dimensions,
joist spacing, floor-to-floor -- inside a box that three other layers have already
fixed, and it reports the best compromise it found:

    building code      -> which structural systems are admissible at all   (codes.py)
    system guideline   -> the legal range of each datum                    (structural_systems/)
    architectural score-> the *proposed* value of each datum inside that range
    GA (this module)   -> the value actually adopted, negotiated against
                          load calculation, material cost, and buildability

The one design decision that matters here
-----------------------------------------

A pure "minimise steel" objective always wins by collapsing the building toward the
cheapest structure, and the music becomes decoration bolted onto a result it did not
influence. So `score_fidelity` is a first-class objective with real weight: every metre
the optimiser moves a datum away from the value the score proposed costs it fitness.

The result is a negotiation with a visible exchange rate rather than an optimisation
that quietly overrules the brief. `explain()` prints that exchange rate for one run.

Determinism
-----------

Seeded RNG, fixed population and generation counts, and no wall-clock or hash-order
dependence, so the same score and bounds reproduce the same genome. The project's
repeatability gate depends on it.
"""

from __future__ import annotations

import random
from typing import Callable, Literal

from pydantic import BaseModel, Field

from .loads import OCCUPANCY_LIVE, OccupancyLive, composite_steel_deck, flat_roof_assembly
from .sections import STEEL_BEAMS, STEEL_COLUMNS, SectionProperties
from .sizing import FrameSizing, size_gravity_frame


# ---------------------------------------------------------------------------
# Search space
# ---------------------------------------------------------------------------

class DatumGene(BaseModel):
    """One searchable datum: a legal range from the system guideline, plus the value the
    architectural score proposed inside it."""

    name: str
    low: float
    high: float
    proposed: float
    unit: str = 'm'
    source_ref: str

    def clamp(self, value: float) -> float:
        return min(self.high, max(self.low, value))

    def normalised_distance(self, value: float) -> float:
        span = self.high - self.low
        return 0.0 if span <= 0 else abs(value - self.proposed) / span


class SearchSpace(BaseModel):
    genes: list[DatumGene]

    def names(self) -> list[str]:
        return [g.name for g in self.genes]

    def proposed(self) -> list[float]:
        return [g.proposed for g in self.genes]

    def clamp(self, genome: list[float]) -> list[float]:
        return [gene.clamp(value) for gene, value in zip(self.genes, genome)]

    def score_fidelity(self, genome: list[float]) -> float:
        """1.0 when every datum sits exactly where the score proposed it."""
        distances = [g.normalised_distance(v) for g, v in zip(self.genes, genome)]
        return 1.0 - sum(distances) / len(distances)


def steel_frame_space(score_datums: dict[str, float]) -> SearchSpace:
    """Legal ranges from `docs/guidelines/structural_systems/01_steel_frame.md`."""
    ref = 'docs/guidelines/structural_systems/01_steel_frame.md'
    return SearchSpace(genes=[
        DatumGene(name='bay_x_m', low=5.6, high=9.0,
                  proposed=score_datums['bay_x_m'], source_ref=ref),
        DatumGene(name='bay_y_m', low=5.6, high=9.0,
                  proposed=score_datums['bay_y_m'], source_ref=ref),
        DatumGene(name='joist_spacing_m', low=1.5, high=3.0,
                  proposed=score_datums['joist_spacing_m'], source_ref=ref),
        DatumGene(name='floor_to_floor_m', low=3.9, high=5.4,
                  proposed=score_datums['floor_to_floor_m'], source_ref=ref),
    ])


# ---------------------------------------------------------------------------
# Objectives
# ---------------------------------------------------------------------------

class ObjectiveWeights(BaseModel):
    """The exchange rate between engineering and intent. Publishing it is the point.

    `material_efficiency` is a **cost proxy and is switched off by default.** The project
    is at the elimination stage: hard standards rule out what is impossible, and the
    criteria for choosing among what remains have not been defined. Letting steel tonnage
    into the objective now would quietly answer that question with "the cheapest one",
    which is a selection decision this layer is not entitled to make.

    Turn it on with `ObjectiveWeights.selection_stage()` only once the project has
    written down what it is actually selecting for.
    """

    score_fidelity: float = 0.45
    utilisation: float = 0.25
    constructability: float = 0.30
    material_efficiency: float = 0.0

    @classmethod
    def elimination_stage(cls) -> 'ObjectiveWeights':
        """Feasibility, intent, and buildability only. No cost."""
        return cls()

    @classmethod
    def selection_stage(cls, material_efficiency: float = 0.26) -> 'ObjectiveWeights':
        """Only for use after the selection criteria exist and are recorded.

        The three elimination-stage objectives are scaled down proportionally to make
        room for the cost term, so introducing cost does not silently change the
        relative importance of intent, utilisation, and buildability.
        """
        share = 1.0 - material_efficiency
        return cls(score_fidelity=round(0.45 * share, 4),
                   utilisation=round(0.25 * share, 4),
                   constructability=round(0.30 * share, 4),
                   material_efficiency=material_efficiency)

    def total(self) -> float:
        return (self.score_fidelity + self.material_efficiency
                + self.utilisation + self.constructability)

    def active(self) -> dict[str, float]:
        return {name: value for name, value in
                (('score_fidelity', self.score_fidelity),
                 ('material_efficiency', self.material_efficiency),
                 ('utilisation', self.utilisation),
                 ('constructability', self.constructability)) if value > 0.0}


class Evaluation(BaseModel):
    genome: list[float]
    datums: dict[str, float]
    feasible: bool
    failures: list[str]
    fitness: float
    objectives: dict[str, float]
    steel_kg_per_m2: float
    mean_utilisation: float
    sections: dict[str, str]
    column_axial_kn: float


INFEASIBLE_FITNESS = -1.0

# A reference intensity used to normalise steel mass into 0..1. It is a project-authored
# scale for comparison inside one run, not a benchmark or a target.
STEEL_REFERENCE_KG_M2 = 90.0

# Preferred module for constructability: bays close to a 0.3 m increment and joist
# spacings that divide the bay a whole number of times are cheaper to detail.
MODULE_M = 0.3


def _utilisation_score(mean_ratio: float) -> float:
    """Reward members working hard but not at the limit. A frame at 0.35 is wasteful; a
    frame at 0.99 has no tolerance for the loads this model does not include."""
    target_low, target_high = 0.75, 0.92
    if target_low <= mean_ratio <= target_high:
        return 1.0
    if mean_ratio < target_low:
        return max(0.0, mean_ratio / target_low)
    return max(0.0, 1.0 - (mean_ratio - target_high) / (1.0 - target_high))


def _constructability_score(datums: dict[str, float]) -> float:
    parts: list[float] = []
    for key in ('bay_x_m', 'bay_y_m', 'floor_to_floor_m'):
        value = datums[key]
        offset = abs(value / MODULE_M - round(value / MODULE_M)) * MODULE_M
        parts.append(max(0.0, 1.0 - offset / (MODULE_M / 2.0)))
    divisions = datums['bay_x_m'] / datums['joist_spacing_m']
    parts.append(max(0.0, 1.0 - abs(divisions - round(divisions))))
    aspect = max(datums['bay_x_m'], datums['bay_y_m']) / min(
        datums['bay_x_m'], datums['bay_y_m'])
    parts.append(max(0.0, 1.0 - (aspect - 1.0) / 0.8))
    return sum(parts) / len(parts)


class FrameProblem(BaseModel):
    """Everything the fitness function needs that the genome does not carry."""

    storeys: int
    plan_x_m: float
    plan_y_m: float
    occupancy_id: str
    roof_occupancy_id: str = 'roof_ordinary'
    max_beam_depth_mm: float | None = None

    @property
    def occupancy(self) -> OccupancyLive:
        return OCCUPANCY_LIVE[self.occupancy_id]

    @property
    def roof_occupancy(self) -> OccupancyLive:
        return OCCUPANCY_LIVE[self.roof_occupancy_id]


def evaluate(
    genome: list[float], space: SearchSpace, problem: FrameProblem,
    weights: ObjectiveWeights,
    beam_catalogue: list[SectionProperties] = STEEL_BEAMS,
    column_catalogue: list[SectionProperties] = STEEL_COLUMNS,
) -> Evaluation:
    datums = dict(zip(space.names(), space.clamp(genome)))
    deck = composite_steel_deck()
    roof = flat_roof_assembly()

    sizing: FrameSizing = size_gravity_frame(
        bay_x_m=datums['bay_x_m'], bay_y_m=datums['bay_y_m'],
        joist_spacing_m=datums['joist_spacing_m'],
        floor_to_floor_m=datums['floor_to_floor_m'],
        storeys=problem.storeys, plan_x_m=problem.plan_x_m, plan_y_m=problem.plan_y_m,
        occupancy=problem.occupancy, roof_occupancy=problem.roof_occupancy,
        superimposed_dead_kpa=deck.superimposed_dead_kpa(),
        roof_dead_kpa=roof.superimposed_dead_kpa(),
        beam_catalogue=beam_catalogue, column_catalogue=column_catalogue,
        max_beam_depth_mm=problem.max_beam_depth_mm)

    fidelity = space.score_fidelity(list(datums.values()))
    if not sizing.feasible:
        return Evaluation(
            genome=list(datums.values()), datums=datums, feasible=False,
            failures=sizing.failures, fitness=INFEASIBLE_FITNESS,
            objectives={'score_fidelity': round(fidelity, 4)},
            steel_kg_per_m2=0.0, mean_utilisation=0.0, sections={},
            column_axial_kn=sizing.column_axial_kn)

    material = max(0.0, 1.0 - sizing.steel_kg_per_m2 / STEEL_REFERENCE_KG_M2)
    utilisation = _utilisation_score(sizing.mean_utilisation)
    constructability = _constructability_score(datums)
    objectives = {
        'score_fidelity': round(fidelity, 4),
        'material_efficiency': round(material, 4),
        'utilisation': round(utilisation, 4),
        'constructability': round(constructability, 4),
    }
    contributions = {
        'score_fidelity': fidelity, 'material_efficiency': material,
        'utilisation': utilisation, 'constructability': constructability,
    }
    active = weights.active()
    fitness = sum(weight * contributions[name] for name, weight in active.items())         / sum(active.values())

    sections = {
        'joist': sizing.joist.check.section_id if sizing.joist and sizing.joist.check else '',
        'girder': sizing.beam.check.section_id if sizing.beam and sizing.beam.check else '',
        'column': sizing.column.check.section_id if sizing.column and sizing.column.check else '',
    }
    return Evaluation(
        genome=list(datums.values()), datums=datums, feasible=True, failures=[],
        fitness=round(fitness, 6), objectives=objectives,
        steel_kg_per_m2=sizing.steel_kg_per_m2,
        mean_utilisation=sizing.mean_utilisation, sections=sections,
        column_axial_kn=sizing.column_axial_kn)


# ---------------------------------------------------------------------------
# Genetic algorithm
# ---------------------------------------------------------------------------

class GaSettings(BaseModel):
    population: int = Field(default=60, ge=8)
    generations: int = Field(default=40, ge=1)
    tournament_size: int = Field(default=3, ge=2)
    crossover_alpha: float = Field(default=0.35, ge=0.0)
    mutation_rate: float = Field(default=0.25, ge=0.0, le=1.0)
    mutation_sigma_fraction: float = Field(default=0.12, gt=0.0)
    elite_count: int = Field(default=2, ge=0)
    seed: int = 20260829


class GenerationRecord(BaseModel):
    generation: int
    best_fitness: float
    mean_fitness: float
    feasible_count: int
    best_datums: dict[str, float]


class OptimisationResult(BaseModel):
    best: Evaluation
    baseline: Evaluation
    history: list[GenerationRecord]
    settings: GaSettings
    weights: ObjectiveWeights
    space: SearchSpace
    evaluations: int
    verdict: Literal['improved', 'score_proposal_retained', 'no_feasible_solution']


def _tournament(
    population: list[Evaluation], rng: random.Random, size: int,
) -> Evaluation:
    picks = [rng.choice(population) for _ in range(size)]
    return max(picks, key=lambda e: e.fitness)


def _crossover(
    a: list[float], b: list[float], space: SearchSpace, rng: random.Random, alpha: float,
) -> list[float]:
    """BLX-alpha: sample inside the parents' interval, widened by alpha, per gene."""
    child: list[float] = []
    for gene, x, y in zip(space.genes, a, b):
        low, high = min(x, y), max(x, y)
        spread = (high - low) * alpha
        child.append(gene.clamp(rng.uniform(low - spread, high + spread)))
    return child


def _mutate(
    genome: list[float], space: SearchSpace, rng: random.Random,
    rate: float, sigma_fraction: float,
) -> list[float]:
    out: list[float] = []
    for gene, value in zip(space.genes, genome):
        if rng.random() < rate:
            sigma = (gene.high - gene.low) * sigma_fraction
            value = gene.clamp(rng.gauss(value, sigma))
        out.append(value)
    return out


def optimise(
    space: SearchSpace, problem: FrameProblem, *,
    weights: ObjectiveWeights | None = None,
    settings: GaSettings | None = None,
    evaluator: Callable[..., Evaluation] = evaluate,
) -> OptimisationResult:
    weights = weights or ObjectiveWeights()
    settings = settings or GaSettings()
    rng = random.Random(settings.seed)
    evaluations = 0

    def score(genome: list[float]) -> Evaluation:
        nonlocal evaluations
        evaluations += 1
        return evaluator(genome, space, problem, weights)

    baseline = score(space.proposed())

    # Seed the population with the score's own proposal so the search can never do
    # worse than the brief unless the brief is infeasible.
    population: list[Evaluation] = [baseline]
    while len(population) < settings.population:
        genome = [rng.uniform(g.low, g.high) for g in space.genes]
        population.append(score(genome))

    history: list[GenerationRecord] = []
    for generation in range(settings.generations):
        population.sort(key=lambda e: -e.fitness)
        feasible = [e for e in population if e.feasible]
        history.append(GenerationRecord(
            generation=generation,
            best_fitness=round(population[0].fitness, 6),
            mean_fitness=round(
                sum(e.fitness for e in population) / len(population), 6),
            feasible_count=len(feasible),
            best_datums={k: round(v, 4) for k, v in population[0].datums.items()}))

        offspring = population[:settings.elite_count]
        while len(offspring) < settings.population:
            parent_a = _tournament(population, rng, settings.tournament_size)
            parent_b = _tournament(population, rng, settings.tournament_size)
            child = _crossover(parent_a.genome, parent_b.genome, space, rng,
                               settings.crossover_alpha)
            child = _mutate(child, space, rng, settings.mutation_rate,
                            settings.mutation_sigma_fraction)
            offspring.append(score(child))
        population = offspring

    population.sort(key=lambda e: -e.fitness)
    best = population[0]
    if not best.feasible:
        verdict: Literal['improved', 'score_proposal_retained', 'no_feasible_solution'] \
            = 'no_feasible_solution'
    elif best.fitness > baseline.fitness + 1e-9:
        verdict = 'improved'
    else:
        verdict = 'score_proposal_retained'

    return OptimisationResult(
        best=best, baseline=baseline, history=history, settings=settings,
        weights=weights, space=space, evaluations=evaluations, verdict=verdict)


def explain(result: OptimisationResult) -> list[str]:
    """The negotiation, in words: what the score asked for, what the optimiser adopted,
    and what each move bought."""
    lines: list[str] = []
    base, best = result.baseline, result.best
    lines.append(f'verdict: {result.verdict} after {result.evaluations} evaluations')
    if not base.feasible:
        lines.append('the score proposal was not structurally feasible: '
                     + '; '.join(base.failures))
    lines.append(f'fitness {base.fitness:.4f} -> {best.fitness:.4f}')
    for gene in result.space.genes:
        proposed = gene.proposed
        adopted = best.datums[gene.name]
        drift = gene.normalised_distance(adopted)
        note = 'held' if drift < 0.02 else f'moved {abs(adopted - proposed):+.2f} {gene.unit}'
        lines.append(
            f'  {gene.name:18} score proposed {proposed:.2f}, adopted {adopted:.2f} '
            f'[{gene.low:.2f}-{gene.high:.2f}]  {note}')
    if base.feasible:
        lines.append(f'  steel {base.steel_kg_per_m2:.1f} -> {best.steel_kg_per_m2:.1f} '
                     f'kg/m2, mean utilisation {base.mean_utilisation:.2f} -> '
                     f'{best.mean_utilisation:.2f}')
    active = result.weights.active()
    for key, value in best.objectives.items():
        weight = active.get(key)
        suffix = (f'(weight {weight:.2f})' if weight is not None
                  else '(reported, weight 0 - deferred to the selection stage)')
        lines.append(f'  objective {key:20} {value:.3f} {suffix}')
    lines.append('  sections: ' + ', '.join(f'{k}={v}' for k, v in best.sections.items()))
    return lines


# ---------------------------------------------------------------------------
# Feasibility mapping -- the elimination-stage use of the search space
# ---------------------------------------------------------------------------

class GeneFeasibleRange(BaseModel):
    name: str
    legal_low: float
    legal_high: float
    feasible_low: float | None
    feasible_high: float | None
    unit: str

    @property
    def fully_usable(self) -> bool:
        return (self.feasible_low is not None
                and abs(self.feasible_low - self.legal_low) < 1e-9
                and abs((self.feasible_high or 0.0) - self.legal_high) < 1e-9)


class FeasibilityMap(BaseModel):
    """Does a workable design exist anywhere in this datum box, and where?

    This is the elimination-stage question, and it is one a single-point check cannot
    answer. A structural system whose legal datum range contains no feasible design for
    this program is ruled out on a hard standard, not on preference -- and equally, a
    system that only works in a corner of its own range has been narrowed by physics in
    a way the designer needs to see before choosing.
    """

    samples: int
    feasible_count: int
    feasible_fraction: float
    gene_ranges: list[GeneFeasibleRange]
    binding_constraints: dict[str, int]
    proposal_feasible: bool
    proposal_failures: list[str]
    resolution: int
    verdict: Literal['no_feasible_design', 'narrow', 'broad']


def _lattice(space: SearchSpace, resolution: int) -> list[list[float]]:
    axes: list[list[float]] = []
    for gene in space.genes:
        if resolution == 1:
            axes.append([(gene.low + gene.high) / 2.0])
        else:
            step = (gene.high - gene.low) / (resolution - 1)
            axes.append([gene.low + step * i for i in range(resolution)])
    points: list[list[float]] = [[]]
    for values in axes:
        points = [point + [value] for point in points for value in values]
    return points


def map_feasible_region(
    space: SearchSpace, problem: FrameProblem, *, resolution: int = 6,
    weights: ObjectiveWeights | None = None,
    evaluator: Callable[..., Evaluation] = evaluate,
) -> FeasibilityMap:
    """Sweep the legal datum box on a deterministic lattice and report where a design
    exists. No optimisation, no ranking, no cost -- only "possible" and "not possible"."""
    weights = weights or ObjectiveWeights.elimination_stage()
    feasible: list[list[float]] = []
    binding: dict[str, int] = {}

    for point in _lattice(space, resolution):
        result = evaluator(point, space, problem, weights)
        if result.feasible:
            feasible.append(result.genome)
        else:
            for failure in result.failures:
                key = failure.split(':')[0].strip()
                binding[key] = binding.get(key, 0) + 1

    ranges: list[GeneFeasibleRange] = []
    for index, gene in enumerate(space.genes):
        values = [point[index] for point in feasible]
        ranges.append(GeneFeasibleRange(
            name=gene.name, legal_low=gene.low, legal_high=gene.high,
            feasible_low=round(min(values), 4) if values else None,
            feasible_high=round(max(values), 4) if values else None,
            unit=gene.unit))

    proposal = evaluator(space.proposed(), space, problem, weights)
    total = resolution ** len(space.genes)
    fraction = len(feasible) / total if total else 0.0
    verdict = ('no_feasible_design' if not feasible
               else 'narrow' if fraction < 0.35 else 'broad')
    return FeasibilityMap(
        samples=total, feasible_count=len(feasible),
        feasible_fraction=round(fraction, 4), gene_ranges=ranges,
        binding_constraints=dict(sorted(binding.items(), key=lambda kv: -kv[1])),
        proposal_feasible=proposal.feasible, proposal_failures=proposal.failures,
        resolution=resolution, verdict=verdict)
