"""Assembly identity added only where the Program Volume protocol is active.

The emitters already author the geometry, hosts and construction reasons.  This
module gives the pieces a stable assembly/part vocabulary so a detail-section audit
can prove which cut marks belong together without inventing drawing geometry.  The
labels are coordination metadata; they do not certify products, connections or code
compliance.
"""
from __future__ import annotations


_CIRCULATION_PART_ROLE = {
    'stair_tread': 'tread',
    'stair_stringer': 'stringer',
    'stair_landing': 'floor_landing',
    'stair_half_landing': 'half_landing',
    'stage_platform': 'stage_arrival_platform',
    'ramp': 'ramp_run',
    'ramp_landing': 'ramp_landing',
    'lift_landing': 'lift_threshold',
    'ramp_curb': 'edge_protection',
    'elevator_shaft': 'shaft_enclosure',
    'lift_car': 'lift_car',
    'mechanical_equipment': 'lift_overrun_equipment',
}


def _circulation_family(public_stair_ids: set[str], group, instance) -> str:
    identifier = instance.id
    if group.subsystem == 'stage_access':
        return 'STAGE-ACCESS'
    if (group.subsystem == 'ramps'
            or identifier.startswith(('CIR-RMP-', 'CIR-RAL-RMP-',
                                      'CIR-TRD-R01', 'CIR-STG-R01',
                                      'CIR-RAL-R01', 'CIR-LND-ACCESS'))):
        return 'ACCESSIBLE-APPROACH'
    if group.subsystem == 'vertical_core':
        return 'LIFT'
    if identifier in public_stair_ids:
        return 'PUBLIC-STAIR'
    return 'PROTECTED-STAIR'


def _circulation_part_role(group, instance, family: str) -> str:
    if group.kind == 'door':
        return 'lift_door' if family == 'LIFT' else 'landing_door'
    if group.kind == 'railing':
        return ('ramp_guard_and_handrail'
                if family == 'ACCESSIBLE-APPROACH'
                else 'stair_guard_and_handrail')
    return _CIRCULATION_PART_ROLE.get(group.kind, group.kind)


def annotate_program_volume_circulation(builder) -> int:
    """Give every emitted PV circulation part a stable identity and role.

    Returns the number of instances annotated.  Legacy runs are deliberately left
    untouched so the explicit Program Volume promotion path cannot silently mutate
    the accepted compatibility output.
    """
    if not getattr(builder.lattice, 'program_volume_regions', None):
        return 0
    annotated = 0
    public_stair_ids = set(getattr(builder, 'public_stair_ids', ()))
    for group in builder.groups.values():
        if group.semantic_layer != 'circulation':
            continue
        if 'MTA-CIRCULATION-ASSEMBLY-001' not in group.rule_refs:
            group.rule_refs.append('MTA-CIRCULATION-ASSEMBLY-001')
        if (any(not instance.supports for instance in group.instances)
                and 'MTA-CIRCULATION-INTERFACE-UNRESOLVED' not in group.rule_refs):
            # The detail-readiness contract permits a named unresolved interface.
            # Do not guess a bearing from proximity merely to fill the host field.
            group.rule_refs.append('MTA-CIRCULATION-INTERFACE-UNRESOLVED')
        for instance in group.instances:
            family = _circulation_family(public_stair_ids, group, instance)
            if instance.assembly_id is None:
                instance.assembly_id = f'ASM-PV-{family}-{instance.level_id}'
            if instance.part_role is None:
                instance.part_role = _circulation_part_role(
                    group, instance, family)
            annotated += 1
    return annotated


__all__ = ['annotate_program_volume_circulation']
