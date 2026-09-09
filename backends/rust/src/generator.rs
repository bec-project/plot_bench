use crate::config::Config;
use anyhow::{Result, ensure};
use bytes::Bytes;
use serde_json::json;
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Clone, Debug)]
pub struct Packet {
    pub bytes: Bytes,
    pub seq: u64,
    pub generation: u64,
}

pub fn now_ms() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64()
        * 1000.0
}

fn coordinate(index: usize, count: usize, stop: f64) -> f32 {
    if count == 1 {
        0.0
    } else if index + 1 == count {
        stop as f32
    } else {
        (index as f64 * (stop / (count - 1) as f64)) as f32
    }
}

pub fn make_packet(config: &Config, seq: u64) -> Result<Packet> {
    config.validate()?;
    // Reserve prefix space, fill the payload once, then place the timestamped
    // header immediately before it. Bytes slicing avoids a full payload copy.
    const PREFIX: usize = 4096;
    let mut bytes = Vec::new();
    bytes.try_reserve_exact(PREFIX + config.payload_bytes())?;
    bytes.resize(PREFIX, 0);
    let phase = seq as f64 * 0.13 + (config.seed % 10_000) as f64 * 0.001;
    let mut arrays = Vec::with_capacity(2);
    if config.view != "image" {
        arrays.push(json!({"name":"waveform","dtype":"float32","shape":[config.points],"offset":0,"nbytes":config.points*4}));
        let absolute_start = (seq as u128 * config.append_count as u128) as f64;
        for index in 0..config.points {
            let value = if config.waveform_mode == "append" {
                let x = index as f64 + absolute_start;
                ((x * 0.017 + config.seed as f64 * 0.001).sin() + 0.23 * (x * 0.071).sin()) as f32
            } else {
                let x = coordinate(index, config.points, 12.0 * std::f64::consts::PI);
                (x + phase as f32).sin() + 0.23_f32 * (x * 4.3_f32 - (phase * 0.7) as f32).sin()
            };
            bytes.extend_from_slice(&value.to_le_bytes());
        }
    }
    if config.view != "waveform" {
        let rgb = config.image_mode == "rgb";
        let shape = if rgb {
            vec![config.height, config.width, 3]
        } else {
            vec![config.height, config.width]
        };
        arrays.push(json!({"name":"image","dtype":if rgb { "uint8" } else { "float32" },
            "shape":shape,"offset":bytes.len()-PREFIX,"nbytes":config.width*config.height*if rgb {3} else {4}}));
        let stop = 4.0 * std::f64::consts::PI;
        let x_wave: Vec<f32> = (0..config.width)
            .map(|i| (coordinate(i, config.width, stop) + phase as f32).sin())
            .collect();
        let y_wave: Vec<f32> = (0..config.height)
            .map(|i| (coordinate(i, config.height, stop) - (phase * 0.7) as f32).cos())
            .collect();
        let green: Vec<u8> = if rgb {
            (0..config.width)
                .map(|i| {
                    ((coordinate(i, config.width, stop) * 0.7_f32 - phase as f32).sin() + 1.0)
                        * 127.5
                })
                .map(|v| v as u8)
                .collect()
        } else {
            Vec::new()
        };
        for (row, y) in y_wave.iter().enumerate() {
            let blue = if rgb {
                ((coordinate(row, config.height, stop) * 0.9_f32 + phase as f32).cos() + 1.0)
                    * 127.5
            } else {
                0.0
            } as u8;
            for (column, x) in x_wave.iter().enumerate() {
                let scalar = ((*x + *y + 2.0) * 0.25).clamp(0.0, 1.0);
                if rgb {
                    bytes.extend_from_slice(&[(scalar * 255.0) as u8, green[column], blue]);
                } else {
                    bytes.extend_from_slice(&scalar.to_le_bytes());
                }
            }
        }
    }
    let header = serde_json::to_vec(
        &json!({"version":1,"seq":seq,"generation":config.generation,
        "emitted_at_ms":now_ms(),"config":config,"arrays":arrays}),
    )?;
    let prefix_length = (header.len() + 7) & !3;
    ensure!(
        prefix_length <= PREFIX,
        "Frame header exceeds reserved prefix"
    );
    let start = PREFIX - prefix_length;
    bytes[start..start + 4].copy_from_slice(&(header.len() as u32).to_le_bytes());
    bytes[start + 4..start + 4 + header.len()].copy_from_slice(&header);
    Ok(Packet {
        bytes: Bytes::from(bytes).slice(start..),
        seq,
        generation: config.generation,
    })
}

pub fn colormap() -> Vec<[u8; 3]> {
    let anchors: [[i32; 3]; 5] = [
        [12, 18, 52],
        [37, 70, 145],
        [24, 165, 168],
        [150, 216, 100],
        [255, 236, 100],
    ];
    (0..256)
        .map(|index| {
            let segment = (index * 4 / 255).min(3);
            let remainder = (index * 4 - segment * 255) as i32;
            std::array::from_fn(|channel| {
                let numerator = anchors[segment][channel] * 255
                    + (anchors[segment + 1][channel] - anchors[segment][channel]) * remainder;
                ((numerator + 127) / 255) as u8
            })
        })
        .collect()
}

#[cfg(test)]
pub fn decode(packet: &Packet) -> (serde_json::Value, &[u8]) {
    let length = u32::from_le_bytes(packet.bytes[..4].try_into().unwrap()) as usize;
    (
        serde_json::from_slice(&packet.bytes[4..4 + length]).unwrap(),
        &packet.bytes[(length + 7) & !3..],
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn append_overlap_is_exact_and_new_sequences_change() {
        let c = Config {
            points: 128,
            append_count: 17,
            view: "waveform".into(),
            waveform_mode: "append".into(),
            ..Config::default()
        };
        let first = make_packet(&c, 3).unwrap();
        let second = make_packet(&c, 4).unwrap();
        let (_, a) = decode(&first);
        let (_, b) = decode(&second);
        assert_eq!(&a[17 * 4..], &b[..(128 - 17) * 4]);
        assert_ne!(a, b);
    }

    #[test]
    fn header_shapes_offsets_ranges_and_single_views_match_protocol() {
        for view in ["waveform", "image", "both"] {
            for mode in ["scalar", "rgb"] {
                let c = Config {
                    points: 31,
                    append_count: 3,
                    width: 9,
                    height: 7,
                    view: view.into(),
                    image_mode: mode.into(),
                    ..Config::default()
                };
                let packet = make_packet(&c, 123).unwrap();
                let (h, data) = decode(&packet);
                assert_eq!(h["version"], 1);
                assert_eq!(h["seq"], 123);
                assert_eq!(data.len(), c.payload_bytes());
                assert_eq!(
                    h["arrays"].as_array().unwrap().len(),
                    if view == "both" { 2 } else { 1 }
                );
                for a in h["arrays"].as_array().unwrap() {
                    if a["dtype"] == "float32" {
                        let start = a["offset"].as_u64().unwrap() as usize;
                        let n = a["nbytes"].as_u64().unwrap() as usize;
                        for bytes in data[start..start + n].chunks_exact(4) {
                            let value = f32::from_le_bytes(bytes.try_into().unwrap());
                            assert!(value.is_finite());
                            assert!(if a["name"] == "waveform" {
                                (-1.23..=1.23).contains(&value)
                            } else {
                                (0.0..=1.0).contains(&value)
                            });
                        }
                    }
                }
            }
        }
    }
}
