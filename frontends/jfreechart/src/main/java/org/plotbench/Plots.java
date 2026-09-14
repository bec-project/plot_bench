package org.plotbench;

import java.awt.*;
import java.awt.geom.Rectangle2D;
import java.awt.image.*;
import java.nio.ByteBuffer;
import javax.swing.*;
import org.jfree.chart.*;
import org.jfree.chart.annotations.AbstractXYAnnotation;
import org.jfree.chart.axis.NumberAxis;
import org.jfree.chart.plot.*;
import org.jfree.chart.renderer.xy.XYLineAndShapeRenderer;
import org.jfree.data.xy.AbstractXYDataset;

/** JFreeChart axes and waveform; a nearest-neighbor Java2D image annotation. */
final class Plots {
  static final Color BACKGROUND = new Color(0x111e28),
      TEXT = new Color(0xd8e6ed),
      MUTED = new Color(0x8fa7b6);

  static final class Wave extends AbstractXYDataset {
    double[] values = new double[0];

    public int getSeriesCount() {
      return 1;
    }

    public Comparable<String> getSeriesKey(int series) {
      return "Waveform";
    }

    public int getItemCount(int series) {
      return values.length;
    }

    public Number getX(int series, int item) {
      return item;
    }

    public Number getY(int series, int item) {
      return values[item];
    }

    public double getXValue(int series, int item) {
      return item;
    }

    public double getYValue(int series, int item) {
      return values[item];
    }

    void update(ByteBuffer data) {
      if (values.length != data.remaining() / 4) values = new double[data.remaining() / 4];
      for (int i = 0; i < values.length; i++) values[i] = data.getFloat(i * 4);
    }
  }

  static final class Pixels extends AbstractXYAnnotation {
    BufferedImage image;

    void update(ByteBuffer data, Protocol.Config c, int[] palette) {
      if (image == null || image.getWidth() != c.width() || image.getHeight() != c.height())
        image = new BufferedImage(c.width(), c.height(), BufferedImage.TYPE_INT_ARGB);
      int[] dest = ((DataBufferInt) image.getRaster().getDataBuffer()).getData();
      for (int i = 0; i < dest.length; i++) {
        if (c.imageMode().equals("rgb"))
          dest[i] =
              0xff000000
                  | (data.get(i * 3) & 255) << 16
                  | (data.get(i * 3 + 1) & 255) << 8
                  | data.get(i * 3 + 2) & 255;
        else dest[i] = palette[(int) (Math.max(0, Math.min(1, data.getFloat(i * 4))) * 255)];
      }
    }

    @Override
    public void draw(
        Graphics2D g,
        XYPlot plot,
        Rectangle2D area,
        org.jfree.chart.axis.ValueAxis x,
        org.jfree.chart.axis.ValueAxis y,
        int rendererIndex,
        PlotRenderingInfo info) {
      if (image == null) return;
      g.setRenderingHint(
          RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_NEAREST_NEIGHBOR);
      g.drawImage(
          image,
          (int) area.getX(),
          (int) area.getY(),
          (int) area.getMaxX(),
          (int) area.getMaxY(),
          0,
          0,
          image.getWidth(),
          image.getHeight(),
          null);
    }
  }

  static final class Surface extends JPanel {
    final JFreeChart chart;
    final ChartRenderingInfo info = new ChartRenderingInfo(null);
    BufferedImage buffer;
    double scale = 1;

    Surface(String title, XYPlot plot) {
      chart = new JFreeChart(title, new Font(Font.SANS_SERIF, Font.BOLD, 16), plot, false);
      chart.setBackgroundPaint(BACKGROUND);
      chart.getTitle().setPaint(TEXT);
      chart.setAntiAlias(false);
      chart.setTextAntiAlias(true);
      plot.setBackgroundPaint(BACKGROUND);
      plot.setOutlinePaint(new Color(0x253745));
      plot.setDomainGridlinesVisible(false);
      plot.setRangeGridlinesVisible(false);
      for (var axis :
          new org.jfree.chart.axis.ValueAxis[] {plot.getDomainAxis(), plot.getRangeAxis()}) {
        axis.setLabelPaint(MUTED);
        axis.setTickLabelPaint(MUTED);
        axis.setAxisLinePaint(MUTED);
        axis.setTickMarkPaint(MUTED);
      }
      setBackground(BACKGROUND);
      setDoubleBuffered(false);
    }

    void render() {
      scale =
          getGraphicsConfiguration() == null
              ? 1
              : getGraphicsConfiguration().getDefaultTransform().getScaleX();
      int w = Math.max(1, (int) Math.ceil(getWidth() * scale)),
          h = Math.max(1, (int) Math.ceil(getHeight() * scale));
      if (buffer == null || buffer.getWidth() != w || buffer.getHeight() != h)
        buffer = new BufferedImage(w, h, BufferedImage.TYPE_INT_RGB);
      Graphics2D g = buffer.createGraphics();
      try {
        g.scale(scale, scale);
        if (chart.getXYPlot().getRenderer() instanceof XYLineAndShapeRenderer renderer)
          renderer.setDefaultStroke(new BasicStroke((float) (1 / scale)), false);
        chart.draw(g, new Rectangle2D.Double(0, 0, getWidth(), getHeight()), info);
      } finally {
        g.dispose();
      }
      repaint();
    }

    java.util.List<Double> viewport() {
      Rectangle2D r = info.getPlotInfo().getDataArea();
      return java.util.List.of(r.getWidth() * scale, r.getHeight() * scale);
    }

    @Override
    protected void paintComponent(Graphics graphics) {
      super.paintComponent(graphics);
      if (buffer != null) graphics.drawImage(buffer, 0, 0, getWidth(), getHeight(), null);
    }
  }

  final Wave wave = new Wave();
  final Pixels pixels = new Pixels();
  final XYPlot waveformPlot =
      new XYPlot(
          wave,
          new NumberAxis("Sample"),
          new NumberAxis("Amplitude"),
          new XYLineAndShapeRenderer(true, false));
  final XYPlot imagePlot = new XYPlot(null, new NumberAxis("Column"), new NumberAxis("Row"), null);
  final Surface waveform = new Surface("Waveform", waveformPlot),
      image = new Surface("Image · Java2D annotation", imagePlot);

  Plots() {
    waveformPlot.getRenderer().setSeriesPaint(0, new Color(0x64dccc));
    ((XYLineAndShapeRenderer) waveformPlot.getRenderer()).setDrawSeriesLineAsPath(true);
    waveformPlot.getRangeAxis().setRange(-1.5, 1.5);
    imagePlot.getRangeAxis().setInverted(true);
    imagePlot.addAnnotation(pixels);
  }

  double[] update(Protocol.Frame f, int[] palette) {
    long start = System.nanoTime();
    if (f.arrays().containsKey("waveform")) wave.update(f.arrays().get("waveform"));
    if (f.arrays().containsKey("image"))
      pixels.update(f.arrays().get("image"), f.config(), palette);
    long converted = System.nanoTime();
    if (f.arrays().containsKey("waveform")) {
      waveformPlot.getDomainAxis().setRange(0, Math.max(1, f.config().points() - 1));
      waveform.render();
    }
    if (f.arrays().containsKey("image")) {
      imagePlot.getDomainAxis().setRange(0, f.config().width());
      imagePlot.getRangeAxis().setRange(0, f.config().height());
      image.render();
    }
    long finished = System.nanoTime();
    return new double[] {
      (finished - start) / 1e6, (converted - start) / 1e6, (finished - converted) / 1e6
    };
  }
}
