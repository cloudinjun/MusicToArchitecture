"""Apply exactly the locally tested patch, refusing concurrent source changes."""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

root = Path.cwd()
meta = json.loads((root / '.redline/manifest.json').read_text())
paths = meta['original_sha256']
for name, expected in paths.items():
    target = root / name
    if target.resolve().parent != root and root not in target.resolve().parents:
        raise SystemExit('Path outside repository')
    if name.startswith('.github/') or name.startswith('.redline/'):
        raise SystemExit('Patch must not modify its own runner')
    if expected is None:
        if target.exists():
            raise SystemExit(f'Refusing to overwrite new path: {name}')
    elif not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
        raise SystemExit(f'Source changed since review: {name}')
packed = b''.join((root / f'.redline/patch.gz.{i}').read_bytes() for i in range(2))
patch = gzip.decompress(packed)
if hashlib.sha256(patch).hexdigest() != meta['patch_sha256']:
    raise SystemExit('Patch checksum mismatch')
subprocess.run(['git', 'apply', '--check', '--unidiff-zero', '-'], input=patch, check=True)
subprocess.run(['git', 'apply', '--index', '--unidiff-zero', '-'], input=patch, check=True)
changed = set(subprocess.check_output(['git','diff','--cached','--name-only']).decode().splitlines())
if changed != set(paths):
    raise SystemExit(f'Unexpected changed files: {changed ^ set(paths)}')
print(f'Applied verified patch to {len(changed)} intended source/test/doc files.')
