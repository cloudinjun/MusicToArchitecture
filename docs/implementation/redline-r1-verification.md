# R1 verification record

Baseline: `bc586fcf2d810a7144a611f2db1b83bd930712db`.
Application-code commit: `109e1a84848200ea9731485d1418e2668ff2a647`.
Compiler version: **3.5.0**. Recorded September 4, 2026 (America/Los_Angeles).

This is a targeted verification record, **not a green full-suite result** and not
approval of an entire building. See [implemented scope and remaining work](redline-r1.md).

## Executed checks

| Suite | Baseline | R1 | Environment |
|---|---:|---:|---|
| R1 counterexamples + drawings + exact geometry + valid rings + preview isolation | Not run as this new combined suite | **122 passed, 0 failed** | Clean GitHub Actions checkout, Python 3.12.14 |
| Existing archetypes | 16 passed | **16 passed** | Local source checkout |
| Existing spatial rules | 33 passed, 7 failed | **33 passed, 7 failed** | Paired local baseline/R1 runs |
| Existing permit-level tests | 31 passed, 6 failed | **32 passed, 5 failed** | Paired local baseline/R1 runs |

The first suite includes a real compile of the checked-in theatre features and score,
not only mocked geometry. Its independent room-support test passes for that compile.
The new R1 test module contributes 40 parametrized cases, including 16 door orientations.
The 122-test CI run completed in 111.02 seconds:
https://github.com/cloudinjun/MusicToArchitecture/actions/runs/33940228475

JUnit artifact from that run: `redline-verified-tests`, artifact ID `9961588615`.
The persistent read-only workflow repeats the targeted suite; its success must not be
interpreted as an assertion that the broader spatial or permit suites pass.

## Failures deliberately not concealed

All seven failing spatial tests are the existing per-massing
`test_no_model_breaks_a_spatial_rule[...]` assertions. In R1 their whole-model status
remains unevaluated because member-based stair head-clearance is approximate. A warning
was not changed to a pass. The paired baseline also fails these seven assertions.

Five permit-suite tests still fail in R1:

1. `test_a_second_remote_stair_core_is_built`: the old assertion requires a normative
   pass from provisional remoteness arithmetic; R1 retains the measured values but
   returns unevaluated without verified code inputs and routes.
2. `test_every_massing_family_produces_a_gradeable_egress_report`: the old assertion
   requires pass/fail even for an entirely unevaluated tower. This is the second
   intentional status-contract mismatch, **not a pre-existing failing assertion**.
3. `test_a_plan_too_narrow_for_two_remote_cores_still_gets_the_best_pair`: fixture
   expectations about the cramped pair no longer match the generated dimensions;
   this assertion also fails on the baseline.
4. `test_every_crowded_storey_has_two_ways_out`: the existing area-based diagnostic
   occupant estimate can demand more exits than the layout supplies. This is an open
   circulation/layout problem, not something this patch fixes or waives. It also
   fails on the baseline; actual seat-based occupant loads remain future work.
5. `test_the_extra_core_is_reserved_like_the_others`: the fixture expects an extra
   core that is not generated. This assertion also fails on the baseline.

Three baseline remoteness assertions no longer fail in R1. That difference is not a
license to describe the building as compliant: favourable arithmetic is now explicitly
unevaluated. The two changed status assertions need an intentional contract update,
while actual egress geometry and capacity still require implementation.

## Not verified or promoted

The full repository test suite was not run. The local text-only source snapshot lacks
the MP3 used by audio-dependent tests, so their missing-file errors were not counted as
product regressions. No Blender/Rhino application run, accepted-geometry publication,
frozen demo regeneration, physical print, or code approval was performed. Existing
`latest` archives and public demonstration assets are unchanged.

Temporary source-transfer helpers and their write-enabled workflow were removed from
the final branch tree. The retained regression workflow has read-only repository
permissions and does not commit files.
