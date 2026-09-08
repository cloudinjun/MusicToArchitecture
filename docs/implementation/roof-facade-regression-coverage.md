# Roof facade coverage regression

2026-09-08. Portfolio evidence: V2 system coordination and V4 regression evaluation.

The live Blender inspection identified the September 6 candidate
`building-v3-55684d34e298.blend`; its roof and roof_closure objects use `white`.
The September 8 physical-roof-73 export is a separate file. No live scene was
replaced and no candidate was promoted by this check.

The previous roof-band test exercised one deep-lattice grammar with three trim
materials and checked heights, collar containment and supports. Those assertions
alone could admit a missing facade side.

The expanded test covers two footprints (setback rectangle and concave L), three
systems (deep lattice, curtain wall and punched wall), and three trim assignments:
18 combinations. At 20%, 50% and 80% of the physical roof-band height it projects
emitted vertical panels onto each weather-boundary edge and measures uncovered
length. Recessed glazing is allowed within the declared collar. Empty skin is a
negative control. Source levels remain unchanged.

An initial coplanar-section check falsely rejected punched-wall glazing because
the emitter deliberately recesses it by 0.8 times the bounded reveal depth. The
elevation-projection test accounts for that declared geometry rather than treating
every window recess as a hole.

Verification: `python -m pytest backend/tests/test_roof_facade_band.py
backend/tests/test_roof_physical_height.py backend/tests/test_roof_span_contract.py -q`
completed with 29 passed in 6.14 seconds.

Limits: three sampled heights do not prove continuous surface coverage; these are
emitter fixtures, not complete musical candidates or all facade grammars. Courtyard
roofs, non-orthogonal edges, occlusion and native-export parity remain outside this
test. The material variants verify propagation, not architectural style quality.
No compiler geometry changed and no new native delivery was generated.
