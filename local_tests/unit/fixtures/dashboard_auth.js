// Exercise the real page's authentication lifecycle without a browser or a simulator.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[2], 'utf8');
const settle = () => new Promise(resolve => setImmediate(resolve));

function page(hash, cookieValid = false) {
  const elements = {}, requests = [], listeners = {};
  let validToken = 'current-token', interval;
  const element = id => elements[id] ||= {
    disabled: false, checked: false, textContent: '',
    addEventListener(type, callback) { listeners[`${id}:${type}`] = callback; },
  };
  const context = vm.createContext({
    URLSearchParams, console,
    location: {hash},
    document: {getElementById: element, addEventListener() {}},
    window: {addEventListener(type, callback) { listeners[type] = callback; }},
    setInterval(callback) { interval = callback; },
    async fetch(path, options) {
      requests.push(path);
      const token = options.headers['X-Operator-Token'];
      const authorized = token ? token === validToken : cookieValid;
      if (!authorized) return {ok: false, status: 401, json: async () => ({error: 'Missing or invalid operator token'})};
      if (path === '/api/session') {
        cookieValid = true;
        return {ok: true, status: 204, json: async () => { throw new SyntaxError('Empty response'); }};
      }
      return {ok: true, status: 200, json: async () => ({tasks: ['make_kong']})};
    },
  });
  // Rendering has its own tests. Observe the data delivered to it after authentication.
  vm.runInContext(source + '\nrender = () => { globalThis.loadedTasks = data.tasks; $("prepare").disabled = false; };', context);
  return {
    context, elements, requests,
    poll: () => interval(),
    follow: async hash => { context.location.hash = hash; await listeners.hashchange(); },
    restart: () => { validToken = 'new-token'; cookieValid = false; },
    retry: () => listeners['refresh:click'](),
  };
}

(async () => {
  for (const hash of ['', '#token=wrong-token']) {
    const p = page(hash);
    await settle();
    assert.deepEqual(p.requests, ['/api/session']);
    assert.match(p.elements.message.textContent, /complete URL.*#token/);
    assert.equal(p.elements.prepare.disabled, true);
    await p.poll();
    assert.equal(p.requests.length, 1, 'Unauthorized pages must stop polling');
    await p.follow('#token=current-token');
    assert.equal(p.context.loadedTasks[0], 'make_kong');
    assert.equal(p.elements.prepare.disabled, false);
    assert.equal(p.elements.message.textContent, '');
  }
  for (const [hash, cookie] of [['#token=current-token', false], ['', true]]) {
    const p = page(hash, cookie);
    await settle();
    assert.deepEqual(p.requests, ['/api/session', '/api/research/state?']);
    assert.equal(p.context.loadedTasks[0], 'make_kong');
    assert.equal(p.elements.message.textContent, '');
  }
  const p = page('#token=current-token');
  await settle();
  p.restart();
  await p.poll();
  assert.equal(p.elements.prepare.disabled, true);
  assert.match(p.elements.message.textContent, /restarting the server changes this link/);
  const count = p.requests.length;
  await p.poll();
  assert.equal(p.requests.length, count);
  await p.follow('#token=new-token');
  assert.equal(p.elements.prepare.disabled, false);
  assert.equal(p.elements.message.textContent, '');
  await p.retry();
  assert.equal(p.context.loadedTasks[0], 'make_kong');
  console.log('Dashboard authentication, cookies, token-link changes and restart recovery passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
