import json
import xml.etree.ElementTree as ET

import pytest

from plotbench.probe_charts import _label, build_probe_charts


def run(**changes):
    return (
        dict(
            scenario="waveform-10k",
            backend="python",
            config={"view": "waveform", "points": 10000, "seed": 42, "generation": 0},
            target_hz=120,
            measurement_seconds=10,
            status="ok",
            source_hz=120,
            received_hz=119,
        )
        | changes
    )


def test_exact_statistics_count_per_run_target_and_exclude_failures():
    result = build_probe_charts(
        [
            run(received_hz=117.5, source_hz=117.6, target_met=True),
            run(received_hz=120, source_hz=119.8),
            run(received_hz=118.5, source_hz=119),
            run(status="failed", received_hz=9999, source_hz=9999),
        ]
    )
    group = result["comparisons"][0]
    assert (group["attempted"], group["valid"], group["invalid"], group["target_met"]) == (
        4,
        3,
        1,
        2,
    )
    assert group["received_hz"] == {"median": 118.5, "min": 117.5, "max": 120}
    assert group["source_hz"] == {"median": 119, "min": 117.6, "max": 119.8}
    assert "9999" not in result["received_svg"]
    json.dumps(result["comparisons"], allow_nan=False)


def test_backend_and_all_workload_settings_are_isolated_except_generation():
    config = run()["config"]
    rows = [
        run(),
        run(config=config | {"generation": 5}),
        run(backend="rust"),
        run(config=config | {"seed": 99}),
        run(config=config | {"points": 20000}),
        run(target_hz=60),
        run(measurement_seconds=30),
        run(scenario="another-scenario"),
    ]
    groups = build_probe_charts(rows)["comparisons"]
    assert len(groups) == 7
    assert sorted(group["attempted"] for group in groups) == [1, 1, 1, 1, 1, 1, 2]
    assert next(group for group in groups if group["attempted"] == 2)["config"] == {
        "view": "waveform",
        "points": 10000,
        "seed": 42,
    }
    assert rows[0]["config"]["generation"] == 0


def test_unknown_configurations_remain_separate_attempts():
    groups = build_probe_charts([run(config=None), run(config=None), run(config={})])["comparisons"]
    assert len(groups) == 3
    assert all(group["attempted"] == 1 and not group["config_known"] for group in groups)
    assert all(group["valid"] == 1 for group in groups)


def test_different_source_revisions_are_not_pooled_into_repetitions():
    groups = build_probe_charts(
        [
            run(provenance={"source_sha256": "A"}),
            run(provenance={"source_sha256": "B"}),
            run(provenance={"source_sha256": "A"}),
        ]
    )["comparisons"]
    assert sorted(group["valid"] for group in groups) == [1, 2]


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), -float("inf"), -1, None, True, "120"]
)
@pytest.mark.parametrize("field", ["source_hz", "received_hz"])
def test_incomplete_or_invalid_paired_rates_are_not_charted(field, value):
    result = build_probe_charts([run(**{field: value})])
    assert result["comparisons"][0]["invalid"] == 1
    assert result["received_svg"] is None
    assert result["delivery_svg"] is None
    json.dumps(result["comparisons"], allow_nan=False)


@pytest.mark.parametrize("field", ["target_hz", "measurement_seconds"])
@pytest.mark.parametrize("value", [0, -1, None, float("nan")])
def test_positive_target_and_duration_are_required(field, value):
    result = build_probe_charts([run(**{field: value})])
    assert result["comparisons"][0][field] is None
    assert result["received_svg"] is None
    json.dumps(result["comparisons"], allow_nan=False)


def test_zero_rates_are_valid_and_all_failed_or_empty_data_has_no_svg():
    result = build_probe_charts([run(received_hz=0, source_hz=0)])
    assert result["comparisons"][0]["received_hz"] == {"median": 0, "min": 0, "max": 0}
    assert result["comparisons"][0]["valid"] == 1
    assert result["comparisons"][0]["target_met"] == 0
    assert 'width="0.00"' in result["received_svg"]
    for rows in ([], [run(status="failed")]):
        charts = build_probe_charts(rows)
        assert charts["received_svg"] is None and charts["delivery_svg"] is None


def test_varied_targets_standalone_namespace_accessibility_and_text_escaping():
    scenario = '<script>alert("x")</script> & ' + "very-long-workload-name " * 20
    charts = build_probe_charts(
        [
            run(scenario=scenario, backend='custom<&"', target_hz=5, source_hz=7, received_hz=6),
            run(target_hz=600, source_hz=580, received_hz=590),
        ]
    )
    for name in ("received_svg", "delivery_svg"):
        svg = charts[name]
        root = ET.fromstring(svg)
        ns = {"s": "http://www.w3.org/2000/svg"}
        assert root.tag == "{http://www.w3.org/2000/svg}svg"
        assert root.get("width") == "1100"
        assert root.find("s:title", ns).text
        assert "98%" in root.find("s:desc", ns).text
        ticks = [element.text for element in root.findall("s:text", ns)]
        assert all(value in ticks for value in ("0", "200", "400", "600"))
        assert "<script>" not in svg
        assert scenario in "".join(root.itertext())
        assert any(element.get("stroke-dasharray") for element in root.iter())
        assert root.find("s:rect", ns).get("fill") == "#11202a"
    assert "<circle" in charts["delivery_svg"]
    assert "Received + decoded" in charts["delivery_svg"]


def test_same_rates_preserve_both_delivery_markers_and_extreme_rates_are_finite():
    charts = build_probe_charts([run(source_hz=1e308, received_hz=1e308, target_hz=1e308)] * 2)
    assert charts["comparisons"][0]["source_hz"]["median"] == 1e308
    for key in ("received_svg", "delivery_svg"):
        assert "inf" not in charts[key].lower()
        ET.fromstring(charts[key])
    assert 'r="7"' in charts["delivery_svg"] and 'width="8"' in charts["delivery_svg"]


def test_labels_prefix_plot_and_curve_counts_only_when_they_exceed_one():
    def label(**config):
        charts = build_probe_charts([run(config=run()["config"] | config)])
        root = ET.fromstring(charts["received_svg"])
        return [element.text for element in root.iter("{http://www.w3.org/2000/svg}text")]

    def compact(**config):
        return _label({"config": run()["config"] | config, "scenario": "wide"})

    assert "10k-point waveform" in label()
    assert "10k-point waveform" in label(curves=1, waveform_plots=1)
    assert "2 × 3-curve 10k-point waveforms" in label(curves=3, waveform_plots=2)
    assert "3-curve 10k-point waveform" in label(curves=3)
    assert "2 × 10k-point waveforms" in label(waveform_plots=2)
    image = dict(view="image", width=512, height=512, image_mode="scalar")
    assert "512² scalar image" in label(**image)
    assert "4 × 512² scalar images" in label(**image, image_plots=4)
    assert "4 × 512² RGB images" in label(**(image | dict(image_mode="rgb", image_plots=4)))
    both = dict(view="both", points=10_000, width=256, height=256, image_mode="scalar")
    assert "10k wf + 256² img" in label(**both)
    # Longer combined labels are shortened in the chart row; check the full compact form.
    assert "2 × 3-curve 10k wf + 3 × 256²…" in label(
        **both, curves=3, waveform_plots=2, image_plots=3
    )
    assert (
        compact(**both, curves=3, waveform_plots=2, image_plots=3)
        == "2 × 3-curve 10k wf + 3 × 256² img"
    )
    assert (
        compact(**(both | dict(curves=3, width=512, image_mode="rgb", image_plots=4)))
        == "3-curve 10k wf + 4 × 512 × 256 RGB img"
    )


def test_plot_and_curve_counts_are_separate_groups_ordered_by_count():
    charts = build_probe_charts(
        [
            run(scenario="wide", config=run()["config"] | {"waveform_plots": 4}),
            run(scenario="wide", config=run()["config"] | {"waveform_plots": 2}),
            run(scenario="narrow"),
        ]
    )
    groups = charts["comparisons"]
    assert [group["scenario"] for group in groups] == ["narrow", "wide", "wide"]
    assert [group["config"].get("waveform_plots", 1) for group in groups] == [1, 2, 4]
    assert all(group["valid"] for group in groups)
