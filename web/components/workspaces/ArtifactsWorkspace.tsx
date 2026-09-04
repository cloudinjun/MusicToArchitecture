'use client';

/**
 * What the run produced, who owns it, and what its hash is.
 *
 * Authority is the column that matters here. Blender's outputs are presentation only,
 * Rhino owns accepted geometry, and the accepted state stays blocked until Rhino says
 * otherwise -- so this page prints the authority next to every artifact rather than
 * letting a downloadable GLB imply it is the design.
 */

import type { GenerationResponse, SystemProfile } from '../../lib/types';
import { assetUrl, downloadJson } from '../../lib/api';
import { compact, shortHash, titleCase } from '../../lib/format';
import { Empty, KeyValue, Panel, Pill, Stat, StatGrid, StatusPill } from '../ui';

/**
 * A declared system candidate, limitations included.
 *
 * The limitations are the half a reader skips, so they are rendered as their own list
 * rather than folded into a value cell where a comma-joined array would hide them.
 */
function ProfileBlock({ label, profile }: { label: string; profile?: SystemProfile }) {
  if (!profile) return <div><p className="section-label">{label}</p></div>;
  const scalars = Object.entries(profile)
    .filter(([key, value]) => key !== 'limitations' && typeof value === 'string');
  return (
    <div>
      <p className="section-label">{label}</p>
      <div style={{ marginTop: 8 }}>
        <KeyValue rows={scalars.map(([key, value]) => [titleCase(key), String(value)])} />
      </div>
      {profile.limitations?.length > 0 && (
        <>
          <p className="section-label" style={{ marginTop: 12 }}>Unresolved</p>
          <ul className="list-reasons" style={{ marginTop: 8 }}>
            {profile.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
          </ul>
        </>
      )}
    </div>
  );
}

export function ArtifactsWorkspace({ run }: { run: GenerationResponse | null }) {
  if (!run) return <Empty title="No artifacts">A run writes its artifacts as it goes.</Empty>;

  const manifest = run.pipeline_manifest;
  const downloads: Array<[string, unknown]> = [
    ['architectural_score.json', run.architectural_score],
    ['building_model_v2.json', run.building_model],
    ['mapping_report.json', run.mapping_report],
    ['facade_host_handoff.json', run.facade_handoff],
    ['pipeline_run_manifest.json', manifest],
    ['audio_features.json', run.audio_features],
  ];
  if (run.translation_report) downloads.push(['translation_report.json', run.translation_report]);
  if (run.analysis) downloads.push(['analysis_bundle.json', run.analysis]);
  if (run.analysis?.bim_handoff) downloads.push(['bim_handoff_report.json', run.analysis.bim_handoff]);
  if (run.drawing_index) downloads.push(['drawing_index.json', run.drawing_index]);

  return (
    <div className="stack">
      <Panel title="Run manifest" sub={manifest.run_id}>
        <StatGrid>
          <Stat label="Overall" value={<StatusPill status={manifest.overall_status} />} />
          <Stat label="Accepted state" value={<StatusPill status={manifest.accepted_state.status} />}
            foot={'owned by ' + manifest.accepted_state.authority_owner} />
          <Stat label="Artifacts" value={manifest.artifacts.length}
            foot={manifest.artifacts.filter((artifact) => artifact.status === 'available').length + ' available'} />
          <Stat label="Stages" value={manifest.stages.length}
            foot={manifest.stages.filter((stage) => stage.status === 'pass').length + ' passed'} />
        </StatGrid>
        {manifest.accepted_state.blocked_by.length > 0 && (
          <ul className="list-reasons" style={{ marginTop: 12 }}>
            {manifest.accepted_state.blocked_by.map((blocker) => <li key={blocker}>{blocker}</li>)}
          </ul>
        )}
      </Panel>

      <Panel title="Stages" sub="portable core · interactive acceptance · web preview" flush>
        <div className="table-wrap" style={{ maxHeight: 420 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Stage</th><th>Route</th><th>Status</th><th>Authority</th>
                <th>Producer</th><th>Message</th>
              </tr>
            </thead>
            <tbody>
              {manifest.stages.map((stage) => (
                <tr key={stage.id}>
                  <td className="id">{stage.id}</td>
                  <td className="nowrap">{stage.route.replace(/_/g, ' ')}</td>
                  <td><StatusPill status={stage.status} /></td>
                  <td style={{ color: 'var(--muted)' }}>{stage.authority.replace(/_/g, ' ')}</td>
                  <td className="nowrap">{stage.producer}</td>
                  <td className="wrap">
                    {stage.message}
                    {stage.blocked_by.length > 0 && (
                      <div className="id" style={{ marginTop: 4 }}>blocked by {stage.blocked_by.join(', ')}</div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel title="Artifacts" sub={manifest.artifacts.length + ' records'} flush>
        <div className="table-wrap" style={{ maxHeight: 420 }}>
          <table className="table">
            <thead>
              <tr><th>Artifact</th><th>Kind</th><th>Status</th><th>Authority</th><th>SHA-256</th><th>URI</th></tr>
            </thead>
            <tbody>
              {manifest.artifacts.map((artifact) => (
                <tr key={artifact.id}>
                  <td className="id">{artifact.id}</td>
                  <td>{titleCase(artifact.kind)}</td>
                  <td><StatusPill status={artifact.status} /></td>
                  <td style={{ color: 'var(--muted)' }}>{artifact.authority.replace(/_/g, ' ')}</td>
                  <td className="id">{artifact.sha256 ? shortHash(artifact.sha256, 16) : '—'}</td>
                  <td className="id">{artifact.uri ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="cols-2">
        <Panel title="Massing GLB" sub="schema 2.0 · presentation only">
          <KeyValue rows={[
            ['Producer', run.model_asset.producer],
            ['Asset', <a key="a" className="mono" href={assetUrl(run.model_asset.asset_url)} download>{run.model_asset.asset_url}</a>],
            ['Asset SHA', <span key="b" className="mono">{shortHash(run.model_asset.asset_sha256, 24)}</span>],
            ['Blend', <span key="c" className="mono">{run.model_asset.native_blend_path}</span>],
            ['Scene state', <span key="d" className="mono">{run.model_asset.scene_state_path}</span>],
            ['Layers', run.model_asset.semantic_layers.length],
          ]} />
        </Panel>

        <Panel title="Member-level GLB" sub="schema 3.0 · presentation only">
          {run.model_asset_v3 ? (
            <KeyValue rows={[
              ['Producer', run.model_asset_v3.producer],
              ['Asset', <a key="a" className="mono" href={assetUrl(run.model_asset_v3.asset_url)} download>{run.model_asset_v3.asset_url}</a>],
              ['Asset SHA', <span key="b" className="mono">{shortHash(run.model_asset_v3.asset_sha256, 24)}</span>],
              ['Elements', compact(run.model_asset_v3.element_count)],
              ['Merged objects', compact(run.model_asset_v3.merged_object_count)],
              ['Faces', compact(run.model_asset_v3.face_count)],
              ['Model JSON', <span key="c" className="mono">{run.model_asset_v3.model_json_path}</span>],
            ]} />
          ) : (
              <div>
                <Pill tone="bad">absent</Pill>
                <p className="prose" style={{ marginTop: 10 }}>
                  The member-level export did not complete on this run. The v2 acceptance
                  chain above is unaffected by design.
                </p>
              </div>
            )}
        </Panel>
      </div>

      <Panel
        title="Massing contract"
        sub={'schema 2.0 · ' + run.building_model.model_id}
        note="The contract the Grasshopper watcher, the facade handoff and the acceptance manifest read. It runs in parallel with schema 3.0 and neither derives from the other."
      >
        <div className="cols-3">
          <div>
            <p className="section-label">Site and grid</p>
            <div style={{ marginTop: 8 }}>
              <KeyValue rows={[
                ['Site', run.building_model.site
                  ? compact(run.building_model.site.width) + ' × ' + compact(run.building_model.site.length)
                    + ' m, max ' + compact(run.building_model.site.max_height) + ' m'
                  : '—'],
                ['Grid X', run.building_model.grid ? compact(run.building_model.grid.spacing_x) + ' m' : '—'],
                ['Grid Y', run.building_model.grid ? compact(run.building_model.grid.spacing_y) + ' m' : '—'],
                ['Column', run.building_model.grid ? compact(run.building_model.grid.column_size) + ' m' : '—'],
                ['Elements', compact(run.building_model.elements.length)],
              ]} />
            </div>
          </div>
          <div>
            <p className="section-label">Generation parameters</p>
            <div style={{ marginTop: 8 }}>
              <KeyValue rows={Object.entries(run.building_model.parameters ?? {}).map(
                ([key, value]) => [titleCase(key), <span key={key} className="num">{compact(Number(value))}</span>])} />
            </div>
          </div>
          <div>
            <p className="section-label">Interior sequence</p>
            <ol className="list-reasons" style={{ marginTop: 8 }}>
              {(run.building_model.interior_sequence ?? []).map((step) => (
                <li key={step} className="mono" style={{ fontSize: 10.5 }}>{step}</li>
              ))}
            </ol>
          </div>
        </div>

        <div className="cols-2" style={{ marginTop: 14 }}>
          <ProfileBlock label="Structural profile" profile={run.building_model.structural_profile} />
          <ProfileBlock label="Facade profile" profile={run.building_model.facade_profile} />
        </div>
      </Panel>

      {(run.building_model.program_relations ?? []).length > 0 && (
        <Panel
          title="Program relations"
          sub={(run.building_model.program_relations ?? []).length + ' required adjacencies'}
          flush
        >
          <div className="table-wrap" style={{ maxHeight: 300 }}>
            <table className="table">
              <thead>
                <tr><th>Relation</th><th>From</th><th>To</th><th>Status</th><th>Rule</th><th>Reason</th></tr>
              </thead>
              <tbody>
                {(run.building_model.program_relations ?? []).map((relation) => (
                  <tr key={relation.id}>
                    <td className="nowrap">{titleCase(relation.relation)}</td>
                    <td className="id">{relation.source_id}</td>
                    <td className="id">{relation.target_id}</td>
                    <td><StatusPill status={relation.status} /></td>
                    <td className="id">{relation.rule_id}</td>
                    <td className="wrap">{relation.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      <Panel title="Downloads" sub="every report this run produced">
        <div className="btn-row">
          {downloads.map(([filename, payload]) => (
            <button
              key={filename} type="button" className="btn"
              onClick={() => downloadJson(filename, payload)}
            >{filename}</button>
          ))}
          <button
            type="button" className="btn btn-primary"
            onClick={() => downloadJson('generation_response.json', run)}
          >Whole run</button>
          <a className="btn" href={assetUrl(run.model_asset.asset_url)} download>massing.glb</a>
          {run.model_asset_v3 && (
            <a className="btn" href={assetUrl(run.model_asset_v3.asset_url)} download>members.glb</a>
          )}
        </div>
      </Panel>

      {manifest.limitations.length > 0 && (
        <Panel title="Manifest limitations">
          <ul className="list-reasons">
            {manifest.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
          </ul>
        </Panel>
      )}
    </div>
  );
}
