import type {
  EnvironmentStatus,
  InitialData,
  Kind,
  Plan,
  Preset,
  SaveResult,
  Suite,
} from './types';

async function jsonOrError(response: Response): Promise<any> {
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(result.error || `Request failed (${response.status}).`);
  }
  return result;
}

export async function fetchInitial(): Promise<InitialData> {
  const response = await fetch('/api/initial');
  if (!response.ok) throw new Error('The matrix editor could not load its initial suite.');
  return response.json();
}

export async function fetchEnvironment(): Promise<EnvironmentStatus | null> {
  const response = await fetch('/api/environment');
  if (!response.ok) return null;
  return response.json();
}

export async function fetchPresets(): Promise<Preset[]> {
  const response = await fetch('/api/presets');
  if (!response.ok) return [];
  const result = await response.json();
  return result.presets ?? [];
}

export async function preview(suite: Suite, kind: Kind): Promise<Plan> {
  const response = await fetch('/api/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ suite, kind }),
  });
  return jsonOrError(response);
}

export async function previewRaw(suiteJson: string, kind: Kind): Promise<Plan> {
  const response = await fetch('/api/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ suite_json: suiteJson, kind }),
  });
  return jsonOrError(response);
}

export async function saveSuite(
  suite: Suite,
  filename: string,
  kind: Kind
): Promise<SaveResult> {
  const response = await fetch('/api/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ suite, filename, kind }),
  });
  return jsonOrError(response);
}
