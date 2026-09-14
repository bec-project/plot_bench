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

/// Phase offset (radians) of waveform plot `plot`, curve `curve`; zero for plot 0 / curve 0.
pub fn waveform_shift(plot: usize, curve: usize) -> f64 {
    plot as f64 * 0.29 + curve as f64 * 0.61
}

/// Replace-mode second-term frequency multiplier; 4.3 for curve 0.
pub fn waveform_harmonic(curve: usize) -> f64 {
    4.3 + 0.37 * curve as f64
}

/// Append-mode second-term frequency multiplier; 0.071 for curve 0.
pub fn waveform_rate(curve: usize) -> f64 {
    0.071 + 0.0061 * curve as f64
}

/// Phase of image plot `plot`; identical to `phase` for plot 0.
pub fn image_phase(phase: f64, plot: usize) -> f64 {
    phase + plot as f64 * 0.47
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
        // Plot-major, then curve-major: plot p curve c occupies points (p*curves + c).. .
        arrays.push(json!({"name":"waveform","dtype":"float32",
            "shape":[config.waveform_plots,config.curves,config.points],"offset":0,
            "nbytes":config.waveform_plots*config.curves*config.points*4}));
        let absolute_start = (seq as u128 * config.append_count as u128) as f64;
        let stop = 12.0 * std::f64::consts::PI;
        for plot in 0..config.waveform_plots {
            for curve in 0..config.curves {
                let shift = waveform_shift(plot, curve);
                if config.waveform_mode == "append" {
                    // f64 throughout, cast once at the end; windows overlap exactly
                    // between sequences because only the absolute position varies.
                    let rate = waveform_rate(curve);
                    for index in 0..config.points {
                        let x = index as f64 + absolute_start;
                        let value = ((x * 0.017 + config.seed as f64 * 0.001 + shift).sin()
                            + 0.23 * (x * rate).sin()) as f32;
                        bytes.extend_from_slice(&value.to_le_bytes());
                    }
                } else {
                    // f32 arithmetic; the f64 offsets are converted to f32 once per curve.
                    let total_shift = (phase + shift) as f32;
                    let harmonic = waveform_harmonic(curve) as f32;
                    let phase_term = (phase * 0.7) as f32;
                    for index in 0..config.points {
                        let x = coordinate(index, config.points, stop);
                        let value =
                            (x + total_shift).sin() + 0.23_f32 * (x * harmonic - phase_term).sin();
                        bytes.extend_from_slice(&value.to_le_bytes());
                    }
                }
            }
        }
    }
    if config.view != "waveform" {
        let rgb = config.image_mode == "rgb";
        let shape = if rgb {
            vec![config.image_plots, config.height, config.width, 3]
        } else {
            vec![config.image_plots, config.height, config.width]
        };
        arrays.push(
            json!({"name":"image","dtype":if rgb { "uint8" } else { "float32" },
            "shape":shape,"offset":bytes.len()-PREFIX,
            "nbytes":config.image_plots*config.width*config.height*if rgb {3} else {4}}),
        );
        let stop = 4.0 * std::f64::consts::PI;
        for plot in 0..config.image_plots {
            // Per image plot: evaluate each axis once, then write pixels row-major.
            let ph = image_phase(phase, plot);
            let x_wave: Vec<f32> = (0..config.width)
                .map(|i| (coordinate(i, config.width, stop) + ph as f32).sin())
                .collect();
            let y_wave: Vec<f32> = (0..config.height)
                .map(|i| (coordinate(i, config.height, stop) - (ph * 0.7) as f32).cos())
                .collect();
            let green: Vec<u8> = if rgb {
                (0..config.width)
                    .map(|i| {
                        ((coordinate(i, config.width, stop) * 0.7_f32 - ph as f32).sin() + 1.0)
                            * 127.5
                    })
                    .map(|v| v as u8)
                    .collect()
            } else {
                Vec::new()
            };
            for (row, y) in y_wave.iter().enumerate() {
                let blue = if rgb {
                    ((coordinate(row, config.height, stop) * 0.9_f32 + ph as f32).cos() + 1.0)
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
    }
    let header = serde_json::to_vec(
        &json!({"version":2,"seq":seq,"generation":config.generation,
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

    /// Byte range of waveform plot `plot`, curve `curve` inside the payload.
    fn curve_bytes<'a>(data: &'a [u8], config: &Config, plot: usize, curve: usize) -> &'a [u8] {
        let start = (plot * config.curves + curve) * config.points * 4;
        &data[start..start + config.points * 4]
    }

    #[test]
    fn plot_constants_reduce_to_the_single_plot_formulas() {
        assert_eq!(waveform_shift(0, 0), 0.0);
        assert_eq!(waveform_harmonic(0), 4.3);
        assert_eq!(waveform_rate(0), 0.071);
        assert_eq!(image_phase(1.25, 0), 1.25);
        assert_eq!(waveform_shift(2, 3), 2.0 * 0.29 + 3.0 * 0.61);
        assert_eq!(waveform_harmonic(5), 4.3 + 0.37 * 5.0);
        assert_eq!(waveform_rate(7), 0.071 + 0.0061 * 7.0);
        assert_eq!(image_phase(1.25, 4), 1.25 + 4.0 * 0.47);
    }

    #[test]
    fn append_overlap_is_exact_per_plot_and_curve_and_new_sequences_change() {
        let c = Config {
            points: 128,
            append_count: 17,
            curves: 3,
            waveform_plots: 2,
            view: "waveform".into(),
            waveform_mode: "append".into(),
            ..Config::default()
        };
        let first = make_packet(&c, 3).unwrap();
        let second = make_packet(&c, 4).unwrap();
        let (_, a) = decode(&first);
        let (_, b) = decode(&second);
        assert_eq!(a.len(), 2 * 3 * 128 * 4);
        for plot in 0..2 {
            for curve in 0..3 {
                let older = curve_bytes(a, &c, plot, curve);
                let newer = curve_bytes(b, &c, plot, curve);
                assert_eq!(&older[17 * 4..], &newer[..(128 - 17) * 4]);
                assert_ne!(older, newer);
            }
        }
        // Every plot and curve carries distinct data.
        assert_ne!(curve_bytes(a, &c, 0, 0), curve_bytes(a, &c, 0, 1));
        assert_ne!(curve_bytes(a, &c, 0, 0), curve_bytes(a, &c, 1, 0));
        assert_ne!(curve_bytes(a, &c, 0, 1), curve_bytes(a, &c, 1, 1));
    }

    #[test]
    fn first_plot_and_curve_are_bit_identical_to_the_single_plot_layout() {
        for mode in ["replace", "append"] {
            for image_mode in ["scalar", "rgb"] {
                let single = Config {
                    points: 97,
                    append_count: 11,
                    width: 6,
                    height: 5,
                    seed: 4711,
                    waveform_mode: mode.into(),
                    image_mode: image_mode.into(),
                    ..Config::default()
                };
                let many = Config {
                    curves: 4,
                    waveform_plots: 3,
                    image_plots: 2,
                    ..single.clone()
                };
                let single_packet = make_packet(&single, 21).unwrap();
                let many_packet = make_packet(&many, 21).unwrap();
                let (_, one) = decode(&single_packet);
                let (header, all) = decode(&many_packet);
                assert_eq!(all.len(), many.payload_bytes());
                assert_eq!(&one[..97 * 4], curve_bytes(all, &many, 0, 0));
                let image_bytes = 6 * 5 * if image_mode == "rgb" { 3 } else { 4 };
                let image_start = header["arrays"][1]["offset"].as_u64().unwrap() as usize;
                assert_eq!(image_start, 3 * 4 * 97 * 4);
                assert_eq!(
                    &one[97 * 4..97 * 4 + image_bytes],
                    &all[image_start..image_start + image_bytes]
                );
                assert_ne!(
                    &all[image_start..image_start + image_bytes],
                    &all[image_start + image_bytes..image_start + 2 * image_bytes]
                );
                for (plot, curve) in [(0, 1), (1, 0), (2, 3)] {
                    assert_ne!(&one[..97 * 4], curve_bytes(all, &many, plot, curve));
                }
            }
        }
    }

    #[test]
    fn header_shapes_offsets_ranges_and_single_views_match_protocol() {
        for view in ["waveform", "image", "both"] {
            for mode in ["scalar", "rgb"] {
                for (curves, waveform_plots, image_plots) in [(1, 1, 1), (3, 2, 4)] {
                    let c = Config {
                        points: 31,
                        append_count: 3,
                        curves,
                        waveform_plots,
                        width: 9,
                        height: 7,
                        image_plots,
                        view: view.into(),
                        image_mode: mode.into(),
                        ..Config::default()
                    };
                    let packet = make_packet(&c, 123).unwrap();
                    let (h, data) = decode(&packet);
                    assert_eq!(h["version"], 2);
                    assert_eq!(h["seq"], 123);
                    assert_eq!(h["config"]["curves"], curves);
                    assert_eq!(h["config"]["waveform_plots"], waveform_plots);
                    assert_eq!(h["config"]["image_plots"], image_plots);
                    assert_eq!(data.len(), c.payload_bytes());
                    let arrays = h["arrays"].as_array().unwrap();
                    assert_eq!(arrays.len(), if view == "both" { 2 } else { 1 });
                    let mut expected_offset = 0;
                    for a in arrays {
                        let start = a["offset"].as_u64().unwrap() as usize;
                        let n = a["nbytes"].as_u64().unwrap() as usize;
                        assert_eq!(start, expected_offset);
                        expected_offset += n;
                        if a["name"] == "waveform" {
                            assert_eq!(a["shape"], json!([waveform_plots, curves, 31]));
                            assert_eq!(a["dtype"], "float32");
                            assert_eq!(n, waveform_plots * curves * 31 * 4);
                        } else if mode == "rgb" {
                            assert_eq!(a["shape"], json!([image_plots, 7, 9, 3]));
                            assert_eq!(a["dtype"], "uint8");
                            assert_eq!(n, image_plots * 7 * 9 * 3);
                        } else {
                            assert_eq!(a["shape"], json!([image_plots, 7, 9]));
                            assert_eq!(a["dtype"], "float32");
                            assert_eq!(n, image_plots * 7 * 9 * 4);
                        }
                        if a["dtype"] == "float32" {
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
                    assert_eq!(expected_offset, data.len());
                }
            }
        }
    }
}
