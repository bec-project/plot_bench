// Decoder checks against packets built exactly like the Python encoder, plus rejection cases.
#include <QtEndian>
#include <QtTest>

#include "protocol.h"

using namespace plotbench;

namespace {

QByteArray encodePacket(const QByteArray &headerJson, const QByteArray &payload) {
    QByteArray packet;
    packet.resize(4);
    qToLittleEndian<quint32>(quint32(headerJson.size()), reinterpret_cast<uchar *>(packet.data()));
    packet.append(headerJson);
    while (packet.size() % 4 != 0) {
        packet.append('\0');
    }
    packet.append(payload);
    return packet;
}

QByteArray floats(std::initializer_list<float> values) {
    QByteArray bytes;
    for (float value : values) {
        char buffer[4];
        qToLittleEndian<float>(value, reinterpret_cast<uchar *>(buffer));
        bytes.append(buffer, 4);
    }
    return bytes;
}

}  // namespace

class ProtocolTest : public QObject {
    Q_OBJECT
private slots:
    void decodesWaveformAndImageViews() {
        const QByteArray wave = floats({0.5f, -1.25f, 1.0f});
        const QByteArray image = QByteArray::fromRawData("\x01\x02\x03\x04\x05\x06", 6);
        const QByteArray header = R"({"version":1,"seq":7,"generation":2,"emitted_at_ms":1234.5,"config":{"hz":60,"view":"both"},"arrays":[{"name":"waveform","dtype":"float32","shape":[3],"offset":0,"nbytes":12},{"name":"image","dtype":"uint8","shape":[1,2,3],"offset":12,"nbytes":6}]})";
        const Frame frame = decodeFrame(encodePacket(header, wave + image));
        QCOMPARE(frame.seq, 7);
        QCOMPARE(frame.generation, 2);
        QCOMPARE(frame.config.value("hz").toDouble(), 60.0);
        QVERIFY(frame.has("waveform") && frame.has("image"));
        const ArrayView &waveform = frame.arrays.value("waveform");
        QCOMPARE(waveform.count, 3);
        QCOMPARE(qFromLittleEndian<float>(reinterpret_cast<const uchar *>(frame.data(waveform)) + 4), -1.25f);
        const ArrayView &pixels = frame.arrays.value("image");
        QCOMPARE(pixels.shape, (QList<int>{1, 2, 3}));
        QCOMPARE(frame.data(pixels)[5], '\x06');
    }

    void rejectsMalformedPackets() {
        const QByteArray wave = floats({0.0f, 1.0f});
        const QByteArray header = R"({"version":1,"seq":0,"generation":0,"emitted_at_ms":0,"config":{},"arrays":[{"name":"waveform","dtype":"float32","shape":[2],"offset":0,"nbytes":8}]})";
        QVERIFY_THROWS_EXCEPTION(ProtocolError, decodeFrame(encodePacket(header, wave + "extra")));
        QVERIFY_THROWS_EXCEPTION(ProtocolError, decodeFrame(encodePacket(header, wave.left(4))));
        QVERIFY_THROWS_EXCEPTION(ProtocolError, decodeFrame(encodePacket(QByteArray(header).replace("\"version\":1", "\"version\":2"), wave)));
        QVERIFY_THROWS_EXCEPTION(ProtocolError, decodeFrame(encodePacket(QByteArray(header).replace("\"seq\":0", "\"seq\":-1"), wave)));
        QVERIFY_THROWS_EXCEPTION(ProtocolError, decodeFrame(encodePacket(QByteArray(header).replace("float32", "float64"), wave)));
        QVERIFY_THROWS_EXCEPTION(ProtocolError, decodeFrame(QByteArray("\x01\x00", 2)));
    }

    void decodesReplayContainer() {
        const QByteArray wave = floats({0.0f, 1.0f});
        const QByteArray header = R"({"version":1,"seq":0,"generation":0,"emitted_at_ms":0,"config":{"hz":30},"arrays":[{"name":"waveform","dtype":"float32","shape":[2],"offset":0,"nbytes":8}]})";
        const QByteArray packet = encodePacket(header, wave);
        QByteArray container;
        container.resize(4);
        qToLittleEndian<quint32>(2, reinterpret_cast<uchar *>(container.data()));
        for (int index = 0; index < 2; ++index) {
            QByteArray length(4, '\0');
            qToLittleEndian<quint32>(quint32(packet.size()), reinterpret_cast<uchar *>(length.data()));
            container.append(length).append(packet);
        }
        QCOMPARE(decodeReplay(container).size(), 2);
        QVERIFY_THROWS_EXCEPTION(ProtocolError, decodeReplay(container + "x"));
        QVERIFY_THROWS_EXCEPTION(ProtocolError, decodeReplay(container.left(container.size() - 1)));
    }
};

QTEST_APPLESS_MAIN(ProtocolTest)
#include "test_protocol.moc"
