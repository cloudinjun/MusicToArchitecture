"""Dump the collection tree and per-collection world bounds of a saved .blend."""
import json
import sys

import bpy
from mathutils import Vector


def bounds(objects):
    corners = [obj.matrix_world @ Vector(c)
               for obj in objects if obj.type == 'MESH' for c in obj.bound_box]
    if not corners:
        return None
    lo = [min(p[i] for p in corners) for i in range(3)]
    hi = [max(p[i] for p in corners) for i in range(3)]
    return {'min': [round(v, 2) for v in lo], 'max': [round(v, 2) for v in hi],
            'span': [round(hi[i] - lo[i], 2) for i in range(3)]}


def walk(collection, depth=0):
    rows = [{'name': collection.name, 'depth': depth,
             'objects': len(collection.objects),
             'all_objects': len(collection.all_objects),
             'bounds': bounds(collection.all_objects)}]
    for child in collection.children:
        rows.extend(walk(child, depth + 1))
    return rows


rows = walk(bpy.context.scene.collection)
print('PROBE_JSON_START')
print(json.dumps(rows, indent=1))
print('PROBE_JSON_END')
