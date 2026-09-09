#include "metrics_sink.h"

#include <QEventLoop>
#include <QJsonDocument>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QTimer>
#include <QUrl>
#include <cmath>

#include "frame_source.h"
#include "protocol.h"

namespace plotbench {

namespace {
constexpr int kMaxPending = 20000;
}

MetricsSink::MetricsSink(const QString &url, const QString &frontend, const QString &mode, const QString &runId,
                         double expectedDuration, QVariantMap metadata, QObject *parent)
    : QObject(parent), m_url(url), m_frontend(frontend), m_mode(mode), m_runId(runId),
      m_expectedDuration(expectedDuration), m_metadata(std::move(metadata)) {
    while (m_url.endsWith(QLatin1Char('/'))) {
        m_url.chop(1);
    }
    m_network = new QNetworkAccessManager(this);
    m_timer = new QTimer(this);
    m_timer->setInterval(1000);
    connect(m_timer, &QTimer::timeout, this, [this] { flush(false); });
    m_started.start();
    m_timer->start();
}

void MetricsSink::record(const Frame &frame, double updateMs, double conversionMs) {
    const double now = m_started.nsecsElapsed() / 1e9;
    if (!m_firstRecordSeconds) {
        m_firstRecordSeconds = now;
    }
    QJsonObject sample{
        {QStringLiteral("seq"), double(frame.presentationSeq)},
        {QStringLiteral("generation"), double(frame.generation)},
        {QStringLiteral("client_time_ms"), wallClockMs()},
        {QStringLiteral("update_ms"), updateMs},
        {QStringLiteral("skipped"), double(frame.skipped)},
        {QStringLiteral("conversion_ms"), conversionMs},
    };
    if (std::isnan(frame.receiveAgeMs)) {
        sample.insert(QStringLiteral("receive_age_ms"), QJsonValue::Null);
        m_lastReceiveAge.reset();
    } else {
        sample.insert(QStringLiteral("receive_age_ms"), frame.receiveAgeMs);
        m_lastReceiveAge = frame.receiveAgeMs;
    }
    if (m_pending.size() < kMaxPending) {
        m_pending.append(sample);
    } else {
        ++m_lost;
    }
    m_recent.emplace_back(now, updateMs);
    while (!m_recent.empty() && m_recent.front().first < now - 2) {
        m_recent.pop_front();
    }
    ++m_count;
    m_skipped += frame.skipped;
    m_lastUpdateMs = updateMs;
}

Snapshot MetricsSink::snapshot() const {
    const double now = m_started.nsecsElapsed() / 1e9;
    Snapshot result;
    double sum = 0;
    qint64 recent = 0;
    for (const auto &[time, updateMs] : m_recent) {
        if (time >= now - 2) {
            sum += updateMs;
            ++recent;
        }
    }
    result.updatesHz = double(recent) / std::min(2.0, std::max(0.001, now));
    result.updateMs = recent ? sum / double(recent) : 0;
    result.skipped = m_skipped;
    result.receiveAgeMs = m_lastReceiveAge;
    result.count = m_count;
    result.telemetryLost = m_lost;
    return result;
}

void MetricsSink::markStopped(const QString &reason) {
    if (m_stoppedSeconds) {
        return;
    }
    const double now = m_started.nsecsElapsed() / 1e9;
    m_stoppedSeconds = now;
    const double elapsed = m_firstRecordSeconds ? now - *m_firstRecordSeconds : 0;
    m_metadata.insert(QStringLiteral("active_seconds"), elapsed);
    m_metadata.insert(QStringLiteral("expected_duration"), m_expectedDuration > 0 ? QVariant(m_expectedDuration) : QVariant());
    QString termination = reason;
    if (termination.isEmpty()) {
        termination = (m_expectedDuration > 0 && elapsed >= m_expectedDuration - 0.05) ? QStringLiteral("duration") : QStringLiteral("user");
    }
    m_metadata.insert(QStringLiteral("termination_reason"), termination);
}

void MetricsSink::flush(bool forceMetadata) {
    if (m_active) {
        return;  // one batch in flight; the next timer tick retries
    }
    if (m_pending.isEmpty() && !forceMetadata) {
        return;
    }
    QJsonArray batch;
    batch.swap(m_pending);
    QVariantMap metadata = m_metadata;
    metadata.insert(QStringLiteral("telemetry_lost"), m_lost);
    const QJsonObject body{
        {QStringLiteral("frontend"), m_frontend},
        {QStringLiteral("mode"), m_mode},
        {QStringLiteral("run_id"), m_runId},
        {QStringLiteral("samples"), batch},
        {QStringLiteral("metadata"), QJsonObject::fromVariantMap(metadata)},
    };
    QNetworkRequest request{QUrl(m_url + QStringLiteral("/api/metrics"))};
    request.setHeader(QNetworkRequest::ContentTypeHeader, QStringLiteral("application/json"));
    request.setTransferTimeout(5000);
    m_active = m_network->post(request, QJsonDocument(body).toJson(QJsonDocument::Compact));
    connect(m_active, &QNetworkReply::finished, this, [this, reply = m_active, batch] { onReplyFinished(reply, batch); });
}

void MetricsSink::onReplyFinished(QNetworkReply *reply, QJsonArray batch) {
    reply->deleteLater();
    m_active = nullptr;
    if (reply->error() == QNetworkReply::NoError) {
        m_error.clear();
        return;
    }
    m_error = reply->errorString();
    // Keep the failed samples ahead of newer ones, bounded like the Python sink.
    QJsonArray combined = batch;
    for (const QJsonValue &value : std::as_const(m_pending)) {
        combined.append(value);
    }
    while (combined.size() > kMaxPending) {
        combined.removeFirst();
        ++m_lost;
    }
    m_pending = combined;
}

void MetricsSink::close() {
    if (m_closing) {
        return;
    }
    m_closing = true;
    markStopped();
    m_timer->stop();
    QElapsedTimer deadline;
    deadline.start();
    // Wait for an in-flight batch, then send the final batch (even with no samples) and wait.
    while (m_active && deadline.elapsed() < 6000) {
        QEventLoop loop;
        QTimer::singleShot(50, &loop, &QEventLoop::quit);
        loop.exec();
    }
    flush(true);
    while (m_active && deadline.elapsed() < 12000) {
        QEventLoop loop;
        QTimer::singleShot(50, &loop, &QEventLoop::quit);
        loop.exec();
    }
    if (m_active) {
        m_error = QStringLiteral("Metrics flush did not finish before shutdown");
    } else if (!m_pending.isEmpty()) {
        m_error = QStringLiteral("%1 measurement samples could not be flushed: %2").arg(m_pending.size()).arg(m_error);
    }
}

}  // namespace plotbench
