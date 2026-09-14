#include "protocol.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QtEndian>

namespace plotbench {

namespace {

quint32 readU32(const QByteArray &bytes, qsizetype offset) {
    return qFromLittleEndian<quint32>(reinterpret_cast<const uchar *>(bytes.constData() + offset));
}

qint64 requireNonNegativeInt(const QJsonObject &object, const char *key) {
    const QJsonValue value = object.value(QLatin1String(key));
    if (!value.isDouble()) {
        throw ProtocolError(QStringLiteral("invalid %1").arg(QLatin1String(key)).toStdString());
    }
    const double number = value.toDouble();
    if (number < 0 || number != static_cast<double>(static_cast<qint64>(number))) {
        throw ProtocolError(QStringLiteral("invalid %1").arg(QLatin1String(key)).toStdString());
    }
    return static_cast<qint64>(number);
}

int configDimension(const QJsonObject &config, const char *key) {
    const QJsonValue value = config.value(QLatin1String(key));
    if (!value.isDouble() || value.toDouble() <= 0 || value.toDouble() != double(int(value.toDouble()))) {
        throw ProtocolError("frame configuration lacks the protocol v2 plot fields");
    }
    return value.toInt();
}

QString shapeText(const QList<int> &shape) {
    QStringList parts;
    for (int dimension : shape) {
        parts.append(QString::number(dimension));
    }
    return QLatin1Char('[') + parts.join(QStringLiteral(", ")) + QLatin1Char(']');
}

}  // namespace

ExpectedLayout expectedLayout(const QJsonObject &config, const QString &name) {
    if (name == QLatin1String("waveform")) {
        return {QStringLiteral("float32"),
                {configDimension(config, "waveform_plots"), configDimension(config, "curves"), configDimension(config, "points")}};
    }
    QList<int> shape{configDimension(config, "image_plots"), configDimension(config, "height"), configDimension(config, "width")};
    const QJsonValue mode = config.value(QStringLiteral("image_mode"));
    if (!mode.isString()) {
        throw ProtocolError("frame configuration lacks the protocol v2 plot fields");
    }
    if (mode.toString() == QLatin1String("rgb")) {
        shape.append(3);
        return {QStringLiteral("uint8"), shape};
    }
    return {QStringLiteral("float32"), shape};
}

Frame decodeFrame(const QByteArray &packet) {
    if (packet.size() < 4 || packet.size() > kMaxPacket) {
        throw ProtocolError("invalid frame size");
    }
    const quint32 headerSize = readU32(packet, 0);
    if (headerSize > 65536 || qsizetype(headerSize) + 4 > packet.size()) {
        throw ProtocolError("invalid frame header length");
    }
    QJsonParseError parseError{};
    const QJsonDocument document = QJsonDocument::fromJson(packet.mid(4, headerSize), &parseError);
    if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
        throw ProtocolError("unreadable frame header");
    }
    Frame frame;
    frame.header = document.object();
    if (frame.header.value(QStringLiteral("version")).toInt() != kProtocolVersion) {
        throw ProtocolError("unsupported protocol version");
    }
    frame.seq = requireNonNegativeInt(frame.header, "seq");
    frame.generation = requireNonNegativeInt(frame.header, "generation");
    frame.presentationSeq = frame.seq;
    frame.emittedAtMs = frame.header.value(QStringLiteral("emitted_at_ms")).toDouble();
    const QJsonValue configValue = frame.header.value(QStringLiteral("config"));
    const bool hasConfig = !configValue.isUndefined() && !configValue.isNull();
    if (hasConfig && !configValue.isObject()) {
        throw ProtocolError("frame configuration must be a JSON object");
    }
    frame.config = configValue.toObject();
    frame.packet = packet;
    frame.payloadBase = qsizetype((headerSize + 7) / 4) * 4;
    qsizetype end = 0;
    const QJsonArray descriptors = frame.header.value(QStringLiteral("arrays")).toArray();
    for (const QJsonValue &item : descriptors) {
        const QJsonObject descriptor = item.toObject();
        const QString name = descriptor.value(QStringLiteral("name")).toString();
        if ((name != QLatin1String("waveform") && name != QLatin1String("image")) || frame.arrays.contains(name)) {
            throw ProtocolError("invalid or repeated array name");
        }
        ArrayView view;
        view.dtype = descriptor.value(QStringLiteral("dtype")).toString();
        const qsizetype itemSize = view.dtype == QLatin1String("float32") ? 4 : view.dtype == QLatin1String("uint8") ? 1 : 0;
        if (itemSize == 0) {
            throw ProtocolError("unsupported dtype");
        }
        const QJsonArray shape = descriptor.value(QStringLiteral("shape")).toArray();
        if (shape.isEmpty() || shape.size() > 4) {
            throw ProtocolError("invalid shape");
        }
        view.count = 1;
        for (const QJsonValue &dimension : shape) {
            if (!dimension.isDouble() || dimension.toDouble() <= 0 || dimension.toDouble() != double(int(dimension.toDouble()))) {
                throw ProtocolError("invalid array dimension");
            }
            view.shape.append(dimension.toInt());
            view.count *= dimension.toInt();
        }
        if (hasConfig) {
            // Protocol v2: the header configuration fixes the exact dtype and shape of every array.
            const ExpectedLayout expected = expectedLayout(frame.config, name);
            const QString configView = frame.config.value(QStringLiteral("view")).toString();
            if (configView != QLatin1String("both") && configView != name) {
                throw ProtocolError(QStringLiteral("%1 array is not enabled by view '%2'").arg(name, configView).toStdString());
            }
            if (view.dtype != expected.dtype) {
                throw ProtocolError(QStringLiteral("%1 dtype %2 does not match configuration").arg(name, view.dtype).toStdString());
            }
            if (view.shape != expected.shape) {
                throw ProtocolError(QStringLiteral("%1 shape %2 does not match configuration %3")
                                        .arg(name, shapeText(view.shape), shapeText(expected.shape))
                                        .toStdString());
            }
        }
        view.offset = qsizetype(descriptor.value(QStringLiteral("offset")).toDouble());
        view.nbytes = qsizetype(descriptor.value(QStringLiteral("nbytes")).toDouble());
        if (view.offset != end || view.nbytes != view.count * itemSize) {
            throw ProtocolError("noncontiguous array descriptor or size mismatch");
        }
        if (frame.payloadBase + end + view.nbytes > packet.size()) {
            throw ProtocolError("truncated array");
        }
        end += view.nbytes;
        frame.arrays.insert(name, view);
    }
    if (frame.payloadBase + end != packet.size()) {
        throw ProtocolError("unexpected trailing bytes");
    }
    return frame;
}

QList<Frame> decodeReplay(const QByteArray &container) {
    if (container.size() < 4) {
        throw ProtocolError("truncated replay");
    }
    const quint32 count = readU32(container, 0);
    if (count < 2 || count > 256) {
        throw ProtocolError("replay must contain between 2 and 256 changing frames");
    }
    QList<Frame> frames;
    qsizetype offset = 4;
    for (quint32 index = 0; index < count; ++index) {
        if (offset + 4 > container.size()) {
            throw ProtocolError("truncated replay length");
        }
        const qsizetype length = readU32(container, offset);
        offset += 4;
        if (offset + length > container.size()) {
            throw ProtocolError("truncated replay frame");
        }
        frames.append(decodeFrame(container.mid(offset, length)));
        offset += length;
    }
    if (offset != container.size()) {
        throw ProtocolError("unexpected replay trailing bytes");
    }
    return frames;
}

}  // namespace plotbench
