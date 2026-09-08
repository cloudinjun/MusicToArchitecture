"""One bounded LLM request: invented plot -> adapted area program, before massing.

Reuses the ordering of legacy OpenAI_ProgramDetails.refineProgram. The legacy
18x33 plot, wearable typology, 2 m rounding and 4 m spine are not general rules.
The reply remains an unvalidated proposal until ProjectBrief accepts its budget.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from datetime import datetime, timezone
from time import perf_counter
from typing import Literal

from pydantic import BaseModel

from backend.app.program import SpaceRequirement
from backend.app.briefs import BRIEFS
from backend.app.project_brief import ProjectBrief, BriefProvenance, SiteBoundary
from backend.app.models import ArchitecturalScore
from backend.app.selection import select_massing


SUPPORTED_TYPOLOGIES = ('library', 'theater', 'museum')
PROMPT_VERSION = 'small-site-brief/2.0'


def brief_request(score: dict, typology_pin: str | None = None) -> dict:
    _, selected, reasons = select_massing(ArchitecturalScore.model_validate(score))
    requested = typology_pin or selected
    if requested not in SUPPORTED_TYPOLOGIES:
        raise ValueError(f'Compact brief provider does not support {requested}; no silent fallback')
    return dict(typology=requested, score_selected_typology=selected,
                authority='experiment_pin' if typology_pin else 'score_selection',
                selection_reasons=reasons, typology_pin=typology_pin)


class SitePoint(BaseModel):
    x: float
    y: float


class LLMBriefProposal(BaseModel):
    label: str
    typology: Literal['library', 'theater', 'museum']
    site_boundary: list[SitePoint]
    occupied_storeys: int
    target_gross_area_m2: float
    circulation_budget_m2: float
    spaces: list[SpaceRequirement]
    assumptions: list[str]
    floor_strategy: list[str]


def prompt_for(score: dict, request: dict | None = None) -> str:
    request = request or brief_request(score)
    readings = {d['id']: {'value': d['value'], 'confidence': d['confidence']}
                for d in score['dimensions']}
    catalog = [{key: getattr(space, key) for key in
                ('id', 'space_type', 'label', 'category', 'occupancy_id',
                 'level_preference', 'daylight', 'adjacency', 'reason')}
               for space in BRIEFS[request['typology']]]
    return (
        'Invent one compact, fictional urban plot and adapt an architectural AREA '
        'program to it BEFORE making geometry. Output JSON matching the schema. '
        'The supplied score is the only expressive input. The recorded typology '
        'decision is binding; do not reclassify it. Decision: '
        + json.dumps(request, separators=(',', ':')) + '. '
        'Choose a simple valid polygon in meters, actual area <=500 m2. A compact '
        'near-rectangular site is acceptable; do not supply a real address or code claims. '
        'Choose 3-5 occupied storeys and a gross area budget that leaves room for '
        'setbacks, entrance, facade offset, independently shifted program volumes '
        'and any required double-height voids. The upper storeys need not align. '
        'Give requirements only, no room rectangles. Adapt areas/minimum dimensions '
        'to a neighbourhood-scale building. Retain the functional identities, room '
        'types and occupancy ids from this typology catalog; omit no primary '
        'public or private room. Service spaces may be supplied by the constitution. '
        'Catalog (areas intentionally left for the proposal): '
        + json.dumps(catalog, separators=(',', ':')) + '. '
        'For a theater only, pair auditorium and stage on the lowest occupied level. '
        'All proposed areas are real requirements; the allocator cannot shrink them. '
        'Every adjacency must reference a supplied room. Capacity is verified later. '
        'Do not add stand-in plant/WC spaces: the existing constitution adds missing '
        'public WC >=28, staff WC14, janitor10, electrical22, riser8, mechanical>=60, '
        'fire service12, refuse16, storage>=40 and loading36 m2. Reserve their area '
        'in the gross budget now. These are project placeholders, not code compliance. '
        'circulation_budget_m2 is TOTAL gross area of all circulation/core spaces '
        'across all floors, INCLUDING the foyer if classified circulation; reserve '
        'two stairs, lift, landings and connecting passages without double counting. '
        'Remaining gross area also pays for walls and structure. Ground entry should '
        'be close to grade; do not keep a five-meter open piloti requiring a giant ramp. '
        'Explain a concise floor strategy and how the musical relationships inform '
        'program hierarchy and later independent XY offsets. No visual or code pass '
        'claims. Score readings: ' + json.dumps(readings, separators=(',', ':')))


def normalize_saved(output: Path) -> ProjectBrief:
    proposal = LLMBriefProposal.model_validate_json((output / 'proposal.json').read_text())
    provider = json.loads((output / 'provider.json').read_text())
    if provider['prompt_version'] == PROMPT_VERSION:
        request = json.loads((output / 'request.json').read_text(encoding='utf-8'))
        if proposal.typology != request['typology']:
            raise ValueError('LLM typology differs from recorded request; proposal retained, brief not emitted')
        templates = {s.id: s for s in BRIEFS[request['typology']]}
        supplied = {s.id: s for s in proposal.spaces}
        missing = [s.id for s in templates.values()
                   if s.category != 'service' and s.id not in supplied]
        changed = [s.id for s in proposal.spaces if s.id in templates and
                   any(getattr(s, k) != getattr(templates[s.id], k)
                       for k in ('space_type', 'category', 'occupancy_id'))]
        if missing or changed:
            raise ValueError(f'Typology program mismatch: missing={missing}, changed={changed}')
    response = json.loads((output / 'response.json').read_text())
    templates = {space.id: space for space in BRIEFS[proposal.typology]}
    repairs = []
    spaces = []
    for space in proposal.spaces:
        # Acceptance thresholds are compiler policy, not a generative design variable.
        threshold = templates[space.id].area_tolerance if space.id in templates else 0.9
        if threshold != space.area_tolerance:
            repairs.append({'space_id': space.id, 'field': 'area_tolerance',
                            'proposed': space.area_tolerance, 'applied': threshold,
                            'reason': 'Retain existing brief acceptance policy; areas unchanged.'})
        spaces.append(space.model_copy(update={'area_tolerance': threshold}))
    brief = ProjectBrief(
        brief_id='BRIEF-' + provider['response_sha256'][:12], typology=proposal.typology,
        site=SiteBoundary(polygon=[(p.x, p.y) for p in proposal.site_boundary]),
        occupied_storeys=proposal.occupied_storeys,
        target_gross_area_m2=proposal.target_gross_area_m2,
        circulation_budget_m2=proposal.circulation_budget_m2, spaces=spaces,
        provenance=BriefProvenance(
            provider_type='openai', model=provider['model'],
            prompt_template_version=provider['prompt_version'],
            raw_response_hash=provider['response_sha256'],
            source_ref=str((output / 'response.json').resolve()),
            generated_at=datetime.fromtimestamp(response['created_at'], timezone.utc).isoformat()),
        assumptions=proposal.assumptions + proposal.floor_strategy)
    (output / 'project_brief.json').write_text(brief.model_dump_json(indent=2), encoding='utf-8')
    report = brief.report()
    report['normalization_repairs'] = repairs
    report['ground_required_m2'] = sum(s.area_m2 for s in brief.resolved_spaces()
                                     if s.level_preference == 'ground')
    (output / 'validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
    return brief


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--score-response', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', default='gpt-5-mini')
    parser.add_argument('--normalize-only', action='store_true')
    parser.add_argument('--feedback-file', type=Path)
    parser.add_argument('--typology-pin', choices=SUPPORTED_TYPOLOGIES,
                        help='Explicit fixed-type experiment; default follows score selection')
    parser.add_argument('--request-only', action='store_true',
                        help='Save the exact prompt and selection without calling an LLM')
    args = parser.parse_args()
    if args.normalize_only:
        normalize_saved(args.output)
        return
    args.output.mkdir(parents=True, exist_ok=False)
    source = args.score_response.read_bytes()
    payload = json.loads(source)
    score = payload.get('architectural_score', payload)
    request = brief_request(score, args.typology_pin)
    request['score_source_sha256'] = hashlib.sha256(source).hexdigest()
    prompt = prompt_for(score, request)
    if args.feedback_file:
        prompt += '\nPrevious proposal preflight: ' + args.feedback_file.read_text(encoding='utf-8')
    (args.output / 'prompt.txt').write_text(prompt, encoding='utf-8')
    (args.output / 'architectural_score.json').write_text(
        json.dumps(score, indent=2), encoding='utf-8')
    (args.output / 'request.json').write_text(json.dumps(request, indent=2), encoding='utf-8')
    if args.request_only:
        print(json.dumps(dict(status='request_prepared_no_llm', **request)))
        return
    helper_path = (Path.home() / '.codex/skills/openai-api-local/scripts/openai_local.py')
    spec = importlib.util.spec_from_file_location('mta_openai_local', helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    client = helper.get_client().with_options(timeout=120.0, max_retries=0)
    started = perf_counter()
    response = client.responses.parse(
        model=args.model, input=prompt, text_format=LLMBriefProposal,
        reasoning={'effort': 'low'}, max_output_tokens=6500)
    raw = response.model_dump_json(indent=2)
    (args.output / 'response.json').write_text(raw, encoding='utf-8')
    (args.output / 'response_text.txt').write_text(response.output_text, encoding='utf-8')
    if response.output_parsed is None:
        raise ValueError('LLM returned no parsed proposal; raw response retained')
    (args.output / 'proposal.json').write_text(
        response.output_parsed.model_dump_json(indent=2), encoding='utf-8')
    evidence = {
        'status': 'proposed_pending_validation', 'model': response.model,
        'elapsed_seconds': round(perf_counter() - started, 2),
        'usage': response.usage.model_dump() if response.usage else None,
        'score_source_sha256': hashlib.sha256(source).hexdigest(),
        'response_sha256': hashlib.sha256(raw.encode()).hexdigest(),
        'prompt_version': PROMPT_VERSION,
        'typology_pin': args.typology_pin,
        'typology_authority': request['authority'],
        'requested_typology': request['typology'],
        'legacy_source': '../architecture_automation_pipeline/program_generator/OpenAI_ProgramDetails.py',
    }
    (args.output / 'provider.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    print(json.dumps(evidence))
    normalize_saved(args.output)


if __name__ == '__main__':
    main()
