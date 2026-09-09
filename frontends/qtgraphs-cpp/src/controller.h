// QML-facing controller: polls the mailbox, updates the Qt Graphs series and the image, records telemetry.
#pragma once

#include <QJsonObject>
#include <QList>
#include <QObject>
#include <QPointF>
#include <QString>
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
    Q_PROPERTY(QString imageUrl READ imageUrl NOTIFY imageChanged)
    Q_PROPERTY(bool waveformVisible READ waveformVisible NOTIFY configChanged)
    Q_PROPERTY(bool imageVisible READ imageVisible NOTIFY configChanged)
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
    QString imageUrl() const { return m_imageUrl; }
    bool waveformVisible() const;
    bool imageVisible() const;
    double xMaximum() const;
    int imageWidth() const;
    int imageHeight() const;

    Q_INVOKABLE void toggle_plot(const QString &plot);
    Q_INVOKABLE void open_controls();

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
    void recordDisplayMetadata(double ratio);
    void applyShapeRendererOverride();

    Options m_options;
    FrameImageProvider *m_provider;
    std::unique_ptr<FrameSource> m_source;
    std::unique_ptr<MetricsSink> m_sink;
    ResourceUsage m_resources;
    QQuickWindow *m_window = nullptr;
    QLineSeries *m_series = nullptr;
    QTimer *m_pollTimer = nullptr;
    QTimer *m_hudTimer = nullptr;
    QJsonObject m_config;
    QVariantMap m_presentation;
    QString m_imageUrl;
    QString m_error;
    QList<QPointF> m_points;
    qint64 m_generation = -1;
    bool m_viewRequestPending = false;
    bool m_durationStarted = false;
    bool m_overrideRequested = false;
};

}  // namespace plotbench
