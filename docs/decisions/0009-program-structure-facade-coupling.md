# Decision 0009 — Program–Structure–Facade Coupling, Code Screening, and Sized Optimisation

- Status: proposed; implemented and tested, pending jurisdiction resolution
- Date: 2026-08-29
- Decision owner: user
- Career-value tags: V1, V2, V3, V4
- Implementation: `backend/app/codes.py`, `coupling.py`, `sections.py`, `loads.py`,
  `sizing.py`, `optimizer.py`
- Evidence: `backend/tests/test_coupling_and_sizing.py` (40 tests),
  `artifacts/coupling/`

## Decision

Typology, structural system, and facade grammar stop being three independent selections.
They become one chain with four layers, and the layers are kept **structurally separate**
so that no layer can quietly overrule another.

```text
typology constitution + brief          decisions 0001, 0004
        |
        v
  ProgramDemand
        |   gate 1: hard gates eliminate; soft axes only describe
        v
 StructuralSupply                      decision 0002, structural_systems/
        |   gate 2: hard gates eliminate; soft axes only describe
        v
  FacadeDemand                         decision 0003, style_guides/facade/
        |
        +--- code layer: screens, never scores      IBC / ASCE 7
        |
        v
   feasible domain
        |
        +--- load calculation: ASCE 7 + AISC 360 / NDS
        |
        v
   feasibility map + genetic search inside the legal datum box
        |                                    the score proposes, the GA negotiates,
        |                                    cost is not yet a criterion
        |
        v
   adopted datums -> registration lattice -> elements     decision 0008
```

Five rules govern the whole chain:

1. **This is an elimination stage, not a selection stage.** The job is to rule out what
   is absolutely impossible. Choosing among what survives is a later question with its
   own criteria, and no layer here may pre-empt it.
2. **Only hard standards eliminate.** Physical hard gates and building-code gates remove
   options. Soft axes have no elimination power: an accumulation of small penalties can
   never remove a physically possible and lawful option.
3. **Compatibility is computed from declared physical quantities**, never from a
   hand-authored opinion matrix. Any elimination can be explained by naming the axis or
   the code rule that removed it, and the number that failed.
4. **Structural claims come from a load calculation**, not from a rule of thumb. Section
   properties are computed from geometry; capacities follow AISC 360 LRFD and NDS ASD.
5. **Cost is not a criterion yet.** `material_efficiency` is a cost proxy and is
   switched off by default, because letting steel tonnage into the objective would
   quietly answer the selection question with "the cheapest one".

### Three statements that are never merged into one number

| | Produced by | Kind | May eliminate? | May rank? |
|---|---|---|---|---|
| `admissibility` | building-code gates | lawful / not | **yes** | no |
| `feasibility` | physical hard gates | possible / not | **yes** | no |
| `resolution_burden` | soft axes | how much detailing is left | **no** | **no** |

`resolution_burden` runs 0.00 (nothing left to detail) to 1.00 (every axis needs work)
and is banded as `clean` / `minor_interfaces` / `significant_interfaces` /
`many_interfaces`. Those are descriptions of effort, not quality tiers. The feasible set
is returned in identifier order, never sorted by burden, so the presentation itself
carries no preference.

---

## Part 1 — The coupling interface

Three participants, each publishing what it needs or offers. Nothing else crosses the
boundary.

| `ProgramDemand` | `StructuralSupply` | `FacadeDemand` |
|---|---|---|
| storey count, height | provides occupied floor plates, max storeys / height | areal mass range |
| max clear span + governing space | ordinary and long-span reach | accepted backup types |
| peak floor live load + governing space | floor load capacity | max support spacing |
| acoustic separation required | acoustic separation support | deflection limit L/n |
| humidity control required | humidity tolerance | panel geometry class |
| min construction class | construction class | facade depth zone |
| occupancy group (derived) | envelope mass capacity, backup types offered, hardpoint spacing, deflection delivered, host surface class, envelope depth, barrier continuity | barrier continuity required, opening ratio range, combustible cladding |

The registries live in `coupling.py` and every value carries a `source_ref` back to the
guide it was read from. The guides remain the source of truth; the module is their
machine projection.

## Part 2 — Physical axes and weights

### Gate 1 — program → structure

Weights apply only inside the burden description. The hard-gate column is what
eliminates.

| Axis | Weight | Hard gate | What it catches |
|---|---:|:---:|---|
| `floor_plates` | 0.22 | ✔ | a covering system asked to be a building |
| `storey_count` | 0.20 | ✔ | material height limits |
| `clear_span` | 0.20 | ✔ | span beyond even the long-span subtype |
| `floor_load` | 0.15 | ✔ | stacks, archives, stages |
| `acoustic_separation` | 0.10 | | auditorium isolation |
| `construction_class` | 0.08 | | combustibility versus occupancy |
| `humidity_control` | 0.05 | | collection care versus timber |

`floor_plates` is the sharpest rule in the chain and it is the reason a tall building
cannot be a tensile membrane. The decisive fact is not height: **a membrane and a shell
do not make occupied floors at all.** A multi-storey building on one of them is really
two systems, and the honest answer is to say so rather than pretend the roof is the
building.

### Gate 2 — structure → facade

| Axis | Weight | Hard gate | What it catches |
|---|---:|:---:|---|
| `deflection` | 0.25 | ✔ | stiffness mismatch — the axis designers miss |
| `areal_mass` | 0.20 | ✔ | the envelope is heavier than the backup can carry |
| `backup_type` | 0.15 | ✔ | a rigid envelope with nothing rigid behind it |
| `panel_geometry` | 0.15 | | flat glass on a doubly curved host |
| `support_spacing` | 0.10 | | the module needs a subframe |
| `barrier_continuity` | 0.10 | | the structure cannot carry the barrier |
| `envelope_depth` | 0.05 | | the facade zone does not exist |

Deflection carries the largest weight because **strength is not stiffness**. A structure
strong enough to hold a panel can still move far more than the panel's joints tolerate.

Both hard-gated axes with a range are **two-tier**, so the report distinguishes
"impossible" from "only at the light end of your palette":

- `areal_mass` blocks on the grammar's *lightest* legal material and scores on its
  *heaviest*.
- `IBC-705.8` blocks on the grammar's *lowest* opening ratio and clamps on its *highest*.

Aggregation is a **weighted geometric mean**, not arithmetic, so one very bad axis stays
visible instead of being averaged away by six comfortable ones. It is reported inverted,
as a burden, precisely so it does not read as a score. Nothing filters on it.

### The worked example, generalised

Burden shown for pairs that survive; `OUT` for pairs a hard gate removes.

| | tensile membrane | cable net | mass timber | RC frame |
|---|---|---|---|---|
| Brutalism (280–500 kg/m², L/480) | **OUT** | **OUT** | 0.38 | 0.01 |
| International Style (50–90, L/175) | **OUT** | 0.43 | 0.05 | 0.00 |
| Parametricism (20–150, L/240) | **OUT** | 0.46 | 0.03 | 0.02 |

Brutalism on a membrane fails three independent hard gates at once — mass (280 against 5),
stiffness (L/50 against L/480), and backup type (a moving edge against a required bearing
wall). Nothing hangs on a membrane, because the membrane *is* the envelope. A cable net
carries the light grammars and refuses the heavy ones, which is what Munich did.

## Part 3 — The code layer

Physical axes say "this is hard to build". Code gates say "this may not be built". They
are different kinds of statement and are never merged into one number.

| Rule | Citation | Catches |
|---|---|---|
| `IBC-504-CONSTRUCTION-TYPE` | IBC Tables 504.3, 504.4 | material versus storeys and height for the occupancy group |
| `IBC-601-FRAME-RATING` | IBC Table 601 | whether the frame may be left exposed at all |
| `IBC-705.8-OPENING-AREA-<face>` | IBC Table 705.8 | glazing ratio versus fire separation distance, per elevation |
| `IBC-1402-NFPA285` | IBC 1402, 1405 | combustible cladding above 12.2 m on Type I–IV |
| `ASCE7-12.2-SEISMIC-SYSTEM` | ASCE/SEI 7 Table 12.2-1 | lateral system permitted and capped by seismic design category |
| `IBC-1604.3-DEFLECTION` | IBC Table 1604.3 | the deflection limits the facade axis must use |

Three properties make this layer honest:

**It screens, it does not select.** `combined_weight` is computed identically whether or
not the code layer ran. A code failure cannot lower a physical weight, and a high physical
weight cannot rescue an inadmissible option. The test
`test_code_layer_does_not_change_any_physical_weight` enforces it.

**A placeholder table can fail a design but can never clear one.** The numeric tables
shipped in `codes.py` are project-authored placeholders. A rule evaluated against them
returns `code_inputs_incomplete`, never `pass`. Only a `JurisdictionProfile` with
`status='resolved'` can produce a `pass`, so the data model makes a compliance claim
unreachable until a human supplies real code data.

**An exclusion made on unverified data is marked as such.** A blocking rule with
placeholder provenance yields `provisionally_excluded`, never `excluded`. Removing a
design option on unsourced code data would be a real architectural decision taken on data
the project has not yet gathered.

### What the code layer actually does to a design

Example jurisdiction: sprinklered Group A-3, SDC D, north face 2.0 m to the lot line.

| Effect | Rule | Result |
|---|---|---|
| glazed grammars die on the north face | `IBC-705.8` | International Style, Bauhaus, High-tech, Deconstructivism, Minimalism, Parametricism excluded; Brutalism, Postmodernism, Critical Regionalism, Organic survive because they can go solid |
| the timber tower changes its lateral system | `ASCE7-12.2` | CLT shear walls run out of height at 26 m in SDC D, so the mass timber building must adopt a concrete core — a different building, stated out loud |
| exposed structure may not survive | `IBC-601` | a required frame rating forces encapsulation, and the material the designer chose for its appearance becomes invisible |

That first row is the point of the whole layer: a lot-line offset, not a stylistic
preference, is what removes the fully glazed grammars from this site.

## Part 4 — Load calculation

Nothing in the sizing path is fitted, regressed, or quoted from memory.

- **Section properties are computed from geometry** (`sections.py`). No catalogue values
  are reproduced. `test_i_section_properties_match_hand_calculation` checks area, `Ix`,
  `Sx`, `Zx`, and `rx` against the closed-form expressions.
- **Dead load is built up from the modelled assembly** (`loads.py`), so changing the deck,
  topping, or finish propagates. The composite deck used here is 3.92 kPa superimposed.
- **Live loads are the ASCE/SEI 7 occupancy minima.** Library stack rooms are 7.18 kPa and
  are non-reducible, except that a member supporting two or more floors may take 20 %.
- **Combinations** are the governing gravity LRFD pair, `1.4D` and `1.2D + 1.6L + 0.5Lr`.
- **Capacities** follow AISC 360 LRFD for steel (`φMn = 0.9 Fy Zx` with a compactness
  check, `φVn`, and E3 flexural buckling with both branches) and NDS ASD for glulam
  (`Fb S`, and the 3.7.1 column stability factor `C_P`).
- **Serviceability** uses IBC Table 1604.3: L/360 live and L/240 total for floors.

Declared assumptions, recorded on every `MemberCheck`: simple spans, uniform gravity only,
continuously braced compression flanges, `K = 1.0`, no connections, no fire protection, no
lateral load. Every result is `professional_review_required`.

Reference run — six storeys, 36 × 22 m, library stacks:

```text
SZ-JOIST    I-350x175x7x11   governed by total deflection   0.96
SZ-GIRDER   I-400x200x8x13   governed by flexure            0.78
SZ-COLUMN   SHS-400x400x8    governed by compression        0.91
column axial 3318 kN with a 0.80 live load reduction
52.4 kg/m2 over 4752 m2
```

Deflection governing the joist and roughly 50 kg/m² of steel are both what a steel-framed
library of this load class should produce, which is the sanity check that matters.

## Part 5 — Genetic search, and the reason it cannot be pure optimisation

The GA moves the datums — `bay_x`, `bay_y`, `joist_spacing`, `floor_to_floor` — inside the
legal ranges published by the structural system guideline, and reports the best compromise.

**The design decision that matters:** a pure "minimise steel" objective always wins by
collapsing the building toward the cheapest frame, and the music becomes decoration bolted
onto a result it did not influence. So `score_fidelity` is a first-class objective with the
largest weight. Every metre the optimiser moves a datum away from the value the score
proposed costs it fitness.

**Elimination-stage weights** (`ObjectiveWeights.elimination_stage()`, the default):

| Objective | Weight | Meaning |
|---|---:|---|
| `score_fidelity` | 0.45 | distance from the datum the architectural score proposed |
| `constructability` | 0.30 | bays on a 0.3 m module, whole-number joist divisions, bay aspect near 1:1 |
| `utilisation` | 0.25 | members working in the 0.75–0.92 band, neither wasteful nor at the limit |
| `material_efficiency` | **0.00** | steel intensity — a **cost proxy, switched off** |

`material_efficiency` is still computed and reported, so the number is visible, but it
carries no weight. Turning it on requires `ObjectiveWeights.selection_stage()`, which
scales the other three down proportionally so that introducing cost does not silently
change the relative importance of intent, buildability, and utilisation. That switch
should only be thrown once the project has written down what it is selecting for.

### Feasibility mapping — the elimination-stage use of the search space

`map_feasible_region()` sweeps the legal datum box on a deterministic lattice and asks
only "does a workable design exist here, and where". No optimisation, no ranking, no
cost. It answers a question a single-point check cannot:

```text
as briefed:                      broad,  1296/1296 (100%)  proposal feasible: True
with a 350 mm beam depth limit:  narrow,  132/1296 ( 10%)  proposal feasible: False
    bay_x_m: legal 5.6-9.0 m, feasible only 5.6-6.28
    bay_y_m: legal 5.6-9.0 m, feasible only 5.6-7.64
    binding: girder 1080, joist 720
```

A structural system whose legal datum range contains **no** feasible design for this
program is ruled out on a hard standard. A system that only works in a corner of its own
range has been narrowed by physics, and the designer needs to see that before choosing.

The population is seeded with the score's own proposal, so the search can never return a
worse building than the brief. The RNG is seeded and the settings fixed, so a score
reproduces a genome — the project's repeatability gate depends on it.

Reference run, 2 380 evaluations in 1.6 s:

```text
verdict: improved
  bay_x_m           score proposed 6.52, adopted 6.60   moved +0.08 m
  bay_y_m           score proposed 7.12, adopted 6.90   moved +0.22 m
  joist_spacing_m   score proposed 1.96, adopted 2.00   moved +0.04 m
  floor_to_floor_m  score proposed 4.72, adopted 4.80   moved +0.08 m
  score_fidelity 0.959   utilisation 1.000   constructability 0.925
  material_efficiency 0.508  (reported, weight 0 - deferred to the selection stage)
```

The music's proposal is **held**, nudged by at most 0.22 m onto a clean module, while steel
falls 15 % and every member lands in the target utilisation band. Re-run with a tight-bay
score proposal, the optimiser keeps the tight bays. That is a negotiation with a visible
exchange rate, not an optimisation that overrules the brief, and
`test_a_different_score_proposal_produces_a_different_building` holds it to that.

## Part 6 — Where this plugs into the existing decisions

| Decision | Effect |
|---|---|
| 0001 typology | supplies `ProgramDemand`; occupancy group is derived from it |
| 0002 tectonic N-choose-1 | Gate B now has a computed elimination screen. It narrows the ten systems to those that are lawful and possible; Gate C's selection criteria remain unwritten and this module supplies none of them |
| 0003 facade grammars | the two-grammar experiment must be selected from the admissible set, not from the ten |
| 0004 score contract | the score proposes datum values; it never sets a capacity, a limit, or a code parameter |
| 0007 pipeline manifest | the feasible domain and the optimiser run become artifacts with hashes and authority |
| 0008 element taxonomy | the adopted datums are the input to the registration lattice |

The compile-time use is a validation gate: a `building_model_v2` whose datums fall outside
the admissible domain, or whose members fail a sizing check, is a `fail` with the axis and
the number named.

## Part 7 — Limitations

- **Gravity only.** No wind, no seismic force, no snow drift, no ponding, no notional
  lateral load, no second-order effects. The seismic gate checks system permission and
  height limits; it does not compute a base shear.
- **The numeric code tables are placeholders.** Their structure is real and the citations
  are real; the numbers require the adopted edition and local amendments. Until then no
  run may say `code_compliant`.
- **Steel is sized fully; glulam and CLT are sized at member level; concrete is not.**
  Reinforced concrete uses geometric rules only and its sizing status stays `unresolved`.
- **No connections, no fire protection, no vibration, no torsion, no lateral-torsional
  buckling.** The bracing assumption must be matched by a modelled bracing element.
- **The GA finds a relative optimum in a four-dimensional box**, seeded and deterministic.
  It is not a global optimum, not a Pareto front, and not a substitute for judgement.
- The registries in `coupling.py` are read from the guides by hand. They must be
  re-derived whenever a guide's ranges change; nothing enforces that link yet.
- **There is no selection criterion in this decision.** It produces a feasible domain and
  an elimination log. What makes one surviving option better than another — architectural
  ambition, portfolio evidence, buildability under a real budget, programme — is a
  separate decision the project has not written. Anyone tempted to sort the feasible set
  by `resolution_burden` and call the top row a recommendation is making that decision by
  accident.
