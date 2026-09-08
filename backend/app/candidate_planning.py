"""Whole compact PV proposals before expensive member emission (ADR 0024).

Reuse actual allocation, selection/sizing and facade-control readers. Each feedback
round creates a new upstream proposal. No accepted PV, room area or gate is edited.
"""
from dataclasses import dataclass, field
from time import perf_counter

from .compiler_v3 import plan_building_systems
from .datums import compile_datum_set
from .facade_control import facade_control_for, weather_plane_site_overflow
from .legacy_program_layout import LegacyLayoutControls, LayoutRejected
from .program_massing import prepare_massing
from .program_volumes import organize_program_volumes
from .site import resolve_site


def joint_layout_intent(score, *, relation=None):
    """Propose public-terminal topology; geometry must still establish feasibility.

    Interruption above the neutral midpoint separates public terminals across the
    hall. At/below it they gather on its public threshold. This is a declared design
    hypothesis, not a code rule or a threshold fitted to recordings. The existing
    datum confidence clamp keeps missing/zero-confidence evidence neutral.
    """
    legal = ('concentrated_threshold', 'separated_terminals')
    if relation is not None and relation not in legal:
        raise ValueError('Unknown joint public-terminal relationship')
    datum = compile_datum_set(score).by_id('void_count')
    position = datum.applied_position if datum.applied_position is not None else .5
    return dict(
        relation=relation or legal[int(position > .5)],
        authority='pinned' if relation is not None else datum.provenance,
        dimension='interruption', value=datum.dimension_value,
        confidence=datum.dimension_confidence, applied_position=position,
        rule='Above neutral interruption separates terminals; otherwise concentrate the threshold.',
        geometry_status='not_evaluated',
    )


@dataclass
class CandidatePlan:
    status: str = 'unresolved'
    volumes: object = None
    controls: LegacyLayoutControls | None = None
    attempts: list[dict] = field(default_factory=list)
    composition_basis: dict = field(default_factory=dict)


def composition_controls(score, controls):
    """High variation spreads the dominant hall; existing confidence clamp applies.

    This is one explicit compositional hypothesis, not a universal music/form rule.
    It changes no brief area and uses the hall's measured feasible depth interval.
    """
    datum = compile_datum_set(score).by_id('plate_step_m')
    position = datum.applied_position if datum.applied_position is not None else .5
    basis = dict(dimension='variation', value=datum.dimension_value,
                 confidence=datum.dimension_confidence, provenance=datum.provenance,
                 applied_position=position, hall_depth_position=1-position,
                 rule='Higher variation proposes a shallower, wider dominant hall at unchanged area.')
    return controls.model_copy(update={'hall_depth_position':1-position}), basis


def plan_compact_candidate(score, brief, *, controls=None, score_composition=False,
                           site=None, max_rounds=2, joint_layout=False):
    """Resolve spatial/system interfaces, or retain every unsuccessful proposal.

    `spatially_coordinated` only means the evaluated pre-emission interfaces fit.
    Physical members, facade support, professional checks and native delivery remain.
    """
    if not 1 <= max_rounds <= 2:
        raise ValueError('A compact planning pass permits one or two proposal rounds')
    controls = controls or LegacyLayoutControls()
    result = CandidatePlan(controls=controls)
    if score_composition or joint_layout:
        controls, result.composition_basis = composition_controls(score, controls)
    if joint_layout:
        result.composition_basis['joint_root'] = joint_layout_intent(score)
    site = site or resolve_site()
    for round_index in range(max_rounds):
        if joint_layout:
            # A rejected new root must never be reported as the previous root.
            controls = controls.model_copy(update={'root_proposal': None})
        started = perf_counter()
        record = dict(round=round_index+1, controls=controls.model_dump(mode='json'),
                      massing_limit_m2=brief.massing_limit_shape.area,
                      massing_limit_bounds=list(brief.massing_limit_shape.bounds),
                      phase='root_proposal' if joint_layout else 'program_volumes')
        result.attempts.append(record)
        result.controls = controls
        result.volumes = None
        try:
            if joint_layout:
                from .joint_layout import root_proposals
                roots = list(root_proposals(brief,compile_datum_set(score),controls,
                    result.composition_basis['joint_root']['relation']))
                root = roots[min(round_index,len(roots)-1)]
                controls = controls.model_copy(update={'root_proposal':root})
                result.controls = controls
                record['controls'] = controls.model_dump(mode='json')
            record['phase'] = 'program_volumes'
            volumes = organize_program_volumes(score, brief.typology,
                project_brief=brief, legacy_controls=controls)
            result.volumes = volumes
            record['phase'] = 'allocation'
            record.update(volume_digest=volumes.digest(),
                          program_volumes=volumes.model_dump(mode='json'))
            prepared = prepare_massing(volumes.to_program_massing(), score=score)
            allocation = prepared.allocation
            unresolved = (allocation.public_circulation.unresolved
                          if allocation.public_circulation else {'network':'not evaluated'})
            record.update(required_m2=allocation.required_area_m2,
                          delivered_m2=allocation.delivered_area_m2,
                          unplaced=[s.model_dump(mode='json') for s in allocation.unplaced],
                          short=[s.space_id for s in allocation.short], circulation_unresolved=unresolved)
            if not allocation.fits or unresolved:
                result.status = record['status'] = 'spatial_unresolved'
                if joint_layout:
                    continue
                break
            record['phase'] = 'systems_and_facade'
            systems = plan_building_systems(score=score, datums=prepared.datums,
                lattice=prepared.lattice, allocation=allocation, carve=prepared.carve,
                typology=brief.typology, massing=prepared.family,
                massing_why=volumes.grammar_reason, site=site)
            facade = facade_control_for(prepared.lattice, prepared.datums,
                                        systems['envelope'], systems['spec'])
            record.update(selection=systems['selection'].model_dump(mode='json'),
                          facade_control=facade.model_dump(mode='json'))
            outside = weather_plane_site_overflow(facade,brief.buildable_shape)
            record['weather_plane_outside_buildable_m2'] = outside
            arrival = volumes.circulation_intent.arrival_assembly
            if arrival is None:
                result.status = record['status'] = 'arrival_unreserved'
                break
            site_conflict = any(area > 1e-6 for area in outside.values())
            arrival_conflict = facade.resolved_offset_m > arrival.facade_allowance_m + 1e-7
            if site_conflict or arrival_conflict:
                record['status'] = 'facade_spatial_reproposal'
                controls = controls.model_copy(update={
                    'arrival_facade_allowance_m':max(controls.arrival_facade_allowance_m,
                                                    facade.resolved_offset_m)})
                if site_conflict:
                    # Narrow the upstream massing domain, never borrow the setback
                    # or push the accepted volume after the facade has been built.
                    payload = brief.model_dump(mode='json')
                    setbacks = payload['site_setbacks']
                    setbacks['facade_projection_m'] = max(setbacks['facade_projection_m'],
                                                         facade.resolved_offset_m)
                    setbacks['provenance'] += '; derived weather-plane planning demand'
                    setbacks['reason'] += '; reserve resolved facade offset before new PV placement'
                    setbacks['needs_review'] = True
                    brief = type(brief).model_validate(payload)
                    record['proposed_massing_limit_m2'] = brief.massing_limit_shape.area
                result.status = 'proposal_budget_exhausted'
                continue
            result.status = record['status'] = 'spatially_coordinated'
            break
        except LayoutRejected as exc:
            result.status = record['status'] = 'form_unresolved'
            record.update(findings=exc.findings, rectangles=exc.rectangles)
            if joint_layout:
                continue
            break
        except ValueError as exc:
            result.status = record['status'] = 'system_unresolved'
            record['error'] = str(exc)
            break
        finally:
            record['seconds'] = round(perf_counter()-started,3)
    return result
