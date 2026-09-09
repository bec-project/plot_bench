// Custom image path: the current frame as an Indexed8 (scalar + shared colour table) or RGB888 QImage.
#pragma once

#include <QImage>
#include <QList>
#include <QMutex>
#include <QQuickImageProvider>
#include <QRgb>

#include "protocol.h"

namespace plotbench {

class FrameImageProvider : public QQuickImageProvider {
public:
    FrameImageProvider();

    // The 256-entry RGB colour table fetched from GET /api/colormap.
    void setColorTable(QList<QRgb> table);
    bool hasColorTable() const { return m_colorTable.size() == 256; }

    // Convert the frame's image array into the provider's current QImage. Returns the format used.
    QImage::Format updateImage(const Frame &frame, const ArrayView &view);

    QImage requestImage(const QString &id, QSize *size, const QSize &requestedSize) override;
    QImage current() const;

private:
    QList<QRgb> m_colorTable;
    mutable QMutex m_lock;
    QImage m_image;
};

}  // namespace plotbench
