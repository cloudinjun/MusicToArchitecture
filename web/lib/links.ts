/**
 * The links from the score to the building, read off the run rather than authored.
 *
 * The compiler reads the *whole* recording: ten measurements over the whole piece
 * become ten score dimensions, each dimension sets datums (floor to floor, the bay,
 * the mullion module…), and each datum is a rule that holds everywhere in its layer.
 * Nothing here is local — no note builds a column. The translation report says which
 * datums each dimension set and which element kinds those datums reach; the element
 * groups say which layer each kind is in; the mapping rules say which parameter
 * families a dimension targets (the lattice's own live under `lattice.`, `grid.` and
 * `sequence.`). A layer's links are the dimensions that reach it.
 */

import type { GenerationResponse } from './types';
import { titleCase } from './format';

export interface Datum { label: string; value: number; unit: string }

/** One score dimension's reach into a layer: its value, the whole-piece features it
 *  was read from, and the datums it set there. */
export interface Link {
  id: string;
  value: number;
  features: string[];
  datums: Datum[];
}

/** Where a mapping rule's target lives, by the parameter's family. */
const TARGET_LAYER: Array<[string, string]> = [
  ['lattice.', 'lattice'], ['grid.', 'lattice'], ['sequence.', 'lattice'],
  ['structure.', 'structure'], ['plate.', 'structure'],
  ['envelope.', 'envelope'], ['facade.', 'envelope'],
  ['circulation.', 'circulation'], ['program.', 'program'],
];

export function linksByLayer(run: GenerationResponse | null): Map<string, Link[]> {
  const out = new Map<string, Link[]>();
  if (!run) return out;
  const kindLayer = new Map<string, string>();
  (run.analysis?.element_groups ?? []).forEach((group) => kindLayer.set(group.kind, group.semantic_layer));
  const ruleLayers = new Map<string, Set<string>>();
  run.architectural_score.mapping_rules.forEach((rule) => {
    const hit = TARGET_LAYER.find(([prefix]) => rule.target_parameter.startsWith(prefix));
    if (!hit) return;
    const set = ruleLayers.get(rule.source_dimension) ?? new Set<string>();
    set.add(hit[1]);
    ruleLayers.set(rule.source_dimension, set);
  });
  const add = (layer: string, link: Link) => {
    const list = out.get(layer) ?? [];
    if (!list.some((item) => item.id === link.id)) list.push(link);
    out.set(layer, list);
  };
  const reported = run.translation_report?.dimensions ?? [];
  if (reported.length > 0) {
    reported.forEach((dimension) => {
      const features = dimension.source_features.map((feature) => feature.id);
      const byLayer = new Map<string, Datum[]>();
      dimension.datums.forEach((datum) => {
        const layers = new Set<string>();
        datum.element_kinds.forEach((kind) => { const layer = kindLayer.get(kind); if (layer) layers.add(layer); });
        (ruleLayers.get(dimension.id) ?? new Set<string>()).forEach((layer) => { if (layer === 'lattice') layers.add(layer); });
        layers.forEach((layer) => {
          const list = byLayer.get(layer) ?? [];
          if (!list.some((item) => item.label === datum.label)) {
            list.push({ label: datum.label, value: datum.value, unit: datum.unit });
          }
          byLayer.set(layer, list);
        });
      });
      byLayer.forEach((datums, layer) => add(layer, {
        id: dimension.id, value: dimension.value ?? Number.NaN, features, datums,
      }));
    });
    return out;
  }
  run.architectural_score.dimensions.forEach((dimension) => {
    (ruleLayers.get(dimension.id) ?? new Set<string>()).forEach((layer) => add(layer, {
      id: dimension.id, value: dimension.value, features: dimension.source_feature.split('+'), datums: [],
    }));
  });
  return out;
}

export function layerLabel(layer: string): string {
  return layer === 'lattice' ? 'Lattice' : titleCase(layer);
}

/** A datum's value the way a drawing states it: `4.2 m`, `2.9 rows`, `5` levels. */
export function datumValue(datum: Datum): string {
  const value = Number.isInteger(datum.value) ? String(datum.value) : datum.value.toFixed(1);
  if (!datum.unit || datum.unit === 'levels' || datum.label.toLowerCase().includes(datum.unit)) return value;
  return value + ' ' + datum.unit;
}
