# Integrated library layer evidence

- Model ID: `building-b7ad95fa45a6-library-steel-international-v1`
- Score ID: `score-b7ad95fa45a6`
- Test audio: `fixtures/audio/gemini_music_to_architecture_44s.mp3`
- GLB SHA-256: `83426227af5e1d78b26d865d323f30c3d2d13bc323d24afc0415d4b9b0351b1f`
- Configuration: library + steel frame candidate + International Style-informed MTA-F2 facade

## Evidence protocol

All five captures use the same browser session, API response, model ID, GLB, camera,
audio metrics, and 471-element building contract. Only the semantic layer or clipping
state changes.

| Capture | Visible contract |
|---|---|
| `01_overall.png` | Facade, structure, interior sequence, site, trees, cars, people |
| `02_program.png` | 21 room-level program volumes: public, private, circulation, service |
| `03_facade.png` | 299 room-owned envelope elements: panels, glazing, mullions, supports, canopy |
| `04_structure.png` | 140 steel-frame candidate elements: foundations, columns, beams, slabs, bracing, cores |
| `05_clipping_section.png` | Overall model clipped horizontally at Z = 3.0 m, inverted to retain the lower occupied zone |

## Authority and limits

The output is a generated candidate and presentation model. Program jurisdiction,
structural analysis and member sizing, facade environmental/connection engineering,
Grasshopper review, and Rhino acceptance remain unresolved. Site context is scale
evidence and has no accepted-design authority.

Facade reference and candidate-plan validators both passed with no warnings. The
generated render is recorded as output evidence only; the selected guideline,
program ownership, and support graph remain the candidate facade's design sources.
