# Score to element traceability

Model `building-v3-7519e839871f` from score `score-b7ad95fa45a6`.

- score dimensions emitted: **10 of 10**
- datums: **34**, 85% score-driven overall, **100% of the variable datums**
- elements: **3545** in 167 groups

A datum whose driving dimension is measured at low confidence is clamped toward the middle of its declared range, so a weak reading nudges the design and a strong one commits. The clamp column shows how much of the range each datum was actually allowed to travel.

## tempo_of_change  (0.137, observed, confidence 0.88)

Measured from `tempo_bpm`.

> Stack more distinct floor episodes and change the module more often along the public sequence.

| datum | value | range | travel | elements |
|---|---:|---|---:|---:|
| `level_count` | 4.410 levels | 4 .. 7 | 100% | 17 |

## tension_release  (0.212, observed, confidence 0.95)

Measured from `rms_energy`.

> Open the section: more headroom and deeper shading where the music releases, compression where it does not.

| datum | value | range | travel | elements |
|---|---:|---|---:|---:|
| `floor_to_floor_m` | 4.218 m | 3.9 .. 5.4 | 100% | 660 |
| `shading_rows` | 1.423 rows | 1 .. 3 | 100% | 0 |
| `shading_depth_m` | 0.527 m | 0.4 .. 1 | 100% | 0 |

## density  (0.264, observed, confidence 0.90)

Measured from `onset_density_hz`.

> Tighten the structural bay and the tertiary framing rhythm within the declared span limits.

| datum | value | range | travel | elements |
|---|---:|---|---:|---:|
| `bay_x_m` | 7.220 m | 7.8 .. 5.6 | 100% | 280 |
| `bay_y_m` | 7.820 m | 8.4 .. 6.2 | 100% | 378 |
| `joist_spacing_m` | 2.310 m | 2.6 .. 1.5 | 100% | 130 |
| `transom_rows` | 2.527 rows | 2 .. 4 | 100% | 471 |

## continuity  (0.518, inferred, confidence 0.72)

Measured from `spectral_centroid_hz`.

> Run the plate past its supports and round the end rather than cutting it; keep more of the floor for continuous routes.

| datum | value | range | travel | elements |
|---|---:|---|---:|---:|
| `cantilever_m` | 2.151 m | 0.6 .. 3.6 | 96% | 381 |
| `apse_radius_m` | 10.068 m | 8 .. 12 | 96% | 380 |
| `circulation_allowance` | 0.222 fraction | 0.16 .. 0.28 | 96% | 253 |
| `flight_width_m` | 2.627 m | 1.8 .. 3.4 | 96% | 265 |

## repetition  (0.507, observed, confidence 0.78)

Measured from `periodicity`.

> Fix the envelope module and the tertiary rhythms -- mullion spacing, spandrel band, guard posts -- to a tighter, more regular cadence.

| datum | value | range | travel | elements |
|---|---:|---|---:|---:|
| `mullion_module_m` | 1.347 m | 1.55 .. 1.15 | 100% | 323 |
| `spandrel_height_m` | 0.573 m | 0.75 .. 0.4 | 100% | 157 |
| `rail_post_spacing_m` | 1.495 m | 1.9 .. 1.1 | 100% | 791 |

## variation  (0.915, observed, confidence 0.75)

Measured from `timbre_variation`.

> Let the upper plates depart from the lower ones: step the plan back and rotate each level against the one below.

| datum | value | range | travel | elements |
|---|---:|---|---:|---:|
| `plate_step_m` | 3.204 m | 0 .. 3.5 | 100% | 380 |
| `plate_rotation_deg` | 2.746 degrees | 0 .. 3 | 100% | 380 |

## hierarchy  (0.727, observed, confidence 0.80)

Measured from `dynamic_range_db`.

> Make one structural order dominate: a deeper roof truss, a taller open ground level, a larger entry gesture.

| datum | value | range | travel | elements |
|---|---:|---|---:|---:|
| `truss_depth_m` | 2.591 m | 1.5 .. 3 | 100% | 5 |
| `truss_panels` | 7.636 panels | 4 .. 9 | 100% | 43 |
| `ground_open_height_m` | 5.509 m | 4.2 .. 6 | 100% | 53 |
| `entry_canopy_span_m` | 6.544 m | 0 .. 9 | 100% | 12 |

## interruption  (0.382, observed, confidence 0.74)

Measured from `novelty_peak_rate_per_min`.

> Break the stack: punch atrium voids through the plates and strip the envelope from whole levels to make terraces.

| datum | value | range | travel | elements |
|---|---:|---|---:|---:|
| `void_count` | 1.152 voids | 0 .. 3 | 99% | 14 |
| `void_scale` | 0.950 factor | 0.7 .. 1.35 | 99% | 14 |
| `terrace_count` | 0.768 levels | 0 .. 2 | 99% | 14 |

## polyphony  (0.491, inferred, confidence 0.55)

Measured from `spectral_contrast_db+harmonic_ratio`.

> Separate the orders so each reads on its own: push the envelope further outboard of the frame, add screen and shading layers, express more braced bays. This is a layering proxy, not a count of voices.

| datum | value | range | travel | elements |
|---|---:|---|---:|---:|
| `envelope_offset_m` | 0.520 m | 0.15 .. 0.9 | 73% | 1099 |
| `envelope_layer_count` | 1.986 layers | 1 .. 3 | 73% | 157 |
| `braced_bay_count` | 3.973 bays | 2 .. 6 | 73% | 0 |

## genre_style  (0.594, inferred, confidence 0.35)

Measured from `spectral_flatness+zero_crossing_rate+spectral_centroid_hz+harmonic_ratio`.

> A timbral position, bright and percussive against dark and sustained. It proposes a weighting between a light glazed envelope and a heavier panelled one, and a fin depth to match. It is not a genre label, it never selects a facade grammar, and a human must accept the weighting.

| datum | value | range | travel | elements |
|---|---:|---|---:|---:|
| `opaque_fraction` | 0.260 fraction | 0.45 .. 0.1 | 47% | 0 |
| `fin_depth_m` | 0.292 m | 0.14 .. 0.42 | 47% | 0 |

## Fixed by the tectonic system, never by music

| datum | value | why |
|---|---:|---|
| `slab_thickness_m` | 0.3 m | Composite deck and topping depth for the selected steel frame. |
| `edge_fascia_m` | 0.55 m | Visible plate edge: slab plus edge beam. |
| `riser_m` | 0.175 m | Stair riser inside the accessible range; sets every flight division. |
| `rail_height_m` | 1.05 m | Guard height; also the primary scale anchor in the model. |
| `figure_height_m` | 1.75 m | Scale figure. Not architecture, but the reason the rest reads as architecture. |
