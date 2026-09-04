# 04 — Glulam Post-and-Beam System

- `system_id`: `STR-SYS-GLULAM-POST-BEAM`
- `tectonic_family`: `frame`
- `material_system`: `glulam_post_and_beam`

## Scope and research basis

Post-and-beam is the **three-tier** timber frame: post, beam, joist or purlin, with a
deck on top. Unlike mass timber it has no panel module, so the visible order is the
framing rhythm itself — you count joists, you read the brace, you see how the beam sits
on the post. This is the system that most closely matches the second and third studio
reference models, where the whole architectural argument is carried by exposed sticks
and their joints.

Canonical references:

1. Shigeru Ban, **Tamedia Office Building**, Zurich, 2013 — an all-timber frame with
   interlocking connections and no steel in the primary joints.
2. Kengo Kuma, **GC Prostho Museum Research Center**, Kasugai, 2010 — the frame is a
   three-dimensional stick lattice at furniture scale.
3. Peter Zumthor, **Swiss Sound Box**, Expo 2000 — stacked timber beams with no adhesive,
   making stacking itself the structural and spatial system.
4. Traditional Japanese and Nordic post-and-beam framing — the historical basis for
   bracket, brace, purlin, and rafter hierarchy.

Primary sources:

- [AWC 2024 National Design Specification for Wood Construction](https://awc.org/resources/2024-nds/)
- [AWC 2021 Special Design Provisions for Wind and Seismic](https://awc.org/resources/2021-sdpws/)
- [APA, Glulam Product Guide and design resources](https://www.apawood.org/glulam)
- [ICC 2024 IBC Chapter 6, Types of Construction](https://codes.iccsafe.org/content/IBC2024V2.0/chapter-6-types-of-construction)

## Structural thesis

Discrete posts carry primary beams; primary beams carry a dense secondary tier of joists,
purlins, or rafters; a structural deck spans the secondary tier and forms the diaphragm.
Because every tier is visible, the **depth ratio between tiers is the architecture**, and
because timber connections are weak in tension, knee braces, portal frames, or a declared
shear wall system are required — not optional.

This system does **not** inherit CLT panel behaviour. If a CLT floor is wanted, select
guide 03 instead.

## Invariants

- `GPB-INV-01` — the spanning hierarchy is three tiers deep: primary beam, secondary
  joist or purlin, deck. A two-tier version is guide 03 or guide 01, not this system.
- `GPB-INV-02` — deck direction is declared and perpendicular to the secondary tier.
- `GPB-INV-03` — every beam-to-post connection is modelled as a named connector or joint
  volume; timber joints are the failure mode and the architecture at once.
- `GPB-INV-04` — a lateral system is declared explicitly: knee braces, portal frames,
  diagonal bracing, or sheathed shear walls. Moment continuity is never assumed.
- `GPB-INV-05` — beam bearing length at each post is modelled and checked; a beam that
  touches a post at a point is unresolved.
- `GPB-INV-06` — roof geometry (flat, mono-pitch, gable) is a datum, and rafters, purlins,
  and ridge follow from it rather than being drawn independently.

## Element taxonomy

| Kind | Primitive | Section / form | Starting range | Located by |
|---|---|---|---|---|
| `glulam_post` | member | rectangular | 0.20–0.45 m square | grid node `(i,j,k)→(i,j,k+1)` |
| `primary_beam` | member | rectangular glulam | depth ≈ span/16 | node `(i,j,k)→(i±1,j,k)` |
| `secondary_beam` | member | rectangular glulam | depth ≈ span/18 | bay subdivision |
| `joist` | member | sawn or LVL | 0.06 × 0.24–0.30 m @ 0.4–0.8 m | secondary tier subdivision |
| `purlin` | member | rectangular | 0.10 × 0.20 m @ 0.8–1.6 m | roof rafter subdivision |
| `rafter` | member | rectangular glulam | depth ≈ span/18 | roof datum, ridge to eave |
| `ridge_beam` | member | rectangular glulam | depth ≈ span/14 | roof apex line |
| `knee_brace` | member | rectangular | 0.15 × 0.20 m | post-to-beam corner, 45° |
| `portal_frame_haunch` | member | tapered | — | declared lateral bays |
| `structural_deck` | extrusion | plank or panel with direction | 0.03–0.06 m | plate polygon per level |
| `sheathed_shear_wall` | extrusion | studs + panel | t 0.15–0.25 m | declared wall lines |
| `bearing_block` · `bracket` | box | steel or timber | 0.15–0.35 m | every beam end |
| `tie_rod` | member | steel rod | Ø 16–32 mm | tension paths only |
| `base_shoe` | box | steel shoe + anchor | 0.2–0.4 m | post base node |
| `footing` | box | pad | 0.9–1.8 m | post base node |

## Geometry primitives required

`member` overwhelmingly dominates — this is the most member-heavy of the frame systems,
typically 80 % or more of all instances, because the joist and purlin tiers are dense.
`extrusion` carries deck and shear walls. `box` carries connectors and footings. The
studio-model read comes almost entirely from the tertiary tier.

## Datum chain specialisation

```text
DATUMS   bay_x, bay_y, floor_to_floor, joist_spacing, purlin_spacing,
         roof_form, roof_pitch, brace_rule, deck_direction
   ↓
LATTICE  level_table[k] × x_lines[i] × y_lines[j] × roof_datum
   ↓
ELEMENTS posts and beams from grid nodes; joists from bay subdivision;
         rafters and purlins from the roof datum; braces from corner nodes
```

The **roof datum** is a lattice element that flat-roofed systems do not need: a ridge
line plus a pitch generates rafter start and end points, and purlins subdivide the
rafters. Once the roof datum exists, the entire roof frame is deterministic.

## Legal variables and starting ranges

| Parameter | Starting range | Owner |
|---|---:|---|
| `bay_x`, `bay_y` | 3.6–7.2 m | score (`density`) inside clamp |
| `joist_spacing` | 0.4–0.8 m | score (`density`) inside clamp |
| `purlin_spacing` | 0.8–1.6 m | score (`repetition`) |
| `floor_to_floor` | 3.3–4.8 m | score (`tension_release`) |
| primary beam depth ratio | span/14–span/18 | tectonic |
| `roof_pitch` | 0°–35° | human or score (`hierarchy`) |
| knee brace length | 0.8–1.6 m | tectonic |
| cantilever | 0–0.30 × adjacent span | score (`continuity`) inside clamp |

## Forbidden operations

- assuming moment continuity at a timber beam-post joint;
- omitting the connector volume and letting members interpenetrate;
- a beam bearing on a post over zero length;
- deriving a knee brace or shear wall dimension from a score value;
- generating rafters, purlins, and ridge independently so they do not meet;
- inheriting CLT diaphragm behaviour without selecting guide 03;
- long clear spans served by deepening a beam past the declared ratio instead of
  selecting a truss or a different system.

## Shared Score channels

| Dimension | Mapping in this system |
|---|---|
| Hierarchy | depth ratio between the three tiers; ridge beam prominence |
| Repetition | joist and purlin cadence — the dominant visual channel in this system |
| Variation | bounded bay-width family change; brace presence per bay |
| Density | joist spacing, purlin spacing, secondary beam count |
| Continuity | whether the joist run is continuous or interrupted per bay |
| Interruption | double-height bays, missing bay, roof light openings |
| Polyphony | post rhythm, joist rhythm, and purlin rhythm as three voices |
| Tension / Release | floor-to-floor, roof pitch, open vs braced bays |
| Tempo of Change | frequency of joist-direction change along the plan |

## Program negotiation

| Program condition | Post-and-beam-specific response |
|---|---|
| reading room, gallery | the exposed frame is the room; span limits set the room size |
| auditorium, long span | select a timber truss or leave the system; do not deepen a beam |
| stacks, archive | joist spacing tightens sharply; check whether the tier is still legible |
| public circulation | knee braces intrude at head height; coordinate or relocate the braced bay |
| fire and egress | exposed timber char and encapsulation requirements may govern member size |
| facade | posts are close to the envelope; decide whether they are inside or outside it |

## Grasshopper / Rhino modelling guideline

1. Establish the roof datum with the level table; both are needed before framing.
2. Generate posts and primary beams from grid nodes with connector volumes at every end.
3. Subdivide bays for the joist tier; keep the direction attribute on every joist.
4. Generate rafters from the roof datum, then purlins as rafter subdivisions.
5. Place knee braces or portal haunches from the declared lateral rule only.
6. Emit deck as an extrusion with an explicit direction perpendicular to the joists.
7. Check bearing length at every beam end before sweeping sections.
8. Bake tiers to separate layers; the tier separation is the deliverable.

## Typology notes

- **Library:** the frame gives warmth and rhythm to reading rooms; stacks zones may need
  a different floor system entirely.
- **Theater:** excellent for foyer and support spaces; the auditorium span usually needs
  a truss variant or another system.
- **Museum:** the exposed frame competes with the exhibits; consider whether the tertiary
  tier should be concealed in gallery zones and exposed elsewhere.

## Validation

- three tiers are present and distinguishable by type and depth;
- deck direction is declared and perpendicular to the secondary tier;
- every beam end has a connector volume and a non-zero bearing length;
- a lateral system is declared and continuous to foundation;
- rafters, purlins, and ridge intersect within tolerance;
- span-to-depth ratios stay inside the declared range or are flagged;
- identical inputs reproduce identical element IDs and tier subdivisions.

## Limitations

No connection capacity, no char or fire-resistance calculation, no shrinkage or
serviceability check, no fabrication tolerance. Section ratios are architectural
conventions at study-model resolution. Every element remains
`professional_review_required`.
