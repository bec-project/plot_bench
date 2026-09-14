use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Serialize};
use std::sync::Arc;

pub const VERSION: u32 = 2;
pub const MAX_PACKET: usize = 257 * 1024 * 1024;
pub const MAX_REPLAY: usize = 256 * 1024 * 1024;

/// Shared workload configuration; the field order matches the Python `Config` dataclass.
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Config {
    pub hz: f64,
    pub points: usize,
    pub append_count: usize,
    pub curves: usize,
    pub waveform_plots: usize,
    pub width: u32,
    pub height: u32,
    pub image_plots: usize,
    pub waveform_mode: String,
    pub image_mode: String,
    pub view: String,
    #[serde(flatten)]
    pub extra: serde_json::Map<String, serde_json::Value>,
}

impl Config {
    /// Waveform plots shown by the current view (0 when hidden).
    pub fn visible_waveform_plots(&self) -> usize {
        if self.view == "image" {
            0
        } else {
            self.waveform_plots
        }
    }

    /// Image plots shown by the current view (0 when hidden).
    pub fn visible_image_plots(&self) -> usize {
        if self.view == "waveform" {
            0
        } else {
            self.image_plots
        }
    }

    /// Range and enumeration checks shared by packet headers and the boot `/api/config`
    /// fetch, so an invalid configuration fails with the same message on both paths.
    pub fn validate(&self) -> Result<()> {
        ensure!(
            self.hz.is_finite() && self.hz > 0.0 && self.hz <= 120.0,
            "Invalid Hz"
        );
        ensure!(
            self.points > 0 && self.width > 0 && self.height > 0,
            "Empty dimensions"
        );
        ensure!(
            self.append_count > 0 && self.append_count <= self.points,
            "Invalid append count"
        );
        ensure!(
            (1..=64).contains(&self.curves),
            "curves must be between 1 and 64"
        );
        ensure!(
            (1..=16).contains(&self.waveform_plots),
            "waveform_plots must be between 1 and 16"
        );
        ensure!(
            (1..=16).contains(&self.image_plots),
            "image_plots must be between 1 and 16"
        );
        ensure!(
            ["replace", "append"].contains(&self.waveform_mode.as_str()),
            "Invalid waveform mode"
        );
        ensure!(
            ["rgb", "scalar"].contains(&self.image_mode.as_str()),
            "Invalid image mode"
        );
        ensure!(
            ["waveform", "image", "both"].contains(&self.view.as_str()),
            "Invalid view"
        );
        Ok(())
    }

    /// Bytes of one image plot: `height × width` float32 or `height × width × 3` uint8.
    pub fn image_plot_bytes(&self) -> usize {
        self.height as usize * self.width as usize * if self.image_mode == "rgb" { 3 } else { 4 }
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct Array {
    pub name: String,
    pub dtype: String,
    pub shape: Vec<usize>,
    pub offset: usize,
    pub nbytes: usize,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Header {
    pub version: u32,
    pub seq: u64,
    pub generation: u64,
    pub emitted_at_ms: f64,
    pub config: Config,
    pub arrays: Vec<Array>,
}

#[derive(Debug, Clone)]
pub struct Packet {
    pub header: Header,
    bytes: Arc<[u8]>,
    payload: usize,
    pub presentation_seq: u64,
    pub receive_age_ms: Option<f64>,
}

fn word(bytes: &[u8], offset: usize) -> Result<usize> {
    let chunk = bytes
        .get(offset..offset + 4)
        .context("Truncated length prefix")?;
    Ok(u32::from_le_bytes(chunk.try_into()?) as usize)
}

impl Packet {
    pub fn parse(bytes: Arc<[u8]>) -> Result<Self> {
        ensure!(bytes.len() <= MAX_PACKET, "Packet exceeds 257 MiB");
        let header_len = word(&bytes, 0)?;
        ensure!(header_len <= 65536, "Header exceeds 64 KiB");
        let end = 4 + header_len;
        let header: Header =
            serde_json::from_slice(bytes.get(4..end).context("Truncated header")?)?;
        ensure!(header.version == VERSION, "Unsupported protocol version");
        let payload = (end + 3) & !3;
        ensure!(payload <= bytes.len(), "Missing header padding");
        ensure!(
            header.emitted_at_ms.is_finite(),
            "Invalid emission timestamp"
        );
        let c = &header.config;
        c.validate()?;
        let mut names = Vec::new();
        let mut payload_end = 0;
        for a in &header.arrays {
            ensure!(!names.contains(&a.name.as_str()), "Duplicate array name");
            names.push(a.name.as_str());
            ensure!(
                (1..=4).contains(&a.shape.len()),
                "Arrays must have one to four dimensions"
            );
            let item_size = match a.dtype.as_str() {
                "float32" => 4,
                "uint8" => 1,
                _ => bail!("Unsupported dtype {}", a.dtype),
            };
            let expected = a
                .shape
                .iter()
                .try_fold(item_size, |n: usize, s| n.checked_mul(*s));
            ensure!(
                expected == Some(a.nbytes),
                "Array byte length disagrees with shape"
            );
            let limit = a
                .offset
                .checked_add(a.nbytes)
                .context("Array offset overflow")?;
            ensure!(
                limit <= bytes.len() - payload,
                "Array exceeds packet payload"
            );
            ensure!(a.offset % item_size == 0, "Misaligned array offset");
            ensure!(
                a.offset == payload_end,
                "Arrays must be contiguous and ordered"
            );
            payload_end = limit;
            let (height, width) = (c.height as usize, c.width as usize);
            match a.name.as_str() {
                "waveform" => ensure!(
                    a.dtype == "float32" && a.shape == [c.waveform_plots, c.curves, c.points],
                    "Invalid waveform shape or dtype"
                ),
                "image" if c.image_mode == "rgb" => ensure!(
                    a.dtype == "uint8" && a.shape == [c.image_plots, height, width, 3],
                    "Invalid RGB shape or dtype"
                ),
                "image" => ensure!(
                    a.dtype == "float32" && a.shape == [c.image_plots, height, width],
                    "Invalid scalar image shape or dtype"
                ),
                _ => bail!("Unexpected array name {}", a.name),
            }
        }
        ensure!(
            c.view == "image" || names.contains(&"waveform"),
            "Missing waveform"
        );
        ensure!(
            c.view == "waveform" || names.contains(&"image"),
            "Missing image"
        );
        ensure!(
            names.len() == if c.view == "both" { 2 } else { 1 },
            "Unexpected array for selected view"
        );
        ensure!(
            payload_end == bytes.len() - payload,
            "Unexpected trailing payload"
        );
        Ok(Self {
            presentation_seq: header.seq,
            header,
            bytes,
            payload,
            receive_age_ms: None,
        })
    }

    /// The complete contiguous bytes of a named array, plot-major then curve-major.
    pub fn array(&self, name: &str) -> Option<&[u8]> {
        self.header
            .arrays
            .iter()
            .find(|a| a.name == name)
            .map(|a| &self.bytes[self.payload + a.offset..self.payload + a.offset + a.nbytes])
    }

    /// Float32 little-endian samples of waveform plot `plot`, curve `curve`, without copying.
    pub fn waveform_curve(&self, plot: usize, curve: usize) -> Option<&[u8]> {
        let c = &self.header.config;
        if plot >= c.waveform_plots || curve >= c.curves {
            return None;
        }
        let stride = c.points * 4;
        let start = (plot * c.curves + curve) * stride;
        self.array("waveform")?.get(start..start + stride)
    }

    /// Row-major pixels of image plot `plot` (float32 scalar or uint8 RGB), without copying.
    pub fn image_plot(&self, plot: usize) -> Option<&[u8]> {
        let c = &self.header.config;
        if plot >= c.image_plots {
            return None;
        }
        let stride = c.image_plot_bytes();
        self.array("image")?.get(plot * stride..(plot + 1) * stride)
    }
}

pub fn replay(bytes: &[u8]) -> Result<Vec<Packet>> {
    ensure!(bytes.len() <= MAX_REPLAY, "Replay exceeds memory limit");
    let count = word(bytes, 0)?;
    ensure!((2..=256).contains(&count), "Invalid replay frame count");
    let mut offset = 4;
    let mut packets = Vec::with_capacity(count);
    for _ in 0..count {
        let n = word(bytes, offset)?;
        offset += 4;
        let end = offset.checked_add(n).context("Replay length overflow")?;
        packets.push(Packet::parse(Arc::from(
            bytes.get(offset..end).context("Truncated replay frame")?,
        ))?);
        offset = end;
    }
    ensure!(offset == bytes.len(), "Trailing replay data");
    Ok(packets)
}

pub fn rgba(data: &[u8], rgb: bool, palette: &[[u8; 3]]) -> Vec<u8> {
    let mut output = Vec::with_capacity(data.len() / if rgb { 3 } else { 4 } * 4);
    if rgb {
        for pixel in data.chunks_exact(3) {
            output.extend_from_slice(&[pixel[0], pixel[1], pixel[2], 255]);
        }
    } else {
        for value in data.chunks_exact(4) {
            let value = f32::from_le_bytes(value.try_into().expect("Four-byte chunk"));
            let index = (value.clamp(0.0, 1.0) * 255.0) as usize;
            let pixel = palette[index];
            output.extend_from_slice(&[pixel[0], pixel[1], pixel[2], 255]);
        }
    }
    output
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    use serde_json::{Value, json};

    /// Packs a header and contiguous payload exactly like the Python `encode_frame`.
    pub(crate) fn pack(mut header: Value, payload: &[u8]) -> Vec<u8> {
        header["version"] = json!(VERSION);
        let json = serde_json::to_vec(&header).unwrap();
        let mut bytes = (json.len() as u32).to_le_bytes().to_vec();
        bytes.extend(json);
        while !bytes.len().is_multiple_of(4) {
            bytes.push(0);
        }
        bytes.extend_from_slice(payload);
        bytes
    }

    pub(crate) fn config(
        view: &str,
        points: usize,
        curves: usize,
        waveform_plots: usize,
        (width, height): (usize, usize),
        image_plots: usize,
        image_mode: &str,
    ) -> Value {
        json!({"hz":30,"points":points,"append_count":1,"curves":curves,
            "waveform_plots":waveform_plots,"width":width,"height":height,
            "image_plots":image_plots,"waveform_mode":"replace","image_mode":image_mode,
            "view":view,"seed":42,"generation":1})
    }

    /// A packet whose sample values encode their plot, curve and index for slice checks.
    pub(crate) fn multi_plot_packet(image_mode: &str) -> (Value, Vec<u8>) {
        let (points, curves, plots, (width, height), images) = (4, 3, 2, (3, 2), 2);
        let config = config(
            "both",
            points,
            curves,
            plots,
            (width, height),
            images,
            image_mode,
        );
        let mut payload = Vec::new();
        for p in 0..plots {
            for c in 0..curves {
                for i in 0..points {
                    payload.extend(((p * 100 + c * 10 + i) as f32).to_le_bytes());
                }
            }
        }
        let waveform_bytes = payload.len();
        let (dtype, shape) = if image_mode == "rgb" {
            for p in 0..images {
                for pixel in 0..width * height {
                    let base = (p * 100 + pixel * 3) as u8;
                    payload.extend([base, base + 1, base + 2]);
                }
            }
            ("uint8", json!([images, height, width, 3]))
        } else {
            for p in 0..images {
                for pixel in 0..width * height {
                    payload.extend(((p * 100 + pixel) as f32).to_le_bytes());
                }
            }
            ("float32", json!([images, height, width]))
        };
        let header = json!({"seq":9,"generation":1,"emitted_at_ms":1234.5,"config":config,
            "arrays":[
                {"name":"waveform","dtype":"float32","shape":[plots,curves,points],
                    "offset":0,"nbytes":waveform_bytes},
                {"name":"image","dtype":dtype,"shape":shape,"offset":waveform_bytes,
                    "nbytes":payload.len()-waveform_bytes}]});
        let bytes = pack(header.clone(), &payload);
        (header, bytes)
    }

    fn packet() -> Vec<u8> {
        let header = json!({"seq":9,"generation":2,"emitted_at_ms":1234.5,
            "config":{"hz":120,"points":2,"append_count":1,"curves":1,"waveform_plots":1,
                "width":1,"height":1,"image_plots":1,"waveform_mode":"append",
                "image_mode":"scalar","view":"both"},
            "arrays":[{"name":"waveform","dtype":"float32","shape":[1,1,2],"offset":0,"nbytes":8},
                {"name":"image","dtype":"float32","shape":[1,1,1],"offset":8,"nbytes":4}]});
        let payload: Vec<u8> = [-1.0_f32, 1.0, 0.5]
            .into_iter()
            .flat_map(f32::to_le_bytes)
            .collect();
        pack(header, &payload)
    }

    #[test]
    fn decodes_authoritative_append_window() {
        let p = Packet::parse(packet().into()).unwrap();
        assert_eq!(p.header.seq, 9);
        assert_eq!(p.header.version, 2);
        assert_eq!(p.header.config.waveform_mode, "append");
        assert_eq!(p.header.config.curves, 1);
        assert_eq!(p.header.config.waveform_plots, 1);
        assert_eq!(p.header.config.image_plots, 1);
        assert_eq!(
            p.array("waveform").unwrap(),
            [(-1.0_f32).to_le_bytes(), 1.0_f32.to_le_bytes()].concat()
        );
        assert_eq!(p.waveform_curve(0, 0), p.array("waveform"));
        assert_eq!(p.image_plot(0), p.array("image"));
        assert_eq!(p.waveform_curve(0, 1), None);
        assert_eq!(p.waveform_curve(1, 0), None);
        assert_eq!(p.image_plot(1), None);
    }

    #[test]
    fn rejects_truncation_and_bad_version() {
        let bytes = packet();
        assert!(Packet::parse(bytes[..bytes.len() - 1].into()).is_err());
        assert!(Packet::parse(Arc::from([255, 255, 255, 255])).is_err());
        for version in ["1", "3"] {
            let changed = String::from_utf8_lossy(&bytes)
                .replace("\"version\":2", &format!("\"version\":{version}"))
                .into_bytes();
            assert!(Packet::parse(changed.into()).is_err(), "version {version}");
        }
    }

    #[test]
    fn slices_every_plot_and_curve_without_copying() {
        for image_mode in ["scalar", "rgb"] {
            let (_, bytes) = multi_plot_packet(image_mode);
            let p = Packet::parse(bytes.into()).unwrap();
            let c = &p.header.config;
            assert_eq!((c.waveform_plots, c.curves, c.points), (2, 3, 4));
            let waveform = p.array("waveform").unwrap();
            for plot in 0..2 {
                for curve in 0..3 {
                    let slice = p.waveform_curve(plot, curve).unwrap();
                    let start = (plot * 3 + curve) * 16;
                    assert_eq!(slice.as_ptr(), waveform[start..].as_ptr());
                    let values: Vec<f32> = slice
                        .chunks_exact(4)
                        .map(|v| f32::from_le_bytes(v.try_into().unwrap()))
                        .collect();
                    let expected: Vec<f32> = (0..4)
                        .map(|i| (plot * 100 + curve * 10 + i) as f32)
                        .collect();
                    assert_eq!(values, expected, "plot {plot} curve {curve}");
                }
            }
            assert_eq!(p.waveform_curve(2, 0), None);
            assert_eq!(p.waveform_curve(0, 3), None);
            let image = p.array("image").unwrap();
            let stride = if image_mode == "rgb" { 6 * 3 } else { 6 * 4 };
            assert_eq!(image.len(), 2 * stride);
            for plot in 0..2 {
                let slice = p.image_plot(plot).unwrap();
                assert_eq!(slice.len(), stride);
                assert_eq!(slice.as_ptr(), image[plot * stride..].as_ptr());
                if image_mode == "rgb" {
                    assert_eq!(
                        slice[..3],
                        [
                            (plot * 100) as u8,
                            (plot * 100 + 1) as u8,
                            (plot * 100 + 2) as u8
                        ]
                    );
                    assert_eq!(slice[stride - 3], (plot * 100 + 15) as u8);
                } else {
                    assert_eq!(
                        f32::from_le_bytes(slice[stride - 4..].try_into().unwrap()),
                        (plot * 100 + 5) as f32
                    );
                }
            }
            assert_eq!(p.image_plot(2), None);
        }
    }

    fn with_changes(mut header: Value, edit: impl FnOnce(&mut Value)) -> Vec<u8> {
        let payload_len: usize = header["arrays"]
            .as_array()
            .unwrap()
            .iter()
            .map(|a| a["nbytes"].as_u64().unwrap() as usize)
            .sum();
        edit(&mut header);
        pack(header, &vec![0; payload_len])
    }

    type HeaderEdit = Box<dyn Fn(&mut Value)>;

    #[test]
    fn rejects_shapes_that_disagree_with_the_plot_layout() {
        let (header, bytes) = multi_plot_packet("scalar");
        assert!(Packet::parse(bytes.into()).is_ok());
        let rejected: Vec<(&str, HeaderEdit)> = vec![
            (
                "flat waveform",
                Box::new(|h| h["arrays"][0]["shape"] = json!([24])),
            ),
            (
                "2-D waveform",
                Box::new(|h| h["arrays"][0]["shape"] = json!([6, 4])),
            ),
            (
                "transposed waveform",
                Box::new(|h| h["arrays"][0]["shape"] = json!([3, 2, 4])),
            ),
            (
                "5-D waveform",
                Box::new(|h| h["arrays"][0]["shape"] = json!([1, 2, 3, 4, 1])),
            ),
            (
                "curves mismatch",
                Box::new(|h| h["config"]["curves"] = json!(2)),
            ),
            (
                "plots mismatch",
                Box::new(|h| h["config"]["waveform_plots"] = json!(1)),
            ),
            (
                "2-D image",
                Box::new(|h| h["arrays"][1]["shape"] = json!([4, 3])),
            ),
            (
                "transposed image",
                Box::new(|h| h["arrays"][1]["shape"] = json!([2, 3, 2])),
            ),
            (
                "rgb config on scalar data",
                Box::new(|h| h["config"]["image_mode"] = json!("rgb")),
            ),
            (
                "image plots mismatch",
                Box::new(|h| h["config"]["image_plots"] = json!(1)),
            ),
            (
                "zero curves",
                Box::new(|h| h["config"]["curves"] = json!(0)),
            ),
            (
                "too many curves",
                Box::new(|h| h["config"]["curves"] = json!(65)),
            ),
            (
                "too many waveform plots",
                Box::new(|h| h["config"]["waveform_plots"] = json!(17)),
            ),
            (
                "too many image plots",
                Box::new(|h| h["config"]["image_plots"] = json!(17)),
            ),
            (
                "missing curves field",
                Box::new(|h| {
                    h["config"].as_object_mut().unwrap().remove("curves");
                }),
            ),
        ];
        for (name, edit) in rejected {
            let bytes = with_changes(header.clone(), edit);
            assert!(Packet::parse(bytes.into()).is_err(), "{name} was accepted");
        }
        // The range checks report the same message from `Config::validate`, which the
        // boot `/api/config` fetch reuses instead of clamping.
        let ranges: Vec<(&str, &str, i64, &str)> = vec![
            (
                "zero curves",
                "curves",
                0,
                "curves must be between 1 and 64",
            ),
            (
                "too many curves",
                "curves",
                65,
                "curves must be between 1 and 64",
            ),
            (
                "too many waveform plots",
                "waveform_plots",
                17,
                "waveform_plots must be between 1 and 16",
            ),
            (
                "too many image plots",
                "image_plots",
                17,
                "image_plots must be between 1 and 16",
            ),
        ];
        for (name, field, value, message) in ranges {
            let bytes = with_changes(header.clone(), |h| h["config"][field] = json!(value));
            let error = Packet::parse(bytes.into()).unwrap_err().to_string();
            assert_eq!(error, message, "{name}");
            let mut config: Config = serde_json::from_value(header["config"].clone()).unwrap();
            match field {
                "curves" => config.curves = value as usize,
                "waveform_plots" => config.waveform_plots = value as usize,
                _ => config.image_plots = value as usize,
            }
            assert_eq!(
                config.validate().unwrap_err().to_string(),
                message,
                "{name}"
            );
        }
    }

    #[test]
    fn replay_checks_exact_container_lengths() {
        let p = packet();
        let mut container = 2_u32.to_le_bytes().to_vec();
        for _ in 0..2 {
            container.extend((p.len() as u32).to_le_bytes());
            container.extend(&p);
        }
        assert_eq!(replay(&container).unwrap().len(), 2);
        container.push(0);
        assert!(replay(&container).is_err());
        assert!(replay(&0_u32.to_le_bytes()).is_err());
    }

    #[test]
    fn scalar_and_rgb_use_exact_palette_and_opaque_alpha() {
        let palette: Vec<_> = (0..=255).map(|i| [i, 255 - i, 7]).collect();
        let values: Vec<_> = [-1.0_f32, 0.5, 1.0, 2.0]
            .into_iter()
            .flat_map(f32::to_le_bytes)
            .collect();
        assert_eq!(
            rgba(&values, false, &palette),
            [
                0, 255, 7, 255, 127, 128, 7, 255, 255, 0, 7, 255, 255, 0, 7, 255
            ]
        );
        assert_eq!(
            rgba(&[1, 2, 3, 4, 5, 6], true, &palette),
            [1, 2, 3, 255, 4, 5, 6, 255]
        );
    }
}
