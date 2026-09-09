export interface Configuration {
  hz: number;
  points: number;
  append_count: number;
  width: number;
  height: number;
  waveform_mode: 'replace' | 'append';
  image_mode: 'scalar' | 'rgb';
  view: 'waveform' | 'image' | 'both';
  seed: number;
  generation: number;
}

export interface Frame {
  seq: number;
  generation: number;
  emitted_at_ms: number;
  config: Configuration;
  waveform?: Float32Array;
  image?: Float32Array | Uint8Array;
}

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Expected a JSON object');
  }
  return value as Record<string, unknown>;
}

function integer(value: unknown, label: string, minimum = 0): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < minimum) {
    throw new Error(`Invalid ${label}`);
  }
  return value;
}

export function parseConfiguration(value: unknown): Configuration {
  const config = object(value);
  if (typeof config.hz !== 'number' || !Number.isFinite(config.hz) || config.hz <= 0 || config.hz > 120) {
    throw new Error('Source frequency must be in (0, 120] Hz');
  }
  const points = integer(config.points, 'points', 1);
  const append_count = integer(config.append_count, 'append_count', 1);
  if (append_count > points) throw new Error('append_count exceeds points');
  if (config.waveform_mode !== 'append' && config.waveform_mode !== 'replace') {
    throw new Error('Invalid waveform_mode');
  }
  if (config.image_mode !== 'scalar' && config.image_mode !== 'rgb') {
    throw new Error('Invalid image_mode');
  }
  if (!['waveform', 'image', 'both'].includes(String(config.view))) throw new Error('Invalid view');
  return {
    hz: config.hz, points, append_count,
    width: integer(config.width, 'width', 1),
    height: integer(config.height, 'height', 1),
    waveform_mode: config.waveform_mode,
    image_mode: config.image_mode,
    view: config.view as Configuration['view'],
    seed: integer(config.seed, 'seed'),
    generation: integer(config.generation, 'generation'),
  };
}

export function parseFrame(buffer: ArrayBuffer): Frame {
  if (buffer.byteLength < 4) throw new Error('Truncated frame prefix');
  const view = new DataView(buffer);
  const headerLength = view.getUint32(0, true);
  const payloadStart = Math.ceil((4 + headerLength) / 4) * 4;
  if (headerLength === 0 || payloadStart > buffer.byteLength) throw new Error('Truncated frame header');
  const header = object(JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(
    new Uint8Array(buffer, 4, headerLength),
  )));
  if (header.version !== 1) throw new Error('Unsupported protocol version');
  const config = parseConfiguration(header.config);
  if (typeof header.emitted_at_ms !== 'number' || !Number.isFinite(header.emitted_at_ms)) {
    throw new Error('Invalid emission timestamp');
  }
  const frame: Frame = {
    seq: integer(header.seq, 'seq'),
    generation: integer(header.generation, 'generation'),
    emitted_at_ms: header.emitted_at_ms,
    config,
  };
  if (frame.generation !== config.generation) throw new Error('Inconsistent frame generation');
  if (!Array.isArray(header.arrays)) throw new Error('Missing array descriptors');
  const occupied: [number, number][] = [];
  for (const rawDescriptor of header.arrays) {
    const descriptor = object(rawDescriptor);
    const name = descriptor.name;
    if (name !== 'waveform' && name !== 'image') throw new Error('Unknown array name');
    if (frame[name]) throw new Error(`Duplicate ${name} array`);
    const expectedShape = name === 'waveform'
      ? [config.points]
      : config.image_mode === 'rgb' ? [config.height, config.width, 3] : [config.height, config.width];
    const expectedDtype = name === 'image' && config.image_mode === 'rgb' ? 'uint8' : 'float32';
    if (descriptor.dtype !== expectedDtype) throw new Error(`Invalid ${name} dtype`);
    if (!Array.isArray(descriptor.shape) || descriptor.shape.length !== expectedShape.length ||
        descriptor.shape.some((size, index) => size !== expectedShape[index])) {
      throw new Error(`Invalid ${name} shape`);
    }
    const count = expectedShape.reduce((product, size) => product * size, 1);
    const offset = integer(descriptor.offset, 'offset');
    const length = integer(descriptor.nbytes, 'nbytes');
    const expectedBytes = count * (expectedDtype === 'float32' ? 4 : 1);
    if (!Number.isSafeInteger(expectedBytes) || length !== expectedBytes ||
        offset + length > buffer.byteLength - payloadStart) throw new Error(`Truncated ${name} payload`);
    if (expectedDtype === 'float32' && offset % 4 !== 0) throw new Error('Misaligned float32 payload');
    if (occupied.some(([start, end]) => offset < end && offset + length > start)) {
      throw new Error('Overlapping array payloads');
    }
    occupied.push([offset, offset + length]);
    if (name === 'waveform') frame.waveform = new Float32Array(buffer, payloadStart + offset, count);
    else frame.image = expectedDtype === 'float32'
      ? new Float32Array(buffer, payloadStart + offset, count)
      : new Uint8Array(buffer, payloadStart + offset, count);
  }
  if (config.view !== 'image' && !frame.waveform) throw new Error('Missing waveform payload');
  if (config.view !== 'waveform' && !frame.image) throw new Error('Missing image payload');
  return frame;
}

/** Return transport credit after offering the decoded frame, before deferred plotting starts. */
export function acceptStreamPacket(buffer: ArrayBuffer, offer: (frame: Frame) => void,
  acknowledge: (message: string) => void): void {
  const frame = parseFrame(buffer);
  offer(frame);
  acknowledge(JSON.stringify({ ack: frame.seq, generation: frame.generation }));
}

export function parseReplay(buffer: ArrayBuffer): Frame[] {
  if (buffer.byteLength < 4) throw new Error('Truncated replay prefix');
  const view = new DataView(buffer);
  const count = view.getUint32(0, true);
  if (count === 0 || count > Math.floor((buffer.byteLength - 4) / 8)) {
    throw new Error('Invalid replay frame count');
  }
  let cursor = 4;
  const frames: Frame[] = [];
  for (let index = 0; index < count; index += 1) {
    if (cursor + 4 > buffer.byteLength) throw new Error('Truncated replay length');
    const length = view.getUint32(cursor, true);
    cursor += 4;
    if (length === 0 || cursor + length > buffer.byteLength) throw new Error('Truncated replay packet');
    frames.push(parseFrame(buffer.slice(cursor, cursor + length)));
    cursor += length;
  }
  if (cursor !== buffer.byteLength) throw new Error('Trailing replay bytes');
  return frames;
}
