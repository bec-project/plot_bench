package org.plotbench;

import java.util.*;
import java.util.concurrent.*;

final class Metrics {
  final Source source;
  final String runId;
  final List<Map<String, Object>> samples = new ArrayList<>();
  final Map<String, Object> metadata = new HashMap<>();
  final ScheduledExecutorService worker =
      Executors.newSingleThreadScheduledExecutor(
          r -> {
            Thread t = new Thread(r, "plotbench-metrics");
            t.setDaemon(true);
            return t;
          });
  volatile String error;
  long lost, count, skipped;
  double lastUpdate;
  Double lastAge;

  Metrics(Source source, String runId, Map<String, Object> metadata) {
    this.source = source;
    this.runId = runId;
    this.metadata.putAll(metadata);
    worker.scheduleAtFixedRate(() -> flush(false), 1, 1, TimeUnit.SECONDS);
  }

  synchronized void set(Map<String, Object> values) {
    metadata.putAll(values);
  }

  synchronized void record(Source.Taken taken, double update, double conversion, double draw) {
    Protocol.Frame f = taken.frame();
    double now = System.currentTimeMillis();
    Double age = source.mode.equals("replay") ? null : now - f.emitted();
    Map<String, Object> sample = new HashMap<>();
    sample.put("seq", f.seq());
    sample.put("generation", f.generation());
    sample.put("client_time_ms", now);
    sample.put("update_ms", update);
    sample.put("conversion_ms", conversion);
    sample.put("draw_ms", draw);
    sample.put("receive_age_ms", age);
    sample.put("skipped", taken.skipped());
    if (samples.size() >= 4096) {
      lost++;
      error = "telemetry buffer overflow";
    } else samples.add(sample);
    count++;
    skipped += taken.skipped();
    lastUpdate = update;
    lastAge = age;
  }

  void flush(boolean last) {
    Map<String, Object> body = new HashMap<>();
    List<Map<String, Object>> batch;
    synchronized (this) {
      batch = new ArrayList<>(samples);
      samples.clear();
      Map<String, Object> meta = new HashMap<>(metadata);
      meta.put("telemetry_lost", lost);
      if (error != null) {
        meta.put("telemetry_error", error);
        if (last) meta.put("termination_reason", "error");
      }
      body.put("metadata", meta);
    }
    if (batch.isEmpty() && !last) return;
    body.put("samples", batch);
    body.put("frontend", "jfreechart");
    body.put("mode", source.mode);
    body.put("run_id", runId);
    try {
      source.post("/api/metrics", body);
    } catch (Exception ex) {
      synchronized (this) {
        lost += batch.size();
        error = ex.toString();
      }
      System.err.println("Metrics export failed: " + ex);
    }
  }

  void close() {
    worker.shutdown();
    try {
      if (!worker.awaitTermination(5, TimeUnit.SECONDS)) {
        worker.shutdownNow();
        error = "telemetry worker timeout";
      }
    } catch (InterruptedException ex) {
      Thread.currentThread().interrupt();
      error = ex.toString();
    }
    flush(true);
  }
}
