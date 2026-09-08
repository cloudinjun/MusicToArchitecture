"""Bind presentation files to the exact portable model that produced them."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .blender_export import sha256_file

SOURCE_HASH_BASIS = 'canonical_json_sort_keys_utf8'


def canonical_model_sha256(model: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(
        model, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
    ).encode('utf-8')).hexdigest()


def validate_blender_lineage(
    model: dict[str, Any], manifest: dict[str, Any], blend: Path, glb: Path,
) -> tuple[str, str]:
    """Reject mixed exports before they can become an asset or a release."""
    source_hash = canonical_model_sha256(model)
    if (manifest.get('model_id') != model.get('model_id')
            or manifest.get('source_hash_basis') != SOURCE_HASH_BASIS
            or manifest.get('source_model_sha256') != source_hash):
        raise ValueError('Blender export source identity does not match the portable model')
    blend_hash = sha256_file(blend)
    if manifest.get('native_blend_sha256') != blend_hash:
        raise ValueError('Blender native file hash is stale')
    if manifest.get('glb_sha256') != sha256_file(glb):
        raise ValueError('Blender GLB file hash is stale')
    return source_hash, blend_hash


def validate_render_lineage(manifest: dict[str, Any], path: Path) -> None:
    recorded = manifest.get('render_sha256', {}).get(path.name)
    if path.name not in manifest.get('renders', []) or recorded != sha256_file(path):
        raise ValueError(f'render is not from this model export: {path}')
