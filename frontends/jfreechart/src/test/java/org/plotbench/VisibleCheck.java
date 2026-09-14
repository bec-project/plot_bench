package org.plotbench;

import java.awt.image.BufferedImage;
import java.nio.file.*;
import java.util.*;
import javax.imageio.ImageIO;
import javax.swing.*;

/** Optional visible integration check against a running source, outside measurements. */
public final class VisibleCheck {
  public static void main(String[] args) throws Exception {
    if (args.length != 3) throw new IllegalArgumentException("URL MODE SNAPSHOT.png");
    Map<String, String> options =
        Main.arguments(new String[] {"--url", args[0], "--mode", args[1]});
    Map<String, Object> versions = Main.runtimeInfo();
    SwingUtilities.invokeAndWait(
        () -> {
          Main app = new Main(options, versions);
          String[] views = {"both", "waveform", "image", "both"};
          int[] step = {0};
          long start = System.nanoTime();
          javax.swing.Timer check = new javax.swing.Timer(1000, null);
          check.addActionListener(
              event -> {
                try {
                  if (app.source.error != null || System.nanoTime() - start > 30_000_000_000L)
                    throw new IllegalStateException("Visible check failed: " + app.source.error);
                  if (!app.view.equals(views[step[0]])
                      || app.source.pending
                      || app.metrics.count == 0) return;
                  int expected = app.view.equals("both") ? 2 : 1;
                  if (app.plotRow.getComponentCount() != expected)
                    throw new IllegalStateException("Wrong plot visibility");
                  System.out.println(
                      "Confirmed "
                          + args[1]
                          + " view="
                          + app.view
                          + " generation="
                          + app.source.current.generation());
                  if (step[0] == 3) {
                    // An application render snapshot, not an OS screen/presentation measurement.
                    var content = app.window.getContentPane();
                    BufferedImage snapshot =
                        new BufferedImage(
                            content.getWidth(), content.getHeight(), BufferedImage.TYPE_INT_RGB);
                    var graphics = snapshot.createGraphics();
                    content.printAll(graphics);
                    graphics.dispose();
                    Path dest = Path.of(args[2]);
                    Files.createDirectories(dest.toAbsolutePath().getParent());
                    ImageIO.write(snapshot, "png", dest.toFile());
                    check.stop();
                    app.finish("user");
                    return;
                  }
                  step[0]++;
                  String desired = views[step[0]];
                  app.one.setSelected(!desired.equals("image"));
                  app.two.setSelected(!desired.equals("waveform"));
                  app.requestView();
                } catch (Exception ex) {
                  ex.printStackTrace();
                  check.stop();
                  app.finish("error");
                }
              });
          check.start();
        });
  }
}
