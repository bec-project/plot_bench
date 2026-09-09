#include "controller.h"

#include <QDesktopServices>
#include <QElapsedTimer>
#include <QGuiApplication>
#include <QLineSeries>
#include <QQuickWindow>
#include <QRectF>
#include <QSGRendererInterface>
#include <QScreen>
#include <QTimer>
#include <QUrl>
#include <QtEndian>
#include <QtGlobal>
#include <algorithm>
#include <chrono>

namespace plotbench {

namespace {

const char *const kMetricGuide =
    "Targets follow the current input frame rate. The update budget is one source period and excludes "
    "deferred GPU and display presentation work. The receive-age goal is indicative; it is not a latency "
    "guarantee. These are not displayed-FPS measurements. Replay has no receive age.";

const char *const kRendererEnvironment[] = {
    "QT_QPA_PLATFORM", "QT_OPENGL", "QT_QUICK_BACKEND", "QSG_RHI_BACKEND", "QSG_RENDER_LOOP",
    "QSG_RHI_PREFER_SOFTWARE_RENDERER", "QSG_RHI_DEBUG_LAYER", "QT_SCALE_FACTOR", "QT_SCREEN_SCALE_FACTORS",
    "QT_SCALE_FACTOR_ROUNDING_POLICY", "QT_ENABLE_HIGHDPI_SCALING", "QT_AUTO_SCREEN_SCALE_FACTOR",
    "QT_DEVICE_PIXEL_RATIO",
};

QVariantList rect(const QRect &r) {
    return {r.x(), r.y(), r.width(), r.height()};
}

QString formatThousands(qint64 value) {
    return QLocale(QLocale::English).toString(value);
}

}  // namespace

Controller::Controller(Options options, FrameImageProvider *provider, QObject *parent)
    : QObject(parent), m_options(std::move(options)), m_provider(provider) {
    m_presentation = {
        {QStringLiteral("submitted"), QStringLiteral("—")},
        {QStringLiteral("update"), QStringLiteral("—")},
        {QStringLiteral("skipped"), QStringLiteral("—")},
        {QStringLiteral("age"), QStringLiteral("—")},
        {QStringLiteral("ageUnit"), QString()},
        {QStringLiteral("state"), QStringLiteral("Connecting")},
        {QStringLiteral("error"), false},
        {QStringLiteral("details"), QStringLiteral("Connecting to the shared producer")},
        {QStringLiteral("resources"), QStringLiteral("Custom Qt Quick image (C++)")},
        {QStringLiteral("renderer"), QStringLiteral("Qt Quick")},
    };
    m_source = std::make_unique<FrameSource>(m_options.url, m_options.mode);
    QVariantMap environment;
    for (const char *name : kRendererEnvironment) {
        environment.insert(QLatin1String(name), qEnvironmentVariableIsSet(name) ? QVariant(qEnvironmentVariable(name)) : QVariant());
    }
    QVariantMap metadata{
        {QStringLiteral("measurement_stage"),
         QStringLiteral("QXYSeries::replace(QList<QPointF>) + scalar index conversion into an Indexed8 QImage with "
                        "the shared colour table (RGB frames wrap the packet bytes) + synchronous QML image-provider "
                        "submission; palette expansion and texture upload happen on the scene-graph render thread "
                        "and are excluded; GPU work excluded")},
        {QStringLiteral("renderer"), QStringLiteral("Qt Graphs LineSeries / Qt Quick scene graph (C++)")},
        {QStringLiteral("language"), QStringLiteral("C++")},
        {QStringLiteral("qsg_rhi_backend_override"), environment.value(QStringLiteral("QSG_RHI_BACKEND"))},
        {QStringLiteral("qt_quick_backend_override"), environment.value(QStringLiteral("QT_QUICK_BACKEND"))},
        {QStringLiteral("image_renderer"),
         QStringLiteral("CUSTOM QQuickImageProvider + Qt Quick Image (Indexed8 with colour table for scalar, RGB888 "
                        "for RGB); NOT a native Qt Graphs image series")},
        {QStringLiteral("custom_work"),
         QStringLiteral("image provider, scalar index conversion, image-provider invalidation and QML image "
                        "axes/layout require additional implementation")},
        {QStringLiteral("update_strategy"),
         QStringLiteral("full authoritative window QXYSeries::replace in replace AND append; one QList<QPointF> is "
                        "rewritten per frame")},
        {QStringLiteral("downsampling"), false},
        {QStringLiteral("antialias"), false},
        {QStringLiteral("versions"),
         QVariantMap{{QStringLiteral("qt"), QString::fromLatin1(qVersion())},
                     {QStringLiteral("app"), QStringLiteral(PLOTBENCH_APP_VERSION)},
                     {QStringLiteral("build_type"), QStringLiteral(PLOTBENCH_BUILD_TYPE)},
#if defined(__clang_version__)
                     {QStringLiteral("compiler"), QStringLiteral("clang ") + QLatin1String(__clang_version__)},
#elif defined(__VERSION__)
                     {QStringLiteral("compiler"), QLatin1String(__VERSION__)},
#endif
         }},
        {QStringLiteral("renderer_environment"), environment},
        {QStringLiteral("qt_platform_plugin"), QGuiApplication::platformName()},
    };
    m_sink = std::make_unique<MetricsSink>(m_options.url, QStringLiteral("qtgraphs-cpp"), m_options.mode,
                                           m_options.runId, m_options.duration, metadata);
    m_pollTimer = new QTimer(this);
    m_pollTimer->setTimerType(Qt::PreciseTimer);
    connect(m_pollTimer, &QTimer::timeout, this, &Controller::pollFrame);
    m_hudTimer = new QTimer(this);
    connect(m_hudTimer, &QTimer::timeout, this, &Controller::updateHud);
}

bool Controller::start(QQuickWindow *window) {
    m_window = window;
    m_series = window->findChild<QLineSeries *>(QStringLiteral("waveformSeries"));
    if (!m_series) {
        m_error = QStringLiteral("QML did not create the required Qt Graphs LineSeries");
        return false;
    }
    applyShapeRendererOverride();
    m_source->start();
    m_pollTimer->start(1);
    m_hudTimer->start(500);
    return true;
}

void Controller::applyShapeRendererOverride() {
    // Diagnostic only, off by default. Qt Graphs draws 2D series through a private
    // QQuickShape whose renderer type and asynchronous processing the public API does
    // not expose. PLOTBENCH_QTGRAPHS_SHAPE_RENDERER=geometry|curve|software and
    // PLOTBENCH_QTGRAPHS_SHAPE_ASYNC=1 reach that object through the item tree once Qt
    // Graphs has created it (after the first series update); the outcome is recorded in
    // metadata so such runs are never mistaken for the default configuration.
    const QString renderer = qEnvironmentVariable("PLOTBENCH_QTGRAPHS_SHAPE_RENDERER").toLower();
    const bool asynchronous = qEnvironmentVariableIntValue("PLOTBENCH_QTGRAPHS_SHAPE_ASYNC") > 0;
    QVariantMap record{
        {QStringLiteral("requested_renderer"), renderer.isEmpty() ? QVariant() : QVariant(renderer)},
        {QStringLiteral("requested_asynchronous"),
         qEnvironmentVariableIsSet("PLOTBENCH_QTGRAPHS_SHAPE_ASYNC") ? QVariant(asynchronous) : QVariant()},
        {QStringLiteral("applied_to_shapes"), 0},
    };
    m_overrideRequested = !renderer.isEmpty() || asynchronous;
    if (m_overrideRequested) {
        // QQuickShape::RendererType: GeometryRenderer = 1, SoftwareRenderer = 3, CurveRenderer = 4.
        const int type = renderer == QLatin1String("geometry") ? 1 : renderer == QLatin1String("software") ? 3
                         : renderer == QLatin1String("curve")   ? 4 : 0;
        int applied = 0;
        for (QObject *child : m_window->findChildren<QObject *>()) {
            if (!child->inherits("QQuickShape")) {
                continue;
            }
            if (type) {
                child->setProperty("preferredRendererType", type);
            }
            if (asynchronous) {
                child->setProperty("asynchronous", true);
            }
            ++applied;
        }
        record.insert(QStringLiteral("applied_to_shapes"), applied);
        if (applied) {
            m_overrideRequested = false;  // done; stop retrying at HUD cadence
        }
    }
    m_sink->metadata().insert(QStringLiteral("shape_renderer_override"), record);
}

QString Controller::failure() const {
    for (const QString &candidate : {m_error, m_source->error(), m_sink->error()}) {
        if (!candidate.isEmpty()) {
            return candidate;
        }
    }
    return QString();
}

QString Controller::runMode() const {
    QString mode = m_options.mode;
    if (!mode.isEmpty()) {
        mode[0] = mode[0].toUpper();
    }
    return mode;
}

QString Controller::view() const {
    return m_config.value(QStringLiteral("view")).toString();
}

QVariantMap Controller::workload() const {
    if (m_config.isEmpty()) {
        return {
            {QStringLiteral("target"), QStringLiteral("—")},
            {QStringLiteral("waveform"), QStringLiteral("—")},
            {QStringLiteral("image"), QStringLiteral("—")},
            {QStringLiteral("waveformSubtitle"), QStringLiteral("Waiting for source")},
            {QStringLiteral("imageSubtitle"), QStringLiteral("Waiting for source")},
        };
    }
    const bool rgb = m_config.value(QStringLiteral("image_mode")).toString() == QLatin1String("rgb");
    const QString points = formatThousands(qint64(m_config.value(QStringLiteral("points")).toDouble()));
    const QString mode = m_config.value(QStringLiteral("waveform_mode")).toString();
    const QString size = QStringLiteral("%1 × %2").arg(m_config.value(QStringLiteral("width")).toInt()).arg(m_config.value(QStringLiteral("height")).toInt());
    return {
        {QStringLiteral("target"), QStringLiteral("%1 Hz").arg(m_config.value(QStringLiteral("hz")).toDouble())},
        {QStringLiteral("waveform"), QStringLiteral("%1 · %2").arg(points, mode)},
        {QStringLiteral("image"), QStringLiteral("%1 · %2").arg(size, rgb ? QStringLiteral("RGB") : QStringLiteral("scalar"))},
        {QStringLiteral("waveformSubtitle"), QStringLiteral("%1 points · %2").arg(points, mode)},
        {QStringLiteral("imageSubtitle"), QStringLiteral("%1 · %2").arg(size, rgb ? QStringLiteral("RGB") : QStringLiteral("scalar colormap"))},
    };
}

QString Controller::metricGuide() const {
    return QLatin1String(kMetricGuide);
}

QVariantMap Controller::metricTargets() const {
    QVariantMap targets{
        {QStringLiteral("submitted"), QStringLiteral("(waiting for source)")},
        {QStringLiteral("update"), QStringLiteral("(waiting for source)")},
        {QStringLiteral("skipped"), QStringLiteral("(target 0)")},
        {QStringLiteral("age"), QStringLiteral("(waiting for source)")},
    };
    if (m_config.contains(QStringLiteral("hz"))) {
        const double hz = m_config.value(QStringLiteral("hz")).toDouble();
        const double period = 1000.0 / hz;
        targets.insert(QStringLiteral("submitted"), QStringLiteral("(target %1/s)").arg(hz));
        targets.insert(QStringLiteral("update"), QStringLiteral("(budget ≤%1 ms)").arg(period, 0, 'f', 2));
        targets.insert(QStringLiteral("age"), QStringLiteral("(goal <%1 ms)").arg(period, 0, 'f', 2));
    }
    if (m_options.mode == QLatin1String("replay")) {
        targets.insert(QStringLiteral("age"), QStringLiteral("(N/A in replay)"));
    }
    return targets;
}

QVariantMap Controller::plotControls() const {
    const QString current = view();
    const bool pending = m_viewRequestPending || m_source->viewPending();
    const bool locked = m_options.duration > 0;
    const bool available = !current.isEmpty() && !(pending || locked);
    QString reason;
    if (locked) {
        reason = QStringLiteral("Locked during recorded runs");
    } else if (current.isEmpty()) {
        reason = QStringLiteral("Waiting for the shared source");
    } else if (pending) {
        reason = QStringLiteral("Updating shared source…");
    } else if (!m_source->viewError().isEmpty()) {
        reason = m_source->viewError();
    } else {
        reason = QStringLiteral("Update the shared source");
        if (m_options.mode == QLatin1String("replay")) {
            reason += QStringLiteral(" and reload replay");
        }
    }
    const QString last = QStringLiteral("At least one plot must remain enabled");
    return {
        {QStringLiteral("waveformChecked"), current == QLatin1String("waveform") || current == QLatin1String("both")},
        {QStringLiteral("imageChecked"), current == QLatin1String("image") || current == QLatin1String("both")},
        {QStringLiteral("waveformEnabled"), available && current != QLatin1String("waveform")},
        {QStringLiteral("imageEnabled"), available && current != QLatin1String("image")},
        {QStringLiteral("waveformTooltip"), QStringLiteral("1D waveform · ") + ((available && current == QLatin1String("waveform")) ? last : reason)},
        {QStringLiteral("imageTooltip"), QStringLiteral("2D image · ") + ((available && current == QLatin1String("image")) ? last : reason)},
    };
}

bool Controller::waveformVisible() const {
    const QString current = m_config.isEmpty() ? QStringLiteral("both") : view();
    return current == QLatin1String("waveform") || current == QLatin1String("both");
}

bool Controller::imageVisible() const {
    const QString current = m_config.isEmpty() ? QStringLiteral("both") : view();
    return current == QLatin1String("image") || current == QLatin1String("both");
}

double Controller::xMaximum() const {
    return double(std::max(1, m_config.value(QStringLiteral("points")).toInt(10000) - 1));
}

int Controller::imageWidth() const {
    return m_config.value(QStringLiteral("width")).toInt(512);
}

int Controller::imageHeight() const {
    return m_config.value(QStringLiteral("height")).toInt(512);
}

void Controller::toggle_plot(const QString &plot) {
    const QString current = view();
    if (current.isEmpty() || m_options.duration > 0 || m_viewRequestPending || m_source->viewPending()
        || (plot != QLatin1String("waveform") && plot != QLatin1String("image"))) {
        emit plotControlsChanged();
        return;
    }
    QStringList selected = current == QLatin1String("both") ? QStringList{QStringLiteral("waveform"), QStringLiteral("image")} : QStringList{current};
    if (selected.contains(plot)) {
        selected.removeAll(plot);
    } else {
        selected.append(plot);
    }
    if (!selected.isEmpty()) {
        m_viewRequestPending = m_source->requestView(selected.size() == 2 ? QStringLiteral("both") : selected.first());
    }
    emit plotControlsChanged();
}

void Controller::open_controls() {
    QDesktopServices::openUrl(QUrl(m_options.url));
}

void Controller::pollFrame() {
    std::optional<Frame> frame = m_source->takeLatest();
    if (!frame) {
        return;
    }
    if (!m_source->viewPending()) {
        m_viewRequestPending = false;
    }
    QElapsedTimer timer;
    timer.start();
    if (frame->generation != m_generation) {
        m_config = frame->config;
        const int points = m_config.value(QStringLiteral("points")).toInt();
        if (m_points.size() != points) {
            m_points.resize(points);
            for (int index = 0; index < points; ++index) {
                m_points[index] = QPointF(index, 0.0);
            }
        }
        m_generation = frame->generation;
        emit configChanged();
        emit plotControlsChanged();
    }
    if (frame->has(QStringLiteral("waveform"))) {
        const ArrayView &view = frame->arrays.value(QStringLiteral("waveform"));
        const uchar *data = reinterpret_cast<const uchar *>(frame->data(view));
        const qsizetype count = std::min<qsizetype>(view.count, m_points.size());
        QPointF *points = m_points.data();  // detaches from the series' shared copy: the true replace cost
        for (qsizetype index = 0; index < count; ++index) {
            points[index].setY(qFromLittleEndian<float>(data + index * 4));
        }
        m_series->replace(m_points);
    }
    double conversionMs = 0;
    if (frame->has(QStringLiteral("image"))) {
        QElapsedTimer conversion;
        conversion.start();
        m_provider->updateImage(*frame, frame->arrays.value(QStringLiteral("image")));
        conversionMs = conversion.nsecsElapsed() / 1e6;
        m_imageUrl = QStringLiteral("image://frames/%1/%2").arg(frame->generation).arg(frame->presentationSeq);
        emit imageChanged();
    }
    const double updateMs = timer.nsecsElapsed() / 1e6;
    m_sink->record(*frame, updateMs, conversionMs);
    const QVariantMap sourceMetadata = m_source->metadata();
    for (auto it = sourceMetadata.cbegin(); it != sourceMetadata.cend(); ++it) {
        m_sink->metadata().insert(it.key(), it.value());
    }
    if (m_options.duration > 0 && !m_durationStarted) {
        m_durationStarted = true;
        QTimer::singleShot(int(std::lround(m_options.duration * 1000)), this, &Controller::finishDuration);
    }
}

void Controller::recordDisplayMetadata(double ratio) {
    QVariantMap &metadata = m_sink->metadata();
    QVariantMap environment;
    for (const char *name : kRendererEnvironment) {
        environment.insert(QLatin1String(name), qEnvironmentVariableIsSet(name) ? QVariant(qEnvironmentVariable(name)) : QVariant());
    }
    metadata.insert(QStringLiteral("renderer_environment"), environment);
    metadata.insert(QStringLiteral("qt_platform_plugin"), QGuiApplication::platformName());
    QScreen *screen = m_window->screen();
    if (!screen) {
        metadata.insert(QStringLiteral("display"), QVariant());
        return;
    }
    using namespace std::chrono;
    metadata.insert(QStringLiteral("display"),
                    QVariantMap{
                        {QStringLiteral("name"), screen->name()},
                        {QStringLiteral("manufacturer"), screen->manufacturer()},
                        {QStringLiteral("model"), screen->model()},
                        {QStringLiteral("refresh_hz"), screen->refreshRate()},
                        {QStringLiteral("refresh_source"), QStringLiteral("QScreen::refreshRate; reported nominal rate, not measured presentation")},
                        {QStringLiteral("geometry"), rect(screen->geometry())},
                        {QStringLiteral("available_geometry"), rect(screen->availableGeometry())},
                        {QStringLiteral("window_geometry"), QGuiApplication::platformName() == QLatin1String("wayland")
                            ? QVariantList{QVariant(), QVariant(), m_window->width(), m_window->height()} : rect(m_window->geometry())},
                        {QStringLiteral("window_position_available"), QGuiApplication::platformName() != QLatin1String("wayland")},
                        {QStringLiteral("geometry_units"), QStringLiteral("logical pixels; [x, y, width, height]")},
                        {QStringLiteral("device_pixel_ratio"), screen->devicePixelRatio()},
                        {QStringLiteral("window_device_pixel_ratio"), ratio},
                        {QStringLiteral("logical_dpi"), QVariantList{screen->logicalDotsPerInchX(), screen->logicalDotsPerInchY()}},
                        {QStringLiteral("physical_dpi"), QVariantList{screen->physicalDotsPerInchX(), screen->physicalDotsPerInchY()}},
                        {QStringLiteral("physical_size_mm"), QVariantList{screen->physicalSize().width(), screen->physicalSize().height()}},
                        {QStringLiteral("recorded_at_ms"), wallClockMs()},
                    });
}

void Controller::updateHud() {
    const Snapshot metrics = m_sink->snapshot();
    if (!m_source->viewError().isEmpty() || !m_source->error().isEmpty()) {
        m_viewRequestPending = false;
    }
    QString error;
    for (const QString &candidate : {m_error, m_source->error(), m_sink->error(), m_source->viewError()}) {
        if (!candidate.isEmpty()) {
            error = candidate;
            break;
        }
    }
    QString state = !error.isEmpty() ? QStringLiteral("Source error")
                    : m_options.mode == QLatin1String("replay") ? QStringLiteral("Replaying")
                                                                  : QStringLiteral("Streaming");
    if (metrics.count == 0 && error.isEmpty()) {
        state = QStringLiteral("Connecting");
    }
    const double ratio = m_window->devicePixelRatio();
    QString graphicsApi = QStringLiteral("unknown");
    if (const QSGRendererInterface *renderer = m_window->rendererInterface()) {
        switch (renderer->graphicsApi()) {
        case QSGRendererInterface::Software: graphicsApi = QStringLiteral("Software"); break;
        case QSGRendererInterface::OpenGL: graphicsApi = QStringLiteral("OpenGL"); break;
        case QSGRendererInterface::Direct3D11: graphicsApi = QStringLiteral("Direct3D11"); break;
        case QSGRendererInterface::Direct3D12: graphicsApi = QStringLiteral("Direct3D12"); break;
        case QSGRendererInterface::Vulkan: graphicsApi = QStringLiteral("Vulkan"); break;
        case QSGRendererInterface::Metal: graphicsApi = QStringLiteral("Metal"); break;
        case QSGRendererInterface::Null: graphicsApi = QStringLiteral("Null"); break;
        default: graphicsApi = QStringLiteral("Unknown"); break;
        }
    }
    m_presentation = {
        {QStringLiteral("submitted"), QString::number(metrics.updatesHz, 'f', 1)},
        {QStringLiteral("update"), QString::number(metrics.updateMs, 'f', 2)},
        {QStringLiteral("skipped"), formatThousands(metrics.skipped)},
        {QStringLiteral("age"), metrics.receiveAgeMs ? QString::number(*metrics.receiveAgeMs, 'f', 1) : QStringLiteral("—")},
        {QStringLiteral("ageUnit"), metrics.receiveAgeMs ? QStringLiteral("ms") : (m_options.mode == QLatin1String("replay") ? QStringLiteral("replay") : QString())},
        {QStringLiteral("state"), state},
        {QStringLiteral("error"), !error.isEmpty()},
        {QStringLiteral("details"), error.isEmpty() ? m_source->status() : error},
        {QStringLiteral("resources"), QStringLiteral("CPU %1% · %2 MiB · Custom Qt Quick image (C++)")
                                           .arg(m_resources.cpuPercent(), 0, 'f', 0)
                                           .arg([this]() { const double rss = m_resources.residentMiB();
                                               return std::isfinite(rss) ? QString::number(rss, 'f', 0) : QStringLiteral("N/A"); }())},
        {QStringLiteral("renderer"), graphicsApi},
    };
    emit hudChanged();
    emit plotControlsChanged();
    if (m_overrideRequested) {
        applyShapeRendererOverride();
    }
    recordDisplayMetadata(ratio);
    m_series->setWidth(1.0 / ratio);
    QVariantMap &metadata = m_sink->metadata();
    metadata.insert(QStringLiteral("pixel_ratio"), ratio);
    metadata.insert(QStringLiteral("viewport_size"), QVariantList{m_window->width(), m_window->height()});
    metadata.insert(QStringLiteral("viewport_size_units"), QStringLiteral("logical pixels"));
    metadata.insert(QStringLiteral("plot_viewport_units"), QStringLiteral("physical pixels; data drawing area excluding axes"));
    metadata.insert(QStringLiteral("graphics_api"), graphicsApi);
    QVariantMap viewports{{QStringLiteral("waveform"), QVariant()}, {QStringLiteral("image"), QVariant()}};
    if (QObject *graph = m_window->findChild<QObject *>(QStringLiteral("waveformGraph")); graph && waveformVisible()) {
        const QRectF area = graph->property("plotArea").toRectF();
        viewports.insert(QStringLiteral("waveform"), QVariantList{area.width() * ratio, area.height() * ratio});
    }
    if (QObject *image = m_window->findChild<QObject *>(QStringLiteral("streamImage")); image && imageVisible()) {
        viewports.insert(QStringLiteral("image"), QVariantList{image->property("paintedWidth").toDouble() * ratio,
                                                               image->property("paintedHeight").toDouble() * ratio});
    }
    metadata.insert(QStringLiteral("plot_viewports"), viewports);
}

void Controller::finishDuration() {
    m_sink->markStopped(QStringLiteral("duration"));
    m_window->close();
}

void Controller::close() {
    m_pollTimer->stop();
    m_hudTimer->stop();
    m_sink->markStopped(QStringLiteral("user"));
    m_source->close();
    m_sink->close();
}

}  // namespace plotbench
