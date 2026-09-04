"""Tectonic families: what a chosen system or grammar actually builds.

The corpus test that prompted this module produced fourteen buildings from fourteen
recordings spanning Baroque harpsichord to hardcore punk, and every one of them used the
same thirty-five kinds of element. Element *counts* varied by up to 1.9x; the element
*vocabulary* varied between 35 and 36. That is the precise shape of the complaint that
the models all look alike: the datum chain was moving quantities inside a single
tectonic, and nothing was moving the tectonic itself.

`coupling.py` already knew about ten structural systems and ten facade grammars, and
`codes.py` already screened them. But `compiler_v3.py` held three constants --
`STRUCTURAL_SYSTEM_ID`, `typology`, `tectonic_system` -- and emitted one steel frame
behind one curtain wall no matter what survived the screen. The screening layer was a
parallel document generator, not a pipeline stage.

This module is the missing vocabulary. A tectonic family says what a system or a grammar
is *made of* and *how it goes together*: which members exist, in what material, at what
proportion, and which assemblies are absent. Two buildings in different families differ
in what kinds of element they contain, which is what the eye reads as style; two
buildings in the same family differ only in count, which is what the eye reads as the
same building twice.

The bar these families are cut to is a facade comparison at constant massing: same
volume, same base, same entrance, and skins that are unmistakably different -- a blank
plane with a single slot next to a deep lattice screen next to a field of panels whose
depth varies. Getting that contrast means the opening logic has to change, not only the
module. A curtain wall subdivides; a punched wall subtracts; a lattice adds a second
structure in front of the first. Those are different operations on the elevation, and
they are what these records encode.

**What is deliberately not here.** Five of the ten structural systems -- the two shells,
the gridshell, the tensile membrane and the cable net -- index their elements into
surface parameters (`SHL-RIB-U012`, `SHL-EDGE-V003`) rather than into levels. They need
a skeleton this compiler does not have, and the guidelines say so. They are recorded here
as `implemented=False` and screened out with a stated reason, because emitting a steel
frame while labelling it a concrete shell would be the exact failure this project exists
to avoid.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

EnvelopeTectonicId = Literal[
    'ENV-CURTAIN-WALL', 'ENV-PUNCHED-WALL', 'ENV-BLANK-SLOT', 'ENV-DEEP-LATTICE',
    'ENV-PANEL-FIELD', 'ENV-FACETED-PANEL', 'ENV-APPLIED-ORDER', 'ENV-EXPRESSED-FRAME',
]
FrameTectonicId = Literal[
    'FRM-STEEL', 'FRM-CONCRETE', 'FRM-MASS-TIMBER', 'FRM-HEAVY-TIMBER',
]

# How an elevation gets its openings. This is the field that separates the families
# from each other more than any dimension does, because it decides what operation the
# emitter performs rather than how large the result is.
#
#   subdivide  -- a frame is drawn and the openings are the cells left between members
#   subtract   -- a wall plane is drawn and the openings are holes cut out of it
#   overlay    -- a plain skin is drawn and a second structure stands in front of it
#   recess     -- the skin is pushed back inside the structural bay and the frame reads
#
OpeningLogic = Literal['subdivide', 'subtract', 'overlay', 'recess']


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------

class EnvelopeTectonic(BaseModel):
    """One way of building an exterior wall, as geometry rather than as a label."""

    id: EnvelopeTectonicId
    label: str
    opening_logic: OpeningLogic
    wall_material: str
    infill_material: str

    # --- the wall plane itself ---------------------------------------------------
    # Share of the elevation that is wall before the score's own opaque_fraction
    # applies. A punched wall is mostly wall whatever the music says; a curtain wall
    # is mostly glass. The score moves this within the family; it cannot move between
    # families, which is what keeps a grammar recognisable.
    #
    # Every value here sits inside the opening band the served grammar's guide
    # publishes, so a tectonic with no music behind it at all still lands where its
    # guide expects. That was not true at first: the curtain wall sat at 0.05 while
    # International Style publishes an opening band of 0.25-0.75, so the tectonic was
    # outside its own guide and only the score could rescue it -- which put the
    # opening-ratio gate and the score-authority gate in direct conflict, each
    # correctly reporting the other's fix as a violation. Where one tectonic serves
    # two grammars the value sits in the overlap of both bands.
    base_opacity: float = Field(ge=0.0, le=1.0)
    # A hole in a solid wall has a thickness to show. A curtain wall has none.
    reveal_depth_m: float = 0.0
    # The opaque wall's own build-up: structure, insulation, both linings. Read by the
    # envelope emitters and carried through to the model so the exporter can give the
    # panel a body. It was declared here from the start and used by nothing, which is
    # how a 450 mm bearing wall came to be drawn as a line.
    wall_thickness_m: float = 0.0
    # The depth of a cladding or infill panel measured off the wall plane behind it: a
    # rainscreen cassette, a spandrel unit, a backing panel. Thinner than the wall,
    # and still not nothing -- at zero the panel cannot be cut and the elevation has
    # no edge to show in plan.
    cladding_depth_m: float = 0.075
    # Glass plus its frame zone. A sealed double unit is about 28 mm; the frame it sits
    # in makes the assembly roughly twice that, and it is the assembly a plan cuts.
    glazing_depth_m: float = 0.055

    # --- openings, when the logic is `subtract` ----------------------------------
    # Openings per structural bay, and how tall they are as a share of the clear
    # storey. `ENV-BLANK-SLOT` gets one narrow opening; a punched wall gets a row.
    openings_per_bay: int = 0
    opening_width_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    opening_height_ratio: float = Field(default=0.0, ge=0.0, le=1.0)

    # --- the outboard structure, when the logic is `overlay` ---------------------
    # 'none' | 'lattice' -- a grid of deep cells | 'field' -- small panels at varying
    # depth | 'order' -- one giant applied frame around the principal elevation
    outboard: Literal['none', 'lattice', 'field', 'order'] = 'none'
    outboard_material: str = 'white'
    outboard_depth_m: float = 0.0
    # Cells per storey vertically; horizontal count follows the module datum.
    outboard_rows_per_storey: int = 0
    # A field varies its panel depth along an axis. Vertical reads as a gradient from
    # the ground; radial reads as a bloom around the entrance.
    field_axis: Literal['none', 'vertical', 'radial'] = 'none'
    field_depth_range_m: tuple[float, float] = (0.0, 0.0)

    # --- panelised skins ---------------------------------------------------------
    # Panel joints stagger course to course, which is what makes cladding read as
    # cladding rather than as a grid.
    stagger_panels: bool = False
    # A diagonal seam cut across the panel courses. Deconstructivism's motif, and the
    # one operation here that deliberately ignores the structural grid.
    diagonal_seams: int = 0

    # --- how the skin sits relative to the frame ---------------------------------
    # Negative recesses it into the structural bay so the frame becomes the elevation.
    setback_multiplier: float = 1.0
    mullion_profile_depth_m: float = 0.240
    draws_mullions: bool = True

    # The third material a family may show, for spandrels, joints and fins. Named
    # here rather than reached for in the emitter, because the guides cap how many
    # materials an elevation may carry and a hardcoded `white_soft` in the emitter
    # is a fourth material nobody declared. The facade gate counts what was drawn.
    trim_material: str = 'white_soft'

    signature_kinds: tuple[str, ...] = ()
    note: str


ENVELOPE_TECTONICS: dict[str, EnvelopeTectonic] = {
    t.id: t for t in (
        EnvelopeTectonic(
            id='ENV-CURTAIN-WALL', trim_material='frame_dark', label='Curtain wall',
            cladding_depth_m=0.180, glazing_depth_m=0.055,
            opening_logic='subdivide',
            wall_material='steel_white', infill_material='glass',
            base_opacity=0.3, mullion_profile_depth_m=0.240,
            signature_kinds=('mullion', 'transom', 'spandrel_panel', 'glazing_panel'),
            note='A mullion-and-transom cage hung off the plate edge. The elevation is '
                 'a grid, and the opaque share is a run of spandrel inside that grid.'),

        EnvelopeTectonic(
            id='ENV-PUNCHED-WALL', trim_material='concrete', label='Punched bearing wall',
            cladding_depth_m=0.090, glazing_depth_m=0.070,
            opening_logic='subtract',
            wall_material='concrete', infill_material='glass',
            # Wider and taller than the first pass, and deeper. At 0.46 x 0.52 on a
            # repeated module the elevation read as a grid of narrow slots -- a
            # curtain wall in masonry -- which is the opposite of what BR-INV-04
            # asks for. One large cut per inhabited bay, with a reveal deep enough
            # to throw a real shadow, is the grammar. Area ratio 0.33, inside the
            # guide's published 0.10-0.45.
            base_opacity=0.66, reveal_depth_m=0.72, wall_thickness_m=0.45,
            openings_per_bay=1, opening_width_ratio=0.58, opening_height_ratio=0.57,
            draws_mullions=False,
            signature_kinds=('wall_panel', 'window_reveal', 'window_head', 'sill'),
            note='A wall plane with openings cut out of it, drawn as an extrusion with '
                 'holes so an opening is a subtraction rather than a panel that happens '
                 'to be transparent. Deep reveals give the mass its shadow.'),

        EnvelopeTectonic(
            id='ENV-BLANK-SLOT', trim_material='concrete_light', label='Blank plane with a slot',
            cladding_depth_m=0.075, glazing_depth_m=0.070,
            opening_logic='subtract',
            wall_material='concrete_light', infill_material='glass',
            base_opacity=0.86, reveal_depth_m=0.28, wall_thickness_m=0.34,
            openings_per_bay=1, opening_width_ratio=0.09, opening_height_ratio=0.74,
            draws_mullions=False,
            signature_kinds=('wall_panel', 'slot_opening', 'sill'),
            note='Very nearly a solid plane. One tall narrow slot per bay and nothing '
                 'else, so the wall is read as a single surface and the opening as an '
                 'incision in it. The restraint is the whole grammar.'),

        EnvelopeTectonic(
            id='ENV-DEEP-LATTICE', trim_material='terracotta', label='Deep lattice screen',
            cladding_depth_m=0.220, glazing_depth_m=0.055,
            opening_logic='overlay',
            wall_material='steel_light', infill_material='glass',
            base_opacity=0.55,
            outboard='lattice', outboard_material='terracotta',
            outboard_depth_m=0.55, outboard_rows_per_storey=5,
            setback_multiplier=1.7, mullion_profile_depth_m=0.140,
            signature_kinds=('lattice_cell', 'lattice_mullion', 'lattice_transom'),
            note='A plain backing skin behind a full-height grid of deep cells. The '
                 'lattice, not the glazing, is the elevation, and it is deep enough '
                 'that the openings read as shadow rather than as glass.'),

        EnvelopeTectonic(
            id='ENV-PANEL-FIELD', trim_material='white', label='Panel field with varying depth',
            cladding_depth_m=0.140, glazing_depth_m=0.055,
            opening_logic='overlay',
            wall_material='steel_light', infill_material='white_soft',
            base_opacity=0.45,
            outboard='field', outboard_material='white',
            # Fewer, larger panels over a wider depth range. Seven rows of shallow
            # panels averaged out into a flat band at any viewing distance, so the
            # gradient -- the thing that makes this a field and not a rainscreen --
            # was invisible in every render. The range stays inside the guide's
            # published 0.04-0.45 m.
            outboard_depth_m=0.44, outboard_rows_per_storey=4,
            field_axis='vertical', field_depth_range_m=(0.03, 0.44),
            setback_multiplier=1.35, mullion_profile_depth_m=0.120,
            signature_kinds=('field_panel', 'field_carrier'),
            note='A dense field of small panels whose depth varies along an axis, so '
                 'the wall reads as a gradient rather than a pattern. The variation is '
                 'the point: an even field of the same panel is a rainscreen, not this.'),

        EnvelopeTectonic(
            id='ENV-FACETED-PANEL', trim_material='frame_dark', label='Faceted panel skin',
            cladding_depth_m=0.160, glazing_depth_m=0.055,
            opening_logic='subdivide',
            wall_material='steel_light', infill_material='white_soft',
            base_opacity=0.52, stagger_panels=True, diagonal_seams=2,
            mullion_profile_depth_m=0.100,
            signature_kinds=('facet_panel', 'seam_edge', 'facet_glazing'),
            note='Large cladding panels with staggered joints, cut across by diagonal '
                 'seams that ignore the structural grid and open into glazing where '
                 'they cross. The conflict between the two geometries is the grammar.'),

        EnvelopeTectonic(
            id='ENV-APPLIED-ORDER', trim_material='concrete_light', label='Applied order on a flat wall',
            cladding_depth_m=0.110, glazing_depth_m=0.060, wall_thickness_m=0.320,
            opening_logic='overlay',
            wall_material='concrete_light', infill_material='glass',
            base_opacity=0.60,
            outboard='order', outboard_material='accent_red', outboard_depth_m=0.24,
            openings_per_bay=1, opening_width_ratio=0.34, opening_height_ratio=0.48,
            draws_mullions=False,
            signature_kinds=('order_jamb', 'order_lintel', 'order_field', 'wall_panel'),
            note='A flat panelled wall with one giant frame applied to the principal '
                 'elevation, centred on the entrance and running most of the height. '
                 'The order is scenography stuck to the front, and says so.'),

        EnvelopeTectonic(
            id='ENV-EXPRESSED-FRAME', trim_material='steel_dark', label='Expressed frame, recessed glazing',
            cladding_depth_m=0.200, glazing_depth_m=0.055,
            opening_logic='recess',
            wall_material='steel_dark', infill_material='glass',
            base_opacity=0.22, setback_multiplier=-0.60,
            mullion_profile_depth_m=0.180,
            signature_kinds=('frame_expression', 'external_strut', 'mullion', 'transom'),
            note='The glazing is pushed back inside each structural bay so the frame '
                 'itself becomes the elevation, with external struts tying the skin '
                 'back to the columns.'),
    )
}


# ---------------------------------------------------------------------------
# Frame
# ---------------------------------------------------------------------------

class FrameTectonic(BaseModel):
    """One way of building a gravity frame that stands on a level lattice.

    `floor_system` changes the section drawing most: a joisted floor shows ribs under
    every plate, a flat slab shows a blank soffit and no secondary tier at all, and a
    panel floor shows wide bands. `lateral_kind` changes the elevation -- a braced bay
    is a diagonal, a shear wall is a plane, and a knee-braced post is a triangulated
    joint at every connection.
    """

    id: FrameTectonicId
    label: str
    column_material: str
    beam_material: str
    floor_system: Literal['joisted', 'flat_slab', 'panel', 'heavy_joist']
    lateral_kind: Literal['braced_bay', 'shear_wall', 'core_wall', 'knee_brace']
    # Members get fatter as they get weaker in bending per unit area. Applied to the
    # section the load calculation chose, so the drawn member still reports the checked
    # section and records where the difference came from.
    member_width_factor: float = Field(gt=0)
    # Timber and concrete want shorter spans than steel at the same depth.
    bay_span_factor: float = Field(gt=0)
    # A concrete flat slab is thicker than a composite deck; CLT thicker again.
    slab_thickness_factor: float = Field(gt=0)
    exposes_connections: bool = False
    signature_kinds: tuple[str, ...] = ()
    note: str


FRAME_TECTONICS: dict[str, FrameTectonic] = {
    t.id: t for t in (
        FrameTectonic(
            id='FRM-STEEL', label='Steel frame',
            column_material='steel_white', beam_material='steel_white',
            floor_system='joisted', lateral_kind='braced_bay',
            member_width_factor=1.0, bay_span_factor=1.0, slab_thickness_factor=1.0,
            signature_kinds=('column', 'girder', 'joist', 'brace'),
            note='Slender rolled sections, a secondary joist tier, and diagonal braced '
                 'bays. The lightest vocabulary in the set.'),
        FrameTectonic(
            id='FRM-CONCRETE', label='Reinforced concrete frame and wall',
            column_material='concrete', beam_material='concrete',
            floor_system='flat_slab', lateral_kind='shear_wall',
            member_width_factor=1.55, bay_span_factor=0.82, slab_thickness_factor=1.45,
            signature_kinds=('column', 'drop_panel', 'shear_wall'),
            note='Blockier columns, no secondary tier at all -- a flat slab on drop '
                 'panels -- and shear-wall planes instead of diagonals. The section '
                 'reads as blank soffits.'),
        FrameTectonic(
            id='FRM-MASS-TIMBER', label='Mass timber, CLT on glulam',
            column_material='timber', beam_material='timber',
            floor_system='panel', lateral_kind='core_wall',
            member_width_factor=1.70, bay_span_factor=0.75, slab_thickness_factor=1.30,
            exposes_connections=True,
            signature_kinds=('column', 'girder', 'clt_panel', 'core_wall'),
            note='Wide glulam posts and beams carrying CLT panel bands. No joists and '
                 'no diagonals; a timber core does the lateral work.'),
        FrameTectonic(
            id='FRM-HEAVY-TIMBER', label='Glulam post and beam',
            column_material='timber', beam_material='timber',
            floor_system='heavy_joist', lateral_kind='knee_brace',
            member_width_factor=1.85, bay_span_factor=0.68, slab_thickness_factor=1.15,
            exposes_connections=True,
            signature_kinds=('column', 'girder', 'heavy_joist', 'knee_brace'),
            note='Fewer, wider bays with a knee brace at every post-to-beam joint. The '
                 'triangulated corner is the motif that identifies it across a room.'),
    )
}


# ---------------------------------------------------------------------------
# What the compiler can actually build
# ---------------------------------------------------------------------------

class SystemBuildability(BaseModel):
    """Whether `compiler_v3` can emit a given structural system, and honestly why not.

    A system whose elements index into surface parameters cannot be emitted by a
    compiler whose skeleton is a stack of levels. Saying so here, and screening on it,
    is what stops the pipeline from labelling a steel frame as a shell.
    """

    system_id: str
    implemented: bool
    frame_tectonic: FrameTectonicId | None = None
    reason: str


SYSTEM_BUILDABILITY: dict[str, SystemBuildability] = {
    entry.system_id: entry for entry in (
        SystemBuildability(
            system_id='STR-SYS-STEEL-FRAME', implemented=True,
            frame_tectonic='FRM-STEEL',
            reason='Level lattice, rolled sections, joisted floor.'),
        SystemBuildability(
            system_id='STR-SYS-RC-FRAME-WALL', implemented=True,
            frame_tectonic='FRM-CONCRETE',
            reason='Level lattice, flat slab on drop panels, shear-wall planes. Sized '
                   'by ACI 318-19: Whitney stress block for flexure with the '
                   'tension-controlled check, phi*Vc for shear with no stirrups '
                   'designed, and the tied-column axial cap with a stated slenderness '
                   'reduction. The reinforcement ratios are fixed assumptions and are '
                   'reported on every member rather than buried.'),
        SystemBuildability(
            system_id='STR-SYS-MASS-TIMBER-CLT-GLULAM', implemented=True,
            frame_tectonic='FRM-MASS-TIMBER',
            reason='Level lattice, CLT panel bands spanning between glulam girders.'),
        SystemBuildability(
            system_id='STR-SYS-GLULAM-POST-BEAM', implemented=True,
            frame_tectonic='FRM-HEAVY-TIMBER',
            reason='Level lattice, heavy joists, knee-braced post-to-beam joints.'),
        SystemBuildability(
            system_id='STR-SYS-LIGHT-WOOD-FRAME', implemented=False,
            reason='Stud walls at 400 mm centres are a wall assembly, not a frame of '
                   'discrete members; the emitter would have to model sheathing '
                   'diaphragms for the result to mean anything. Not built.'),
        SystemBuildability(
            system_id='STR-SYS-RC-SHELL', implemented=False,
            reason='Elements index into surface parameters (SHL-RIB-U012), not levels. '
                   'Needs a thrust-network skeleton this compiler does not have.'),
        SystemBuildability(
            system_id='STR-SYS-TIMBER-GRIDSHELL', implemented=False,
            reason='A doubly-curved lath grid set out by geodesic curves on a surface; '
                   'there is no level lattice to index into.'),
        SystemBuildability(
            system_id='STR-SYS-TENSILE-MEMBRANE', implemented=False,
            reason='Form is found by relaxation under prestress, not laid out on a '
                   'grid. Emitting one from these datums would be a drawing, not a '
                   'model.'),
        SystemBuildability(
            system_id='STR-SYS-CABLE-NET-HYBRID', implemented=False,
            reason='The same form-finding problem as the membrane, plus a mast and '
                   'anchor layout that no datum in this set describes.'),
        SystemBuildability(
            system_id='STR-SYS-STEEL-SPACE-FRAME-SHELL', implemented=False,
            reason='A space frame follows a curved surface subdivision; the level '
                   'lattice cannot place its nodes.'),
    )
}


# Which envelope tectonic each facade grammar builds. The pairing is architectural
# fact rather than preference: Brutalism is a wall with holes in it, High-Tech shows
# its frame, Critical Regionalism shades with a deep screen, Postmodernism applies an
# order to a flat wall. Organic and Parametricism share the panel field and differ in
# the axis the depth varies along, which is the honest distinction between them here --
# both build a field, and they compose it differently.
GRAMMAR_ENVELOPE: dict[str, EnvelopeTectonicId] = {
    'FCD-01-INTERNATIONAL-STYLE': 'ENV-CURTAIN-WALL',
    'FCD-02-BAUHAUS': 'ENV-CURTAIN-WALL',
    'FCD-03-BRUTALISM': 'ENV-PUNCHED-WALL',
    'FCD-04-ORGANIC': 'ENV-PANEL-FIELD',
    'FCD-05-HIGH-TECH': 'ENV-EXPRESSED-FRAME',
    'FCD-06-POSTMODERNISM': 'ENV-APPLIED-ORDER',
    'FCD-07-DECONSTRUCTIVISM': 'ENV-FACETED-PANEL',
    'FCD-08-MINIMALISM': 'ENV-BLANK-SLOT',
    'FCD-09-CRITICAL-REGIONALISM': 'ENV-DEEP-LATTICE',
    'FCD-10-PARAMETRICISM': 'ENV-PANEL-FIELD',
}

# The two grammars that share `ENV-PANEL-FIELD` compose it along different axes.
GRAMMAR_FIELD_AXIS: dict[str, str] = {
    'FCD-04-ORGANIC': 'radial',
    'FCD-10-PARAMETRICISM': 'vertical',
}


def envelope_for(grammar_id: str) -> EnvelopeTectonic:
    """The envelope tectonic a grammar builds, with any per-grammar composition applied."""
    tectonic = ENVELOPE_TECTONICS[GRAMMAR_ENVELOPE[grammar_id]]
    axis = GRAMMAR_FIELD_AXIS.get(grammar_id)
    if axis and tectonic.outboard == 'field':
        return tectonic.model_copy(update={'field_axis': axis})
    return tectonic


def frame_for(system_id: str) -> FrameTectonic:
    entry = SYSTEM_BUILDABILITY[system_id]
    if not entry.implemented or entry.frame_tectonic is None:
        raise KeyError(f'{system_id} has no frame tectonic: {entry.reason}')
    return FRAME_TECTONICS[entry.frame_tectonic]


def buildable_systems() -> list[str]:
    return [s for s, e in SYSTEM_BUILDABILITY.items() if e.implemented]


def unbuildable_reason(system_id: str) -> str | None:
    entry = SYSTEM_BUILDABILITY.get(system_id)
    if entry is None:
        return f'{system_id} is not a known structural system.'
    return None if entry.implemented else entry.reason
