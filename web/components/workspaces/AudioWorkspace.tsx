'use client';

/**
 * The measurement layer: twelve features and six segments, with their methods.
 *
 * The page used to show four of the twelve. That is not a display choice -- a reader
 * cannot judge a translation whose evidence is hidden, and eight of the ten score
 * dimensions are computed from features that were never on screen. Every feature here
 * carries its extractor method and confidence next to its number, because the
 * confidence is what clamps how far the datum it drives may travel.
 */

import { useEffect, useRef } from 'react';
import { animate, stagger, svg } from 'animejs';
import type { GenerationResponse } from '../../lib/types';
import { audioFeatureEntries, compact, number, percent } from '../../lib/format';
import { EASE_OUT, reducedMotion } from '../../lib/motion';
import { Empty, KeyValue, Meter, Panel, Stat, StatGrid } from '../ui';

function SegmentTimeline({ run }: { run: GenerationResponse }) {
  const segments = run.audio_features.segments ?? [];
  const svgRef = useRef<SVGSVGElement>(null);

  // The lines draw themselves left to right, the way the measurement actually ran —
  // once, when the panel first opens. Marks pop in behind their line.
  useEffect(() => {
    const host = svgRef.current;
    if (!host || reducedMotion()) return;
    const lines = host.querySelectorAll('.seg-line');
    const dots = host.querySelectorAll('.seg-dot');
    if (lines.length === 0) return;
    const drawables = svg.createDrawable(lines as NodeListOf<SVGPolylineElement>);
    const drawing = animate(drawables, {
      draw: ['0 0', '0 1'],
      duration: 850,
      ease: 'linear',
      delay: stagger(120),
    });
    const popping = animate(dots, {
      opacity: [0, 1],
      scale: [0.85, 1],
      duration: 180,
      ease: EASE_OUT,
      delay: stagger(24, { start: 500 }),
    });
    return () => { drawing.cancel(); popping.cancel(); };
  }, [run.run_id]);

  if (segments.length === 0) return null;
  const duration = run.audio_features.provenance.duration_seconds || 1;
  const maxRms = Math.max(...segments.map((segment) => segment.rms_energy), 0.0001);
  const maxOnset = Math.max(...segments.map((segment) => segment.onset_density_hz), 0.0001);
  const maxCentroid = Math.max(...segments.map((segment) => segment.spectral_centroid_hz), 1);

  const width = 960;
  const height = 168;
  const padLeft = 42;
  const padBottom = 24;
  const plotWidth = width - padLeft - 12;
  const plotHeight = height - padBottom - 14;
  const xOf = (t: number) => padLeft + (t / duration) * plotWidth;

  const series: Array<{ key: 'rms_energy' | 'onset_density_hz' | 'spectral_centroid_hz'; label: string; max: number; color: string }> = [
    { key: 'rms_energy', label: 'RMS energy', max: maxRms, color: 'var(--accent)' },
    { key: 'onset_density_hz', label: 'Onset density', max: maxOnset, color: 'var(--circulation)' },
    { key: 'spectral_centroid_hz', label: 'Centroid', max: maxCentroid, color: 'var(--service)' },
  ];

  return (
    <div>
      <svg ref={svgRef} className="diagram" viewBox={'0 0 ' + width + ' ' + height} role="img"
        aria-label="Six analysis segments across the track">
        {segments.map((segment) => (
          <g key={segment.id}>
            <rect
              x={xOf(segment.start_seconds)} y={12}
              width={Math.max(1, xOf(segment.end_seconds) - xOf(segment.start_seconds) - 2)}
              height={plotHeight} fill="var(--surface)" stroke="var(--line)"
            />
            <text
              x={xOf(segment.start_seconds) + 4} y={height - 8}
              fontSize="9" fill="var(--muted)"
            >
              {segment.start_seconds.toFixed(0)}s
            </text>
          </g>
        ))}
        {series.map((line, lineIndex) => {
          const points = segments.map((segment) => {
            const mid = (segment.start_seconds + segment.end_seconds) / 2;
            const value = segment[line.key] / line.max;
            return [xOf(mid), 12 + plotHeight - value * plotHeight * 0.92].join(',');
          }).join(' ');
          return (
            <g key={line.key}>
              <polyline className="seg-line" points={points} fill="none" stroke={line.color} strokeWidth="1.6" />
              {segments.map((segment) => {
                const mid = (segment.start_seconds + segment.end_seconds) / 2;
                const value = segment[line.key] / line.max;
                return (
                  <circle
                    key={segment.id} className="seg-dot" r="2.6" fill={line.color}
                    cx={xOf(mid)} cy={12 + plotHeight - value * plotHeight * 0.92}
                    style={{ transformBox: 'fill-box', transformOrigin: 'center' }}
                  />
                );
              })}
              <text x={6} y={26 + lineIndex * 13} fontSize="9" fill={line.color}>{line.label}</text>
            </g>
          );
        })}
      </svg>
      <div className="table-wrap" style={{ marginTop: 10 }}>
        <table className="table">
          <thead>
            <tr>
              <th>Segment</th><th className="right">Start</th><th className="right">End</th>
              <th className="right">RMS</th><th className="right">Onsets / s</th><th className="right">Centroid Hz</th>
            </tr>
          </thead>
          <tbody>
            {segments.map((segment) => (
              <tr key={segment.id}>
                <td className="id">{segment.id}</td>
                <td className="right">{number(segment.start_seconds, 1)}</td>
                <td className="right">{number(segment.end_seconds, 1)}</td>
                <td className="right">{number(segment.rms_energy, 3)}</td>
                <td className="right">{number(segment.onset_density_hz, 2)}</td>
                <td className="right">{number(segment.spectral_centroid_hz, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function AudioWorkspace({ run }: { run: GenerationResponse | null }) {
  if (!run) return <Empty title="No audio analysed">Upload an MP3 to measure it.</Empty>;

  const provenance = run.audio_features.provenance;
  const features = audioFeatureEntries(run.audio_features);
  const saturated = features.filter(({ metric }) =>
    metric.normalized <= 0.02 || metric.normalized >= 0.98).length;

  return (
    <div className="stack">
      <Panel title="Source" sub={provenance.filename}>
        <StatGrid>
          <Stat label="Duration" value={number(provenance.duration_seconds, 1)} unit="S" />
          <Stat label="Sample rate" value={compact(provenance.sample_rate_hz)} unit="HZ" />
          <Stat label="Channels" value={provenance.channels} />
          <Stat label="Features" value={features.length} foot="all measured, none inferred here" />
          <Stat
            label="At a range end"
            value={saturated}
            tone={saturated > 0 ? 'warn' : 'ok'}
            foot="a reading within 0.02 of an endpoint has stopped measuring"
          />
        </StatGrid>
        <div style={{ marginTop: 12 }}>
          <KeyValue rows={[
            ['Extractor', provenance.extractor + ' ' + provenance.extractor_version],
            ['SHA-256', <span key="h" className="mono" style={{ fontSize: 10.5 }}>{provenance.sha256}</span>],
            ['Score id', <span key="s" className="mono">{run.architectural_score.score_id}</span>],
          ]} />
        </div>
      </Panel>

      <Panel
        title="Measured features"
        sub="value · normalised position in the calibrated range · confidence"
        flush
        note="Ranges come from backend/scripts/calibrate_audio_ranges.py against the cross-genre corpus. They are calibrated, not chosen, and a reading at an endpoint is reported rather than smoothed."
      >
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Feature</th>
                <th className="right">Value</th>
                <th>Unit</th>
                <th style={{ width: 190 }}>Normalised</th>
                <th className="right">Confidence</th>
                <th>Extraction method</th>
              </tr>
            </thead>
            <tbody>
              {features.map(({ key, label, metric }) => (
                <tr key={key}>
                  <td><b>{label}</b><div className="id">{key}</div></td>
                  <td className="right">{number(metric.value, metric.value >= 100 ? 1 : 3)}</td>
                  <td className="nowrap" style={{ color: 'var(--muted)' }}>{metric.unit}</td>
                  <td>
                    <div className="meter-row">
                      <Meter
                        value={metric.normalized}
                        tone={metric.normalized <= 0.02 || metric.normalized >= 0.98 ? 'warn' : 'info'}
                      />
                      <span className="num" style={{ fontSize: 11 }}>{metric.normalized.toFixed(3)}</span>
                    </div>
                  </td>
                  <td className="right">{percent(metric.confidence)}</td>
                  <td className="wrap">{metric.method}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel title="Temporal segments" sub={(run.audio_features.segments?.length ?? 0) + ' windows'}>
        <SegmentTimeline run={run} />
      </Panel>
    </div>
  );
}
