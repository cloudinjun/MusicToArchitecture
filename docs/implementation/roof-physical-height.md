# Roof cap reads physical geometry

Candidate 72's coping failed the cap check despite both displayed heights reading
20.03642 m. RoofControl's cap was 20.036416796666668 m; the emitted extrusion top
was rounded to 20.036417 m. Its 0.000000203333332 m excess is inside the existing
0.000001 m tolerance. The viewport compatibility bounds instead rounded center
and size separately, reporting a top of 20.03642 m and a false excess of roughly
0.000003203333332 m. That helper also pads thin geometry to a 0.01 m display size.

roof_geometry_max_z now reads extrusion z_top and quad vertex heights directly;
boxes keep their physical center/size and members keep the conservative profile
allowance. Quads receive only their declared physical thickness. No model geometry,
roof cap or tolerance is changed. Failure messages now include nine-decimal heights,
the excess and tolerance so an identical formatted number cannot obscure the cause.

Three new tests cover the fractional coping, an actual 2-micrometre overflow that
still fails, and thin quads with/without declared thickness. The roof-height,
span and facade-band suite has 14 passing tests. The separate roof-proportion,
joint-root and candidate-planning suite has 26 passing tests. Full compile evidence
belongs to artifacts/skill_runs/2026-09-08-small-site/physical-roof-73/compiled;
tests alone do not establish candidate readiness.
