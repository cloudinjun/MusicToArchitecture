# 07 — Cable Net and Cable-Supported Hybrid System

- `system_id`: `STR-SYS-CABLE-NET-HYBRID`
- `tectonic_family`: `tensile`
- `material_system`: `cable_net_hybrid`

## Scope and research basis

Where a membrane is a continuous tension *surface*, a cable net is a discrete tension
*network*: two or more cable families crossing at clamped nodes, carrying a cladding that
is not itself structural. The architectural difference is decisive. A membrane hides its
forces inside a fabric; a cable net puts them on display as a countable lattice of lines
and joints, and the node becomes the detail the whole building is judged by.

This guide also covers cable-supported hybrids — cable-stayed roofs, cable-braced
facades, cable domes, and tensegrity — where tension elements stabilise a compression
skeleton rather than forming a complete surface.

Canonical references:

1. Frei Otto with Behnisch & Partner, **Munich Olympiapark**, 1972 — a prestressed cable
   net carrying acrylic panels, with every node a designed component.
2. David Geiger and Matthys Levy, **cable dome roofs** (Seoul 1988, Georgia Dome 1992) —
   continuous tension, discontinuous compression, at stadium span.
3. Arup and Cox Rayner, **Kurilpa Bridge**, Brisbane, 2009 — a large built tensegrity
   demonstrating masts stabilised entirely by tension families.
4. Renzo Piano Building Workshop, cable-braced glass facades — cable trusses as the
   primary support for a non-structural envelope.

Primary sources:

- [ASCE 19, Structural Applications of Steel Cables for Buildings](https://www.asce.org/publications-and-news/codes-and-standards/)
- [ASCE/SEI 55-16, Tensile Membrane Structures](https://sp360.asce.org/personifyebusiness/Merchandise/Product-Details/productId/233135208)
- [ASCE/SEI 7-22, Minimum Design Loads and Associated Criteria](https://www.asce.org/publications-and-news/codes-and-standards/asce-sei-7-22)
- [IASS, International Association for Shell and Spatial Structures](https://iass-structures.org/)

## Structural thesis

Two or more cable families are prestressed against a compression boundary — a ring, a
mast set, an arch, or a rigid frame — so that every cable stays in tension under every
load case. Cladding hangs from the net and adds no stiffness. Stability comes from
prestress level and from the opposing curvature of the two families, exactly as in a
membrane, but the discreteness means node positions, cable lengths, and clamp angles are
all fabrication data from the first sketch.

## Invariants

- `CN-INV-01` — at least two cable families with opposing curvature are modelled, and
  every family carries a declared pretension state. A cable element without an axial
  force state is not a cable.
- `CN-INV-02` — no cable goes slack under any declared load case; slack is a failure, not
  a warning.
- `CN-INV-03` — every crossing is a modelled `net_node` element with an ID, not an
  incidental geometric intersection.
- `CN-INV-04` — the compression boundary (ring, mast, arch, frame) is a separate element
  family with its own continuous load path to foundation and published reactions.
- `CN-INV-05` — cladding is explicitly non-structural and its support points are declared
  on nodes or cables.
- `CN-INV-06` — a box frame with decorative cables does not satisfy this system. If the
  cables can be deleted without changing the load path, the profile fit check fails.

## Element taxonomy

| Kind | Primitive | Form | Starting range | Located by |
|---|---|---|---|---|
| `cable_family_a` | member | spiral strand or locked coil | Ø 20–90 mm | net grid, direction 1 |
| `cable_family_b` | member | spiral strand or locked coil | Ø 20–90 mm | net grid, direction 2 |
| `net_node` | box | cast or fabricated clamp | 0.15–0.60 m | every family crossing |
| `compression_ring` | member ×N | closed CHS or box polygon | Ø 0.6–2.0 m | net boundary |
| `mast` | member | CHS, tapered | Ø 0.4–1.5 m, h 10–60 m | declared high points |
| `strut` | member | CHS | Ø 0.15–0.5 m | tensegrity and cable-dome layers |
| `stay_cable` | member | strand | Ø 30–120 mm | mast head to deck or ring |
| `stabilising_cable` | member | strand | Ø 16–50 mm | anti-flutter and reversal paths |
| `hoop_cable` | member | strand | Ø 24–70 mm | cable-dome tension rings |
| `cladding_panel` | quad | glass, acrylic, or metal | ≤ 2.0 × 3.0 m | node-to-node quads |
| `panel_bracket` | box | articulated fitting | 0.1–0.3 m | node or cable attachment |
| `anchor_block` | extrusion | mass or piled foundation | 2.0–8.0 m | every cable termination |
| `turnbuckle` · `tensioner` | box | adjustment device | 0.3–1.0 m | declared tensioning points |
| `boundary_frame` | member ×N | box or CHS frame | depth ≈ span/25 | rigid boundary configurations |

## Geometry primitives required

`member` with a **required axial-force state** — this system extends `MemberGeometry`
with `pretension_kn` and `slack_check_status`, which no other system needs. `box` for
nodes, which are first-class elements here and carry the fabrication argument. `quad` for
cladding, with a **planarity tolerance** because glass panels on a doubly curved net must
be planar or cold-bent within a declared limit. `extrusion` for anchors.

## Datum chain specialisation

Like the membrane, geometry is downstream of a solve. Unlike the membrane, the solve
produces a **node set**, not a surface, and that node set is the lattice.

```text
DATUMS   boundary_geometry, cable_family_count, net_module, prestress_level,
         mast_or_ring_configuration, cladding_panel_limit
   ↓
FORM FINDING   force-density or dynamic-relaxation solve -> net_node positions
   ↓
LATTICE  net_node[i][j]  (the registration set)
   ↓
ELEMENTS cables between adjacent nodes; cladding quads from node quads;
         struts and hoops from the layer configuration; anchors from cable ends
```

`net_node[i][j]` is a genuine two-index lattice, so element IDs recover the same
self-locating property as the orthogonal grid systems — `TEN-NODE-I012-J007`,
`TEN-CBL-A-I012-J007`. That is a real advantage of the net over the membrane.

## Legal variables and starting ranges

| Parameter | Starting range | Owner |
|---|---:|---|
| `net_module` | 0.75–3.0 m | score (`density`) inside clamp |
| cable family count | 2–4 | tectonic; score selects inside |
| prestress level | 15–45 % of breaking load | tectonic; never score |
| curvature (rise / span) | 1 : 8 to 1 : 14 | tectonic; never score |
| mast height | 10–60 m | score (`hierarchy`) inside clamp |
| cladding panel size | ≤ 2.0 × 3.0 m | fabrication; never score |
| panel planarity tolerance | ≤ 1 : 200 of diagonal | fabrication; never score |
| node family count | 1–6 unique types | fabrication target |

## Forbidden operations

- a cable modelled as a straight member with no pretension and no slack check;
- a crossing left as a geometric intersection instead of a `net_node` element;
- cladding assigned any stiffness contribution;
- cables that could be deleted without changing the load path;
- score dimensions modifying prestress, cable diameter, or curvature ratio;
- a doubly curved net clad with panels that are neither planar nor declared cold-bent;
- reporting a node count without reporting the count of *unique* node types.

## Shared Score channels

| Dimension | Mapping in this system |
|---|---|
| Hierarchy | mast height, ring prominence, primary versus stabilising cable families |
| Repetition | net module regularity — the dominant visual channel |
| Variation | bounded module change across declared zones |
| Density | net module, cable family count |
| Continuity | whether a cable family runs unbroken from boundary to boundary |
| Interruption | an opening in the net, a rigid infill zone, a mast penetration |
| Polyphony | two cable families plus the compression system as three voices |
| Tension / Release | prestress selection inside the legal band; rise-to-span |
| Tempo of Change | frequency of module change along a family direction |

## Program negotiation

| Program condition | Cable-net-specific response |
|---|---|
| covered public space, atrium, courtyard | the strongest fit; net plus glazing reads as one system |
| conditioned interior | the net is a roof or a facade support; enclosure is a separate system |
| auditorium, acoustic control | the net cannot deliver it; declare a separate acoustic envelope |
| gallery, light-sensitive | transparency conflicts with collection care; declare shading or a liner |
| large clear span | native strength; publish reactions early because they dominate foundations |
| facade support | cable trusses are a native fit; movement and deflection limits govern glass |

## Grasshopper / Rhino modelling guideline

1. Author the boundary geometry, family count, and net module as a datum set.
2. Solve for node positions with a recorded method and prestress level.
3. Freeze the node set as the accepted registration lattice.
4. Generate cable elements between adjacent nodes, one family at a time, each carrying a
   pretension attribute.
5. Emit `net_node` elements at every crossing and classify them into unique types.
6. Generate cladding quads from node quads and run the planarity check before anything
   else is drawn.
7. Build the compression system and anchors, then publish reactions at every termination.
8. Report cable schedule (length, diameter, pretension) and node schedule (type, count,
   angle set).
9. Bake families, nodes, compression system, cladding, and anchors to separate layers.

## Typology notes

- **Library:** a cable-net roof over a central atrium with a conventional structure around
  it is the realistic configuration.
- **Theater:** strong for the foyer and public volume; the auditorium needs mass.
- **Museum:** a net-and-glass court between solid gallery boxes is the classic pairing and
  is a legitimate hybrid declaration.

## Validation

- every cable has a pretension value and passes the slack check in every declared case;
- every crossing is a `net_node` element with an ID and a type classification;
- unique node type count is reported alongside total node count;
- the compression system is continuous to foundation with published reactions;
- every cladding panel satisfies the planarity tolerance or is flagged as cold-bent;
- cladding contributes no stiffness in the declared model;
- deleting the cable families breaks the load path (the anti-decoration test);
- re-solving with identical inputs reproduces node positions within tolerance.

## Limitations

No cable force solution, no nonlinear or dynamic analysis, no flutter, no fatigue, no
connection design, no cold-bending stress verification. Pretension values here are
placeholders for a solver that the project has not yet implemented. Every element remains
`professional_review_required`.
