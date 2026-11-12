// Main chart on the Parameters page: the selected tile's series over a time window, with a target
// band, min-max error bars, event markers, a scrub crosshair + tooltip, and an overview strip whose
// window can be dragged and resized. Plain Chart.js (pinned in base.html); plugins below are inline.
(function () {
    const DAY = 86400000;
    const SEAFOAM = '#4ecdc4', CORAL = '#ff6b9d', SAND = '#f7b267', PEARL = '#f0f4f8', WC = '#60a5fa';
    const esc = v => String(v ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    const num = v => (v === null || v === undefined) ? '' : String(+v);
    const toX = t => new Date(t).getTime();        // 'YYYY-MM-DDTHH:MM' parses as local time
    const $ = id => document.getElementById(id);

    const S = {
        aq: null, key: null, data: null, chart: null,
        days: 30, win: null, full: null, showBad: false, cross: null, pinned: false, token: 0,
    };

    // ---- formatting ----
    function fmtWhen(t, known) {
        const d = new Date(t);
        const date = d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
        return known === false ? `${date} · time unknown` : `${date} · ${t.slice(11, 16)}`;
    }
    function fmtShort(t, known) {
        const d = new Date(t).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
        return known === false ? d : `${d} ${t.slice(11, 16)}`;
    }
    function span(ms) {
        const h = ms / 3600000;
        if (h < 1) return `${Math.max(1, Math.round(ms / 60000))} min`;
        if (h < 48) return `${Math.round(h)} h`;
        return `${Math.round(h / 24)} d`;
    }
    function eventText(e) {
        const unit = e.unit === '%' ? '%' : (e.unit ? ' ' + e.unit : '');
        return e.value !== null && e.value !== undefined ? `${num(e.value)}${unit} ${e.label.toLowerCase()}` : e.label.toLowerCase();
    }
    const unitText = () => (S.data.unit && S.data.unit !== 'pH') ? S.data.unit : '';

    // ---- data in the window ----
    const isBad = p => p.quality === 'bad';
    const shown = p => S.showBad || !isBad(p);
    const inWin = x => x >= S.win[0] && x <= S.win[1];

    // y scale fits the ok readings (plus target band). Suspect and shown-bad points outside it are
    // pinned to the edge with a marker (clipPlugin) and keep their real value in the tooltip.
    // Only if the window has no ok reading at all does the scale fit whatever is shown.
    function yRange() {
        const vals = [], fallback = [];
        for (const p of S.data.points) {
            if (!shown(p) || !inWin(p.x)) continue;
            const into = p.quality === 'ok' ? vals : fallback;
            into.push(p.y);
            if (p.min !== null) into.push(p.min);
            if (p.max !== null) into.push(p.max);
        }
        if (!vals.length) vals.push(...fallback);
        if (S.data.step && S.data.points.length) {   // the setting in force at the left edge
            const before = S.data.points.filter(p => p.x < S.win[0]).pop();
            if (before) vals.push(before.y);
        }
        const tg = S.data.target;
        if (tg) for (const v of tg) if (v !== null) vals.push(v);
        if (!vals.length) return {};
        let lo = Math.min(...vals), hi = Math.max(...vals);
        const pad = (hi - lo) * 0.1 || Math.abs(hi) * 0.05 || 1;
        return { min: lo - pad, max: hi + pad };
    }

    // ---- inline plugins ----
    const bandPlugin = {
        id: 'targetBand',
        beforeDatasetsDraw(chart) {
            const tg = S.data && S.data.target;
            if (!tg) return;
            const { ctx, chartArea: a, scales: { y } } = chart;
            const top = tg[1] !== null ? y.getPixelForValue(tg[1]) : a.top;
            const bottom = tg[0] !== null ? y.getPixelForValue(tg[0]) : a.bottom;
            ctx.save();
            ctx.fillStyle = 'rgba(78, 205, 196, 0.12)';
            ctx.fillRect(a.left, Math.max(a.top, Math.min(top, bottom)), a.right - a.left,
                         Math.min(a.bottom, Math.max(top, bottom)) - Math.max(a.top, Math.min(top, bottom)));
            ctx.restore();
        }
    };
    const eventsPlugin = {
        id: 'eventMarkers',
        beforeDatasetsDraw(chart) {
            const { ctx, chartArea: a, scales: { x } } = chart;
            ctx.save();
            ctx.font = '10px Outfit, sans-serif';
            ctx.textAlign = 'center';
            for (const e of S.data.events) {
                const px = x.getPixelForValue(e.x);
                if (px < a.left || px > a.right) continue;
                const wc = e.type === 'water_change';
                ctx.strokeStyle = wc ? 'rgba(96, 165, 250, 0.8)' : 'rgba(240, 244, 248, 0.22)';
                ctx.setLineDash(wc ? [5, 4] : []);
                ctx.lineWidth = 1;
                ctx.beginPath(); ctx.moveTo(px, a.top + (wc ? 12 : 0)); ctx.lineTo(px, a.bottom); ctx.stroke();
                if (wc && e.value !== null) { ctx.fillStyle = WC; ctx.fillText(`${num(e.value)}%`, px, a.top + 8); }
            }
            ctx.restore();
        }
    };
    const errorBarsPlugin = {
        id: 'errorBars',
        afterDatasetsDraw(chart) {
            const { ctx, chartArea: a, scales: { x, y } } = chart;
            ctx.save();
            ctx.lineWidth = 1.5;
            for (const p of S.data.points) {
                if (p.min === null && p.max === null) continue;
                if (!shown(p) || !inWin(p.x)) continue;
                const px = x.getPixelForValue(p.x);
                const cl = v => Math.max(a.top, Math.min(a.bottom, y.getPixelForValue(v)));
                const y1 = cl(p.min ?? p.y), y2 = cl(p.max ?? p.y);
                ctx.strokeStyle = isBad(p) ? 'rgba(240, 244, 248, 0.35)' : 'rgba(78, 205, 196, 0.75)';
                ctx.beginPath();
                ctx.moveTo(px, y1); ctx.lineTo(px, y2);
                ctx.moveTo(px - 4, y1); ctx.lineTo(px + 4, y1);
                ctx.moveTo(px - 4, y2); ctx.lineTo(px + 4, y2);
                ctx.stroke();
            }
            ctx.restore();
        }
    };
    // clamp each plotted point into the y range; .real keeps the reading's value
    function clampToRange(r) {
        for (const ds of S.chart.data.datasets) for (const d of ds.data) {
            const v = d.real;
            d.clip = r.max !== undefined && v > r.max ? 'up' : r.min !== undefined && v < r.min ? 'down' : null;
            d.y = d.clip === 'up' ? r.max : d.clip === 'down' ? r.min : v;
        }
    }
    const clipPlugin = {
        id: 'clipMarkers',
        afterDatasetsDraw(chart) {
            const { ctx, chartArea: a, scales: { x } } = chart;
            ctx.save();
            for (const ds of chart.data.datasets) for (const d of ds.data) {
                if (!d.clip || d.synthetic) continue;
                const px = x.getPixelForValue(d.x);
                if (px < a.left || px > a.right) continue;
                const up = d.clip === 'up', edge = up ? a.top : a.bottom, s = up ? 1 : -1;
                ctx.fillStyle = d.quality === 'bad' ? 'rgba(240, 244, 248, 0.6)' : d.quality === 'suspect' ? SAND : SEAFOAM;
                ctx.beginPath();     // triangle pointing off the chart, its tip on the edge
                ctx.moveTo(px, edge + s); ctx.lineTo(px - 5, edge + s * 9); ctx.lineTo(px + 5, edge + s * 9); ctx.closePath();
                ctx.fill();
            }
            ctx.restore();
        }
    };
    const crossPlugin = {
        id: 'crosshair',
        afterDraw(chart) {
            const c = S.cross;
            if (!c) return;
            const { ctx, chartArea: a, scales: { x, y } } = chart;
            const px = x.getPixelForValue(c.item.x);
            if (px < a.left || px > a.right) return;
            ctx.save();
            ctx.strokeStyle = 'rgba(240, 244, 248, 0.6)';
            ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(px, a.top); ctx.lineTo(px, a.bottom); ctx.stroke();
            if (c.kind === 'point') {
                ctx.strokeStyle = PEARL; ctx.lineWidth = 2;
                const cy = Math.max(a.top, Math.min(a.bottom, y.getPixelForValue(c.item.y)));
                ctx.beginPath(); ctx.arc(px, cy, 7, 0, Math.PI * 2); ctx.stroke();
            }
            ctx.restore();
        }
    };

    // ---- chart ----
    function datasets() {
        const color = p => p.quality === 'suspect' ? SAND : SEAFOAM;
        const main = S.data.points.filter(p => !isBad(p)).map(p => ({ ...p, real: p.y }));
        if (S.data.step && main.length) main.push({ ...main[main.length - 1], x: Date.now(), synthetic: true });
        const sets = [{
            label: S.data.label, data: main, parsing: false, borderColor: SEAFOAM, borderWidth: 2,
            cubicInterpolationMode: 'monotone', stepped: S.data.step ? 'before' : false, spanGaps: true,
            backgroundColor: SEAFOAM,
            pointRadius: c => c.raw?.synthetic || c.raw?.clip ? 0 : 3.5,
            pointHoverRadius: c => c.raw?.synthetic || c.raw?.clip ? 0 : 3.5,
            pointBorderWidth: c => c.raw?.quality === 'suspect' ? 2 : 1,
            pointBackgroundColor: c => c.raw?.quality === 'suspect' ? 'rgba(10, 22, 40, 0.9)' : color(c.raw || {}),
            pointBorderColor: c => color(c.raw || {}),
        }];
        if (S.showBad) sets.push({
            label: 'bad', data: S.data.points.filter(isBad).map(p => ({ ...p, real: p.y })), parsing: false, showLine: false,
            pointStyle: 'crossRot', pointRadius: c => c.raw?.clip ? 0 : 5, pointBorderWidth: 2, borderColor: 'rgba(240, 244, 248, 0.45)',
        });
        return sets;
    }

    function build() {
        if (S.chart) S.chart.destroy();
        const grid = { color: 'rgba(240, 244, 248, 0.07)' }, tick = { color: 'rgba(240, 244, 248, 0.75)', font: { size: 11 } };
        S.chart = new Chart($('mc-canvas'), {
            type: 'line',
            data: { datasets: datasets() },
            options: {
                responsive: true, maintainAspectRatio: false, animation: false, events: [],
                layout: { padding: { top: 4, right: 6 } },
                plugins: { legend: { display: false }, tooltip: { enabled: false } },
                scales: {
                    x: { type: 'linear', min: S.win[0], max: S.win[1], grid, ticks: { ...tick, maxTicksLimit: 6, maxRotation: 0, includeBounds: false,
                         callback: v => new Date(v).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) } },
                    y: { ...yRange(), grid, ticks: { ...tick, maxTicksLimit: 6, includeBounds: false } }
                }
            },
            plugins: [bandPlugin, eventsPlugin, errorBarsPlugin, clipPlugin, crossPlugin]
        });
    }

    function applyWindow() {
        const c = S.chart;
        c.options.scales.x.min = S.win[0];
        c.options.scales.x.max = S.win[1];
        const r = yRange();
        Object.assign(c.options.scales.y, { min: undefined, max: undefined }, r);
        clampToRange(r);
        c.update('none');
        const any = S.data.points.some(p => shown(p) && inWin(p.x));
        $('mc-empty').hidden = any;
        $('mc-empty').textContent = S.data.points.length ? 'No readings in this range' : 'No data yet';
        if (S.cross && !inWin(S.cross.item.x)) clearCross();
        drawOverview();
    }

    // ---- range buttons and overview ----
    function setDays(days) {
        S.days = days;
        document.querySelectorAll('.mc-ranges button').forEach(b => b.classList.toggle('active', +b.dataset.days === days));
        const now = Date.now();
        const first = S.data.points.length ? S.data.points[0].x : now - 7 * DAY;
        S.full = [Math.min(first, now - (days || 7) * DAY), now];
        S.win = days ? [now - days * DAY, now] : [...S.full];
        applyWindow();
    }

    function drawOverview() {
        const cv = $('mc-ov-canvas'), box = $('mc-overview');
        const w = box.clientWidth, h = box.clientHeight, dpr = window.devicePixelRatio || 1;
        if (cv.width !== Math.round(w * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
        const ctx = cv.getContext('2d');
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, w, h);
        const [f0, f1] = S.full, X = x => (x - f0) / (f1 - f0) * w;
        for (const e of S.data.events) {
            if (e.type !== 'water_change') continue;
            ctx.fillStyle = 'rgba(96, 165, 250, 0.5)';
            ctx.fillRect(Math.round(X(e.x)), 0, 1, h);
        }
        const pts = S.data.points.filter(p => !isBad(p));
        if (pts.length) {
            const ys = pts.map(p => p.y), lo = Math.min(...ys), hi = Math.max(...ys), r = hi - lo || 1;
            const Y = v => h - 6 - (v - lo) / r * (h - 12);
            ctx.strokeStyle = 'rgba(78, 205, 196, 0.7)'; ctx.lineWidth = 1.5;
            ctx.beginPath();
            pts.forEach((p, i) => i ? ctx.lineTo(X(p.x), Y(p.y)) : ctx.moveTo(X(p.x), Y(p.y)));
            if (S.data.step) ctx.lineTo(w, Y(pts[pts.length - 1].y));
            ctx.stroke();
        }
        const win = $('ov-window');
        win.style.left = `${X(S.win[0])}px`;
        win.style.width = `${Math.max(6, X(S.win[1]) - X(S.win[0]))}px`;
    }

    function overviewDrag() {
        const box = $('mc-overview');
        let drag = null;
        box.addEventListener('pointerdown', e => {
            if (!S.data) return;
            const w = box.clientWidth, [f0, f1] = S.full, toT = px => f0 + px / w * (f1 - f0);
            const edge = e.target.dataset.edge;
            let mode = edge || (e.target.closest('#ov-window') ? 'move' : 'jump');
            if (mode === 'jump') {     // tap outside the window: centre it there, then drag it
                const half = (S.win[1] - S.win[0]) / 2, c = toT(e.offsetX);
                S.win = clampWin([c - half, c + half]);
                mode = 'move';
                touched();
            }
            drag = { mode, x0: e.clientX, win0: [...S.win], perPx: (f1 - f0) / w };
            box.setPointerCapture(e.pointerId);
            e.preventDefault();
        });
        box.addEventListener('pointermove', e => {
            if (!drag) return;
            const dt = (e.clientX - drag.x0) * drag.perPx, [a, b] = drag.win0, minW = Math.min(DAY, (S.full[1] - S.full[0]) / 4);
            if (drag.mode === 'move') S.win = clampWin([a + dt, b + dt]);
            else if (drag.mode === 'l') S.win = [Math.max(S.full[0], Math.min(a + dt, b - minW)), b];
            else S.win = [a, Math.min(S.full[1], Math.max(b + dt, a + minW))];
            touched();
        });
        const end = () => { drag = null; };
        box.addEventListener('pointerup', end);
        box.addEventListener('pointercancel', end);
    }
    function clampWin([a, b]) {
        const [f0, f1] = S.full, w = b - a;
        if (a < f0) return [f0, f0 + w];
        if (b > f1) return [f1 - w, f1];
        return [a, b];
    }
    function touched() {        // custom window: no range button is active any more
        S.days = null;
        document.querySelectorAll('.mc-ranges button').forEach(b => b.classList.remove('active'));
        applyWindow();
    }

    // ---- scrubbing ----
    function candidates() {
        const items = [];
        for (const p of S.data.points) if (shown(p) && inWin(p.x)) items.push({ kind: 'point', item: p });
        for (const e of S.data.events) if (inWin(e.x)) items.push({ kind: 'event', item: e });
        return items;
    }
    function scrubAt(offsetX) {
        const c = S.chart;
        if (!c || !S.data) return;
        const x = c.scales.x, a = c.chartArea;
        const px = Math.max(a.left, Math.min(a.right, offsetX));
        let best = null, bestD = Infinity;
        for (const cand of candidates()) {
            // readings win ties with events at the same spot
            const d = Math.abs(x.getPixelForValue(cand.item.x) - px) + (cand.kind === 'event' ? 0.5 : 0);
            if (d < bestD) { best = cand; bestD = d; }
        }
        if (!best) return clearCross();
        if (!S.cross || S.cross.item !== best.item) {
            S.cross = best;
            c.draw();
            showTip(best, x.getPixelForValue(best.item.x));
        }
    }
    function clearCross() {
        if (!S.cross) return;
        S.cross = null;
        $('mc-tip').hidden = true;
        S.chart && S.chart.draw();
    }
    function precedingEvent(x) {
        let ev = null;
        for (const e of S.data.events) if (e.x <= x && e.type !== 'co2_bubble_rate') ev = e;
        return ev;
    }
    function tipHtml(c) {
        const u = unitText();
        if (c.kind === 'event') {
            const e = c.item;
            return `<div class="tt-when">${esc(fmtWhen(e.t, e.time_known))}</div>
                <div class="tt-val">${esc(eventText(e).replace(/^./, ch => ch.toUpperCase()))}</div>
                ${e.notes ? `<div class="tt-meta">${esc(e.notes)}</div>` : ''}`;
        }
        const p = c.item;
        const range = (p.min !== null || p.max !== null) ? ` <small>(${num(p.min)}–${num(p.max)})</small>` : '';
        const badge = p.quality !== 'ok' ? ` <span class="badge badge-${esc(p.quality)}">${esc(p.quality)}</span>` : '';
        let html = `<div class="tt-when">${esc(fmtWhen(p.t, p.time_known))}</div>
            <div class="tt-val">${num(p.y)}${range}${u ? ` <small>${esc(u)}</small>` : ''}${badge}</div>`;
        if (p.pair) html += `<div class="tt-meta">degassed ${num(p.pair.degassed.y)} · ${esc(fmtShort(p.pair.degassed.t, p.pair.degassed.time_known))}<br>
            in tank ${num(p.pair.tank.y)} · ${esc(fmtShort(p.pair.tank.t, p.pair.tank.time_known))}</div>`;
        if (p.method) html += `<div class="tt-meta">${esc(p.method)}</div>`;
        if (p.notes) html += `<div class="tt-meta">“${esc(p.notes)}”</div>`;
        const ev = precedingEvent(p.x);
        if (ev) html += `<div class="tt-event">${p.x - ev.x < 60000 ? 'at' : esc(span(p.x - ev.x)) + ' after'} ${esc(eventText(ev))}</div>`;
        return html;
    }
    function showTip(c, px) {
        const tip = $('mc-tip'), box = $('mc-box');
        tip.innerHTML = tipHtml(c);
        tip.hidden = false;
        const w = tip.offsetWidth, bw = box.clientWidth;
        tip.style.left = `${px + 14 + w > bw ? Math.max(0, px - 14 - w) : px + 14}px`;
    }
    function scrubEvents() {
        const box = $('mc-box');
        let touching = false;
        box.addEventListener('pointerdown', e => {
            if (e.pointerType !== 'mouse') { touching = true; scrubAt(e.offsetX); }
        });
        box.addEventListener('pointermove', e => {
            if (e.pointerType === 'mouse' || touching) scrubAt(e.offsetX);
        });
        box.addEventListener('pointerup', () => { touching = false; });          // touch: tooltip stays until tapped away
        box.addEventListener('pointercancel', () => { touching = false; });       // vertical drag became a page scroll
        box.addEventListener('pointerleave', e => { if (e.pointerType === 'mouse') clearCross(); });
        document.addEventListener('pointerdown', e => { if (!box.contains(e.target)) clearCross(); });
    }

    // ---- public ----
    async function show(key, { scroll = false } = {}) {
        if (!key) return;
        S.key = key;
        const token = ++S.token;
        if (scroll) $('main-chart').scrollIntoView({ behavior: 'smooth', block: 'start' });
        let data;
        try {
            const r = await fetch(`/api/aquarium/${S.aq}/series?key=${encodeURIComponent(key)}`);
            data = await r.json();
            if (!r.ok) throw new Error(data.error);
        } catch (e) {
            $('mc-empty').hidden = false; $('mc-empty').textContent = 'Failed to load chart data';
            return;
        }
        if (token !== S.token) return;   // a newer tile was picked meanwhile
        data.points.forEach(p => { p.x = toX(p.t); });
        data.events.forEach(e => { e.x = toX(e.t); });
        S.data = data;
        S.cross = null; $('mc-tip').hidden = true;
        $('mc-title').innerHTML = `${esc(data.label)}${unitText() ? `<span class="mc-unit">${esc(unitText())}</span>` : ''}`;
        const days = S.days === null ? 30 : S.days;
        S.win = [0, 1];
        build();
        setDays(days);
    }

    function init(aquariumId) {
        S.aq = aquariumId;
        document.querySelectorAll('.mc-ranges button').forEach(b => b.addEventListener('click', () => S.data && setDays(+b.dataset.days)));
        $('mc-bad').addEventListener('change', e => {
            S.showBad = e.target.checked;
            if (!S.data) return;
            S.chart.data.datasets = datasets();
            applyWindow();
        });
        scrubEvents();
        overviewDrag();
        new ResizeObserver(() => S.data && drawOverview()).observe($('mc-overview'));
    }

    window.MainChart = { init, show, _state: S, _scrubAt: scrubAt };
})();
