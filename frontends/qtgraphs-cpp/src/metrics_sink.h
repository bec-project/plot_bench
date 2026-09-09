// Batched telemetry to the source's /api/metrics endpoint, mirroring the Python MetricsSink.
#pragma once

#include <QElapsedTimer>
#include <QJsonArray>
#include <QJsonObject>
#include <QObject>
#include <QString>
#include <QVariantMap>
#include <deque>
#include <optional>

class QNetworkAccessManager;
class QNetworkReply;
class QTimer;

namespace plotbench {

struct Frame;

struct Snapshot {
    double updatesHz = 0;
    double updateMs = 0;
    qint64 skipped = 0;
    std::optional<double> receiveAgeMs;
    qint64 count = 0;
    qint64 telemetryLost = 0;
};

class MetricsSink : public QObject {
    Q_OBJECT
public:
    MetricsSink(const QString &url, const QString &frontend, const QString &mode, const QString &runId,
                double expectedDuration, QVariantMap metadata, QObject *parent = nullptr);

    void record(const Frame &frame, double updateMs, double conversionMs);
    Snapshot snapshot() const;
    void markStopped(const QString &reason = QString());
    void close();  // flushes the final batch and waits for it (bounded)
    QString error() const { return m_error; }
    QVariantMap &metadata() { return m_metadata; }
    qint64 count() const { return m_count; }

private:
    void flush(bool forceMetadata);
    void onReplyFinished(QNetworkReply *reply, QJsonArray batch);

    QString m_url, m_frontend, m_mode, m_runId;
    double m_expectedDuration;
    QVariantMap m_metadata;
    QNetworkAccessManager *m_network;
    QTimer *m_timer;
    QJsonArray m_pending;
    std::deque<std::pair<double, double>> m_recent;  // (seconds since start, update_ms)
    QElapsedTimer m_started;
    std::optional<double> m_firstRecordSeconds;
    std::optional<double> m_stoppedSeconds;
    qint64 m_count = 0, m_skipped = 0, m_lost = 0;
    std::optional<double> m_lastReceiveAge;
    double m_lastUpdateMs = 0;
    QString m_error;
    QNetworkReply *m_active = nullptr;
    bool m_closing = false;
};

}  // namespace plotbench
