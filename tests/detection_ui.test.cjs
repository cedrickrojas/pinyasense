const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function page() {
    const root = path.join(__dirname, '..');
    const html = fs.readFileSync(path.join(root, 'templates/index.html'), 'utf8');
    const markup = html.match(/<section[^>]*id="resultsSection"[^>]*>([\s\S]*?)<\/section>/)[1];
    const elements = {};
    const resultIds = [...markup.matchAll(/id="([^"]+)"/g)].map(match => match[1]);
    const element = () => ({ textContent: '', style: {}, appendChild() {}, scrollIntoView() {} });
    const section = element();
    let currentHtml;
    Object.defineProperty(section, 'innerHTML', {
        get: () => currentHtml,
        set(value) {
            currentHtml = value;
            resultIds.forEach(id => delete elements[id]);
            for (const [, id] of value.matchAll(/id="([^"]+)"/g)) elements[id] = element();
        }
    });
    elements.resultsSection = section;
    section.innerHTML = markup;
    const context = vm.createContext({
        document: { getElementById: id => elements[id] || null, addEventListener() {}, createElement: element,
            head: element(), body: element() },
        window: { addEventListener() {} }, console: { error() {}, warn() {} },
        fetch: async () => ({ ok: true, json: async () => ({ total_detections: 0, disease_count: {} }) }),
    });
    for (const name of ['html-utils.js', 'app.js']) {
        vm.runInContext(fs.readFileSync(path.join(root, 'static/js', name), 'utf8'), context);
    }
    return { context, elements, section };
}

test('single detection still renders after batch, video, and rejected-image results', () => {
    const { context, elements } = page();
    const result = { disease: 'Healthy', confidence: 0.8, method: 'test',
        frame_count: 2, disease_distribution: { Healthy: 2 } };
    for (const display of [
        () => context.displayBatchResults({ batch_count: 1, results: [result] }),
        () => context.displayVideoResults(result),
        () => context.displayResults({ not_pineapple: true, error: 'Rejected image' }),
    ]) {
        display();
        context.displayResults(result);
        assert.equal(elements.diseaseName.textContent, 'Healthy');
        assert.equal(elements.confidenceValue.textContent, '80%');
    }
});

test('untrusted text cannot become HTML in result and account views', () => {
    const { context, section } = page();
    const payload = '<img src=x onerror="alert(1)">';
    context.displayResults({ not_pineapple: true, error: payload });
    assert.ok(!section.innerHTML.includes(payload));
    assert.match(section.innerHTML, /&lt;img/);
    assert.equal(context.escapeHtml('"\'&<>'), '&quot;&#39;&amp;&lt;&gt;');
});

test('stats errors show unavailable, while a genuine empty result shows zero', async () => {
    const { context, elements } = page();
    for (const id of ['totalDetections', 'healthyCount', 'diseaseCount']) elements[id] = {};
    await context.loadStats();
    assert.equal(elements.totalDetections.textContent, 0);
    context.fetch = async () => ({ ok: false });
    await context.loadStats();
    assert.equal(elements.totalDetections.textContent, '\u2014');
});
