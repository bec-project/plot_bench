use plotbench_source_rust::{
    config::Config,
    generator::{colormap, make_packet},
};
use serde_json::Value;

#[test]
fn native_generation_matches_python_reference_with_documented_tolerance() {
    let fixtures: Value = serde_json::from_str(include_str!("fixtures/generation.json")).unwrap();
    assert_eq!(
        serde_json::to_value(colormap()).unwrap(),
        fixtures["colormap"]
    );
    let mut max_float_error = 0.0_f64;
    let mut max_rgb_error = 0_i64;
    for case in fixtures["cases"].as_array().unwrap() {
        let config: Config = serde_json::from_value(case["config"].clone()).unwrap();
        let seq = case["seq"].as_u64().unwrap();
        let packet = make_packet(&config, seq).unwrap();
        let length = u32::from_le_bytes(packet.bytes[..4].try_into().unwrap()) as usize;
        let header: Value = serde_json::from_slice(&packet.bytes[4..4 + length]).unwrap();
        let payload = &packet.bytes[(length + 7) & !3..];
        for descriptor in header["arrays"].as_array().unwrap() {
            let name = descriptor["name"].as_str().unwrap();
            let expected = &case["arrays"][name];
            assert_eq!(descriptor["shape"], expected["shape"]);
            assert_eq!(descriptor["dtype"], expected["dtype"]);
            let start = descriptor["offset"].as_u64().unwrap() as usize;
            let end = start + descriptor["nbytes"].as_u64().unwrap() as usize;
            let data = &payload[start..end];
            let reference = expected["values"].as_array().unwrap();
            if descriptor["dtype"] == "float32" {
                assert_eq!(data.len(), reference.len() * 4);
                for (bytes, expected) in data.chunks_exact(4).zip(reference) {
                    let actual = f32::from_le_bytes(bytes.try_into().unwrap()) as f64;
                    let error = (actual - expected.as_f64().unwrap()).abs();
                    max_float_error = max_float_error.max(error);
                    assert!(
                        error <= 3e-6,
                        "{name} seq {seq}: native {actual}, Python {expected}, error {error}"
                    );
                }
            } else {
                assert_eq!(data.len(), reference.len());
                for (actual, expected) in data.iter().zip(reference) {
                    let error = (*actual as i64 - expected.as_i64().unwrap()).abs();
                    max_rgb_error = max_rgb_error.max(error);
                    assert!(error <= 1, "RGB channel differs by {error} at seq {seq}");
                }
            }
        }
    }
    println!(
        "Python fixture maximum absolute f32 error: {max_float_error:e}; maximum RGB difference: {max_rgb_error}"
    );
}
