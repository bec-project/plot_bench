use crate::source::{endpoint, http_client};
use serde::Serialize;
use serde_json::{Value, json};
use std::{
    sync::{Arc, Mutex, mpsc},
    thread::{self, JoinHandle},
    time::Duration,
};

#[derive(Debug, Clone, Serialize)]
pub struct Sample {
    pub seq: u64,
    pub generation: u64,
    pub client_time_ms: f64,
    pub update_ms: f64,
    pub update_complete_ms: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub image_upload_wait_ms: Option<f64>,
    pub receive_age_ms: Option<f64>,
    pub skipped: u64,
    pub conversion_ms: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub draw_ms: Option<f64>,
}

#[derive(Default)]
pub struct Buffer {
    pub samples: Vec<Sample>,
    pub metadata: Value,
    pub error: Option<String>,
    pub lost: usize,
}

pub struct Metrics {
    pub buffer: Arc<Mutex<Buffer>>,
    stop: mpsc::Sender<()>,
    worker: Option<JoinHandle<()>>,
}

impl Metrics {
    pub fn start(base: String, mode: String, run_id: String, metadata: Value) -> Self {
        let buffer = Arc::new(Mutex::new(Buffer {
            metadata,
            ..Buffer::default()
        }));
        let state = buffer.clone();
        let (stop, rx) = mpsc::channel();
        let worker = thread::spawn(move || {
            let client = match http_client() {
                Ok(client) => client,
                Err(error) => {
                    state.lock().unwrap().error = Some(error.to_string());
                    return;
                }
            };
            loop {
                let closing = !matches!(
                    rx.recv_timeout(Duration::from_secs(1)),
                    Err(mpsc::RecvTimeoutError::Timeout)
                );
                let (samples, metadata) = {
                    let mut b = state.lock().unwrap();
                    let mut metadata = b.metadata.clone();
                    metadata["telemetry_lost"] = json!(b.lost);
                    metadata["telemetry_error"] = json!(b.error);
                    if closing && b.error.is_some() {
                        metadata["termination_reason"] = json!("error");
                    }
                    (std::mem::take(&mut b.samples), metadata)
                };
                if !samples.is_empty() || closing {
                    let body = json!({"frontend":"iced","mode":mode,"run_id":run_id,"samples":samples,"metadata":metadata});
                    let result = endpoint(&base, "/api/metrics").and_then(|url| {
                        Ok(client
                            .post(url)
                            .timeout(Duration::from_secs(3))
                            .json(&body)
                            .send()?
                            .error_for_status()?)
                    });
                    if let Err(error) = result {
                        let mut b = state.lock().unwrap();
                        b.lost += samples.len();
                        let message = format!(
                            "Metrics export failed: {error}; {} samples unconfirmed",
                            b.lost
                        );
                        eprintln!("{message}");
                        b.error = Some(message);
                    }
                }
                if closing {
                    break;
                }
            }
        });
        Self {
            buffer,
            stop,
            worker: Some(worker),
        }
    }

    pub fn record(&self, sample: Sample) {
        let mut b = self.buffer.lock().unwrap();
        if b.samples.len() >= 4096 {
            b.lost += 1;
            b.error = Some(format!("Metrics buffer overflow: {} samples lost", b.lost));
        } else {
            b.samples.push(sample);
        }
    }

    pub fn close(&mut self) {
        let _ = self.stop.send(());
        if let Some(worker) = self.worker.take() {
            let _ = worker.join();
        }
    }
}

impl Drop for Metrics {
    fn drop(&mut self) {
        self.close();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{BufRead, Read, Write};

    #[test]
    fn serializes_completion_stages_without_inventing_missing_draw_or_upload_times() {
        let mut sample = Sample {
            seq: 1,
            generation: 0,
            client_time_ms: 1.0,
            update_ms: 2.0,
            update_complete_ms: 2.5,
            image_upload_wait_ms: None,
            receive_age_ms: None,
            skipped: 0,
            conversion_ms: 1.5,
            draw_ms: None,
        };
        let waveform = serde_json::to_value(&sample).unwrap();
        assert_eq!(waveform["update_complete_ms"], 2.5);
        assert!(waveform.get("image_upload_wait_ms").is_none());
        assert!(waveform.get("draw_ms").is_none());
        sample.image_upload_wait_ms = Some(8.0);
        sample.update_complete_ms = 10.5;
        let image = serde_json::to_value(&sample).unwrap();
        assert_eq!(image["image_upload_wait_ms"], 8.0);
        assert_eq!(image["update_complete_ms"], 10.5);
        assert_eq!(image["update_ms"], 2.0);
    }

    #[test]
    fn close_exports_final_metadata_without_samples() {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        listener.set_nonblocking(true).unwrap();
        let server = thread::spawn(move || {
            let deadline = std::time::Instant::now() + Duration::from_secs(5);
            let (stream, _) = loop {
                match listener.accept() {
                    Ok(connection) => break connection,
                    Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                        assert!(
                            std::time::Instant::now() < deadline,
                            "Final batch never arrived"
                        );
                        thread::sleep(Duration::from_millis(10));
                    }
                    Err(error) => panic!("{error}"),
                }
            };
            stream
                .set_read_timeout(Some(Duration::from_secs(3)))
                .unwrap();
            let mut reader = std::io::BufReader::new(stream);
            let mut length = None;
            loop {
                let mut line = String::new();
                assert!(reader.read_line(&mut line).unwrap() > 0);
                if line == "\r\n" {
                    break;
                }
                if let Some(value) = line.to_lowercase().strip_prefix("content-length:") {
                    length = Some(value.trim().parse::<usize>().unwrap());
                }
            }
            let mut body = vec![0; length.unwrap()];
            reader.read_exact(&mut body).unwrap();
            reader
                .get_mut()
                .write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}")
                .unwrap();
            serde_json::from_slice::<Value>(&body).unwrap()
        });
        let mut metrics = Metrics::start(
            format!("http://{address}"),
            "stream".into(),
            "final-metadata-test".into(),
            json!({"termination_reason":"user","active_seconds":0.0}),
        );
        metrics.close();
        let batch = server.join().unwrap();
        assert_eq!(batch["samples"], json!([]));
        assert_eq!(batch["metadata"]["termination_reason"], "user");
        assert_eq!(batch["metadata"]["active_seconds"], 0.0);
        assert_eq!(batch["metadata"]["telemetry_lost"], 0);
    }
}
