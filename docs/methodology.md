# Measurement and interpretation

## Shared input

The unified source makes this primarily a comparison of frontend implementations:
receiving and decoding frames, converting them for a renderer, submitting updates,
and sustaining a workload in a live GUI. Holding the source and workload constant
removes per-demo data generation as a variable. It does not remove source or
transport bottlenecks from streaming results, or make every adapter's API timing
boundary equivalent. Results describe these adapters, not every possible use of
the underlying libraries.

The Python/NumPy and Rust/Tokio sources implement the same
[binary protocol](protocol.md). Backend selection is a benchmark dimension: their
results are never pooled. Numerical fixtures validate documented floating-point
tolerances; cross-platform bit identity is not assumed.

Workloads contain waveform replacement, waveform append, scalar images, RGB images,
or both kinds of plot. Append sends the authoritative full rolling window; current adapters
replace that window. This measures rolling-window display, not compressed append
transport. Disabled plots are removed from generation and transport as well as
rendering. Frontends may convert arrays for their renderer, but never synthesize
benchmark data.

## Multi-plot and multi-curve workloads

Beamline operators keep several plot widgets open at once: several 1-D plots with
several curves each, plus several detector images. A workload can therefore ask
for `waveform_plots` waveform plots with `curves` curves each and `image_plots`
image plots in one window (see [suites](suites.md) for the fields and limits). The
source generates distinct data for every plot and every curve, so a frame carries
`waveform_plots × curves × points` samples and `image_plots` images: transport,
decoding, conversion and rendering all scale with the counts, and the 256 MiB
frame limit applies to the whole frame.

What is measured does not change. One update submission per frame covers all
plots and curves, so **submitted updates/s** still counts frames, `update_ms`
times the whole frame across every plot and `conversion_ms` covers every image
conversion in it. A frontend that draws four plots with four curves each submits
one update per frame, not sixteen. Every frontend arranges the plots with the same
grid rule and equal cell sizes ([presentation](presentation.md)), and metadata
records `plot_counts`, `curves` and the physical data area of the first plot of
each kind, so compare plot-count workloads only against the same counts and
window size: more plots in the same window means smaller plots. The bundled
`multi-plot-smoke`, `beamline-dashboard` and `multi-plot-sweep` scenarios cover
these workloads; the standard `smoke` suite includes one such case.

Streaming uses uncompressed WebSockets, one frame in flight and one latest pending
frame per receiver. Decoded-frame acknowledgements bound buffering. Slow renderers
skip stale input instead of accumulating unbounded latency. Source rate, deadlines
and delivery counters remain visible when the source or transport is limiting.

Replay centrally generates a bounded cyclic dataset in CPU memory (at most
256 MiB). It removes transport from the timed path but retains conversion and GPU
uploads. It is a cache-warm diagnostic, not an unlimited stream of unique frames.

## What the metrics mean

**Submitted updates/s** is the strongest common measurement available here. It is
not displayed FPS. A 120 Hz input or timer does not prove 120 presented frames/s.
`update_ms` measures each adapter's documented synchronous work; asynchronous GPU
work and screen scanout are excluded. Matplotlib rasterization and accelerated
API submission are different boundaries. Timing stages can overlap and must not
be added together or used to infer total frame time.

Compare equivalent workloads, physical plot areas, source backends, delivery modes,
builds, graphics APIs and display/runtime contexts. Charts show the median and
observed range of valid repetition rates. Missing measurements are not zeros.
Receive age uses same-host wall clocks and is not presentation latency. Process-tree
CPU uses 100% for one logical core; summed RSS may count shared pages more than once.

## Running controlled measurements

Use short smoke suites first. For repeatable comparisons, start with three
30-second measured repetitions and a warmup, on an otherwise idle machine. Fix
power policy, screen refresh/scaling, window placement and logical size. Record
operator context with `--display-context`; toolkit-reported refresh is nominal.
Wayland may not expose absolute window positions or physical display timing.

The runner launches one frontend at a time and records readiness, duration,
completion, failures, hardware and source/build identity. Do not run other demos,
edit source, change dependencies or rebuild binaries during a campaign. Visual
checks and screenshots belong outside timed windows. Headless, offscreen and
software-rendered runs are functional diagnostics, not substitutes for desktop
benchmark measurements.

Use receiver probes to investigate source/delivery limits, replay to investigate
transport-independent rendering, and longer stability runs for sustained behavior.
Keep diagnostic attempts separate from the main comparison and retain failures.
Document conditions that changed between attempts.
