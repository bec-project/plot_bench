import { readFile, writeFile } from 'node:fs/promises';
import { parseArgs } from 'node:util';
import { exportSummary } from '../src/export';
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
if (values.help) {
  console.log(
    'npm --prefix website run export -- --input ../results/CAMPAIGN/summary.json --output results/CAMPAIGN-ID.json --id CAMPAIGN-ID --host-id PUBLIC-HOST-ID --host-label "Public hardware label" [--notes "Operating conditions"]',
  );
} else {
  for (const key of ['input', 'output', 'id', 'host-id', 'host-label'] as const)
    if (!values[key]) throw new Error(`Missing --${key}; use --help`);
  const text = await readFile(values.input!, 'utf8');
  if (Buffer.byteLength(text) > 25 * 1024 * 1024)
    throw new Error('Input summary exceeds 25 MiB; split large campaigns before submitting');
  const submission = await exportSummary(JSON.parse(text), {
    id: values.id!,
    hostId: values['host-id']!,
    hostLabel: values['host-label']!,
    notes: values.notes,
  });
  const output = JSON.stringify(submission, null, 2) + '\n';
  parseSubmissionText(output);
  await writeFile(values.output!, output, { flag: 'wx' });
  console.log(
    `Exported ${submission.runs.length} runs (${submission.classification}). Review ${values.output} before submitting a PR. Original data remains unchanged.`,
  );
}
