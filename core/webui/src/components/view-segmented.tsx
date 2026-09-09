import { ENUMS, VIEW_TIP } from '../config-fields';
import { InfoTip } from './infotip';

// The waveform / image / both selector, shared by the matrix cards and the
// source controls so both pages separate the plot kinds the same way.
export function ViewSegmented(props: { value: string; onChange: (view: string) => void }) {
  return (
    <span class="view-control">
      <div class="segmented" role="group" aria-label="Plots">
        {ENUMS.view.map((option) => (
          <button
            type="button"
            class={props.value === option ? 'seg seg-on' : 'seg'}
            aria-pressed={props.value === option}
            onClick={() => props.onChange(option)}
          >
            {option}
          </button>
        ))}
      </div>
      <InfoTip text={VIEW_TIP} />
    </span>
  );
}
