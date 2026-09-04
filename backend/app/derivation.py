"""How each element came to be where it is and what size it is.

Every element in this model already carries the pieces of its own justification --
which datums it read, which lattice indices it sits on, what it bears on, which
section was chosen and by what check. What it did not carry was the *order*: the
sequence a person actually reasons in when they model something, from a located point,
through a line, to a surface, to a solid.

That order is the thing worth showing. A panel of loose facts -- `datum_refs`,
`section_id`, `governing_check` -- tells a reader what was recorded; a chain tells them
how the decision was made, and lets them see the step where they disagree. So this
assembles the facts into steps and states which stage of the chain each one is.

The stages are the modelling sequence:

  point     a located node -- a lattice intersection, an apse node, a level datum
  line      a centre-line or an edge between points
  surface   a polygon: the floor plate, a facade bay, a panel
  solid     the body itself, swept or extruded from the stage above
  host      what it bears on or hangs from, and by what relation
  check     the calculation that fixed its size, or the honest absence of one

A chain that never reaches `solid` is incomplete, and a chain whose first step is a
solid skipped the reasoning entirely. Both are reported rather than hidden -- the
scale figures are the second case, and saying so is more useful than a chain that
starts in the middle and looks finished.
"""

from __future__ import annotations

import math

from .geometry import BoxGeometry, ExtrusionGeometry, MemberGeometry, QuadGeometry
from .models_v3 import DerivationChain, DerivationStep


# A coordinate is "on" a lattice datum within this. Positions are computed from the
# lattice, so agreement is to floating point; the tolerance covers the arithmetic, not
# a design allowance.
ON_DATUM_M = 0.05


def _fmt(value: float) -> str:
    return f'{value:+.3f}' if abs(value) >= 0.0005 else '0.000'


def _grid_label(index: int, letters: bool) -> str:
    if not letters:
        return str(index + 1)
    label = ''
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        label = chr(ord('A') + remainder) + label
    return label


def _node_name(lattice, x: float, y: float) -> str | None:
    """The grid reference for a point, if it stands on one."""
    xi = next((i for i, value in enumerate(lattice.x_lines)
               if abs(value - x) < ON_DATUM_M), None)
    yj = next((j for j, value in enumerate(lattice.y_lines)
               if abs(value - y) < ON_DATUM_M), None)
    if xi is not None and yj is not None:
        return f'{_grid_label(xi, True)}/{_grid_label(yj, False)}'
    for index, node in enumerate(lattice.apse_nodes):
        if math.hypot(node.x - x, node.y - y) < ON_DATUM_M:
            return f'apse node A{index:02d}'
    if xi is not None:
        return f'grid line {_grid_label(xi, True)}'
    if yj is not None:
        return f'grid line {_grid_label(yj, False)}'
    return None


def _level_of(lattice, z: float):
    return next((level for level in lattice.levels
                 if abs(level.z - z) < 0.6), None)


def _datum_step(element, datum_set) -> DerivationStep | None:
    """The datums the element declares it read, with the values they held."""
    if not element.datum_refs:
        return None
    values = []
    for name in element.datum_refs[:6]:
        try:
            values.append(f'{name} = {datum_set.value(name):.3f}')
        except (AttributeError, KeyError):
            # A datum ref that names something the set does not hold is worth showing
            # as the bare name rather than dropping: the reference is the claim.
            values.append(name)
    return DerivationStep(
        stage='point', label='datums read',
        value='; '.join(values),
        source='datum_set',
        why=('The dimensions this element is a function of. Change one and the element '
             'moves or resizes; nothing here is a literal.'))


def _member_steps(element, lattice) -> list[DerivationStep]:
    geometry: MemberGeometry = element.geometry
    start, end = geometry.path[0], geometry.path[-1]
    steps: list[DerivationStep] = []

    for label, point in (('start', start), ('end', end)):
        name = _node_name(lattice, point.x, point.y)
        level = _level_of(lattice, point.z)
        located = name or 'derived point'
        where = f'({_fmt(point.x)}, {_fmt(point.y)}, {_fmt(point.z)})'
        steps.append(DerivationStep(
            stage='point', label=f'{label} node', value=f'{located} at {where}',
            source=(f'lattice {name}' if name else 'derived from the lattice'),
            why=(f'Registered on {level.id} at {_fmt(level.z)} m.' if level
                 else 'Between level datums.')))

    length = math.dist((start.x, start.y, start.z), (end.x, end.y, end.z))
    steps.append(DerivationStep(
        stage='line', label='centre-line', value=f'{length:.3f} m between those nodes',
        source='axis skeleton',
        why=('The member is this line first. Its body is swept along it, so the two '
             'cannot disagree about where the member is.')))

    steps.append(DerivationStep(
        stage='solid', label='swept section',
        value=(element.section_id or geometry.profile or 'convention profile'),
        source=element.sizing_status,
        why=('Sized by calculation.' if element.sizing_status == 'sized_by_calculation'
             else 'An architectural dimension no check governs; recorded as convention '
                  'so it is never presented as verified.')))
    return steps


def _extrusion_steps(element, lattice) -> list[DerivationStep]:
    geometry: ExtrusionGeometry = element.geometry
    level = _level_of(lattice, geometry.z_top) or _level_of(lattice, geometry.z_base)
    holes = len(geometry.holes or ())
    steps = [
        DerivationStep(
            stage='surface', label='boundary polygon',
            value=(f'{len(geometry.boundary)} points'
                   + (f', {holes} void{"s" if holes != 1 else ""}' if holes else '')),
            source=(f'{level.id} plate' if level else 'plate datum'),
            why=('The floor plate the massing family produced. The element takes that '
                 'polygon rather than an outline of its own, so a change to the '
                 'massing moves it.')),
        DerivationStep(
            stage='solid', label='extruded',
            value=f'{_fmt(geometry.z_base)} to {_fmt(geometry.z_top)} m '
                  f'({geometry.z_top - geometry.z_base:.3f} m thick)',
            source='thickness datum',
            why='The surface given a body between two level-referenced heights.'),
    ]
    return steps


def _box_steps(element, lattice) -> list[DerivationStep]:
    centre, size = element.geometry.center, element.geometry.size
    name = _node_name(lattice, centre.x, centre.y)
    level = _level_of(lattice, centre.z)
    steps = [
        DerivationStep(
            stage='point' if name else 'surface',
            label='placed at',
            value=f'({_fmt(centre.x)}, {_fmt(centre.y)}, {_fmt(centre.z)})',
            source=(f'lattice {name}' if name
                    else f'within the {level.id} plate' if level
                    else 'derived position'),
            why=('On a registered grid node.' if name and '/' in name
                 else 'On a registered grid line.' if name
                 else 'Positioned inside a plate the lattice produced, not at a '
                      'coordinate written by hand.')),
        DerivationStep(
            stage='solid', label='box',
            value=f'{size.x:.3f} x {size.y:.3f} x {size.z:.3f} m',
            source=element.sizing_status,
            why=('Sized by calculation.' if element.sizing_status == 'sized_by_calculation'
                 else 'A conventional dimension; no check governs it.')),
    ]
    return steps


def _quad_steps(element, lattice) -> list[DerivationStep]:
    corners = element.geometry.corners
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    zs = [c.z for c in corners]
    width = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
    station = element.lattice_index.get('station')
    steps = [
        DerivationStep(
            stage='line', label='bay station',
            value=(f'station {station}' if station is not None else 'facade station'),
            source='envelope module',
            why=('The elevation is set out as stations along the plate edge; the panel '
                 'spans between two of them.')),
        DerivationStep(
            stage='surface', label='panel',
            value=f'{width:.3f} x {max(zs) - min(zs):.3f} m',
            source='transom rows / module datums',
            why='The face itself, between two stations and two transom heights.'),
    ]
    if element.thickness_m:
        steps.append(DerivationStep(
            stage='solid', label='construction depth',
            value=f'{element.thickness_m * 1000:.0f} mm',
            source='tectonic assembly',
            why=('The depth the panel is built at. Without it the panel is a surface '
                 'with no body and a cut plane can make nothing of it.')))
    return steps


# How many hosts to name before summarising. A slab bears on every joist under it --
# thirty of them -- and thirty identical lines is not a reasoning chain, it is a list
# that buries the steps either side of it.
HOSTS_SHOWN = 4


def _host_steps(element_id: str, relations) -> list[DerivationStep]:
    by_relation: dict[tuple[str, str], list] = {}
    for relation in relations:
        by_relation.setdefault(
            (relation.relation, relation.topology_status), []).append(relation)

    steps = []
    for (kind, topology), group in by_relation.items():
        shown = group[:HOSTS_SHOWN]
        value = ', '.join(item.host_id for item in shown)
        if len(group) > HOSTS_SHOWN:
            value += f' and {len(group) - HOSTS_SHOWN} more'
        steps.append(DerivationStep(
            stage='host', label=kind.replace('_', ' '),
            value=value, source=topology, why=group[0].basis))
    return steps


def _check_step(element) -> DerivationStep | None:
    if element.governing_check:
        return DerivationStep(
            stage='check', label='governing check', value=element.governing_check,
            source=f'utilisation {element.utilisation:.2f}'
                   if element.utilisation is not None else 'checked',
            why='The clause that decided the section. Others were satisfied by more.')
    if element.sizing_status == 'architectural_convention':
        return DerivationStep(
            stage='check', label='not calculated', value='architectural convention',
            source=element.sizing_status,
            why=('No load check governs this size. Saying so is the point: nothing '
                 'here may be presented as verified.'))
    return None


def _music_steps(element, datum_set, features, score) -> list[DerivationStep]:
    """Sound to datum: the half of the chain this project exists to make legible.

    A column is at 7.22 m centres because the recording has a certain onset density,
    and the path from one to the other runs through a named score dimension, a
    published mapping rule with a declared output range, and a datum. Every link is
    already recorded; without them assembled in order, an element carries a list of
    facts and no argument.

    Elements the music does not drive say so. A fire stair is required by code whatever
    the piece sounds like, and inventing a musical cause for it would be the one thing
    worse than having none.
    """
    if datum_set is None or not element.datum_refs:
        return []
    dimensions = {dimension.id: dimension
                  for dimension in (score.dimensions if score else ())}
    rules = {rule.id: rule for rule in (score.mapping_rules if score else ())}

    # Driven datums first, constants after. A chain that opens on a tectonic constant
    # -- a stair riser, a slab thickness -- buries the thing it exists to show, which
    # is that the building's dimensions came from a recording. The constants still
    # belong in the chain; they belong at the end of it, where they read as what they
    # are: the parts the music did not decide.
    ordered: list[str] = []
    for name in element.datum_refs:
        try:
            ordered.append((0 if datum_set.by_id(name).driving_dimension else 1, name))
        except (AttributeError, KeyError):
            continue
    ordered = [name for _rank, name in sorted(ordered, key=lambda item: item[0])]

    steps: list[DerivationStep] = []
    seen_dimensions: set[str] = set()
    seen_datums: set[str] = set()
    for name in ordered:
        if name in seen_datums:
            continue
        seen_datums.add(name)
        try:
            datum = datum_set.by_id(name)
        except (AttributeError, KeyError):
            continue
        driver = datum.driving_dimension
        if driver and driver not in seen_dimensions:
            seen_dimensions.add(driver)
            dimension = dimensions.get(driver)
            if dimension is not None:
                # A dimension may be read from more than one measurement, and the
                # name records that as `a+b`. Showing both values is the point: a
                # reader can see which measurement moved and which did not.
                parts, methods = [], []
                for field in dimension.source_feature.split('+'):
                    metric = getattr(features, field.strip(), None) if features else None
                    number = getattr(metric, 'value', metric)
                    if isinstance(number, (int, float)):
                        unit = getattr(metric, 'unit', '') or ''
                        parts.append(f'{field.strip()} = {number:.4g} {unit}'.strip())
                        method = getattr(metric, 'method', None)
                        if method:
                            methods.append(method)
                    else:
                        # A measurement the analyser did not produce. Naming it and
                        # showing nothing is the truthful state; the dimension was
                        # built from what was there.
                        parts.append(f'{field.strip()} (not measured)')
                steps.append(DerivationStep(
                    stage='feature', label=dimension.source_feature,
                    value='; '.join(parts),
                    source='; '.join(dict.fromkeys(methods)) or 'audio analysis',
                    why=('What the analyser measured. Everything downstream is a '
                         'function of numbers like this one.')))
                steps.append(DerivationStep(
                    stage='dimension', label=dimension.id,
                    value=f'{dimension.value:.3f} of 1',
                    source=f'{dimension.extraction_method}, '
                           f'confidence {dimension.confidence:.2f}',
                    why=dimension.architectural_proposal))
            rule = rules.get(datum.rule_id)
            if rule is not None:
                low, high = rule.output_range
                steps.append(DerivationStep(
                    stage='rule', label=rule.id,
                    value=f'{rule.source_dimension} -> {rule.target_parameter}, '
                          f'{rule.direction} into [{low:g}, {high:g}]',
                    source=f'priority {rule.priority}, owned by {rule.owner}',
                    why=('The published mapping. It is the place to argue with the '
                         'result: the range and the direction are the design decision, '
                         'and the music only chooses a position within them.')))
        position = ('' if datum.applied_position is None
                    else f', at {datum.applied_position:.2f} of its range')
        steps.append(DerivationStep(
            stage='datum', label=datum.id,
            value=f'{datum.value:.3f} {datum.unit}{position}',
            source=datum.provenance,
            why=datum.reason))
    return steps


def build_chain(element, lattice, datum_set, relations,
                features=None, score=None) -> DerivationChain:
    """Assemble one element's reasoning, in the order it was reasoned."""
    geometry = element.geometry
    if isinstance(geometry, MemberGeometry):
        body = _member_steps(element, lattice)
    elif isinstance(geometry, ExtrusionGeometry):
        body = _extrusion_steps(element, lattice)
    elif isinstance(geometry, QuadGeometry):
        body = _quad_steps(element, lattice)
    elif isinstance(geometry, BoxGeometry):
        body = _box_steps(element, lattice)
    else:
        body = []

    steps: list[DerivationStep] = _music_steps(element, datum_set, features, score)
    if not steps:
        # No musical driver. The datums are still worth naming -- they are what the
        # element is a function of -- but the chain begins at the building.
        datum = _datum_step(element, datum_set)
        if datum is not None:
            steps.append(datum)
    steps.extend(body)
    steps.extend(_host_steps(element.id, relations))
    check = _check_step(element)
    if check is not None:
        steps.append(check)

    stages = {step.stage for step in steps}
    return DerivationChain(
        element_id=element.id, kind=element.kind, level_id=element.level_id,
        steps=steps,
        reaches_solid='solid' in stages,
        starts_located=bool(stages & {'point', 'line', 'surface'}),
        reaches_audio='feature' in stages,
        rule_refs=list(element.rule_refs),
        summary=element.reason)


def build_chains(model, features=None, score=None
                 ) -> dict[str, DerivationChain]:
    """One chain per element, keyed by id, for a viewer to look up on click."""
    by_dependent: dict[str, list] = {}
    graph = getattr(model, 'dependency_graph', None)
    if graph is not None:
        for group in graph.relation_groups:
            for relation in group.expand():
                by_dependent.setdefault(relation.dependent_id, []).append(relation)

    datum_set = getattr(model, 'datum_set', None)
    chains: dict[str, DerivationChain] = {}
    for group in model.element_groups:
        for element in group.expand():
            chains[element.id] = build_chain(
                element, model.lattice, datum_set, by_dependent.get(element.id, ()),
                features=features, score=score)
    return chains
