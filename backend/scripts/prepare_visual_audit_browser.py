"""Write a Playwright CLI capture recipe for geometry-derived stair close-ups.

The browser reads the exported GLB. Camera targets come from the JSON authority;
the recipe records exactly which layers and clipping plane produced each image.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch', type=Path)
    parser.add_argument('--recipe', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    batch = args.batch.resolve()
    captures = []
    (batch / 'closeups').mkdir(exist_ok=True)
    results = [json.loads(path.read_text(encoding='utf-8'))
               for path in sorted((batch / 'tracks').glob('*/result.json'))]
    for result in results:
        if result['status'] != 'compiled':
            continue
        model_path = batch / 'geometry' / result['model_id'] / 'building_model_v3.json'
        model = json.loads(model_path.read_text(encoding='utf-8'))
        landings = [i for g in model['element_groups'] if g['kind'] == 'stair_landing'
                    for i in g['instances'] if i['id'].startswith('CIR-LND-L')]
        if not landings:
            continue
        landing = landings[min(1, len(landings) - 1)]
        levels = model['lattice']['levels']
        upper = next(lv for lv in levels if lv['id'] == landing['level_id'])
        lower = levels[max(0, upper['index'] - 1)]
        x = landing['geometry']['center']['x']
        y = landing['geometry']['center']['y']
        half = [i for g in model['element_groups'] if g['kind'] == 'stair_half_landing'
                for i in g['instances'] if i['level_id'] == lower['id'] and '-A' in i['id']]
        if half:
            y = (y + half[0]['geometry']['center']['y']) / 2
        z = upper['z']
        target = [x, (z + lower['z']) / 2, -y]
        url = (f'http://127.0.0.1:{args.port}/artifacts/visual_audit/2026-09-03/inspector.html'
               f'?model=/{(batch / "models" / (result["model_id"] + ".glb")).relative_to(ROOT).as_posix()}')
        for name, eye, axis, at, sign in [
                ('floor', [x + 13, z + 8, -y + 15], 'y', z + .05, -1),
                ('section', [x - 17, z + 1, -y + 12], 'x', x, 1)]:
            captures.append(dict(track_id=result['track_id'], model_id=result['model_id'],
                                 anchor_element=landing['id'], url=url,
                                 path=str(batch / 'closeups' / f"{result['track_id']}-{name}.png"),
                                 options=dict(subsystems=['slabs', 'stairs', 'vertical_core', 'beams', 'finishes'],
                                              clipAxis=axis, clipAt=at, clipSign=sign,
                                              eye=eye, target=target,
                                              title=f"{result['track_id']} | {upper['id']} {name}\nOrange: stairs · Purple: lift core · Gray: floor/frame")))
    (batch / 'detail_views.json').write_text(json.dumps(captures, indent=2), encoding='utf-8')
    code = 'async (page) => {\nconst captures = ' + json.dumps(captures) + ';\n'
    code += '''await page.setViewportSize({width:1400,height:1000});
let current='';
for(const view of captures){
 if(current!==view.url){await page.goto(view.url);await page.waitForFunction(()=>window.audit?.ready);current=view.url;}
 await page.evaluate(options=>window.audit.configure(options),view.options);
 await page.evaluate(()=>new Promise(requestAnimationFrame));
 await page.screenshot({path:view.path});
}
return {captured:captures.length};
}'''
    args.recipe.write_text(code, encoding='utf-8')
    print(f'{len(captures)} detail views → {args.recipe}')


if __name__ == '__main__':
    main()
