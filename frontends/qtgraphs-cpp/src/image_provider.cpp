#include "image_provider.h"

#include <QStringView>
#include <QtEndian>
#include <algorithm>
#include <cstring>

namespace plotbench {

namespace {

void freeBuffer(void *buffer) {
    delete[] static_cast<uchar *>(buffer);
}

void releaseByteArray(void *holder) {
    delete static_cast<QByteArray *>(holder);
}

}  // namespace

FrameImageProvider::FrameImageProvider() : QQuickImageProvider(QQuickImageProvider::Image) {}

void FrameImageProvider::setColorTable(QList<QRgb> table) {
    m_colorTable = std::move(table);
}

void FrameImageProvider::setPlotCount(int count) {
    QMutexLocker locker(&m_lock);
    m_images.resize(std::max(0, count));
}

int FrameImageProvider::plotCount() const {
    QMutexLocker locker(&m_lock);
    return int(m_images.size());
}

QImage::Format FrameImageProvider::updateImage(int plot, const Frame &frame, const ArrayView &view) {
    // v2 shapes: scalar [plots, height, width], RGB [plots, height, width, 3]. The decoder accepts
    // any 1..4-D shape when the packet carries no configuration, so refuse anything else here
    // instead of indexing past the shape.
    const bool scalar = view.dtype == QLatin1String("float32");
    if (view.shape.size() != (scalar ? 3 : 4) || (!scalar && view.shape.last() != 3)) {
        throw ProtocolError("image array must be [image_plots, height, width] or [image_plots, height, width, 3]");
    }
    if (plot < 0 || plot >= view.plots()) {
        throw ProtocolError("image plot index outside the array");
    }
    const int height = view.shape.at(1);
    const int width = view.shape.at(2);
    const char *source = frame.plotData(view, plot);  // the plot's contiguous slice, no copy
    QImage image;
    if (scalar) {
        // Scalar [0,1] -> uint8 index = truncate(clamp(v) * 255) in float32 arithmetic, as in the
        // Python adapters; the colour expansion happens when Qt Quick uploads the Indexed8 texture.
        const qsizetype stride = (qsizetype(width) + 3) & ~qsizetype(3);
        uchar *buffer = new uchar[stride * height];
        for (int row = 0; row < height; ++row) {
            const char *in = source + qsizetype(row) * width * 4;
            uchar *out = buffer + qsizetype(row) * stride;
            for (int column = 0; column < width; ++column) {
                float value = qFromLittleEndian<float>(reinterpret_cast<const uchar *>(in) + qsizetype(column) * 4);
                value = std::clamp(value, 0.0f, 1.0f) * 255.0f;
                out[column] = static_cast<uchar>(value);
            }
        }
        image = QImage(buffer, width, height, int(stride), QImage::Format_Indexed8, freeBuffer, buffer);
        image.setColorTable(m_colorTable);
    } else {
        // RGB888 rows straight from the packet at the plot's offset; the QByteArray copy keeps the
        // bytes alive (shared, not deep-copied).
        const qsizetype stride = qsizetype(width) * 3;
        if (stride % 4 == 0) {
            auto *holder = new QByteArray(frame.packet);
            const uchar *pixels = reinterpret_cast<const uchar *>(holder->constData() + frame.payloadBase + view.offset
                                                                  + view.plotOffset(plot));
            image = QImage(pixels, width, height, int(stride), QImage::Format_RGB888, releaseByteArray, holder);
        } else {
            const qsizetype aligned = (stride + 3) & ~qsizetype(3);
            uchar *buffer = new uchar[aligned * height];
            for (int row = 0; row < height; ++row) {
                std::memcpy(buffer + qsizetype(row) * aligned, source + qsizetype(row) * stride, size_t(stride));
            }
            image = QImage(buffer, width, height, int(aligned), QImage::Format_RGB888, freeBuffer, buffer);
        }
    }
    QMutexLocker locker(&m_lock);
    if (plot >= m_images.size()) {
        m_images.resize(plot + 1);
    }
    m_images[plot] = image;
    return image.format();
}

QImage FrameImageProvider::requestImage(const QString &id, QSize *size, const QSize &requestedSize) {
    // "<plot>/<generation>/<seq>": only the leading plot index selects the image; the rest
    // makes every frame a distinct, uncached URL.
    const qsizetype slash = id.indexOf(QLatin1Char('/'));
    bool ok = false;
    const int plot = (slash > 0 ? QStringView(id).left(slash) : QStringView(id)).toInt(&ok);
    QImage image = current(ok ? plot : 0);
    if (size) {
        *size = image.size();
    }
    if (requestedSize.isValid() && requestedSize != image.size()) {
        return image.scaled(requestedSize, Qt::IgnoreAspectRatio, Qt::FastTransformation);
    }
    return image;
}

QImage FrameImageProvider::current(int plot) const {
    QMutexLocker locker(&m_lock);
    return plot >= 0 && plot < m_images.size() ? m_images.at(plot) : QImage();
}

}  // namespace plotbench
