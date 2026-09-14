import { readdir, readFile, mkdir, writeFile, lstat } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve, basename } from 'node:path';
import { parseSubmissionText, validateCatalog } from '../src/validation';
const root = fileURLToPath(new URL('..', import.meta.url));
const PLOT_COUNTS = ['waveform_plots', 'curves', 'image_plots'];
export async function loadCatalog(directory: string) {
  const entries = (await readdir(directory)).filter((name) => name.endsWith('.json')).sort();
  const inputs = [];
  for (const name of entries) {
    const path = resolve(directory, name);
    const info = await lstat(path);
    if (!info.isFile() || info.isSymbolicLink())
      throw new Error(`${name}: submissions must be regular JSON files`);
    if (info.size > 5 * 1024 * 1024) throw new Error(`${name}: submission exceeds 5 MiB`);
    const text = await readFile(path, 'utf8');
    let submission;
    try {
      submission = parseSubmissionText(text);
    } catch (error) {
      // The validator lists every problem; lead with the first and count the rest.
      const lines = (error as Error).message.split('\n');
      const summary = lines.length > 1 ? `${lines[0]} (+${lines.length - 1} more)` : lines[0];
      // Submissions written before plot counts entered the format lack these keys.
      const hint = PLOT_COUNTS.some((key) => lines[0].includes(`'${key}'`))
        ? ' This file predates the plot-count fields; export it again from the original summary.json with the current website or CLI exporter.'
        : '';
      throw new Error(`${name}: ${summary}.${hint}`);
    }
    if (basename(name, '.json') !== submission.id)
      throw new Error(
        `${name}: the file name must be the campaign ID, so rename it to ${submission.id}.json. Browsers append a number such as "-2" or " (1)" when a download with that name already exists.`,
      );
    inputs.push(submission);
  }
  return { schema_version: 1 as const, campaigns: validateCatalog(inputs) };
}
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  try {
    const catalog = await loadCatalog(resolve(root, 'results'));
    if (!process.argv.includes('--check')) {
      await mkdir(resolve(root, 'public'), { recursive: true });
      await writeFile(resolve(root, 'public/catalog.json'), JSON.stringify(catalog) + '\n');
    }
    console.log(
      `${catalog.campaigns.length} valid campaign(s), ${catalog.campaigns.reduce((n, c) => n + c.runs.length, 0)} run(s).`,
    );
  } catch (error) {
    // A rejected submission is a data problem, not a crash: name it without a stack trace.
    console.error(`Catalogue rejected: ${(error as Error).message}`);
    process.exit(1);
  }
}
