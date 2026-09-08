# Pipeline code review — 2026-09-08

Audience: an agent picking up work on this repository. Every finding below was produced
by running the code, not by reading it. Each one carries the command that reproduces it,
so nothing here has to be taken on trust.

Scope of the pass: cross-component contradictions, values that stop travelling between
producer and consumer, and defensive code that hides a real failure. Read alongside
[`decisions/0024-program-volumes-author-the-form.md`](decisions/0024-program-volumes-author-the-form.md) and
[`evidence_matrix.md`](evidence_matrix.md).

Status values: `confirmed` (reproduced by command), `measured` (a number, not a defect),
`by design` (looks wrong, is not).

| ID | Finding | Severity | Status |
|---|---|---|---|
| CR-01 | Program Volume path fails for `theater`, which is the default typology | blocker | confirmed |
| CR-02 | Facade programme resolution: 3 of 4 sources never deliver; 44% of bays fall back unreported | high | confirmed |
| CR-03 | One transom→member rule implemented twice, with opposite failure behaviour | medium | confirmed |
| CR-04 | 20.9% of the analysis bundle reaches the browser unread | medium | measured |
| CR-05 | 88 of 154 defensive `getattr` guards never used their default | low | measured |
| CR-06 | No machine-readable split between code-mandated and choosable constants | design | measured |
| CR-07 | `v3_mode` dual-track and the `unevaluated` gate verdicts | none | by design |

Environment for every command below:

```bash
cd D:/School/sciarc/ATStudioTwo/MusicToArchitecture
# .venv/Scripts/python.exe on Windows; python on POSIX
```

---

## CR-01 — the Program Volume path fails for `theater` (blocker)

`compile_program_volume_candidate(score)` with no arguments raises:

```
ValueError: ENV-CLOSE-L02-S014 (wall_panel) has invalid physical geometry:
Degenerate direction or repeated member path point
```

**What is wrong with the element.** `ENV-CLOSE-L02-S014` is a `QuadGeometry` whose four
corners collapse to two distinct points — corners 0 and 1 are identical, 2 and 3 are
identical, and all four share one `x` and one `y`:

```
0: (-39.1111, 8.4202,  9.7263)
1: (-39.1111, 8.4202,  9.7263)
2: (-39.1111, 8.4202, 13.6438)
3: (-39.1111, 8.4202, 13.6438)
```

It is a zero-width wall panel: a line, not a surface.

**Where it surfaces vs where it comes from.** It surfaces in
`backend/app/room_fixtures.py:205`, inside `_shape`, which meshes every body to build
placement obstacles. That refusal is **correct and should not be softened** — the defect
is upstream, in whatever subdivided the bay at level L02 to zero width. Do not fix this
by widening the guard in `room_fixtures`.

**Coverage.** Three of four typologies compile; the default one does not:

| typology | Program Volume path |
|---|---|
| library | OK — 12,881 elements |
| museum | OK — 11,831 elements |
| pavilion | OK — 6,346 elements |
| theater | **FAIL** |
| *(no typology argument)* | **FAIL** — the score resolves to `theater` |

**The legacy path is clean.** A degeneracy scan over `compile_building_model_v3` for
`FCD-05-HIGH-TECH`, `FCD-01-INTERNATIONAL-STYLE` and `FCD-03-BRUTALISM` found **0
degenerate bodies** out of 9,432 / 11,746 / 11,627 elements. So this is specific to the
massing the Program Volume path produces, not a general emitter fault.

**Why no test catches it.** The only theater test on this path,
`backend/tests/test_structural_capabilities.py:61`
(`test_incapable_theatre_pin_is_refused_before_emission`), asserts a `pytest.raises`
*refusal before emission* and monkeypatches `_run_sizing` to fail if reached. It never
reaches the envelope. **No test compiles a theater to completion on the Program Volume
path.** That gap is what lets the default entry stay broken.

This matters more than its element count suggests: `backend/app/pipeline.py:132` selects
this path whenever a `project_brief` is supplied, which is the skill/agent entry.

Reproduce:

```python
import json
from backend.app.models import ArchitecturalScore
from backend.app.program_volumes import compile_program_volume_candidate

score = ArchitecturalScore.model_validate(
    json.load(open('artifacts/v3_demo/architectural_score.json', encoding='utf-8')))
for typology in (None, 'library', 'museum', 'pavilion', 'theater'):
    kwargs = {} if typology is None else {'typology': typology}
    try:
        model, _ = compile_program_volume_candidate(score, **kwargs)
        print(f'{typology or "(default)":<12} OK   {model.element_count} elements')
    except Exception as error:
        print(f'{typology or "(default)":<12} FAIL {type(error).__name__}: {error}')
```

Suggested order of work: find the L02 bay whose width collapses, and make the emitter
refuse to author a sub-tolerance panel at source rather than emitting one for a later
stage to reject.

---

## CR-02 — facade programme resolution is running on a fallback nobody reports (high)

`backend/app/envelope.py:869` offers four sources for the programme behind a facade bay.
Instrumenting `builtins.getattr` over a real compile shows **three of them never
deliver**:

| source (`envelope.py:869-875`) | measured over one compile |
|---|---|
| `getattr(b.lattice, 'program_volume_regions', ())` | empty — lattice carries 0 regions |
| `getattr(b, 'program_volume_regions', ())` | attribute absent **656/656** calls |
| `getattr(volume_model, 'volumes', ())` | `volume_model` is `None` **656/656** calls |
| `program_allocation.zones` | the only one that resolves — 11 zones |

The third line is `getattr` applied to an object that is always `None`. That is the
guard that hides the break.

**The break.** `program_volume_model` is written **onto the model** at
`backend/app/program_volumes.py:1669` (`model_copy(update={'program_volume_model': …})`)
and read **off the builder** at `backend/app/envelope.py:868` and `:997`. Different
objects. The value never crosses. The only other reference,
`backend/app/analysis_bundle.py:690`, reads it back off the model, so nothing else
notices.

**Consequence, measured.** On `theater/FCD-05-HIGH-TECH`:

| rule ref | bays |
|---|---|
| `DENSITY_TO_FACADE` | 242 |
| `PROGRAM_ALLOCATION_TO_FACADE` | 229 |
| `FACADE_PROGRAM_FALLBACK_UNEVALUATED` | **183** |
| `PROGRAM_VOLUME_TO_FACADE` | **0** |

183 of 412 programme-resolved bays — **44%** — are authored on a fallback, and the
Program Volume path contributes nothing to the facade at all.

**What is already right, and must stay right.** The gate that audits this,
`_gate_high_tech_program_control` in `backend/app/facade_gates.py`, returns
`verdict='unevaluated'` when the model carries no Program Volume regions. It does **not**
report a pass. That is the project's earned-status discipline working; do not "fix" the
gate to make it green. The gap is that the 44% fallback rate is reported to no one,
because the gate bails before it counts those bays.

Reproduce:

```python
from collections import Counter
refs = Counter(ref for element in model.elements for ref in element.rule_refs
               if 'TO_FACADE' in ref or 'FACADE_PROGRAM' in ref)
print(refs.most_common())
```

---

## CR-03 — one rule, two implementations, opposite failure behaviour (medium)

The same transom-rows → secondary-member-count mapping is implemented twice:

- producer: `backend/app/envelope.py:1080` `_high_tech_secondary_count`
- checker: `backend/app/facade_gates.py:940` `_secondary_expected`

Both read the `transom_rows` datum, prefer `applied_position`, fall back to
`dimension_value`, then fall back again to `datums.integer('transom_rows')`. The two
copies diverge exactly where it matters — on a datum set that lacks `transom_rows`:

| | producer (`envelope.py`) | checker (`facade_gates.py`) |
|---|---|---|
| fallback call | unguarded | wrapped in `try` |
| result | raises `KeyError` — run dies | returns `None` — gate silently skipped |

This is the shape the project's own `_core_box` docstring warns about: two copies of one
decision is two opinions about that decision.

**The guard around both is half dead.** `except (AttributeError, KeyError)` at
`envelope.py:1090` and `facade_gates.py:950`:

- `AttributeError` **cannot fire**. `Datum.applied_position` and `Datum.dimension_value`
  are declared `float | None` at `backend/app/datums.py:80,82`; attribute access on a
  Pydantic model with a declared field never raises.
- `KeyError` fires only if the datum is missing — and `DatumSet.by_id`
  (`datums.py:111`) and `DatumSet.value` (`datums.py:102`) both raise it. So in the
  producer the `except` swallows the `KeyError`, and two lines later
  `datums.integer('transom_rows')` raises the **same** `KeyError` uncaught. The guard
  defers the crash by two lines and makes the code look protected.

**It is also dead in production.** `transom_rows` is emitted unconditionally from the
module-level datum table at `backend/app/datums.py:177`, so `by_id` never raises on a
real compile. The comment at `envelope.py:1093` states the guard's real audience:
"Legacy/test datum sets expose only the already-derived 2-4 transom count." This is test
shape living in production code.

Suggested fix: one function, one module, imported by both; let the missing-datum case
fail loudly in one place.

---

## CR-04 — a fifth of the payload is never read (medium)

The three hops from compiler to browser are **clean**: `BuildingModelV3` (39 fields) →
`AnalysisBundle` (43) → `web/lib/types.ts` `AnalysisBundle` (43), with only `units` and
`coordinate_system` dropped, both documented as deliberate in
`backend/tests/test_analysis_bundle.py`. Nothing is lost in transit.

The problem is at the far end. The bundle is now **5.22 MB** on a 9,432-element model,
and six top-level fields are named by no component in `web/`:

| field | KB | share |
|---|---|---|
| `transfer_structure` | 876 | 16.4% |
| `room_layout_plan` | 213 | 4.0% |
| `portals` | 27 | 0.5% |
| `room_layouts` | 5 | 0.1% |
| `circulation_plan` | 0 | null |
| `project_brief` | — | — |
| **total unread** | **1,121** | **20.9%** |

Caveat on method, and it is a real one: 27 `Object.entries/keys/values` sites exist in
`web/`, so a name-based miss is not proof a field is unused. These six are top-level
bundle fields that a component would have to name to render, and none is named — but
open the consumer before deleting anything. Related:
[`decisions/0021-review-evidence-architecture.md`](decisions/0021-review-evidence-architecture.md).

For context on relative cost, the three largest read fields are `life_safety` (1,368 KB,
25.6%), `dependency_graph` (1,216 KB, 22.7%) and `derivation` (1,147 KB, 21.4%).
`derivation` publishes one reasoning chain per element family; at 9,432 elements it is
now the third-largest field in the response and is worth re-checking against the
lightweight goal.

Reproduce:

```python
import json
bundle = json.loads(compile_analysis_bundle(model).model_dump_json())
for name, value in sorted(bundle.items(), key=lambda kv: -len(json.dumps(kv[1])))[:16]:
    print(f'{name:<28}{len(json.dumps(value)) / 1024:>9.0f} KB')
```

---

## CR-05 — defensive guard census (low)

Patching `builtins.getattr` before importing the app and compiling one model
(`theater/FCD-05-HIGH-TECH`, 9,432 elements) records every three-argument call:

- **88** guards never used their default — they defend against a state this pipeline
  does not produce.
- **66** did use it, but most are Pydantic and stdlib internals
  (`ModelMetaclass.*`, `GenericAlias.*`, `module.__file__`), not application code.

The application-level guards whose default fires **every** time are the informative
ones, because a guard that always fires is not a guard:

| guard | fires | meaning |
|---|---|---|
| `QuadGeometry.profile` (`room_fixtures.py:198`) | 11,279 / 11,279 | `QuadGeometry` has no `profile` field; the lookup is always `None` |
| `_Builder.program_volume_model` | 656 / 656 | see CR-02 |
| `_Builder.program_volume_regions` | 656 / 656 | see CR-02 |
| `NoneType.volumes` | 656 / 656 | `getattr` on `None` — see CR-02 |
| `AllocatedZone.boundary` | 1,705 / 1,705 | consumer expects a field the producer does not set |
| `AllocatedZone.space_ids` | 1,705 / 1,705 | same |

Most of the guarded names are declared Pydantic fields with defaults —
`program_volume_regions` (`datums.py:478`), `profiles` (`models_v3.py:469`, required),
`thickness_m` (`models_v3.py:252`), `portals`, `roof_control`, `transfer_structure` — so
plain attribute access already yields the same value the default supplies. Removing those
guards changes no behaviour and stops them hiding the cases that matter.

Reproduce (must patch before importing the app):

```python
import builtins
from collections import Counter
_real, PRESENT, MISSING = builtins.getattr, Counter(), Counter()

def traced(obj, name, *default):
    if not default:
        return _real(obj, name)
    key = (type(obj).__name__, name)
    try:
        value = _real(obj, name)
    except AttributeError:
        MISSING[key] += 1
        return default[0]
    PRESENT[key] += 1
    return value

builtins.getattr = traced
# ... import the compiler, compile a model, then restore builtins.getattr = _real
```

---

## CR-06 — the option-bank split does not exist yet (design)

Relevant to moving this project toward a skill that hands an agent tools and a
deliverable contract, with the judgement left to the model.

**The selection layer is already an option bank.** 27 module-level `dict` registries
(`tectonics.py` 5, `codes.py` 4, `selection.py` 3, `typology.py`, `registry.py`,
`materials.py`, …), and only **8** hard branches on `typology` / `grammar_id` in the
entire application. Type, form, style and structure are already chosen from tables rather
than from code. That work does not need redoing.

**What is still hard-coded is numeric policy** — 215 module-level numeric constants,
`compiler_v3.py` alone holding 34. These fall into two categories that the code does not
currently distinguish, and the distinction is the core contract of an option-bank
architecture:

*Must stay fixed — code, material and standards facts. An agent must not choose these:*

- `CORE_WALL_FC_KPA = 30_000.0` (`compiler_v3.py:539`) — f'c 30 MPa
- `CORE_WALL_DENSITY_KN_M3 = 24.0` (`:540`)
- ADA slope and landing constants in `ada.py`
- IBC egress widths and travel distances in `life_safety.py`, `codes.py`
- section and material properties in `sections.py`, `registry.py`

*Should become choosable — design preference currently frozen as a script:*

- the twelve shelf-layout constants at `compiler_v3.py:5743-5757` —
  `SHELF_RUN_MAX_M`, `SHELF_RUN_MIN_M`, `SHELF_RUN_GAP_M`, `SHELF_CROSS_AISLE_M`,
  `SHELF_EDGE_CLEARANCE_M`, `SHELF_DEPTH_M`, `SHELF_ROW_PITCH_M`,
  `SHELF_FIRST_ROW_OFFSET_M`, `SHELF_AISLE_SEARCH_STEP_M`,
  `SHELF_FIXED_OBSTACLE_CLEARANCE_M`, `SHELF_REGION_BODY_MARGIN_M`. A librarian and an
  architect would choose these per project; nothing about them is a code requirement.
- `PLAN_FIT_MIN = 0.7` / `PLAN_FIT_MAX = 1.5` (`compiler_v3.py:3971-3972`) — tolerance,
  not law
- `MAX_PRIMARY_TRIALS = 8` (`:3604`) — a search budget
- `LIFT_WALL_M = 0.20` (`:4307`), whose own comment reads "schematic wall thickness, not
  a calculated assembly"

Only **2** constants in the whole application annotate their own status
(`LIFT_WALL_M` above, and `NDS_CM` at `validators.py:348`). Everything else is a bare
number, so there is no machine-readable way for an agent to tell what it may move from
what it must not. **That marker is the first thing the pivot needs** — a registry, a
field on a constant record, or a naming convention, but something a tool can read.

The other shape worth converting is the fallback waterfall. `envelope.py:869` and `:998`
resolve a bay's programme by trying four sources in a fixed order and silently taking the
first that answers. Under an option-bank model that ordering is a decision the agent
should make explicitly, and the fallback rate (CR-02: 44%) should be a reported figure in
the deliverable rather than an invisible default.

---

## CR-07 — what looks wrong and is not (by design)

Recorded so the next reader does not re-litigate them.

- **Two v3 compile paths.** `pipeline.py:159` switches on `v3_mode` between
  `compile_program_volume_candidate` and `compile_building_model_v3`. This is
  [decision 0024](decisions/0024-program-volumes-author-the-form.md) keeping the Program
  Volume path explicit until its promotion gates pass, not
  accidental duplication. `v3_mode` defaults to `program_volume` whenever a
  `project_brief` is supplied (`pipeline.py:132`).
- **`legacy_program_layout.py` is not dead.** Despite the name it is imported by
  `main.py`, `pipeline.py`, `candidate_planning.py`, `joint_layout.py` and
  `program_volumes.py`. It and `program_volumes.py` import each other, which is worth
  cleaning, but neither is abandoned code.
- **Gates returning `unevaluated`.** Several facade gates decline to grade rather than
  passing when evidence is absent. That is the earned-status rule, not a bug.
- **`room_fixtures._shape` raising on degenerate geometry.** Correct. See CR-01 — fix the
  producer, not the check.

---

## Suggested order

1. **CR-01** — the default entry to the path the project is promoting is broken.
2. **CR-02 / CR-03** — both are small, local, and each removes a guard that hides a real
   failure. CR-03 in particular is a single-function extraction.
3. **CR-06** — decide the fixed-vs-choosable marker before converting any constant, or
   the conversion has no contract to check against.
4. **CR-04** — cheapest payload win is `transfer_structure` (876 KB); confirm no consumer
   first.

Not covered by this pass: `blender/`, `tools/`, `backend/scripts/`, the drawing set, and
the frontend beyond field consumption.
