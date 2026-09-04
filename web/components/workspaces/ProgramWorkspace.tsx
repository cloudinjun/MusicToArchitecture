'use client';

/**
 * The brief, as areas the allocator either found room for or reported.
 *
 * The plan diagram is drawn from the lattice the compiler set out -- the plate
 * polygon, its voids, and the structural grid lines -- with the allocated zones laid
 * on top. Nothing here is a picture of the model: every rectangle is the zone record
 * the allocator wrote, so a zone that reads as too small on screen is too small in the
 * building.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { animate, stagger } from 'animejs';
import type { AllocatedZone, GenerationResponse, LevelDatum } from '../../lib/types';
import { compact, number, percent, titleCase } from '../../lib/format';
import { EASE_OUT, reducedMotion } from '../../lib/motion';
import { Empty, Meter, Panel, Pill, Stat, StatGrid } from '../ui';

const CATEGORY_FILL: Record<string, string> = {
  public: 'rgba(0, 61, 242, .16)',
  private: 'rgba(209, 41, 45, .16)',
  circulation: 'rgba(11, 158, 82, .16)',
  service: 'rgba(235, 138, 20, .18)',
  context: 'rgba(154, 160, 166, .16)',
};
const CATEGORY_STROKE: Record<string, string> = {
  public: 'var(--public)',
  private: 'var(--private)',
  circulation: 'var(--circulation)',
  service: 'var(--service)',
  context: 'var(--context)',
};

/** The order rooms arrive in: the main public spaces first, then how you move,
 *  then the private and back-of-house rooms that serve them. */
const ENTRY_RANK: Record<string, number> = { public: 0, circulation: 1, private: 2, service: 3 };

function LevelPlan({
  level, zones, xLines, yLines, plan,
}: {
  level: LevelDatum;
  zones: AllocatedZone[];
  xLines: number[];
  yLines: number[];
  plan: { x_min: number; x_max: number; y_min: number; y_max: number };
}) {
  const hostRef = useRef<SVGSVGElement>(null);

  // Rooms take their places once per level change — public rooms first, then
  // circulation, then the rooms that serve them. Repeated re-renders stay still.
  useEffect(() => {
    const host = hostRef.current;
    if (!host || reducedMotion()) return;
    const rooms = host.querySelectorAll('.zone-in');
    if (rooms.length === 0) return;
    const entering = animate(rooms, {
      opacity: [0, 1],
      scale: [0.96, 1],
      duration: 280,
      ease: EASE_OUT,
      delay: stagger(45),
    });
    return () => { entering.cancel(); };
  }, [level.id]);

  const orderedZones = [...zones].sort((a, b) =>
    (ENTRY_RANK[a.category] ?? 9) - (ENTRY_RANK[b.category] ?? 9)
    || b.area_delivered_m2 - a.area_delivered_m2);

  const pad = 3;
  const width = plan.x_max - plan.x_min + pad * 2;
  const height = plan.y_max - plan.y_min + pad * 2;
  const toX = (x: number) => x - plan.x_min + pad;
  // World Y is up; the sheet's is down. Flipping here keeps north at the top.
  const toY = (y: number) => plan.y_max - y + pad;
  const ring = (points: Array<{ x: number; y: number }>) =>
    points.map((point) => toX(point.x) + ',' + toY(point.y)).join(' ');

  return (
    <svg
      ref={hostRef}
      className="diagram"
      viewBox={'0 0 ' + width.toFixed(2) + ' ' + height.toFixed(2)}
      role="img"
      aria-label={'Plan of level ' + level.id}
      style={{ maxHeight: 460 }}
    >
      {xLines.map((x) => (
        <line key={'x' + x} x1={toX(x)} y1={0} x2={toX(x)} y2={height}
          stroke="var(--line)" strokeWidth="0.06" strokeDasharray="0.9 0.6" />
      ))}
      {yLines.map((y) => (
        <line key={'y' + y} x1={0} y1={toY(y)} x2={width} y2={toY(y)}
          stroke="var(--line)" strokeWidth="0.06" strokeDasharray="0.9 0.6" />
      ))}
      {level.plate.length > 0 && (
        <polygon points={ring(level.plate)} fill="var(--surface)" stroke="var(--text)" strokeWidth="0.14" />
      )}
      {level.voids.map((hole, index) => (
        <polygon key={index} points={ring(hole)} fill="var(--surface-3)"
          stroke="var(--line-strong)" strokeWidth="0.09" />
      ))}
      {orderedZones.map((zone) => (
        <g
          key={zone.space_id}
          className="zone-in"
          style={{ transformBox: 'fill-box', transformOrigin: 'center' }}
        >
          <rect
            x={toX(zone.x0)} y={toY(zone.y1)}
            width={Math.max(0.1, zone.x1 - zone.x0)} height={Math.max(0.1, zone.y1 - zone.y0)}
            fill={CATEGORY_FILL[zone.category] ?? CATEGORY_FILL.context}
            stroke={CATEGORY_STROKE[zone.category] ?? 'var(--muted)'}
            strokeWidth="0.12"
          />
          <text
            x={toX(zone.x0) + 0.7} y={toY(zone.y1) + 1.8}
            fontSize="1.1" fill="var(--text)"
          >
            {zone.label}
          </text>
          <text
            x={toX(zone.x0) + 0.7} y={toY(zone.y1) + 3.2}
            fontSize="0.9" fill="var(--muted)"
          >
            {zone.area_delivered_m2.toFixed(0)} m²
          </text>
        </g>
      ))}
    </svg>
  );
}

export function ProgramWorkspace({ run }: { run: GenerationResponse | null }) {
  const analysis = run?.analysis ?? null;
  const levels = useMemo(() => analysis?.lattice.levels ?? [], [analysis]);
  const [levelId, setLevelId] = useState<string | null>(null);

  const activeLevel = useMemo(() => {
    if (levels.length === 0) return null;
    return levels.find((level) => level.id === levelId)
      ?? levels.find((level) => level.kind === 'occupied')
      ?? levels[0];
  }, [levels, levelId]);

  if (!run || !analysis) {
    return <Empty title="No program allocation">A run states its brief as areas and reports what it could not place.</Empty>;
  }

  const allocation = analysis.program_allocation;
  const zonesHere = allocation.zones.filter((zone) => zone.level_id === activeLevel?.id);
  const fulfilment = allocation.delivered_area_m2 / (allocation.required_area_m2 || 1);
  const usableTotal = Object.values(allocation.usable_area_by_level).reduce((sum, area) => sum + area, 0);

  return (
    <div className="stack">
      <Panel title="Brief" sub={analysis.typology + ' · ' + (analysis.selection?.program_id ?? '')}>
        <StatGrid>
          <Stat label="Briefed" value={compact(allocation.required_area_m2)} unit="M²" />
          <Stat
            label="Delivered"
            value={compact(allocation.delivered_area_m2)}
            unit="M²"
            tone={allocation.unplaced.length ? 'warn' : 'ok'}
            foot={percent(fulfilment) + ' of the brief'}
          />
          <Stat label="Usable plate" value={compact(usableTotal)} unit="M²"
            foot={Object.keys(allocation.usable_area_by_level).length + ' occupied levels'} />
          <Stat label="Placed" value={allocation.zones.length} foot="zones on the lattice" />
          <Stat
            label="Unplaced"
            value={allocation.unplaced.length}
            tone={allocation.unplaced.length ? 'bad' : 'ok'}
            foot="reported rather than absorbed by shrinking rooms"
          />
        </StatGrid>
      </Panel>

      <Panel
        title="Plan"
        sub={activeLevel ? activeLevel.id + ' · ' + titleCase(activeLevel.kind)
          + ' · FFL ' + number(activeLevel.z, 2) + ' m' : ''}
        actions={
          <div className="segmented">
            {levels.map((level) => (
              <button
                key={level.id} type="button"
                className={activeLevel?.id === level.id ? 'is-active' : ''}
                onClick={() => setLevelId(level.id)}
              >{level.id}</button>
            ))}
          </div>
        }
        note={'Plate polygon, voids and structural grid from the lattice; zones from the allocator. Plan extent '
          + number(analysis.lattice.plan_x_m, 1) + ' × ' + number(analysis.lattice.plan_y_m, 1) + ' m.'}
      >
        {activeLevel ? (
          <>
            <LevelPlan
              level={activeLevel}
              zones={zonesHere}
              xLines={analysis.lattice.x_lines}
              yLines={analysis.lattice.y_lines}
              plan={analysis.lattice.plan}
            />
            <div className="chip-row" style={{ marginTop: 10 }}>
              {['public', 'private', 'circulation', 'service'].map((category) => (
                <span key={category} className="chip">
                  <span className={'swatch swatch-' + category} aria-hidden="true" />
                  {titleCase(category)}
                </span>
              ))}
              <span className="chip">
                <span className="chip-key">usable here</span>
                <b className="num">{compact(allocation.usable_area_by_level[activeLevel.id] ?? 0)} m²</b>
              </span>
            </div>
          </>
        ) : <Empty title="No level to draw" />}
      </Panel>

      <Panel title="Allocated zones" sub={allocation.zones.length + ' spaces'} flush>
        <div className="table-wrap" style={{ maxHeight: 460 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Space</th><th>Level</th><th>Category</th><th>Occupancy</th>
                <th className="right">Briefed m²</th><th className="right">Delivered m²</th>
                <th className="right">Deviation</th><th>Daylight</th><th>Level preference</th>
              </tr>
            </thead>
            <tbody>
              {allocation.zones.map((zone) => {
                const deviation = zone.area_required_m2
                  ? (zone.area_delivered_m2 - zone.area_required_m2) / zone.area_required_m2 : 0;
                return (
                  <tr key={zone.space_id} className={zone.level_id === activeLevel?.id ? 'is-selected' : ''}>
                    <td>
                      <b>{zone.label}</b>
                      <div className="id">{zone.space_id} · {zone.space_type}</div>
                    </td>
                    <td className="nowrap">{zone.level_id}</td>
                    <td>
                      <span className="chip">
                        <span className={'swatch swatch-' + zone.category} aria-hidden="true" />
                        {zone.category}
                      </span>
                    </td>
                    <td className="id">{zone.occupancy_id}</td>
                    <td className="right">{compact(zone.area_required_m2)}</td>
                    <td className="right">{compact(zone.area_delivered_m2)}</td>
                    <td className="right" style={{ color: deviation < -0.02 ? 'var(--bad)' : undefined }}>
                      {(deviation >= 0 ? '+' : '') + percent(deviation, 1)}
                    </td>
                    <td>{zone.daylight_satisfied
                      ? <Pill tone="ok">yes</Pill> : <Pill tone="warn">no</Pill>}</td>
                    <td>{zone.level_preference_satisfied
                      ? <Pill tone="ok">yes</Pill> : <Pill tone="warn">no</Pill>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="cols-2">
        <Panel
          title="Unplaced"
          sub={allocation.unplaced.length + ' spaces'}
          note="The allocator reports what it could not place. Shrinking a room to make the brief fit would be the same defect with a better-looking number."
        >
          {allocation.unplaced.length === 0 ? (
            <Empty title="Every briefed space was placed" />
          ) : (
            <ul className="list-reasons">
              {allocation.unplaced.map((space) => (
                <li key={space.space_id}>
                  <b>{space.label}</b> — {compact(space.area_required_m2)} m². {space.reason}
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Usable plate by level" sub="after voids and cores">
          <div className="stack" style={{ gap: 10 }}>
            {Object.entries(allocation.usable_area_by_level).map(([level, area]) => {
              const maxArea = Math.max(...Object.values(allocation.usable_area_by_level), 1);
              return (
                <div key={level}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 4 }}>
                    <span className="mono">{level}</span>
                    <span className="num">{compact(area)} m²</span>
                  </div>
                  <Meter value={area / maxArea} />
                </div>
              );
            })}
          </div>
        </Panel>
      </div>
    </div>
  );
}
