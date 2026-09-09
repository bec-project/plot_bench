// Shapes exchanged with the loopback editor server. The suite schema mirrors
// the Python `plotbench.suites` format exactly so exported and saved JSON runs
// unchanged through the CLI.

export type Kind = 'run' | 'probe';

export type ConfigValue = number | string;
export type Config = Record<string, ConfigValue>;

export interface Case {
  name: string;
  config: Config;
}

export interface CaseGroup {
  name: string;
  base: Config;
  matrix: Record<string, ConfigValue[]>;
}

export interface Suite {
  name?: string;
  description?: string;
  display_context?: string;
  frontends?: string[];
  backends?: string[];
  modes?: string[];
  warmup_seconds?: number;
  measurement_seconds?: number;
  cooldown_seconds?: number;
  repetitions?: number;
  order_seed?: number;
  cases?: Case[];
  case_groups?: CaseGroup[];
}

export interface InitialData {
  suite: Suite;
  frontends: string[];
  backends: string[];
  default_backend: string;
  modes: string[];
  config: Record<string, ConfigValue>;
}

export interface Job {
  run_id: string;
  scenario: string;
  mode: string;
  repetition: number;
  frontend: string | null;
  backend: string;
  config: Record<string, ConfigValue>;
}

export interface Plan {
  kind: Kind;
  suite: Suite;
  case_count: number;
  run_count: number;
  selected_frontends: string[];
  selected_modes: string[];
  selected_backends: string[];
  repetitions: number;
  warmup_seconds: number;
  measurement_seconds: number;
  cooldown_seconds: number;
  estimate: {
    sampling_seconds: number;
    cooldown_seconds: number;
    minimum_seconds: number;
    note: string;
  };
  jobs: Job[];
}

export interface Preset {
  filename: string;
  path: string;
  source: 'bundled' | 'custom';
  name: string;
  description: string;
  kind: Kind;
  case_count: number;
  run_count: number;
  minimum_minutes: number;
  suite: Suite;
  error?: string;
}

export interface SaveResult {
  path: string;
  name: string;
  run_count: number;
  minimum_minutes: number;
  commands: { dry_run: string; quick_check: string; full: string };
}
