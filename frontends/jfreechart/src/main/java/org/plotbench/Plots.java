package org.plotbench;

import java.awt.*;
import java.awt.geom.Rectangle2D;
import java.awt.image.*;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.ArrayList;
import java.util.List;
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
    double[][] values = new double[0][];

    public int getSeriesCount() {
      return values.length;
    }

    public Comparable<String> getSeriesKey(int series) {
      return "Curve " + (series + 1);
    }

    public int getItemCount(int series) {
      return values[series].length;
    }

    public Number getX(int series, int item) {
      return item;
    }

    public Number getY(int series, int item) {
      return values[series][item];
    }

    public double getXValue(int series, int item) {
      return item;
    }

    public double getYValue(int series, int item) {
      return values[series][item];
    }

    void update(ByteBuffer data, int curves, int points) {
      if (values.length != curves || values[0].length != points)
        values = new double[curves][points];
      for (int c = 0; c < curves; c++)
        for (int i = 0; i < points; i++) values[c][i] = data.getFloat((c * points + i) * 4);
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
    double dataWidth = 1, dataHeight = 1, axisWidth = 100, axisHeight = 80;

    void dataSize(double width, double height) {
      dataWidth = width;
      dataHeight = height;
    }

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
        g.setColor(BACKGROUND);
        g.fillRect(0, 0, getWidth(), getHeight());
        chart.draw(g, new Rectangle2D.Double(0, 0, dataWidth + axisWidth, dataHeight + axisHeight), info);
        Rectangle2D area = info.getPlotInfo().getDataArea();
        // Native title/axis spacing is learned from the previous layout. It settles
        // during warmup; metadata reports the actual rectangle, never the target.
        // Java2D rounds layout to device pixels. Do not integrate a subpixel
        // residual forever: that alternates adjacent pixel sizes between frames.
        double dx = dataWidth - area.getWidth(), dy = dataHeight - area.getHeight();
        if (Math.abs(dx) > 0.5 / scale)
          axisWidth = Math.max(0, Math.min(300, axisWidth + dx));
        if (Math.abs(dy) > 0.5 / scale)
          axisHeight = Math.max(0, Math.min(300, axisHeight + dy));
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

  static final int[] CURVE_COLORS = {
    0x64dccc, 0xf5c76e, 0x7aa6ff, 0xff9d7a, 0xc39bff, 0x9be564, 0xff7ab8, 0x6ee7ff
  };

  final List<Wave> waves = new ArrayList<>();
  final List<Pixels> pixels = new ArrayList<>();
  final List<Surface> waveforms = new ArrayList<>(), images = new ArrayList<>();
  Protocol.Config config;
  JPanel grid;

  boolean configure(Protocol.Config c, JPanel grid) {
    if (config != null
        && config.generation() == c.generation()
        && config.view().equals(c.view())
        && config.waveformPlots() == c.waveformPlots()
        && config.imagePlots() == c.imagePlots()
        && config.curves() == c.curves()) return false;
    config = c;
    this.grid = grid;
    waves.clear();
    pixels.clear();
    waveforms.clear();
    images.clear();
    grid.removeAll();
    int nw = c.view().equals("image") ? 0 : c.waveformPlots();
    int ni = c.view().equals("waveform") ? 0 : c.imagePlots();
    int columns = (int) Math.ceil(Math.sqrt(nw + ni));
    grid.setLayout(new GridLayout(0, columns, 16, 16));
    for (int p = 0; p < nw; p++) {
      Wave wave = new Wave();
      var renderer = new XYLineAndShapeRenderer(true, false);
      renderer.setDrawSeriesLineAsPath(true);
      renderer.setAutoPopulateSeriesStroke(false);
      for (int curve = 0; curve < c.curves(); curve++)
        renderer.setSeriesPaint(curve, new Color(CURVE_COLORS[curve % CURVE_COLORS.length]));
      var plot = new XYPlot(wave, new NumberAxis("Sample"), new NumberAxis("Amplitude"), renderer);
      plot.getRangeAxis().setRange(-1.5, 1.5);
      Surface surface = new Surface(nw == 1 ? "Waveform" : "Waveform " + (p + 1), plot);
      waves.add(wave);
      waveforms.add(surface);
      grid.add(surface);
    }
    for (int p = 0; p < ni; p++) {
      Pixels image = new Pixels();
      var plot = new XYPlot(null, new NumberAxis("Column"), new NumberAxis("Row"), null);
      plot.getRangeAxis().setInverted(true);
      plot.addAnnotation(image);
      Surface surface = new Surface(ni == 1 ? "Image" : "Image " + (p + 1), plot);
      if (nw + ni > 1) {
        surface.chart.setTitle((String) null);
        plot.getDomainAxis().setVisible(false);
        plot.getRangeAxis().setVisible(false);
      }
      pixels.add(image);
      images.add(surface);
      grid.add(surface);
    }
    grid.revalidate();
    return true;
  }

  static double[] dataSlot(double width, double height, int count, boolean image) {
    double columns = Math.ceil(Math.sqrt(count)), rows = Math.ceil(count / columns);
    double horizontal = image ? (count > 1 ? 16 : 96) : 100, vertical = image ? (count > 1 ? 16 : 100) : 120;
    return new double[] {
      Math.max(1, Math.floor((width - 48 - 16 * (columns - 1)) / columns - horizontal)),
      Math.max(1, Math.floor((height - 220 - 16 * (rows - 1)) / rows - vertical))
    };
  }

  static ByteBuffer plotSlice(ByteBuffer data, int plot, int bytes) {
    return data.slice(plot * bytes, bytes).order(ByteOrder.LITTLE_ENDIAN);
  }

  double[] update(Protocol.Frame f, int[] palette) {
    long start = System.nanoTime();
    JRootPane root = grid == null ? null : SwingUtilities.getRootPane(grid);
    double windowWidth = root == null ? 1100 : root.getContentPane().getWidth();
    double windowHeight = root == null ? 820 : root.getContentPane().getHeight();
    double[] slot = dataSlot(windowWidth, windowHeight, waveforms.size() + images.size(), false);
    for (Surface waveform : waveforms) waveform.dataSize(slot[0], slot[1]);
    double[] imageSlot = dataSlot(windowWidth, windowHeight, waveforms.size() + images.size(), true);
    double fit = Math.min(imageSlot[0] / f.config().width(), imageSlot[1] / f.config().height());
    for (Surface image : images) image.dataSize(f.config().width() * fit, f.config().height() * fit);
    var c = f.config();
    for (int p = 0; p < waves.size(); p++)
      waves.get(p).update(
          plotSlice(f.arrays().get("waveform"), p, c.curves() * c.points() * 4),
          c.curves(),
          c.points());
    int imageBytes = c.width() * c.height() * (c.imageMode().equals("rgb") ? 3 : 4);
    for (int p = 0; p < pixels.size(); p++)
      pixels.get(p).update(plotSlice(f.arrays().get("image"), p, imageBytes), c, palette);
    long converted = System.nanoTime();
    for (Surface waveform : waveforms) {
      waveform.chart.getXYPlot().getDomainAxis().setRange(0, Math.max(1, c.points() - 1));
      waveform.render();
    }
    for (Surface image : images) {
      image.chart.getXYPlot().getDomainAxis().setRange(0, c.width());
      image.chart.getXYPlot().getRangeAxis().setRange(0, c.height());
      image.render();
    }
    long finished = System.nanoTime();
    return new double[] {
      (finished - start) / 1e6, (converted - start) / 1e6, (finished - converted) / 1e6
    };
  }
}
