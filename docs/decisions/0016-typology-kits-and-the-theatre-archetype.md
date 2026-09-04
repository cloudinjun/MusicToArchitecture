# Decision 0016 — Typology kits, and the archetype layer the theatre proves

- Status: kit registry implemented; theatre bowl archetype implemented and measured
  (sightline gate, claim gate, colonnade finding, FOH/BOH gate); fly tower and the
  long-span re-frame remain owed
- Date: 2026-09-03
- Decision owner: user (ten-typology expansion planning)
- Career-value tags: V2, V3

## The problem the ten-typology plan exposes

The project wants ten candidate typologies. The program generator alone cannot make
ten *buildings*: it differentiates the room list, the areas and the adjacencies, and
every one of them is then laid out by the same machinery — `level_bands` cuts each
plate into strips, `allocate_program` fills the strips with rectangles. Ten briefs in,
ten arrangements of rectangles out. Decision [0015](0015-a-placement-is-not-a-delivery.md)
fixed the theatre's room *types* (auditorium, stage, their acoustics, their occupant
loads), but the auditorium is still a flat rectangle: no rake, no sightlines, no stage
tower. The type labels arrived; the type geometry did not.

What a typology needs beyond its brief, in this project's terms:

| kit part | exists today | where |
|---|---|---|
| program brief + adjacency | yes | `briefs.py`, `SpaceRequirement.adjacency` |
| structural demand | yes | `coupling.PROGRAM_DEMANDS`, read by the screen |
| acoustic / occupancy semantics | yes (per space type) | `partitions.py`, `constitution.py` |
| spatial archetype | **no** | — |
| sectional rules | **no** (music owns the section) | `datums.py` |
| circulation separation (FOH/BOH) | **no** (egress only) | `life_safety.py` |
| typology-specific gates | mechanism only | `area_tolerance`, `validate_model` |
| drawing profile | **no** | `drawings.py` is one sheet set |

## Part 1 — the kit registry (implemented)

Adding a typology touched four files that failed four different ways when one was
missed, two of them silently: the massing bias had no consumer at all, and the
loading-dock rule was a membership test that does not know what it has never heard of.
`backend/app/typology.py` now assembles one `TypologyKit` per typology at import —
brief, program id, structural demand, massing bias, loading-dock rule — and **raises
naming the typology and the missing part** rather than serving a kit with a hole in it.
The definitions stay in their home modules; the kit is the lookup. A new typology is
one `_SPECS` entry plus exactly the parts the build demands.

Two consumers moved onto the kit: `compiler_v3` takes the program id from it, and
`constitution.support_spaces` asks it whether the typology needs a dock.

## Part 2 — sectional sovereignty (decided here, built with the archetype)

Today the music owns the section: `floor_to_floor_m` from tension release, `void_count`
and `void_scale` from interruption, `ground_open_height_m` from hierarchy. A theatre's
sectional rules cannot *negotiate* with that — a house whose clear height depends on
how interrupted the piece was is not a house.

The rule adopted: **the typology owns the structure of the section; the music modulates
values inside the ranges the typology leaves open.** Concretely:

- The archetype states *sectional claims*: plates removed over the house until its
  clear height is met, a tower volume over the stage, a rake on the house floor. These
  are requirements, not datums, and they win.
- The music keeps every datum it has, evaluated inside typology bounds where the
  typology states one: floor-to-floor may still breathe with tension release, but not
  below the archetype's clear-height claim; interruption still punches its atrium
  voids, but never through a volume an archetype has claimed.
- The translation report says which is which, per value, so a reader can still trace
  every dimension to either the score or the brief — the project's standing claim.

This narrows the "music decides the building" claim and says so deliberately, the same
way `briefs.py` already narrows the typology-from-music claim: the music picks and
modulates; the typology, once picked, is entitled to be itself.

## Part 3 — the archetype layer (built; what the build measured is below)

An archetype is authored type-specific geometry that runs **before** general
allocation and hands the allocator what is left:

1. `carve(lattice, datums, kit)` places the archetype's own volumes — for the theatre,
   the house and the stage as one acoustic mass — and returns their reservations plus
   sectional claims.
2. The existing allocator lays out the rest of the brief around them, exactly as it
   already lays out around cores. `Reservation` must grow a level extent for this: a
   bowl occupies the ground plate but eats the two plates above it, and today a
   reservation applies to every level alike.
3. The archetype then emits its authored geometry into the model — the machinery for
   this exists (`LevelDatum.voids` removes plate; `geometry.py` has the solids; the
   dependency graph hosts them).

The theatre goes first because it stresses every part of the interface:

- **Bowl and rake.** Riser profile derived, not quoted: constant C-value sightline
  (C ≥ 60 mm to a focal point at the stage edge) over ~0.95 m rows gives each riser
  from the one before — first-principles, hand-checkable, in the style of `sections.py`.
  The rake is authored geometry standing on the flat structural plate.
- **Sightline gate.** The C-value the profile was derived from is then *measured* from
  the emitted geometry, per row, as its own validator — derived-then-measured, because
  a status must be earned by a measurement, not by the derivation that promised it.
- **Stage tower.** Grid height over the stage ≈ 2.3 × proscenium height; plates
  removed above the stage; the envelope must rise with it. This is the honest hard
  part: massing families are single prisms per level, and a tower over one bay is
  either a family variant (`MAS-BAR-PODIUM` with a raised bar) or a second prism the
  envelope walks around. Scoped as its own phase; the bowl does not wait for it.
- **FOH/BOH gate.** The audience's rooms and the company's rooms partition the brief
  (`category` already encodes it); the gate fails any route that crosses sides
  anywhere but at the proscenium and the pass door.

The kit grew the `archetype` field (default none — a typology without one allocates
exactly as before); the gates live in `archetypes.evaluate_archetype` and their
report travels on `model.archetype` beside the constitution and the spatial report.

### What building it measured

Three things the design above did not predict, each now a rule:

- **The carve outranks the cores.** The first wiring handed the carver the core
  reservations to dodge, and the cores — placed to maximise egress remoteness —
  kept landing mid-plate where the house must be, until no placement existed. The
  order is now: carve first, then `core_anchors` refuses any site whose core box
  (one formula, `_core_box`, shared with the reservation) stands in carved floor.
  The house is what the building is for; a stair serves it.
- **The house takes the plate's full depth.** Pinned to a 16 m strip, a 680 m²
  house came out 42 m long with the last row 40 m from the proscenium — a corridor
  facing a stage. Depth is the audience's width; the carve takes the deepest row
  run (capped at 33 m) and the band allocator lays the foyer beside the house in
  the same rows, which it could already do.
- **A claim that erases a storey is a demolition, not a section.** On
  `MAS-BAR-PODIUM` the bar stands centred exactly where the house must be: cutting
  the house's clear height out of it leaves the bar's levels at 0–17 % of their
  floor with every room up there stranded. The carver refuses a pairing that guts
  a level (under a quarter of its plate, or under 120 m², left), and the theatre's
  massing bias moved to `MAS-SLAB` — a bias toward a massing the typology's own
  archetype refuses is a trap, not a bias. The bar-podium pairing returns when the
  fly tower gives the bar a reason to stand over the stage.
- **A storey the carve orphans is refused like one it erases.** At its largest
  plate the bar-podium passed the gutting check — the bar kept 42 % of its floor —
  and the life-safety graph then reported that floor with **zero exits**: every
  feasible core site for the run that serves it lay inside the carved house. The
  carver cannot see that, because the core search lives in the compiler; so
  `_carve_and_allocate` runs the search after the carve and converts the carve to
  a refusal when any occupied storey falls outside every stair's run. Measured by
  running the search, not predicted.
- **The carved floor lives on the lattice.** The keep-out was first passed to the
  core search as a parameter, and the two-answers bug this codebase warns about
  arrived within the hour: tests recomputing `core_reservations(lattice, datums)`
  without the parameter disagreed with the model they were checking. It is now
  `Lattice.carved`, written when the carve is applied, so build, emitter and test
  all read one answer.
- **`SP-STANDS-IN-VOID` now measures a share, not a point.** The carve put walls
  where a person would put them — along the void's edge, enclosing the room beside
  the drop — and the centre-point test flagged three of them for touching the
  line. The rule now samples the solid's footprint and fires at 60 % over the
  hole, which keeps the desk-in-the-atrium finding and stops accusing the
  enclosure.

On the slab the theatre now compiles carved: ~20 rows deliver the house at full
area, every row's measured C-value clears 60 mm, the claimed plates are voided, the
spatial rules stay clean — and the columns still standing in the bowl are reported
by `ARCH-CLEAR-SPAN` as the violation they are, because the long-span re-frame the
demand row asks for is not built yet. A true red light, standing where a silent
colonnade used to be. The other standing red is decision 0015's: a full house
demands a fourth exit on its storey and the core system still places cores for
coverage, not for exit count — the carve neither caused nor cures that, and the
life-safety graph goes on reporting it.

## Sequencing, and the selection question

Depth first: theatre bowl → sightline gate → FOH/BOH gate → stage tower; then one
maximally different typology (housing's repeated cells, or the bath's wet sequence) to
prove the interface is not theatre-shaped; only then breadth to ten. Every archetype
heuristic is A/B measured across the corpus before it stays — three of four "obvious"
layout fixes have measured worse in this project, and an archetype is a much bigger
lever than a layout heuristic.

Ten typologies also outgrow `choose_typology`: three scalar readings picking one of
four is defensible; picking one of ten is invented precision. The ten are a candidate
set — the score narrows to a recorded shortlist, and the choice among the shortlist is
a pin (`compile_building_model_v3` already takes one) or a stated default, with the
reasoning on the model as it is today.

## Evidence

- `backend/app/typology.py` — the registry and its build-time gates; the
  `archetype` field.
- `backend/app/archetypes.py` — the carver (`carve_theatre`), the derived rake
  (`derive_bowl`), the refusals, and the measured gates (`evaluate_archetype`).
- `backend/app/program.py` — `carved` / `preplaced` / `precluded` on
  `allocate_program`: floor an archetype has taken, rooms it delivered, rooms it
  refused.
- `backend/app/compiler_v3.py` — `_carve_and_allocate`, `_core_box`, the carve
  keep-out threaded through `core_anchors` / `core_reservations` /
  `_emit_circulation`, the `_emit_archetype` emitter (risers, stage platform,
  proscenium wall), full-height acoustic enclosures in `_emit_partitions`, and the
  ceiling/figure holes over carved floor.
- `backend/app/models_v3.py`, `backend/app/dependencies.py` — three new element
  kinds, hosted; `model.archetype`.
- `backend/tests/test_archetypes.py` — the recurrence checked by hand, the compiled
  slab theatre measured (12 tests), the library unaffected.
- `backend/tests/test_typology.py` — whole-kit gate, loud unknown-typology errors,
  loading-dock parity with the old membership test.
- Compiler version 3.1.0 → 3.2.0: same score now builds different geometry.
- Decisions [0001](0001-primary-typology-shortlist.md),
  [0013](0013-brief-sizes-the-plate.md),
  [0015](0015-a-placement-is-not-a-delivery.md).
