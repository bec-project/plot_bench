import { readFile, writeFile } from 'node:fs/promises';
import { parseArgs } from 'node:util';
import { exportSummary, suggestSubmission } from '../src/export';
import { parseSubmissionText } from '../src/validation';
const { values } = parseArgs({
  options: {
    input: { type: 'string' },
    output: { type: 'string' },
    id: { type: 'string' },
    'host-id': { type: 'string' },
    'host-label': { type: 'string' },
    notes: { type: 'string' },
    help: { type: 'boolean' },
  },
});
if (values.help || !values.input) {
  console.log(
    'npm --prefix website run export -- --input ../results/CAMPAIGN/summary.json [--output results/CAMPAIGN-ID.json] [--id CAMPAIGN-ID] [--host-id PUBLIC-HOST-ID] [--host-label "Public hardware label"] [--notes "Operating conditions"]\n' +
      'Omitted fields are proposed from the summary (CPU model, OS, acquisition date, suite name, timings and display context); review the written file before submitting.',
  );
  if (!values.help) process.exitCode = 1;
} else {
  const text = await readFile(values.input, 'utf8');
  if (Buffer.byteLength(text) > 25 * 1024 * 1024)
    throw new Error('Input summary exceeds 25 MiB; split large campaigns before submitting');
  const raw = JSON.parse(text);
  const proposed = suggestSubmission(raw);
  const options = {
    id: values.id ?? proposed.id,
    hostId: values['host-id'] ?? proposed.hostId,
    hostLabel: values['host-label'] ?? proposed.hostLabel,
    notes: values.notes ?? proposed.notes,
  };
  const submission = await exportSummary(raw, options);
  const output = JSON.stringify(submission, null, 2) + '\n';
  parseSubmissionText(output);
  const path = values.output ?? `results/${options.id}.json`;
  await writeFile(path, output, { flag: 'wx' });
  console.log(
    `Exported ${submission.runs.length} runs (${submission.classification}) as ${options.id} for host ${options.hostId} (${options.hostLabel}). Review ${path} before submitting a PR. Original data remains unchanged.`,
  );
}
