#include "image_provider.h"

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

QImage::Format FrameImageProvider::updateImage(const Frame &frame, const ArrayView &view) {
    const int height = view.shape.at(0);
    const int width = view.shape.at(1);
    QImage image;
    if (view.dtype == QLatin1String("float32")) {
        // Scalar [0,1] -> uint8 index = truncate(clamp(v) * 255) in float32 arithmetic, as in the
        // Python adapters; the colour expansion happens when Qt Quick uploads the Indexed8 texture.
        const qsizetype stride = (qsizetype(width) + 3) & ~qsizetype(3);
        uchar *buffer = new uchar[stride * height];
        const char *source = frame.data(view);
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
        // RGB888 rows straight from the packet; the QByteArray copy keeps the bytes alive (shared).
        const qsizetype stride = qsizetype(width) * 3;
        if (stride % 4 == 0) {
            auto *holder = new QByteArray(frame.packet);
            const uchar *pixels = reinterpret_cast<const uchar *>(holder->constData() + frame.payloadBase + view.offset);
            image = QImage(pixels, width, height, int(stride), QImage::Format_RGB888, releaseByteArray, holder);
        } else {
            const qsizetype aligned = (stride + 3) & ~qsizetype(3);
            uchar *buffer = new uchar[aligned * height];
            const char *source = frame.data(view);
            for (int row = 0; row < height; ++row) {
                std::memcpy(buffer + qsizetype(row) * aligned, source + qsizetype(row) * stride, size_t(stride));
            }
            image = QImage(buffer, width, height, int(aligned), QImage::Format_RGB888, freeBuffer, buffer);
        }
    }
    QMutexLocker locker(&m_lock);
    m_image = image;
    return image.format();
}

QImage FrameImageProvider::requestImage(const QString &, QSize *size, const QSize &requestedSize) {
    QImage image = current();
    if (size) {
        *size = image.size();
    }
    if (requestedSize.isValid() && requestedSize != image.size()) {
        return image.scaled(requestedSize, Qt::IgnoreAspectRatio, Qt::FastTransformation);
    }
    return image;
}

QImage FrameImageProvider::current() const {
    QMutexLocker locker(&m_lock);
    return m_image;
}

}  // namespace plotbench
