import { readdir, readFile, mkdir, writeFile, lstat } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve, basename } from 'node:path';
import { parseSubmissionText, validateCatalog } from '../src/validation';
const root = fileURLToPath(new URL('..', import.meta.url));
export async function loadCatalog(directory: string) {
  const entries = (await readdir(directory)).filter((name) => name.endsWith('.json')).sort();
  const inputs = [];
  for (const name of entries) {
    const path = resolve(directory, name);
    const info = await lstat(path);
    if (!info.isFile() || info.isSymbolicLink())
      throw new Error(`${name}: submissions must be regular JSON files`);
    if (info.size > 5 * 1024 * 1024) throw new Error(`${name}: submission exceeds 5 MiB`);
    const submission = parseSubmissionText(await readFile(path, 'utf8'));
    if (basename(name, '.json') !== submission.id)
      throw new Error(`${name}: filename must match campaign ID`);
    inputs.push(submission);
  }
  return { schema_version: 1 as const, campaigns: validateCatalog(inputs) };
}
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const catalog = await loadCatalog(resolve(root, 'results'));
  if (!process.argv.includes('--check')) {
    await mkdir(resolve(root, 'public'), { recursive: true });
    await writeFile(resolve(root, 'public/catalog.json'), JSON.stringify(catalog) + '\n');
  }
  console.log(
    `${catalog.campaigns.length} valid campaign(s), ${catalog.campaigns.reduce((n, c) => n + c.runs.length, 0)} run(s).`,
  );
}
