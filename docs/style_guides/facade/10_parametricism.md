# 10 — Parametricism-informed Relational Facade Grammar

## Scope and research basis

Parametric design is a method; Parametricism is Patrik Schumacher's proposed stylistic
doctrine. This project uses a qualified grammar focused on relational logic:
parameterized variability, differentiation, correlation among systems and adaptive
response to context. Smoothness and complexity are optional outcomes. Every visible
change must be recoverable from a dependency graph.

Canonical references:

1. Zaha Hadid Architects, **MAXXI**, 1998–2009.
2. Zaha Hadid Architects, **Heydar Aliyev Center**, 2007–2012.
3. Zaha Hadid Architects, **Morpheus Hotel**, 2012–2018.
4. Projects using performance-driven facade differentiation and rationalized panel
   families, studied as technical references rather than style proof.

Primary sources:

- [Patrik Schumacher, On Parametricism](https://patrikschumacher.com/on-parametricism/)
- [Patrik Schumacher, Dialogue on Parametricism](https://patrikschumacher.com/on-parametricism-a-dialogue-between-neil-leach-and-patrik-schumacher/)
- [Zaha Hadid Architects, Morpheus model and exoskeleton](https://www.zaha-hadid.com/2020/02/28/morpheus-model-showcased-at-the-pompidou-centre/)
- [Zaha Hadid Architects, MAXXI project material](https://www.zaha-hadid.com/wp-content/uploads/2019/12/maxxi.pdf)
- [McNeel, PanelingTools for Grasshopper Primer](https://wiki.mcneel.com/_media/labs/panelingtools4grasshopperprimer.pdf)
- [Facade Tectonics Institute, Design Considerations and the Complex Facade](https://www.facadetectonics.org/papers/design-considerations-and-the-complex-facade)

## Facade thesis

The facade is a system of interdependent variables. Program, structure, orientation,
environment, circulation and score fields influence related geometric and assembly
parameters through declared functions. Differentiation forms gradients, thresholds and
singular events while maintaining correlation and fabrication continuity.

## Invariants

- `PA-INV-01` — every variable has domain, owner, unit, source and dependency edges.
- `PA-INV-02` — facade differentiation is deterministic and correlated to meaningful
  input fields.
- `PA-INV-03` — at least two systems are correlated without collapsing into one scalar;
  for example structure, shading and aperture interpret a shared field differently.
- `PA-INV-04` — panelization and support are generated alongside or immediately after
  host geometry, not deferred until presentation.
- `PA-INV-05` — singularities and thresholds are explicitly located and bounded.
- `PA-INV-06` — fixed inputs and seed reproduce equivalent fields, IDs and geometry.

## Legal variables and starting ranges

Project-authored experiment defaults:

| Parameter | Starting range | Owner and use |
|---|---:|---|
| normalized driver fields | 2–5 | environment/program/score |
| active degrees of freedom per panel family | 1–4 | grammar/fabrication |
| aperture ratio | 0.15–0.80 | environment/program clamp |
| panel twist/non-planarity | material-system limit; concept placeholder 0–30 mm/m | fabrication |
| gradient smoothing radius | 1–5 panel widths | grammar |
| singularity zones | 1–5 per facade system | program/hierarchy |
| unique panel ratio target | ≤ 0.35 at MTA-F2 unless fabrication case supports more | fabrication/cost proxy |
| neighbor parameter jump | ≤ 20% normally; threshold zones documented | continuity |

## Forbidden operations

- mapping music amplitude directly to vertex displacement;
- using random noise with no seeded and semantically owned input;
- treating a blob or continuous curve as sufficient evidence;
- adding dependencies that cannot be visualized or tested independently;
- generating thousands of unique panels without a fabrication rationale;
- allowing trimmed-surface UV irregularities to masquerade as intentional variation;
- hiding failed panels, self-intersections or support gaps through remeshing.

## Shared Score channels

| Dimension | Mapping in this grammar |
|---|---|
| Hierarchy | weight a bounded attractor/singularity at primary program nodes |
| Repetition | establish base panel/component genotype |
| Variation | drive genotype parameters through correlated fields |
| Density | adjust subdivision, member or opening density after performance clamps |
| Continuity | smooth field transitions and align correlated seams/routes |
| Interruption | explicit discontinuity curve, threshold or topology change |
| Polyphony | multiple systems read one score field through separate adapter functions |
| Tension / Release | increase/decrease curvature, depth, aperture contrast or system convergence |
| Tempo of Change | tune spatial derivative/frequency of field change along a path |

## Grasshopper/Rhino modeling guideline

1. Declare a dependency graph before building the final definition. Separate raw input,
   normalized field, grammar mapping, constraint clamp and applied value.
2. Create facade host geometry with stable parameterization. For trimmed or multi-face
   Breps, use explicit elevation paths, contour/section grids, remeshed topology or
   remapped domains; do not assume raw UV consistency.
3. Build driver fields independently: program hierarchy, orientation/solar, view/privacy,
   structure proximity and accepted score.
4. Define panel/component genotypes with bounded degrees of freedom and stable interfaces.
5. Correlate systems with separate functions, such as density → smaller structural bays,
   denser shading and reduced aperture, each with its own legal range.
6. Apply smoothing, threshold and singularity rules; store both proposed and clamped
   values.
7. Panelize and evaluate planarity, curvature, size, corner angle, support, seam
   continuity and unique-part ratio.
8. Cluster components by geometric similarity and regenerate using family IDs/instances
   where feasible.
9. Run deterministic unit fixtures for zero/min/max/mid fields and boundary conditions.
10. Bake host, field samples, panels, support and invalid/debug geometry into separate
    review layers; only valid accepted layers pass downstream.

## Tectonic compatibility

- **Frame — native.** Variable bays, diagrids and correlated infill are accessible, with
  clear structural clamps.
- **Tensile — native.** Form-finding, boundary and prestress are inherently relational;
  physics owns the final legal domain.
- **Shell — native.** Surface continuity and differentiated rib/panel systems fit well;
  geometry health and fabrication checks are essential.

## Typology notes

- **Library:** correlate daylight, views, quiet/public zones and reading-module density;
  prevent visual complexity from overwhelming wayfinding.
- **Theater:** correlate foyer circulation, structural span, acoustic enclosure and
  public facade; auditorium constraints remain hard.
- **Museum:** correlate gallery daylight limits, route hierarchy and panel/shading fields;
  smooth form cannot erase display-wall and loading requirements.

## Validation

- 100% of active variables have owner, domain, source and dependency record;
- all field samples and outputs reproduce for fixed inputs/seed/version;
- no invalid, self-intersecting, sub-minimum or unsupported panel enters accepted output;
- neighbor jumps, singularities and topology changes meet declared rules;
- unique panel ratio and family counts are reported honestly;
- each correlated subsystem responds differently but traceably to the same score input;
- turning score influence to zero yields a valid environment/program baseline;
- a reviewer can isolate one driver and predict its intended downstream changes.

## Limitations

This guide does not endorse the universal historical claims associated with
Parametricism. It defines a bounded relational grammar for controlled comparison.
Performance, fabrication and structure require verified models and external expertise.
