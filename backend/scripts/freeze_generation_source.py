"""Create a verified generation snapshot while other design tasks keep editing."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import shutil
import sys
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.version import ROOT, compiler_source_fingerprint


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_record():
    packages = {}
    for name in ('numpy','scipy','shapely','pydantic','librosa','rhino3dm'):
        try:
            packages[name] = package_version(name)
        except PackageNotFoundError:
            packages[name] = None
    return {'python':sys.version,'packages':packages}


def freeze(audio_path: Path, root: Path = ROOT, *, corpus_path: Path | None = None) -> Path:
    root = root.resolve()
    audio_path = audio_path.resolve()
    audio_path.relative_to(root)
    files = set(root.glob('backend/app/**/*.py')) | set(root.glob('backend/scripts/**/*.py'))
    files |= set(root.glob('blender/**/*.py')) | set(root.glob('rhino/**/*.py'))
    files |= {path for path in (root/'docs').rglob('*') if path.is_file()}
    files |= {root/'backend/__init__.py', audio_path}
    corpus_inputs = {}
    if corpus_path is not None:
        corpus_path = corpus_path.resolve()
        corpus_path.relative_to(root)
        corpus = json.loads(corpus_path.read_text(encoding='utf-8-sig'))
        for track in corpus['tracks']:
            if not track.get('counted_in_final_20', False):
                continue
            path = Path(track['local_path']).resolve()
            relative = path.relative_to(root).as_posix()
            if digest(path) != track['sha256'].lower():
                raise ValueError(f'Corpus recording hash changed: {track["id"]}')
            files.add(path)
            corpus_inputs[track['id']] = relative
        files.add(corpus_path)
    files |= {root/name for name in ('PROJECT_CHARTER.md', 'AGENTS.md', 'backend/requirements.txt')
              if (root/name).is_file()}
    before = {path.relative_to(root).as_posix(): digest(path) for path in sorted(files)}
    source_hash = compiler_source_fingerprint(root)
    runtime = runtime_record()
    inventory_hash = hashlib.sha256(json.dumps(
        {'files':before,'runtime':runtime}, sort_keys=True).encode()).hexdigest()
    # Native Windows SDKs still encounter MAX_PATH even when Python itself accepts
    # a longer filename. The full inventory hash remains mandatory in metadata.
    destination = root/'artifacts/model_versions/source_snapshots'/inventory_hash[:16]
    if destination.exists():
        if verify(destination)['inventory_sha256'] != inventory_hash:
            raise ValueError('Snapshot directory prefix collision; existing snapshot was preserved')
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.snapshot-', dir=destination.parent) as temp:
        stage = Path(temp)
        for name in before:
            target = stage/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root/name, target)
        # Validate copied bytes against the original pre-copy inventory. Partial
        # editor writes or edits during copying invalidate this attempt.
        if (any(digest(stage/name) != value or digest(root/name) != value
                for name,value in before.items())
                or compiler_source_fingerprint(root) != source_hash
                or compiler_source_fingerprint(stage) != source_hash):
            raise RuntimeError('Generation source changed during snapshot copy; no snapshot was accepted')
        tree = ast.parse((stage/'backend/app/version.py').read_text(encoding='utf-8-sig'))
        version = next(ast.literal_eval(node.value) for node in tree.body
                       if isinstance(node, ast.Assign)
                       and any(isinstance(t,ast.Name) and t.id=='COMPILER_VERSION' for t in node.targets))
        metadata = {'schema_version':'mta.source_snapshot/1.0', 'status':'immutable_source_snapshot',
            'compiler_source_sha256':source_hash, 'compiler_version':version,
            'inventory_sha256':inventory_hash, 'files':before,
            'runtime':runtime,
            'corpus_inputs':corpus_inputs,
            'source_workspace':str(root), 'audio_path':audio_path.relative_to(root).as_posix()}
        (stage/'source_snapshot.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
        stage.replace(destination)
    return destination


def verify(snapshot: Path) -> dict:
    snapshot = snapshot.resolve()
    metadata = json.loads((snapshot/'source_snapshot.json').read_text(encoding='utf-8'))
    if metadata['inventory_sha256'] != hashlib.sha256(json.dumps(
            {'files':metadata['files'],'runtime':metadata['runtime']},sort_keys=True).encode()).hexdigest():
        raise ValueError('Snapshot inventory hash is stale')
    for name,expected in metadata['files'].items():
        path = (snapshot/name).resolve()
        path.relative_to(snapshot)
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f'Snapshot resource changed: {name}')
    if compiler_source_fingerprint(snapshot) != metadata['compiler_source_sha256']:
        raise ValueError('Snapshot compiler source changed')
    return metadata


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio',type=Path,required=True)
    parser.add_argument('--corpus',type=Path)
    args = parser.parse_args()
    print(freeze(args.audio,corpus_path=args.corpus))
