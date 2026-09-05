# Decision 0017 — Every typology carves

- Status: accepted; all four typologies carry an archetype, its carver and its gates
- Date: 2026-09-03
- Decision owner: user ("每种建筑类型都要设计相应的 TypologyKit 以指导详细的设计，不止是剧场")
- Career-value tags: V2, V3

## The claim being tested

Decision [0016](0016-typology-kits-and-the-theatre-archetype.md) built the archetype
layer and had the theatre prove it. This decision tests the layer's real claim: that
the interface is not theatre-shaped, and that a typology's kit can guide detailed
design for *every* type in the registry. The proof is three more carvers written
against the same plumbing — no compiler changes beyond dispatch — each producing the
geometry its type is actually about, each audited by gates that measure the built
model rather than the derivation.

## The interface, generalised

`Carve` is now the base every carver returns: rooms placed as finished zones, the
floor they stand on reserved, the plates their section removes, the walls that must
run their full height. The compiler's plumbing — voids, `Lattice.carved` core
keep-out, the stranding refusal, preplacement — reads only those fields. A new
archetype is a carver plus its gates, registered in `_CARVERS`; the kit registry
refuses an archetype id with no carver at import, the same way it refuses a missing
brief.

## What each typology's kit now guides

**Theatre — `ARCH-THEATRE-BOWL`** (0016): the raked bowl derived to a constant
C-value and measured back per row, the stage, the proscenium wall, full-height
acoustic enclosure; gates for sightlines, section claims, the colonnade, FOH/BOH.

**Museum — `ARCH-GALLERY-SEQUENCE`**: the two galleries as an enfilade on the top
plate — the one place daylight arrives from above and can be controlled — joined
through a 3 m portal in a built party wall. On a courtyard plan the straight pair
does not fit beside the court, and the carver turns the sequence around the corner
instead: one gallery down the west band, one along the south band, the portal at the
turn — which is not a fallback from the type but the type on that plan. Gates:
ARCH-ENFILADE (the portal measured between the built wall pieces), ARCH-TOPLIGHT
(the galleries stand on the last occupied plate), ARCH-CLEAR-SPAN (a gallery broken
by columns is a corridor — their own brief's words, reported as the standing red the
long-span phase owes).

**Library — `ARCH-READING-ROOM`**: the principal reading room as a double-height
volume against a perimeter glazing line — placed on the second plate from the top,
the plate above opened over it with the same claim machinery the theatre built.
Where an atrium takes the perimeter strip the room rotates and stands beside the
void. Gates: ARCH-CLAIM-UNCUT and ARCH-DAYLIGHT — daylight measured against the
plate *polygon*, because a cantilever bulges the bounding box past the real envelope
and a room can stand hard on the glazing while sitting metres inside the box. No
colonnade gate: an 18 m span ask is ordinary bays, and a reading room with a column
grid is a reading room.

**Pavilion — `ARCH-HALL`**: the hall takes the east end of the ground plate through
its full depth and every plate above it is opened to the roof — a pavilion is a
room, not a stack of them, and now the model says so in section. Gates:
ARCH-DAYLIGHT and ARCH-CLEAR-SPAN (the demand row asks for a 40 m covered single
volume).

## What generalising measured

- **Bounding boxes lie about plates.** The first library placement anchored on the
  plate's bbox south edge and failed everywhere: the projecting levels cantilever
  south along part of the boundary only. Rooms now anchor on structural row lines,
  and the daylight gate probes the plate polygon, not the box.
- **Music voids are prior occupants.** An atrium the interruption punched into the
  gallery band is floor that is not there; carvers slide along the band, rotate, or
  wrap the court to get clear, and `_rect_clear_of` probes voids as well as the
  boundary on every placement.
- **The courtyard demanded the L.** At every scale the straight enfilade missed the
  courtyard plate by half a metre to a few metres — the court steals exactly the
  middle the pair wanted. The wrap is the honest resolution and the older figure.
- **Refusal-then-growth carried over unchanged.** Museum and library refuse at
  small scales (gutting, no clear band) and carve at the scales the plate fit
  reaches — the 0016 contract, exercised by three new carvers without modification.

## Evidence

- `backend/app/archetypes.py` — `Carve` base, `MuseumCarve` / `LibraryCarve` /
  `PavilionCarve`, the three carvers, shared helpers (`_rect_clear_of`, `_gutted`,
  `_place_zone`, `_plate_x_span`), the per-type gates and the generic ones.
- `backend/app/compiler_v3.py` — dispatch only: generic `Carve` handling in
  `_carve_and_allocate`, the museum party wall in `_emit_archetype`.
- `backend/app/typology.py` — every kit names its archetype; the registry refuses
  an archetype with no carver at import.
- `backend/tests/test_archetypes.py` — all four typologies compile carved on their
  own biased massings; the enfilade, the double-height reading room and the
  full-height hall are asserted from the built models.
- Decisions [0015](0015-a-placement-is-not-a-delivery.md),
  [0016](0016-typology-kits-and-the-theatre-archetype.md).
