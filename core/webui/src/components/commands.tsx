import { useState } from 'preact/hooks';

export function CopyButton(props: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      class="btn-copy"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(props.text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1400);
        } catch {
          setCopied(false);
        }
      }}
    >
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

export function CommandLine(props: { label: string; note?: string; command: string }) {
  return (
    <div class="command-row">
      <div class="command-meta">
        <span class="command-label">{props.label}</span>
        {props.note ? <span class="muted small">{props.note}</span> : null}
      </div>
      <div class="command-line">
        <code>{props.command}</code>
        <CopyButton text={props.command} />
      </div>
    </div>
  );
}
