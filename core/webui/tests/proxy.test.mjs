import assert from 'node:assert/strict';
import { once } from 'node:events';
import { createServer as createHttpServer } from 'node:http';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { createServer, loadConfigFromFile } from 'vite';

test('the development proxy preserves Host and Origin for the editor', async (t) => {
  const backend = createHttpServer((request, response) => {
    response.setHeader('Content-Type', 'application/json');
    response.end(JSON.stringify({ host: request.headers.host, origin: request.headers.origin }));
  });
  let vite;
  t.after(async () => {
    await vite?.close();
    await new Promise((resolve) => backend.close(resolve));
  });
  backend.listen(0, '127.0.0.1');
  await once(backend, 'listening');

  // Load the actual config; replace only ports so the test uses free loopback
  // addresses and cannot contact a contributor's running editor.
  const { config } = await loadConfigFromFile(
    { command: 'serve', mode: 'development' },
    fileURLToPath(new URL('../vite.config.ts', import.meta.url))
  );
  const proxy = config.server.proxy['/api'];
  const target = `http://127.0.0.1:${backend.address().port}`;
  // Keep shorthand proxies as strings: Vite gives those different Host behavior.
  config.server.proxy['/api'] = typeof proxy === 'string' ? target : { ...proxy, target };
  vite = await createServer({
    ...config,
    configFile: false,
    root: fileURLToPath(new URL('..', import.meta.url)),
    logLevel: 'silent',
    server: { ...config.server, port: 0 },
  });
  await vite.listen();
  const origin = `http://127.0.0.1:${vite.httpServer.address().port}`;

  for (const requestOrigin of [origin, 'http://untrusted.invalid']) {
    const response = await fetch(`${origin}/api/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Origin: requestOrigin },
      body: '{}',
    });
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), {
      host: new URL(origin).host,
      // An unrelated origin must also survive unchanged so Python can reject it.
      origin: requestOrigin,
    });
  }
});
