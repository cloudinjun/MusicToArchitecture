"""What each element is made of, and what that looks like.

The model used to carry a palette key -- `steel_white`, `concrete_light` -- and nothing
else. What the key meant was decided by whichever renderer read it: the Blender importer
held a table of colours and roughnesses, the web viewport had its own, and a third
consumer would have invented a third. A key with no definition behind it is a name, not
a material, and two renderers of the same building were free to disagree about it.

So the definition lives here and travels on the model. Two things are recorded and they
are not the same thing:

**What it is.** `family` is the construction material -- steel, concrete, timber, glass.
This is the half that can be wrong in a way that matters: the frame was *sized* against
a material, with that material's capacity equations, and an element whose appearance
says timber while its section was checked to AISC is a real contradiction rather than a
styling choice. `agrees_with_structure` is what makes that checkable.

**What it looks like.** Base colour, roughness, metallic, transmission -- enough for a
physically-based renderer to draw it without guessing, and the same numbers for every
renderer that reads them.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


MaterialFamily = Literal[
    'steel', 'concrete', 'timber', 'glass', 'masonry', 'plaster', 'ground',
    'fabric', 'diagram', 'insulation', 'membrane', 'board',
]


class MaterialSpec(BaseModel):
    """One material: what it is made of, and what a renderer should draw."""

    id: str
    family: MaterialFamily
    finish: str
    # sRGB hex, so a consumer that is not a 3D renderer -- a drawing, a schedule, a
    # web swatch -- can use it without a colour-space conversion of its own.
    base_color: str
    roughness: float = Field(ge=0.0, le=1.0)
    metallic: float = Field(default=0.0, ge=0.0, le=1.0)
    transmission: float = Field(default=0.0, ge=0.0, le=1.0)
    ior: float = Field(default=1.5, gt=1.0)
    reason: str

    @property
    def rgba(self) -> tuple[float, float, float, float]:
        """Linear-ish float RGBA, which is what a renderer wants."""
        value = self.base_color.lstrip('#')
        channels = tuple(int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
        return (*channels, 1.0)

    @property
    def is_structural(self) -> bool:
        return self.family in ('steel', 'concrete', 'timber', 'masonry')


def _spec(id: str, family: MaterialFamily, finish: str, colour: str,
          roughness: float, reason: str, *, metallic: float = 0.0,
          transmission: float = 0.0) -> MaterialSpec:
    return MaterialSpec(id=id, family=family, finish=finish, base_color=colour,
                        roughness=roughness, metallic=metallic,
                        transmission=transmission, reason=reason)


# The palette, with the values the renderer had already been tuned to. What is new is
# the family and the finish: a colour alone cannot be checked against anything.
MATERIALS: dict[str, MaterialSpec] = {spec.id: spec for spec in (
    _spec('white', 'plaster', 'painted board', '#e6e5e3', 0.52,
          'The general light surface: linings, treads, soffits.'),
    _spec('white_soft', 'plaster', 'matt paint', '#d6d5d3', 0.62,
          'A half-tone below white, so two adjacent surfaces read apart.'),
    _spec('steel_white', 'steel', 'off-white paint on steel', '#ececeb', 0.40,
          'Painted structural steel, the frame default.', metallic=0.1),
    _spec('steel_light', 'steel', 'galvanised', '#dedddd', 0.45,
          'Lighter steel for secondary and screen members.', metallic=0.2),
    _spec('steel_dark', 'steel', 'dark paint on steel', '#616162', 0.35,
          'Dark steel: bracing and the members meant to read as structure.',
          metallic=0.3),
    _spec('frame_dark', 'steel', 'anodised dark', '#222325', 0.40,
          'Curtain-wall framing, which is dark on almost every building of this type.',
          metallic=0.4),
    _spec('concrete', 'concrete', 'fair-faced', '#c2bfbe', 0.78,
          'Cast concrete as struck, without a finish over it.'),
    _spec('concrete_light', 'concrete', 'fair-faced, pale aggregate', '#dad9d7', 0.70,
          'The lighter cast surface: slabs and podium.'),
    _spec('timber', 'timber', 'glulam, oiled', '#caaf85', 0.62,
          'Mass timber. A timber frame that renders as white steel loses the one cue '
          'that says which material was selected.'),
    _spec('timber_light', 'timber', 'CLT, clear finish', '#dbc7a3', 0.58,
          'Panel timber, lighter than the glulam frame it sits on.'),
    _spec('terracotta', 'masonry', 'terracotta rainscreen', '#b46547', 0.74,
          'Fired cladding, on the families whose guides call for it.'),
    _spec('glass', 'glass', 'sealed double unit', '#b3c7d0', 0.08,
          'Vision glass. Transmission is what makes it glass rather than a pale panel.',
          transmission=0.84),
    _spec('roof_deck_substrate', 'steel', 'profiled roof deck substrate', '#9a9c9f', 0.48,
          'The visible 180 mm structural roof substrate zone used by the shared roof '
          'section convention; deck gauge, profile and capacity require selection.',
          metallic=0.28),
    _spec('roof_vapour_control', 'membrane', 'vapour-control sheet', '#4b5158', 0.58,
          'A 3 mm visible vapour-control layer for student-detail coordination; '
          'condensation analysis and product selection remain open.'),
    _spec('roof_insulation', 'insulation', 'tapered rigid insulation', '#d8c97e', 0.82,
          'The conventional insulation/fall build-up. The model carries its average '
          'depth; drainage design and thermal performance remain open.'),
    _spec('roof_cover_board', 'board', 'high-density cover board', '#c2bda9', 0.76,
          'A 15 mm cover board separating insulation from the weathering layer.'),
    _spec('roof_waterproofing', 'membrane', 'dark roof membrane', '#3b3c3e', 0.34,
          'A 5 mm visible weathering membrane for student detail sections; laps, '
          'upstands, outlets, penetrations and warranty remain professional work.'),
    _spec('roof_parapet_substrate', 'board', 'cementitious parapet substrate', '#d8d7d4', 0.68,
          'The solid parapet carrier inside the controlled roof perimeter; framing, '
          'fire performance and attachment remain unresolved.'),
    _spec('roof_coping', 'steel', 'folded metal coping', '#b9bab9', 0.36,
          'A conventional folded-metal coping volume. Joints, drips, cleats, movement '
          'and fixing design require professional review.', metallic=0.32),
    _spec('accent_red', 'steel', 'signal paint', '#b31915', 0.55,
          'The one saturated colour, for what a building marks out: handrails, doors.'),
    _spec('furn', 'fabric', 'upholstery and worktop', '#b3afa8', 0.72,
          'Loose furniture, deliberately quiet against the fabric.'),
    _spec('ground', 'ground', 'earth', '#838486', 0.90,
          'Cut earth below grade.'),
    _spec('ground_light', 'ground', 'paving', '#bcbcba', 0.86,
          'The made surface outside the building.'),
    # The program overlay is not a material and says so. It is a diagram drawn in the
    # same scene, and a renderer that treats it as a surface will light it like one.
    _spec('prog_public', 'diagram', 'program overlay', '#3d82e0', 0.72,
          'Public program, shown as a diagram rather than as a built surface.'),
    _spec('prog_private', 'diagram', 'program overlay', '#e68538', 0.72,
          'Private program overlay.'),
    _spec('prog_circulation', 'diagram', 'program overlay', '#38b369', 0.72,
          'Circulation overlay.'),
    _spec('prog_service', 'diagram', 'program overlay', '#9463c2', 0.72,
          'Service overlay.'),
)}


# Which appearance families are acceptable for a frame sized in a given material. The
# check this enables is narrow and worth having: a member checked to NDS timber
# capacities that renders as painted steel is telling a viewer the wrong thing about
# the building, and no amount of care in the palette catches it.
STRUCTURAL_FAMILY = {
    'steel': {'steel'},
    'timber': {'timber'},
    'concrete': {'concrete', 'masonry'},
}


def agrees_with_structure(material_id: str, structural_material: str) -> bool | None:
    """Does the appearance agree with the material the member was sized in?

    `None` where the question does not apply -- a glazing panel has no structural
    material, and a program overlay is not a surface at all.
    """
    spec = MATERIALS.get(material_id)
    if spec is None or not spec.is_structural:
        return None
    allowed = STRUCTURAL_FAMILY.get(structural_material)
    if allowed is None:
        return None
    return spec.family in allowed


# Which Revit material class a source family lands in. Named here rather than in the
# handoff so the mapping sits beside the families it maps, and so a family added to the
# literal above without a class shows up as a KeyError at the seam rather than as a
# silent default in a coordination model. `diagram` is the analytic palette -- program
# colours, not a substance -- and it maps to Generic on purpose.
REVIT_MATERIAL_CLASS: dict[str, str] = {
    'steel': 'Metal',
    'concrete': 'Concrete',
    'timber': 'Wood',
    'glass': 'Glass',
    'masonry': 'Masonry',
    'plaster': 'Generic',
    'ground': 'Generic',
    'fabric': 'Generic',
    'diagram': 'Generic',
    'insulation': 'Generic',
    'membrane': 'Generic',
    'board': 'Generic',
}


def used_by(model) -> dict[str, MaterialSpec]:
    """Only the materials this model actually uses, so the payload stays honest."""
    keys = {group.material_profile for group in model.element_groups}
    return {key: MATERIALS[key] for key in sorted(keys) if key in MATERIALS}
