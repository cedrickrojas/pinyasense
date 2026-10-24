const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../templates/forecast.html'), 'utf8');
const script = Array.from(source.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g), m => m[1])
    .join('\n').replace(/\{\{[\s\S]*?\}\}/g, '[]');

function predictions(height = 45) {
    return { predictions: {
        profile_used: 'standard', current_month: 6, days_after_planting: 180,
        harvest_month: 18, today_x: 6, model: {}, notes: [],
        months: [1, 6, 18].map(month => ({
            month, date: '2026-10-23', days_after_planting: month * 30,
            phase: month < 6 ? 'past' : 'future', growth_stage: 'Vegetative Stage',
            height_cm: height, height_cm_range: [height - 4, height + 4], confidence: 0.7
        })),
        actual_series: { height_cm: [{ x: 5, value: 40, logged_at: '2026-09-23' }] }
    } };
}

function page(fetch, chartFails = false) {
    const elements = {};
    for (const [, id] of source.matchAll(/\bid="([^"]+)"/g)) {
        elements[id] = {
            value: '', textContent: '', innerHTML: '', hidden: false, style: {},
            setAttribute(name, value) { this[name] = value; },
            getContext() { return {}; }, querySelectorAll() { return []; }
        };
    }
    for (const [id, value] of Object.entries({ plantCode: 'PLOT-A1', plantingDate: '2026-04-01',
        profile: 'standard', cycleDays: '540', horizonDays: '30', historyDays: '90' })) {
        elements[id].value = value;
    }
    const document = {
        getElementById: id => elements[id] || null, addEventListener() {},
        querySelector: () => ({ textContent: 'Standard' }), querySelectorAll: () => []
    };
    const configs = [];
    class Chart {
        constructor(ctx, config) {
            if (chartFails) throw new Error('Chart unavailable');
            configs.push(config);
        }
        destroy() {}
    }
    const api = new Function('document', 'window', 'fetch', 'Chart',
        script + '\nreturn {loadPredictions, loadCurrentStatus, apiRequest, renderCharts};'
    )(document, { addEventListener() {} }, fetch, Chart);
    return { ...api, elements, configs };
}

const response = data => ({ ok: true, json: async () => data });

test('monthly predictions render the chart, actual measurements and table', async () => {
    const p = page(async () => response(predictions()));
    await p.loadPredictions();
    assert.match(p.elements.predictionTableBody.innerHTML, /Month 18/);
    assert.doesNotMatch(p.elements.predictionTableBody.innerHTML, /Loading predictions/);
    assert.equal(p.elements.predictionTableBody['aria-busy'], 'false');
    assert.equal(p.elements.growthChart.hidden, false);
    assert.equal(p.configs.length, 1);
    assert(p.configs[0].data.datasets.some(d => d.label.includes('Actual') && d.data.length === 1));
});

test('a failed initial request clears both loading placeholders', async () => {
    const p = page(async () => { throw new TypeError('offline'); });
    await p.loadPredictions();
    assert.match(p.elements.predictionTableBody.innerHTML, /could not be loaded/);
    assert.match(p.elements.growthChartEmpty.textContent, /could not be loaded/);
    assert.equal(p.elements.predictionMessage.hidden, false);
    assert.equal(p.elements.predictionTableBody['aria-busy'], 'false');
});

test('chart failure still leaves monthly records in the table', async () => {
    const p = page(async () => response(predictions()), true);
    await p.loadPredictions();
    assert.match(p.elements.predictionTableBody.innerHTML, /Month 18/);
    assert.match(p.elements.predictionMessage.textContent, /Chart unavailable/);
});

test('a late response from the previous plot cannot replace the selected plot', async () => {
    let release;
    const p = page(url => url.includes('plant_code=PLOT-A1')
        ? new Promise(resolve => { release = resolve; })
        : Promise.resolve(response(predictions(72))));
    const oldRequest = p.loadPredictions();
    p.elements.plantCode.value = 'PLOT-B1';
    await p.loadPredictions();
    release(response(predictions(11)));
    await oldRequest;
    assert.match(p.elements.predictionTableBody.innerHTML, /72\.0/);
    assert.doesNotMatch(p.elements.predictionTableBody.innerHTML, /11\.0/);
    assert.equal(p.configs.length, 1);
});

test('a failed status refresh preserves the records already displayed', async () => {
    let offline = false;
    const log = { logged_at: '2026-10-23T18:45:00', growth_stage: 'Pre-Flowering Stage',
        plant_condition: 'Healthy', height_cm: 45, days_after_planting: 200 };
    const p = page(async () => {
        if (offline) throw new TypeError('offline');
        return response({ latest: log, history: [log], total: 7 });
    });
    await p.loadCurrentStatus();
    const history = p.elements.statusHistoryBody.innerHTML;
    const latest = p.elements.latestStatus.innerHTML;
    offline = true;
    await p.loadCurrentStatus();
    assert.equal(p.elements.statusHistoryBody.innerHTML, history);
    assert.equal(p.elements.latestStatus.innerHTML, latest);
    assert.equal(p.elements.statusCount.textContent, 7);
    assert.match(p.elements.storageBanner.textContent, /Could not refresh/);
});

test('unresponsive requests time out with a recovery message', async () => {
    const p = page((url, options) => new Promise((resolve, reject) => {
        options.signal.addEventListener('abort', () => reject(new Error('aborted')));
    }));
    await assert.rejects(p.apiRequest('/test', { timeoutMs: 5 }), /timed out.*not been deleted/);
});

test('daily score chart uses the modeled scenario and explains its inputs', () => {
    const p = page(async () => response({}));
    const days = [
        { date: '2026-10-24', soil_moisture_percent: 72, growth_score: 82,
            temperature_c: null, humidity_percent: null, event: 'Simulated drying / drainage' },
        { date: '2026-10-25', soil_moisture_percent: 65, growth_score: 92.5,
            temperature_c: 28, humidity_percent: 70, event: 'Simulated rain' }
    ];
    p.renderCharts(days.map(day => ({ ...day, growth_score: 70 })), { daily: days }, { daily: days });
    const score = p.configs[1];
    assert.deepEqual(score.data.labels, days.map(day => day.date));
    assert.deepEqual(score.data.datasets[0].data, [82, 92.5]);
    assert.match(score.data.datasets[0].label, /Modeled/);
    const tooltip = score.options.plugins.tooltip.callbacks.afterLabel;
    assert.deepEqual(tooltip({ dataIndex: 0 }), [
        'Environmental suitability estimate; not measured growth.',
        'Soil proxy: 72.0%', 'Simulated drying / drainage'
    ]);
    assert(tooltip({ dataIndex: 1 }).some(text => /Temperature trend: 28.0/.test(text)));
    assert.equal(score.options.scales.y.max, 100);
});

test('older API responses keep the sensor trend visible without inventing scores', () => {
    const p = page(async () => response({}));
    p.renderCharts([{ date: '2026-10-24', growth_score: null }], { daily: [] });
    const score = p.configs[1];
    assert.deepEqual(score.data.datasets[0].data, [null]);
    assert.match(score.data.datasets[0].label, /Sensor Trend/);
});
