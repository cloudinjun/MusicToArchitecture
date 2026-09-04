"""One machine-readable spec per facade grammar, derived from its written guide.

`docs/style_guides/facade/` already carried ten guides, each with invariants, a table of
legal variables with real ranges, forbidden operations and a validation section. None of
it reached the compiler. The emitter drew one curtain wall, and the guides were a
literature review sitting beside a program that ignored them.

This module is the bridge. Every number here is transcribed from a guide's *Legal
variables and starting ranges* table, and every `invariants` entry names a rule from that
guide's *Invariants* section. Nothing is invented: where a guide declines to give a
universal number -- Critical Regionalism gives derivation rules instead, because a
shading depth without a latitude is a decoration -- the spec records that refusal rather
than filling in a plausible-looking figure.

Two things here are load-bearing beyond documentation.

**`score_authority`.** Each grammar decides for itself how much the music is allowed to
move it. Minimalism states the limit outright -- "score-driven dimensional variation
+/-0-12%, intentionally low amplitude" -- and a pipeline that let the score swing a
minimalist elevation as hard as a parametric one would be violating the guide while
claiming to implement it. Deconstructivism sits at the other end and says so. This single
number is why two grammars given the same score produce differently *disciplined*
buildings, not just differently shaped ones.

**`opening_ratio`.** The guides bound it per grammar, and those bounds are checked after
emission by `facade_gates.py`. A Brutalist elevation that came out 70 % glass would be a
curtain wall wearing a Brutalist label, and the gate says so instead of shipping it.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GrammarSpec(BaseModel):
    """What one facade grammar's guide requires, in a form the compiler can honour."""

    grammar_id: str
    label: str
    guide_ref: str
    invariants: tuple[str, ...]

    # --- from the guide's legal-variables table ---------------------------------
    # The module the elevation is set out on, in metres.
    module_range_m: tuple[float, float]
    # Share of the elevation that may be opening. Checked after emission.
    opening_ratio_range: tuple[float, float]
    # Depth of a reveal, a screen or a projecting layer, in metres. (0, 0) means the
    # grammar declares no projecting depth of its own.
    depth_range_m: tuple[float, float] = (0.0, 0.0)
    # How many distinct materials the elevation may show. Minimalism caps this at
    # three and the cap is the grammar.
    material_families: tuple[int, int] = (1, 4)
    # Area share that may be an accent or a motif, as a fraction of the elevation.
    accent_area_max: float = Field(default=0.12, ge=0.0, le=1.0)
    # Smallest panel or fragment the grammar tolerates before it reads as debris.
    minimum_fragment_m: float = 0.30

    # --- how much of its declared range the score may use ------------------------
    # 1.0 lets a datum travel its whole declared range; 0.12 is Minimalism's stated
    # limit. This scales the score's contribution, never the tectonic floor, so a
    # grammar stays recognisable whatever the music does.
    score_authority: float = Field(ge=0.0, le=1.0)
    score_authority_source: str

    # --- properties a gate can check --------------------------------------------
    # Orientation must change the response (Critical Regionalism, CR-INV-02).
    requires_orientation_response: bool = False
    # The guide requires the source system to remain recoverable after transformation
    # (Deconstructivism, DC-INV-*), so a baseline must exist with score influence off.
    requires_recoverable_baseline: bool = False
    # Parametricism caps how much two neighbouring panels may differ.
    neighbour_jump_max: float | None = None
    # Parametricism reports, and caps, the share of panels that are unique.
    unique_panel_ratio_max: float | None = None

    forbidden: tuple[str, ...] = ()
    note: str


GRAMMAR_SPECS: dict[str, GrammarSpec] = {
    spec.grammar_id: spec for spec in (
        GrammarSpec(
            grammar_id='FCD-01-INTERNATIONAL-STYLE', label='International Style',
            guide_ref='docs/style_guides/facade/01_international_style.md',
            invariants=('IS-INV-01', 'IS-INV-03'),
            module_range_m=(1.2, 3.6), opening_ratio_range=(0.25, 0.75),
            depth_range_m=(0.0, 0.45), material_families=(2, 3),
            accent_area_max=0.12, score_authority=0.20,
            score_authority_source='mullion rhythm variation, +/-0-20% around the base '
                                   'module; plane offset is separately score-eligible',
            note='An orthogonal datum and a base module, with the plane offset and the '
                 'mullion rhythm the two things the score is allowed to touch.'),

        GrammarSpec(
            grammar_id='FCD-02-BAUHAUS', label='Bauhaus',
            guide_ref='docs/style_guides/facade/02_bauhaus.md',
            invariants=('BH-INV-01',),
            module_range_m=(0.6, 1.5), opening_ratio_range=(0.55, 0.85),
            depth_range_m=(0.0, 0.40), material_families=(2, 3),
            accent_area_max=0.10, score_authority=0.30,
            score_authority_source='module grouping, 2-8 units, is the score-eligible '
                                   'variable; the ratios are typology-clamped',
            note='The workshop-wing curtain wall: a standard module, grouped, with the '
                 'opaque ratio owned by the program rather than by the music.'),

        GrammarSpec(
            grammar_id='FCD-03-BRUTALISM', label='Brutalism',
            guide_ref='docs/style_guides/facade/03_brutalism.md',
            invariants=('BR-INV-01', 'BR-INV-04'),
            module_range_m=(1.8, 4.8), opening_ratio_range=(0.10, 0.45),
            depth_range_m=(0.35, 1.80), material_families=(1, 2),
            accent_area_max=0.06, minimum_fragment_m=0.30,
            score_authority=0.45,
            score_authority_source='mass step/setback of 0.5-2.0 structural bays is '
                                   'owned by hierarchy and interruption',
            forbidden=('an opening drawn as an applied graphic layer rather than as a '
                       'cut (BR-INV-04)',),
            note='Openings are cuts and recesses. The reveal range is wide because the '
                 'depth hierarchy, not the surface texture, is what the guide asks to '
                 'be visible in section.'),

        GrammarSpec(
            grammar_id='FCD-04-ORGANIC', label='Organic architecture',
            guide_ref='docs/style_guides/facade/04_organic_architecture.md',
            invariants=('OR-INV-01',),
            module_range_m=(0.6, 1.8), opening_ratio_range=(0.20, 0.65),
            depth_range_m=(0.25, 2.50), material_families=(2, 4),
            accent_area_max=0.10, score_authority=0.50,
            score_authority_source='site-driver influence is a 0.2-0.8 weight and the '
                                   'score works inside what it leaves',
            note='A field composed radially about the entrance. The guide requires site '
                 'drivers this pipeline does not have, which the gate reports rather '
                 'than silently substituting the score for them.'),

        GrammarSpec(
            grammar_id='FCD-05-HIGH-TECH', label='High-Tech',
            guide_ref='docs/style_guides/facade/05_high_tech.md',
            invariants=('HT-INV-01',),
            module_range_m=(0.75, 1.8), opening_ratio_range=(0.45, 0.85),
            depth_range_m=(0.60, 2.40), material_families=(2, 4),
            accent_area_max=0.12, score_authority=0.35,
            score_authority_source='visible secondary-member density, 1-5 per bay, is '
                                   'score-eligible under a structural clamp',
            note='The frame and its ties are the elevation. Facade system depth is '
                 'generous because the guide expects routing and maintenance in it.'),

        GrammarSpec(
            grammar_id='FCD-06-POSTMODERNISM', label='Postmodernism',
            guide_ref='docs/style_guides/facade/06_postmodernism.md',
            invariants=('PM-INV-01',),
            module_range_m=(0.9, 3.6), opening_ratio_range=(0.15, 0.50),
            depth_range_m=(0.10, 1.00), material_families=(2, 4),
            accent_area_max=0.30, score_authority=0.40,
            score_authority_source='compositional exceptions, 1-4 per elevation, come '
                                   'from interruption and need human review',
            note='One applied order over a repeated background module. Motif area may '
                 'reach 30% because the order is the point, not an accent on it.'),

        GrammarSpec(
            grammar_id='FCD-07-DECONSTRUCTIVISM', label='Deconstructivism',
            guide_ref='docs/style_guides/facade/07_deconstructivism.md',
            invariants=('DC-INV-01',),
            module_range_m=(0.9, 2.4), opening_ratio_range=(0.20, 0.60),
            depth_range_m=(0.05, 0.60), material_families=(2, 3),
            accent_area_max=0.12, minimum_fragment_m=0.30,
            score_authority=0.65, requires_recoverable_baseline=True,
            score_authority_source='plane rotation 3-18 deg and fragment displacement '
                                   '0.05-0.40 bay are both score-eligible under a '
                                   'structural clamp; transformed share stays 15-45%',
            forbidden=('residual slivers below the material limit, placeholder 0.3 m',),
            note='Two geometries in conflict. The guide requires the untransformed '
                 'facade to remain recoverable, which is why the baseline flag is set.'),

        GrammarSpec(
            grammar_id='FCD-08-MINIMALISM', label='Minimalism',
            guide_ref='docs/style_guides/facade/08_minimalism.md',
            invariants=('MI-INV-01', 'MI-INV-02', 'MI-INV-04'),
            module_range_m=(1.2, 3.6), opening_ratio_range=(0.04, 0.22),
            depth_range_m=(0.10, 0.90), material_families=(1, 3),
            accent_area_max=0.08, score_authority=0.12,
            score_authority_source='the guide states it outright: score-driven '
                                   'dimensional variation +/-0-12%, intentionally low '
                                   'amplitude',
            forbidden=('unreasoned sliver panels, duplicate faces, near-coplanar '
                       'offsets',),
            note='The lowest score authority in the set, and deliberately so. A '
                 'minimalist elevation that swung as hard as a parametric one under the '
                 'same music would be violating its own guide.'),

        GrammarSpec(
            grammar_id='FCD-09-CRITICAL-REGIONALISM', label='Critical Regionalism',
            guide_ref='docs/style_guides/facade/09_critical_regionalism.md',
            invariants=('CR-INV-02', 'CR-INV-04', 'CR-INV-06'),
            module_range_m=(0.6, 1.6), opening_ratio_range=(0.15, 0.55),
            depth_range_m=(0.30, 1.20), material_families=(2, 3),
            accent_area_max=0.08, score_authority=0.25,
            score_authority_source='the guide gives no universal ranges at all: the '
                                   'score may modulate only the interval left after '
                                   'environmental and typology constraints are met, and '
                                   'this pipeline has none of those inputs',
            requires_orientation_response=True,
            note='The only guide that refuses to publish numbers, because a shading '
                 'depth without a latitude is a decoration. The spec keeps the refusal: '
                 'the gate reports the missing context rather than inventing a site.'),

        GrammarSpec(
            grammar_id='FCD-10-PARAMETRICISM', label='Parametricism',
            guide_ref='docs/style_guides/facade/10_parametricism.md',
            invariants=('PA-INV-01',),
            module_range_m=(0.6, 1.5), opening_ratio_range=(0.15, 0.80),
            depth_range_m=(0.04, 0.45), material_families=(1, 3),
            accent_area_max=0.10, score_authority=0.70,
            neighbour_jump_max=0.20, unique_panel_ratio_max=0.35,
            requires_recoverable_baseline=True,
            score_authority_source='2-5 normalised driver fields with 1-4 active '
                                   'degrees of freedom per panel family; the score is '
                                   'one field among them',
            note='A gradient, not a pattern. The neighbour-jump and unique-panel caps '
                 'are fabrication limits from the guide and are checked after emission '
                 'rather than assumed.'),
    )
}


def spec_for(grammar_id: str) -> GrammarSpec:
    return GRAMMAR_SPECS[grammar_id]
