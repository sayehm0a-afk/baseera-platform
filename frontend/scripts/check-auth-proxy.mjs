// Network contract test against a real Next server and a simulated upstream.
// This checks forwarding, not Safari's cookie policy or backend auth logic.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { setTimeout as delay } from 'node:timers/promises';

const upstream = createServer(async (req, res) => {
  let body = '';
  for await (const chunk of req) body += chunk;
  res.setHeader('Content-Type', 'application/json');
  if (req.url === '/api/v1/auth/login') {
    res.setHeader('Set-Cookie', [
      'access_token=fixture; Path=/; HttpOnly; Secure; SameSite=None',
      'refresh_token=fixture; Path=/api/v1/auth; HttpOnly; Secure; SameSite=None',
      'csrf_token=fixture; Path=/; Secure; SameSite=None',
    ]);
    res.setHeader('X-CSRF-Token', 'fixture');
  }
  if (req.url === '/api/v1/auth/refresh' && req.headers['x-csrf-token'] !== 'fixture') res.statusCode = 403;
  if (req.url === '/api/v1/auth/me' && !req.headers.cookie) res.statusCode = 401;
  res.end(JSON.stringify({ path: req.url, method: req.method, cookie: req.headers.cookie, csrf: req.headers['x-csrf-token'], body }));
});
upstream.listen(0, '127.0.0.1');
await once(upstream, 'listening');
const reserve = createServer().listen(0, '127.0.0.1');
await once(reserve, 'listening');
const port = reserve.address().port;
await new Promise(resolve => reserve.close(resolve));
const app = spawn(process.execPath, ['node_modules/next/dist/bin/next', 'dev', '--hostname', '127.0.0.1', '--port', String(port)], {
  env: { ...process.env, BACKEND_API_URL: `http://127.0.0.1:${upstream.address().port}`, NEXT_TELEMETRY_DISABLED: '1' },
  stdio: ['ignore', 'pipe', 'pipe'],
});
let output = '';
app.stdout.on('data', data => { output += data; });
app.stderr.on('data', data => { output += data; });
const request = (path, init) => fetch(`http://127.0.0.1:${port}${path}`, { ...init, signal: AbortSignal.timeout(15000) });
try {
  let ready = false;
  for (let i = 0; i < 120; i++) {
    if (app.exitCode !== null) throw new Error(output);
    try { if ((await request('/health/market-data')).ok) { ready = true; break; } } catch {}
    await delay(500);
  }
  assert.ok(ready, output);
  const login = await request('/api/v1/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"fixture":true}' });
  assert.equal(login.status, 200);
  const cookies = login.headers.getSetCookie();
  assert.equal(cookies.length, 3);
  assert.ok(cookies.some(cookie => cookie.includes('Path=/api/v1/auth') && cookie.includes('HttpOnly')));
  assert.ok(cookies.every(cookie => cookie.includes('Secure') && cookie.includes('SameSite=None') && !/Domain=/i.test(cookie)));
  assert.equal(login.headers.get('x-csrf-token'), 'fixture');
  assert.equal((await login.json()).body, '{"fixture":true}');
  const headers = { Cookie: 'access_token=fixture; refresh_token=fixture; csrf_token=fixture', 'X-CSRF-Token': 'fixture' };
  const refresh = await request('/api/v1/auth/refresh', { method: 'POST', headers });
  assert.equal(refresh.status, 200);
  const echoed = await refresh.json();
  assert.equal(echoed.cookie, headers.Cookie);
  assert.equal(echoed.csrf, 'fixture');
  assert.equal((await request('/api/v1/auth/refresh', { method: 'POST' })).status, 403);
  assert.equal((await request('/api/v1/auth/me')).status, 401);
  const query = await request('/api/v1/stocks?symbol=2030', { headers });
  assert.equal((await query.json()).path, '/api/v1/stocks?symbol=2030');
  console.log('PASS: real Next proxy preserves cookie attributes, CSRF, JSON body, query, and 401/403 statuses.');
} finally {
  app.kill('SIGTERM');
  await new Promise(resolve => upstream.close(resolve));
}
