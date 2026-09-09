// Strict decoder for the Plotbench v1 binary frame and replay container (docs/protocol.md).
#pragma once

#include <QByteArray>
#include <QHash>
#include <QJsonObject>
#include <QList>
#include <QString>
#include <limits>
#include <stdexcept>

namespace plotbench {

constexpr qsizetype kMaxPacket = qsizetype(257) * 1024 * 1024;

struct ArrayView {
    QString dtype;         // "float32" or "uint8"
    QList<int> shape;      // C order
    qsizetype offset = 0;  // bytes from the start of the array payload
    qsizetype nbytes = 0;
    qsizetype count = 0;   // number of elements
};

struct Frame {
    QJsonObject header;
    QJsonObject config;
    qint64 seq = 0;
    qint64 generation = 0;
    qint64 presentationSeq = 0;  // replay: increasing presentation counter; stream: seq
    double emittedAtMs = 0;
    double receiveAgeMs = std::numeric_limits<double>::quiet_NaN();  // NaN when unavailable
    qint64 skipped = 0;
    QByteArray packet;      // whole packet; array bytes are views into it
    qsizetype payloadBase = 0;
    QHash<QString, ArrayView> arrays;

    bool has(const QString &name) const { return arrays.contains(name); }
    const char *data(const ArrayView &view) const { return packet.constData() + payloadBase + view.offset; }
};

class ProtocolError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

Frame decodeFrame(const QByteArray &packet);
QList<Frame> decodeReplay(const QByteArray &container);

}  // namespace plotbench
