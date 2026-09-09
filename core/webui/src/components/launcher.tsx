import type { SaveResult } from '../types';
import { CommandLine } from './commands';

export function Launcher(props: { result: SaveResult; onDismiss: () => void }) {
  const { result } = props;
  return (
    <section class="panel launcher">
      <div class="panel-head">
        <h2>Saved · ready to run</h2>
        <button type="button" class="btn-soft" onClick={props.onDismiss}>
          Dismiss
        </button>
      </div>
      <p class="summary">
        Saved to <code>{result.path}</code>
      </p>
      <p class="muted small">
        This folder is git-ignored. The editor never runs benchmarks — stop it with Ctrl+C, then run one of
        these in your terminal. Progress prints as <code>[i/N]</code> with elapsed time, a live ETA and a
        pass/fail tally.
      </p>
      <div class="commands">
        <CommandLine
          label="1 · Preview"
          note="Validate and print the schedule without launching."
          command={result.commands.dry_run}
        />
        <CommandLine
          label="2 · Quick check"
          note="Four short runs to confirm every component works."
          command={result.commands.quick_check}
        />
        <CommandLine
          label="3 · Full run"
          note={`The configured campaign (~${result.minimum_minutes.toFixed(1)} min minimum, ${result.run_count.toLocaleString()} runs).`}
          command={result.commands.full}
        />
      </div>
    </section>
  );
}
