"""The compiler's declared version and exact generation-source fingerprint.

Bump the minor when a change alters what gets built from the same score -- new
emitters, changed layout rules, resized plates. Bump the patch for changes that leave
the geometry alone. The four selection outcomes travel in the identity beside this, so
most behavioural drift changes the identity even when nobody remembered to bump; the
constant exists for the drift they cannot catch, and a stale value here costs an
overwritten artifact directory, which is precisely the bug the identity exists to end.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


COMPILER_VERSION = '3.4.0'

ROOT = Path(__file__).resolve().parents[2]


def compiler_source_fingerprint(root: Path | None = None) -> str:
    """Hash every Python source file that can change generated geometry or exports."""
    project = (root or ROOT).resolve()
    files = [
        *project.glob('backend/app/**/*.py'),
        *project.glob('blender/**/*.py'),
    ]
    digest = hashlib.sha256()
    for path in sorted((path for path in files if path.is_file()),
                       key=lambda item: item.relative_to(project).as_posix()):
        relative = path.relative_to(project).as_posix().encode('utf-8')
        digest.update(len(relative).to_bytes(4, 'big'))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, 'big'))
        digest.update(content)
    return digest.hexdigest()
