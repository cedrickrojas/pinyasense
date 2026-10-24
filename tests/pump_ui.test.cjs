const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../templates/water_pump.html'), 'utf8');
const script = Array.from(source.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g), m => m[1])
    .join('\n').replace(/\{\{[\s\S]*?\}\}/g, '300');

function page(fetch) {
    const elements = {};
    for (const [, id] of source.matchAll(/\bid="([^"]+)"/g)) {
        elements[id] = { textContent: '', style: {}, hidden: false, disabled: false,
            classList: { toggle() {} }, setAttribute(name, value) { this[name] = value; } };
    }
    const document = { getElementById: id => elements[id] || null,
        querySelector: () => null, addEventListener() {} };
    const api = new Function('document', 'window', 'fetch', script + '\nreturn {refreshStatus, setBusy, pumpOn, pumpOff};')(
        document, { addEventListener() {} }, fetch);
    return { ...api, elements };
}

function assertPumpState(p, state) {
    assert.equal(p.elements.btnOn.className, `btn ${state === 'on' ? 'btn-success' : 'btn-secondary'}`);
    assert.equal(p.elements.btnOff.className, `btn ${state === 'off' ? 'btn-danger' : 'btn-secondary'}`);
    assert.equal(p.elements.btnOn['aria-pressed'], String(state === 'on'));
    assert.equal(p.elements.btnOff['aria-pressed'], String(state === 'off'));
    assert.equal(p.elements.statusPill, undefined);
}

test('unreachable controller disables actions without a redirect notice', async () => {
    const p = page(async () => ({ ok: true, json: async () => ({
        hardware_available: false, status: 'unavailable', hardware_message: 'Pump controller unavailable.'
    }) }));
    await p.refreshStatus();
    p.setBusy(true);
    p.setBusy(false);
    assertPumpState(p, 'unavailable');
    assert(!source.includes('controllerNotice'));
    assert.equal(p.elements.errorBox.textContent, 'Pump controller unavailable.');
    for (const id of ['btnOn', 'btnOff', 'btnAutoOn', 'btnCreateSchedule']) {
        assert.equal(p.elements[id].disabled, true, id);
    }
    assert.equal(p.elements.btnAutoOff.disabled, false);
});

test('working Pi backend keeps real pump controls enabled', async () => {
    const p = page(async () => ({ ok: true, json: async () => ({
        hardware_available: true, status: 'off', gpio_pin: 27, breaker_on: true
    }) }));
    await p.refreshStatus();
    assertPumpState(p, 'off');
    assert.equal(p.elements.btnOn.disabled, false);
});

test('a failed status refresh disables previously available pump controls', async () => {
    let offline = false;
    const p = page(async () => {
        if (offline) throw new Error('Connection lost');
        return { ok: true, json: async () => ({ hardware_available: true, status: 'off' }) };
    });
    await p.refreshStatus();
    offline = true;
    await p.refreshStatus();
    assert.equal(p.elements.btnOn.disabled, true);
    assertPumpState(p, 'unavailable');
    assert.equal(p.elements.errorBox.textContent, 'Connection lost');
});

test('background polling does not lock the buttons or overlap a pending status request', async () => {
    let resolve, calls = 0;
    const p = page(() => {
        calls++;
        if (calls === 1) return Promise.resolve({ ok: true, json: async () => ({ hardware_available: true, status: 'off' }) });
        return new Promise(done => { resolve = done; });
    });
    await p.refreshStatus();
    const pending = p.refreshStatus(true);
    assert.equal(p.elements.btnOn.disabled, false);
    await p.refreshStatus(true);
    assert.equal(calls, 2);
    p.setBusy(true);
    resolve({ ok: true, json: async () => ({ hardware_available: true, status: 'off' }) });
    await pending;
    assert.equal(p.elements.btnOn.disabled, true, 'a background response must not release another operation');
});

test('ON and OFF display the confirmed command response without an extra status request', async () => {
    const calls = [];
    const p = page(async (url, options) => {
        calls.push([url, options.method]);
        return { ok: true, json: async () => ({ status: url.endsWith('/on') ? 'on' : 'off',
            gpio_pin: 27, breaker_on: true }) };
    });
    await p.pumpOn();
    assertPumpState(p, 'on');
    assert.equal(p.elements.btnOff.disabled, false);
    await p.pumpOff();
    assertPumpState(p, 'off');
    assert.deepEqual(calls, [['/api/water-pump/on', 'POST'], ['/api/water-pump/off', 'POST']]);
});

test('a delayed poll cannot overwrite a newer confirmed pump command', async () => {
    let resolvePoll, reads = 0;
    const p = page(async (url) => {
        if (url.endsWith('/status')) {
            if (++reads === 1) return { ok: true, json: async () => ({ status: 'off' }) };
            return new Promise(resolve => { resolvePoll = resolve; });
        }
        return { ok: true, json: async () => ({ status: 'on', gpio_pin: 27, breaker_on: true }) };
    });
    await p.refreshStatus();
    const pending = p.refreshStatus(true);
    await p.pumpOn();
    resolvePoll({ ok: true, json: async () => ({ status: 'off' }) });
    await pending;
    assertPumpState(p, 'on');
});

test('a rejected ON command never displays a successful pump state', async () => {
    const p = page(async (url) => url.endsWith('/status')
        ? { ok: true, json: async () => ({ status: 'off' }) }
        : { ok: false, json: async () => ({ error: 'Breaker is off' }) });
    await p.refreshStatus();
    await p.pumpOn();
    assertPumpState(p, 'off');
    assert.equal(p.elements.errorBox.textContent, 'Breaker is off');
});

