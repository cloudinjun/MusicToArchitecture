"""Check furniture part completeness and measured interfaces, not just host names."""
from __future__ import annotations

from collections import Counter, defaultdict

from .furniture import REQUIRED_ROLES
from .geometry_review import GeometryFinding, _polygon, _z_interval

CONTACT_REVIEW_M = 1e-4  # numerical geometry tolerance, not a printer fit allowance


def _contact(a, b) -> bool:
    pa,pb = _polygon(a),_polygon(b)
    za,zb = _z_interval(a),_z_interval(b)
    if pa is None or pb is None or za is None or zb is None:
        return False
    dz = min(za[1],zb[1])-max(za[0],zb[0])
    if dz < -CONTACT_REVIEW_M or pa.distance(pb) > CONTACT_REVIEW_M:
        return False
    intersection = pa.intersection(pb)
    if intersection.area > 1e-9:
        return True  # end bearing or intentional cabinet joint, with nonzero area
    return dz > CONTACT_REVIEW_M and intersection.length > CONTACT_REVIEW_M


def review_furniture(model) -> list[GeometryFinding]:
    by_id = {item.id:item for group in model.element_groups for item in group.instances}
    assemblies = defaultdict(list); findings = []
    def fail(rule, ids, measure, unit, detail):
        findings.append(GeometryFinding(rule,'violation',tuple(ids),measure,unit,detail))
    for group in model.element_groups:
        if group.kind not in REQUIRED_ROLES or group.subsystem != 'furniture':
            continue
        for item in group.instances:
            if not item.assembly_id or not item.part_role:
                fail('SP-FURNITURE-COMPLETE',[item.id],1,'part',
                     'Furniture has no assembly/part identity; a named box is not a complete assembly.')
                continue
            assemblies[item.assembly_id].append((group.kind,item))
    for assembly_id,entries in assemblies.items():
        kinds = {kind for kind,_ in entries}
        roles = Counter(item.part_role for _,item in entries)
        expected = REQUIRED_ROLES[entries[0][0]]
        missing = expected-set(roles)
        duplicates = [role for role,n in roles.items() if n != 1]
        if len(kinds) != 1 or missing or duplicates or set(roles)-expected:
            fail('SP-FURNITURE-COMPLETE',[item.id for _,item in entries],
                 len(missing)+len(duplicates)+len(set(roles)-expected), 'parts',
                 f'{assembly_id}: missing={sorted(missing)}, duplicate={duplicates}, '
                 f'unexpected={sorted(set(roles)-expected)}; kinds={sorted(kinds)}.')
        for _,item in entries:
            if not item.supports:
                fail('SP-FURNITURE-CONTACT',[item.id],1,'interface',
                     f'{item.id}: no declared support for this part.')
            for host_id in item.supports:
                host=by_id.get(host_id)
                if host is None or host_id == item.id or not _contact(item.geometry,host.geometry):
                    fail('SP-FURNITURE-CONTACT',[item.id,host_id],1,'interface',
                         f'{item.id} does not make a nonzero-area bearing/joint with {host_id}; '
                         'declared hosting does not prove physical contact.')
    return findings
