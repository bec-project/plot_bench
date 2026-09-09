use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Serialize};
use std::sync::Arc;

pub const MAX_PACKET: usize = 257 * 1024 * 1024;
pub const MAX_REPLAY: usize = 256 * 1024 * 1024;

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Config {
    pub hz: f64,
    pub points: usize,
    pub append_count: usize,
    pub width: u32,
    pub height: u32,
    pub waveform_mode: String,
    pub image_mode: String,
    pub view: String,
    #[serde(flatten)]
    pub extra: serde_json::Map<String, serde_json::Value>,
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
        ensure!(header.version == 1, "Unsupported protocol version");
        let payload = (end + 3) & !3;
        ensure!(payload <= bytes.len(), "Missing header padding");
        ensure!(
            header.emitted_at_ms.is_finite(),
            "Invalid emission timestamp"
        );
        let c = &header.config;
        ensure!(
            c.hz.is_finite() && c.hz > 0.0 && c.hz <= 120.0,
            "Invalid Hz"
        );
        ensure!(
            c.points > 0 && c.width > 0 && c.height > 0,
            "Empty dimensions"
        );
        ensure!(
            c.append_count > 0 && c.append_count <= c.points,
            "Invalid append count"
        );
        ensure!(
            ["replace", "append"].contains(&c.waveform_mode.as_str()),
            "Invalid waveform mode"
        );
        ensure!(
            ["rgb", "scalar"].contains(&c.image_mode.as_str()),
            "Invalid image mode"
        );
        ensure!(
            ["waveform", "image", "both"].contains(&c.view.as_str()),
            "Invalid view"
        );
        let mut names = Vec::new();
        let mut payload_end = 0;
        for a in &header.arrays {
            ensure!(!names.contains(&a.name.as_str()), "Duplicate array name");
            names.push(a.name.as_str());
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
            match a.name.as_str() {
                "waveform" => ensure!(
                    a.dtype == "float32" && a.shape == [c.points],
                    "Invalid waveform shape or dtype"
                ),
                "image" if c.image_mode == "rgb" => ensure!(
                    a.dtype == "uint8" && a.shape == [c.height as usize, c.width as usize, 3],
                    "Invalid RGB shape or dtype"
                ),
                "image" => ensure!(
                    a.dtype == "float32" && a.shape == [c.height as usize, c.width as usize],
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

    pub fn array(&self, name: &str) -> Option<&[u8]> {
        self.header
            .arrays
            .iter()
            .find(|a| a.name == name)
            .map(|a| &self.bytes[self.payload + a.offset..self.payload + a.offset + a.nbytes])
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
mod tests {
    use super::*;
    use serde_json::json;

    fn packet() -> Vec<u8> {
        let h = json!({"version":1,"seq":9,"generation":2,"emitted_at_ms":1234.5,
            "config":{"hz":120,"points":2,"append_count":1,"width":1,"height":1,
                "waveform_mode":"append","image_mode":"scalar","view":"both"},
            "arrays":[{"name":"waveform","dtype":"float32","shape":[2],"offset":0,"nbytes":8},
                {"name":"image","dtype":"float32","shape":[1,1],"offset":8,"nbytes":4}]});
        let json = serde_json::to_vec(&h).unwrap();
        let mut bytes = (json.len() as u32).to_le_bytes().to_vec();
        bytes.extend(json);
        while !bytes.len().is_multiple_of(4) {
            bytes.push(0);
        }
        for value in [-1.0_f32, 1.0, 0.5] {
            bytes.extend(value.to_le_bytes());
        }
        bytes
    }

    #[test]
    fn decodes_authoritative_append_window() {
        let p = Packet::parse(packet().into()).unwrap();
        assert_eq!(p.header.seq, 9);
        assert_eq!(p.header.config.waveform_mode, "append");
        assert_eq!(
            p.array("waveform").unwrap(),
            [(-1.0_f32).to_le_bytes(), 1.0_f32.to_le_bytes()].concat()
        );
    }

    #[test]
    fn rejects_truncation_and_bad_version() {
        let bytes = packet();
        assert!(Packet::parse(bytes[..bytes.len() - 1].into()).is_err());
        assert!(Packet::parse(Arc::from([255, 255, 255, 255])).is_err());
        let changed = String::from_utf8_lossy(&bytes)
            .replace("\"version\":1", "\"version\":2")
            .into_bytes();
        assert!(Packet::parse(changed.into()).is_err());
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
