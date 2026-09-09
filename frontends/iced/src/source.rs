use crate::protocol::{self, Config, MAX_PACKET, MAX_REPLAY, Packet};
use anyhow::{Context, Result, bail};
use iced::futures::channel::mpsc as async_mpsc;
use reqwest::blocking::Client;
use serde_json::{Value, json};
use std::{
    io::{ErrorKind, Read},
    net::{TcpStream, ToSocketAddrs},
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
        mpsc::{self, SyncSender},
    },
    thread::{self, JoinHandle},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use tungstenite::{Message, client_tls_with_config, protocol::WebSocketConfig};
use url::Url;

pub fn now_ms() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64()
        * 1000.0
}

pub fn http_client() -> Result<Client> {
    Ok(Client::builder()
        .connect_timeout(Duration::from_secs(3))
        .timeout(Duration::from_secs(20))
        .build()?)
}

pub fn endpoint(base: &str, path: &str) -> Result<Url> {
    Ok(Url::parse(base)?.join(path)?)
}

pub fn read_limited(response: reqwest::blocking::Response, limit: usize) -> Result<Vec<u8>> {
    let response = response.error_for_status()?;
    if response.content_length().is_some_and(|n| n > limit as u64) {
        bail!("Response exceeds the {limit}-byte limit");
    }
    let mut bytes = Vec::new();
    response.take(limit as u64 + 1).read_to_end(&mut bytes)?;
    anyhow::ensure!(
        bytes.len() <= limit,
        "Response exceeds the {limit}-byte limit"
    );
    Ok(bytes)
}

#[derive(Default)]
pub struct Shared {
    pub latest: Option<Packet>,
    pub status: String,
    pub metadata: Value,
    epoch: u64,
    control_result: Option<Result<AppliedView, String>>,
    pending_replay: Option<(ReplayDataset, AppliedView)>,
}

#[derive(Clone, Debug)]
pub struct AppliedView {
    pub generation: u64,
    pub view: String,
}

struct ReplayDataset {
    packets: Vec<Packet>,
    payload_bytes: usize,
}

pub struct Source {
    pub shared: Arc<Mutex<Shared>>,
    pub wakeups: Wakeups,
    stop: Arc<AtomicBool>,
    worker: Option<JoinHandle<()>>,
    controls: Option<SyncSender<String>>,
    control_busy: Arc<AtomicBool>,
    control_worker: Option<JoinHandle<()>>,
}

/// A bounded wakeup stream; packets remain in the single latest-value mailbox.
#[derive(Clone)]
pub struct Wakeups(Arc<WakeupChannel>);

struct WakeupChannel {
    sender: Mutex<async_mpsc::Sender<()>>,
    receiver: Mutex<Option<async_mpsc::Receiver<()>>>,
}

impl std::hash::Hash for Wakeups {
    fn hash<H: std::hash::Hasher>(&self, state: &mut H) {
        std::hash::Hash::hash(&Arc::as_ptr(&self.0), state);
    }
}

impl Wakeups {
    fn new() -> Self {
        // futures mpsc reserves one sender slot even with a zero-sized buffer.
        let (sender, receiver) = async_mpsc::channel(0);
        Self(Arc::new(WakeupChannel {
            sender: Mutex::new(sender),
            receiver: Mutex::new(Some(receiver)),
        }))
    }

    fn wake(&self) {
        // A full channel means a wakeup is already pending. Never block decoding.
        let _ = self.0.sender.lock().unwrap().try_send(());
    }

    pub fn stream(&self) -> async_mpsc::Receiver<()> {
        self.0
            .receiver
            .lock()
            .unwrap()
            .take()
            .expect("The stable source subscription is started once")
    }
}

impl Source {
    pub fn start(base: String, replay: bool) -> Self {
        let wakeups = Wakeups::new();
        let shared = Arc::new(Mutex::new(Shared {
            status: "Connecting".into(),
            metadata: json!({}),
            ..Shared::default()
        }));
        let stop = Arc::new(AtomicBool::new(false));
        let (controls, requests) = mpsc::sync_channel::<String>(1);
        let control_busy = Arc::new(AtomicBool::new(false));
        let control_state = shared.clone();
        let control_cancel = stop.clone();
        let control_base = base.clone();
        let control_wakeups = wakeups.clone();
        let control_worker = thread::spawn(move || {
            while let Ok(view) = requests.recv() {
                if control_cancel.load(Ordering::Relaxed) {
                    break;
                }
                let result = apply_view(&control_base, &view, replay);
                let mut state = control_state.lock().unwrap();
                match result {
                    Ok((applied, Some(dataset))) => {
                        state.pending_replay = Some((dataset, applied));
                    }
                    Ok((applied, None)) => state.control_result = Some(Ok(applied)),
                    Err(error) => state.control_result = Some(Err(format!("{error:#}"))),
                }
                drop(state);
                control_wakeups.wake();
            }
        });
        let state = shared.clone();
        let cancel = stop.clone();
        let source_wakeups = wakeups.clone();
        let worker = thread::spawn(move || {
            while !cancel.load(Ordering::Relaxed) {
                let result = if replay {
                    replay_loop(&base, &state, &cancel, &source_wakeups)
                } else {
                    stream_loop(&base, &state, &cancel, &source_wakeups)
                };
                if let Err(error) = result {
                    state.lock().unwrap().status = format!("Error: {error:#}; reconnecting");
                    source_wakeups.wake();
                    eprintln!("Source: {error:#}");
                    pause(&cancel, Duration::from_secs(1));
                }
            }
        });
        Self {
            shared,
            wakeups,
            stop,
            worker: Some(worker),
            controls: Some(controls),
            control_busy,
            control_worker: Some(control_worker),
        }
    }

    #[cfg(test)]
    pub fn take_latest(&self) -> Option<Packet> {
        self.shared.lock().unwrap().latest.take()
    }

    pub fn take_latest_with_epoch(&self) -> Option<(u64, Packet)> {
        let mut state = self.shared.lock().unwrap();
        state.latest.take().map(|packet| (state.epoch, packet))
    }

    pub fn request_view(&self, view: &str) -> Result<()> {
        let controls = self.controls.as_ref().context("Source is closed")?;
        anyhow::ensure!(
            ["both", "waveform", "image"].contains(&view),
            "Invalid view"
        );
        anyhow::ensure!(
            self.control_busy
                .compare_exchange(false, true, Ordering::Relaxed, Ordering::Relaxed)
                .is_ok(),
            "A plot selection request is already running"
        );
        if let Err(error) = controls.try_send(view.to_owned()) {
            self.control_busy.store(false, Ordering::Relaxed);
            return Err(error.into());
        }
        Ok(())
    }

    pub fn take_control_result(&self) -> Option<Result<AppliedView, String>> {
        let result = self.shared.lock().unwrap().control_result.take();
        if result.is_some() {
            self.control_busy.store(false, Ordering::Relaxed);
        }
        result
    }

    pub fn close(&mut self) {
        self.stop.store(true, Ordering::Relaxed);
        self.controls.take();
        if let Some(worker) = self.control_worker.take() {
            let _ = worker.join();
        }
        if let Some(worker) = self.worker.take() {
            let _ = worker.join();
        }
    }
}

fn load_replay(client: &Client, base: &str) -> Result<ReplayDataset> {
    let bytes = read_limited(
        client.get(endpoint(base, "/api/replay?count=16")?).send()?,
        MAX_REPLAY,
    )?;
    Ok(ReplayDataset {
        packets: protocol::replay(&bytes)?,
        payload_bytes: bytes.len(),
    })
}

fn apply_view(
    base: &str,
    view: &str,
    replay: bool,
) -> Result<(AppliedView, Option<ReplayDataset>)> {
    let client = http_client()?;
    let config: Config = serde_json::from_slice(&read_limited(
        client
            .post(endpoint(base, "/api/config")?)
            .json(&json!({"view": view}))
            .send()?,
        1024 * 1024,
    )?)?;
    anyhow::ensure!(
        config.view == view,
        "Source returned a different plot selection"
    );
    let applied = AppliedView {
        generation: config
            .extra
            .get("generation")
            .and_then(Value::as_u64)
            .context("Source configuration has no generation")?,
        view: config.view,
    };
    let dataset = if replay {
        let dataset = load_replay(&client, base)?;
        anyhow::ensure!(
            dataset.packets.iter().all(|packet| {
                packet.header.generation == applied.generation
                    && packet.header.config.view == applied.view
            }),
            "Source configuration changed while reloading replay; retry the selection"
        );
        Some(dataset)
    } else {
        None
    };
    Ok((applied, dataset))
}

impl Drop for Source {
    fn drop(&mut self) {
        self.close();
    }
}

fn pause(stop: &AtomicBool, duration: Duration) {
    let deadline = Instant::now() + duration;
    while !stop.load(Ordering::Relaxed) && Instant::now() < deadline {
        thread::sleep(
            deadline
                .saturating_duration_since(Instant::now())
                .min(Duration::from_millis(50)),
        );
    }
}

fn stream_loop(
    base: &str,
    shared: &Mutex<Shared>,
    stop: &AtomicBool,
    wakeups: &Wakeups,
) -> Result<()> {
    let mut url = endpoint(base, "/ws")?;
    let scheme = if url.scheme() == "https" { "wss" } else { "ws" };
    url.set_scheme(scheme)
        .map_err(|_| anyhow::anyhow!("Invalid WebSocket scheme"))?;
    let host = url.host_str().context("Missing server host")?;
    let port = url.port_or_known_default().context("Missing server port")?;
    let addresses: Vec<_> = (host, port).to_socket_addrs()?.collect();
    let stream = addresses
        .into_iter()
        .find_map(|a| TcpStream::connect_timeout(&a, Duration::from_secs(3)).ok())
        .context("Could not connect to source")?;
    stream.set_read_timeout(Some(Duration::from_millis(250)))?;
    stream.set_write_timeout(Some(Duration::from_secs(3)))?;
    stream.set_nodelay(true)?;
    let config = WebSocketConfig::default()
        .max_message_size(Some(MAX_PACKET))
        .max_frame_size(Some(MAX_PACKET));
    let (mut socket, _) = client_tls_with_config(url.as_str(), stream, Some(config), None)?;
    {
        let mut state = shared.lock().unwrap();
        state.epoch += 1;
        state.latest = None;
        state.status = "Connected — binary WebSocket".into();
    }
    wakeups.wake();
    while !stop.load(Ordering::Relaxed) {
        match socket.read() {
            Ok(Message::Binary(bytes)) => {
                let received_ms = now_ms();
                let mut packet = Packet::parse(Arc::from(bytes.as_ref()))?;
                packet.receive_age_ms = Some(received_ms - packet.header.emitted_at_ms);
                let acknowledgement = json!({
                    "ack": packet.header.seq,
                    "generation": packet.header.generation,
                });
                shared.lock().unwrap().latest = Some(packet);
                wakeups.wake();
                socket.send(Message::Text(acknowledgement.to_string().into()))?;
            }
            Ok(Message::Close(_)) => bail!("Source closed the socket"),
            Ok(_) => {}
            Err(tungstenite::Error::Io(error))
                if matches!(error.kind(), ErrorKind::WouldBlock | ErrorKind::TimedOut) => {}
            Err(error) => return Err(error.into()),
        }
    }
    let _ = socket.close(None);
    Ok(())
}

fn replay_loop(
    base: &str,
    shared: &Mutex<Shared>,
    stop: &AtomicBool,
    wakeups: &Wakeups,
) -> Result<()> {
    let client = http_client()?;
    let mut dataset = load_replay(&client, base)?;
    {
        let mut state = shared.lock().unwrap();
        state.epoch += 1;
        state.latest = None;
    }
    let record_dataset = |dataset: &ReplayDataset| {
        let mut state = shared.lock().unwrap();
        state.status = format!(
            "Replay — {} CPU frames, {:.1} MiB",
            dataset.packets.len(),
            dataset.payload_bytes as f64 / 1048576.0
        );
        state.metadata = json!({"replay_frames":dataset.packets.len(),"replay_bytes":dataset.payload_bytes,"replay_policy":"bounded cyclic CPU packets; no preloaded GPU handles"});
        drop(state);
        wakeups.wake();
    };
    record_dataset(&dataset);
    let mut epoch = Instant::now();
    let mut next = 0_u64;
    while !stop.load(Ordering::Relaxed) {
        let replacement = shared.lock().unwrap().pending_replay.take();
        let mut applied = None;
        if let Some((replacement, selection)) = replacement {
            dataset = replacement;
            epoch = Instant::now();
            next = 0;
            applied = Some(selection);
            record_dataset(&dataset);
        }
        let hz = dataset.packets[0].header.config.hz;
        let seq = (epoch.elapsed().as_secs_f64() * hz).floor() as u64;
        if seq >= next {
            let mut packet = dataset.packets[(seq % dataset.packets.len() as u64) as usize].clone();
            packet.presentation_seq = seq;
            packet.receive_age_ms = None;
            let mut state = shared.lock().unwrap();
            state.latest = Some(packet);
            if let Some(applied) = applied {
                state.control_result = Some(Ok(applied));
            }
            next = seq + 1;
            drop(state);
            wakeups.wake();
        }
        let deadline = epoch + Duration::from_secs_f64(next as f64 / hz);
        pause(
            stop,
            deadline
                .saturating_duration_since(Instant::now())
                .min(Duration::from_millis(50)),
        );
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{BufRead, Write};

    #[test]
    fn wakeups_coalesce_without_blocking_and_resume_after_drain() {
        let wakeups = Wakeups::new();
        let mut receiver = wakeups.stream();
        for _ in 0..1000 {
            wakeups.wake();
        }
        assert_eq!(receiver.try_recv(), Ok(()));
        assert!(receiver.try_recv().is_err());
        wakeups.wake();
        assert_eq!(receiver.try_recv(), Ok(()));
    }

    fn replay_fixture(view: &str, generation: u64) -> (Value, Vec<u8>) {
        let config = json!({"hz":30,"points":2,"append_count":1,"width":1,"height":1,
            "waveform_mode":"replace","image_mode":"scalar","view":view,"generation":generation});
        let mut arrays = Vec::new();
        let mut payload = Vec::new();
        if view != "image" {
            arrays.push(
                json!({"name":"waveform","dtype":"float32","shape":[2],"offset":0,"nbytes":8}),
            );
            payload.extend([0.0_f32, 1.0].into_iter().flat_map(f32::to_le_bytes));
        }
        if view != "waveform" {
            arrays.push(json!({"name":"image","dtype":"float32","shape":[1,1],"offset":payload.len(),"nbytes":4}));
            payload.extend(0.5_f32.to_le_bytes());
        }
        let header = serde_json::to_vec(&json!({"version":1,"seq":0,"generation":generation,
            "emitted_at_ms":0.0,"config":config,"arrays":arrays}))
        .unwrap();
        let mut packet = (header.len() as u32).to_le_bytes().to_vec();
        packet.extend(header);
        while !packet.len().is_multiple_of(4) {
            packet.push(0);
        }
        packet.extend(payload);
        let mut replay = 2_u32.to_le_bytes().to_vec();
        for _ in 0..2 {
            replay.extend((packet.len() as u32).to_le_bytes());
            replay.extend(&packet);
        }
        (config, replay)
    }

    fn wait_until<T>(mut receive: impl FnMut() -> Option<T>) -> T {
        let started = Instant::now();
        loop {
            if let Some(value) = receive() {
                return value;
            }
            assert!(
                started.elapsed() < Duration::from_secs(5),
                "Source operation timed out"
            );
            thread::sleep(Duration::from_millis(5));
        }
    }

    #[test]
    fn replay_selection_reloads_cpu_data_and_preserves_it_on_rejection() {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let address = listener.local_addr().unwrap();
        let server = thread::spawn(move || {
            let (waveform_config, waveform_replay) = replay_fixture("waveform", 2);
            let responses = [
                (
                    "GET /api/replay?count=16",
                    None,
                    "200 OK",
                    replay_fixture("both", 1).1,
                ),
                (
                    "POST /api/config",
                    Some("waveform"),
                    "200 OK",
                    serde_json::to_vec(&waveform_config).unwrap(),
                ),
                ("GET /api/replay?count=16", None, "200 OK", waveform_replay),
                (
                    "POST /api/config",
                    Some("image"),
                    "400 Bad Request",
                    b"selection rejected".to_vec(),
                ),
            ];
            for (route, expected_view, status, body) in responses {
                let (stream, _) = wait_until(|| match listener.accept() {
                    Ok(connection) => Some(connection),
                    Err(error) if error.kind() == ErrorKind::WouldBlock => None,
                    Err(error) => panic!("{error}"),
                });
                stream.set_nonblocking(false).unwrap();
                stream
                    .set_read_timeout(Some(Duration::from_secs(3)))
                    .unwrap();
                let mut reader = std::io::BufReader::new(stream);
                let mut first = String::new();
                reader.read_line(&mut first).unwrap();
                assert!(first.starts_with(route), "Unexpected request: {first}");
                let mut length = 0;
                loop {
                    let mut line = String::new();
                    assert!(reader.read_line(&mut line).unwrap() > 0);
                    if line == "\r\n" {
                        break;
                    }
                    if let Some(value) = line.to_ascii_lowercase().strip_prefix("content-length:") {
                        length = value.trim().parse::<usize>().unwrap();
                    }
                }
                assert!(length < 1024);
                let mut request = vec![0; length];
                reader.read_exact(&mut request).unwrap();
                if let Some(view) = expected_view {
                    assert_eq!(
                        serde_json::from_slice::<Value>(&request).unwrap(),
                        json!({"view":view})
                    );
                }
                write!(
                    reader.get_mut(),
                    "HTTP/1.1 {status}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                    body.len()
                )
                .unwrap();
                reader.get_mut().write_all(&body).unwrap();
            }
        });
        let mut source = Source::start(format!("http://{address}"), true);
        assert_eq!(
            wait_until(|| source.take_latest()).header.config.view,
            "both"
        );
        source.request_view("waveform").unwrap();
        assert!(
            source.request_view("image").is_err(),
            "Only one change may be in flight"
        );
        let applied = wait_until(|| source.take_control_result()).unwrap();
        assert_eq!(applied.generation, 2);
        assert_eq!(applied.view, "waveform");
        let packet = wait_until(|| source.take_latest().filter(|p| p.header.generation == 2));
        assert!(packet.array("waveform").is_some());
        assert!(packet.array("image").is_none());
        assert!(packet.receive_age_ms.is_none());
        source.request_view("image").unwrap();
        assert!(wait_until(|| source.take_control_result()).is_err());
        let continued = wait_until(|| {
            source
                .take_latest()
                .filter(|p| p.presentation_seq > packet.presentation_seq)
        });
        assert_eq!(continued.header.config.view, "waveform");
        source.close();
        server.join().unwrap();
    }

    #[test]
    fn endpoint_resets_path_for_protocol_route() {
        assert_eq!(
            endpoint("http://localhost:8765/ignored", "/api/config")
                .unwrap()
                .as_str(),
            "http://localhost:8765/api/config"
        );
    }

    #[test]
    #[ignore = "Requires shared source at PLOTBENCH_TEST_URL or localhost:8765"]
    fn live_shared_source_protocol_and_mailboxes() {
        let base =
            std::env::var("PLOTBENCH_TEST_URL").unwrap_or_else(|_| "http://127.0.0.1:8765".into());
        let client = http_client().unwrap();
        let frame_url = endpoint(&base, "/api/frame?seq=7").unwrap();
        let first = Packet::parse(
            read_limited(client.get(frame_url.clone()).send().unwrap(), MAX_PACKET)
                .unwrap()
                .into(),
        )
        .unwrap();
        let second = Packet::parse(
            read_limited(client.get(frame_url).send().unwrap(), MAX_PACKET)
                .unwrap()
                .into(),
        )
        .unwrap();
        assert_eq!(first.header.seq, 7);
        assert_eq!(first.header.config.hz, second.header.config.hz);
        for descriptor in &first.header.arrays {
            assert_eq!(
                first.array(&descriptor.name),
                second.array(&descriptor.name)
            );
        }
        let palette: Vec<[u8; 3]> = client
            .get(endpoint(&base, "/api/colormap").unwrap())
            .send()
            .unwrap()
            .error_for_status()
            .unwrap()
            .json()
            .unwrap();
        assert_eq!(palette.len(), 256);
        for is_replay in [false, true] {
            let mut source = Source::start(base.clone(), is_replay);
            let started = Instant::now();
            let packet = loop {
                if let Some(packet) = source.take_latest() {
                    break packet;
                }
                assert!(
                    started.elapsed() < Duration::from_secs(10),
                    "{}",
                    source.shared.lock().unwrap().status
                );
                thread::sleep(Duration::from_millis(10));
            };
            assert_eq!(packet.receive_age_ms.is_none(), is_replay);
            let first_identity = (packet.header.generation, packet.presentation_seq);
            loop {
                if let Some(next) = source.take_latest() {
                    assert_ne!(
                        first_identity,
                        (next.header.generation, next.presentation_seq)
                    );
                    break;
                }
                assert!(
                    started.elapsed() < Duration::from_secs(10),
                    "Source did not advance after the first frame acknowledgement"
                );
                thread::sleep(Duration::from_millis(10));
            }
            if is_replay {
                assert!(
                    source.shared.lock().unwrap().metadata["replay_frames"]
                        .as_u64()
                        .unwrap()
                        > 0
                );
            }
            source.close();
        }
    }
}
