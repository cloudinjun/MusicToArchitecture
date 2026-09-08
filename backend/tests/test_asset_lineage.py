from __future__ import annotations

import copy

import pytest

from backend.app.asset_lineage import (
    SOURCE_HASH_BASIS, canonical_model_sha256, validate_blender_lineage,
    validate_render_lineage,
)
from backend.app.blender_export import sha256_file


@pytest.fixture
def export(tmp_path):
    model = {'model_id': 'model-a', 'elements': [{'id': '柱', 'x': 1.5}]}
    blend, glb, render = (tmp_path / name for name in ('scene.blend', 'model.glb', 'view.png'))
    for path in (blend, glb, render):
        path.write_bytes(path.suffix.encode())
    manifest = {
        'model_id': 'model-a', 'source_hash_basis': SOURCE_HASH_BASIS,
        'source_model_sha256': canonical_model_sha256(model),
        'native_blend_sha256': sha256_file(blend), 'glb_sha256': sha256_file(glb),
        'renders': [render.name], 'render_sha256': {render.name: sha256_file(render)},
    }
    return model, manifest, blend, glb, render


def test_equivalent_json_order_preserves_lineage(export):
    model, manifest, blend, glb, render = export
    reordered = {'elements': model['elements'], 'model_id': model['model_id']}
    assert validate_blender_lineage(reordered, manifest, blend, glb) == (
        manifest['source_model_sha256'], manifest['native_blend_sha256'])
    validate_render_lineage(manifest, render)


@pytest.mark.parametrize('change', ['model_id', 'geometry', 'blend', 'glb', 'missing_binding'])
def test_rejects_cross_version_exports(export, change):
    model, manifest, blend, glb, _ = export
    model = copy.deepcopy(model)
    if change == 'model_id':
        model['model_id'] = 'model-b'
    elif change == 'geometry':
        model['elements'][0]['x'] = 2.5
    elif change == 'missing_binding':
        manifest.pop('source_model_sha256')
    else:
        (blend if change == 'blend' else glb).write_bytes(b'older export')
    with pytest.raises(ValueError):
        validate_blender_lineage(model, manifest, blend, glb)


def test_old_picture_with_same_filename_is_rejected(export):
    _, manifest, _, _, render = export
    render.write_bytes(b'old picture')
    with pytest.raises(ValueError, match='not from this model export'):
        validate_render_lineage(manifest, render)
