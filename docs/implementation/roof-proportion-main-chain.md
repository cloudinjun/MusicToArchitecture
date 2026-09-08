# Roof scale follows Program Volumes

Scope: source-level repair separate from archived `core-interface-20`. V2/V3
coordination evidence sought: same rooms and footprints, smaller roof construction
zone on the compact site, with one depth propagated to cap, datum and emission.

The whole-set review exposed a 3.8657 m roof construction zone. Its section recipe
was internally consistent but read an absolute 1.5–3.0 m hierarchy-driven depth,
independent of site/roof scale. The steel-frame guide already defines span/12–span/8
as a project-authored study range. No structural sizing/approval is inferred from it.

`roof.score_roof_control` now measures the longest interior World-Y chord of the
rectilinear PV roof plan, including concavities and holes. This is a conservative
plan-span budget **before** trimming around cores, not verified support spacing.
Music selects a ratio within the existing guide band, using the datum's already
confidence-clamped position. Unknown hierarchy uses a neutral ratio and retains
`design_fixture` provenance. An undersized plan cannot force overlapping chord
profiles; that truss recipe is refused instead of silently enlarging the volume.

`RoofControl.span_proportion` carries that basis and validates it against the actual
plan. Both PV authoring routes use it. `program_massing.datums_for` propagates the
same depth and updated range without changing score confidence or coverage. The
existing roof emitter consumes that datum and still checks profile/cap agreement,
physical plan containment and warm-roof layers. Explicit conflicting depth overrides
are refused. Legacy controls without a span basis retain their old behavior.

This repair changes neither the top functional datum nor the roof's XY boundary,
room layout, facade selection, member catalogue, foundation or connection capacity.
It does not select beam versus truss topology or establish a full tectonic roof
family library. Those are separate design decisions, not hidden consequences of
reducing a building's scale.

Verified study: `artifacts/skill_runs/2026-09-08-small-site/span-roof-21/` reduces the
roof zone from 3.8657 to 3.1699 m, preserving PV unions, allocated zones and World XY
grid. Only 145 roof-related geometries change. 130 targeted tests and web typecheck
pass. Matched sections, nine SVG sheets and a read-back-checked native Rhino file
are recorded; spatial/dependency failures and missing acceptance remain visible.
