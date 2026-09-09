import type { Configuration } from './protocol';

type EditableKey = Exclude<keyof Configuration, 'generation' | 'view'>;
type Edit = { value: Configuration[EditableKey] };
export type DraftSubmission = Map<EditableKey, Edit>;

/** Keep unsaved fields separate from confirmed shared-source values. */
export class ConfigurationDraft {
  private confirmed: Configuration | null = null;
  private edits: DraftSubmission = new Map();

  receive(config: Configuration): Configuration | null {
    if (this.confirmed && config.generation < this.confirmed.generation) return this.values();
    this.confirmed = config;
    return this.values();
  }

  change<K extends EditableKey>(key: K, value: Configuration[K], pending = false): Configuration | null {
    if (!pending && this.confirmed && Object.is(value, this.confirmed[key])) this.edits.delete(key);
    else this.edits.set(key, { value });
    return this.values();
  }

  values(): Configuration | null {
    return this.confirmed ? { ...this.confirmed, ...Object.fromEntries(
      [...this.edits].map(([key, edit]) => [key, edit.value])) } : null;
  }

  capture(): DraftSubmission { return new Map(this.edits); }

  static patch(submission: DraftSubmission): Partial<Configuration> {
    return Object.fromEntries([...submission].map(([key, edit]) => [key, edit.value]));
  }

  acknowledge(submission: DraftSubmission): Configuration | null {
    for (const [key, edit] of submission) {
      // An edit made during the request belongs to the next submission.
      if (this.edits.get(key) === edit) this.edits.delete(key);
    }
    return this.values();
  }
}
