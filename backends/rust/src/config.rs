use anyhow::{Result, bail, ensure};
use serde::{Deserialize, Serialize};
use serde_json::Value;

pub const MAX_PAYLOAD: usize = 256 * 1024 * 1024;

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(default, deny_unknown_fields)]
pub struct Config {
    pub hz: f64,
    pub points: usize,
    pub append_count: usize,
    pub width: usize,
    pub height: usize,
    pub waveform_mode: String,
    pub image_mode: String,
    pub view: String,
    pub seed: u64,
    pub generation: u64,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            hz: 30.0,
            points: 10_000,
            append_count: 1_000,
            width: 512,
            height: 512,
            waveform_mode: "replace".into(),
            image_mode: "scalar".into(),
            view: "both".into(),
            seed: 42,
            generation: 0,
        }
    }
}

impl Config {
    pub fn validate(&self) -> Result<()> {
        ensure!(
            self.hz.is_finite() && self.hz > 0.0 && self.hz <= 120.0,
            "hz must be greater than zero and at most 120"
        );
        ensure!(
            self.points > 0 && self.append_count > 0 && self.width > 0 && self.height > 0,
            "dimensions and append_count must be positive integers"
        );
        ensure!(
            self.append_count <= self.points,
            "append_count must not exceed points"
        );
        ensure!(
            ["replace", "append"].contains(&self.waveform_mode.as_str()),
            "invalid waveform_mode"
        );
        ensure!(
            ["scalar", "rgb"].contains(&self.image_mode.as_str()),
            "invalid image_mode"
        );
        ensure!(
            ["waveform", "image", "both"].contains(&self.view.as_str()),
            "invalid view"
        );
        ensure!(
            self.points <= 10_000_000 && self.width <= 8192 && self.height <= 8192,
            "maximum dimensions: 10M waveform samples and 8192 image pixels/axis"
        );
        ensure!(
            self.payload_bytes() <= MAX_PAYLOAD,
            "a frame must fit in 256 MiB"
        );
        Ok(())
    }

    pub fn payload_bytes(&self) -> usize {
        let waveform = if self.view != "image" {
            self.points * 4
        } else {
            0
        };
        let image = if self.view != "waveform" {
            self.width * self.height * if self.image_mode == "scalar" { 4 } else { 3 }
        } else {
            0
        };
        waveform + image
    }

    pub fn updated(&self, patch: Value) -> Result<Self> {
        let Some(patch) = patch.as_object() else {
            bail!("configuration must be a JSON object");
        };
        let mut config = serde_json::to_value(self)?;
        let object = config
            .as_object_mut()
            .expect("Config serializes to an object");
        for (key, value) in patch {
            ensure!(
                key != "generation" && object.contains_key(key),
                "unknown or read-only field: {key}"
            );
            object.insert(key.clone(), value.clone());
        }
        object.insert(
            "generation".into(),
            self.generation
                .checked_add(1)
                .ok_or_else(|| anyhow::anyhow!("generation exhausted u64"))?
                .into(),
        );
        let next: Self = serde_json::from_value(config)?;
        next.validate()?;
        Ok(next)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn patches_preserve_unspecified_values_and_always_increment_generation() {
        let original = Config::default();
        let changed = original.updated(json!({"view":"waveform"})).unwrap();
        assert_eq!(changed.points, original.points);
        assert_eq!(changed.generation, 1);
        assert_eq!(changed.updated(json!({})).unwrap().generation, 2);
        assert_eq!(original.view, "both");
    }

    #[test]
    fn rejects_unknown_readonly_types_ranges_and_oversized_payloads() {
        for patch in [
            json!({"generation":4}),
            json!({"bogus":1}),
            json!({"points":true}),
            json!({"points":1.5}),
            json!({"seed":-1}),
            json!({"hz":0}),
            json!({"hz":121}),
            json!({"points":1}),
            json!({"width":8193}),
            json!({"view":"none"}),
            json!({"width":8192,"height":8192}),
            json!([]),
        ] {
            assert!(
                Config::default().updated(patch.clone()).is_err(),
                "accepted {patch}"
            );
        }
        assert!(
            Config::default()
                .updated(json!({"width":8192,"height":8192,"view":"image"}))
                .is_ok()
        );
        assert!(Config::default().updated(json!({"hz":0.1})).is_ok());
    }
}
