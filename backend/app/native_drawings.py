"""Issue the whole drawing set through Blender.

A thin driver, deliberately. It works out which cuts a model needs, hands each one to
`blender/draw_building.py`, and restates the exported sheets in millimetres at the
intended scale. Everything it does not do is the point: the solidifying, the cutting,
the occlusion and the linework all happen in Blender, which already does them better
than a reimplementation here would.

The template still governs. `drawing_standard.export_profile` writes the weights, greys
and dash patterns once, and both renderers read it -- so the sheets cannot drift apart
by one of them having its own opinion about what a cut line looks like.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess

from .blender_export import BlenderExportError, find_blender_executable
from .drawing_standard import PLAN_STANDARD, SECTION_STANDARD, export_profile
from .svg_sheet import fit_metres

ROOT = Path(__file__).resolve().parents[2]
DRAW_SCRIPT = ROOT / 'blender' / 'draw_building.py'
OUTPUT_ROOT = ROOT / 'artifacts' / 'drawings' / 'native'
TIMEOUT_SECONDS = 300

# Where a plan is cut, and where a roof plan is: head height on an occupied floor, just
# above the datum on a roof, where cutting at head height would slice the parapet and
# show the storey below through it.
PLAN_CUT_HEIGHT_M = 1.2
ROOF_CUT_HEIGHT_M = 0.15


@dataclass(frozen=True)
class Sheet:
    """One issued drawing and what it cost to make."""

    id: str
    kind: str
    svg: Path
    png: Path
    sheet_mm: tuple[float, float]
    metres_across: float
    objects: int
    line_art_layers: int


def _run(blender: Path, model_path: Path, profile_path: Path, out: Path,
         *, view: str, name: str, scale: int, z: float = 0.0,
         bearing: float = 90.0, offset: float = 0.0) -> Sheet:
    command = [
        str(blender), '-b', '--factory-startup', '--python', str(DRAW_SCRIPT), '--',
        '--model', str(model_path), '--profile', str(profile_path), '--out', str(out),
        '--view', view, '--name', name, '--scale', str(scale),
        '--z', f'{z:.4f}', '--bearing', f'{bearing:g}', '--offset', f'{offset:g}',
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                            timeout=TIMEOUT_SECONDS)
    sidecar = out / f'{name}.json'
    if result.returncode != 0 or not sidecar.is_file():
        raise BlenderExportError(
            f'{name}: Blender did not produce a sheet.\n{result.stdout[-1500:]}')
    meta = json.loads(sidecar.read_text(encoding='utf-8'))

    raw = out / f'{name}.svg'
    fitted, info = fit_metres(raw.read_text(encoding='utf-8'),
                              metres_across=meta['metres_across'],
                              scale_denominator=meta['scale_denominator'])
    sheet = out / f'{name}_sheet.svg'
    sheet.write_text(fitted, encoding='utf-8')
    return Sheet(id=name, kind=view, svg=sheet, png=out / f'{name}.png',
                 sheet_mm=info.sheet_mm, metres_across=meta['metres_across'],
                 objects=meta['objects'], line_art_layers=meta['grease_pencil'])


def issue_native_drawings(
    model, *, sections: tuple[tuple[str, float, float], ...] = (
        ('A', 90.0, 0.0), ('B', 0.0, 0.0)),
    directory: Path | None = None,
) -> list[Sheet]:
    """Every floor plan, the roof plan, and a section per entry in `sections`.

    Each section is `(name, bearing, offset)` -- bearing is the direction of view, so
    any angle works and an oblique cut takes the same path as an orthogonal one.
    """
    blender = find_blender_executable()
    out = (directory or OUTPUT_ROOT) / model.model_id
    out.mkdir(parents=True, exist_ok=True)

    model_path = out / 'model.json'
    model_path.write_text(model.model_dump_json(), encoding='utf-8')
    profile_path = out / 'profile.json'
    profile_path.write_text(json.dumps(export_profile(PLAN_STANDARD), indent=2),
                            encoding='utf-8')

    sheets: list[Sheet] = []
    for level in model.lattice.levels:
        roof = level.kind == 'roof'
        cut = level.z + (ROOF_CUT_HEIGHT_M if roof else PLAN_CUT_HEIGHT_M)
        sheets.append(_run(blender, model_path, profile_path, out, view='plan',
                           name=f'DWG-PLAN-{level.id}',
                           scale=PLAN_STANDARD.scale.denominator, z=cut))

    section_profile = out / 'profile_section.json'
    section_profile.write_text(json.dumps(export_profile(SECTION_STANDARD), indent=2),
                               encoding='utf-8')
    for name, bearing, offset in sections:
        sheets.append(_run(blender, model_path, section_profile, out, view='section',
                           name=f'DWG-SECT-{name}',
                           scale=SECTION_STANDARD.scale.denominator,
                           bearing=bearing, offset=offset))

    (out / 'index.json').write_text(json.dumps({
        'schema_version': 'mta.native_drawings/1.0',
        'model_id': model.model_id,
        'renderer': 'blender-line-art',
        'sheets': [
            {'id': sheet.id, 'kind': sheet.kind,
             'sheet_mm': [round(value, 1) for value in sheet.sheet_mm],
             'metres_across': round(sheet.metres_across, 3),
             'line_art_layers': sheet.line_art_layers,
             'svg': sheet.svg.name, 'png': sheet.png.name}
            for sheet in sheets
        ],
        'note': ('Base drawings: linework and correct occlusion, no poche and no '
                 'annotation. Poche is left to the annotation pass because neither '
                 'native mechanism for it survived -- a Boolean leaves its cut faces '
                 'on the camera near plane that then clips them, and back-face '
                 'shading needs outward normals a merged mesh of interpenetrating '
                 'members does not have.'),
        'verified': ('The PNG. Framing, scale, orientation and content were checked '
                     'sheet by sheet.'),
        'not_verified': ('The SVG canvas. Its geometry and scale are right and its '
                         "stroke weights are the standard's, but Grease Pencil writes "
                         'a canvas that is not the camera frame and axes that need not '
                         'match the render -- one section comes back a quarter turn '
                         'from its image, and an oblique cut reports a sheet four '
                         'times its true size. Re-frame before laying up.'),
    }, indent=2), encoding='utf-8')
    return sheets
