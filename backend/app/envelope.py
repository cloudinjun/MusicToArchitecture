"""Envelope emitters, one per tectonic family.

`compiler_v3._emit_envelope` used to be a single function that built a curtain wall,
because a curtain wall was the only envelope the project had. Everything it could vary
-- module, transom rows, spandrel height, opaque share, fin depth, standoff -- moved
quantities inside that one wall, so fourteen recordings produced fourteen curtain walls
of slightly different grain. This module is where the wall stops being a constant.

The families differ in the **operation** they perform on an elevation, not in the size
of the result, and that is what the eye reads:

    subdivide   draw a frame; the openings are the cells left between members
    subtract    draw a wall; the openings are holes cut out of it
    overlay     draw a plain skin; stand a second structure in front of it
    recess      push the skin back inside the structural bay so the frame reads

A note on the punched wall, because the obvious implementation is wrong: an opening in a
wall is a hole in a *vertical* plane, and `ExtrusionGeometry` extrudes a plan polygon
upward, so it cannot express one. The wall is built instead as four quads around each
opening -- sill band, head band, two jambs -- with the reveal drawn as real boxes. That
is more honest than faking the hole and better for a study model besides, because a
reveal with thickness casts the shadow that makes masonry read as masonry.

Every element still carries the datums that placed it, so the translation report keeps
working across all eight families.
"""

from __future__ import annotations

import math

from .geometry import (
    BoxGeometry, MemberGeometry, QuadGeometry, Vector3, convention_profile, inset,
    polyline_stations, v3,
)
from .grammar_specs import GrammarSpec
from .tectonics import EnvelopeTectonic

PLATE_DATUMS = ('cantilever_m', 'plate_step_m', 'plate_rotation_deg', 'apse_radius_m')


class _Bay:
    """One module of elevation, and everything an emitter needs to place it."""

    __slots__ = ('point', 'nxt', 'z_base', 'z_head', 'angle', 'roll', 'index',
                 'level_id', 'si', 'is_principal')

    def __init__(self, point, nxt, z_base, z_head, angle, index, level_id, si,
                 is_principal):
        self.point, self.nxt = point, nxt
        self.z_base, self.z_head = z_base, z_head
        self.angle = angle
        self.roll = v3(math.cos(angle), math.sin(angle), 0.0)
        self.index, self.level_id, self.si = index, level_id, si
        self.is_principal = is_principal

    @property
    def width(self) -> float:
        return math.hypot(self.nxt.x - self.point.x, self.nxt.y - self.point.y)

    @property
    def height(self) -> float:
        return self.z_head - self.z_base

    def at(self, t: float, z: float) -> Vector3:
        """A point across the bay, `t` from 0 at `point` to 1 at `nxt`."""
        return v3(self.point.x + (self.nxt.x - self.point.x) * t,
                  self.point.y + (self.nxt.y - self.point.y) * t, z)

    def outward(self, distance: float) -> tuple[float, float]:
        """An offset normal to the bay, pointing away from the building."""
        return (math.cos(self.angle + math.pi / 2.0) * -distance,
                math.sin(self.angle + math.pi / 2.0) * -distance)

    def quad(self, t0: float, t1: float, z0: float, z1: float,
             push: float = 0.0) -> QuadGeometry:
        dx, dy = self.outward(push) if push else (0.0, 0.0)
        a, bb = self.at(t0, z0), self.at(t1, z0)
        return QuadGeometry(corners=(
            v3(a.x + dx, a.y + dy, z0), v3(bb.x + dx, bb.y + dy, z0),
            v3(bb.x + dx, bb.y + dy, z1), v3(a.x + dx, a.y + dy, z1)))


def effective_opening_width(env: EnvelopeTectonic, bay_width: float,
                           min_fragment: float) -> float:
    """The opening width a bay of this size will actually get.

    A slot is narrow on purpose; it is not narrower than a window can be built. At
    9 % of a 1.2 m bay the blank-plane grammar was cutting sixty-millimetre openings,
    which the facade gate caught as slivers -- correctly, because that is a drawn
    line rather than an opening anyone could make.

    Defined once and shared, because the first version widened the opening in the
    emitter while the sliver guard upstream still tested the declared ratio, and a
    guard measuring a different number from the one the emitter uses is not a guard.
    """
    if env.opening_width_ratio <= 0.0 or bay_width <= 0.0:
        return env.opening_width_ratio
    return min(0.85, max(env.opening_width_ratio, min_fragment / bay_width))


# ---------------------------------------------------------------------------
# subtract: a wall with holes cut in it
# ---------------------------------------------------------------------------

def _bay_punched(b, bay: _Bay, env: EnvelopeTectonic, datums,
                 min_fragment: float = 0.30) -> None:
    """A wall plane with an opening subtracted, drawn as the four bands around it.

    `ENV-PUNCHED-WALL` and `ENV-BLANK-SLOT` share this emitter and differ only in the
    proportions the tectonic declares: a punched wall takes roughly half the bay and
    half the storey, a blank plane takes a ninth of the bay and three quarters of the
    storey. That single pair of numbers is the whole difference between a masonry
    facade and an incision in a monolith, which is why they are declared data rather
    than branches.
    """
    # A slot is narrow on purpose; it is not narrower than a window can be built.
    # At 9 % of a 1.2 m bay the blank-plane grammar was cutting sixty-millimetre
    # openings, which the facade gate caught as slivers -- correctly, because that
    # is a drawn line rather than an opening anyone could make.
    width_ratio = effective_opening_width(env, bay.width, min_fragment)
    height_ratio = env.opening_height_ratio
    material = env.wall_material
    refs = ['opaque_fraction', 'mullion_module_m', 'envelope_offset_m', *PLATE_DATUMS]

    # The opening is centred in the bay and sits on a sill proportioned off the storey.
    t0 = (1.0 - width_ratio) / 2.0
    t1 = t0 + width_ratio
    sill_z = bay.z_base + bay.height * (1.0 - height_ratio) * 0.62
    head_z = min(bay.z_head, sill_z + bay.height * height_ratio)

    parts = (
        ('SILL', 0.0, 1.0, bay.z_base, sill_z),
        ('HEAD', 0.0, 1.0, head_z, bay.z_head),
        ('JAMBL', 0.0, t0, sill_z, head_z),
        ('JAMBR', t1, 1.0, sill_z, head_z),
    )
    for tag, a, c, z0, z1 in parts:
        if z1 - z0 < 0.04 or c - a < 0.01:
            continue
        b.add(f'ENV-WAL-{bay.level_id}-S{bay.si:03d}-{tag}', 'wall_panel', 'envelope',
              'bearing_wall', bay.quad(a, c, z0, z1), material,
              level_id=bay.level_id, lattice_index=bay.index, datum_refs=refs,
              rule_refs=['MASS_TO_PUNCHED_WALL'],
              thickness_m=env.wall_thickness_m or env.cladding_depth_m,
              reason='Wall plane. The opening is a subtraction from it, not a panel '
                     'that happens to be transparent.')

    if head_z - sill_z < 0.04:
        return

    # The reveal is what gives the mass its shadow; it is drawn, not implied.
    depth = env.reveal_depth_m
    if depth > 0.01:
        for tag, t in (('RVL', t0), ('RVR', t1)):
            dx, dy = bay.outward(depth / 2.0)
            centre = bay.at(t, (sill_z + head_z) / 2.0)
            b.add(f'ENV-RVL-{bay.level_id}-S{bay.si:03d}-{tag}', 'window_reveal',
                  'envelope', 'bearing_wall',
                  BoxGeometry(center=v3(centre.x - dx, centre.y - dy, centre.z),
                              size=v3(max(0.12, bay.width * 0.03), depth,
                                      head_z - sill_z)),
                  material, level_id=bay.level_id, lattice_index=bay.index,
                  datum_refs=refs,
                  reason='Reveal: the wall thickness shown at the opening edge.')
        dx, dy = bay.outward(depth / 2.0)
        for tag, z in (('HD', head_z), ('SL', sill_z)):
            centre = bay.at((t0 + t1) / 2.0, z)
            b.add(f'ENV-{tag}-{bay.level_id}-S{bay.si:03d}',
                  'window_head' if tag == 'HD' else 'sill', 'envelope', 'bearing_wall',
                  BoxGeometry(center=v3(centre.x - dx, centre.y - dy, z),
                              size=v3(bay.width * width_ratio, depth, 0.16)),
                  material, level_id=bay.level_id, lattice_index=bay.index,
                  datum_refs=refs,
                  reason='Head and sill close the reveal and read as one course.')

    b.add(f'ENV-GLZ-{bay.level_id}-S{bay.si:03d}', 'glazing_panel', 'envelope',
          'bearing_wall', bay.quad(t0, t1, sill_z, head_z, push=-depth * 0.8),
          env.infill_material, level_id=bay.level_id, lattice_index=bay.index,
          datum_refs=refs, thickness_m=env.glazing_depth_m,
          reason='Glazing set back within the reveal so the wall reads in front of it.')


# ---------------------------------------------------------------------------
# subdivide: a frame whose cells are the openings
# ---------------------------------------------------------------------------

def _bay_subdivided(b, bay: _Bay, env: EnvelopeTectonic, datums, *, opaque: bool,
                    row_z: list[float], spandrel_height: float, mullion_profile: str,
                    course: int) -> None:
    """A mullion-and-transom grid, or the same grid cut by seams.

    `ENV-CURTAIN-WALL` and `ENV-FACETED-PANEL` both subdivide, and the difference is
    what the subdivision answers to. The curtain wall answers to the module; the faceted
    skin staggers its joints course by course and lets two diagonal seams cut across the
    whole elevation, ignoring the structural grid entirely. That conflict between the
    panel geometry and the frame behind it is the grammar, not a decoration on it.
    """
    refs = ['mullion_module_m', 'fin_depth_m', 'envelope_offset_m', *PLATE_DATUMS]
    stagger = 0.5 if (env.stagger_panels and course % 2) else 0.0

    if opaque:
        b.add(f'ENV-SWP-{bay.level_id}-S{bay.si:03d}',
              'facet_panel' if env.stagger_panels else 'solid_wall_panel', 'envelope',
              'opaque_wall', bay.quad(stagger, 1.0 + stagger, bay.z_base, bay.z_head),
              env.wall_material if env.stagger_panels else env.trim_material,
              level_id=bay.level_id, lattice_index=bay.index,
              datum_refs=[*refs, 'opaque_fraction'],
              rule_refs=['GENRE_TO_OPAQUE_FRACTION'],
              thickness_m=env.wall_thickness_m or env.cladding_depth_m,
              reason='Opaque panel. The share of solid to glazed is proposed by the '
                     'timbral position and requires human acceptance.')
        if env.draws_mullions:
            b.add(f'ENV-MUL-{bay.level_id}-S{bay.si:03d}', 'mullion', 'envelope',
                  'opaque_wall',
                  MemberGeometry(path=[v3(bay.point.x, bay.point.y, bay.z_base),
                                       v3(bay.point.x, bay.point.y, bay.z_head)],
                                 profile=mullion_profile, roll=bay.roll),
                  env.trim_material, level_id=bay.level_id,
                  lattice_index=bay.index, datum_refs=refs,
                  reason='Panel joint expressed at the envelope module.')
        return

    if env.draws_mullions:
        b.add(f'ENV-MUL-{bay.level_id}-S{bay.si:03d}', 'mullion', 'envelope',
              'curtain_wall',
              MemberGeometry(path=[v3(bay.point.x, bay.point.y, bay.z_base),
                                   v3(bay.point.x, bay.point.y, bay.z_head)],
                             profile=mullion_profile, roll=bay.roll),
              env.trim_material, level_id=bay.level_id,
              lattice_index=bay.index, datum_refs=refs,
              rule_refs=['IS-INV-01', 'IS-INV-03', 'REPETITION_TO_MULLION'],
              reason='Vertical mullion at the envelope module the score set, with a '
                     'projection the timbral position proposed.')

    for r in range(len(row_z) - 1):
        za, zb = row_z[r], row_z[r + 1]
        if r == 0 and spandrel_height > 0.02:
            b.add(f'ENV-SPD-{bay.level_id}-S{bay.si:03d}', 'spandrel_panel', 'envelope',
                  'curtain_wall',
                  bay.quad(stagger, 1.0 + stagger, za, za + spandrel_height),
                  env.trim_material, level_id=bay.level_id,
                  lattice_index=bay.index,
                  datum_refs=['spandrel_height_m', 'mullion_module_m'],
                  rule_refs=['REPETITION_TO_SPANDREL'],
                  thickness_m=env.cladding_depth_m,
                  reason='Spandrel band closes the floor zone at the repeated height '
                         'the score set.')
            za += spandrel_height
        if zb - za < 0.05:
            continue
        b.add(f'ENV-GLZ-{bay.level_id}-S{bay.si:03d}-R{r:02d}',
              'facet_glazing' if env.stagger_panels else 'glazing_panel', 'envelope',
              'curtain_wall', bay.quad(stagger, 1.0 + stagger, za, zb),
              env.infill_material if env.stagger_panels else 'glass',
              level_id=bay.level_id, lattice_index={**bay.index, 'row': r},
              datum_refs=['transom_rows', 'mullion_module_m', 'envelope_offset_m'],
              thickness_m=env.glazing_depth_m,
              reason='Vision panel between adjacent mullions and transoms.')

    if env.draws_mullions:
        for r, zr in enumerate(row_z):
            b.add(f'ENV-TRN-{bay.level_id}-S{bay.si:03d}-R{r:02d}', 'transom',
                  'envelope', 'curtain_wall',
                  MemberGeometry(path=[v3(bay.point.x, bay.point.y, zr),
                                       v3(bay.nxt.x, bay.nxt.y, zr)],
                                 profile='TRAN-75x140'),
                  env.trim_material, level_id=bay.level_id,
                  lattice_index={**bay.index, 'row': r},
                  datum_refs=['transom_rows', 'mullion_module_m'],
                  reason='Horizontal transom at a declared row.')

    # The seams that make a faceted skin faceted. Two of them, running at a fixed rake
    # across the whole elevation, so they cross the structural grid rather than follow
    # it. A seam is drawn only where it passes through this bay.
    for s in range(env.diagonal_seams):
        rake = 0.55 + 0.35 * s
        t = (bay.si * 0.17 + s * 0.5) % 1.0
        z = bay.z_base + bay.height * ((t * rake) % 1.0)
        if not (bay.z_base + 0.15 < z < bay.z_head - 0.15):
            continue
        b.add(f'ENV-SEAM-{bay.level_id}-S{bay.si:03d}-D{s}', 'seam_edge', 'envelope',
              'facet_seam',
              MemberGeometry(path=[v3(bay.point.x, bay.point.y, z),
                                   v3(bay.nxt.x, bay.nxt.y,
                                      min(bay.z_head - 0.05, z + bay.height * 0.28))],
                             profile='EDGEBEAM-160'),
              env.trim_material, level_id=bay.level_id, lattice_index=bay.index,
              datum_refs=['mullion_module_m', 'plate_rotation_deg'],
              reason='Seam cutting across the panel courses at a rake that ignores the '
                     'structural grid.')


# ---------------------------------------------------------------------------
# recess: the frame is the elevation
# ---------------------------------------------------------------------------

def _bay_recessed(b, bay: _Bay, env: EnvelopeTectonic, datums, row_z: list[float],
                  mullion_profile: str, setback: float) -> None:
    """Glazing pushed back inside the bay, with the frame left in front of it."""
    refs = ['envelope_offset_m', 'mullion_module_m', *PLATE_DATUMS]
    push = -abs(setback)

    b.add(f'ENV-FRM-{bay.level_id}-S{bay.si:03d}', 'frame_expression', 'envelope',
          'expressed_frame',
          MemberGeometry(path=[v3(bay.point.x, bay.point.y, bay.z_base),
                               v3(bay.point.x, bay.point.y, bay.z_head)],
                         profile=mullion_profile, roll=bay.roll),
          env.wall_material, level_id=bay.level_id, lattice_index=bay.index,
          datum_refs=refs, rule_refs=['LAYERING_TO_EXPRESSED_FRAME'],
          reason='The frame member left standing in front of the glazing line, so the '
                 'structure reads as the elevation.')

    # A spandrel closes the floor zone behind the frame. Without it the recessed
    # family emitted nothing but glass, and the facade gate measured an opening ratio of
    # 1.00 against a published band of 0.45-0.85 -- correctly, because a building with
    # no opaque wall at all is not what the High-Tech guide describes either.
    spandrel = min(0.9, max(0.25, (row_z[1] - row_z[0]) * 0.55)) if len(row_z) > 1 else 0.0
    if spandrel > 0.05:
        b.add(f'ENV-SPD-{bay.level_id}-S{bay.si:03d}', 'spandrel_panel', 'envelope',
              'expressed_frame',
              bay.quad(0.0, 1.0, bay.z_base, bay.z_base + spandrel, push=push),
              env.trim_material, level_id=bay.level_id, lattice_index=bay.index,
              datum_refs=['spandrel_height_m', 'envelope_offset_m'],
              thickness_m=env.cladding_depth_m,
              reason='Spandrel closing the floor zone behind the expressed frame.')

    for r in range(len(row_z) - 1):
        za, zb = max(row_z[r], bay.z_base + spandrel), row_z[r + 1]
        if zb - za < 0.05:
            continue
        b.add(f'ENV-GLZ-{bay.level_id}-S{bay.si:03d}-R{r:02d}', 'glazing_panel',
              'envelope', 'expressed_frame', bay.quad(0.0, 1.0, za, zb, push=push),
              'glass', level_id=bay.level_id, lattice_index={**bay.index, 'row': r},
              datum_refs=['transom_rows', 'envelope_offset_m'],
              thickness_m=env.glazing_depth_m,
              reason='Vision panel set back inside the structural bay.')

    # The tie back to the frame, which is the detail High-Tech makes visible.
    dx, dy = bay.outward(abs(setback))
    mid_z = (bay.z_base + bay.z_head) / 2.0
    b.add(f'ENV-STR-{bay.level_id}-S{bay.si:03d}', 'external_strut', 'envelope',
          'expressed_frame',
          MemberGeometry(path=[v3(bay.point.x, bay.point.y, bay.z_base + 0.3),
                               v3(bay.point.x - dx, bay.point.y - dy, mid_z)],
                         profile='STRUT-CHS180'),
          env.trim_material, level_id=bay.level_id, lattice_index=bay.index,
          datum_refs=refs,
          reason='Strut tying the recessed skin back to the frame, drawn because the '
                 'grammar exists to show exactly this joint.')


# ---------------------------------------------------------------------------
# overlay: a second structure in front of the skin
# ---------------------------------------------------------------------------

def _bay_backing(b, bay: _Bay, env: EnvelopeTectonic, row_z: list[float],
                 opaque_fraction: float = 0.0) -> None:
    """The plain skin that an overlay tectonic stands its second structure in front of.

    The opaque share is honoured here and not only on the framed families. It was not,
    at first: the backing skin made row zero solid and everything above it glass, so an
    overlay grammar's opening ratio was a function of the transom count alone. That made
    it unresponsive to the score *and* impossible for the facade gate to correct, since
    the one lever the gate can pull was not connected to anything. Solid rows are taken
    from the bottom so the skin reads as a wall the screen stands on.
    """
    rows = max(1, len(row_z) - 1)
    solid_rows = int(round(rows * min(1.0, max(0.0, opaque_fraction))))
    for r in range(rows):
        za, zb = row_z[r], row_z[r + 1]
        if zb - za < 0.05:
            continue
        opaque = r < max(1, solid_rows)
        b.add(f'ENV-BCK-{bay.level_id}-S{bay.si:03d}-R{r:02d}',
              'backing_panel' if opaque else 'glazing_panel', 'envelope', 'backing_skin',
              bay.quad(0.0, 1.0, za, zb),
              env.wall_material if opaque else env.infill_material,
              level_id=bay.level_id, lattice_index={**bay.index, 'row': r},
              datum_refs=['transom_rows', 'envelope_offset_m'],
              thickness_m=env.cladding_depth_m,
              reason='Backing skin. It is deliberately plain: the layer in front of it '
                     'is what the elevation is.')


def _bay_lattice(b, bay: _Bay, env: EnvelopeTectonic, cells: int) -> None:
    """A deep grid of cells standing off the skin.

    Depth is the whole point. A shallow grid is a pattern; a grid deep enough to shade
    itself reads as shadow, which is why `outboard_depth_m` is large and the cell
    members are drawn as boxes rather than as lines.
    """
    depth = env.outboard_depth_m
    dx, dy = bay.outward(depth / 2.0)
    if not b.lattice.encloses(bay.point.x - dx, bay.point.y - dy):
        return
    refs = ['mullion_module_m', 'envelope_offset_m', 'envelope_layer_count',
            *PLATE_DATUMS]
    thickness = max(0.07, bay.width / 14.0)

    for c in range(cells + 1):
        z = bay.z_base + bay.height * c / cells
        centre = bay.at(0.5, z)
        b.add(f'ENV-LTT-{bay.level_id}-S{bay.si:03d}-H{c:02d}', 'lattice_transom',
              'envelope', 'lattice_screen',
              BoxGeometry(center=v3(centre.x - dx, centre.y - dy, z),
                          size=v3(bay.width, depth, thickness)),
              env.outboard_material, level_id=bay.level_id,
              lattice_index={**bay.index, 'cell': c}, datum_refs=refs,
              rule_refs=['LAYERING_TO_LATTICE'],
              reason='Lattice course. The screen is deep enough that its openings read '
                     'as shadow rather than as glass.')

    verticals = 2
    for vpos in range(verticals + 1):
        t = vpos / verticals
        centre = bay.at(t, (bay.z_base + bay.z_head) / 2.0)
        b.add(f'ENV-LTV-{bay.level_id}-S{bay.si:03d}-V{vpos:02d}', 'lattice_mullion',
              'envelope', 'lattice_screen',
              BoxGeometry(center=v3(centre.x - dx, centre.y - dy, centre.z),
                          size=v3(thickness, depth, bay.height)),
              env.outboard_material, level_id=bay.level_id,
              lattice_index={**bay.index, 'cell': vpos}, datum_refs=refs,
              reason='Lattice pier between cells.')


def _bay_field(b, bay: _Bay, env: EnvelopeTectonic, rows: int, columns: int,
               level_t: float) -> None:
    """A field of small panels whose depth varies along an axis.

    An even field of one panel is a rainscreen. What makes this a field is that the
    depth is a function of position, so the wall reads as a gradient. The axis comes
    from the grammar: Parametricism varies it vertically from the ground, Organic blooms
    it radially around the entrance.
    """
    lo, hi = env.field_depth_range_m
    refs = ['mullion_module_m', 'envelope_offset_m', 'shading_depth_m', *PLATE_DATUMS]

    for r in range(rows):
        for c in range(columns):
            u = (c + 0.5) / columns
            v = (r + 0.5) / rows
            if env.field_axis == 'radial':
                # distance from the entrance, which sits at the middle of the base
                d = math.hypot((u - 0.5) * 1.4, (v + level_t) * 0.9)
                weight = max(0.0, 1.0 - d)
            else:
                weight = max(0.0, 1.0 - (v * 0.45 + level_t * 0.75))
            depth = lo + (hi - lo) * weight
            if depth < lo + (hi - lo) * 0.06:
                continue
            dx, dy = bay.outward(depth / 2.0)
            z = bay.z_base + bay.height * v
            centre = bay.at(u, z)
            if not b.lattice.encloses(centre.x - dx, centre.y - dy):
                continue
            b.add(f'ENV-FLD-{bay.level_id}-S{bay.si:03d}-R{r:02d}C{c:02d}',
                  'field_panel', 'envelope', 'panel_field',
                  BoxGeometry(center=v3(centre.x - dx, centre.y - dy, z),
                              size=v3(bay.width / columns * 0.86, depth,
                                      bay.height / rows * 0.86)),
                  env.outboard_material, level_id=bay.level_id,
                  lattice_index={**bay.index, 'row': r, 'col': c}, datum_refs=refs,
                  rule_refs=['LAYERING_TO_PANEL_FIELD'],
                  reason='Field panel. Its projection is a function of where it sits, '
                         'so the wall reads as a gradient rather than a pattern.')


def _emit_applied_order(b, env: EnvelopeTectonic, lattice, datums) -> None:
    """One giant frame applied to the principal elevation, centred on the entrance.

    This is scenography stuck to the front of a building and the emitter does not
    pretend otherwise: the order carries no load, is not tied to the frame, and is
    recorded as `architectural_convention` like every other member here that a
    calculation did not govern.
    """
    occupied = lattice.occupied
    if not occupied:
        return
    south = min(p.y for p in occupied[0].plate)
    xs = [p.x for p in occupied[0].plate]
    centre_x = (min(xs) + max(xs)) / 2.0
    top = occupied[min(len(occupied) - 1, max(1, int(len(occupied) * 0.8)))].z
    base = occupied[0].z
    width = (max(xs) - min(xs)) * 0.52
    depth = env.outboard_depth_m
    jamb = max(0.8, width * 0.11)
    refs = ['entry_canopy_span_m', 'floor_to_floor_m', *PLATE_DATUMS]

    for side, sign in (('L', -1.0), ('R', 1.0)):
        b.add(f'ENV-ORD-JAMB-{side}', 'order_jamb', 'envelope', 'applied_order',
              BoxGeometry(
                  center=v3(centre_x + sign * (width / 2.0 - jamb / 2.0),
                            south - depth / 2.0, (base + top) / 2.0),
                  size=v3(jamb, depth, top - base)),
              env.outboard_material, level_id=occupied[0].id, datum_refs=refs,
              rule_refs=['INCIDENT_TO_APPLIED_ORDER'],
              reason='Pier of the applied order. It carries no load and is recorded as '
                     'convention, because that is what it is.')

    b.add('ENV-ORD-LINTEL', 'order_lintel', 'envelope', 'applied_order',
          BoxGeometry(center=v3(centre_x, south - depth / 2.0, top - jamb / 2.0),
                      size=v3(width, depth, jamb)),
          env.outboard_material, level_id=occupied[0].id, datum_refs=refs,
          reason='Lintel closing the applied order over the entrance.')


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

def emit_envelope(b, env: EnvelopeTectonic, spec: GrammarSpec | None = None,
                  opacity_override: float | None = None) -> None:
    """Build the envelope for one tectonic family, under its grammar's own spec.

    `env` says what operation the elevation performs; `spec` says how far the music
    is allowed to push it and within what bounds the guide expects the result to
    land. Passing `None` runs the tectonic at full score authority, which is what
    the older tests expect and what a grammar with no published limits would get.
    """
    lattice, datums = b.lattice, b.datums
    module = datums.value('mullion_module_m')
    if spec:
        # The guide publishes the module range the grammar is set out on. Brutalism
        # runs 1.8-4.8 m inhabited bays; Bauhaus runs a 0.6-1.5 m standard unit.
        # Clamping here is what stops a score from handing one grammar the other's
        # grain while keeping its name.
        low, high = spec.module_range_m
        module = min(high, max(low, module))
    rows = max(1, datums.integer('transom_rows'))
    spandrel_height = datums.value('spandrel_height_m')
    offset = datums.value('envelope_offset_m') * env.setback_multiplier
    layers = max(1, datums.integer('envelope_layer_count'))
    fascia = datums.value('edge_fascia_m')
    f2f = datums.value('floor_to_floor_m')
    shading_rows = max(0, datums.integer('shading_rows'))

    # The tectonic sets the floor on how solid the wall is; the score moves it upward
    # from there, but only as far as the grammar's own guide permits. Minimalism caps
    # score-driven dimensional variation at 12 % in writing, so a minimalist elevation
    # under a loud recording must stay a minimalist elevation; Parametricism allows 70 %
    # and expects the field to swing. Applying that authority here is the difference
    # between implementing the guides and citing them.
    authority = spec.score_authority if spec else 1.0
    score_opacity = min(0.9, max(0.0, datums.value('opaque_fraction')))
    headroom = 1.0 - env.base_opacity
    opaque_fraction = min(
        0.96, env.base_opacity + score_opacity * headroom * authority)
    if opacity_override is not None:
        # The facade gate measured an opening ratio outside the band the grammar's
        # guide publishes and asked for one specific number back. Honouring it here
        # rather than clamping the datum keeps the correction visible: the datum
        # still records what the music asked for, and the model records that a gate
        # overrode it.
        opaque_fraction = min(0.96, max(0.0, opacity_override))

    mullion_profile = b.profile(convention_profile(
        f'MULL-{env.mullion_profile_depth_m * 1000:.0f}x75', 'box',
        env.mullion_profile_depth_m, 0.075))

    occupied = list(lattice.occupied)
    for course, level in enumerate(occupied):
        if level.is_terrace:
            continue
        z_base = level.z
        z_head = z_base + f2f - fascia
        outboard = inset(level.plate, -abs(offset) if offset >= 0 else 0.0)
        stations = polyline_stations(outboard, module)
        if not stations:
            continue
        row_z = [z_base + (z_head - z_base) * r / rows for r in range(rows + 1)]
        level_t = course / max(1, len(occupied) - 1)

        # The narrowest panel a bay of this family contains, as a share of the bay.
        # A punched wall's jamb is the slenderest thing on it; a curtain wall's panels
        # span the whole bay.
        min_fragment = spec.minimum_fragment_m if spec else 0.30
        narrowest_share = 1.0

        visible = [i for i, (point, _) in enumerate(stations)
                   if lattice.encloses(point.x, point.y)]
        opaque_count = int(round(len(visible) * opaque_fraction))
        opaque_set = set(sorted(visible, key=lambda i: -stations[i][0].x)[:opaque_count])
        south_y = min(p.y for p in outboard)
        # Where the way in is. Every door in the model was between two program zones:
        # the envelope was sealed, the entry canopy stood outside an unbroken glass
        # wall, and no plan could show how anyone gets into the building. The entrance
        # sits on the plan's own centre line, which is where the canopy is placed from
        # the same derivation.
        entry_x = (min(point.x for point in outboard)
                   + max(point.x for point in outboard)) / 2.0
        entry_span = max(ENTRANCE_MIN_WIDTH_M,
                         min(ENTRANCE_MAX_WIDTH_M,
                             datums.value('entry_canopy_span_m') * 0.55))

        for si, (point, angle) in enumerate(stations):
            if si not in visible:
                continue
            nxt = stations[(si + 1) % len(stations)][0]
            span = math.hypot(nxt.x - point.x, nxt.y - point.y)
            if span > module * 1.8:
                continue
            # A wall does not end in an offcut. `polyline_stations` leaves a short
            # remainder where a run meets a corner, and drawing a full bay's worth of
            # panels and openings into it produced eleven-centimetre jambs -- which the
            # facade gate caught, and which every guide that mentions slivers forbids.
            #
            # The limit is the grammar's own declared minimum fragment applied to the
            # narrowest panel the bay would contain, not a fraction of the module. A
            # fraction of the module was the first attempt and it was subtly wrong: it
            # scaled with the very quantity `repetition` moves, so tightening the module
            # dropped bays in step and the mullion count stopped rising with it.
            if env.opening_logic == 'subtract' and env.opening_width_ratio > 0.0:
                opening = effective_opening_width(env, span, min_fragment)
                narrowest_share = max(0.02, min(opening, (1.0 - opening) / 2.0))
            if span * narrowest_share < min_fragment:
                continue
            bay = _Bay(point, nxt, z_base, z_head, angle,
                       {'level': level.index, 'station': si}, level.id, si,
                       point.y < south_y + 0.8)
            if (course == 0 and bay.is_principal
                    and abs((point.x + nxt.x) / 2.0 - entry_x) <= entry_span / 2.0):
                _emit_entrance(b, bay, env, datums)
                continue

            if env.opening_logic == 'subtract':
                _bay_punched(b, bay, env, datums, min_fragment)
            elif env.opening_logic == 'recess':
                _bay_recessed(b, bay, env, datums, row_z, mullion_profile, offset)
            elif env.opening_logic == 'overlay':
                _bay_backing(b, bay, env, row_z, opaque_fraction)
                if env.outboard == 'lattice':
                    _bay_lattice(b, bay, env, max(2, env.outboard_rows_per_storey))
                elif env.outboard == 'field':
                    # A field is made of small panels, but not of offcuts. The
                    # column and row counts are capped so no panel face falls below
                    # the minimum the grammar's guide publishes.
                    columns = max(1, min(int(round(module / 0.9)),
                                         int(bay.width / (min_fragment * 1.15))))
                    rows = max(1, min(env.outboard_rows_per_storey,
                                      int(bay.height / (min_fragment * 1.15))))
                    _bay_field(b, bay, env, rows, columns, level_t)
            else:
                _bay_subdivided(b, bay, env, datums,
                                opaque=si in opaque_set, row_z=row_z,
                                spandrel_height=spandrel_height,
                                mullion_profile=mullion_profile, course=course)

            # Polyphony's second voice. An overlay family already has one -- the
            # lattice or the field *is* the second voice -- so adding a fin there
            # would be saying the same thing twice. A framed or punched elevation has
            # no second layer of its own, so the fin is what keeps polyphony reaching
            # geometry in those families instead of quietly dropping out of the model.
            if layers >= 2 and env.outboard == 'none':
                _emit_screen_fin(b, bay, env, abs(offset))

            # The shading comb survives from the original emitter, on the families
            # whose skin has room for it. A punched wall or a lattice already does this
            # work with its own depth, and adding a comb would be saying it twice.
            if (layers >= 3 and bay.is_principal
                    and env.opening_logic in ('subdivide', 'recess')):
                _emit_shading(b, bay, datums, shading_rows, module, env)

    if env.outboard == 'order':
        _emit_applied_order(b, env, lattice, datums)


# An entrance is wider than a door and narrower than a shopfront.
ENTRANCE_MIN_WIDTH_M = 2.4
ENTRANCE_MAX_WIDTH_M = 7.2
# Head height of the entrance screen. Above it the wall resumes.
ENTRANCE_HEAD_M = 2.6


def _emit_entrance(b, bay: _Bay, env: EnvelopeTectonic, datums) -> None:
    """The opening in the envelope, and the doors in it.

    This bay would otherwise take the family's ordinary infill, which is what sealed
    the building: the plan showed a continuous wall on every face and an entry canopy
    standing outside it. An entrance is a hole in the enclosure with leaves in it and
    a panel over the head, and all three are drawn, because in plan the hole is the
    information -- the leaves swing inside it and the head is what tells a section the
    wall carries on above.
    """
    leaf = min(1.1, bay.width / 2.0)
    head_z = min(bay.z_head, bay.z_base + ENTRANCE_HEAD_M)
    refs = ['entry_canopy_span_m', 'mullion_module_m']
    # The family's own materials, not new ones. Hard-coding glass and trim here put a
    # fourth material family on the Deconstructivist elevation, whose guide caps the
    # visible count at three -- and the facade gate failed it, correctly. An entrance
    # is a hole in this wall, so it is made of what this wall is made of.

    for index, (t0, t1) in enumerate(((0.0, 0.5), (0.5, 1.0))):
        b.add(f'ENV-ENT-{bay.level_id}-S{bay.si:03d}-L{index}', 'entrance_door',
              'envelope', 'entrance', bay.quad(t0, t1, bay.z_base, head_z),
              env.infill_material, level_id=bay.level_id, lattice_index=bay.index,
              datum_refs=refs, thickness_m=env.glazing_depth_m,
              rule_refs=['ADA-404.2.3', 'IBC-1010.1.1'],
              reason=f'Entrance leaf, {leaf * 1000:.0f} mm, in the opening on the '
                     f'plan centre line. The envelope had no way through it at all.')
    if bay.z_head - head_z > 0.05:
        b.add(f'ENV-ENT-{bay.level_id}-S{bay.si:03d}-HD', 'entrance_head', 'envelope',
              'entrance', bay.quad(0.0, 1.0, head_z, bay.z_head),
              env.wall_material, level_id=bay.level_id, lattice_index=bay.index,
              datum_refs=refs, thickness_m=env.cladding_depth_m,
              reason='Panel over the entrance head: the wall resumes above the '
                     'opening rather than the opening running to the soffit.')


def _emit_screen_fin(b, bay: _Bay, env: EnvelopeTectonic, offset: float) -> None:
    """The second envelope voice on a family that has no outboard layer of its own.

    The standoff is checked against the sectional cut, not just the station it hangs
    from. A fin on the last visible bay of the south face projects sideways at the
    corner and can land a few centimetres into the cut region, which reads in a
    render as one stray member floating past the end of the wall.
    """
    depth = max(0.12, offset * 0.55)
    dx, dy = bay.outward(depth)
    if not b.lattice.encloses(bay.point.x - dx, bay.point.y - dy):
        return
    # What holds the fin out there. A fin stands off the skin by `depth`, so its
    # centre-line never crosses the carrier's and no amount of geometry inspection
    # will pair the two -- the relation has to be declared. Emitted without one, the
    # fin was the largest floating population in the model: a rule downstream guessed
    # a host for it afterwards, which reads as an answer while resting on nothing.
    # It brackets back to the carrier standing at the same bay station.
    # A mullion at the same bay station where the family has one. Several families
    # have none -- a punched wall carries its skin in the wall itself -- and there the
    # fin brackets back to the floor-edge fascia running along the plate at its base,
    # which is the member a bracket would reach in the built version too.
    carrier = next(
        (candidate for candidate in
         (f'ENV-FRM-{bay.level_id}-S{bay.si:03d}', f'ENV-STR-{bay.level_id}-S{bay.si:03d}')
         if candidate in b.element_ids), None)
    if carrier is None:
        carrier = b.axis.nearest_owner(
            v3(bay.point.x - dx, bay.point.y - dy, bay.z_base),
            f'STR-FAS-{bay.level_id}-')
    if carrier is None:
        return
    b.add(f'ENV-SCR-{bay.level_id}-S{bay.si:03d}', 'screen_fin', 'envelope', 'screen',
          MemberGeometry(
              path=[v3(bay.point.x - dx, bay.point.y - dy, bay.z_base),
                    v3(bay.point.x - dx, bay.point.y - dy, bay.z_head)],
              profile=b.profile(convention_profile(
                  f'SCREEN-{depth * 1000 * 0.75:.0f}x50', 'box', depth * 0.75, 0.050)),
              roll=bay.roll),
          env.trim_material, level_id=bay.level_id, lattice_index=bay.index,
          datum_refs=['envelope_layer_count', 'envelope_offset_m'],
          supports=[carrier],
          rule_refs=['POLYPHONY_TO_ENVELOPE_LAYERS'],
          reason='Screen fin: the second envelope voice, standing off the skin so both '
                 'layers stay readable. Bracketed back to the carrier at its bay.')


def _emit_shading(b, bay: _Bay, datums, shading_rows: int, module: float,
                  env: EnvelopeTectonic | None = None) -> None:
    depth = datums.value('shading_depth_m')
    for k in range(shading_rows):
        z = bay.z_base + bay.height * (0.40 + 0.26 * k)
        if z > bay.z_head - 0.1:
            break
        centre = bay.at(0.5, z)
        b.add(f'ENV-BRS-{bay.level_id}-S{bay.si:03d}-R{k:02d}', 'brise_soleil',
              'envelope', 'shading',
              BoxGeometry(center=v3(centre.x, centre.y - depth / 2.0, z),
                          size=v3(module, depth, 0.06)),
              env.trim_material if env else 'white_soft',
              level_id=bay.level_id, lattice_index={**bay.index, 'row': k},
              datum_refs=['shading_rows', 'shading_depth_m'],
              rule_refs=['TENSION_TO_SHADING_DEPTH'],
              reason='Shading comb: the third envelope voice, at the projection the '
                     'release set.')
