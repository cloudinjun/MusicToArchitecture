# Concealed envelope returns

2026-09-08. User redline: return brackets protrude through roof caps and floor
soffits. Candidate 75 measured roof HEAD bracket tops at approximately 20.1064 m
against a 20.0364 m cap; ordinary HEAD brackets also protruded below the soffit.

The axis previously ended on the finish datum. A 140 mm member centred there
exposes half its section; a 75 mm panel cannot conceal it. The repaired controlled
non-high-tech path places the body behind the finish and offsets the facade-end
axis by half the section depth. A direct two-node tie avoids short folded sweeps.
Top returns sit above ordinary soffits and below roof caps; base returns sit below
floor finishes. Roof bearings are selected from actual solids at the new bracket
height, usually the parapet substrate rather than the coping. Missing bearings
remain unresolved, never invented.

Legacy and explicitly high-tech return paths retain their existing behavior.
Professional attachment and capacity design remain unresolved.

Tests: 102 roof-band/envelope-closure tests plus 11 facade-boundary/high-tech
dependency tests passed. Added assertions measure emitted physical vertical
extents across two roof shapes, three facade systems and three trim assignments;
solid-bearing checks remain in place. The older axis-coincidence assertion now
checks section-edge contact at the facade datum.

Complete candidate compile and native visual verification are tracked separately
under artifacts/skill_runs/2026-09-08-small-site/concealed-returns-76. These tests
alone do not establish that the screenshot redline is closed or that every style
is covered.
