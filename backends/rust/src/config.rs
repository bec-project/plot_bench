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
    pub curves: usize,
    pub waveform_plots: usize,
    pub width: usize,
    pub height: usize,
    pub image_plots: usize,
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
            curves: 1,
            waveform_plots: 1,
            width: 512,
            height: 512,
            image_plots: 1,
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

    /// Bytes of array payload per frame: every waveform plot and curve, every image plot.
    pub fn payload_bytes(&self) -> usize {
        let waveform = if self.view != "image" {
            self.waveform_plots * self.curves * self.points * 4
        } else {
            0
        };
        let image = if self.view != "waveform" {
            self.image_plots
                * self.width
                * self.height
                * if self.image_mode == "scalar" { 4 } else { 3 }
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
        let plots = original
            .updated(json!({"curves":3,"waveform_plots":2,"image_plots":4}))
            .unwrap();
        assert_eq!(
            (plots.curves, plots.waveform_plots, plots.image_plots),
            (3, 2, 4)
        );
        assert_eq!(original.curves, 1);
    }

    #[test]
    fn serializes_fields_in_protocol_order_with_unit_plot_defaults() {
        // The streaming serializer follows the struct order (serde_json::Value sorts keys).
        assert_eq!(
            serde_json::to_string(&Config::default()).unwrap(),
            concat!(
                r#"{"hz":30.0,"points":10000,"append_count":1000,"curves":1,"waveform_plots":1,"#,
                r#""width":512,"height":512,"image_plots":1,"waveform_mode":"replace","#,
                r#""image_mode":"scalar","view":"both","seed":42,"generation":0}"#
            )
        );
        let parsed: Config = serde_json::from_str("{}").unwrap();
        assert_eq!(
            (parsed.curves, parsed.waveform_plots, parsed.image_plots),
            (1, 1, 1)
        );
        assert_eq!(parsed, Config::default());
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
            json!({"curves":0}),
            json!({"curves":65}),
            json!({"curves":true}),
            json!({"curves":1.5}),
            json!({"curves":-1}),
            json!({"waveform_plots":0}),
            json!({"waveform_plots":17}),
            json!({"waveform_plots":true}),
            json!({"waveform_plots":"2"}),
            json!({"image_plots":0}),
            json!({"image_plots":17}),
            json!({"image_plots":true}),
            json!({"image_plots":2.0}),
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
        assert!(
            Config::default()
                .updated(json!({"curves":64,"waveform_plots":16,"image_plots":16}))
                .is_ok()
        );
    }

    #[test]
    fn range_messages_match_the_python_source() {
        for (patch, message) in [
            (json!({"curves":65}), "curves must be between 1 and 64"),
            (
                json!({"waveform_plots":0}),
                "waveform_plots must be between 1 and 16",
            ),
            (
                json!({"image_plots":17}),
                "image_plots must be between 1 and 16",
            ),
            (
                json!({"points":10_000_000,"curves":7,"view":"waveform"}),
                "a frame must fit in 256 MiB",
            ),
        ] {
            let error = Config::default().updated(patch).unwrap_err().to_string();
            assert_eq!(error, message);
        }
    }

    #[test]
    fn payload_bytes_scale_with_plots_and_curves_and_respect_the_view() {
        let base = Config {
            points: 100,
            append_count: 10,
            width: 8,
            height: 4,
            ..Config::default()
        };
        assert_eq!(base.payload_bytes(), 400 + 128);
        let scaled = base
            .updated(json!({"curves":3,"waveform_plots":2,"image_plots":5}))
            .unwrap();
        assert_eq!(scaled.payload_bytes(), 2 * 3 * 400 + 5 * 128);
        assert_eq!(
            scaled
                .updated(json!({"view":"waveform"}))
                .unwrap()
                .payload_bytes(),
            2 * 3 * 400
        );
        assert_eq!(
            scaled
                .updated(json!({"view":"image"}))
                .unwrap()
                .payload_bytes(),
            5 * 128
        );
        assert_eq!(
            scaled
                .updated(json!({"view":"image","image_mode":"rgb"}))
                .unwrap()
                .payload_bytes(),
            5 * 8 * 4 * 3
        );
        // Ignored plot counts are still validated and carried.
        assert!(
            scaled
                .updated(json!({"view":"image","waveform_plots":17}))
                .is_err()
        );
        assert_eq!(
            scaled
                .updated(json!({"view":"image","waveform_plots":16}))
                .unwrap()
                .waveform_plots,
            16
        );
        // 6 waveform plots of 10M points fit; 7 do not. 16 scalar images of 2048² fit; 8192² do not.
        let big = Config::default();
        assert!(
            big.updated(json!({"view":"waveform","points":10_000_000,"waveform_plots":6}))
                .is_ok()
        );
        assert!(
            big.updated(json!({"view":"waveform","points":10_000_000,"waveform_plots":7}))
                .is_err()
        );
        assert!(
            big.updated(json!({"view":"image","width":2048,"height":2048,"image_plots":16}))
                .is_ok()
        );
        assert!(
            big.updated(json!({"view":"image","width":8192,"height":8192,"image_plots":2,"image_mode":"rgb"}))
                .is_err()
        );
    }
}
