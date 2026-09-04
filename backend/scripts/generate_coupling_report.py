"""Emit the program -> structure -> facade screen and one optimiser run as artifacts.

    python -m backend.scripts.generate_coupling_report

Writes to `artifacts/coupling/`:

    feasible_domain_<jurisdiction>.json   full machine-readable screen
    coupling_report.md                    the human-readable version
    optimiser_run.json                    one deterministic GA run with its history
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.codes import UNRESOLVED_JURISDICTION, JurisdictionProfile
from backend.app.coupling import (
    FACADE_AXIS_WEIGHTS, FACADE_DEMANDS, PROGRAM_AXIS_WEIGHTS, PROGRAM_DEMANDS,
    STRUCTURAL_SUPPLIES, evaluate_program_structure, evaluate_structure_facade,
    program_by_id, screen_project,
)
from backend.app.optimizer import (
    FrameProblem, explain, map_feasible_region, optimise, steel_frame_space,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'artifacts' / 'coupling'

LOS_ANGELES = JurisdictionProfile(
    id='EXAMPLE-URBAN-SDC-D', status='resolved',
    adopted_building_code='IBC 2024 with a state amendment set (example only)',
    adopted_load_standard='ASCE/SEI 7-22',
    sprinklered=True, risk_category=3, seismic_design_category='D',
    fire_separation_distance_m={'north': 2.0, 'south': 18.0, 'east': 9.0, 'west': 30.0},
    source_urls=['https://codes.iccsafe.org/content/IBC2024P1/chapter-5-general-building-heights-and-areas'],
)

SCORE_DATUMS = {'bay_x_m': 6.52, 'bay_y_m': 7.12,
                'joist_spacing_m': 1.96, 'floor_to_floor_m': 4.72}


def _short(identifier: str) -> str:
    return identifier.replace('STR-SYS-', '').replace('FCD-', '')


def matrix_lines() -> list[str]:
    lines = ['## Gate 1 - program to structure', '',
             '| System | ' + ' | '.join(p.program_id.replace('PRG-', '')
                                        for p in PROGRAM_DEMANDS) + ' |',
             '|---|' + '---|' * len(PROGRAM_DEMANDS)]
    for supply in STRUCTURAL_SUPPLIES:
        cells = []
        for program in PROGRAM_DEMANDS:
            r = evaluate_program_structure(program, supply)
            cells.append('OUT [' + ','.join(r.failed_gates) + ']' if r.failed_gates
                         else f'in / {r.burden}')
        lines.append(f'| {_short(supply.system_id)} | ' + ' | '.join(cells) + ' |')

    lines += ['', '## Gate 2 - structure to facade', '',
              '| Grammar \\ System | '
              + ' | '.join(_short(s.system_id) for s in STRUCTURAL_SUPPLIES) + ' |',
              '|---|' + '---|' * len(STRUCTURAL_SUPPLIES)]
    for demand in FACADE_DEMANDS:
        cells = []
        for supply in STRUCTURAL_SUPPLIES:
            r = evaluate_structure_facade(demand, supply)
            cells.append('OUT' if r.feasibility == 'infeasible'
                         else f'{r.resolution_burden:.2f}')
        lines.append(f'| {_short(demand.grammar_id)} | ' + ' | '.join(cells) + ' |')
    lines.append('')
    lines.append('`OUT` marks a pair ruled out by a hard gate. A number is the '
                 'resolution burden: 0.00 means nothing left to detail, 1.00 means every '
                 'axis needs work. It describes effort, not quality, and nothing may be '
                 'selected or eliminated on it.')
    return lines


def domain_lines(program_id: str, jurisdiction: JurisdictionProfile):
    program = program_by_id(program_id)
    domain = screen_project(program, jurisdiction=jurisdiction)
    lines = [
        '', f'## Feasible domain - {program_id} under {jurisdiction.id}', '',
        f'- jurisdiction resolved: **{jurisdiction.resolved}**',
        f'- feasible and admissible: **{len(domain.feasible)}**',
        f'- ruled out by a physical hard gate: **{len(domain.physically_infeasible)}**',
        f'- ruled out by a resolved code rule: **{len(domain.excluded)}**',
        f'- provisionally out on placeholder code data: '
        f'**{len(domain.provisionally_excluded)}**',
        f'- rules that could not be evaluated: {len(domain.unevaluated_rules)}',
        '',
        'The feasible set is listed in identifier order, **not** sorted by burden. '
        'Choosing inside it is a later stage with its own criteria, and nothing here '
        'provides them.', '',
        '### Feasible', '',
        '| system | grammar | burden | interfaces to resolve |',
        '|---|---|---:|---|',
    ]
    for option in domain.feasible:
        lines.append(
            f'| {_short(option.system_id)} | {_short(option.grammar_id)} | '
            f'{option.resolution_burden:.2f} | {option.burden} |')

    lines += ['', '### Elimination log', '',
              'Every removal names the hard standard that removed it.', '',
              '| system | grammar | ruled out by |', '|---|---|---|']
    for key, reasons in domain.eliminated_because().items():
        system, grammar = key.split(' x ')
        lines.append(f'| {_short(system)} | {_short(grammar)} | '
                     f'{", ".join(reasons)} |')
    return lines, domain


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    report: list[str] = [
        '# Program - structure - facade coupling report', '',
        'Generated by `backend/scripts/generate_coupling_report.py`. '
        'Authority: none. Every structural number is '
        '`professional_review_required`, and every code result computed against a '
        'placeholder table is `code_inputs_incomplete`.', '',
        '## Axis weights', '',
        'Hard-gated axes eliminate. The rest only contribute to the resolution burden, '
        'which describes detailing effort and has no elimination power and no ranking '
        'authority.', '',
        '| Gate | Axis | Weight |', '|---|---|---:|',
    ]
    for axis, weight in PROGRAM_AXIS_WEIGHTS.items():
        report.append(f'| program -> structure | {axis} | {weight:.2f} |')
    for axis, weight in FACADE_AXIS_WEIGHTS.items():
        report.append(f'| structure -> facade | {axis} | {weight:.2f} |')
    report.append('')
    report += matrix_lines()

    for jurisdiction in (UNRESOLVED_JURISDICTION, LOS_ANGELES):
        lines, domain = domain_lines('PRG-LIBRARY-MID-RISE', jurisdiction)
        report += lines
        path = OUT / f'feasible_domain_{jurisdiction.id}.json'
        path.write_text(domain.model_dump_json(indent=2), encoding='utf-8')

    space = steel_frame_space(SCORE_DATUMS)
    problem = FrameProblem(storeys=6, plan_x_m=36.0, plan_y_m=22.0,
                           occupancy_id='library_stacks')
    result = optimise(space, problem)
    (OUT / 'optimiser_run.json').write_text(
        result.model_dump_json(indent=2), encoding='utf-8')

    report += ['', '## Feasibility map - does a design exist in the legal datum box?',
               '', '```text']
    for label, prob in (
        ('as briefed', problem),
        ('with a 350 mm beam depth limit',
         FrameProblem(storeys=6, plan_x_m=36.0, plan_y_m=22.0,
                      occupancy_id='library_stacks', max_beam_depth_mm=350.0)),
    ):
        fmap = map_feasible_region(space, prob, resolution=6)
        report.append(f'{label}: {fmap.verdict}, {fmap.feasible_count}/{fmap.samples} '
                      f'({fmap.feasible_fraction:.0%}), '
                      f'score proposal feasible: {fmap.proposal_feasible}')
        for gene in fmap.gene_ranges:
            if gene.feasible_low is not None and not gene.fully_usable:
                report.append(f'    {gene.name}: legal '
                              f'{gene.legal_low}-{gene.legal_high} {gene.unit}, '
                              f'feasible only {gene.feasible_low}-{gene.feasible_high}')
        if fmap.binding_constraints:
            report.append(f'    binding: {fmap.binding_constraints}')
    report += ['```', '',
               'This is elimination work, not optimisation. A structural system whose '
               'legal datum range contains no feasible design for this program is out on '
               'a hard standard, which a single-point check cannot show.', '']

    report += ['', '## Optimiser run - steel frame, six-storey library', '', '```text']
    report += explain(result)
    report += ['```', '',
               'Objective weights are the elimination-stage set: `material_efficiency` is '
               'a cost proxy and is switched off, because the criteria for choosing among '
               'feasible options have not been written down yet and steel tonnage must '
               'not answer that question by default. The score proposal seeds the '
               'population, so the search can never return a worse building than the '
               'brief.', '']

    (OUT / 'coupling_report.md').write_text('\n'.join(report), encoding='utf-8')
    print(f'wrote {OUT}')


if __name__ == '__main__':
    main()
