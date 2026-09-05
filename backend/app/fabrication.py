"""Explicit, non-authoritative scale-model fabrication packages.

This first route exports *diagnostic* STL parts from v3 source primitives, not from a
merged web GLB. It never adds thickness, closes architectural openings, drops an invalid
part, or labels an unrun slicer/physical test as passed. Optional dependencies are loaded
only by mesh export; the API/v2 acceptance path does not depend on them.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import re
import tempfile
import shutil
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .mesh_primitives import primitive_mesh, triangulate_faces
from . import mesh_primitives

SAFE_ID = re.compile(r'^[A-Za-z0-9_-]{1,120}$')
FABRICATION_VERSION = '0.1.0'
NON_CONSTRUCTION = {'program_zone','figure','site_ground'}


class PrintProfile(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    id: str
    scale_denominator: float = Field(gt=0)
    source_unit: Literal['m'] = 'm'
    output_unit: Literal['mm'] = 'mm'
    process: Literal['FDM','SLA','unresolved'] = 'unresolved'
    printer: str | None = None
    material: str | None = None
    build_volume_mm: tuple[float,float,float] | None = None
    minimum_feature_mm: float | None = Field(default=None,gt=0)
    edge_margin_mm: float = Field(default=0,ge=0)
    parameter_basis: str = 'Unresolved: no printer/material calibration supplied.'
    status: Literal['planning','reviewed'] = 'planning'

    @model_validator(mode='after')
    def check_profile(self):
        if not SAFE_ID.fullmatch(self.id):
            raise ValueError('Unsafe profile ID')
        if self.build_volume_mm and any(v<=0 for v in self.build_volume_mm):
            raise ValueError('Build volume dimensions must be positive')
        if self.build_volume_mm and min(self.build_volume_mm) <= 2*self.edge_margin_mm:
            raise ValueError('Margin consumes the build volume')
        if self.status == 'reviewed' and (not self.printer or not self.material
                or self.process == 'unresolved' or self.build_volume_mm is None
                or self.minimum_feature_mm is None or not self.parameter_basis.strip()):
            raise ValueError('Reviewed profiles require resolved device/material/geometry limits and basis')
        return self

    @property
    def factor(self) -> float:
        return 1000.0/self.scale_denominator


class PrintPart(BaseModel):
    model_config = ConfigDict(extra='forbid',allow_inf_nan=False)
    id: str
    source_ids: list[str] = Field(min_length=1)
    rotation_deg: tuple[float,float,float] = (0,0,0)

    @model_validator(mode='after')
    def check_part(self):
        if not SAFE_ID.fullmatch(self.id):
            raise ValueError('Unsafe part ID')
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError('Duplicate source IDs in a part')
        return self


class PrintPlan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    parts: list[PrintPart] = Field(min_length=1)
    exclusions: dict[str,str] = Field(default_factory=dict)
    representation: Literal['complete','sectional','unresolved'] = 'unresolved'

    @model_validator(mode='after')
    def check_plan(self):
        if len({p.id for p in self.parts}) != len(self.parts):
            raise ValueError('Duplicate print part IDs')
        all_ids = [i for p in self.parts for i in p.source_ids]
        if len(set(all_ids)) != len(all_ids) or set(all_ids)&set(self.exclusions):
            raise ValueError('A source element must be assigned exactly once or explicitly excluded')
        if any(not reason.strip() for reason in self.exclusions.values()):
            raise ValueError('Every exclusion needs a reason')
        return self


def source_records(model: dict) -> dict:
    out = {}
    if str(model.get('schema_version','')).split('.')[0] != '3':
        raise ValueError('Expected a schema 3 building model, not a GLB or generation response')
    for group in model['element_groups']:
        for item in group['instances']:
            if item['id'] in out:
                raise ValueError(f"Duplicate source ID: {item['id']}")
            out[item['id']] = (group,item)
    if not out:
        raise ValueError('Cannot fabricate an empty model')
    return out


def level_plan(model: dict) -> PrintPlan:
    """A diagnostic grouping, not a claim that each floor is connected or removable."""
    groups = defaultdict(list); exclusions = {}
    for source_id,(group,item) in source_records(model).items():
        if group['kind'] in NON_CONSTRUCTION:
            exclusions[source_id] = 'Non-construction semantic/scale/earth visualization; not part of the scale-model body.'
        else:
            groups[item['level_id']].append(source_id)
    return PrintPlan(parts=[PrintPart(id=f'level-{level}',source_ids=sorted(ids))
                            for level,ids in sorted(groups.items())],exclusions=exclusions,
                     representation=('sectional' if model.get('lattice',{}).get('cutaway') is True else
                                     'complete' if model.get('lattice',{}).get('cutaway') is False else 'unresolved'))


def _features(geometry,profiles,thickness):
    kind=geometry['type']
    if kind=='box': return list(geometry['size'].values())
    if kind=='extrusion': return [geometry['z_top']-geometry['z_base']]
    if kind=='quad': return [thickness] if thickness else []
    profile=profiles[geometry['profile']]
    if profile['shape']=='i_section': return [profile['web_m'],profile['flange_m']]
    return [profile['width_m'],profile['depth_m']]


def mesh_for(geometry,profiles,thickness=None):
    import numpy as np
    import trimesh
    vertices,faces = primitive_mesh(geometry,profiles,thickness)
    mesh = trimesh.Trimesh(vertices=np.array(vertices,dtype=float),
                           faces=triangulate_faces(vertices,faces),process=True)
    if (not np.isfinite(mesh.vertices).all() or not mesh.is_volume
            or not mesh.is_watertight or not mesh.is_winding_consistent
            or (mesh.area_faces <= 1e-14).any()):
        raise ValueError('Primitive does not describe a closed consistently oriented positive volume')
    return mesh


def _digest(data) -> str:
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),
                                    allow_nan=False).encode()).hexdigest()


def _source_blockers(model):
    blockers=[]
    for name in ('spatial','dependency_graph','axis_report'):
        status=(model.get(name) or {}).get('status','not_checked')
        if status!='passed': blockers.append(f'{name}: {status}')
    return blockers


def export_print_package(model: dict, profile: PrintProfile, destination: Path,
                         plan: PrintPlan | None = None, *, release: bool = False) -> dict:
    """Build a new immutable diagnostic directory and re-read every written STL.

    Release promotion is intentionally blocked until slicer, support-removal and
    assembly checks have implementations/evidence. Geometry export still works and
    names every blocker. Never overwrite the last accepted artifact or source JSON.
    """
    if release:
        raise ValueError('Production release blocked: slicer/layer, support-removal, and assembly verification are not implemented by this diagnostic exporter')
    import numpy as np
    import trimesh
    try:
        import manifold3d  # noqa: F401 -- boolean engine must be installed, never silently replaced
    except ImportError as exc:
        raise RuntimeError('Install backend/requirements-fabrication.txt before STL export') from exc
    records=source_records(model); plan=plan or level_plan(model)
    covered={i for p in plan.parts for i in p.source_ids}|set(plan.exclusions)
    if covered != set(records):
        raise ValueError(f'Plan coverage mismatch: missing={sorted(set(records)-covered)[:10]}, unknown={sorted(covered-set(records))[:10]}')
    source_hash=_digest(model)
    exporter_source = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in (Path(__file__), Path(mesh_primitives.__file__))}

    destination=Path(destination)
    if destination.exists():
        raise FileExistsError(f'Refusing to overwrite {destination}')
    destination.parent.mkdir(parents=True,exist_ok=True)
    versions={name:importlib.metadata.version(name) for name in ('trimesh','manifold3d','shapely','numpy')}
    report={'schema_version':'mta.fabrication/0.1','fabrication_version':FABRICATION_VERSION,
            'source_model_id':model.get('model_id'),'source_sha256':source_hash,
            'profile':profile.model_dump(),'plan':plan.model_dump(),'versions':versions,
            'exporter_source':exporter_source,
            'artifact_role':'diagnostic_only','release_ready':False,
            'parts':[],'source_blockers':_source_blockers(model),
            'limitations':['Not a construction/permit approval.',
                'No automatic thickening, opening filling or source design changes.',
                'Feature screen checks declared primitive thicknesses, not a complete local-thickness field.',
                'Disconnected floor groups require designed parts and connectors; no automatic supports are invented.',
                'Build-volume screening excludes ungenerated supports/brim/raft and is not a sliced-bed fit.',
                'Box and CHS section profiles retain the source outer-solid presentation convention, not hollow fabrication sections.',
                'Self-intersection screening is limited to constructed primitives and the Manifold boolean engine.'],
            'verification':{'geometry_verified':'not_checked','profile_screened':'not_checked',
                            'slicer_verified':'not_checked','physical_sample_verified':'not_checked',
                            'assembly_verified':'not_checked'}}
    profiles=model.get('profiles',{}); geometry_ok=True; profile_ok=profile.status=='reviewed'
    staging=Path(tempfile.mkdtemp(prefix='.mta-print-',dir=destination.parent))
    try:
        for spec in plan.parts:
            entry={'id':spec.id,'source_ids':spec.source_ids,'issues':[],
                   'geometry_verified':False,'rotation_deg':spec.rotation_deg}
            meshes=[]
            for source_id in spec.source_ids:
                group,item=records[source_id]; geometry=item['geometry']
                try:
                    mesh=mesh_for(geometry,profiles,group.get('thickness_m'))
                    mesh.apply_scale(profile.factor); meshes.append(mesh)
                    for feature in _features(geometry,profiles,group.get('thickness_m')):
                        if profile.minimum_feature_mm is not None and feature*profile.factor < profile.minimum_feature_mm:
                            entry['issues'].append({'rule':'PRINT-THIN-FEATURE','source_id':source_id,
                                'measure_mm':feature*profile.factor,'minimum_mm':profile.minimum_feature_mm})
                            profile_ok=False
                except (ValueError,KeyError,TypeError) as error:
                    entry['issues'].append({'rule':'PRINT-SOURCE-GEOMETRY','source_id':source_id,'detail':str(error)})
            if any(i['rule']=='PRINT-SOURCE-GEOMETRY' for i in entry['issues']):
                geometry_ok=False; report['parts'].append(entry); continue
            try:
                result=trimesh.boolean.union(meshes,engine='manifold',check_volume=True)
                if result is None or not result.is_volume:
                    raise ValueError('Boolean union has no valid positive volume')
                # Only orientation/translation change; record inverse placement to assemble.
                rotation=trimesh.transformations.euler_matrix(*(math.radians(v) for v in spec.rotation_deg),axes='sxyz')
                result.apply_transform(rotation)
                offset=-result.bounds[0].copy(); result.apply_translation(offset)
                transform=rotation.copy(); transform[:3,3]+=offset
                path=staging/f'{spec.id}.stl'; result.export(path,file_type='stl')
                reread=trimesh.load_mesh(path,file_type='stl',process=True)
                tolerance=max(1e-3,float(result.extents.max())*1e-6)
                if (not reread.is_volume or not reread.is_watertight
                        or not reread.is_winding_consistent
                        or not np.allclose(reread.bounds,result.bounds,atol=tolerance,rtol=0)
                        or not math.isclose(reread.volume,result.volume,rel_tol=1e-4,abs_tol=1e-6)):
                    raise ValueError('Export/reimport volume, orientation or millimetre bounds check failed')
                # Negative-volume interior boundary shells do not count as loose objects.
                positive_shells=sum(int(piece.volume>1e-8) for piece in reread.split(only_watertight=False))
                if positive_shells!=1:
                    entry['issues'].append({'rule':'PRINT-DISCONNECTED-PART','positive_shells':positive_shells})
                if profile.build_volume_mm is not None:
                    available=np.array(profile.build_volume_mm)-2*profile.edge_margin_mm
                    if (reread.extents>available+1e-5).any():
                        entry['issues'].append({'rule':'PRINT-BED-OVERFLOW','extent_mm':reread.extents.tolist(),
                                                'available_mm':available.tolist()}); profile_ok=False
                entry.update({'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                    'extent_mm':reread.extents.tolist(),'volume_mm3':float(reread.volume),
                    'geometry_verified':positive_shells==1,'positive_shells':positive_shells,
                    'assembly_to_print_mm':transform.tolist(),
                    'print_to_assembly_mm':np.linalg.inv(transform).tolist()})
                geometry_ok=geometry_ok and positive_shells==1
            except (ValueError,RuntimeError) as error:
                entry['issues'].append({'rule':'PRINT-EXPORT-FAILED','detail':str(error)}); geometry_ok=False
            report['parts'].append(entry)
        report['verification']['geometry_verified']='passed' if geometry_ok else 'failed'
        report['verification']['profile_screened']=('passed' if profile_ok and geometry_ok else
            'failed' if any(p['issues'] for p in report['parts']) else 'not_checked')
        report['package_id']='print-'+_digest({'source':source_hash,'profile':profile.model_dump(),
            'plan':plan.model_dump(),'versions':versions,'exporter':FABRICATION_VERSION,'source_files':exporter_source})[:16]
        (staging/'print_manifest.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        (staging/'README.txt').write_text(
            'DIAGNOSTIC MODEL PACKAGE - NOT A VERIFIED PRINT JOB\n'
            'STL coordinates are millimetres. Do not apply the architectural scale again.\n'
            'Read print_manifest.json for exclusions, source IDs, inverse assembly transforms,\n'
            'measured blockers and unperformed checks. No slicing or physical printing was done.\n',encoding='utf-8')
        if exporter_source != {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in (Path(__file__), Path(mesh_primitives.__file__))}:
            raise RuntimeError('Exporter source changed during fabrication')
        if _digest(model)!=source_hash:
            raise RuntimeError('Source model changed during fabrication')
        staging.rename(destination)
        return report
    except BaseException:
        shutil.rmtree(staging,ignore_errors=True)
        raise
