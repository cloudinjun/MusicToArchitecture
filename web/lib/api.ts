import type { GenerationResponse, GlbManifest, RunSummary } from './types';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

/** Where the frozen demo run lives. Written by `backend.scripts.generate_web_demo`. */
const DEMO_RUN_URL = '/reports/demo_run.json';

/**
 * Resolve an artifact URL against whichever server owns it.
 *
 * A live run's sheets and stills are files on the API host, so their URLs start
 * `/api/`. The frozen demo's copies live in `web/public`, so theirs do not. One
 * prefix test keeps both working without either side knowing about the other.
 */
export function assetUrl(url: string): string {
  if (!url) return url;
  if (/^https?:\/\//i.test(url)) return url;
  return url.startsWith('/api/') ? API_URL + url : url;
}

export async function generateArchitecture(file: File): Promise<GenerationResponse> {
  const body = new FormData();
  body.append('file', file);
  const response = await fetch(API_URL + '/api/generate', { method: 'POST', body });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail ?? 'Generation failed (' + response.status + ')');
  }
  return response.json() as Promise<GenerationResponse>;
}

/** The run library. Returns an empty list when the API is not up, which is not an error. */
export async function listRuns(): Promise<RunSummary[]> {
  try {
    const response = await fetch(API_URL + '/api/runs');
    if (!response.ok) return [];
    return await response.json() as RunSummary[];
  } catch {
    return [];
  }
}

export async function loadRun(runId: string): Promise<GenerationResponse> {
  const response = await fetch(API_URL + '/api/runs/' + runId);
  if (!response.ok) throw new Error('That run could not be reopened (' + response.status + ')');
  return response.json() as Promise<GenerationResponse>;
}

/** The frozen run the workbench opens with, so every panel has real data on load. */
export async function loadDemoRun(): Promise<GenerationResponse | null> {
  try {
    const response = await fetch(DEMO_RUN_URL);
    if (!response.ok) return null;
    return await response.json() as GenerationResponse;
  } catch {
    return null;
  }
}

/** The GLB's own manifest: which merged objects exist, and what each one holds. */
export async function loadGlbManifest(url: string): Promise<GlbManifest | null> {
  try {
    const response = await fetch(assetUrl(url));
    if (!response.ok) return null;
    return await response.json() as GlbManifest;
  } catch {
    return null;
  }
}

/** Fetch a sheet as text so it can be inlined and inspected rather than framed. */
export async function loadSheetSvg(url: string): Promise<string | null> {
  try {
    const response = await fetch(assetUrl(url));
    if (!response.ok) return null;
    return await response.text();
  } catch {
    return null;
  }
}

export async function apiHealthy(): Promise<boolean> {
  try {
    const response = await fetch(API_URL + '/api/health');
    return response.ok;
  } catch {
    return false;
  }
}

export function downloadJson(filename: string, payload: unknown): void {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function downloadText(filename: string, text: string, type = 'text/plain'): void {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export { API_URL };
