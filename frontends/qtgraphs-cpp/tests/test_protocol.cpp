// Decoder and image-provider checks against v2 packets built exactly like the Python encoder, plus rejection cases.
#include <QColor>
#include <QtEndian>
#include <QtTest>

#include "image_provider.h"
#include "protocol.h"
#include "resource_usage.h"
#include <cmath>

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

// A complete v2 configuration, as every source puts it into the frame header.
const char *const kBothConfig =
    R"("config":{"hz":60,"points":3,"append_count":1,"curves":1,"waveform_plots":1,"width":2,"height":1,"image_plots":1,"waveform_mode":"replace","image_mode":"rgb","view":"both","seed":42,"generation":2})";

}  // namespace

class ProtocolTest : public QObject {
    Q_OBJECT
private slots:
    void residentMemoryUsesCurrentProcessUnits() {
        ResourceUsage usage;
        const double memory = usage.residentMiB();
        QVERIFY(std::isfinite(memory));
        QVERIFY(memory > 1.0);
    }

    void decodesWaveformAndImageViews() {
        const QByteArray wave = floats({0.5f, -1.25f, 1.0f});
        const QByteArray image = QByteArray::fromRawData("\x01\x02\x03\x04\x05\x06", 6);
        const QByteArray header = QByteArray(R"({"version":2,"seq":7,"generation":2,"emitted_at_ms":1234.5,)") + kBothConfig
            + R"(,"arrays":[{"name":"waveform","dtype":"float32","shape":[1,1,3],"offset":0,"nbytes":12},{"name":"image","dtype":"uint8","shape":[1,1,2,3],"offset":12,"nbytes":6}]})";
        const Frame frame = decodeFrame(encodePacket(header, wave + image));
        QCOMPARE(frame.seq, 7);
        QCOMPARE(frame.generation, 2);
        QCOMPARE(frame.config.value("hz").toDouble(), 60.0);
        QCOMPARE(frame.config.value("curves").toInt(), 1);
        QVERIFY(frame.has("waveform") && frame.has("image"));
        const ArrayView &waveform = frame.arrays.value("waveform");
        QCOMPARE(waveform.shape, (QList<int>{1, 1, 3}));
        QCOMPARE(waveform.count, 3);
        QCOMPARE(waveform.plots(), 1);
        QCOMPARE(waveform.elementsPerPlot(), 3);
        QCOMPARE(qFromLittleEndian<float>(reinterpret_cast<const uchar *>(frame.data(waveform)) + 4), -1.25f);
        const ArrayView &pixels = frame.arrays.value("image");
        QCOMPARE(pixels.shape, (QList<int>{1, 1, 2, 3}));
        QCOMPARE(frame.data(pixels)[5], '\x06');
        QCOMPARE(frame.plotData(pixels, 0), frame.data(pixels));
    }

    void decodesMultiPlotSlices() {
        // 2 waveform plots × 3 curves × 2 points, then 2 RGB image plots of 1 × 2 pixels (4-D).
        QByteArray wave;
        for (int index = 0; index < 12; ++index) {
            wave += floats({float(index)});
        }
        const QByteArray image = QByteArray::fromRawData("\x01\x02\x03\x04\x05\x06\x11\x12\x13\x14\x15\x16", 12);
        const QByteArray header =
            R"({"version":2,"seq":1,"generation":0,"emitted_at_ms":0,"config":{"hz":30,"points":2,"append_count":1,"curves":3,"waveform_plots":2,"width":2,"height":1,"image_plots":2,"waveform_mode":"append","image_mode":"rgb","view":"both","seed":1,"generation":0},"arrays":[{"name":"waveform","dtype":"float32","shape":[2,3,2],"offset":0,"nbytes":48},{"name":"image","dtype":"uint8","shape":[2,1,2,3],"offset":48,"nbytes":12}]})";
        const Frame frame = decodeFrame(encodePacket(header, wave + image));
        const ArrayView &waveform = frame.arrays.value("waveform");
        QCOMPARE(waveform.plots(), 2);
        QCOMPARE(waveform.elementsPerPlot(), 6);
        QCOMPARE(waveform.plotOffset(1), 24);
        // Plot 1, curve 2 is the contiguous slice starting at (1 * 3 + 2) * 2 elements.
        const uchar *curve = reinterpret_cast<const uchar *>(frame.plotData(waveform, 1)) + 2 * 2 * 4;
        QCOMPARE(qFromLittleEndian<float>(curve), 10.0f);
        QCOMPARE(qFromLittleEndian<float>(curve + 4), 11.0f);
        const ArrayView &pixels = frame.arrays.value("image");
        QCOMPARE(pixels.shape, (QList<int>{2, 1, 2, 3}));
        QCOMPARE(pixels.plots(), 2);
        QCOMPARE(pixels.elementsPerPlot(), 6);
        QCOMPARE(pixels.plotOffset(1), 6);
        QCOMPARE(frame.plotData(pixels, 1)[0], '\x11');
        QCOMPARE(frame.plotData(pixels, 1)[5], '\x16');
        QCOMPARE(frame.plotData(pixels, 1) - frame.data(pixels), 6);
    }

    void decodesScalarImagePlots() {
        // Scalar images are float32 [image_plots, height, width]: 2 plots of 1 × 2 pixels.
        const QByteArray image = floats({0.0f, 0.5f, 1.0f, 0.25f});
        const QByteArray header =
            R"({"version":2,"seq":3,"generation":0,"emitted_at_ms":0,"config":{"hz":30,"points":1,"append_count":1,"curves":1,"waveform_plots":1,"width":2,"height":1,"image_plots":2,"waveform_mode":"replace","image_mode":"scalar","view":"image","seed":7,"generation":0},"arrays":[{"name":"image","dtype":"float32","shape":[2,1,2],"offset":0,"nbytes":16}]})";
        const Frame frame = decodeFrame(encodePacket(header, image));
        const ArrayView &pixels = frame.arrays.value("image");
        QCOMPARE(pixels.dtype, QStringLiteral("float32"));
        QCOMPARE(pixels.shape, (QList<int>{2, 1, 2}));
        QCOMPARE(pixels.plots(), 2);
        QCOMPARE(pixels.elementsPerPlot(), 2);
        QCOMPARE(pixels.plotOffset(1), 1 * 2 * 4);  // height * width * sizeof(float32)
        QCOMPARE(qFromLittleEndian<float>(reinterpret_cast<const uchar *>(frame.plotData(pixels, 1))), 1.0f);
        QCOMPARE(qFromLittleEndian<float>(reinterpret_cast<const uchar *>(frame.plotData(pixels, 1)) + 4), 0.25f);
        const ExpectedLayout expected = expectedLayout(frame.config, QStringLiteral("image"));
        QCOMPARE(expected.dtype, QStringLiteral("float32"));
        QCOMPARE(expected.shape, (QList<int>{2, 1, 2}));
        // A uint8 array or an RGB-style trailing 3 does not match a scalar configuration.
        QVERIFY_THROWS_EXCEPTION(ProtocolError, decodeFrame(encodePacket(QByteArray(header).replace("\"dtype\":\"float32\"", "\"dtype\":\"uint8\""), image.left(4))));
        QVERIFY_THROWS_EXCEPTION(ProtocolError, decodeFrame(encodePacket(QByteArray(header).replace("\"shape\":[2,1,2]", "\"shape\":[2,1,2,3]").replace("\"nbytes\":16", "\"nbytes\":48"), image + image + image)));
    }

    void convertsImagePlotsFromSlices() {
        // The provider takes each plot's slice: scalar values become Indexed8 indices
        // truncate(clamp(v) * 255); RGB plots wrap the packet bytes at the plot's offset.
        FrameImageProvider provider;
        QList<QRgb> table;
        for (int index = 0; index < 256; ++index) {
            table.append(qRgb(index, index, index));
        }
        provider.setColorTable(table);
        provider.setPlotCount(2);
        const QByteArray scalar = floats({0.0f, 0.5f, 1.5f, 0.25f});
        const QByteArray scalarHeader =
            R"({"version":2,"seq":0,"generation":0,"emitted_at_ms":0,"config":{"hz":30,"points":1,"append_count":1,"curves":1,"waveform_plots":1,"width":2,"height":1,"image_plots":2,"waveform_mode":"replace","image_mode":"scalar","view":"image","seed":7,"generation":0},"arrays":[{"name":"image","dtype":"float32","shape":[2,1,2],"offset":0,"nbytes":16}]})";
        const Frame scalarFrame = decodeFrame(encodePacket(scalarHeader, scalar));
        const ArrayView &scalarView = scalarFrame.arrays.value("image");
        QCOMPARE(provider.updateImage(0, scalarFrame, scalarView), QImage::Format_Indexed8);
        QCOMPARE(provider.updateImage(1, scalarFrame, scalarView), QImage::Format_Indexed8);
        QCOMPARE(provider.current(0).size(), QSize(2, 1));
        QCOMPARE(provider.current(0).pixelIndex(0, 0), 0);
        QCOMPARE(provider.current(0).pixelIndex(1, 0), 127);
        QCOMPARE(provider.current(1).pixelIndex(0, 0), 255);  // clamped
        QCOMPARE(provider.current(1).pixelIndex(1, 0), 63);
        QCOMPARE(provider.current(1).colorTable().size(), 256);
        QCOMPARE(provider.current(2).isNull(), true);
        QVERIFY_THROWS_EXCEPTION(ProtocolError, provider.updateImage(2, scalarFrame, scalarView));

        const QByteArray rgb = QByteArray::fromRawData("\x01\x02\x03\x04\x05\x06\x11\x12\x13\x14\x15\x16", 12);
        const QByteArray rgbHeader =
            R"({"version":2,"seq":0,"generation":0,"emitted_at_ms":0,"config":{"hz":30,"points":1,"append_count":1,"curves":1,"waveform_plots":1,"width":2,"height":1,"image_plots":2,"waveform_mode":"replace","image_mode":"rgb","view":"image","seed":7,"generation":0},"arrays":[{"name":"image","dtype":"uint8","shape":[2,1,2,3],"offset":0,"nbytes":12}]})";
        const Frame rgbFrame = decodeFrame(encodePacket(rgbHeader, rgb));
        const ArrayView &rgbView = rgbFrame.arrays.value("image");
        QCOMPARE(provider.updateImage(1, rgbFrame, rgbView), QImage::Format_RGB888);
        QCOMPARE(provider.current(1).pixelColor(0, 0), QColor(0x11, 0x12, 0x13));
        QCOMPARE(provider.current(1).pixelColor(1, 0), QColor(0x14, 0x15, 0x16));

        // A packet without a configuration may carry a 2-D image; the provider refuses it
        // instead of indexing shape[1] / shape[2] out of range.
        const QByteArray bare =
            R"({"version":2,"seq":0,"generation":0,"emitted_at_ms":0,"arrays":[{"name":"image","dtype":"float32","shape":[2,2],"offset":0,"nbytes":16}]})";
        const Frame bareFrame = decodeFrame(encodePacket(bare, scalar));
        QVERIFY_THROWS_EXCEPTION(ProtocolError, provider.updateImage(0, bareFrame, bareFrame.arrays.value("image")));
        const QByteArray bareRgb =
            R"({"version":2,"seq":0,"generation":0,"emitted_at_ms":0,"arrays":[{"name":"image","dtype":"uint8","shape":[2,2,3],"offset":0,"nbytes":12}]})";
        const Frame bareRgbFrame = decodeFrame(encodePacket(bareRgb, rgb));
        QVERIFY_THROWS_EXCEPTION(ProtocolError, provider.updateImage(0, bareRgbFrame, bareRgbFrame.arrays.value("image")));
    }

    void validatesShapesAgainstConfig() {
        const QByteArray wave = floats({0.0f, 1.0f, 2.0f});
        const QByteArray header = QByteArray(R"({"version":2,"seq":0,"generation":0,"emitted_at_ms":0,)") + kBothConfig
            + R"(,"arrays":[{"name":"waveform","dtype":"float32","shape":[1,1,3],"offset":0,"nbytes":12}]})";
        decodeFrame(encodePacket(header, wave));
        // Wrong shape, wrong dtype, hidden kind and a configuration without the v2 fields.
        QVERIFY_THROWS_EXCEPTION(ProtocolError, decodeFrame(encodePacket(QByteArray(header).replace("\"shape\":[1,1,3]", "\"shape\":[3]"), wave)));
        QVERIFY_THROWS_EXCEPTION(ProtocolError, decodeFrame(encodePacket(QByteArray(header).replace("\"shape\":[1,1,3]", "\"shape\":[1,3,1]"), wave)));
        QVERIFY_THROWS_EXCEPTION(ProtocolError, decodeFrame(encodePacket(QByteArray(header).replace("\"view\":\"both\"", "\"view\":\"image\""), wave)));
        QVERIFY_THROWS_EXCEPTION(ProtocolError, decodeFrame(encodePacket(QByteArray(header).replace("\"curves\":1,", ""), wave)));
        QVERIFY_THROWS_EXCEPTION(ProtocolError, decodeFrame(encodePacket(QByteArray(header).replace("\"curves\":1", "\"curves\":true"), wave)));
        // Without a configuration the layout checks alone apply.
        const QByteArray bare = R"({"version":2,"seq":0,"generation":0,"emitted_at_ms":0,"arrays":[{"name":"waveform","dtype":"float32","shape":[1,1,3],"offset":0,"nbytes":12}]})";
        QCOMPARE(decodeFrame(encodePacket(bare, wave)).arrays.value("waveform").count, 3);
        QVERIFY_THROWS_EXCEPTION(ProtocolError, decodeFrame(encodePacket(QByteArray(bare).replace("\"shape\":[1,1,3]", "\"shape\":[1,1,1,1,3]"), wave)));
    }

    void rejectsMalformedPackets() {
        const QByteArray wave = floats({0.0f, 1.0f, 2.0f});
        const QByteArray header = QByteArray(R"({"version":2,"seq":0,"generation":0,"emitted_at_ms":0,)") + kBothConfig
            + R"(,"arrays":[{"name":"waveform","dtype":"float32","shape":[1,1,3],"offset":0,"nbytes":12}]})";
        QVERIFY_THROWS_EXCEPTION(ProtocolError, decodeFrame(encodePacket(header, wave + "extra")));
        QVERIFY_THROWS_EXCEPTION(ProtocolError, decodeFrame(encodePacket(header, wave.left(8))));
        // Protocol version 1 (and anything else) is rejected.
        QVERIFY_THROWS_EXCEPTION(ProtocolError, decodeFrame(encodePacket(QByteArray(header).replace("\"version\":2", "\"version\":1"), wave)));
        QVERIFY_THROWS_EXCEPTION(ProtocolError, decodeFrame(encodePacket(QByteArray(header).replace("\"version\":2", "\"version\":3"), wave)));
        QVERIFY_THROWS_EXCEPTION(ProtocolError, decodeFrame(encodePacket(QByteArray(header).replace("\"seq\":0", "\"seq\":-1"), wave)));
        QVERIFY_THROWS_EXCEPTION(ProtocolError, decodeFrame(encodePacket(QByteArray(header).replace("float32", "float64"), wave)));
        // Valid JSON whose configuration is not an object fails the config-type check.
        QVERIFY_THROWS_EXCEPTION(ProtocolError, decodeFrame(encodePacket(QByteArray(header).replace(kBothConfig, "\"config\":[1]"), wave)));
        QVERIFY_THROWS_EXCEPTION(ProtocolError, decodeFrame(QByteArray("\x01\x00", 2)));
    }

    void decodesReplayContainer() {
        const QByteArray wave = floats({0.0f, 1.0f, 2.0f});
        const QByteArray header = QByteArray(R"({"version":2,"seq":0,"generation":0,"emitted_at_ms":0,)") + kBothConfig
            + R"(,"arrays":[{"name":"waveform","dtype":"float32","shape":[1,1,3],"offset":0,"nbytes":12}]})";
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
