"""Choosing a system and a grammar: the stage `coupling.py` deliberately left empty.

`screen_project` ends with a domain and refuses to rank it -- "choosing inside this set
is a later stage with its own criteria; this module deliberately provides none of them."
This is that later stage, and it is the reason fourteen recordings stopped producing
fourteen copies of the same building.

The division of labour is the one the project has held to throughout, and nothing here
weakens it:

- **The screen eliminates and never scores.** Hard physical gates and building-code
  gates decide what may exist. They contribute no number to the choice.
- **The score proposes and never eliminates.** The music places the project on four
  architectural axes. A low affinity cannot remove an option; it can only lose to a
  higher one *inside the admissible set*.
- **If the two disagree, the screen wins and says so.** When the music's preferred
  grammar is not admissible, the chosen option records the distance it had to travel,
  so the report can show that the building was overruled rather than pretending the
  music asked for what it got.

**`genre_style` still does not select a grammar.** Decision 0004 committed to that, and
the commitment survives here: the timbral reading enters as a bounded nudge on one axis,
never as a term that can carry a decision on its own. Its confidence is 0.35, so the
datum layer has already clamped its travel; letting it pick a facade would be exactly
the overreach that ADR refused.
"""

from __future__ import annotations

from .models import ArchitecturalScore
from .codes import JurisdictionProfile, UNRESOLVED_JURISDICTION
from .coupling import (
    FeasibleDomain, ProgramDemand, program_by_id, screen_project,
)
from .datums import DatumSet, Lattice
from .models_v3 import AxisReading, RankedOption, SelectionRecord
from .briefs import choose_typology
from .massing import MassingFamily, choose_massing
from .program import ProgramAllocation
from .tectonics import (
    ENVELOPE_TECTONICS, GRAMMAR_ENVELOPE, SYSTEM_BUILDABILITY, buildable_systems,
)

# ---------------------------------------------------------------------------
# The four axes
# ---------------------------------------------------------------------------
#
# These are chosen because each one is something a piece of music can genuinely be said
# to have, and something an elevation genuinely does. Axes that would have been easy to
# invent -- "warmth", "elegance" -- are absent because no measurement in this pipeline
# supports them.
#
#   mass        dissolved and glassy  ->  solid and load-bearing
#   layering    one skin              ->  a second structure standing in front
#   regularity  composed, irregular   ->  a strict repeating module
#   incident    an even field         ->  one dominant event on the elevation
#
AXES = ('mass', 'layering', 'regularity', 'incident')

ENVELOPE_POSITION: dict[str, dict[str, float]] = {
    'ENV-CURTAIN-WALL':    {'mass': 0.05, 'layering': 0.10, 'regularity': 0.90,
                            'incident': 0.05},
    'ENV-EXPRESSED-FRAME': {'mass': 0.12, 'layering': 0.45, 'regularity': 0.75,
                            'incident': 0.40},
    'ENV-DEEP-LATTICE':    {'mass': 0.35, 'layering': 0.95, 'regularity': 0.95,
                            'incident': 0.10},
    'ENV-PANEL-FIELD':     {'mass': 0.50, 'layering': 0.80, 'regularity': 0.70,
                            'incident': 0.20},
    'ENV-FACETED-PANEL':   {'mass': 0.60, 'layering': 0.30, 'regularity': 0.10,
                            'incident': 0.60},
    'ENV-APPLIED-ORDER':   {'mass': 0.68, 'layering': 0.60, 'regularity': 0.25,
                            'incident': 0.95},
    'ENV-PUNCHED-WALL':    {'mass': 0.85, 'layering': 0.15, 'regularity': 0.50,
                            'incident': 0.35},
    'ENV-BLANK-SLOT':      {'mass': 0.95, 'layering': 0.00, 'regularity': 0.35,
                            'incident': 0.80},
}

# The frame is judged on two axes only. A gravity frame does not have a "regularity"
# in the sense an elevation does, and pretending otherwise would put weight on a
# number that means nothing.
FRAME_POSITION: dict[str, dict[str, float]] = {
    'FRM-STEEL':        {'mass': 0.15, 'expression': 0.40},
    'FRM-HEAVY-TIMBER': {'mass': 0.50, 'expression': 0.90},
    'FRM-MASS-TIMBER':  {'mass': 0.55, 'expression': 0.55},
    'FRM-CONCRETE':     {'mass': 0.95, 'expression': 0.10},
}

# How much each axis counts. `mass` leads because it is the axis with the two clearest
# musical sources behind it, and `incident` trails because `hierarchy` is a single
# measurement carrying it alone.
AXIS_WEIGHTS: dict[str, float] = {
    'mass': 0.34, 'layering': 0.26, 'regularity': 0.24, 'incident': 0.16,
}

# How sharply a decisive axis outweighs a lukewarm one. At 0 this module is back to
# plain averaging and the two grammars nearest the centre of the space win almost every
# track; too high and one axis picks the facade by itself.
DOMINANCE_GAIN = 2.6

# The most `genre_style` may move the mass axis, in either direction. Small on purpose:
# a timbral inference at 0.35 confidence must be able to break a tie between adjacent
# grammars and must never be able to carry a jump from glass to masonry.
GENRE_STYLE_NUDGE = 0.12


def _dimension(score: ArchitecturalScore, name: str, default: float = 0.5) -> float:
    for dimension in score.dimensions:
        if dimension.id == name:
            return float(dimension.value)
    return default


def _decisive(*readings: float) -> float:
    """Of several readings of one quality, return whichever is furthest from neutral.

    An axis assembled by averaging two dimensions inherits the problem the dominance
    weighting exists to solve, one level further down: the mean of two mid-range numbers
    is more mid-range than either, so an axis built that way can never reach its own
    ends and the grammars positioned there become dead options. Averaging `tension` with
    `1 - continuity` put every one of the fourteen recordings between 0.29 and 0.62 on an
    axis that runs 0 to 1.

    Taking the more decisive reading instead keeps the claim honest and is the same
    architectural principle applied consistently: a piece with an enormous dynamic range
    earns a massive facade even if it is also continuous, and a radically discontinuous
    piece earns one even if its dynamics are flat. Neither quality gets talked out of
    its consequence by the other being unremarkable.
    """
    return max(readings, key=lambda value: abs(value - 0.5))


def read_axes(score: ArchitecturalScore) -> list[AxisReading]:
    """Place the project on the four axes, from the score alone.

    Each mapping is stated as a claim a reader can disagree with, which is the point of
    writing them down rather than tuning them silently.
    """
    tension = _dimension(score, 'tension_release')
    continuity = _dimension(score, 'continuity')
    polyphony = _dimension(score, 'polyphony')
    repetition = _dimension(score, 'repetition')
    hierarchy = _dimension(score, 'hierarchy')
    genre = _dimension(score, 'genre_style')

    # genre_style runs bright-and-percussive (1.0) to dark-and-sustained (0.0). Dark and
    # sustained material reads as mass; the nudge is bounded so it can only settle a
    # close call.
    nudge = (0.5 - genre) * 2.0 * GENRE_STYLE_NUDGE
    mass = min(1.0, max(0.0, _decisive(tension, 1.0 - continuity) + nudge))

    return [
        AxisReading(
            axis='mass', value=round(mass, 4),
            sources=['tension_release', 'continuity', 'genre_style (nudge only)'],
            reason='A wide dynamic range asks the elevation to hold a strong contrast '
                   'between solid and void, and a discontinuous piece asks it to be '
                   'broken rather than uniform. Both push toward wall over glass. The '
                   'timbral reading nudges this by at most '
                   f'{GENRE_STYLE_NUDGE:.2f} and never selects on its own.'),
        AxisReading(
            axis='layering', value=round(polyphony, 4), sources=['polyphony'],
            reason='Independent simultaneous strands ask to be read separately, which '
                   'on an elevation means a second structure standing off the first '
                   'rather than one skin doing all the work.'),
        AxisReading(
            axis='regularity', value=round(repetition, 4), sources=['repetition'],
            reason='Material that returns on a fixed period asks for a strict module; '
                   'material that never returns asks for a composed elevation.'),
        AxisReading(
            axis='incident', value=round(hierarchy, 4), sources=['hierarchy'],
            reason='A piece with one dominant event wants one dominant event on the '
                   'facade; an even piece wants an even field.'),
    ]


def choose_envelope(reading: dict[str, float]) -> tuple[str, list[str]]:
    """Pick an envelope tectonic by design reasoning, and return the reasoning.

    The first three versions of this function looked for the nearest option in the
    four-dimensional axis space, and each one collapsed onto whichever grammar happened
    to sit closest to the middle of the corpus: first `ENV-PANEL-FIELD` and
    `ENV-FACETED-PANEL` took ten of fourteen tracks, then `ENV-EXPRESSED-FRAME` took
    seven. Sharpening the weights only moved the winner. That is not a tuning problem
    with a better constant behind it -- nearest-neighbour selection over a fixed option
    set always concentrates on the options nearest the data's centre of mass, and the
    grammars at the corners of the space stay unreachable however the metric is scaled.

    Worse, tuning the constants against fourteen recordings is the overfitting the audio
    calibration went to some trouble to avoid, applied this time to architectural
    positions that have no business being fitted to a corpus at all.

    So the choice is made the way it is actually made in practice: as a short sequence
    of discrete questions, each one asked against a single axis at full resolution. Is
    this a wall or a frame? Does a second structure stand in front of it? Is the
    composition modular or driven by one event? Every leaf is reachable whenever the
    combination that leads to it occurs, no leaf can be crowded out by its neighbours,
    and the thresholds are legible as design reasoning rather than as coefficients.
    """
    mass = reading['mass']
    layering = reading['layering']
    regularity = reading['regularity']
    incident = reading['incident']
    why: list[str] = []

    if mass >= 0.62:
        why.append(f'mass {mass:.2f} >= 0.62: the elevation is a wall, not a frame')
        if incident >= 0.55 and regularity < 0.52:
            why.append(f'incident {incident:.2f} high against regularity '
                       f'{regularity:.2f} low: one dominant event, composed rather '
                       f'than modular')
            return 'ENV-APPLIED-ORDER', why
        if mass >= 0.80 and layering < 0.42:
            why.append(f'mass {mass:.2f} >= 0.80 with layering {layering:.2f} < 0.42: '
                       f'a single surface, so the opening becomes an incision in it')
            return 'ENV-BLANK-SLOT', why
        why.append('a wall with a regular row of openings cut through it')
        return 'ENV-PUNCHED-WALL', why

    why.append(f'mass {mass:.2f} < 0.62: the elevation is a framed or layered skin')
    if layering >= 0.60:
        why.append(f'layering {layering:.2f} >= 0.60: a second structure stands in '
                   f'front of the skin')
        if regularity >= 0.58:
            why.append(f'regularity {regularity:.2f} >= 0.58: that structure is a '
                       f'strict grid, deep enough to read as shadow')
            return 'ENV-DEEP-LATTICE', why
        why.append(f'regularity {regularity:.2f} < 0.58: the outboard layer varies '
                   f'along an axis instead of repeating')
        return 'ENV-PANEL-FIELD', why

    why.append(f'layering {layering:.2f} < 0.60: one skin does the work')
    if regularity >= 0.58:
        why.append(f'regularity {regularity:.2f} >= 0.58: a strict module, so the '
                   f'elevation is a grid')
        return 'ENV-CURTAIN-WALL', why
    if regularity < 0.34:
        why.append(f'regularity {regularity:.2f} < 0.34: nothing returns on a period, '
                   f'so the skin is cut by seams that ignore the structural grid')
        return 'ENV-FACETED-PANEL', why
    why.append(f'regularity {regularity:.2f} in between: neither a strict grid nor a '
               f'composed one, so the frame itself is left to read as the elevation')
    return 'ENV-EXPRESSED-FRAME', why


def choose_frame(reading: dict[str, float]) -> tuple[str, list[str]]:
    """Pick a frame tectonic by the same kind of reasoning.

    The concrete branch leads because it is the heaviest and the most monolithic, and
    it was unreachable until the ACI 318 checks existed: writing the tree while the
    system was screened out left a leaf with nothing routing to it, which is the same
    silent dead option the nearest-neighbour selector used to produce. A branch added
    for a capability that does not exist yet is a branch that quietly never fires.
    """
    mass, expression = reading['mass'], reading['expression']
    why: list[str] = []
    if mass >= 0.66 and expression < 0.48:
        why.append(f'mass {mass:.2f} with expression {expression:.2f}: weight carried '
                   f'monolithically, by a frame that shows no joints because it has '
                   f'none to show')
        return 'FRM-CONCRETE', why
    if expression >= 0.58:
        why.append(f'expression {expression:.2f} >= 0.58: material that transforms '
                   f'between sections asks for a frame that shows how it is joined')
        return 'FRM-HEAVY-TIMBER', why
    if mass >= 0.46:
        why.append(f'mass {mass:.2f} >= 0.46 with expression {expression:.2f} low: '
                   f'weight carried by broad panels rather than by slender members')
        return 'FRM-MASS-TIMBER', why
    why.append(f'mass {mass:.2f} < 0.46: the lightest vocabulary, rolled sections and '
               f'diagonal bracing')
    return 'FRM-STEEL', why


def select_massing(score: ArchitecturalScore
                   ) -> tuple[MassingFamily, str, list[str]]:
    """Choose the silhouette and the brief from the score alone, in that order.

    Both run before `build_lattice`, which is why neither can use the screen: there is
    no building yet to screen. That ordering is not a compromise -- a footprint is the
    first decision, and asking whether a system can carry it is a question about a
    building that already has one.

    Massing leads and constrains typology rather than the other way round, because a
    single low volume can only hold a pavilion brief whatever the music says about
    dominant events. Where the massing has already settled it, `choose_typology` says
    so instead of inventing an independent reason.
    """
    reading = {a.axis: a.value for a in read_axes(score)}
    density = _dimension(score, 'density')
    family, why = choose_massing(reading, density, _dimension(score, 'tempo_of_change'))
    typology, typology_why = choose_typology(reading, density, family.id)
    return family, typology, why + typology_why


def _grammar_for_envelope(envelope_id: str, reading: dict[str, float]) -> str:
    """Name the grammar that builds this tectonic.

    Two tectonics are built by more than one grammar. `ENV-PANEL-FIELD` is shared by
    Organic and Parametricism, and there the choice is real rather than cosmetic: they
    compose the same field along different axes, so a project with one dominant event
    gets the radial bloom around the entrance and an even one gets the vertical
    gradient. `ENV-CURTAIN-WALL` is shared by International Style and Bauhaus, and no
    measurement in this pipeline separates them; the first in identifier order is taken
    so the result stays deterministic, and pretending to distinguish them would be an
    invented reading.
    """
    if envelope_id == 'ENV-PANEL-FIELD':
        return ('FCD-04-ORGANIC' if reading['incident'] >= 0.5
                else 'FCD-10-PARAMETRICISM')
    return next(g for g in sorted(GRAMMAR_ENVELOPE)
                if GRAMMAR_ENVELOPE[g] == envelope_id)


def dominance_weights(reading: dict[str, float],
                      base: dict[str, float]) -> dict[str, float]:
    """Let the axis the music is most decisive about carry the choice.

    Averaging four moderate readings is what made the first version of this module
    choose the same two grammars for almost every recording. The arithmetic is
    unavoidable: an option sitting near the middle of the space is close to *every*
    mid-range reading, so `ENV-PANEL-FIELD` and `ENV-FACETED-PANEL` won ten of fourteen
    tracks and the four grammars at the corners -- the blank plane, the punched wall,
    the curtain wall, the deep screen -- were unreachable. Fourteen buildings that
    differed only between two skins would have been the original complaint again with a
    smaller number attached.

    The correction is architectural rather than numerical. A building takes its identity
    from whatever the music is most decisive about, not from the average of four things
    it is lukewarm about. So an axis is weighted by how far the reading sits from the
    midpoint: a piece that is emphatically continuous and emphatically monolithic gets a
    facade chosen on those two, and one that is moderate everywhere keeps a moderate
    facade, which is the right answer for it.
    """
    return {axis: weight * (1.0 + DOMINANCE_GAIN * abs(reading[axis] - 0.5) * 2.0)
            for axis, weight in base.items()}


def _affinity(position: dict[str, float], reading: dict[str, float],
              weights: dict[str, float]) -> float:
    """1.0 when the option sits exactly where the music placed the project."""
    weights = dominance_weights(reading, weights)
    total = sum(weights[axis] for axis in weights)
    distance = sum(weights[axis] * abs(position[axis] - reading[axis])
                   for axis in weights)
    return round(1.0 - distance / total, 4)


def live_demand(
    base: ProgramDemand, datums: DatumSet, lattice: Lattice,
    allocation: ProgramAllocation,
) -> ProgramDemand:
    """The screening demand as this score actually built it.

    Screening against the canned brief would have asked the same question of every
    recording. The storey count, the height and the clear span are all things the datum
    chain just decided, so the screen is given those instead: a score that stacks nine
    levels genuinely does rule out timber, and a score that stacks three genuinely does
    not. This is what makes the logic chain continuous rather than two chains that
    happen to run beside each other.
    """
    storeys = max(1, len(lattice.occupied))
    height = max(3.0, lattice.levels[-1].z)
    span = max(datums.value('bay_x_m'), datums.value('bay_y_m'))
    return base.model_copy(update={
        'storey_count': storeys,
        'building_height_m': round(height, 3),
        'max_clear_span_m': round(max(span, base.max_clear_span_m * 0.5), 3),
    })


def select_project(
    score: ArchitecturalScore, datums: DatumSet, lattice: Lattice,
    allocation: ProgramAllocation, *,
    program_id: str = 'PRG-LIBRARY-MID-RISE',
    typology: str | None = None,
    jurisdiction: JurisdictionProfile = UNRESOLVED_JURISDICTION,
    massing: MassingFamily | None = None,
    massing_why: list[str] | None = None,
) -> tuple[SelectionRecord, FeasibleDomain]:
    """Choose one (system, grammar) pair the music prefers and the screen permits."""
    base = program_by_id(program_id)
    demand = live_demand(base, datums, lattice, allocation)
    domain = screen_project(demand, jurisdiction=jurisdiction)

    axes = read_axes(score)
    reading = {a.axis: a.value for a in axes}

    # --- what the music would choose, ignoring every screen -----------------------
    frame_reading = {'mass': reading['mass'],
                     'expression': _dimension(score, 'variation')}
    frame_weights = {'mass': 0.6, 'expression': 0.4}

    wanted_envelope, envelope_why = choose_envelope(reading)
    wanted_frame, frame_why = choose_frame(frame_reading)
    preferred_grammar = _grammar_for_envelope(wanted_envelope, reading)
    preferred_system = next(
        (s for s, e in SYSTEM_BUILDABILITY.items() if e.frame_tectonic == wanted_frame),
        'STR-SYS-STEEL-FRAME')

    # --- what survives every screen ----------------------------------------------
    # Three independent filters, none of which consults the music: the physical and
    # code screens from `screen_project`, and whether this compiler can emit the
    # system at all.
    buildable = set(buildable_systems())
    options = [o for o in domain.feasible if o.system_id in buildable]

    if not options:
        # The screen has removed everything this compiler can build. Falling back to
        # steel keeps the run alive, and the record says plainly that it is a fallback.
        options = [o for o in domain.feasible if o.system_id == 'STR-SYS-STEEL-FRAME']

    if options:
        exact = [o for o in options if o.grammar_id == preferred_grammar
                 and o.system_id == preferred_system]
        same_grammar = [o for o in options if o.grammar_id == preferred_grammar]
        if exact:
            best, note = exact[0], (
                'The screen admitted exactly what the music asked for.')
        elif same_grammar:
            # Keep the facade the design reasoning arrived at and take the closest
            # admissible frame under it, because the grammar is what the eye reads.
            best = max(same_grammar, key=lambda o: (
                _affinity(FRAME_POSITION[SYSTEM_BUILDABILITY[o.system_id]
                                         .frame_tectonic], frame_reading,
                          frame_weights), o.system_id))
            note = ('The grammar the music asked for was admissible; its preferred '
                    'frame was not, so the nearest admissible frame carries it.')
        else:
            best = max(options, key=lambda o: (
                _affinity(ENVELOPE_POSITION[GRAMMAR_ENVELOPE[o.grammar_id]], reading,
                          AXIS_WEIGHTS) * 0.68
                + _affinity(FRAME_POSITION[SYSTEM_BUILDABILITY[o.system_id]
                                           .frame_tectonic], frame_reading,
                            frame_weights) * 0.32,
                o.system_id, o.grammar_id))
            note = ('The grammar the music asked for was not admissible on any system '
                    'this compiler can build; the closest admissible option stands in '
                    'its place and the overrule is recorded.')
        system_id, grammar_id = best.system_id, best.grammar_id
    else:
        system_id, grammar_id = 'STR-SYS-STEEL-FRAME', 'FCD-01-INTERNATIONAL-STYLE'
        note = ('No admissible option this compiler can build. The run continues on '
                'the steel frame and the curtain wall so the failure is visible as a '
                'building rather than as an exception, and this note is the record '
                'that nothing was actually selected.')
    note = note + ' Reasoning: ' + '; '.join(envelope_why + frame_why) + '.'

    # --- runner-up, so the margin is legible --------------------------------------
    ranked = sorted(
        {o.grammar_id for o in options},
        key=lambda g: -_affinity(ENVELOPE_POSITION[GRAMMAR_ENVELOPE[g]], reading,
                                 AXIS_WEIGHTS))
    runner_up = next((g for g in ranked if g != grammar_id), None)
    grammar_affinity = _affinity(ENVELOPE_POSITION[GRAMMAR_ENVELOPE[grammar_id]],
                                 reading, AXIS_WEIGHTS)
    margin = (round(grammar_affinity
                    - _affinity(ENVELOPE_POSITION[GRAMMAR_ENVELOPE[runner_up]],
                                reading, AXIS_WEIGHTS), 4)
              if runner_up else None)

    overruled = (system_id != preferred_system) or (grammar_id != preferred_grammar)
    overrule_reason = None
    if overruled:
        parts = []
        if system_id != preferred_system:
            entry = SYSTEM_BUILDABILITY[preferred_system]
            if not entry.implemented:
                parts.append(f'{preferred_system} is not emitted by this compiler: '
                             f'{entry.reason}')
            else:
                gates = next((o.failed_gates + o.blocking_rules
                              for o in domain.physically_infeasible + domain.excluded
                              if o.system_id == preferred_system), [])
                parts.append(f'{preferred_system} did not survive the screen'
                             + (f' ({", ".join(gates[:3])})' if gates else ''))
        if grammar_id != preferred_grammar:
            parts.append(f'{preferred_grammar} was not available on an admissible '
                         f'system for this demand')
        overrule_reason = '; '.join(parts)

    # Every admissible pair this compiler can build, best first. The compiler walks
    # this when the preferred frame turns out not to be sizeable, so a correct
    # engineering refusal becomes a recorded fallback instead of a crash.
    def _rank(option) -> float:
        return round(
            _affinity(ENVELOPE_POSITION[GRAMMAR_ENVELOPE[option.grammar_id]], reading,
                      AXIS_WEIGHTS) * 0.68
            + _affinity(FRAME_POSITION[SYSTEM_BUILDABILITY[option.system_id]
                                       .frame_tectonic], frame_reading,
                        frame_weights) * 0.32, 4)

    ranked = [RankedOption(system_id=o.system_id, grammar_id=o.grammar_id,
                           affinity=_rank(o)) for o in options]
    ranked.sort(key=lambda o: (-o.affinity, o.system_id, o.grammar_id))
    # the option actually chosen leads, whatever its raw affinity
    ranked.sort(key=lambda o: (o.system_id, o.grammar_id) != (system_id, grammar_id))

    # The building's typology and the *screening* typology are allowed to differ, and
    # for the pavilion they do: `coupling.ProgramDemand` classifies it as a museum
    # because that is its occupancy group for code purposes, which is the right call
    # for a screen and the wrong label for a building. The brief decides what this is.
    record = SelectionRecord(
        ranked_options=ranked,
        massing_id=massing.id if massing else 'MAS-SLAB',
        massing_label=massing.label if massing else 'Stacked slab',
        massing_reason=list(massing_why or []),
        program_id=program_id, typology=typology or demand.typology,
        system_id=system_id, grammar_id=grammar_id,
        frame_tectonic_id=SYSTEM_BUILDABILITY[system_id].frame_tectonic or 'FRM-STEEL',
        envelope_tectonic_id=GRAMMAR_ENVELOPE[grammar_id],
        preferred_system_id=preferred_system, preferred_grammar_id=preferred_grammar,
        overruled_by_screen=overruled, overrule_reason=overrule_reason,
        axes=axes, grammar_affinity=grammar_affinity,
        system_affinity=_affinity(
            FRAME_POSITION[SYSTEM_BUILDABILITY[system_id].frame_tectonic or 'FRM-STEEL'],
            frame_reading, frame_weights),
        runner_up_grammar_id=runner_up, runner_up_margin=margin,
        admissible_systems=sorted({o.system_id for o in domain.feasible}),
        admissible_grammars=sorted({o.grammar_id for o in domain.feasible}),
        unbuildable_systems={s: e.reason for s, e in SYSTEM_BUILDABILITY.items()
                             if not e.implemented},
        jurisdiction_resolved=domain.jurisdiction_resolved, note=note)
    return record, domain
