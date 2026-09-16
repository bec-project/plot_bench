package org.plotbench;

import static org.junit.jupiter.api.Assertions.*;

import com.sun.net.httpserver.HttpServer;
import java.io.*;
import java.net.*;
import java.net.http.WebSocket;
import java.nio.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import javax.swing.SwingUtilities;
import org.junit.jupiter.api.Test;

class AdapterTest {
  @Test
  void compactSlotsMatchCommonVectors() {
    int[] counts = {1,2,4,6};
    double[][] images = {{956,500},{502,584},{502,276},{324,276}};
    double[][] waves = {{952,480},{418,480},{418,172},{240,172}};
    for (int i=0; i<counts.length; i++) {
      assertArrayEquals(images[i], Plots.dataSlot(1100,820,counts[i],true));
      assertArrayEquals(waves[i], Plots.dataSlot(1100,820,counts[i],false));
    }
  }

  @Test
  void imageAxesPreserveAspectAndConvergeToContract() throws Exception {
    SwingUtilities.invokeAndWait(() -> {
      for (int count : new int[] {1, 2, 4, 6}) {
        double[] slot = Plots.dataSlot(1100, 820, count, true);
        var plot = new org.jfree.chart.plot.XYPlot(null,
            new org.jfree.chart.axis.NumberAxis("Column"),
            new org.jfree.chart.axis.NumberAxis("Row"), null);
        plot.getDomainAxis().setRange(0, 640);
        plot.getRangeAxis().setRange(0, 360);
        var surface = new Plots.Surface("Image", plot);
        surface.setSize(1100, 820);
        double fit = Math.min(slot[0]/640, slot[1]/360);
        surface.dataSize(640*fit, 360*fit);
        for (int i=0; i<4; i++) surface.render();
        var area = surface.viewport();
        assertEquals(640*fit, area.get(0), 1.5);
        assertEquals(360*fit, area.get(1), 1.5);
        assertEquals(640.0/360, area.get(0)/area.get(1), 0.01);
        for (int i=0; i<30; i++) {
          surface.render();
          assertEquals(area, surface.viewport(), "data geometry must not oscillate after warmup");
        }
      }
    });
  }

  @Test
  void authoritativeSourcePacketsRenderEveryPlotAndCurve() throws Exception {
    Path directory = Path.of(System.getProperty("plotbench.protocolFixtures"));
    int[] palette = Protocol.palette(Files.readAllBytes(directory.resolve("palette.json")));
    try (var files = Files.list(directory)) {
      var packets = files.filter(p -> p.toString().endsWith(".bin")).sorted().toList();
      assertEquals(24, packets.size());
      Plots plots = new Plots();
      var grid = new javax.swing.JPanel();
      for (Path path : packets) {
        var frame = Protocol.decode(Files.readAllBytes(path));
        var expected = Protocol.JSON.readTree(
            Files.readAllBytes(path.resolveSibling(path.getFileName().toString().replace(".bin", ".json"))));
        SwingUtilities.invokeAndWait(() -> {
          var c = frame.config();
          assertTrue(plots.configure(c, grid));
          int nw = c.view().equals("image") ? 0 : c.waveformPlots();
          int ni = c.view().equals("waveform") ? 0 : c.imagePlots();
          assertEquals(nw, plots.waveforms.size());
          assertEquals(ni, plots.images.size());
          assertEquals(nw + ni, grid.getComponentCount());
          int columns = (int) Math.ceil(Math.sqrt(nw + ni));
          grid.setSize(columns * 400, ((nw + ni + columns - 1) / columns) * 300);
          grid.doLayout();
          plots.update(frame, palette);
          assertFalse(plots.configure(c, grid));
          for (int p = 0; p < nw; p++) {
            var wave = plots.waves.get(p);
            assertEquals(c.curves(), wave.getSeriesCount());
            var surface = plots.waveforms.get(p);
            assertTrue(surface.viewport().get(0) > 0);
            for (int curve = 0; curve < c.curves(); curve++) {
              assertEquals(c.points(), wave.getItemCount(curve));
              assertEquals(new java.awt.Color(Plots.CURVE_COLORS[curve % 8]),
                  surface.chart.getXYPlot().getRenderer().getSeriesPaint(curve));
              for (int point = 0; point < c.points(); point++)
                assertEquals(expected.path("waveform").get(p).get(curve).get(point).doubleValue(),
                    wave.getYValue(curve, point));
            }
          }
          for (int p = 0; p < ni; p++) {
            assertTrue(plots.images.get(p).viewport().get(0) > 0);
            for (int y = 0; y < c.height(); y++)
              for (int x = 0; x < c.width(); x++) {
                var pixel = expected.path("image").get(p).get(y).get(x);
                int color = c.imageMode().equals("rgb")
                    ? 0xff000000 | pixel.get(0).intValue() << 16 | pixel.get(1).intValue() << 8
                        | pixel.get(2).intValue()
                    : palette[(int) (pixel.doubleValue() * 255)];
                assertEquals(color, plots.pixels.get(p).image.getRGB(x, y));
              }
          }
        });
      }
    }
  }

  static byte[] packet(long seq, String view, String mode) throws Exception {
    Map<String, Object> config =
        new HashMap<>(
            Map.of(
                "hz",
                30,
                "points",
                3,
                "append_count",
                1,
                "width",
                2,
                "height",
                1,
                "waveform_mode",
                "append",
                "image_mode",
                mode,
                "view",
                view,
                "seed",
                42,
                "generation",
                0));
    config.put("curves", 1);
    config.put("waveform_plots", 1);
    config.put("image_plots", 1);
    List<Map<String, Object>> arrays = new ArrayList<>();
    ByteBuffer payload = ByteBuffer.allocate(32).order(ByteOrder.LITTLE_ENDIAN);
    if (!view.equals("image")) {
      arrays.add(
          Map.of(
              "name",
              "waveform",
              "dtype",
              "float32",
              "shape",
              List.of(1, 1, 3),
              "offset",
              0,
              "nbytes",
              12));
      payload.putFloat(-1).putFloat(0.25f).putFloat(1);
    }
    if (!view.equals("waveform")) {
      boolean rgb = mode.equals("rgb");
      arrays.add(
          Map.of(
              "name",
              "image",
              "dtype",
              rgb ? "uint8" : "float32",
              "shape",
              rgb ? List.of(1, 1, 2, 3) : List.of(1, 1, 2),
              "offset",
              payload.position(),
              "nbytes",
              rgb ? 6 : 8));
      if (rgb) payload.put(new byte[] {(byte) 255, 0, 1, 0, (byte) 255, 2});
      else payload.putFloat(0).putFloat(1);
    }
    byte[] h =
        Protocol.JSON.writeValueAsBytes(
            Map.of(
                "version",
                2,
                "seq",
                seq,
                "generation",
                0,
                "emitted_at_ms",
                123.0,
                "config",
                config,
                "arrays",
                arrays));
    int prefix = (4 + h.length + 3) & ~3;
    ByteBuffer result =
        ByteBuffer.allocate(prefix + payload.position()).order(ByteOrder.LITTLE_ENDIAN);
    result.putInt(h.length).put(h).position(prefix);
    result.put(payload.array(), 0, payload.position());
    return result.array();
  }

  static byte[] replay() throws Exception {
    byte[] first = packet(4, "both", "scalar"), second = packet(5, "both", "scalar");
    return ByteBuffer.allocate(12 + first.length + second.length)
        .order(ByteOrder.LITTLE_ENDIAN)
        .putInt(2)
        .putInt(first.length)
        .put(first)
        .putInt(second.length)
        .put(second)
        .array();
  }

  @Test
  void decodeViewsAndLayouts() throws Exception {
    for (String view : List.of("both", "image", "waveform"))
      for (String mode : List.of("scalar", "rgb")) {
        var f = Protocol.decode(packet(17, view, mode));
        assertEquals(17, f.seq());
        assertEquals("append", f.config().waveformMode());
        assertEquals(view.equals("both") ? 2 : 1, f.arrays().size());
        if (!view.equals("image")) {
          assertEquals(0.25f, f.arrays().get("waveform").getFloat(4));
          assertThrows(
              ReadOnlyBufferException.class, () -> f.arrays().get("waveform").putFloat(0, 1));
        }
        if (mode.equals("rgb") && !view.equals("waveform"))
          assertEquals(6, f.arrays().get("image").remaining());
      }
  }

  @Test
  void rejectTruncatedAndMalformedPackets() throws Exception {
    byte[] data = packet(0, "both", "rgb");
    for (int i = 0; i < data.length; i++) {
      byte[] partial = Arrays.copyOf(data, i);
      assertThrows(IllegalArgumentException.class, () -> Protocol.decode(partial));
    }
    assertThrows(
        IllegalArgumentException.class,
        () -> Protocol.decode(Arrays.copyOf(data, data.length + 1)));
    ByteBuffer.wrap(data).order(ByteOrder.LITTLE_ENDIAN).putInt(Integer.MAX_VALUE);
    assertThrows(IllegalArgumentException.class, () -> Protocol.decode(data));
    byte[] valid = packet(0, "both", "scalar");
    int len = ByteBuffer.wrap(valid).order(ByteOrder.LITTLE_ENDIAN).getInt();
    String header = new String(valid, 4, len, java.nio.charset.StandardCharsets.UTF_8);
    for (String modified :
        List.of(
            header.replace("\"nbytes\":12", "\"nbytes\":11"),
            header.replace("\"offset\":12", "\"offset\":13"),
            header.replace("\"curves\":1", "\"curves\":2"),
            header.replace("\"waveform_plots\":1", "\"waveform_plots\":2"),
            header.replace("\"image_plots\":1", "\"image_plots\":2"),
            header.replace("\"version\":2", "\"version\":1"))) {
      assertNotEquals(header, modified);
      byte[] broken = valid.clone();
      System.arraycopy(
          modified.getBytes(java.nio.charset.StandardCharsets.UTF_8), 0, broken, 4, len);
      assertThrows(IllegalArgumentException.class, () -> Protocol.decode(broken));
    }
  }

  @Test
  void replayIsBoundedAndConfigurationConsistent() throws Exception {
    byte[] data = replay();
    assertEquals(2, Protocol.replay(data).size());
    assertThrows(
        IllegalArgumentException.class,
        () -> Protocol.replay(Arrays.copyOf(data, data.length - 1)));
    assertThrows(
        IllegalArgumentException.class,
        () -> Protocol.replay(Arrays.copyOf(data, data.length + 1)));
    ByteBuffer.wrap(data).order(ByteOrder.LITTLE_ENDIAN).putInt(257);
    assertThrows(IllegalArgumentException.class, () -> Protocol.replay(data));
  }

  @Test
  void conversionsAndSynchronousRaster() throws Exception {
    int[] palette = new int[256];
    Arrays.fill(palette, 0xff123456);
    palette[255] = 0xffabcdef;
    var scalar = Protocol.decode(packet(0, "both", "scalar"));
    var rgb = Protocol.decode(packet(1, "both", "rgb"));
    SwingUtilities.invokeAndWait(
        () -> {
          Plots plots = new Plots();
          plots.configure(scalar.config(), new javax.swing.JPanel());
          var waveform = plots.waveforms.get(0);
          var image = plots.images.get(0);
          var pixels = plots.pixels.get(0);
          waveform.setSize(500, 400);
          image.setSize(500, 400);
          double[] times = plots.update(scalar, palette);
          assertArrayEquals(new double[] {-1, 0.25, 1}, plots.waves.get(0).values[0]);
          assertEquals(0xff123456, pixels.image.getRGB(0, 0));
          assertEquals(0xffabcdef, pixels.image.getRGB(1, 0));
          assertTrue(times[2] > 0);
          assertTrue(waveform.viewport().get(0) > 100);
          var reused = pixels.image;
          plots.update(rgb, palette);
          assertSame(reused, pixels.image);
          assertEquals(0xffff0001, pixels.image.getRGB(0, 0));
          assertEquals(0xff00ff02, pixels.image.getRGB(1, 0));
          // Rendered pixels exist before Swing ever paints a window.
          var area = image.info.getPlotInfo().getDataArea();
          assertEquals(
              0xffff0001,
              image.buffer.getRGB(
                  (int) (area.getX() + area.getWidth() / 4), (int) area.getCenterY()));
        });
  }

  @Test
  void latestMailboxCountsSkipsAndResetsOnReconnect() throws Exception {
    try (Source s = new Source("http://localhost:1", "stream")) {
      s.offer(Protocol.decode(packet(1, "waveform", "scalar")));
      assertEquals(0, s.take().skipped());
      s.offer(Protocol.decode(packet(2, "waveform", "scalar")));
      s.offer(Protocol.decode(packet(5, "waveform", "scalar")));
      assertEquals(3, s.take().skipped());
      assertNull(s.take());
      s.epoch++;
      s.offer(Protocol.decode(packet(20, "waveform", "scalar")));
      assertEquals(0, s.take().skipped());
    }
  }

  static final class SocketStub implements WebSocket {
    String ack;
    long requested;
    boolean aborted;

    public CompletableFuture<WebSocket> sendText(CharSequence s, boolean last) {
      ack = s.toString();
      return CompletableFuture.completedFuture(this);
    }

    public CompletableFuture<WebSocket> sendBinary(ByteBuffer b, boolean l) {
      throw new UnsupportedOperationException();
    }

    public CompletableFuture<WebSocket> sendPing(ByteBuffer b) {
      return CompletableFuture.completedFuture(this);
    }

    public CompletableFuture<WebSocket> sendPong(ByteBuffer b) {
      return CompletableFuture.completedFuture(this);
    }

    public CompletableFuture<WebSocket> sendClose(int c, String r) {
      return CompletableFuture.completedFuture(this);
    }

    public void request(long n) {
      requested += n;
    }

    public String getSubprotocol() {
      return "";
    }

    public boolean isOutputClosed() {
      return aborted;
    }

    public boolean isInputClosed() {
      return aborted;
    }

    public void abort() {
      aborted = true;
    }
  }

  @Test
  void fragmentedMessagesAckOnlyAfterDecodeAndOffer() throws Exception {
    try (Source s = new Source("http://localhost:1", "stream")) {
      SocketStub ws = new SocketStub();
      var session = s.new Session();
      session.onOpen(ws);
      byte[] data = packet(7, "both", "rgb");
      session.onBinary(ws, ByteBuffer.wrap(data, 0, 10), false);
      assertNull(ws.ack);
      assertNull(s.take());
      session
          .onBinary(ws, ByteBuffer.wrap(data, 10, data.length - 10), true)
          .toCompletableFuture()
          .join();
      assertEquals(7, s.take().frame().seq());
      assertEquals(7, Protocol.JSON.readTree(ws.ack).get("ack").intValue());
      ws.ack = null;
      session.onBinary(ws, ByteBuffer.wrap(new byte[4]), true);
      assertTrue(ws.aborted);
      assertNull(ws.ack);
      assertNotNull(s.error);
    }
  }

  @Test
  void boundedHttpBodyCancelsOversize() {
    var body = new Source.LimitedBody(3);
    AtomicBoolean cancelled = new AtomicBoolean();
    body.onSubscribe(
        new Flow.Subscription() {
          public void request(long n) {}

          public void cancel() {
            cancelled.set(true);
          }
        });
    body.onNext(List.of(ByteBuffer.wrap(new byte[4])));
    assertTrue(cancelled.get());
    assertTrue(body.body.isCompletedExceptionally());
  }

  @Test
  void replayPreloadsOnceAndFlushesFinalMetadata() throws Exception {
    HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
    AtomicInteger preloads = new AtomicInteger();
    List<byte[]> batches = new CopyOnWriteArrayList<>();
    byte[] replay = replay();
    byte[] palette = Protocol.JSON.writeValueAsBytes(Collections.nCopies(256, List.of(0, 0, 0)));
    server.createContext(
        "/",
        exchange -> {
          byte[] response;
          switch (exchange.getRequestURI().getPath()) {
            case "/api/colormap" -> response = palette;
            case "/api/replay" -> {
              preloads.incrementAndGet();
              response = replay;
            }
            case "/api/metrics" -> {
              batches.add(exchange.getRequestBody().readAllBytes());
              response = "{}".getBytes();
            }
            default -> {
              exchange.sendResponseHeaders(404, -1);
              exchange.close();
              return;
            }
          }
          exchange.sendResponseHeaders(200, response.length);
          exchange.getResponseBody().write(response);
          exchange.close();
        });
    server.start();
    try (Source s = new Source("http://127.0.0.1:" + server.getAddress().getPort(), "replay")) {
      s.start();
      long deadline = System.nanoTime() + 3_000_000_000L;
      Source.Taken latest = null;
      while (System.nanoTime() < deadline) {
        var next = s.take();
        if (next != null) latest = next;
        if (latest != null && latest.frame().seq() >= 4) break;
        Thread.sleep(5);
      }
      assertNull(s.error);
      assertNotNull(latest);
      assertTrue(latest.frame().seq() >= 4);
      assertEquals(1, preloads.get());
      Metrics metrics =
          new Metrics(s, "test", Map.of("termination_reason", "duration", "active_seconds", 1.0));
      metrics.record(latest, 1, 0.25, 0.75);
      metrics.flush(false);
      metrics.close();
      assertEquals(2, batches.size());
      var last = Protocol.JSON.readTree(batches.get(1));
      assertEquals(0, last.get("samples").size());
      assertEquals("duration", last.path("metadata").path("termination_reason").asText());
      assertTrue(
          Protocol.JSON
              .readTree(batches.get(0))
              .path("samples")
              .get(0)
              .get("receive_age_ms")
              .isNull());
    } finally {
      server.stop(0);
    }
  }

  @Test
  void argumentValidation() {
    assertThrows(
        IllegalArgumentException.class, () -> Main.arguments(new String[] {"--duration", "NaN"}));
    assertThrows(
        IllegalArgumentException.class, () -> Main.arguments(new String[] {"--mode", "fast"}));
    assertThrows(IllegalArgumentException.class, () -> Main.arguments(new String[] {"--width"}));
  }
}
