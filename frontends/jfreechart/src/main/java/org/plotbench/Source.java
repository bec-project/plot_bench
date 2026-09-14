package org.plotbench;

import java.io.*;
import java.net.URI;
import java.net.http.*;
import java.nio.ByteBuffer;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.locks.LockSupport;

/** Networking is off the EDT. One latest frame, one in-flight source packet. */
final class Source implements AutoCloseable {
  final URI base;
  final String mode;
  final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
  final AtomicReference<Protocol.Frame> latest = new AtomicReference<>();
  volatile String status = "Connecting", error, viewError;
  volatile boolean closed, pending, reload;
  volatile int epoch, replayCount, replayBytes;
  volatile int[] palette;
  volatile WebSocket socket;
  volatile long lastMessage;
  volatile Protocol.Config current;
  volatile String requestedView;
  long lastSeq, lastGeneration;
  int lastEpoch;
  boolean taken;
  Runnable wake = () -> {};
  final Thread worker;
  final ExecutorService controls =
      Executors.newSingleThreadExecutor(
          r -> {
            Thread t = new Thread(r, "plotbench-controls");
            t.setDaemon(true);
            return t;
          });

  Source(String url, String mode) {
    base = URI.create(url);
    if (!Set.of("http", "https").contains(base.getScheme()) || base.getHost() == null)
      throw new IllegalArgumentException("URL must be http(s)");
    this.mode = mode;
    worker = new Thread(this::run, "plotbench-source");
    worker.setDaemon(true);
  }

  URI endpoint(String path) {
    return base.resolve(path);
  }

  /** Bound the complete body and keep the request timeout active until EOF. */
  static final class LimitedBody implements HttpResponse.BodySubscriber<byte[]> {
    final CompletableFuture<byte[]> body = new CompletableFuture<>();
    final ByteArrayOutputStream bytes = new ByteArrayOutputStream();
    final int limit;
    Flow.Subscription subscription;

    LimitedBody(int limit) {
      this.limit = limit;
    }

    public CompletionStage<byte[]> getBody() {
      return body;
    }

    public void onSubscribe(Flow.Subscription s) {
      subscription = s;
      s.request(1);
    }

    public void onNext(List<ByteBuffer> buffers) {
      for (ByteBuffer buffer : buffers) {
        if ((long) bytes.size() + buffer.remaining() > limit) {
          subscription.cancel();
          body.completeExceptionally(new IOException("response exceeds bound"));
          return;
        }
        byte[] part = new byte[buffer.remaining()];
        buffer.get(part);
        bytes.writeBytes(part);
      }
      subscription.request(1);
    }

    public void onError(Throwable ex) {
      body.completeExceptionally(ex);
    }

    public void onComplete() {
      body.complete(bytes.toByteArray());
    }
  }

  byte[] get(String path, int limit) throws Exception {
    HttpRequest req =
        HttpRequest.newBuilder(endpoint(path)).timeout(Duration.ofSeconds(30)).GET().build();
    HttpResponse<byte[]> res = http.send(req, info -> new LimitedBody(limit));
    if (res.statusCode() != 200) throw new IOException("GET " + path + ": " + res.statusCode());
    return res.body();
  }

  void post(String path, Object object) throws Exception {
    HttpRequest req =
        HttpRequest.newBuilder(endpoint(path))
            .timeout(Duration.ofSeconds(3))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofByteArray(Protocol.JSON.writeValueAsBytes(object)))
            .build();
    HttpResponse<Void> res = http.send(req, HttpResponse.BodyHandlers.discarding());
    if (res.statusCode() >= 300) throw new IOException("POST " + path + ": " + res.statusCode());
  }

  void start() {
    worker.start();
  }

  void fail(Throwable ex) {
    if (!closed) {
      error = ex.toString();
      status = error;
      wake.run();
    }
  }

  void offer(Protocol.Frame f) {
    if (closed) return;
    latest.set(f);
    current = f.config();
    status = "Connected";
    if (pending && mode.equals("stream") && f.config().view().equals(requestedView))
      pending = false;
    wake.run();
  }

  record Taken(Protocol.Frame frame, long skipped) {}

  synchronized Taken take() {
    Protocol.Frame f = latest.getAndSet(null);
    if (f == null) return null;
    long skipped =
        taken && lastGeneration == f.generation() && lastEpoch == epoch && f.seq() > lastSeq
            ? f.seq() - lastSeq - 1
            : 0;
    lastSeq = f.seq();
    lastGeneration = f.generation();
    lastEpoch = epoch;
    taken = true;
    return new Taken(f, skipped);
  }

  void run() {
    try {
      palette = Protocol.palette(get("/api/colormap", 65536));
      if (mode.equals("replay")) replay();
      else stream();
    } catch (Exception ex) {
      fail(ex);
    }
  }

  void replay() throws Exception {
    while (!closed) {
      reload = false;
      byte[] bytes = get("/api/replay?count=16", Protocol.MAX_REPLAY);
      List<Protocol.Frame> frames = Protocol.replay(bytes);
      replayBytes = bytes.length;
      replayCount = frames.size();
      latest.set(null);
      synchronized (this) {
        taken = false;
      }
      pending = false;
      long start = System.nanoTime(), seq = 0;
      double period = 1e9 / frames.get(0).config().hz();
      while (!closed && !reload) {
        seq = Math.max(seq, (long) ((System.nanoTime() - start) / period));
        offer(frames.get((int) (seq % frames.size())).withSequence(seq));
        seq++;
        long due = start + (long) (seq * period);
        while (!closed && !reload && System.nanoTime() < due)
          LockSupport.parkNanos(Math.min(due - System.nanoTime(), 100_000_000));
      }
    }
  }

  void stream() throws Exception {
    URI ws = URI.create(endpoint("/ws").toString().replaceFirst("^http", "ws"));
    while (!closed && error == null) {
      Session listener = new Session();
      try {
        socket =
            http.newWebSocketBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .buildAsync(ws, listener)
                .get(6, TimeUnit.SECONDS);
        while (!closed && !listener.done.isDone()) {
          try {
            listener.done.get(1, TimeUnit.SECONDS);
          } catch (TimeoutException ex) {
            if (System.nanoTime() - lastMessage > 40_000_000_000L)
              throw new IOException("source idle timeout");
          }
        }
      } catch (Exception ex) {
        if (!closed && error == null) status = "Reconnecting: " + ex.getClass().getSimpleName();
      } finally {
        if (socket != null) socket.abort();
        socket = null;
      }
      if (!closed && error == null) {
        status = "Reconnecting";
        Thread.sleep(1000);
      }
    }
  }

  final class Session implements WebSocket.Listener {
    final ByteArrayOutputStream packet = new ByteArrayOutputStream();
    final CompletableFuture<Void> done = new CompletableFuture<>();

    @Override
    public void onOpen(WebSocket ws) {
      epoch++;
      latest.set(null);
      lastMessage = System.nanoTime();
      ws.request(1);
    }

    @Override
    public CompletionStage<?> onBinary(WebSocket ws, ByteBuffer data, boolean last) {
      try {
        lastMessage = System.nanoTime();
        if ((long) packet.size() + data.remaining() > Protocol.MAX_PACKET)
          throw Protocol.bad("packet exceeds limit");
        byte[] fragment = new byte[data.remaining()];
        data.get(fragment);
        packet.write(fragment);
        if (!last) {
          ws.request(1);
          return null;
        }
        Protocol.Frame f = Protocol.decode(packet.toByteArray());
        packet.reset();
        offer(f);
        // Request the next message only after ACK transmission; callback buffers remain bounded.
        return ws.sendText("{\"ack\":" + f.seq() + ",\"generation\":" + f.generation() + "}", true)
            .whenComplete(
                (sent, ex) -> {
                  if (ex != null) done.completeExceptionally(ex);
                  else ws.request(1);
                });
      } catch (Exception ex) {
        fail(ex);
        ws.abort();
        done.completeExceptionally(ex);
        return null;
      }
    }

    @Override
    public CompletionStage<?> onText(WebSocket ws, CharSequence text, boolean last) {
      IOException ex = new IOException("expected binary source frame");
      fail(ex);
      ws.abort();
      done.completeExceptionally(ex);
      return null;
    }

    @Override
    public CompletionStage<?> onPing(WebSocket ws, ByteBuffer data) {
      lastMessage = System.nanoTime();
      ws.request(1);
      return ws.sendPong(data);
    }

    @Override
    public CompletionStage<?> onPong(WebSocket ws, ByteBuffer data) {
      lastMessage = System.nanoTime();
      ws.request(1);
      return null;
    }

    @Override
    public CompletionStage<?> onClose(WebSocket ws, int code, String reason) {
      done.complete(null);
      return null;
    }

    @Override
    public void onError(WebSocket ws, Throwable ex) {
      done.completeExceptionally(ex);
    }
  }

  void requestView(String view) {
    if (pending || closed) return;
    pending = true;
    requestedView = view;
    viewError = null;
    controls.submit(
        () -> {
          try {
            post("/api/config", Map.of("view", view));
            if (mode.equals("replay")) {
              reload = true;
              LockSupport.unpark(worker);
            }
          } catch (Exception ex) {
            viewError = ex.toString();
            pending = false;
          }
        });
  }

  @Override
  public void close() {
    closed = true;
    if (socket != null) socket.abort();
    worker.interrupt();
    controls.shutdownNow();
    try {
      worker.join(1500);
    } catch (InterruptedException ex) {
      Thread.currentThread().interrupt();
    }
  }
}
