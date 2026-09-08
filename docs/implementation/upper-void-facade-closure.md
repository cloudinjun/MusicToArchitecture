# Preserve authored upper openings

Candidate 64's unsupported ENV-RET-L01-HEAD-P001 covers 30.854626 m2. Its footprint
matches the L02 Program Volume opening to 0.000081 m2. Nearby floor slabs cover none
of it; L01 ceilings already cover the occupied room portions below.

The HEAD return computed lower weather region minus upper floor material, which
converted the upper opening into a closure panel. The first repair read upper.voids.
Full compile 65 disproved its completeness: after floor carving that list is empty,
although the immutable facade control still carries the source void. The offending
panel and missing dependencies remained. Walking findings became zero with local
surface measurement; spatial status stayed unevaluated due to regional facade input.

The revised repair subtracts the upper facade control's source_voids together with
the floor's remaining voids. Regression reproduces the disappearing floor-hole list
and checks that the authored opening stays empty while legitimate step returns remain.
91 envelope/roof/walking tests pass. Full compile 66 completed in 29.43 seconds:
building-v3-b1d2dadcced6, 6,689 elements, source unchanged. The offending panel is
absent and the dependency graph passes. Spatial violation counts are zero; status
remains unevaluated for the regional facade evidence warning. All 309 m2 of required
program remains allocated. Native export and visual review have not yet been run
for 66; no accepted candidate is claimed by this note.

This is a V2 boundary-authority repair. Geometry retains its actual support checks;
the panel is not given a fabricated support or a blanket exemption. The separate
seven-family spatial regression has three unresolved legacy walking findings, recorded
in walking-surface-local-height.md.
