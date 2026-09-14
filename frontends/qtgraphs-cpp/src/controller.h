// QML-facing controller: polls the mailbox, updates every Qt Graphs series and image plot, records telemetry.
#pragma once

#include <QJsonObject>
#include <QList>
#include <QObject>
#include <QPointF>
#include <QPointer>
#include <QString>
#include <QStringList>
#include <QVariantList>
#include <QVariantMap>
#include <memory>

#include "frame_source.h"
#include "image_provider.h"
#include "metrics_sink.h"
#include "resource_usage.h"

class QLineSeries;
class QQuickWindow;
class QTimer;

namespace plotbench {

// Shared curve palette (docs/protocol.md): curve `c` of every waveform plot uses index c % 8.
extern const QStringList kCurveColors;

struct Options {
    QString url = QStringLiteral("http://127.0.0.1:8765");
    QString mode = QStringLiteral("stream");
    QString runId = QStringLiteral("demo");
    double duration = 0;
    int width = 1100;
    int height = 820;
};

class Controller : public QObject {
    Q_OBJECT
    Q_PROPERTY(QVariantMap presentation READ presentation NOTIFY hudChanged)
    Q_PROPERTY(QString runMode READ runMode CONSTANT)
    Q_PROPERTY(QVariantMap workload READ workload NOTIFY configChanged)
    Q_PROPERTY(QString metricGuide READ metricGuide CONSTANT)
    Q_PROPERTY(QVariantMap metricTargets READ metricTargets NOTIFY configChanged)
    Q_PROPERTY(QVariantMap plotControls READ plotControls NOTIFY plotControlsChanged)
    Q_PROPERTY(QStringList imageUrls READ imageUrls NOTIFY imageChanged)
    Q_PROPERTY(bool waveformVisible READ waveformVisible NOTIFY configChanged)
    Q_PROPERTY(bool imageVisible READ imageVisible NOTIFY configChanged)
    // Visible plot counts (0 when the kind is hidden by `view`), curves per waveform plot and
    // the shared grid rule columns = ceil(sqrt(waveformPlots + imagePlots)).
    Q_PROPERTY(int waveformPlots READ waveformPlots NOTIFY configChanged)
    Q_PROPERTY(int imagePlots READ imagePlots NOTIFY configChanged)
    Q_PROPERTY(int curves READ curves NOTIFY configChanged)
    // Repeater model of the waveform panels: one entry per visible plot holding its curve count.
    // The list changes value only when the plot or curve count changes, and every change makes
    // the Repeater re-instantiate all panels (GraphsView included); series are never removed
    // from a live GraphsView, which Qt Graphs' PointRenderer does not survive.
    Q_PROPERTY(QVariantList waveformPanels READ waveformPanels NOTIFY configChanged)
    Q_PROPERTY(int gridColumns READ gridColumns NOTIFY configChanged)
    Q_PROPERTY(QStringList waveformTitles READ waveformTitles NOTIFY configChanged)
    Q_PROPERTY(QStringList imageTitles READ imageTitles NOTIFY configChanged)
    Q_PROPERTY(QStringList curveColors READ curveColors CONSTANT)
    Q_PROPERTY(double xMaximum READ xMaximum NOTIFY configChanged)
    Q_PROPERTY(int imageWidth READ imageWidth NOTIFY configChanged)
    Q_PROPERTY(int imageHeight READ imageHeight NOTIFY configChanged)
public:
    Controller(Options options, FrameImageProvider *provider, QObject *parent = nullptr);

    bool start(QQuickWindow *window);
    QString failure() const;
    qint64 submitted() const { return m_sink->count(); }

    QVariantMap presentation() const { return m_presentation; }
    QString runMode() const;
    QVariantMap workload() const;
    QString metricGuide() const;
    QVariantMap metricTargets() const;
    QVariantMap plotControls() const;
    QStringList imageUrls() const { return m_imageUrls; }
    bool waveformVisible() const;
    bool imageVisible() const;
    int waveformPlots() const;
    int imagePlots() const;
    int curves() const;
    QVariantList waveformPanels() const;
    int gridColumns() const;
    QStringList waveformTitles() const;
    QStringList imageTitles() const;
    QStringList curveColors() const { return kCurveColors; }
    double xMaximum() const;
    int imageWidth() const;
    int imageHeight() const;

    Q_INVOKABLE void toggle_plot(const QString &plot);
    Q_INVOKABLE void open_controls();
    // Called by each waveform panel after it (re)built its LineSeries children, in curve order.
    Q_INVOKABLE void register_series(int plot, const QVariantList &series);

public slots:
    void close();

signals:
    void configChanged();
    void imageChanged();
    void hudChanged();
    void plotControlsChanged();

private slots:
    void pollFrame();
    void updateHud();
    void finishDuration();

private:
    QString view() const;
    int configuredWaveformPlots() const;
    int configuredImagePlots() const;
    bool resolveSeries();
    void failFrame(const QString &message);
    void recordDisplayMetadata(double ratio);
    void applyShapeRendererOverride();

    Options m_options;
    FrameImageProvider *m_provider;
    std::unique_ptr<FrameSource> m_source;
    std::unique_ptr<MetricsSink> m_sink;
    ResourceUsage m_resources;
    QQuickWindow *m_window = nullptr;
    QList<QPointer<QLineSeries>> m_series;  // index p * curves + c, matching the payload order
    QList<QList<QPointF>> m_points;         // one preallocated point list per (plot, curve)
    QTimer *m_pollTimer = nullptr;
    QTimer *m_hudTimer = nullptr;
    QJsonObject m_config;
    QVariantMap m_presentation;
    QStringList m_imageUrls;
    QString m_error;
    qint64 m_generation = -1;
    bool m_viewRequestPending = false;
    bool m_durationStarted = false;
    bool m_overrideRequested = false;
};

}  // namespace plotbench
