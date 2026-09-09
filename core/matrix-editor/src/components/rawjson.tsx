import { useEffect, useState } from 'preact/hooks';
import type { Suite } from '../types';

export function RawJson(props: { suite: Suite; onApply: (text: string) => Promise<string | null> }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) setText(JSON.stringify(props.suite, null, 2));
  }, [props.suite, open]);

  return (
    <details
      id="advanced"
      class="raw"
      open={open}
      onToggle={(event) => setOpen((event.target as HTMLDetailsElement).open)}
    >
      <summary>Advanced · edit complete suite JSON</summary>
      <p class="muted small">
        Applying JSON replaces the form. Python validates it first and preserves unknown fields so
        errors point at the offending path.
      </p>
      <textarea
        id="raw"
        rows={16}
        spellcheck={false}
        aria-label="Complete suite JSON"
        value={text}
        onInput={(event) => setText((event.target as HTMLTextAreaElement).value)}
      />
      {error ? <p class="alert" role="alert">{error}</p> : null}
      <button
        type="button"
        class="btn-soft"
        onClick={async () => setError(await props.onApply(text))}
      >
        Apply JSON
      </button>
    </details>
  );
}
