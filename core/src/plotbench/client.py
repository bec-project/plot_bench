"""Small renderer-independent threaded client and batched instrumentation."""

import argparse
import json
import math
import threading
import time
from collections import deque
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from websockets.sync.client import connect

from .protocol import MAX_PACKET, Frame, decode_frame, decode_replay


def request(url, data=None, timeout=30):
    body = None if data is None else json.dumps(data, allow_nan=False).encode()
    req = Request(url, data=body, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=timeout) as response:
        return response.read()


def frontend_parser(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--mode", choices=("stream", "replay"), default="stream")
    parser.add_argument("--run-id", default="demo")
    parser.add_argument("--duration", type=nonnegative_seconds, default=0)
    parser.add_argument("--width", type=positive_integer, default=1100)
    parser.add_argument("--height", type=positive_integer, default=820)
    return parser


def nonnegative_seconds(value):
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise argparse.ArgumentTypeError("duration must be finite and nonnegative")
    return value


def positive_integer(value):
    value = int(value)
    if value <= 0:
        raise argparse.ArgumentTypeError("dimension must be positive")
    return value


class FrameSource:
    def __init__(self, url, mode="stream"):
        if mode not in ("stream", "replay"):
            raise ValueError("unknown source mode")
        if urlparse(url).scheme not in ("http", "https"):
            raise ValueError("source URL must use http or https")
        self.url = url.rstrip("/")
        self.mode = mode
        self.status = "Connecting"
        self.error = None
        self.metadata = {}
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest = None
        self._previous = None
        self._socket = None
        self._thread = None
        self._view_thread = None
        self._view_pending = False
        self._view_generation = None
        self._last_generation = -1
        self._reload_replay = threading.Event()
        self.view_error = None

    @property
    def view_pending(self):
        with self._lock:
            return self._view_pending

    def request_view(self, view):
        """Change the shared workload off the UI thread; complete on a new input frame."""
        if view not in ("both", "waveform", "image"):
            raise ValueError("view must be both, waveform, or image")
        with self._lock:
            if (
                self._stop.is_set()
                or self._view_pending
                or (self._view_thread is not None and self._view_thread.is_alive())
            ):
                return False
            self._view_pending = True
            self._view_generation = None
            self.view_error = None
            self._view_thread = threading.Thread(
                target=self._change_view, args=(view,), name="plotbench-view", daemon=True
            )
            self._view_thread.start()
        return True

    def _change_view(self, view):
        try:
            config = json.loads(request(self.url + "/api/config", {"view": view}, timeout=5))
            if config.get("view") != view or type(config.get("generation")) is not int:
                raise ValueError("source returned an invalid view configuration")
            with self._lock:
                if self._stop.is_set():
                    self._view_pending = False
                    return
                self._view_generation = config["generation"]
                if self.mode == "replay":
                    self._latest = None
                    self._reload_replay.set()
                elif self._last_generation >= self._view_generation:
                    self._view_pending = False
                    self.view_error = None
        except Exception as exc:
            with self._lock:
                self.view_error = f"Could not change plot selection: {exc}"
                self._view_pending = False

    def start(self):
        if self._thread is not None:
            raise RuntimeError("source already started")
        self._thread = threading.Thread(target=self._run, name="plotbench-source", daemon=True)
        self._thread.start()

    def _publish(self, frame):
        with self._lock:
            if self.mode == "replay" and self._reload_replay.is_set():
                return
            self._latest = frame
            self._last_generation = frame.generation
            if self._view_generation is not None and frame.generation >= self._view_generation:
                self._view_pending = False
                self.view_error = None

    def take_latest(self):
        with self._lock:
            frame, self._latest = self._latest, None
        if frame is None:
            return None
        if self._previous is not None and self._previous[0] == frame.generation:
            frame.skipped = max(0, frame.seq - self._previous[1] - 1)
        self._previous = frame.generation, frame.seq
        return frame

    def _run(self):
        while not self._stop.is_set():
            try:
                if self.mode == "stream":
                    self._stream()
                else:
                    self._replay()
            except Exception as exc:
                if self._stop.is_set():
                    break
                self.error = f"{type(exc).__name__}: {exc}"
                self.status = f"Connection error: {exc}; retrying"
                with self._lock:
                    if self._view_pending:
                        self.view_error = f"Plot selection is waiting for the source: {exc}"
                        self._view_pending = False
                self._stop.wait(1)
        self.status = "Stopped"

    def _stream(self):
        ws_url = self.url.replace("http", "ws", 1) + "/ws"
        with connect(
            ws_url, max_size=MAX_PACKET, max_queue=1, compression=None, open_timeout=10
        ) as ws:
            self._socket = ws
            self.status, self.error = "Streaming", None
            self.metadata["receiver_connection_epoch"] = (
                self.metadata.get("receiver_connection_epoch", 0) + 1
            )
            while not self._stop.is_set():
                try:
                    packet = ws.recv(timeout=1)
                except TimeoutError:
                    continue
                if not isinstance(packet, bytes):
                    raise ValueError("source sent a nonbinary frame")
                frame = decode_frame(packet)
                frame.receive_age_ms = time.time_ns() / 1e6 - frame.header["emitted_at_ms"]
                self.metadata.update(
                    target_hz=frame.header["config"]["hz"], config=frame.header["config"]
                )
                self._publish(frame)
                ws.send(json.dumps({"ack": frame.seq, "generation": frame.generation}))
        self._socket = None

    def _replay(self):
        while not self._stop.is_set():
            self._reload_replay.clear()
            self.status = "Preloading replay"
            data = request(self.url + "/api/replay?count=16")
            frames = decode_replay(data)
            replay_bytes = len(data)
            del data
            config = frames[0].header["config"]
            self.metadata["receiver_connection_epoch"] = (
                self.metadata.get("receiver_connection_epoch", 0) + 1
            )
            self.metadata.update(
                replay_frames=len(frames),
                replay_bytes=replay_bytes,
                target_hz=config["hz"],
                config=config,
            )
            self.status, self.error = "Replaying preloaded input", None
            start = time.perf_counter()
            previous = -1
            while not self._stop.is_set() and not self._reload_replay.is_set():
                now = time.perf_counter()
                seq = int((now - start) * config["hz"])
                if seq > previous:
                    original = frames[seq % len(frames)]
                    header = dict(original.header, seq=seq, replay_index=seq % len(frames))
                    self._publish(Frame(header, original.arrays))
                    previous = seq
                self._stop.wait(
                    max(0.0005, min(0.05, start + (seq + 1) / config["hz"] - time.perf_counter()))
                )

    def close(self):
        self._stop.set()
        if self._socket is not None:
            try:
                self._socket.close()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2)
        if self._view_thread is not None:
            self._view_thread.join(timeout=6)


class MetricsSink:
    def __init__(self, url, frontend, mode, run_id, metadata=None, expected_duration=None):
        self.url, self.frontend, self.mode, self.run_id = url.rstrip("/"), frontend, mode, run_id
        self.metadata = dict(metadata or {})
        self.error = None
        self.expected_duration = expected_duration
        self._first_record = None
        self._stopped_at = None
        self._pending = []
        self._recent = deque()
        self._count = self._skipped = self._lost = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._started = time.perf_counter()
        self._thread = threading.Thread(target=self._worker, name="plotbench-metrics", daemon=True)
        self._thread.start()

    def record(self, frame, update_ms, **extra):
        now = time.perf_counter()
        if self._first_record is None:
            self._first_record = now
        sample = dict(
            seq=frame.seq,
            generation=frame.generation,
            client_time_ms=time.time_ns() / 1e6,
            update_ms=float(update_ms),
            receive_age_ms=frame.receive_age_ms,
            skipped=frame.skipped,
            **extra,
        )
        with self._lock:
            # Bound instrumentation memory if the collector is unavailable.
            if len(self._pending) < 20_000:
                self._pending.append(sample)
            else:
                self._lost += 1
            self._recent.append((now, sample))
            self._count += 1
            self._skipped += frame.skipped
            self._trim(now)

    def _trim(self, now):
        while self._recent and self._recent[0][0] < now - 2:
            self._recent.popleft()

    def snapshot(self):
        now = time.perf_counter()
        with self._lock:
            self._trim(now)
            recent = list(self._recent)
            last = recent[-1][1] if recent else {}
            return dict(
                updates_hz=len(recent) / min(2, max(0.001, now - self._started)),
                update_ms=sum(x[1]["update_ms"] for x in recent) / max(1, len(recent)),
                skipped=self._skipped,
                receive_age_ms=last.get("receive_age_ms"),
                count=self._count,
                telemetry_lost=self._lost,
            )

    def _flush(self, force_metadata=False):
        with self._lock:
            pending, self._pending = self._pending, []
        if not pending and not force_metadata:
            return
        try:
            request(
                self.url + "/api/metrics",
                dict(
                    frontend=self.frontend,
                    mode=self.mode,
                    run_id=self.run_id,
                    samples=pending,
                    metadata=dict(self.metadata, telemetry_lost=self._lost),
                ),
                timeout=5,
            )
            self.error = None
        except Exception as exc:
            self.error = str(exc)
            with self._lock:
                combined = pending + self._pending
                self._lost += max(0, len(combined) - 20_000)
                self._pending = combined[-20_000:]

    def _worker(self):
        while not self._stop.wait(1):
            self._flush()
        self._flush(force_metadata=True)

    def mark_stopped(self, reason=None):
        if self._stopped_at is not None:
            return
        self._stopped_at = time.perf_counter()
        elapsed = 0 if self._first_record is None else self._stopped_at - self._first_record
        self.metadata["active_seconds"] = elapsed
        self.metadata["expected_duration"] = self.expected_duration
        self.metadata["termination_reason"] = reason or (
            "duration"
            if self.expected_duration and elapsed >= self.expected_duration - 0.05
            else "user"
        )

    def close(self):
        self.mark_stopped()
        self._stop.set()
        self._thread.join(timeout=12)
        if self._thread.is_alive():
            self.error = "Metrics flush did not finish before shutdown"
        elif self._pending:
            self.error = (
                f"{len(self._pending)} measurement samples could not be flushed: {self.error}"
            )
