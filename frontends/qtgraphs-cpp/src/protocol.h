// Strict decoder for the Plotbench v2 binary frame and replay container (docs/protocol.md).
#pragma once

#include <QByteArray>
#include <QHash>
#include <QJsonObject>
#include <QList>
#include <QString>
#include <limits>
#include <stdexcept>

namespace plotbench {

constexpr int kProtocolVersion = 2;
constexpr qsizetype kMaxPacket = qsizetype(257) * 1024 * 1024;

struct ArrayView {
    QString dtype;         // "float32" or "uint8"
    QList<int> shape;      // C order; v2: waveform [plots, curves, points], image [plots, h, w(, 3)]
    qsizetype offset = 0;  // bytes from the start of the array payload
    qsizetype nbytes = 0;
    qsizetype count = 0;   // number of elements

    qsizetype itemSize() const { return dtype == QLatin1String("float32") ? 4 : 1; }
    // Leading dimension: the number of plots this array carries (0 for an empty view).
    int plots() const { return shape.isEmpty() ? 0 : shape.first(); }
    // Contiguous elements per plot: curves*points for waveforms, height*width(*3) for images.
    qsizetype elementsPerPlot() const { return plots() > 0 ? count / plots() : 0; }
    qsizetype plotOffset(int plot) const { return qsizetype(plot) * elementsPerPlot() * itemSize(); }
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
    // Start of plot `plot`'s contiguous slice; no copy.
    const char *plotData(const ArrayView &view, int plot) const { return data(view) + view.plotOffset(plot); }
};

class ProtocolError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

// The (dtype, shape) a v2 frame configuration implies for `waveform` or `image`; throws
// ProtocolError when the configuration lacks the protocol v2 plot fields.
struct ExpectedLayout {
    QString dtype;
    QList<int> shape;
};
ExpectedLayout expectedLayout(const QJsonObject &config, const QString &name);

Frame decodeFrame(const QByteArray &packet);
QList<Frame> decodeReplay(const QByteArray &container);

}  // namespace plotbench
