const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

test('soil zones and current average update on the timer without a Refresh click', async () => {
    const source = fs.readFileSync(path.join(__dirname, '../templates/soil_moisture.html'), 'utf8');
    const script = Array.from(source.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g), m => m[1]).join('\n');
    const elements = {};
    for (const [, id] of source.matchAll(/\bid="([^"]+)"/g)) {
        elements[id] = { innerHTML: '', textContent: '', getContext: () => ({}) };
    }
    const document = {
        getElementById: id => elements[id], querySelectorAll: () => [], addEventListener() {}
    };
    let onLoad, intervalCallback, intervalMs, tick = 0, zoneRequests = 0;
    const window = { addEventListener(event, callback) { if (event === 'load') onLoad = callback; } };
    const values = [[25.7, 54.7, 75.7, 56.7], [26.0, 54.9, 75.9, 56.9]];
    const fetch = async (url, options) => {
        if (url.endsWith('/arduino-zones')) {
            zoneRequests++;
            assert.equal(options.cache, 'no-store');
            return { json: async () => ({
                source: 'simulated',
                zones: values[tick].map((value, i) => ({
                    zone: i + 1, value, status: 'moist', state: 'MOIST', sensor_mode: 'estimated_percent'
                })),
                summary: { valid_zones: 4, dry_zones: 0, watering_recommended: false }
            }) };
        }
        const average = Number((values[tick].reduce((a, b) => a + b, 0) / 4).toFixed(1));
        return { json: async () => ({
            readings: [{ timestamp: '2026-10-23T19:37:00', value: average, sensor_mode: 'estimated_percent' }],
            statistics: { count: 1, average, min: average, max: average, alerts: 0, sensor_mode: 'estimated_percent' }
        }) };
    };
    class Chart { destroy() {} }
    new Function('document', 'window', 'fetch', 'Chart', 'setInterval', 'clearInterval', script)(
        document, window, fetch, Chart,
        (callback, milliseconds) => { intervalCallback = callback; intervalMs = milliseconds; return 1; },
        () => {}
    );
    onLoad();
    await new Promise(resolve => setImmediate(resolve));
    const before = elements.zoneGrid.innerHTML;
    assert.equal(elements.zoneSummary.textContent, '');
    assert.match(before, /25\.7% DRY/);
    assert.match(before, /54\.7% MOIST/);
    assert.match(before, /75\.7% WET/);
    assert.equal((before.match(/zone-card dry/g) || []).length, 1);
    assert.equal((before.match(/zone-card moist/g) || []).length, 2);
    assert.equal((before.match(/zone-card wet/g) || []).length, 1);
    assert.equal(intervalMs, 5000);
    tick = 1;
    intervalCallback();
    await new Promise(resolve => setImmediate(resolve));
    assert.notEqual(elements.zoneGrid.innerHTML, before);
    assert.match(elements.zoneGrid.innerHTML, /54\.9%/);
    assert.match(elements.currentReading.innerHTML, /53\.4/);
    assert.equal(zoneRequests, 2, 'grid and current average share one request per update');
});
