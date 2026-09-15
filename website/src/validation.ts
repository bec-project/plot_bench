import Ajv from 'ajv';
import addFormats from 'ajv-formats';
import schema from '../submission.schema.json';
import { classify, type Submission } from './model';
import { baselineProblems, BASELINE_SUITE_PATH } from './baseline';

const ajv = new Ajv({ allErrors: true, strict: true });
addFormats(ajv);
const validate = ajv.compile<Submission>(schema);
export const MAX_SUBMISSION_BYTES = 5 * 1024 * 1024;
export function parseSubmission(data: unknown): Submission {
  if (!validate(data)) throw new Error(ajv.errorsText(validate.errors, { separator: '\n' }));
  const ids = new Set<string>();
  for (const r of data.runs) {
    if (ids.has(r.id)) throw new Error(`Duplicate run ID: ${r.id}`);
    ids.add(r.id);
    if (r.config.append_count > r.config.points)
      throw new Error(`${r.id}: append count exceeds window`);
    if (r.status === 'ok' && (r.samples < 1 || r.metrics.submitted_hz === null))
      throw new Error(`${r.id}: valid runs require observations`);
  }
  if (data.runs.length > data.planned_runs) throw new Error('Recorded runs exceed planned runs');
  if (data.classification !== classify(data.runs))
    throw new Error('Classification disagrees with run durations, repetitions or display context');
  // The results site publishes one suite only. Identity is structural: no marker in the
  // file can claim it, the runs themselves must be a complete baseline campaign.
  if (data.classification !== 'benchmark')
    throw new Error(
      `Not a baseline campaign: classification is ${data.classification}; the results site publishes only complete benchmark-classified runs of ${BASELINE_SUITE_PATH} on a visible desktop`,
    );
  for (const r of data.runs)
    if (r.context.commit === null || r.context.dirty !== false)
      throw new Error(
        `Not a baseline campaign: ${r.id}: official campaigns need a recorded commit from a clean checkout`,
      );
  const problems = baselineProblems({
    planned_runs: data.planned_runs,
    completion_status: data.completion_status,
    runs: data.runs.map((r) => ({
      ...r,
      commit: r.context.commit,
      source_hash: r.context.source_hash,
    })),
  });
  if (problems.length)
    throw new Error(
      `Not a baseline campaign: ${problems[0]}${problems.length > 1 ? ` (+${problems.length - 1} more)` : ''}`,
    );
  for (const link of Object.values(data.links))
    if (link) {
      const url = new URL(link);
      if (
        url.protocol !== 'https:' ||
        url.username ||
        url.password ||
        url.hostname === 'localhost' ||
        /^127\.|^192\.168\.|^10\.|^\[/.test(url.hostname)
      )
        throw new Error('Report links must be public HTTPS URLs without credentials');
    }
  return data;
}
export function parseSubmissionText(text: string): Submission {
  if (new TextEncoder().encode(text).length > MAX_SUBMISSION_BYTES)
    throw new Error('Submission exceeds 5 MiB');
  return parseSubmission(JSON.parse(text));
}
export function validateCatalog(inputs: unknown[]): Submission[] {
  const campaigns = inputs.map(parseSubmission);
  const ids = new Set<string>(),
    origins = new Set<string>();
  for (const c of campaigns) {
    if (ids.has(c.id)) throw new Error(`Duplicate campaign ID: ${c.id}`);
    if (origins.has(c.input_sha256)) throw new Error(`Campaign already submitted: ${c.id}`);
    ids.add(c.id);
    origins.add(c.input_sha256);
  }
  return campaigns.sort(
    (a, b) => Date.parse(b.recorded_at) - Date.parse(a.recorded_at) || a.id.localeCompare(b.id),
  );
}
