// Custom image path: one Indexed8 (scalar + shared colour table) or RGB888 QImage per image plot.
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

    // Keep exactly `count` per-plot images (dropping or adding empty slots).
    void setPlotCount(int count);
    int plotCount() const;

    // Convert image plot `plot` of the frame's [plots, h, w(, 3)] array into that plot's QImage.
    // Returns the format used; throws ProtocolError for any other shape or a plot outside it.
    QImage::Format updateImage(int plot, const Frame &frame, const ArrayView &view);

    // Image ids are "<plot>/<generation>/<seq>"; the plot index selects the image.
    QImage requestImage(const QString &id, QSize *size, const QSize &requestedSize) override;
    QImage current(int plot = 0) const;

private:
    QList<QRgb> m_colorTable;
    mutable QMutex m_lock;
    QList<QImage> m_images;
};

}  // namespace plotbench
