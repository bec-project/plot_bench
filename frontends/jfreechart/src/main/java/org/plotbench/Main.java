package org.plotbench;

import java.awt.*;
import java.awt.event.*;
import java.lang.management.ManagementFactory;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;
import javax.swing.*;

public final class Main {
  final Source source;
  final Metrics metrics;
  final Plots plots = new Plots();
  final JFrame window = new JFrame("Plotbench · JFreeChart");
  final JPanel plotRow = new JPanel(new GridLayout(1, 0, 16, 0));
  final JLabel workload = new JLabel("Waiting for source…"), status = new JLabel("Connecting");
  final JLabel[] indicators = {new JLabel(), new JLabel(), new JLabel(), new JLabel()};
  final JToggleButton one = new JToggleButton("1D"), two = new JToggleButton("2D");
  final AtomicBoolean queued = new AtomicBoolean();
  final double duration;
  final boolean recorded;
  final javax.swing.Timer timer;
  long started, lastHud, lastCount;
  boolean closing;
  String view = "";

  static Map<String, Object> runtimeInfo() throws Exception {
    Map<String, Object> info = new LinkedHashMap<>();
    info.put("java", System.getProperty("java.version"));
    info.put("java_feature", Runtime.version().feature());
    info.put("java_vendor", System.getProperty("java.vendor"));
    info.put("java_vm", System.getProperty("java.vm.name"));
    Properties library = new Properties();
    try (var stream =
        org.jfree.chart.JFreeChart.class.getResourceAsStream(
            "/META-INF/maven/org.jfree/jfreechart/pom.properties")) {
      library.load(stream);
    }
    info.put("jfreechart", library.getProperty("version"));
    info.put("jackson", Protocol.JSON.version().toString());
    try (var stream = Main.class.getResourceAsStream("/build-info.json")) {
      info.put("build", Protocol.JSON.readTree(stream));
    }
    info.put("jvm_arguments", ManagementFactory.getRuntimeMXBean().getInputArguments());
    info.put("headless", GraphicsEnvironment.isHeadless());
    info.put(
        "display_protocol",
        System.getProperty("os.name").startsWith("Mac") ? "native" : "unvalidated");
    return info;
  }

  static Map<String, String> arguments(String[] args) {
    Map<String, String> values =
        new HashMap<>(
            Map.of(
                "url",
                "http://127.0.0.1:8765",
                "mode",
                "stream",
                "run-id",
                "demo",
                "duration",
                "0",
                "width",
                "1100",
                "height",
                "820"));
    for (int i = 0; i < args.length; i += 2) {
      if (!args[i].startsWith("--")
          || !values.containsKey(args[i].substring(2))
          || i + 1 == args.length)
        throw new IllegalArgumentException(
            "Expected --url, --mode, --run-id, --duration, --width or --height followed by a"
                + " value");
      values.put(args[i].substring(2), args[i + 1]);
    }
    if (!Set.of("stream", "replay").contains(values.get("mode")))
      throw new IllegalArgumentException("Invalid mode");
    double seconds = Double.parseDouble(values.get("duration"));
    if (!Double.isFinite(seconds) || seconds < 0)
      throw new IllegalArgumentException("Invalid duration");
    if (Integer.parseInt(values.get("width")) < 400 || Integer.parseInt(values.get("height")) < 400)
      throw new IllegalArgumentException("Window dimensions must be at least 400");
    return values;
  }

  public static void main(String[] args) throws Exception {
    if (Arrays.equals(args, new String[] {"--runtime-info"})) {
      System.out.println(Protocol.JSON.writeValueAsString(runtimeInfo()));
      return;
    }
    Map<String, String> options = arguments(args);
    if (!System.getProperty("os.name").startsWith("Mac") || GraphicsEnvironment.isHeadless())
      throw new IllegalStateException(
          "Visible JFreeChart runs currently require macOS. Native Wayland Swing is unvalidated; no"
              + " XWayland fallback.");
    Map<String, Object> versions = runtimeInfo();
    SwingUtilities.invokeAndWait(() -> new Main(options, versions));
  }

  Main(Map<String, String> args, Map<String, Object> versions) {
    duration = Double.parseDouble(args.get("duration"));
    recorded = duration > 0 || !args.get("run-id").equals("demo");
    source = new Source(args.get("url"), args.get("mode"));
    metrics =
        new Metrics(
            source,
            args.get("run-id"),
            Map.of(
                "renderer",
                "JFreeChart / Java2D BufferedImage + Swing blit",
                "measurement_stage",
                "float32→double and scalar/RGB→ARGB conversion, dataset/range update and"
                    + " synchronous JFreeChart Java2D rasterization; Swing blit and screen"
                    + " presentation deferred",
                "versions",
                versions,
                "display_protocol",
                "native",
                "update_strategy",
                "full authoritative window; no decimation; one reusable raster per plot",
                "expected_duration",
                duration,
                "termination_reason",
                "error",
                "active_seconds",
                0.0));
    JPanel root = new JPanel(new BorderLayout(0, 8));
    root.setBackground(new Color(0x0b141c));
    root.setBorder(BorderFactory.createEmptyBorder(24, 24, 24, 24));
    JPanel top = new JPanel();
    top.setLayout(new BoxLayout(top, BoxLayout.Y_AXIS));
    top.setOpaque(false);
    JLabel heading =
        new JLabel("JFreeChart · Java2D · " + source.mode);
    heading.setAlignmentX(Component.LEFT_ALIGNMENT);
    workload.setAlignmentX(Component.LEFT_ALIGNMENT);
    heading.setFont(new Font(Font.SANS_SERIF, Font.BOLD, 20));
    JPanel actions = new JPanel(new FlowLayout(FlowLayout.LEFT, 8, 0));
    actions.setOpaque(false);
    actions.setAlignmentX(Component.LEFT_ALIGNMENT);
    actions.add(heading);
    actions.add(status);
    JButton controls = new JButton("Source controls");
    controls.setEnabled(!recorded);
    controls.addActionListener(
        e -> {
          try {
            Desktop.getDesktop().browse(source.endpoint("/"));
          } catch (Exception ex) {
            status.setText(ex.toString());
          }
        });
    actions.add(controls);
    actions.add(new JLabel("PLOTS"));
    actions.add(one);
    actions.add(two);
    top.add(actions);
    one.getAccessibleContext().setAccessibleName("Show waveform");
    two.getAccessibleContext().setAccessibleName("Show image");
    one.setEnabled(!recorded);
    two.setEnabled(!recorded);
    one.setUI(new javax.swing.plaf.basic.BasicToggleButtonUI());
    two.setUI(new javax.swing.plaf.basic.BasicToggleButtonUI());
    one.addActionListener(e -> requestView());
    two.addActionListener(e -> requestView());
    top.add(workload);
    top.add(Box.createVerticalStrut(8));
    JPanel hud = new JPanel(new GridLayout(1, 4, 14, 0));
    hud.setOpaque(false);
    hud.setPreferredSize(new Dimension(100,48));
    hud.setMaximumSize(new Dimension(Integer.MAX_VALUE,48));
    hud.setAlignmentX(Component.LEFT_ALIGNMENT);
    for (JLabel label : indicators) {
      label.setBorder(BorderFactory.createEmptyBorder(4, 12, 4, 12));
      label.setOpaque(true);
      label.setBackground(Plots.BACKGROUND);
      hud.add(label);
    }
    top.add(hud);
    root.add(top, BorderLayout.NORTH);
    plotRow.setOpaque(false);
    root.add(plotRow, BorderLayout.CENTER);
    JLabel footer =
        new JLabel(
            "Submitted updates · not displayed FPS   |   JFreeChart waveform/axes · custom"
                + " nearest-neighbor image annotation");
    root.add(footer, BorderLayout.SOUTH);
    colorLabels(root);
    root.setPreferredSize(
        new Dimension(Integer.parseInt(args.get("width")), Integer.parseInt(args.get("height"))));
    window.setContentPane(root);
    window.pack();
    window.setDefaultCloseOperation(WindowConstants.DO_NOTHING_ON_CLOSE);
    window.addWindowListener(
        new WindowAdapter() {
          @Override
          public void windowClosing(WindowEvent e) {
            finish("user");
          }
        });
    window.setVisible(true);
    timer = new javax.swing.Timer(50, e -> tick());
    timer.start();
    source.wake = this::schedule;
    source.start();
  }

  static void colorLabels(Container container) {
    for (Component c : container.getComponents()) {
      if (c instanceof JLabel) c.setForeground(Plots.TEXT);
      if (c instanceof Container child) colorLabels(child);
    }
  }

  void requestView() {
    if (!one.isSelected() && !two.isSelected()) {
      one.setSelected(!view.equals("image"));
      two.setSelected(view.equals("image"));
      return;
    }
    source.requestView(one.isSelected() ? (two.isSelected() ? "both" : "waveform") : "image");
  }

  void schedule() {
    if (queued.compareAndSet(false, true))
      SwingUtilities.invokeLater(
          () -> {
            try {
              adopt();
            } catch (Exception ex) {
              source.fail(ex);
              finish("error");
            } finally {
              queued.set(false);
              if (!closing && source.latest.get() != null) schedule();
            }
          });
  }

  void adopt() {
    if (closing) return;
    Source.Taken taken = source.take();
    if (taken == null) return;
    Protocol.Config c = taken.frame().config();
    view = c.view();
    if (plots.configure(c, plotRow)) window.validate();
    double[] timing = plots.update(taken.frame(), source.palette);
    if (started == 0) {
      started = System.nanoTime();
      lastHud = started;
    }
    metrics.record(taken, timing[0], timing[1], timing[2]);
  }

  void tick() {
    if (closing) return;
    if (source.error != null || metrics.error != null) {
      finish("error");
      return;
    }
    long now = System.nanoTime();
    if (started != 0 && duration > 0 && (now - started) / 1e9 >= duration) {
      finish("duration");
      return;
    }
    if (now - lastHud < 500_000_000L) return;
    double hz = started == 0 ? 0 : (metrics.count - lastCount) * 1e9 / (now - lastHud);
    lastHud = now;
    lastCount = metrics.count;
    status.setText(source.viewError != null ? source.viewError : source.status);
    Protocol.Config c = source.current;
    if (c == null) return;
    one.setSelected(!c.view().equals("image"));
    two.setSelected(!c.view().equals("waveform"));
    one.setEnabled(!recorded && !source.pending);
    two.setEnabled(!recorded && !source.pending);
    for (JToggleButton button : new JToggleButton[] {one, two}) {
      button.setBackground(button.isSelected() ? new Color(0x64dccc) : Plots.BACKGROUND);
      button.setForeground(button.isSelected() ? new Color(0x0b141c) : Plots.TEXT);
    }
    workload.setText(
        String.format(
            Locale.ROOT,
            "%.0f Hz · %,d points · %s (%d) · %d %s × %d %s · %d × %d %s · %d %s",
            c.hz(),
            c.points(),
            c.waveformMode(),
            c.appendCount(),
            c.waveformPlots(),
            c.waveformPlots() == 1 ? "plot" : "plots",
            c.curves(),
            c.curves() == 1 ? "curve" : "curves",
            c.width(),
            c.height(),
            c.imageMode(),
            c.imagePlots(),
            c.imagePlots() == 1 ? "plot" : "plots"));
    String[] values = {
      String.format(Locale.ROOT, "Submitted: %.1f updates/s", hz),
      String.format(Locale.ROOT, "Update time: %.2f ms", metrics.lastUpdate),
      "Skipped: " + metrics.skipped,
      "Receive age: "
          + (metrics.lastAge == null ? "—" : String.format(Locale.ROOT, "%.1f ms", metrics.lastAge))
    };
    String[] targets = {
      String.format(Locale.ROOT, "target %.0f Hz", c.hz()),
      String.format(Locale.ROOT, "budget %.1f ms", 1000 / c.hz()),
      "target 0",
      source.mode.equals("replay")
          ? "N/A"
          : String.format(Locale.ROOT, "goal %.1f ms", 1000 / c.hz())
    };
    for (int i = 0; i < 4; i++) {
      indicators[i].setText(
          "<html>" + values[i].replace(": ", "<br>") + "</html>");
      indicators[i].setToolTipText(targets[i] + "; these do not measure GPU or display deadlines.");
    }
    geometry();
  }

  void geometry() {
    if (started == 0) return;
    var gc = window.getGraphicsConfiguration();
    var device = gc.getDevice();
    var dm = device.getDisplayMode();
    metrics.set(Map.of("render_contract", "data-area-v2", "plot_viewports_all", Map.of(
        "waveform", plots.waveforms.stream().map(Plots.Surface::viewport).toList(),
        "image", plots.images.stream().map(Plots.Surface::viewport).toList())));
    Map<String, Object> areas = new HashMap<>();
    if (!view.equals("image")) areas.put("waveform", plots.waveforms.get(0).viewport());
    if (!view.equals("waveform")) areas.put("image", plots.images.get(0).viewport());
    metrics.set(
        Map.of(
            "pixel_ratio",
            gc.getDefaultTransform().getScaleX(),
            "viewport_size",
            java.util.List.of(
                window.getContentPane().getWidth(), window.getContentPane().getHeight()),
            "plot_viewports",
            areas,
            "plot_counts",
            Map.of("waveform", plots.waveforms.size(), "image", plots.images.size()),
            "curves",
            plots.config.curves(),
            "display",
            Map.of(
                "name",
                device.getIDstring(),
                "width",
                dm.getWidth(),
                "height",
                dm.getHeight(),
                "refresh_hz",
                dm.getRefreshRate(),
                "scale_y",
                gc.getDefaultTransform().getScaleY()),
            "receiver_connection_epoch",
            Math.max(1, source.epoch),
            "replay_frames",
            source.replayCount,
            "replay_bytes",
            source.replayBytes));
  }

  void finish(String reason) {
    if (closing) return;
    closing = true;
    timer.stop();
    geometry();
    double active = started == 0 ? 0 : (System.nanoTime() - started) / 1e9;
    metrics.set(Map.of("termination_reason", reason, "active_seconds", active));
    window.dispose();
    new Thread(
            () -> {
              source.close();
              metrics.close();
              if (source.error != null) System.err.println(source.error);
              System.exit(reason.equals("error") || metrics.error != null ? 1 : 0);
            },
            "plotbench-shutdown")
        .start();
  }
}
