// A small keyboard-accessible tooltip. Pure CSS reveal on hover/focus keeps it
// within the strict CSP (no inline handlers, no positioning library).
export function InfoTip(props: { text: string }) {
  return (
    <span class="infotip" tabIndex={0} role="note" aria-label={props.text}>
      <span class="infotip-icon" aria-hidden="true">
        i
      </span>
      <span class="infotip-bubble" role="tooltip">
        {props.text}
      </span>
    </span>
  );
}
