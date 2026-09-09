// Threaded receiver: WebSocket stream or preloaded replay, one latest-frame mailbox, ACK after publish.
#pragma once

#include <QElapsedTimer>
#include <QJsonObject>
#include <QMutex>
#include <QObject>
#include <QString>
#include <QThread>
#include <QVariantMap>
#include <atomic>
#include <memory>
#include <optional>

#include "protocol.h"

class QNetworkAccessManager;
class QTimer;
class QWebSocket;

namespace plotbench {

class SourceWorker;

class FrameSource : public QObject {
    Q_OBJECT
public:
    FrameSource(const QString &url, const QString &mode, QObject *parent = nullptr);
    ~FrameSource() override;

    void start();
    void close();
    std::optional<Frame> takeLatest();
    bool requestView(const QString &view);
    bool viewPending() const;
    QString viewError() const;
    QString status() const;
    QString error() const;
    QVariantMap metadata() const;
    QString mode() const { return m_mode; }
    QString url() const { return m_url; }

signals:
    void frameAvailable();

private:
    friend class SourceWorker;
    void publish(Frame frame);
    void setStatus(const QString &status, const QString &error);
    void setMetadata(const QString &key, const QVariant &value);

    QString m_url;
    QString m_mode;
    QThread m_thread;
    SourceWorker *m_worker = nullptr;
    mutable QMutex m_lock;
    std::optional<Frame> m_latest;
    std::optional<std::pair<qint64, qint64>> m_previous;  // generation, seq
    qint64 m_lastGeneration = -1;
    std::optional<qint64> m_viewGeneration;
    bool m_viewPending = false;
    QString m_viewError;
    QString m_status = QStringLiteral("Connecting");
    QString m_error;
    QVariantMap m_metadata;
    std::atomic_bool m_closing{false};
};

// Lives in the worker thread: owns the socket, replay dataset and configuration requests.
class SourceWorker : public QObject {
    Q_OBJECT
public:
    explicit SourceWorker(FrameSource *owner);

public slots:
    void run();
    void stop();
    void changeView(const QString &view);

private slots:
    void connectStream();
    void onBinaryMessage(const QByteArray &message);
    void onDisconnected();
    void loadReplay();
    void replayTick();

private:
    FrameSource *m_owner;
    QWebSocket *m_socket = nullptr;
    QNetworkAccessManager *m_network = nullptr;
    QTimer *m_reconnect = nullptr;
    QTimer *m_replayTimer = nullptr;
    QList<Frame> m_replay;
    QElapsedTimer m_replayClock;
    qint64 m_replayPrevious = -1;
    double m_replayHz = 0;
    bool m_reloadReplay = false;
    bool m_stopping = false;
};

double wallClockMs();

}  // namespace plotbench
