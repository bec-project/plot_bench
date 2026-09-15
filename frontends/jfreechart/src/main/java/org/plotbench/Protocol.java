package org.plotbench;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.*;

/** Strict protocol decoding. Array slices remain immutable and owned by the packet. */
final class Protocol {
  static final int MAX_REPLAY = 256 * 1024 * 1024;
  static final int MAX_PACKET = MAX_REPLAY + 65540;
  static final ObjectMapper JSON =
      new ObjectMapper().enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);

  record Config(
      double hz,
      int points,
      int appendCount,
      int curves,
      int waveformPlots,
      int width,
      int height,
      int imagePlots,
      String waveformMode,
      String imageMode,
      String view,
      long seed,
      long generation) {}

  record Frame(
      long seq, long generation, double emitted, Config config, Map<String, ByteBuffer> arrays) {
    Frame withSequence(long sequence) {
      return new Frame(sequence, generation, emitted, config, arrays);
    }
  }

  static long integer(JsonNode node, String key, long min, long max) {
    JsonNode v = node.get(key);
    if (v == null
        || !v.isIntegralNumber()
        || !v.canConvertToLong()
        || v.longValue() < min
        || v.longValue() > max) throw bad("invalid " + key);
    return v.longValue();
  }

  static double number(JsonNode node, String key) {
    JsonNode v = node.get(key);
    if (v == null || !v.isNumber() || !Double.isFinite(v.doubleValue()))
      throw bad("invalid " + key);
    return v.doubleValue();
  }

  static String choice(JsonNode node, String key, String... choices) {
    JsonNode v = node.get(key);
    if (v == null || !v.isTextual() || !Arrays.asList(choices).contains(v.textValue()))
      throw bad("invalid " + key);
    return v.textValue();
  }

  static IllegalArgumentException bad(String msg) {
    return new IllegalArgumentException(msg);
  }

  static Frame decode(byte[] data) {
    return decode(ByteBuffer.wrap(data));
  }

  static Frame decode(ByteBuffer input) {
    ByteBuffer data = input.slice().asReadOnlyBuffer().order(ByteOrder.LITTLE_ENDIAN);
    if (data.remaining() < 4 || data.remaining() > MAX_PACKET) throw bad("invalid packet length");
    int n = data.getInt();
    if (n < 1 || n > 65536 || ((4L + n + 3) & ~3L) > data.limit())
      throw bad("invalid header length");
    byte[] header = new byte[n];
    data.get(header);
    JsonNode h;
    try {
      h = JSON.readTree(header);
    } catch (IOException ex) {
      throw bad("invalid JSON header");
    }
    if (h == null || !h.isObject()) throw bad("invalid header");
    if (!h.path("version").isIntegralNumber()
        || !h.path("version").canConvertToInt()
        || h.path("version").intValue() != 2)
      throw bad("unsupported protocol version: " + h.path("version") + "; expected 2");
    long seq = integer(h, "seq", 0, Long.MAX_VALUE);
    long generation = integer(h, "generation", 0, Long.MAX_VALUE);
    double emitted = number(h, "emitted_at_ms");
    JsonNode c = h.path("config");
    double hz = number(c, "hz");
    if (hz <= 0 || hz > 120) throw bad("invalid hz");
    int points = (int) integer(c, "points", 1, 10_000_000);
    Config config =
        new Config(
            hz,
            points,
            (int) integer(c, "append_count", 1, points),
            (int) integer(c, "curves", 1, 64),
            (int) integer(c, "waveform_plots", 1, 16),
            (int) integer(c, "width", 1, 8192),
            (int) integer(c, "height", 1, 8192),
            (int) integer(c, "image_plots", 1, 16),
            choice(c, "waveform_mode", "append", "replace"),
            choice(c, "image_mode", "scalar", "rgb"),
            choice(c, "view", "both", "image", "waveform"),
            integer(c, "seed", 0, Long.MAX_VALUE),
            integer(c, "generation", 0, Long.MAX_VALUE));
    if (config.generation != generation) throw bad("generation mismatch");
    int payload = (4 + n + 3) & ~3;
    for (int i = 4 + n; i < payload; i++) if (data.get(i) != 0) throw bad("nonzero padding");
    JsonNode descriptors = h.path("arrays");
    if (!descriptors.isArray()) throw bad("missing arrays");
    Map<String, ByteBuffer> arrays = new HashMap<>();
    long offset = 0;
    for (JsonNode a : descriptors) {
      String name = choice(a, "name", "waveform", "image");
      if (arrays.containsKey(name)) throw bad("duplicate array");
      int[] shape;
      int item = 4;
      if (name.equals("waveform")) {
        if (config.view.equals("image")) throw bad("unexpected waveform");
        shape = new int[] {config.waveformPlots, config.curves, points};
      } else {
        if (config.view.equals("waveform")) throw bad("unexpected image");
        shape =
            config.imageMode.equals("rgb")
                ? new int[] {config.imagePlots, config.height, config.width, 3}
                : new int[] {config.imagePlots, config.height, config.width};
        if (config.imageMode.equals("rgb")) item = 1;
      }
      choice(a, "dtype", item == 1 ? "uint8" : "float32");
      if (!a.path("shape").isArray() || a.path("shape").size() != shape.length)
        throw bad("shape mismatch");
      long bytes = item;
      for (int i = 0; i < shape.length; i++) {
        JsonNode d = a.path("shape").get(i);
        if (!d.isIntegralNumber() || d.longValue() != shape[i]) throw bad("shape mismatch");
        bytes *= shape[i];
      }
      integer(a, "offset", offset, offset);
      integer(a, "nbytes", bytes, bytes);
      if (offset % item != 0 || bytes > data.limit() - payload - offset)
        throw bad("truncated array");
      arrays.put(
          name,
          data.slice(payload + (int) offset, (int) bytes)
              .asReadOnlyBuffer()
              .order(ByteOrder.LITTLE_ENDIAN));
      offset += bytes;
    }
    if (arrays.size() != (config.view.equals("both") ? 2 : 1)
        || offset != data.limit() - payload
        || offset > MAX_REPLAY) throw bad("missing arrays or trailing bytes");
    return new Frame(seq, generation, emitted, config, Collections.unmodifiableMap(arrays));
  }

  static List<Frame> replay(byte[] bytes) {
    if (bytes.length < 4 || bytes.length > MAX_REPLAY) throw bad("invalid replay size");
    ByteBuffer b = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN);
    int n = b.getInt();
    if (n < 2 || n > 256) throw bad("invalid replay count");
    List<Frame> frames = new ArrayList<>();
    for (int i = 0; i < n; i++) {
      if (b.remaining() < 4) throw bad("truncated replay length");
      int len = b.getInt();
      if (len < 0 || len > b.remaining()) throw bad("truncated replay frame");
      Frame f = decode(b.slice(b.position(), len));
      b.position(b.position() + len);
      if (i > 0 && (!f.config.equals(frames.get(0).config) || f.seq <= frames.get(i - 1).seq))
        throw bad("inconsistent replay");
      frames.add(f);
    }
    if (b.hasRemaining()) throw bad("trailing replay bytes");
    return List.copyOf(frames);
  }

  static int[] palette(byte[] bytes) throws IOException {
    JsonNode lut = JSON.readTree(bytes);
    if (lut == null || !lut.isArray() || lut.size() != 256) throw bad("invalid palette");
    int[] colors = new int[256];
    for (int i = 0; i < 256; i++) {
      JsonNode rgb = lut.get(i);
      if (!rgb.isArray() || rgb.size() != 3) throw bad("invalid palette entry");
      int color = 0xff000000;
      for (int j = 0; j < 3; j++) {
        JsonNode v = rgb.get(j);
        if (!v.isIntegralNumber() || !v.canConvertToInt() || v.intValue() < 0 || v.intValue() > 255)
          throw bad("invalid color");
        color |= v.intValue() << (16 - 8 * j);
      }
      colors[i] = color;
    }
    return colors;
  }
}
