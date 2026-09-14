mod metrics;
mod opener;
mod protocol;
mod readiness;
mod source;

use anyhow::{Context, Result, ensure};
use clap::{Parser, ValueEnum};
use iced::{
    Border, Color, Element, Fill, Point, Rectangle, Renderer, Size, Subscription, Task, Theme,
    alignment, mouse,
    widget::{button, canvas, column, container, image, responsive, row, space, text, tooltip},
    window,
};
use iced_runtime::image as image_allocation;
use metrics::{Metrics, Sample};
use protocol::{Config, Packet};
use readiness::{Identity, Readiness};
use serde_json::json;
use source::{AppliedView, Source, endpoint, http_client, now_ms, read_limited};
use std::{
    borrow::Cow,
    collections::VecDeque,
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};

const BACKGROUND: Color = Color::from_rgb8(11, 20, 28);
const PANEL: Color = Color::from_rgb8(17, 30, 40);
const BORDER: Color = Color::from_rgb8(37, 55, 69);
const PRIMARY: Color = Color::from_rgb8(216, 230, 237);
const MUTED: Color = Color::from_rgb8(143, 167, 182);
const ACCENT: Color = Color::from_rgb8(100, 220, 204);
const ERROR: Color = Color::from_rgb8(255, 167, 167);
/// Shared curve palette (`CURVE_COLORS` in `plotbench.palette`): curve `c` uses index `c % 8`.
const CURVE_COLORS: [Color; 8] = [
    Color::from_rgb8(100, 220, 204), // #64dccc (accent)
    Color::from_rgb8(245, 199, 110), // #f5c76e
    Color::from_rgb8(122, 166, 255), // #7aa6ff
    Color::from_rgb8(255, 157, 122), // #ff9d7a
    Color::from_rgb8(195, 155, 255), // #c39bff
    Color::from_rgb8(155, 229, 100), // #9be564
    Color::from_rgb8(255, 122, 184), // #ff7ab8
    Color::from_rgb8(110, 231, 255), // #6ee7ff
];
const GRID_SPACING: f32 = 16.0;

fn curve_color(curve: usize) -> Color {
    CURVE_COLORS[curve % CURVE_COLORS.len()]
}

/// Shared layout rule: `columns = ceil(sqrt(n))`, `rows = ceil(n / columns)`, row-major.
fn grid_shape(plots: usize) -> (usize, usize) {
    let plots = plots.max(1);
    let mut columns = (plots as f64).sqrt().floor() as usize;
    while columns * columns < plots {
        columns += 1;
    }
    (columns, plots.div_ceil(columns))
}

fn plot_title(kind: &str, index: usize, count: usize) -> String {
    if count == 1 {
        kind.to_owned()
    } else {
        format!("{kind} {}", index + 1)
    }
}

/// `1 plot` / `3 plots`: a count with its grammatically pluralised noun.
fn plural(count: usize, noun: &str) -> String {
    format!("{count} {noun}{}", if count == 1 { "" } else { "s" })
}

/// Workload strip suffixes: ` · N plot(s) × K curve(s)` when either exceeds one,
/// ` · M plots` when there are several image plots; empty otherwise.
fn workload_suffixes(config: &Config) -> (String, String) {
    let waveform = if config.waveform_plots > 1 || config.curves > 1 {
        format!(
            " · {} × {}",
            plural(config.waveform_plots, "plot"),
            plural(config.curves, "curve")
        )
    } else {
        String::new()
    };
    let image = if config.image_plots > 1 {
        format!(" · {}", plural(config.image_plots, "plot"))
    } else {
        String::new()
    };
    (waveform, image)
}

#[derive(Clone, Debug, ValueEnum)]
enum Mode {
    Stream,
    Replay,
}

impl Mode {
    fn name(&self) -> &'static str {
        match self {
            Self::Stream => "stream",
            Self::Replay => "replay",
        }
    }
}

#[derive(Clone, Debug, Parser)]
#[command(
    version,
    about = "Shared-source plotting benchmark: Iced custom Canvas and image"
)]
struct Args {
    #[arg(long, default_value = "http://127.0.0.1:8765")]
    url: String,
    #[arg(long, value_enum, default_value = "stream")]
    mode: Mode,
    #[arg(long, default_value = "demo")]
    run_id: String,
    #[arg(long, default_value_t = 0.0)]
    duration: f64,
    #[arg(long, default_value_t = 1100)]
    width: u32,
    #[arg(long, default_value_t = 820)]
    height: u32,
    /// Save a PNG after four seconds for visual QA; omit during benchmark measurements.
    #[arg(long)]
    screenshot: Option<std::path::PathBuf>,
}

#[derive(Clone, Debug)]
enum Message {
    Tick,
    SourceReady,
    ImageReady(
        Identity,
        usize,
        Result<image_allocation::Allocation, image_allocation::Error>,
    ),
    Window(window::Id),
    Scale(f32),
    MonitorSize(Option<Size>),
    WindowPosition(Option<Point>),
    System(iced::system::Information),
    Close,
    Screenshot(window::Screenshot),
    Resized(Size),
    OpenControls,
    ControlsOpened(Result<(), String>),
    TogglePlot(Plot),
    SelectionCompleted(Result<AppliedView, String>),
}

#[derive(Clone, Copy, Debug)]
enum Plot {
    Waveform,
    Image,
}

fn selection_target(view: &str, plot: Plot, locked: bool, pending: bool) -> Option<&'static str> {
    if locked || pending {
        return None;
    }
    match (view, plot) {
        ("both", Plot::Waveform) => Some("image"),
        ("both", Plot::Image) => Some("waveform"),
        ("image", Plot::Waveform) | ("waveform", Plot::Image) => Some("both"),
        _ => None,
    }
}

struct PendingSelection {
    target: &'static str,
    started: Instant,
    accepted: Option<AppliedView>,
}

struct PreparedFrame {
    identity: Identity,
    config: Config,
    receive_age_ms: Option<f64>,
    /// One entry per waveform plot; each holds one path (and its layout size) per curve.
    waveforms: Vec<Vec<(canvas::Path, Size)>>,
    /// One allocation slot per image plot, filled as `ImageReady` completions arrive.
    allocations: Vec<Option<image_allocation::Allocation>>,
    remaining_allocations: usize,
    started: Instant,
    cpu_ms: f64,
    conversion_ms: f64,
    allocation_started: Option<Instant>,
}

/// One Canvas program per waveform plot, drawing every curve of that plot.
struct Waveform {
    paths: Vec<canvas::Path>,
    path_size: Size,
    points: usize,
    seq: u64,
    scale: f32,
    cache: canvas::Cache,
    draw_sample: Arc<Mutex<Option<(u64, f64)>>>,
    data_area: Arc<Mutex<Option<Size>>>,
    canvas_size: Arc<Mutex<Option<Size>>>,
}

impl Waveform {
    fn new(scale: f32) -> Self {
        Self {
            paths: Vec::new(),
            path_size: Size::new(1.0, 1.0),
            points: 0,
            seq: 0,
            scale,
            cache: canvas::Cache::new(),
            draw_sample: Arc::new(Mutex::new(None)),
            data_area: Arc::new(Mutex::new(None)),
            canvas_size: Arc::new(Mutex::new(None)),
        }
    }
}

impl canvas::Program<Message> for Waveform {
    type State = ();

    fn draw(
        &self,
        _state: &(),
        renderer: &Renderer,
        _theme: &Theme,
        bounds: Rectangle,
        _cursor: mouse::Cursor,
    ) -> Vec<canvas::Geometry> {
        *self.data_area.lock().unwrap() = Some(plot_area(bounds.size()).size());
        let started = Instant::now();
        let generated = std::cell::Cell::new(false);
        let geometry = self.cache.draw(renderer, bounds.size(), |frame| {
            generated.set(true);
            let area = plot_area(bounds.size());
            let foreground = MUTED;
            frame.fill_rectangle(Point::ORIGIN, bounds.size(), PANEL);
            let axes = canvas::Path::new(|b| {
                b.move_to(Point::new(area.x, area.y));
                b.line_to(Point::new(area.x, area.y + area.height));
                b.line_to(Point::new(area.x + area.width, area.y + area.height));
            });
            frame.stroke(
                &axes,
                canvas::Stroke::default()
                    .with_color(foreground)
                    .with_width(1.0 / self.scale),
            );
            for (label, y) in [
                ("1.5", area.y),
                ("0", area.y + area.height / 2.0),
                ("-1.5", area.y + area.height),
            ] {
                frame.fill_text(canvas::Text {
                    content: label.into(),
                    position: Point::new(4.0, y - 6.0),
                    color: foreground,
                    size: 12.0.into(),
                    ..canvas::Text::default()
                });
            }
            for (label, fraction) in [
                ("0".to_string(), 0.0),
                ((self.points.saturating_sub(1) / 2).to_string(), 0.5),
                (self.points.saturating_sub(1).to_string(), 1.0),
            ] {
                frame.fill_text(canvas::Text {
                    content: label,
                    position: Point::new(
                        area.x + fraction * area.width - fraction * 38.0,
                        area.y + area.height + 7.0,
                    ),
                    color: foreground,
                    size: 12.0.into(),
                    ..canvas::Text::default()
                });
            }
            let original = plot_area(self.path_size);
            let sx = area.width / original.width;
            let sy = area.height / original.height;
            let fit = canvas::path::lyon_path::math::Transform::new(
                sx,
                0.0,
                0.0,
                sy,
                area.x - original.x * sx,
                area.y - original.y * sy,
            );
            for (curve, path) in self.paths.iter().enumerate() {
                let path = if bounds.size() == self.path_size {
                    Cow::Borrowed(path)
                } else {
                    Cow::Owned(path.transform(&fit))
                };
                frame.stroke(
                    &path,
                    canvas::Stroke::default()
                        .with_color(curve_color(curve))
                        .with_width(1.0 / self.scale),
                );
            }
        });
        if generated.get() {
            *self.draw_sample.lock().unwrap() =
                Some((self.seq, started.elapsed().as_secs_f64() * 1000.0));
        }
        vec![geometry]
    }
}

fn plot_area(size: Size) -> Rectangle {
    Rectangle {
        x: 42.0,
        y: 14.0,
        width: (size.width - 58.0).max(1.0),
        height: (size.height - 46.0).max(1.0),
    }
}

fn curve_path(bytes: &[u8], size: Size) -> canvas::Path {
    let area = plot_area(size);
    let count = bytes.len() / 4;
    let dx = area.width / count.saturating_sub(1).max(1) as f32;
    canvas::Path::new(|builder| {
        for (index, chunk) in bytes.chunks_exact(4).enumerate() {
            let value = f32::from_le_bytes(chunk.try_into().expect("Four-byte chunk"));
            let point = Point::new(
                area.x + index as f32 * dx,
                area.y + (1.5 - value) / 3.0 * area.height,
            );
            if index == 0 {
                builder.move_to(point);
            } else {
                builder.line_to(point);
            }
        }
    })
}

struct App {
    args: Args,
    source: Source,
    metrics: Metrics,
    config: Config,
    palette: Arc<Vec<[u8; 3]>>,
    waveforms: Vec<Waveform>,
    images: Vec<image_allocation::Allocation>,
    readiness: Readiness<Packet>,
    preparing: Option<PreparedFrame>,
    image_area: Arc<Mutex<Option<Size>>>,
    pending: Option<Sample>,
    last_identity: Option<Identity>,
    recent: VecDeque<Instant>,
    skipped: u64,
    update_ms: f64,
    age: Option<f64>,
    started: Option<Instant>,
    hud_updated: Instant,
    hud: [String; 4],
    hud_targets: [String; 4],
    state_text: String,
    window: Option<window::Id>,
    scale: f32,
    screenshot_requested: bool,
    termination_reason: &'static str,
    controls_error: Option<String>,
    connection_error: bool,
    pending_selection: Option<PendingSelection>,
    selection_error: Option<String>,
}

impl App {
    fn boot(args: Args, config: Config, palette: Arc<Vec<[u8; 3]>>) -> (Self, Task<Message>) {
        let metadata = json!({
            "renderer":"Iced wgpu (actual adapter recorded after window creation)",
            "iced_version":"0.14.0", "app_version":env!("CARGO_PKG_VERSION"),
            "build_profile":if cfg!(debug_assertions) { "debug" } else { "release" },
            "os":std::env::consts::OS,"architecture":std::env::consts::ARCH,
            "display_protocol":if cfg!(target_os = "linux") { "wayland" } else { "native" },
            "pixel_ratio":null,"viewport_logical":[args.width,args.height],
            "viewport_size":[args.width,args.height],"viewport_size_units":"logical pixels",
            "plot_viewport_units":"physical pixels; data drawing area excluding axes",
            "measurement_stage":"update_ms: synchronous CPU preparation (one Canvas path per curve of every waveform plot and RGBA conversion of every image plot) plus ready-frame adoption; excludes asynchronous allocation waiting and later Canvas tessellation. update_complete_ms: elapsed from selected-packet preparation to ready-frame adoption, including allocation and event-loop waiting for every image plot; not GPU or screen presentation time. image_upload_wait_ms: first allocation request to the last completion-message processing, including queue/GPU/event scheduling. draw_ms: sum of the Canvas cache generations (axes/text/stroke tessellation) of every waveform plot when each callback matches the adopted frame; excludes image upload, GPU submission and physical presentation",
            "update_strategy":"authoritative full-window replacement in append and replace; no decimation; one Canvas per waveform plot with one path per curve; iced_runtime::image::allocate for every image plot before adopting a frame; retain the last ready Allocations until replacement; one active preparation/allocation plus one latest CPU packet; stale-generation allocation completions discarded",
            "image_interpolation":"nearest", "image_levels":[0,1],"waveform_y_range":[-1.5,1.5],
            "waveform_stroke_physical_px":1,"custom_work":"Custom Canvas waveform paths, fixed axes and ticks; custom scalar LUT to RGBA conversion; custom plot grid. Iced is a GUI toolkit, not a plotting library.",
            "gpu_time_available":false,"displayed_fps_available":false,
            "mailbox_capacity":1,"source_notifications":"bounded coalesced wakeup; no packet polling",
            "housekeeping_interval_ms":250,"target_hz":config.hz,"config":config,
            "plot_counts":{"waveform":config.visible_waveform_plots(),"image":config.visible_image_plots()},
            "curves":config.curves,
            "plot_layout":"waveform plots first, then image plots; columns = ceil(sqrt(n)), rows = ceil(n / columns), row-major, equal cells",
            "curve_colors":["#64dccc","#f5c76e","#7aa6ff","#ff9d7a","#c39bff","#9be564","#ff7ab8","#6ee7ff"],
            "image_allocation_timeout_seconds":20,
            "monitor_identity":null,"monitor_refresh_hz":null,
            "display_metadata_note":"Iced exposes monitor dimensions and window position here, not physical monitor identity or actual refresh rate; controlled-display context must be supplied by the harness",
            "presentation_policy":"Iced default vsync=true; ICED_PRESENT_MODE may override. Actual selected surface mode and physical presentation are not observed",
            "renderer_environment":renderer_environment(),
            "build_provenance":build_provenance(),
            "stream_flow_control":"one in-flight packet; acknowledgement after receiver decode and latest-mailbox publication",
            "screenshot_requested":args.screenshot.is_some()
        });
        let metrics = Metrics::start(
            args.url.clone(),
            args.mode.name().into(),
            args.run_id.clone(),
            metadata,
        );
        let source = Source::start(args.url.clone(), matches!(args.mode, Mode::Replay));
        let hud_targets = metric_target_hints(None, matches!(args.mode, Mode::Replay));
        let waveforms = (0..config.waveform_plots)
            .map(|_| Waveform::new(1.0))
            .collect();
        let app = Self {
            args,
            source,
            metrics,
            config,
            palette,
            waveforms,
            images: Vec::new(),
            readiness: Readiness::default(),
            preparing: None,
            image_area: Arc::new(Mutex::new(None)),
            pending: None,
            last_identity: None,
            recent: VecDeque::new(),
            skipped: 0,
            update_ms: 0.0,
            age: None,
            started: None,
            hud_updated: Instant::now() - Duration::from_secs(1),
            hud: ["—".into(), "—".into(), "0".into(), "—".into()],
            hud_targets,
            state_text: "Connecting".into(),
            window: None,
            scale: 1.0,
            screenshot_requested: false,
            termination_reason: "user",
            controls_error: None,
            connection_error: false,
            pending_selection: None,
            selection_error: None,
        };
        (
            app,
            Task::batch([
                iced::system::information().map(Message::System),
                window::latest()
                    .then(|id| id.map_or(Task::none(), |id| Task::done(Message::Window(id)))),
            ]),
        )
    }

    /// Estimated Canvas size of one grid cell before the first layout pass reports it.
    fn estimated_canvas_size(&self, config: &Config) -> Size {
        let (columns, rows) =
            grid_shape(config.visible_waveform_plots() + config.visible_image_plots());
        let width = (self.args.width as f32 - 48.0 - GRID_SPACING * (columns - 1) as f32)
            / columns as f32
            - 36.0;
        let height = (self.args.height as f32 - 276.0 - GRID_SPACING * (rows - 1) as f32)
            / rows as f32
            - 84.0;
        Size::new(width.max(1.0), height.max(1.0))
    }

    /// The Canvas size to build waveform plot `plot` for: the last measured layout of that
    /// plot, unless the frame changes the visible plot set (its old measurement is stale).
    fn waveform_size(&self, plot: usize, config: &Config) -> Size {
        let same_layout = (
            self.config.view.as_str(),
            self.config.visible_waveform_plots(),
            self.config.visible_image_plots(),
        ) == (
            config.view.as_str(),
            config.visible_waveform_plots(),
            config.visible_image_plots(),
        );
        same_layout
            .then(|| self.waveforms.get(plot))
            .flatten()
            .and_then(|waveform| *waveform.canvas_size.lock().unwrap())
            .unwrap_or_else(|| self.estimated_canvas_size(config))
    }

    /// Total Canvas generation time when every waveform plot reported a match for `seq`.
    fn take_draw_ms(&self, seq: u64) -> Option<f64> {
        let samples: Vec<_> = self
            .waveforms
            .iter()
            .map(|waveform| waveform.draw_sample.lock().unwrap().take())
            .collect();
        (!samples.is_empty() && samples.iter().all(|s| s.is_some_and(|(s, _)| s == seq)))
            .then(|| samples.iter().flatten().map(|(_, ms)| ms).sum())
    }

    fn finish_pending(&mut self) {
        if let Some(mut sample) = self.pending.take() {
            sample.draw_ms = self.take_draw_ms(sample.seq);
            self.metrics.record(sample);
        }
    }

    fn record_geometry_metadata(&self) {
        let waveform = if self.config.view == "image" {
            None
        } else {
            self.waveforms
                .first()
                .and_then(|waveform| *waveform.data_area.lock().unwrap())
        };
        let image = if self.config.view == "waveform" {
            None
        } else {
            *self.image_area.lock().unwrap()
        };
        let dimensions =
            |size: Option<Size>, ratio| size.map(|s| [s.width * ratio, s.height * ratio]);
        let mut buffer = self.metrics.buffer.lock().unwrap();
        buffer.metadata["plot_viewports"] = json!({
            "waveform": dimensions(waveform, self.scale),
            "image": dimensions(image, self.scale),
        });
        buffer.metadata["plot_viewports_logical"] = json!({
            "waveform": dimensions(waveform, 1.0),
            "image": dimensions(image, 1.0),
        });
        buffer.metadata["plot_counts"] = json!({
            "waveform": self.config.visible_waveform_plots(),
            "image": self.config.visible_image_plots(),
        });
        buffer.metadata["curves"] = json!(self.config.curves);
    }

    fn collect_latest(&mut self) {
        if let Some((epoch, packet)) = self.source.take_latest_with_epoch() {
            self.metrics.buffer.lock().unwrap().metadata["receiver_connection_epoch"] =
                json!(epoch);
            let identity = Identity {
                epoch,
                generation: packet.header.generation,
                seq: packet.presentation_seq,
            };
            self.readiness.offer(identity, packet);
        }
    }

    fn prepare_next(&mut self) -> Task<Message> {
        let Some((identity, packet)) = self.readiness.start_next() else {
            return Task::none();
        };
        let started = Instant::now();
        let converting = Instant::now();
        let config = &packet.header.config;
        let waveforms: Vec<Vec<(canvas::Path, Size)>> = if packet.array("waveform").is_some() {
            (0..config.waveform_plots)
                .map(|plot| {
                    let size = self.waveform_size(plot, config);
                    (0..config.curves)
                        .map(|curve| {
                            let bytes = packet
                                .waveform_curve(plot, curve)
                                .expect("Validated waveform layout");
                            (curve_path(bytes, size), size)
                        })
                        .collect()
                })
                .collect()
        } else {
            Vec::new()
        };
        let handles: Vec<image::Handle> = if packet.array("image").is_some() {
            (0..config.image_plots)
                .map(|plot| {
                    image::Handle::from_rgba(
                        config.width,
                        config.height,
                        protocol::rgba(
                            packet.image_plot(plot).expect("Validated image layout"),
                            config.image_mode == "rgb",
                            &self.palette,
                        ),
                    )
                })
                .collect()
        } else {
            Vec::new()
        };
        let conversion_ms = converting.elapsed().as_secs_f64() * 1000.0;
        let mut prepared = PreparedFrame {
            identity,
            config: packet.header.config,
            receive_age_ms: packet.receive_age_ms,
            waveforms,
            allocations: (0..handles.len()).map(|_| None).collect(),
            remaining_allocations: handles.len(),
            started,
            cpu_ms: started.elapsed().as_secs_f64() * 1000.0,
            conversion_ms,
            allocation_started: None,
        };
        if !handles.is_empty() {
            prepared.allocation_started = Some(Instant::now());
            self.preparing = Some(prepared);
            Task::batch(handles.into_iter().enumerate().map(|(plot, handle)| {
                image_allocation::allocate(handle)
                    .map(move |result| Message::ImageReady(identity, plot, result))
            }))
        } else {
            self.collect_latest();
            if self.readiness.complete(identity) {
                self.adopt(prepared, Vec::new(), None);
            }
            if self.readiness.has_candidate() {
                Task::done(Message::SourceReady)
            } else {
                Task::none()
            }
        }
    }

    fn adopt(
        &mut self,
        prepared: PreparedFrame,
        allocations: Vec<image_allocation::Allocation>,
        image_upload_wait_ms: Option<f64>,
    ) {
        // Flush the previous observation before clearing its Canvas callback slots.
        self.finish_pending();
        let adopting = Instant::now();
        for waveform in &self.waveforms {
            *waveform.draw_sample.lock().unwrap() = None;
        }
        self.config = prepared.config;
        let identity = prepared.identity;
        let skipped = self
            .last_identity
            .filter(|previous| {
                (previous.epoch, previous.generation) == (identity.epoch, identity.generation)
            })
            .map_or(0, |previous| {
                identity.seq.saturating_sub(previous.seq.saturating_add(1))
            });
        if !prepared.waveforms.is_empty() {
            // Rebuild the Canvas set when the plot count changes; otherwise reuse the
            // programs and only replace their paths.
            let scale = self.scale;
            self.waveforms.truncate(prepared.waveforms.len());
            self.waveforms
                .resize_with(prepared.waveforms.len(), || Waveform::new(scale));
            for (waveform, curves) in self.waveforms.iter_mut().zip(prepared.waveforms) {
                waveform.path_size = curves
                    .first()
                    .map_or(Size::new(1.0, 1.0), |(_, size)| *size);
                waveform.paths = curves.into_iter().map(|(path, _)| path).collect();
                waveform.points = self.config.points;
                waveform.seq = identity.seq;
                waveform.cache.clear();
            }
        }
        self.images = allocations;
        self.update_ms = prepared.cpu_ms + adopting.elapsed().as_secs_f64() * 1000.0;
        self.age = prepared.receive_age_ms;
        self.skipped += skipped;
        self.last_identity = Some(identity);
        self.recent.push_back(Instant::now());
        self.started.get_or_insert_with(Instant::now);
        self.pending = Some(Sample {
            seq: identity.seq,
            generation: identity.generation,
            client_time_ms: now_ms(),
            update_ms: self.update_ms,
            update_complete_ms: prepared.started.elapsed().as_secs_f64() * 1000.0,
            image_upload_wait_ms,
            receive_age_ms: prepared.receive_age_ms,
            skipped,
            conversion_ms: prepared.conversion_ms,
            draw_ms: None,
        });
    }

    fn fail_allocation(&mut self, message: String) -> Task<Message> {
        eprintln!("{message}");
        self.metrics.buffer.lock().unwrap().error = Some(message);
        self.termination_reason = "error";
        self.readiness.close();
        self.preparing = None;
        self.finish_pending();
        iced::exit()
    }

    fn update(&mut self, message: Message) -> Task<Message> {
        match message {
            Message::SourceReady => {
                self.collect_latest();
                let selection = self
                    .source
                    .take_control_result()
                    .map_or(Task::none(), |result| {
                        Task::done(Message::SelectionCompleted(result))
                    });
                return Task::batch([self.prepare_next(), selection]);
            }
            Message::ImageReady(identity, plot, result) => {
                // A newer generation can already be in the mailbox while its
                // coalesced wakeup waits in the event queue. Observe it first.
                self.collect_latest();
                let Some(mut prepared) = self.preparing.take() else {
                    return Task::none();
                };
                // Stale (other identity), duplicate or out-of-range completions are discarded.
                if prepared.identity != identity
                    || prepared
                        .allocations
                        .get(plot)
                        .is_none_or(|slot| slot.is_some())
                {
                    self.preparing = Some(prepared);
                    return Task::none();
                }
                match result {
                    Ok(allocation) => {
                        prepared.allocations[plot] = Some(allocation);
                        prepared.remaining_allocations -= 1;
                    }
                    Err(error) => {
                        // Only the frame that would still be adopted is fatal; a
                        // superseded frame (newer generation or closed run) is
                        // logged and discarded like any other stale completion.
                        let message = format!(
                            "Image allocation failed for image plot {}: {error}",
                            plot + 1
                        );
                        if self.readiness.complete(identity) {
                            return self.fail_allocation(message);
                        }
                        eprintln!("{message} (frame superseded; discarded)");
                        return self.prepare_next();
                    }
                }
                if prepared.remaining_allocations > 0 {
                    self.preparing = Some(prepared);
                    return Task::none();
                }
                // Every image plot of this frame is allocated: adopt them together.
                if self.readiness.complete(identity) {
                    let wait = prepared
                        .allocation_started
                        .map(|started| started.elapsed().as_secs_f64() * 1000.0);
                    let allocations = std::mem::take(&mut prepared.allocations)
                        .into_iter()
                        .map(|slot| slot.expect("Every image plot completed"))
                        .collect();
                    self.adopt(prepared, allocations, wait);
                }
                return self.prepare_next();
            }
            Message::Tick => {
                if self.args.duration > 0.0
                    && self
                        .started
                        .is_some_and(|s| s.elapsed().as_secs_f64() >= self.args.duration)
                {
                    self.termination_reason = "duration";
                    self.readiness.close();
                    self.preparing = None;
                    self.finish_pending();
                    return iced::exit();
                }
                if self
                    .preparing
                    .as_ref()
                    .is_some_and(|frame| frame.started.elapsed() > Duration::from_secs(20))
                {
                    return self.fail_allocation(
                        "Image allocation of the frame did not complete within 20 seconds".into(),
                    );
                }
                if let Some(pending) = &self.pending_selection {
                    if let Some(applied) = &pending.accepted
                        && self
                            .last_identity
                            .is_some_and(|identity| identity.generation >= applied.generation)
                    {
                        if self.config.view != applied.view {
                            self.selection_error = Some(
                                "Another source change replaced the requested plot selection."
                                    .into(),
                            );
                        }
                        self.pending_selection = None;
                    } else if pending.started.elapsed() >= Duration::from_secs(60) {
                        self.selection_error = Some(format!(
                            "Timed out waiting for the source to show {}. The buttons reflect the current data.",
                            pending.target
                        ));
                        self.pending_selection = None;
                    }
                }
                if self.args.screenshot.is_some()
                    && !self.screenshot_requested
                    && self
                        .started
                        .is_some_and(|s| s.elapsed() >= Duration::from_secs(4))
                    // Iced captures the previous renderer primitives. Let refreshed
                    // text reach a redraw before capturing its weak paragraph handles.
                    && (Duration::from_millis(150)..Duration::from_millis(400))
                        .contains(&self.hud_updated.elapsed())
                    && let Some(id) = self.window
                {
                    self.screenshot_requested = true;
                    return window::screenshot(id).map(Message::Screenshot);
                }
                if self.hud_updated.elapsed() >= Duration::from_millis(500) {
                    self.record_geometry_metadata();
                    self.hud_updated = Instant::now();
                    while self
                        .recent
                        .front()
                        .is_some_and(|time| time.elapsed() > Duration::from_secs(1))
                    {
                        self.recent.pop_front();
                    }
                    self.hud = [
                        format!("{:.1} /s", self.recent.len() as f64),
                        format!("{:.2} ms", self.update_ms),
                        self.skipped.to_string(),
                        self.age.map_or("—".into(), |v| format!("{v:.1} ms")),
                    ];
                    self.hud_targets = metric_target_hints(
                        self.last_identity.map(|_| self.config.hz),
                        matches!(self.args.mode, Mode::Replay),
                    );
                    let state = self.source.shared.lock().unwrap();
                    let mut metrics = self.metrics.buffer.lock().unwrap();
                    metrics.metadata["target_hz"] = json!(self.config.hz);
                    metrics.metadata["config"] = json!(self.config);
                    if let Some(values) = state.metadata.as_object() {
                        for (key, value) in values {
                            metrics.metadata[key] = value.clone();
                        }
                    }
                    self.state_text = metrics.error.as_ref().map_or_else(
                        || state.status.clone(),
                        |error| format!("{} | {error}", state.status),
                    );
                    self.connection_error =
                        state.status.starts_with("Error:") || metrics.error.is_some();
                    if let Some(id) = self.window {
                        return Self::display_tasks(id);
                    }
                }
            }
            Message::Window(id) => {
                self.window = Some(id);
                return Self::display_tasks(id);
            }
            Message::MonitorSize(size) => {
                self.metrics.buffer.lock().unwrap().metadata["monitor_size_logical"] =
                    json!(size.map(|size| [size.width, size.height]));
            }
            Message::WindowPosition(position) => {
                self.metrics.buffer.lock().unwrap().metadata["window_position_logical"] =
                    json!(position.map(|point| [point.x, point.y]));
            }
            Message::Resized(size) => {
                self.args.width = size.width.round() as u32;
                self.args.height = size.height.round() as u32;
                let mut buffer = self.metrics.buffer.lock().unwrap();
                buffer.metadata["viewport_size"] = json!([size.width, size.height]);
                buffer.metadata["viewport_logical"] = json!([size.width, size.height]);
                buffer.metadata["viewport_physical"] =
                    json!([size.width * self.scale, size.height * self.scale]);
            }
            Message::OpenControls => {
                self.controls_error = None;
                let url = self.args.url.clone();
                return Task::perform(async move { opener::open(&url) }, Message::ControlsOpened);
            }
            Message::ControlsOpened(result) => {
                self.controls_error = result.err();
            }
            Message::TogglePlot(plot) => {
                if let Some(target) = selection_target(
                    &self.config.view,
                    plot,
                    self.args.duration > 0.0,
                    self.pending_selection.is_some(),
                ) {
                    self.selection_error = None;
                    match self.source.request_view(target) {
                        Ok(()) => {
                            self.pending_selection = Some(PendingSelection {
                                target,
                                started: Instant::now(),
                                accepted: None,
                            })
                        }
                        Err(error) => {
                            self.selection_error = Some(format!("Plot selection failed: {error:#}"))
                        }
                    }
                }
            }
            Message::SelectionCompleted(result) => match result {
                Ok(applied) => {
                    if let Some(pending) = &mut self.pending_selection {
                        pending.accepted = Some(applied);
                    }
                }
                Err(error) => {
                    self.pending_selection = None;
                    self.selection_error = Some(format!("Plot selection failed: {error}"));
                }
            },
            Message::Scale(scale) => {
                self.scale = scale;
                for waveform in &mut self.waveforms {
                    if waveform.scale != scale {
                        waveform.scale = scale;
                        waveform.cache.clear();
                    }
                }
                let mut buffer = self.metrics.buffer.lock().unwrap();
                buffer.metadata["pixel_ratio"] = json!(scale);
                buffer.metadata["viewport_physical"] = json!([
                    self.args.width as f32 * scale,
                    self.args.height as f32 * scale
                ]);
            }
            Message::System(info) => {
                let mut buffer = self.metrics.buffer.lock().unwrap();
                buffer.metadata["renderer"] = json!(info.graphics_backend);
                buffer.metadata["gpu"] = json!(info.graphics_adapter);
                buffer.metadata["system_version"] = json!(info.system_version);
                buffer.metadata["cpu"] = json!(info.cpu_brand);
            }
            Message::Close => {
                self.termination_reason = "user";
                self.readiness.close();
                self.preparing = None;
                self.finish_pending();
                return iced::exit();
            }
            Message::Screenshot(screenshot) => {
                if let Some(path) = &self.args.screenshot {
                    if let Err(error) = save_screenshot(path, &screenshot) {
                        let message = format!("Screenshot failed: {error:#}");
                        eprintln!("{message}");
                        self.metrics.buffer.lock().unwrap().error = Some(message);
                    } else {
                        eprintln!("Screenshot saved: {}", path.display());
                    }
                }
            }
        }
        Task::none()
    }

    fn subscription(&self) -> Subscription<Message> {
        Subscription::batch([
            Subscription::run_with(self.source.wakeups.clone(), source::Wakeups::stream)
                .map(|_| Message::SourceReady),
            iced::time::every(Duration::from_millis(250)).map(|_| Message::Tick),
            window::open_events().map(Message::Window),
            window::close_requests().map(|_| Message::Close),
            window::resize_events().map(|(_, size)| Message::Resized(size)),
        ])
    }

    fn display_tasks(id: window::Id) -> Task<Message> {
        Task::batch([
            window::scale_factor(id).map(Message::Scale),
            window::monitor_size(id).map(Message::MonitorSize),
            window::position(id).map(Message::WindowPosition),
        ])
    }

    fn view(&self) -> Element<'_, Message> {
        let connection = if self.connection_error {
            "●  Source error"
        } else if self.last_identity.is_none() {
            "●  Connecting"
        } else if matches!(self.args.mode, Mode::Replay) {
            "●  Replay ready"
        } else {
            "●  Connected"
        };
        let header = row![
            column![
                text("PLOTTING BENCHMARK").size(10).color(MUTED),
                row![
                    text("Iced").size(26).color(PRIMARY),
                    badge("Canvas / wgpu", false),
                    badge(self.args.mode.name(), true)
                ]
                .spacing(12)
                .align_y(alignment::Vertical::Center),
            ]
            .spacing(9),
            space().width(Fill),
            column![
                text(connection)
                    .size(11)
                    .color(if self.connection_error { ERROR } else { ACCENT }),
                button(text("Source controls").size(12))
                    .padding([10, 14])
                    .on_press(Message::OpenControls)
                    .style(source_button),
            ]
            .spacing(9)
            .align_x(alignment::Horizontal::Right),
        ]
        .align_y(alignment::Vertical::Center);
        let (waveform_suffix, image_suffix) = workload_suffixes(&self.config);
        let workload = container(
            row![
                workload_item("TARGET RATE", format!("{} Hz", self.config.hz)),
                workload_item(
                    "WAVEFORM",
                    format!(
                        "{} points · {}{waveform_suffix}",
                        grouped_count(self.config.points),
                        self.config.waveform_mode
                    )
                ),
                workload_item(
                    "IMAGE",
                    format!(
                        "{} × {} · {}{image_suffix}",
                        self.config.width, self.config.height, self.config.image_mode
                    )
                ),
                column![
                    text("PLOTS").size(9).color(MUTED),
                    row![
                        self.plot_button(Plot::Waveform),
                        self.plot_button(Plot::Image)
                    ]
                    .spacing(6)
                    .height(20),
                ]
                .spacing(2)
                .width(Fill),
            ]
            .spacing(16),
        )
        .padding([14, 18])
        .style(panel_style);
        let metrics = row![
            metric_item("Submitted", &self.hud[0], &self.hud_targets[0]),
            metric_item("Update time", &self.hud[1], &self.hud_targets[1]),
            metric_item("Skipped", &self.hud[2], &self.hud_targets[2]),
            metric_item("Receive age", &self.hud[3], &self.hud_targets[3]),
        ]
        .spacing(16);
        let plots = self.plot_grid();
        let footer = row![
            text("Submitted updates · not displayed FPS")
                .size(10)
                .color(MUTED),
            space().width(Fill),
            text("Custom Canvas waveform · custom scalar mapping")
                .size(10)
                .color(MUTED),
        ]
        .spacing(12)
        .align_y(alignment::Vertical::Center);
        let mut body = column![header, workload, metrics].spacing(16);
        if let Some(error) = &self.selection_error {
            body = body.push(text(error).size(11).color(ERROR));
        }
        if self.connection_error {
            body = body.push(text(&self.state_text).size(11).color(ERROR));
        }
        if let Some(error) = &self.controls_error {
            body = body.push(text(error).size(11).color(ERROR));
        }
        body = body.push(plots).push(footer);
        container(body)
            .padding(24)
            .width(Fill)
            .height(Fill)
            .style(|_| container::Style {
                background: Some(BACKGROUND.into()),
                text_color: Some(PRIMARY),
                ..container::Style::default()
            })
            .into()
    }

    /// Waveform cards first, then image cards, in the shared `ceil(sqrt(n))`-column grid.
    /// Trailing cells of the last row stay empty so every cell keeps the same size.
    fn plot_grid(&self) -> Element<'_, Message> {
        let mut cells: Vec<Element<'_, Message>> = Vec::new();
        if self.config.view != "image" {
            let count = self.waveforms.len();
            let curves = if self.config.curves > 1 {
                format!(" · {} curves", self.config.curves)
            } else {
                String::new()
            };
            for (index, waveform) in self.waveforms.iter().enumerate() {
                let canvas = responsive(move |available| {
                    *waveform.canvas_size.lock().unwrap() = Some(available);
                    canvas::Canvas::new(waveform)
                        .width(Fill)
                        .height(Fill)
                        .into()
                });
                cells.push(plot_card(
                    plot_title("Waveform", index, count),
                    format!(
                        "{} points · {}{curves} · full data",
                        grouped_count(self.config.points),
                        self.config.waveform_mode
                    ),
                    canvas.into(),
                ));
            }
        }
        if self.config.view != "waveform" {
            let count = self.config.image_plots;
            let mode = if self.config.image_mode == "rgb" {
                "RGB"
            } else {
                "scalar · levels 0–1"
            };
            for index in 0..count {
                let image_view: Element<'_, Message> = if let Some(handle) = self.images.get(index)
                {
                    responsive(move |available| {
                        let original =
                            Size::new(self.config.width as f32, self.config.height as f32);
                        if index == 0 {
                            *self.image_area.lock().unwrap() =
                                Some(iced::ContentFit::Contain.fit(original, available));
                        }
                        image(handle.handle().clone())
                            .filter_method(image::FilterMethod::Nearest)
                            .content_fit(iced::ContentFit::Contain)
                            .width(Fill)
                            .height(Fill)
                            .into()
                    })
                    .into()
                } else {
                    container(text("Waiting for image").size(13).color(MUTED))
                        .center_x(Fill)
                        .center_y(Fill)
                        .into()
                };
                cells.push(plot_card(
                    plot_title("Image", index, count),
                    format!("{} × {} · {}", self.config.width, self.config.height, mode),
                    image_view,
                ));
            }
        }
        let (columns, _) = grid_shape(cells.len());
        let mut grid = column![].spacing(GRID_SPACING).height(Fill);
        let mut current = row![].spacing(GRID_SPACING).height(Fill);
        let mut filled = 0;
        for cell in cells {
            current = current.push(cell);
            filled += 1;
            if filled == columns {
                grid = grid.push(current);
                current = row![].spacing(GRID_SPACING).height(Fill);
                filled = 0;
            }
        }
        if filled > 0 {
            for _ in filled..columns {
                current = current.push(space().width(Fill).height(Fill));
            }
            grid = grid.push(current);
        }
        grid.into()
    }

    fn plot_button(&self, plot: Plot) -> Element<'_, Message> {
        let (label, description, selected) = match plot {
            Plot::Waveform => ("1D", "1D waveform", self.config.view != "image"),
            Plot::Image => ("2D", "2D image", self.config.view != "waveform"),
        };
        let locked = self.args.duration > 0.0;
        let pending = self.pending_selection.is_some();
        let target = selection_target(&self.config.view, plot, locked, pending);
        let explanation = if locked {
            format!("{description} · Locked during a recorded run")
        } else if pending {
            format!("{description} · Updating shared source…")
        } else if target.is_none() {
            format!("{description} · Enable the other plot before hiding this one")
        } else {
            description.into()
        };
        let control = button(text(label).size(10))
            .padding([0, 8])
            .height(20)
            .width(38)
            .on_press_maybe(target.map(|_| Message::TogglePlot(plot)))
            .style(move |_, status| plot_button_style(selected, status));
        tooltip(
            control,
            text(explanation).size(11),
            tooltip::Position::Bottom,
        )
        .padding(8)
        .style(panel_style)
        .into()
    }
}

impl Drop for App {
    fn drop(&mut self) {
        self.readiness.close();
        self.preparing = None;
        self.finish_pending();
        self.record_geometry_metadata();
        let source_error = self
            .source
            .shared
            .lock()
            .unwrap()
            .status
            .starts_with("Error:");
        {
            let mut buffer = self.metrics.buffer.lock().unwrap();
            buffer.metadata["termination_reason"] =
                json!(if source_error || buffer.error.is_some() {
                    "error"
                } else {
                    self.termination_reason
                });
            buffer.metadata["active_seconds"] =
                json!(self.started.map_or(0.0, |s| s.elapsed().as_secs_f64()));
            buffer.metadata["telemetry_lost"] = json!(buffer.lost);
        }
        self.source.close();
        self.metrics.close();
    }
}

fn main() -> Result<()> {
    let args = Args::parse();
    ensure!(
        args.duration.is_finite() && args.duration >= 0.0,
        "Duration must be nonnegative and finite"
    );
    ensure!(
        args.width >= 860 && args.height >= 640,
        "Window must be at least 860 × 640 logical pixels"
    );
    let base = url::Url::parse(&args.url)?;
    ensure!(
        ["http", "https"].contains(&base.scheme()),
        "Server URL must use http or https"
    );
    let client = http_client()?;
    let config: Config = serde_json::from_slice(&read_limited(
        client
            .get(endpoint(&args.url, "/api/config")?)
            .send()
            .context("Cannot read shared source configuration; start plotbench serve first")?,
        1024 * 1024,
    )?)?;
    config
        .validate()
        .context("Invalid shared source configuration from /api/config")?;
    let palette: Vec<[u8; 3]> = serde_json::from_slice(&read_limited(
        client.get(endpoint(&args.url, "/api/colormap")?).send()?,
        1024 * 1024,
    )?)?;
    ensure!(
        palette.len() == 256,
        "Shared colormap must have exactly 256 RGB entries"
    );
    let size = Size::new(args.width as f32, args.height as f32);
    let palette = Arc::new(palette);
    iced::application(
        move || App::boot(args.clone(), config.clone(), palette.clone()),
        App::update,
        App::view,
    )
    .title("Plotbench · Iced 0.14 · custom Canvas + image")
    .subscription(App::subscription)
    .theme(Theme::custom(
        "Plotting Benchmark",
        iced::theme::Palette {
            background: BACKGROUND,
            text: PRIMARY,
            primary: ACCENT,
            success: ACCENT,
            warning: Color::from_rgb8(255, 211, 145),
            danger: ERROR,
        },
    ))
    .window(window::Settings {
        size,
        min_size: Some(Size::new(860.0, 640.0)),
        resizable: true,
        ..window::Settings::default()
    })
    .antialiasing(false)
    .exit_on_close_request(false)
    .run()?;
    Ok(())
}

fn save_screenshot(path: &std::path::Path, screenshot: &window::Screenshot) -> Result<()> {
    let file = std::fs::File::create(path)?;
    let mut encoder = png::Encoder::new(
        std::io::BufWriter::new(file),
        screenshot.size.width,
        screenshot.size.height,
    );
    encoder.set_color(png::ColorType::Rgba);
    encoder.set_depth(png::BitDepth::Eight);
    let mut writer = encoder.write_header()?;
    writer.write_image_data(&screenshot.rgba)?;
    writer.finish()?;
    Ok(())
}

fn panel_style(_theme: &Theme) -> container::Style {
    container::Style {
        background: Some(PANEL.into()),
        text_color: Some(PRIMARY),
        border: Border {
            color: BORDER,
            width: 1.0,
            radius: 12.0.into(),
        },
        ..container::Style::default()
    }
}

fn badge(label: &str, accent: bool) -> Element<'_, Message> {
    container(
        text(label)
            .size(11)
            .color(if accent { ACCENT } else { MUTED }),
    )
    .padding([6, 10])
    .style(move |_| container::Style {
        background: Some(if accent {
            Color::from_rgb8(22, 49, 48).into()
        } else {
            PANEL.into()
        }),
        border: Border {
            color: BORDER,
            width: 1.0,
            radius: 6.0.into(),
        },
        ..container::Style::default()
    })
    .into()
}

fn plot_card<'a>(
    title: String,
    subtitle: String,
    content: Element<'a, Message>,
) -> Element<'a, Message> {
    container(
        column![
            text(title).size(17).color(PRIMARY),
            text(subtitle).size(11).color(MUTED),
            content,
        ]
        .spacing(10),
    )
    .padding(18)
    .width(Fill)
    .height(Fill)
    .style(panel_style)
    .into()
}

fn workload_item(label: &str, value: String) -> Element<'_, Message> {
    column![
        text(label).size(9).color(MUTED),
        text(value).size(12).color(PRIMARY)
    ]
    .spacing(7)
    .width(Fill)
    .into()
}

const METRIC_GUIDE: &str = "Submitted counts adopted frames; images wait for allocation before adoption. Targets follow the active frame rate. Update time measures synchronous CPU preparation and adoption; it excludes allocation waiting, Canvas draw and display presentation. The one-period budget and receive-age goal are guides, not latency or displayed-FPS guarantees. Replay has no receive age.";

fn metric_target_hints(hz: Option<f64>, replay: bool) -> [String; 4] {
    let Some(hz) = hz else {
        return [
            "(waiting for source)".into(),
            "(waiting for source)".into(),
            "(target 0)".into(),
            if replay {
                "(N/A in replay)"
            } else {
                "(waiting for source)"
            }
            .into(),
        ];
    };
    let period = 1000.0 / hz;
    [
        format!("(target {hz}/s)"),
        format!("(budget ≤{period:.2} ms)"),
        "(target 0)".into(),
        if replay {
            "(N/A in replay)".into()
        } else {
            format!("(goal <{period:.2} ms)")
        },
    ]
}

fn metric_item<'a>(label: &'a str, value: &'a str, target: &'a str) -> Element<'a, Message> {
    tooltip(
        container(
            column![
                text(label).size(11).color(MUTED),
                text(value).size(25).color(PRIMARY),
                text(target).size(10).color(MUTED),
            ]
            .spacing(3)
            .width(Fill),
        )
        .padding([10, 18])
        .width(Fill)
        .height(88)
        .style(panel_style),
        text(METRIC_GUIDE).size(11).width(300),
        tooltip::Position::Bottom,
    )
    .style(panel_style)
    .into()
}

fn grouped_count(value: usize) -> String {
    let digits = value.to_string();
    let mut formatted = String::with_capacity(digits.len() + digits.len() / 3);
    for (index, digit) in digits.chars().enumerate() {
        if index > 0 && (digits.len() - index).is_multiple_of(3) {
            formatted.push(',');
        }
        formatted.push(digit);
    }
    formatted
}

fn source_button(_theme: &Theme, status: button::Status) -> button::Style {
    button::Style {
        background: Some(
            if matches!(status, button::Status::Hovered) {
                Color::from_rgb8(126, 233, 219)
            } else {
                ACCENT
            }
            .into(),
        ),
        text_color: BACKGROUND,
        border: Border {
            radius: 7.0.into(),
            ..Border::default()
        },
        ..button::Style::default()
    }
}

fn renderer_environment() -> serde_json::Value {
    [
        "ICED_PRESENT_MODE",
        "ICED_BACKEND",
        "ICED_RENDERER",
        "WGPU_BACKEND",
        "WGPU_ADAPTER_NAME",
    ]
    .into_iter()
    .map(|key| (key.to_owned(), json!(std::env::var(key).ok())))
    .collect::<serde_json::Map<String, serde_json::Value>>()
    .into()
}

fn build_provenance() -> serde_json::Value {
    json!({
        "source_revision":env!("PLOTBENCH_BUILD_REVISION"),
        "frontend_source_dirty":env!("PLOTBENCH_BUILD_DIRTY"),
        "cargo_lock_git_blob":env!("PLOTBENCH_BUILD_LOCK_GIT_BLOB"),
        "rustc":env!("PLOTBENCH_BUILD_COMPILER"),
        "note":"Embedded at compile time; lock identity is Git's blob hash. Binary identity is recorded by the harness; unavailable values are explicit."
    })
}

fn plot_button_style(selected: bool, status: button::Status) -> button::Style {
    let hovered = matches!(status, button::Status::Hovered);
    button::Style {
        background: Some(if selected {
            Color::from_rgb8(22, 49, 48).into()
        } else if hovered {
            BORDER.into()
        } else {
            BACKGROUND.into()
        }),
        text_color: if selected { ACCENT } else { MUTED },
        border: Border {
            color: if selected { ACCENT } else { BORDER },
            width: 1.0,
            radius: 4.0.into(),
        },
        ..button::Style::default()
    }
}

#[cfg(test)]
mod selection_tests {
    use super::*;

    fn config(view: &str, curves: usize, waveform_plots: usize, image_plots: usize) -> Config {
        serde_json::from_value(protocol::tests::config(
            view,
            10_000,
            curves,
            waveform_plots,
            (256, 256),
            image_plots,
            "scalar",
        ))
        .unwrap()
    }

    #[test]
    fn grid_columns_follow_the_shared_layout_rule() {
        let expected = [
            (1, (1, 1)),
            (2, (2, 1)),
            (3, (2, 2)),
            (4, (2, 2)),
            (5, (3, 2)),
            (6, (3, 2)),
            (7, (3, 3)),
            (8, (3, 3)),
            (9, (3, 3)),
        ];
        for (plots, shape) in expected {
            assert_eq!(grid_shape(plots), shape, "n = {plots}");
        }
        assert_eq!(grid_shape(0), (1, 1));
        assert_eq!(grid_shape(10), (4, 3));
        assert_eq!(grid_shape(16), (4, 4));
        assert_eq!(grid_shape(32), (6, 6));
        for plots in 1..=32 {
            let (columns, rows) = grid_shape(plots);
            assert_eq!(columns, (plots as f64).sqrt().ceil() as usize);
            assert_eq!(rows, plots.div_ceil(columns));
        }
    }

    #[test]
    fn curve_colours_match_the_shared_palette() {
        let expected = [
            "#64dccc", "#f5c76e", "#7aa6ff", "#ff9d7a", "#c39bff", "#9be564", "#ff7ab8", "#6ee7ff",
        ];
        let hex = |color: Color| {
            let channel = |value: f32| (value * 255.0).round() as u8;
            format!(
                "#{:02x}{:02x}{:02x}",
                channel(color.r),
                channel(color.g),
                channel(color.b)
            )
        };
        for (index, expected) in expected.iter().enumerate() {
            assert_eq!(hex(curve_color(index)), *expected);
            assert_eq!(hex(curve_color(index + 8)), *expected, "wraps at eight");
        }
        assert_eq!(hex(curve_color(0)), hex(ACCENT));
    }

    #[test]
    fn titles_and_workload_suffixes_follow_the_plot_counts() {
        assert_eq!(plot_title("Waveform", 0, 1), "Waveform");
        assert_eq!(plot_title("Waveform", 0, 2), "Waveform 1");
        assert_eq!(plot_title("Image", 2, 3), "Image 3");
        assert_eq!(
            workload_suffixes(&config("both", 1, 1, 1)),
            (String::new(), String::new())
        );
        assert_eq!(
            workload_suffixes(&config("both", 3, 2, 3)),
            (" · 2 plots × 3 curves".into(), " · 3 plots".into())
        );
        assert_eq!(
            workload_suffixes(&config("waveform", 4, 1, 1)).0,
            " · 1 plot × 4 curves"
        );
        assert_eq!(
            workload_suffixes(&config("waveform", 1, 4, 1)).0,
            " · 4 plots × 1 curve"
        );
        assert_eq!(
            workload_suffixes(&config("both", 1, 1, 2)),
            (String::new(), " · 2 plots".into())
        );
        assert_eq!(
            workload_suffixes(&config("image", 1, 1, 4)),
            (String::new(), " · 4 plots".into())
        );
    }

    #[test]
    fn visible_plot_counts_follow_the_view() {
        let both = config("both", 2, 3, 4);
        assert_eq!(
            (both.visible_waveform_plots(), both.visible_image_plots()),
            (3, 4)
        );
        let waveform = config("waveform", 2, 3, 4);
        assert_eq!(
            (
                waveform.visible_waveform_plots(),
                waveform.visible_image_plots()
            ),
            (3, 0)
        );
        let image = config("image", 2, 3, 4);
        assert_eq!(
            (image.visible_waveform_plots(), image.visible_image_plots()),
            (0, 4)
        );
    }

    #[test]
    fn metric_hints_follow_active_rate_and_replay_mode() {
        assert_eq!(metric_target_hints(None, false)[0], "(waiting for source)");
        assert_eq!(metric_target_hints(None, true)[3], "(N/A in replay)");
        let slow = metric_target_hints(Some(30.0), false);
        assert_eq!(
            slow,
            [
                "(target 30/s)",
                "(budget ≤33.33 ms)",
                "(target 0)",
                "(goal <33.33 ms)"
            ]
        );
        let fast = metric_target_hints(Some(120.0), false);
        assert_eq!(fast[0], "(target 120/s)");
        assert_eq!(fast[1], "(budget ≤8.33 ms)");
        assert_eq!(fast[3], "(goal <8.33 ms)");
        let replay = metric_target_hints(Some(59.94), true);
        assert_eq!(replay[0], "(target 59.94/s)");
        assert_eq!(replay[1], "(budget ≤16.68 ms)");
        assert_eq!(replay[3], "(N/A in replay)");
    }

    #[test]
    fn toggles_each_plot_without_allowing_an_empty_view() {
        assert_eq!(
            selection_target("both", Plot::Waveform, false, false),
            Some("image")
        );
        assert_eq!(
            selection_target("both", Plot::Image, false, false),
            Some("waveform")
        );
        assert_eq!(
            selection_target("image", Plot::Waveform, false, false),
            Some("both")
        );
        assert_eq!(
            selection_target("waveform", Plot::Image, false, false),
            Some("both")
        );
        assert_eq!(
            selection_target("waveform", Plot::Waveform, false, false),
            None
        );
        assert_eq!(selection_target("image", Plot::Image, false, false), None);
    }

    #[test]
    fn recorded_runs_and_pending_changes_reject_toggles() {
        for plot in [Plot::Waveform, Plot::Image] {
            assert_eq!(selection_target("both", plot, true, false), None);
            assert_eq!(selection_target("both", plot, false, true), None);
        }
    }
}
