#include "frame_source.h"

#include <QJsonDocument>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QTimer>
#include <QUrl>
#include <QWebSocket>
#include <QtGlobal>
#include <chrono>
#include <cmath>

namespace plotbench {

double wallClockMs() {
    using namespace std::chrono;
    return duration<double, std::milli>(system_clock::now().time_since_epoch()).count();
}

FrameSource::FrameSource(const QString &url, const QString &mode, QObject *parent)
    : QObject(parent), m_url(url), m_mode(mode) {
    while (m_url.endsWith(QLatin1Char('/'))) {
        m_url.chop(1);
    }
    m_worker = new SourceWorker(this);
    m_worker->moveToThread(&m_thread);
    m_thread.setObjectName(QStringLiteral("plotbench-source"));
    connect(&m_thread, &QThread::started, m_worker, &SourceWorker::run);
    connect(&m_thread, &QThread::finished, m_worker, &QObject::deleteLater);
}

FrameSource::~FrameSource() {
    close();
}

void FrameSource::start() {
    m_thread.start();
}

void FrameSource::close() {
    if (m_closing.exchange(true)) {
        return;
    }
    if (m_thread.isRunning()) {
        QMetaObject::invokeMethod(m_worker, &SourceWorker::stop, Qt::QueuedConnection);
        m_thread.quit();
        if (!m_thread.wait(3000)) {
            m_thread.terminate();
            m_thread.wait(1000);
        }
    }
    QMutexLocker locker(&m_lock);
    m_status = QStringLiteral("Stopped");
}

std::optional<Frame> FrameSource::takeLatest() {
    std::optional<Frame> frame;
    {
        QMutexLocker locker(&m_lock);
        frame.swap(m_latest);
    }
    if (!frame) {
        return frame;
    }
    if (m_previous && m_previous->first == frame->generation) {
        frame->skipped = std::max<qint64>(0, frame->presentationSeq - m_previous->second - 1);
    }
    m_previous = std::make_pair(frame->generation, frame->presentationSeq);
    return frame;
}

bool FrameSource::requestView(const QString &view) {
    if (view != QLatin1String("both") && view != QLatin1String("waveform") && view != QLatin1String("image")) {
        return false;
    }
    {
        QMutexLocker locker(&m_lock);
        if (m_closing || m_viewPending) {
            return false;
        }
        m_viewPending = true;
        m_viewGeneration.reset();
        m_viewError.clear();
    }
    QMetaObject::invokeMethod(m_worker, [worker = m_worker, view] { worker->changeView(view); }, Qt::QueuedConnection);
    return true;
}

bool FrameSource::viewPending() const {
    QMutexLocker locker(&m_lock);
    return m_viewPending;
}

QString FrameSource::viewError() const {
    QMutexLocker locker(&m_lock);
    return m_viewError;
}

QString FrameSource::status() const {
    QMutexLocker locker(&m_lock);
    return m_status;
}

QString FrameSource::error() const {
    QMutexLocker locker(&m_lock);
    return m_error;
}

QVariantMap FrameSource::metadata() const {
    QMutexLocker locker(&m_lock);
    return m_metadata;
}

void FrameSource::publish(Frame frame) {
    QMutexLocker locker(&m_lock);
    m_lastGeneration = frame.generation;
    if (m_viewGeneration && frame.generation >= *m_viewGeneration) {
        m_viewPending = false;
        m_viewError.clear();
    }
    m_latest = std::move(frame);
}

void FrameSource::setStatus(const QString &status, const QString &error) {
    QMutexLocker locker(&m_lock);
    m_status = status;
    m_error = error;
    if (!error.isEmpty() && m_viewPending) {
        m_viewError = QStringLiteral("Plot selection is waiting for the source: %1").arg(error);
        m_viewPending = false;
    }
}

void FrameSource::setMetadata(const QString &key, const QVariant &value) {
    QMutexLocker locker(&m_lock);
    m_metadata.insert(key, value);
}

// ---------------------------------------------------------------------------

SourceWorker::SourceWorker(FrameSource *owner) : m_owner(owner) {}

void SourceWorker::run() {
    m_network = new QNetworkAccessManager(this);
    if (m_owner->mode() == QLatin1String("replay")) {
        m_replayTimer = new QTimer(this);
        m_replayTimer->setTimerType(Qt::PreciseTimer);
        m_replayTimer->setSingleShot(true);
        connect(m_replayTimer, &QTimer::timeout, this, &SourceWorker::replayTick);
        loadReplay();
        return;
    }
    m_socket = new QWebSocket(QString(), QWebSocketProtocol::VersionLatest, this);
    m_socket->setMaxAllowedIncomingMessageSize(kMaxPacket);
    m_reconnect = new QTimer(this);
    m_reconnect->setSingleShot(true);
    m_reconnect->setInterval(1000);
    connect(m_reconnect, &QTimer::timeout, this, &SourceWorker::connectStream);
    connect(m_socket, &QWebSocket::binaryMessageReceived, this, &SourceWorker::onBinaryMessage);
    connect(m_socket, &QWebSocket::disconnected, this, &SourceWorker::onDisconnected);
    connect(m_socket, &QWebSocket::connected, this, [this] {
        const QVariant epoch = m_owner->metadata().value(QStringLiteral("receiver_connection_epoch"), 0);
        m_owner->setMetadata(QStringLiteral("receiver_connection_epoch"), epoch.toInt() + 1);
        m_owner->setStatus(QStringLiteral("Streaming"), QString());
    });
    connect(m_socket, &QWebSocket::errorOccurred, this, [this](QAbstractSocket::SocketError) {
        if (!m_stopping) {
            m_owner->setStatus(QStringLiteral("Connection error: %1; retrying").arg(m_socket->errorString()),
                               m_socket->errorString());
        }
    });
    connectStream();
}

void SourceWorker::stop() {
    m_stopping = true;
    if (m_reconnect) {
        m_reconnect->stop();
    }
    if (m_replayTimer) {
        m_replayTimer->stop();
    }
    if (m_socket) {
        m_socket->close();
    }
}

void SourceWorker::connectStream() {
    if (m_stopping) {
        return;
    }
    QString wsUrl = m_owner->url();
    wsUrl.replace(0, wsUrl.indexOf(QLatin1String("://")), wsUrl.startsWith(QLatin1String("https")) ? QStringLiteral("wss") : QStringLiteral("ws"));
    m_socket->open(QUrl(wsUrl + QStringLiteral("/ws")));
}

void SourceWorker::onBinaryMessage(const QByteArray &message) {
    Frame frame;
    try {
        frame = decodeFrame(message);
    } catch (const ProtocolError &error) {
        m_owner->setStatus(QStringLiteral("Protocol error: %1").arg(QLatin1String(error.what())), QLatin1String(error.what()));
        m_socket->close();
        return;
    }
    frame.receiveAgeMs = wallClockMs() - frame.emittedAtMs;
    m_owner->setMetadata(QStringLiteral("target_hz"), frame.config.value(QStringLiteral("hz")).toDouble());
    m_owner->setMetadata(QStringLiteral("config"), frame.config.toVariantMap());
    const qint64 seq = frame.seq, generation = frame.generation;
    m_owner->publish(std::move(frame));
    emit m_owner->frameAvailable();
    m_socket->sendTextMessage(QStringLiteral("{\"ack\": %1, \"generation\": %2}").arg(seq).arg(generation));
}

void SourceWorker::onDisconnected() {
    if (m_stopping) {
        return;
    }
    m_owner->setStatus(QStringLiteral("Connection closed; retrying"), m_owner->error().isEmpty() ? QStringLiteral("connection closed") : m_owner->error());
    m_reconnect->start();
}

void SourceWorker::loadReplay() {
    if (m_stopping) {
        return;
    }
    m_reloadReplay = false;
    m_owner->setStatus(QStringLiteral("Preloading replay"), QString());
    QNetworkRequest request{QUrl(m_owner->url() + QStringLiteral("/api/replay?count=16"))};
    QNetworkReply *reply = m_network->get(request);
    connect(reply, &QNetworkReply::finished, this, [this, reply] {
        reply->deleteLater();
        if (m_stopping) {
            return;
        }
        if (reply->error() != QNetworkReply::NoError) {
            m_owner->setStatus(QStringLiteral("Replay preload failed: %1; retrying").arg(reply->errorString()), reply->errorString());
            QTimer::singleShot(1000, this, &SourceWorker::loadReplay);
            return;
        }
        const QByteArray data = reply->readAll();
        try {
            m_replay = decodeReplay(data);
        } catch (const ProtocolError &error) {
            m_owner->setStatus(QStringLiteral("Replay decode failed: %1").arg(QLatin1String(error.what())), QLatin1String(error.what()));
            QTimer::singleShot(1000, this, &SourceWorker::loadReplay);
            return;
        }
        const QJsonObject config = m_replay.first().config;
        m_replayHz = config.value(QStringLiteral("hz")).toDouble();
        const QVariant epoch = m_owner->metadata().value(QStringLiteral("receiver_connection_epoch"), 0);
        m_owner->setMetadata(QStringLiteral("receiver_connection_epoch"), epoch.toInt() + 1);
        m_owner->setMetadata(QStringLiteral("replay_frames"), int(m_replay.size()));
        m_owner->setMetadata(QStringLiteral("replay_bytes"), qint64(data.size()));
        m_owner->setMetadata(QStringLiteral("target_hz"), m_replayHz);
        m_owner->setMetadata(QStringLiteral("config"), config.toVariantMap());
        m_owner->setStatus(QStringLiteral("Replaying preloaded input"), QString());
        m_replayClock.start();
        m_replayPrevious = -1;
        replayTick();
    });
}

void SourceWorker::replayTick() {
    if (m_stopping) {
        return;
    }
    if (m_reloadReplay) {
        m_replay.clear();
        loadReplay();
        return;
    }
    const double elapsed = m_replayClock.nsecsElapsed() / 1e9;
    const qint64 seq = qint64(std::floor(elapsed * m_replayHz));
    if (seq > m_replayPrevious) {
        Frame frame = m_replay.at(int(seq % m_replay.size()));
        frame.presentationSeq = seq;
        frame.header.insert(QStringLiteral("replay_index"), double(seq % m_replay.size()));
        frame.receiveAgeMs = std::numeric_limits<double>::quiet_NaN();
        m_owner->publish(std::move(frame));
        emit m_owner->frameAvailable();
        m_replayPrevious = seq;
    }
    const double next = (double(seq + 1) / m_replayHz - elapsed) * 1000.0;
    m_replayTimer->start(int(std::clamp(next, 0.5, 50.0) + 0.5));
}

void SourceWorker::changeView(const QString &view) {
    if (m_stopping) {
        return;
    }
    QNetworkRequest request{QUrl(m_owner->url() + QStringLiteral("/api/config"))};
    request.setHeader(QNetworkRequest::ContentTypeHeader, QStringLiteral("application/json"));
    QNetworkReply *reply = m_network->post(request, QJsonDocument(QJsonObject{{QStringLiteral("view"), view}}).toJson(QJsonDocument::Compact));
    connect(reply, &QNetworkReply::finished, this, [this, reply, view] {
        reply->deleteLater();
        const QJsonObject config = QJsonDocument::fromJson(reply->readAll()).object();
        QMutexLocker locker(&m_owner->m_lock);
        if (reply->error() != QNetworkReply::NoError || config.value(QStringLiteral("view")).toString() != view
            || !config.value(QStringLiteral("generation")).isDouble()) {
            m_owner->m_viewError = QStringLiteral("Could not change plot selection: %1").arg(reply->errorString());
            m_owner->m_viewPending = false;
            return;
        }
        const qint64 generation = qint64(config.value(QStringLiteral("generation")).toDouble());
        m_owner->m_viewGeneration = generation;
        if (m_owner->mode() == QLatin1String("replay")) {
            m_owner->m_latest.reset();
            m_reloadReplay = true;
            if (m_replayTimer && !m_replayTimer->isActive()) {
                m_replayTimer->start(1);
            }
        } else if (m_owner->m_lastGeneration >= generation) {
            m_owner->m_viewPending = false;
            m_owner->m_viewError.clear();
        }
    });
}

}  // namespace plotbench
