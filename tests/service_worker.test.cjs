const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function worker(ok = true) {
    const handlers = {};
    let writes = 0;
    const context = {
        URL,
        self: { location: { origin: 'https://example.test' },
            addEventListener: (name, handler) => { handlers[name] = handler; } },
        fetch: async () => ({ ok, clone: () => ({}) }),
        caches: { open: async () => ({ put: async () => { writes++; } }) },
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../static/sw.js'), 'utf8'), context);
    return { handlers, writes: () => writes };
}

test('private media and API requests bypass the offline cache', () => {
    const { handlers } = worker();
    for (const pathname of ['/uploads/private.jpg', '/api/history']) {
        let intercepted = false;
        handlers.fetch({ request: { method: 'GET', url: 'https://example.test' + pathname },
            respondWith() { intercepted = true; } });
        assert.equal(intercepted, false);
    }
});

test('failed static requests are not stored in the cache', async () => {
    const instance = worker(false);
    let response;
    instance.handlers.fetch({ request: { method: 'GET', url: 'https://example.test/static/js/app.js' },
        respondWith(promise) { response = promise; } });
    await response;
    assert.equal(instance.writes(), 0);
});
