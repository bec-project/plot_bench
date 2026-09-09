import pytest
from plotbench.config import Config
from qtpy.QtWidgets import QApplication

from plotbench_matplotlib.dashboard import Dashboard


@pytest.fixture
def dashboard():
    qapp = QApplication.instance() or QApplication([])
    widget = Dashboard("Test", "Renderer", "stream", "http://localhost")
    yield widget
    widget.close()
    qapp.processEvents()


@pytest.mark.parametrize(
    "initial, clicked, expected",
    [
        ("both", "image", "waveform"),
        ("both", "waveform", "image"),
        ("waveform", "image", "both"),
        ("image", "waveform", "both"),
    ],
)
def test_toggle_requests_source_view_and_waits_for_authoritative_frame(
    dashboard, initial, clicked, expected
):
    requests = []

    def request(view):
        requests.append(view)
        dashboard.sync_plot_controls(pending=True)

    dashboard.viewRequested.connect(request)
    dashboard.update_summary(Config(view=initial).to_dict())
    dashboard.plot_buttons[clicked].click()
    assert requests == [expected]
    assert not any(button.isEnabled() for button in dashboard.plot_buttons.values())
    for plot, button in dashboard.plot_buttons.items():
        assert button.isChecked() == (initial in ("both", plot))
    dashboard.update_summary(Config(view=expected).to_dict())
    dashboard.sync_plot_controls()
    assert requests == [expected]
    for plot, button in dashboard.plot_buttons.items():
        assert button.isChecked() == (expected in ("both", plot))


@pytest.mark.parametrize("view", ["waveform", "image"])
def test_last_plot_cannot_be_disabled(dashboard, view):
    requests = []
    dashboard.viewRequested.connect(requests.append)
    dashboard.update_summary(Config(view=view).to_dict())
    assert not dashboard.plot_buttons[view].isEnabled()
    dashboard.plot_buttons[view].click()
    dashboard.request_plot(view, False)
    assert requests == []
    assert dashboard.plot_buttons[view].isChecked()


def test_controls_lock_before_first_frame_and_during_recorded_runs(dashboard):
    requests = []
    dashboard.viewRequested.connect(requests.append)
    assert not any(button.isEnabled() for button in dashboard.plot_buttons.values())
    dashboard.request_plot("image", True)
    dashboard.update_summary(Config(view="both").to_dict())
    dashboard.sync_plot_controls(locked=True)
    dashboard.request_plot("image", False)
    assert not any(button.isEnabled() for button in dashboard.plot_buttons.values())
    assert "Locked during recorded runs" in dashboard.plot_buttons["image"].toolTip()
    assert requests == []


def test_failed_request_restores_actual_state_and_external_config_does_not_request(dashboard):
    requests = []
    dashboard.viewRequested.connect(requests.append)
    dashboard.update_summary(Config(view="both").to_dict())
    dashboard.sync_plot_controls(pending=True)
    dashboard.sync_plot_controls(error="Source unavailable")
    assert all(
        button.isChecked() and button.isEnabled() for button in dashboard.plot_buttons.values()
    )
    assert "Source unavailable" in dashboard.plot_buttons["image"].toolTip()
    dashboard.update_summary(Config(view="image").to_dict())
    assert dashboard.plot_buttons["image"].isChecked()
    assert not dashboard.plot_buttons["waveform"].isChecked()
    assert requests == []


@pytest.mark.parametrize("mode", ["stream", "replay"])
def test_metric_targets_follow_active_frame_rate_and_replay_has_no_age(dashboard, mode):
    dashboard.mode = mode
    dashboard.update_metric_targets(None)
    assert dashboard.metric_targets[0].text() == "(waiting for source)"
    assert dashboard.metric_targets[1].text() == "(waiting for source)"
    assert dashboard.metric_targets[2].text() == "(target 0)"
    for hz, period in [(30, "33.33"), (120, "8.33"), (59.94, "16.68")]:
        dashboard.update_summary(Config(hz=hz).to_dict())
        expected_age = "(N/A in replay)" if mode == "replay" else f"(goal <{period} ms)"
        assert [hint.text() for hint in dashboard.metric_targets] == [
            f"(target {hz:g}/s)",
            f"(budget ≤{period} ms)",
            "(target 0)",
            expected_age,
        ]
    assert "deferred GPU" in dashboard.metric_targets[0].parent().toolTip()
    assert "indicative" in dashboard.metric_targets[3].parent().toolTip()
