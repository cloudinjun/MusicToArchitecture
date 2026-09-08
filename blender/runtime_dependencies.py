"""Fail before scene generation if Blender cannot load the pinned polygon runtime."""
from pathlib import Path
import sys


def require_polygon_runtime():
    root = Path(__file__).resolve().parents[1]
    dependencies = root / '.venv' / 'blender_dependencies'
    if dependencies.is_dir() and str(dependencies) not in sys.path:
        sys.path.insert(0, str(dependencies))
    try:
        import shapely
        from shapely import constrained_delaunay_triangles
        from shapely.geometry import Polygon
        result = constrained_delaunay_triangles(Polygon([(0,0),(1,0),(1,1),(0,1)]))
        if len(result.geoms) != 2:
            raise RuntimeError('Polygon runtime smoke test did not produce two triangles')
    except (ImportError, OSError) as error:
        raise RuntimeError(
            f'Blender polygon dependency unavailable: {error}. '
            f'Python {sys.version.split()[0]}; isolated dependency directory: {dependencies}. '
            f'Install {root / "blender" / "requirements.txt"} for this Blender Python ABI '
            'into that directory; backend venv installation alone does not supply Blender.') from error
    return {'shapely_version': shapely.__version__, 'module_path': shapely.__file__}
