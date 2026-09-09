use crate::{
    config::{Config, MAX_PAYLOAD},
    generator::{Packet, colormap, make_packet, now_ms},
};
use anyhow::{Context, Result, ensure};
use axum::{
    Json, Router,
    body::{Body, Bytes},
    extract::{
        DefaultBodyLimit, Query, State, WebSocketUpgrade,
        ws::{CloseFrame, Message, WebSocket},
    },
    http::{StatusCode, header},
    response::{Html, IntoResponse, Response},
    routing::{get, post},
};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, HashMap},
    fs::{File, OpenOptions},
    io::Write,
    path::PathBuf,
    sync::{
        Arc, Condvar, Mutex, RwLock,
        atomic::{AtomicBool, AtomicU64, Ordering},
    },
    thread,
    time::{Duration, Instant},
};
use tokio::sync::{Notify, Semaphore, mpsc, watch};
use tokio_stream::wrappers::ReceiverStream;
use tower_http::cors::CorsLayer;

pub const RUNTIME_VERSION: &str = "1.53.1";
pub const HTTP_VERSION: &str = "0.8.9";

#[derive(Default)]
struct Mailbox {
    latest: Mutex<Option<Packet>>,
    changed: Notify,
}

impl Mailbox {
    fn publish(&self, packet: Packet) -> bool {
        let replaced = self.latest.lock().unwrap().replace(packet).is_some();
        self.changed.notify_one();
        replaced
    }

    fn take(&self) -> Option<Packet> {
        self.latest.lock().unwrap().take()
    }
}

#[derive(Default)]
struct Stats {
    generated: u64,
    deadline_misses: u64,
    mailbox_drops: u64,
    acknowledgements: u64,
    error: Option<String>,
}

pub struct Source {
    config: RwLock<Config>,
    clients: Mutex<BTreeMap<u64, Arc<Mailbox>>>,
    next_client: AtomicU64,
    stats: Mutex<Stats>,
    output: PathBuf,
    controls: String,
    metrics: Mutex<File>,
    running: AtomicBool,
    wake: Condvar,
    wake_lock: Mutex<()>,
    shutdown: watch::Sender<bool>,
    jobs: Arc<Semaphore>,
    replay_lock: Arc<Semaphore>,
}

pub struct RunningSource {
    pub state: Arc<Source>,
    producer: Option<thread::JoinHandle<()>>,
}

impl Source {
    pub fn shutdown_receiver(&self) -> watch::Receiver<bool> {
        self.shutdown.subscribe()
    }

    pub fn request_shutdown(&self) {
        self.running.store(false, Ordering::Relaxed);
        self.shutdown.send_replace(true);
        self.wake.notify_all();
    }
}

impl RunningSource {
    pub fn start(config: Config, output: PathBuf, controls: String) -> Result<Self> {
        config.validate()?;
        std::fs::create_dir_all(&output)?;
        let output = output.canonicalize()?;
        let metrics = OpenOptions::new()
            .create(true)
            .append(true)
            .open(output.join("measurements.jsonl"))?;
        let source_file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(output.join("source.jsonl"))?;
        write_host(&output, &config)?;
        let (shutdown, _) = watch::channel(false);
        let state = Arc::new(Source {
            config: RwLock::new(config),
            clients: Mutex::new(BTreeMap::new()),
            next_client: AtomicU64::new(1),
            stats: Mutex::new(Stats::default()),
            output,
            controls,
            metrics: Mutex::new(metrics),
            running: AtomicBool::new(true),
            wake: Condvar::new(),
            wake_lock: Mutex::new(()),
            shutdown,
            jobs: Arc::new(Semaphore::new(2)),
            replay_lock: Arc::new(Semaphore::new(1)),
        });
        let producer_state = state.clone();
        let producer = thread::Builder::new()
            .name("plotbench-generation".into())
            .spawn(move || producer(producer_state, source_file))?;
        Ok(Self {
            state,
            producer: Some(producer),
        })
    }

    pub fn stop(&mut self) {
        self.state.request_shutdown();
        if let Some(producer) = self.producer.take() {
            let _ = producer.join();
        }
    }
}

impl Drop for RunningSource {
    fn drop(&mut self) {
        self.stop();
    }
}

fn producer(source: Arc<Source>, mut file: File) {
    let epoch = Instant::now();
    let mut generation = source.config.read().unwrap().generation;
    let mut seq = 0_u64;
    let mut deadline = 0.0;
    while source.running.load(Ordering::Relaxed) {
        if source.clients.lock().unwrap().is_empty() {
            let guard = source.wake_lock.lock().unwrap();
            let _ = source
                .wake
                .wait_timeout(guard, Duration::from_millis(25))
                .unwrap();
            deadline = epoch.elapsed().as_secs_f64();
            continue;
        }
        let config = source.config.read().unwrap().clone();
        if config.generation != generation {
            generation = config.generation;
            seq = 0;
            deadline = epoch.elapsed().as_secs_f64();
        }
        let started = Instant::now();
        let result = make_packet(&config, seq).and_then(|packet| {
            if source.config.read().unwrap().generation != generation {
                return Ok(false);
            }
            let packet_bytes = packet.bytes.len();
            let drops = source
                .clients
                .lock()
                .unwrap()
                .values()
                .filter(|mailbox| mailbox.publish(packet.clone()))
                .count() as u64;
            let generation_ms = started.elapsed().as_secs_f64() * 1000.0;
            let (deadline_misses_total, acknowledgements_total) = {
                let stats = source.stats.lock().unwrap();
                (stats.deadline_misses, stats.acknowledgements)
            };
            let line = json!({"time_ms":now_ms(),"seq":seq,"generation":generation,
                "generation_ms":generation_ms,"packet_bytes":packet_bytes,
                "deadline_misses_total":deadline_misses_total,
                "acknowledgements_total":acknowledgements_total,
                "clients":source.clients.lock().unwrap().len(),
                "mailbox_drops":drops,"target_hz":config.hz});
            serde_json::to_writer(&mut file, &line)?;
            file.write_all(b"\n")?;
            let mut stats = source.stats.lock().unwrap();
            stats.generated = stats.generated.saturating_add(1);
            stats.mailbox_drops = stats.mailbox_drops.saturating_add(drops);
            stats.error = None;
            Ok(true)
        });
        match result {
            Ok(false) => continue,
            Err(error) => {
                source.stats.lock().unwrap().error = Some(format!("{error:#}"));
                let guard = source.wake_lock.lock().unwrap();
                let _ = source
                    .wake
                    .wait_timeout(guard, Duration::from_secs(1))
                    .unwrap();
                continue;
            }
            Ok(true) => {}
        }
        let Some(next) = seq.checked_add(1) else {
            source.stats.lock().unwrap().error = Some("sequence exhausted u64".into());
            break;
        };
        seq = next;
        deadline += 1.0 / config.hz;
        let now = epoch.elapsed().as_secs_f64();
        if deadline < now {
            let missed = ((now - deadline) * config.hz).floor() as u64 + 1;
            source.stats.lock().unwrap().deadline_misses += missed;
            let Some(next) = seq.checked_add(missed) else {
                break;
            };
            seq = next;
            deadline += missed as f64 / config.hz;
        }
        let mut guard = source.wake_lock.lock().unwrap();
        while source.running.load(Ordering::Relaxed)
            && source.config.read().unwrap().generation == generation
            && epoch.elapsed().as_secs_f64() < deadline
        {
            let remaining = (deadline - epoch.elapsed().as_secs_f64()).clamp(0.0, 0.25);
            guard = source
                .wake
                .wait_timeout(guard, Duration::from_secs_f64(remaining))
                .unwrap()
                .0;
        }
    }
}

struct ApiError(StatusCode, String);
impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (self.0, Json(json!({"error":self.1}))).into_response()
    }
}
impl From<anyhow::Error> for ApiError {
    fn from(error: anyhow::Error) -> Self {
        Self(StatusCode::BAD_REQUEST, format!("{error:#}"))
    }
}
fn internal(error: impl std::fmt::Display) -> ApiError {
    ApiError(StatusCode::INTERNAL_SERVER_ERROR, error.to_string())
}

async fn wait_shutdown(receiver: &mut watch::Receiver<bool>) {
    // Discard the watch borrow before a select branch can reuse the receiver.
    let _ = receiver.wait_for(|stopped| *stopped).await;
}

async fn acquire_job(
    source: &Source,
    semaphore: Arc<Semaphore>,
) -> Result<tokio::sync::OwnedSemaphorePermit, ApiError> {
    let mut shutdown = source.shutdown.subscribe();
    let permit = tokio::select! {
        _ = wait_shutdown(&mut shutdown) => return Err(ApiError(StatusCode::SERVICE_UNAVAILABLE,"Source is stopping".into())),
        permit = semaphore.acquire_owned() => permit.map_err(internal)?,
    };
    if !source.running.load(Ordering::Relaxed) {
        return Err(ApiError(
            StatusCode::SERVICE_UNAVAILABLE,
            "Source is stopping".into(),
        ));
    }
    Ok(permit)
}

pub fn app(source: Arc<Source>) -> Router {
    Router::new()
        .route("/", get(controls))
        .route("/ws", get(websocket))
        .route("/api/config", get(get_config).post(set_config))
        .route("/api/health", get(health))
        .route("/api/frame", get(frame))
        .route("/api/replay", get(replay))
        .route("/api/metrics", post(metrics))
        .route("/api/colormap", get(|| async { Json(colormap()) }))
        .layer(DefaultBodyLimit::max(32 * 1024 * 1024))
        .layer(CorsLayer::permissive())
        .with_state(source)
}

async fn controls(State(source): State<Arc<Source>>) -> Html<String> {
    Html(source.controls.clone())
}
async fn get_config(State(source): State<Arc<Source>>) -> Json<Config> {
    Json(source.config.read().unwrap().clone())
}

async fn set_config(
    State(source): State<Arc<Source>>,
    body: Bytes,
) -> Result<Json<Config>, ApiError> {
    let patch = serde_json::from_slice(&body)
        .map_err(|e| ApiError(StatusCode::BAD_REQUEST, e.to_string()))?;
    let updated = {
        let mut config = source.config.write().unwrap();
        let updated = config.updated(patch)?;
        *config = updated.clone();
        updated
    };
    source.wake.notify_all();
    Ok(Json(updated))
}

async fn health(State(source): State<Arc<Source>>) -> Json<Value> {
    let config = source.config.read().unwrap().clone();
    let clients = source.clients.lock().unwrap().len();
    let stats = source.stats.lock().unwrap();
    Json(
        json!({"status":if stats.error.is_none(){"ok"}else{"error"},"error":stats.error,
        "generated":stats.generated,"deadline_misses":stats.deadline_misses,"mailbox_drops":stats.mailbox_drops,
        "acknowledgements":stats.acknowledgements,
        "clients":clients,"output":source.output,"config":config,"backend":"rust","version":env!("CARGO_PKG_VERSION"),
        "runtime":"tokio","runtime_version":RUNTIME_VERSION,"http_framework":"axum","http_framework_version":HTTP_VERSION}),
    )
}

async fn frame(
    State(source): State<Arc<Source>>,
    Query(query): Query<HashMap<String, String>>,
) -> Result<Response, ApiError> {
    let seq: u64 = query.get("seq").map_or(Ok(0), |s| s.parse()).map_err(|_| {
        ApiError(
            StatusCode::BAD_REQUEST,
            "seq must be a nonnegative u64 integer".into(),
        )
    })?;
    let config = source.config.read().unwrap().clone();
    let permit = acquire_job(&source, source.jobs.clone()).await?;
    let packet = tokio::task::spawn_blocking(move || {
        let _permit = permit;
        make_packet(&config, seq)
    })
    .await
    .map_err(internal)?
    .map_err(internal)?;
    Ok((
        [(header::CONTENT_TYPE, "application/octet-stream")],
        packet.bytes,
    )
        .into_response())
}

async fn replay(
    State(source): State<Arc<Source>>,
    Query(query): Query<HashMap<String, String>>,
) -> Result<Response, ApiError> {
    let requested: usize = query
        .get("count")
        .map_or(Ok(16), |s| s.parse())
        .map_err(|_| ApiError(StatusCode::BAD_REQUEST, "invalid replay count".into()))?;
    if !(2..=256).contains(&requested) {
        return Err(ApiError(
            StatusCode::BAD_REQUEST,
            "replay count must be between 2 and 256".into(),
        ));
    }
    let replay_permit = acquire_job(&source, source.replay_lock.clone()).await?;
    let config = source.config.read().unwrap().clone();
    let count = requested.min((MAX_PAYLOAD - 4) / (config.payload_bytes() + 4096));
    if count < 2 {
        return Err(ApiError(
            StatusCode::BAD_REQUEST,
            "replay needs at least two frames within 256 MiB; reduce the dimensions".into(),
        ));
    }
    let permit = acquire_job(&source, source.jobs.clone()).await?;
    let (sender, receiver) = mpsc::channel::<Result<Bytes, std::io::Error>>(1);
    let mut shutdown = source.shutdown.subscribe();
    tokio::spawn(async move {
        let (_permit, _replay_permit) = (permit, replay_permit);
        let send = |chunk| async { sender.send(chunk).await.is_ok() };
        let prefix = Ok(Bytes::copy_from_slice(&(count as u32).to_le_bytes()));
        if !tokio::select! { ok = send(prefix) => ok, _=wait_shutdown(&mut shutdown)=>false } {
            return;
        }
        for seq in 0..count {
            let current = config.clone();
            let work = tokio::task::spawn_blocking(move || make_packet(&current, seq as u64));
            let result =
                tokio::select! { result = work => result, _=wait_shutdown(&mut shutdown)=>return };
            let packet = match result {
                Ok(Ok(packet)) => packet,
                error => {
                    let error = Err(std::io::Error::other(format!(
                        "Replay generation failed: {error:?}"
                    )));
                    tokio::select! { _ = sender.send(error) => {}, _=wait_shutdown(&mut shutdown)=>{} }
                    return;
                }
            };
            for chunk in [
                Bytes::copy_from_slice(&(packet.bytes.len() as u32).to_le_bytes()),
                packet.bytes,
            ] {
                if !tokio::select! { ok = send(Ok(chunk)) => ok, _=wait_shutdown(&mut shutdown)=>false }
                {
                    return;
                }
            }
        }
    });
    Ok((
        [(header::CONTENT_TYPE, "application/octet-stream")],
        Body::from_stream(ReceiverStream::new(receiver)),
    )
        .into_response())
}

pub fn validate_batch(batch: &Value) -> Result<usize> {
    ensure!(batch.is_object(), "measurement batch must be an object");
    for key in ["frontend", "run_id", "mode"] {
        ensure!(
            batch
                .get(key)
                .and_then(Value::as_str)
                .is_some_and(|v| (1..=256).contains(&v.chars().count())),
            "invalid {key}"
        );
    }
    ensure!(
        ["stream", "replay"].contains(&batch["mode"].as_str().unwrap()),
        "unknown measurement mode"
    );
    let samples = batch
        .get("samples")
        .and_then(Value::as_array)
        .context("invalid sample batch")?;
    ensure!(samples.len() <= 20_000, "invalid sample batch");
    for sample in samples {
        for key in ["seq", "generation", "skipped"] {
            ensure!(
                sample.get(key).and_then(Value::as_u64).is_some(),
                "invalid sample {key}"
            );
        }
        for key in ["client_time_ms", "update_ms"] {
            ensure!(
                sample
                    .get(key)
                    .and_then(Value::as_f64)
                    .is_some_and(f64::is_finite),
                "invalid sample {key}"
            );
        }
        ensure!(
            sample["update_ms"].as_f64().unwrap() >= 0.0,
            "negative update duration"
        );
        for key in [
            "receive_age_ms",
            "conversion_ms",
            "draw_ms",
            "update_complete_ms",
            "image_upload_wait_ms",
        ] {
            if let Some(value) = sample.get(key).filter(|value| !value.is_null()) {
                ensure!(
                    value
                        .as_f64()
                        .is_some_and(|v| v.is_finite() && (key == "receive_age_ms" || v >= 0.0)),
                    "invalid sample {key}"
                );
            }
        }
    }
    Ok(samples.len())
}

async fn metrics(State(source): State<Arc<Source>>, body: Bytes) -> Result<Json<Value>, ApiError> {
    let permit = acquire_job(&source, source.jobs.clone()).await?;
    let count = tokio::task::spawn_blocking(move || -> Result<usize, ApiError> {
        let _permit = permit;
        let mut batch: Value = serde_json::from_slice(&body)
            .map_err(|error| ApiError(StatusCode::BAD_REQUEST, error.to_string()))?;
        let count = validate_batch(&batch)?;
        batch["received_at_ms"] = json!(now_ms());
        let mut bytes = serde_json::to_vec(&batch).map_err(internal)?;
        bytes.push(b'\n');
        source
            .metrics
            .lock()
            .unwrap()
            .write_all(&bytes)
            .map_err(internal)?;
        Ok(count)
    })
    .await
    .map_err(internal)??;
    Ok(Json(json!({"accepted":count})))
}

async fn websocket(State(source): State<Arc<Source>>, upgrade: WebSocketUpgrade) -> Response {
    upgrade
        .max_message_size(4096)
        .max_frame_size(4096)
        .on_upgrade(move |socket| connection(source, socket))
}

fn matching_ack(text: &str, outstanding: Option<(u64, u64)>) -> Result<bool, serde_json::Error> {
    let ack: Value = serde_json::from_str(text)?;
    Ok(outstanding.is_some_and(|(seq, generation)| {
        ack.get("ack").and_then(Value::as_u64) == Some(seq)
            && ack.get("generation").and_then(Value::as_u64) == Some(generation)
    }))
}

async fn connection(source: Arc<Source>, mut socket: WebSocket) {
    let mailbox = Arc::new(Mailbox::default());
    let id = source.next_client.fetch_add(1, Ordering::Relaxed);
    source.clients.lock().unwrap().insert(id, mailbox.clone());
    source.wake.notify_all();
    let mut shutdown = source.shutdown.subscribe();
    let mut outstanding = None;
    let mut heartbeat_deadline = tokio::time::Instant::now() + Duration::from_secs(20);
    let mut awaiting_liveness = false;
    loop {
        tokio::select! {
            _ = wait_shutdown(&mut shutdown) => break,
            message = socket.recv() => {
                // Match aiohttp: incoming activity resets the idle heartbeat and
                // its response timeout. ACKs and control frames establish liveness.
                heartbeat_deadline = tokio::time::Instant::now() + Duration::from_secs(20);
                awaiting_liveness = false;
                match message {
                Some(Ok(Message::Text(text))) => match matching_ack(&text, outstanding) {
                    Ok(true) => {
                        outstanding = None;
                        source.stats.lock().unwrap().acknowledgements += 1;
                    },
                    Ok(false) => {},
                    Err(_) => {
                        let close = Message::Close(Some(CloseFrame{code:1003,reason:"Expected a JSON frame acknowledgement".into()}));
                        tokio::select! { _=socket.send(close)=>{}, _=wait_shutdown(&mut shutdown)=>{} }
                        break;
                    }
                },
                Some(Ok(Message::Close(_))) | Some(Err(_)) | None => break,
                _ => {},
                }
            },
            _ = mailbox.changed.notified(), if outstanding.is_none() => {
                if let Some(packet) = mailbox.take() {
                    outstanding = Some((packet.seq,packet.generation));
                    let sent = tokio::select! {
                        result = socket.send(Message::Binary(packet.bytes)) => result.is_ok(),
                        _ = wait_shutdown(&mut shutdown) => false,
                    };
                    if !sent { break; }
                }
            },
            _ = tokio::time::sleep_until(heartbeat_deadline) => {
                if awaiting_liveness { break; }
                let sent = tokio::select! {
                    result=socket.send(Message::Ping(Bytes::new()))=>result.is_ok(),
                    _=wait_shutdown(&mut shutdown)=>false,
                };
                if !sent { break; }
                awaiting_liveness = true;
                heartbeat_deadline = tokio::time::Instant::now() + Duration::from_secs(10);
            },
        }
    }
    source.clients.lock().unwrap().remove(&id);
    source.wake.notify_all();
}

fn command_output(command: &str, args: &[&str]) -> Option<String> {
    let output = std::process::Command::new(command)
        .args(args)
        .output()
        .ok()?;
    output
        .status
        .success()
        .then(|| String::from_utf8_lossy(&output.stdout).trim().to_owned())
}

fn write_host(output: &std::path::Path, config: &Config) -> Result<()> {
    let mut host = json!({"recorded_at_ms":now_ms(),"platform":command_output("uname", &["-srm"]).unwrap_or_else(||std::env::consts::OS.into()),
        "machine":std::env::consts::ARCH,"logical_cpus":thread::available_parallelism().map(|n|n.get()).ok(),
        "physical_cpus":null,"memory_bytes":null,"backend":"rust","backend_version":env!("CARGO_PKG_VERSION"),
        "rustc":env!("PLOTBENCH_RUSTC_VERSION"),"runtime":"tokio","runtime_version":RUNTIME_VERSION,
        "http_framework":"axum","http_framework_version":HTTP_VERSION,"config":config,
        "generation_strategy":"fresh deterministic native generation; separable image trig; fused row-major payload writes; dedicated thread",
        "numeric_policy":"f32 replace/image arithmetic; f64 append arithmetic; native libm, numerical tolerance applies"});
    host["emitted_at_boundary"] =
        json!("payload packed; before JSON header serialization/insertion");
    host["generation_boundary"] = json!(
        "generation, packing and mailbox publication on dedicated thread; excludes JSONL write"
    );
    host["heartbeat_policy"] = json!(
        "20 seconds receive-idle then ping; 10 seconds response timeout; inbound activity resets"
    );
    host["tcp_nodelay"] = json!(true);
    if cfg!(target_os = "macos") {
        host["cpu_model"] = json!(command_output(
            "sysctl",
            &["-n", "machdep.cpu.brand_string"]
        ));
        host["physical_cpus"] = json!(
            command_output("sysctl", &["-n", "hw.physicalcpu"]).and_then(|s| s.parse::<u64>().ok())
        );
        host["memory_bytes"] = json!(
            command_output("sysctl", &["-n", "hw.memsize"]).and_then(|s| s.parse::<u64>().ok())
        );
    } else if cfg!(target_os = "linux") {
        let data = linux_host_metadata(
            &std::fs::read_to_string("/proc/cpuinfo").unwrap_or_default(),
            &std::fs::read_to_string("/proc/meminfo").unwrap_or_default(),
            &std::fs::read_to_string("/etc/os-release").unwrap_or_default(),
        );
        for (key, value) in data.as_object().unwrap() {
            host[key] = value.clone();
        }
        host["display_session"] = json!({
            "session_type":std::env::var("XDG_SESSION_TYPE").ok(),
            "desktop":std::env::var("XDG_CURRENT_DESKTOP").ok(),
        });
    }
    let mut bytes = serde_json::to_vec_pretty(&host)?;
    bytes.push(b'\n');
    std::fs::write(output.join("host.json"), bytes)?;
    Ok(())
}

fn linux_host_metadata(cpuinfo: &str, meminfo: &str, os_release: &str) -> Value {
    let mut cores = std::collections::HashSet::new();
    let mut model = None;
    for processor in cpuinfo.split("\n\n") {
        let fields: std::collections::HashMap<_, _> = processor
            .lines()
            .filter_map(|line| line.split_once(':'))
            .map(|(key, value)| (key.trim(), value.trim()))
            .collect();
        model = model.or_else(|| fields.get("model name").copied());
        if let (Some(package), Some(core)) = (fields.get("physical id"), fields.get("core id")) {
            cores.insert((*package, *core));
        }
    }
    let memory = meminfo.lines().find_map(|line| {
        let value = line.strip_prefix("MemTotal:")?;
        let mut fields = value.split_whitespace();
        let kib = fields.next()?.parse::<u64>().ok()?;
        (fields.next()? == "kB")
            .then(|| kib.checked_mul(1024))
            .flatten()
    });
    let release: std::collections::HashMap<_, _> = os_release
        .lines()
        .filter_map(|line| line.split_once('='))
        .map(|(key, value)| (key, value.trim_matches('"')))
        .collect();
    json!({"cpu_model":model,"memory_bytes":memory,
        "physical_cpus":if cores.is_empty() { None } else { Some(cores.len()) },
        "os":{"name":release.get("NAME").copied().unwrap_or("Linux"),
              "version":release.get("VERSION_ID")}})
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{body::to_bytes, http::Request};
    use futures_util::{SinkExt, StreamExt};
    use tower::ServiceExt;

    #[test]
    fn linux_hardware_is_nonidentifying_and_missing_values_stay_null() {
        let cpu = "model name : Example CPU\nphysical id : 0\ncore id : 0\n\nphysical id : 0\ncore id : 0\n\nphysical id : 0\ncore id : 1\n";
        let host = linux_host_metadata(
            cpu,
            "MemTotal: 1024 kB\n",
            "NAME=\"Example Linux\"\nVERSION_ID=\"9\"\n",
        );
        assert_eq!(host["physical_cpus"], 2);
        assert_eq!(host["memory_bytes"], 1048576);
        assert_eq!(host["cpu_model"], "Example CPU");
        assert_eq!(host["os"]["name"], "Example Linux");
        let missing = linux_host_metadata("", "", "");
        assert!(missing["cpu_model"].is_null());
        assert!(missing["physical_cpus"].is_null());
        assert!(missing["memory_bytes"].is_null());
        assert_eq!(missing["os"]["name"], "Linux");
    }

    #[test]
    fn optional_stage_timings_are_nonnegative_and_nullable() {
        let base = json!({"frontend":"test","run_id":"test","mode":"stream",
            "samples":[{"seq":0,"generation":0,"skipped":0,"client_time_ms":1.0,"update_ms":0.2,
            "receive_age_ms":-0.1}]});
        for field in [
            "conversion_ms",
            "draw_ms",
            "update_complete_ms",
            "image_upload_wait_ms",
        ] {
            for valid in [Value::Null, json!(0.0), json!(2.5)] {
                let mut batch = base.clone();
                batch["samples"][0][field] = valid;
                assert!(validate_batch(&batch).is_ok());
            }
            for invalid in [json!(-1), json!(true), json!("1")] {
                let mut batch = base.clone();
                batch["samples"][0][field] = invalid;
                assert!(validate_batch(&batch).is_err(), "accepted invalid {field}");
            }
        }
    }

    #[test]
    fn credit_requires_exact_sequence_and_generation() {
        assert!(matching_ack(r#"{"ack":3,"generation":7}"#, Some((3, 7))).unwrap());
        for value in [
            r#"{"ack":3,"generation":8}"#,
            r#"{"ack":2,"generation":7}"#,
            r#"{"ack":true,"generation":7}"#,
            "[]",
        ] {
            assert!(!matching_ack(value, Some((3, 7))).unwrap());
        }
        assert!(matching_ack("broken", Some((3, 7))).is_err());
    }

    #[tokio::test]
    async fn config_errors_are_atomic_and_metrics_validate_before_writing() {
        let dir = tempfile::tempdir().unwrap();
        let running =
            RunningSource::start(Config::default(), dir.path().into(), "test controls".into())
                .unwrap();
        let router = app(running.state.clone());
        let bad = Request::post("/api/config")
            .body(Body::from(r#"{"view":"image","generation":4}"#))
            .unwrap();
        assert_eq!(
            router.clone().oneshot(bad).await.unwrap().status(),
            StatusCode::BAD_REQUEST
        );
        assert_eq!(running.state.config.read().unwrap().view, "both");
        let valid = json!({"frontend":"test","run_id":"test","mode":"stream","samples":[{"seq":0,"generation":0,"skipped":0,"client_time_ms":1.0,"update_ms":0.2}]});
        let mut invalid = valid.clone();
        invalid["samples"][0]["seq"] = json!(-1);
        let bad = Request::post("/api/metrics")
            .body(Body::from(invalid.to_string()))
            .unwrap();
        assert_eq!(
            router.clone().oneshot(bad).await.unwrap().status(),
            StatusCode::BAD_REQUEST
        );
        assert_eq!(
            std::fs::metadata(dir.path().join("measurements.jsonl"))
                .unwrap()
                .len(),
            0
        );
        let response = router
            .oneshot(
                Request::post("/api/metrics")
                    .body(Body::from(valid.to_string()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            serde_json::from_slice::<Value>(&to_bytes(response.into_body(), 1024).await.unwrap())
                .unwrap()["accepted"],
            1
        );
        let stored: Value = serde_json::from_str(
            std::fs::read_to_string(dir.path().join("measurements.jsonl"))
                .unwrap()
                .trim(),
        )
        .unwrap();
        assert!(stored["received_at_ms"].as_f64().unwrap() > 0.0);
    }

    #[tokio::test]
    async fn frame_and_replay_follow_config_and_replay_framing() {
        let dir = tempfile::tempdir().unwrap();
        let running = RunningSource::start(
            Config {
                points: 13,
                append_count: 3,
                width: 3,
                height: 2,
                ..Config::default()
            },
            dir.path().into(),
            "controls".into(),
        )
        .unwrap();
        let router = app(running.state.clone());
        let response = router
            .clone()
            .oneshot(
                Request::post("/api/config")
                    .body(Body::from(r#"{"view":"image"}"#))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let response = router
            .clone()
            .oneshot(
                Request::get("/api/frame?seq=7")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        let bytes = to_bytes(response.into_body(), 16_384).await.unwrap();
        let length = u32::from_le_bytes(bytes[..4].try_into().unwrap()) as usize;
        let header: Value = serde_json::from_slice(&bytes[4..4 + length]).unwrap();
        assert_eq!(header["seq"], 7);
        assert_eq!(header["generation"], 1);
        assert_eq!(header["arrays"].as_array().unwrap().len(), 1);
        assert_eq!(header["arrays"][0]["name"], "image");
        let response = router
            .clone()
            .oneshot(
                Request::get("/api/replay?count=3")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        let bytes = to_bytes(response.into_body(), 16_384).await.unwrap();
        assert_eq!(u32::from_le_bytes(bytes[..4].try_into().unwrap()), 3);
        let mut cursor = 4;
        let mut payloads = Vec::new();
        for seq in 0..3 {
            let length = u32::from_le_bytes(bytes[cursor..cursor + 4].try_into().unwrap()) as usize;
            cursor += 4;
            let packet = &bytes[cursor..cursor + length];
            let header_length = u32::from_le_bytes(packet[..4].try_into().unwrap()) as usize;
            let header: Value = serde_json::from_slice(&packet[4..4 + header_length]).unwrap();
            assert_eq!(header["seq"], seq);
            assert_eq!(header["generation"], 1);
            payloads.push(packet[(header_length + 7) & !3..].to_vec());
            cursor += length;
        }
        assert_eq!(cursor, bytes.len());
        assert_ne!(payloads[0], payloads[1]);
        assert_ne!(payloads[1], payloads[2]);
        let response = router
            .oneshot(
                Request::get("/api/replay?count=1")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn shutdown_cancels_queued_replays_and_rejects_late_requests() {
        let dir = tempfile::tempdir().unwrap();
        let mut running =
            RunningSource::start(Config::default(), dir.path().into(), "".into()).unwrap();
        let held_jobs = running
            .state
            .jobs
            .clone()
            .acquire_many_owned(2)
            .await
            .unwrap();
        let router = app(running.state.clone());
        let first = tokio::spawn(
            router
                .clone()
                .oneshot(Request::get("/api/replay").body(Body::empty()).unwrap()),
        );
        tokio::time::timeout(Duration::from_secs(1), async {
            while running.state.replay_lock.available_permits() != 0 {
                tokio::task::yield_now().await;
            }
        })
        .await
        .unwrap();
        let second = tokio::spawn(
            router
                .clone()
                .oneshot(Request::get("/api/replay").body(Body::empty()).unwrap()),
        );
        tokio::task::yield_now().await;
        running.state.request_shutdown();
        for task in [first, second] {
            let response = tokio::time::timeout(Duration::from_secs(1), task)
                .await
                .unwrap()
                .unwrap()
                .unwrap();
            assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
        }
        drop(held_jobs);
        let response = tokio::time::timeout(
            Duration::from_secs(1),
            router.oneshot(Request::get("/api/replay").body(Body::empty()).unwrap()),
        )
        .await
        .unwrap()
        .unwrap();
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
        running.stop();
    }

    #[tokio::test]
    async fn shutdown_releases_stalled_replay_producer() {
        let dir = tempfile::tempdir().unwrap();
        let mut running = RunningSource::start(
            Config {
                points: 512,
                append_count: 16,
                width: 16,
                height: 16,
                ..Config::default()
            },
            dir.path().into(),
            "".into(),
        )
        .unwrap();
        let response = app(running.state.clone())
            .oneshot(Request::get("/api/replay").body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        // Keep the body unread so its single-chunk delivery channel fills.
        assert_eq!(running.state.replay_lock.available_permits(), 0);
        running.state.request_shutdown();
        tokio::time::timeout(Duration::from_secs(1), async {
            while running.state.replay_lock.available_permits() != 1
                || running.state.jobs.available_permits() != 2
            {
                tokio::task::yield_now().await;
            }
        })
        .await
        .unwrap();
        drop(response);
        running.stop();
    }

    #[tokio::test]
    async fn websocket_waits_for_ack_then_sends_latest_and_cleans_up() {
        let dir = tempfile::tempdir().unwrap();
        let mut running = RunningSource::start(
            Config {
                hz: 120.0,
                points: 32,
                append_count: 4,
                width: 4,
                height: 3,
                ..Config::default()
            },
            dir.path().into(),
            "".into(),
        )
        .unwrap();
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let router = app(running.state.clone());
        let task = tokio::spawn(async move {
            axum::serve(listener, router).await.unwrap();
        });
        let (mut socket, _) = tokio_tungstenite::connect_async(format!("ws://{addr}/ws"))
            .await
            .unwrap();
        let first = tokio::time::timeout(Duration::from_secs(2), socket.next())
            .await
            .unwrap()
            .unwrap()
            .unwrap()
            .into_data();
        let len = u32::from_le_bytes(first[..4].try_into().unwrap()) as usize;
        let header: Value = serde_json::from_slice(&first[4..4 + len]).unwrap();
        assert!(
            tokio::time::timeout(Duration::from_millis(75), socket.next())
                .await
                .is_err()
        );
        socket
            .send(tokio_tungstenite::tungstenite::Message::Text(
                json!({"ack":header["seq"],"generation":999})
                    .to_string()
                    .into(),
            ))
            .await
            .unwrap();
        assert!(
            tokio::time::timeout(Duration::from_millis(25), socket.next())
                .await
                .is_err()
        );
        socket
            .send(tokio_tungstenite::tungstenite::Message::Text(
                json!({"ack":header["seq"],"generation":header["generation"]})
                    .to_string()
                    .into(),
            ))
            .await
            .unwrap();
        let second = tokio::time::timeout(Duration::from_secs(2), socket.next())
            .await
            .unwrap()
            .unwrap()
            .unwrap()
            .into_data();
        let len = u32::from_le_bytes(second[..4].try_into().unwrap()) as usize;
        let next: Value = serde_json::from_slice(&second[4..4 + len]).unwrap();
        assert!(next["seq"].as_u64().unwrap() > header["seq"].as_u64().unwrap() + 1);
        assert!(running.state.stats.lock().unwrap().mailbox_drops > 0);
        socket.close(None).await.unwrap();
        for _ in 0..100 {
            if running.state.clients.lock().unwrap().is_empty() {
                break;
            }
            tokio::time::sleep(Duration::from_millis(5)).await;
        }
        assert!(running.state.clients.lock().unwrap().is_empty());
        running.stop();
        task.abort();
    }
}
