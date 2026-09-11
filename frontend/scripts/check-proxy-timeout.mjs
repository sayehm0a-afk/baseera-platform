// Regression test for next.config.ts's experimental.proxyTimeout: proves
// a same-origin proxied request that legitimately takes longer than
// http-proxy's zero-config 30s default (see the comment on
// experimental.proxyTimeout in next.config.ts) still succeeds through
// THIS REPO'S ACTUAL, unmodified next.config.ts -- not a hardcoded
// assumption about its value. If a future edit removes or lowers
// proxyTimeout below this script's delay, this fails with the exact
// "HTTP 500 Internal Server Error at ~30s" symptom that motivated
// setting it in the first place (see docs/governance/
// ADR-safari-session-recovery.md).
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { setTimeout as delay } from 'node:timers/promises';

const DELAY_SECONDS = 33; // just past http-proxy's zero-config 30s default

const upstream = createServer(async (req, res) => {
  if (req.url === '/health/market-data') {
    res.statusCode = 200;
    res.end('ok');
    return;
  }
  if (req.url === '/api/v1/slow-analysis') {
    await delay(DELAY_SECONDS * 1000);
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify({ status: 'analysis complete' }));
    return;
  }
  res.statusCode = 404;
  res.end('not found');
});
upstream.listen(0, '127.0.0.1');
await once(upstream, 'listening');

const reserve = createServer().listen(0, '127.0.0.1');
await once(reserve, 'listening');
const port = reserve.address().port;
await new Promise((resolve) => reserve.close(resolve));

const app = spawn(process.execPath, ['node_modules/next/dist/bin/next', 'dev', '--hostname', '127.0.0.1', '--port', String(port)], {
  env: { ...process.env, BACKEND_API_URL: `http://127.0.0.1:${upstream.address().port}`, NEXT_TELEMETRY_DISABLED: '1' },
  stdio: ['ignore', 'pipe', 'pipe'],
});
let output = '';
app.stdout.on('data', (d) => { output += d; });
app.stderr.on('data', (d) => { output += d; });

try {
  let ready = false;
  for (let i = 0; i < 120; i++) {
    if (app.exitCode !== null) throw new Error(output);
    try {
      if ((await fetch(`http://127.0.0.1:${port}/health/market-data`)).ok) { ready = true; break; }
    } catch {}
    await delay(500);
  }
  assert.ok(ready, output);

  const start = Date.now();
  const response = await fetch(`http://127.0.0.1:${port}/api/v1/slow-analysis`, {
    signal: AbortSignal.timeout((DELAY_SECONDS + 20) * 1000),
  });
  const elapsedSeconds = (Date.now() - start) / 1000;
  assert.equal(response.status, 200, `expected the ${DELAY_SECONDS}s-delayed backend response to succeed through the proxy, got HTTP ${response.status} after ${elapsedSeconds.toFixed(1)}s -- experimental.proxyTimeout in next.config.ts may be missing, unset, or too low`);
  assert.ok(elapsedSeconds >= DELAY_SECONDS, `response returned suspiciously early (${elapsedSeconds.toFixed(1)}s) -- the backend delay may not have been reached`);
  console.log(`PASS: a ${DELAY_SECONDS}s-delayed backend response succeeded through the proxy in ${elapsedSeconds.toFixed(1)}s (past http-proxy's zero-config 30s default).`);
} finally {
  app.kill('SIGTERM');
  await new Promise((resolve) => upstream.close(resolve));
}
