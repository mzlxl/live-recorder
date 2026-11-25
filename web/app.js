// 前端逻辑：看板 / 任务 / 产物 三页管理
const $ = (s) => document.querySelector(s);

const INTERVALS = [5, 10, 15, 20, 30, 45, 60, 90, 120];
const allSelects = [];
const CHEVRON = '<svg class="ui-select-chevron" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 7.5 10 12.5 15 7.5"/></svg>';
const CHECK = '<svg class="option-check" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m3 8.5 3.2 3.2L13 5"/></svg>';
const ICONS = {
    scan: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M13.2 6.6A5.3 5.3 0 1 0 13 10"/><path d="M13.4 2.6v4h-4"/><circle cx="8" cy="8" r="1.6" fill="currentColor" stroke="none"/></svg>',
    play: '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M5 3.5v9l7-4.5z"/></svg>',
    edit: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 2.8 13.2 5 5.7 12.5H3.5v-2.2z"/><path d="m9.7 4.1 2.2 2.2"/></svg>',
    pause: '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><rect x="4" y="3" width="3" height="10" rx="1"/><rect x="9" y="3" width="3" height="10" rx="1"/></svg>',
    resume: '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M5 3.5v9l7-4.5z"/></svg>',
    stop: '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><rect x="4" y="4" width="8" height="8" rx="1.5"/></svg>',
    power: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><path d="M8 2v5"/><path d="M4.7 4.6a5 5 0 1 0 6.6 0"/></svg>',
    powerOff: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><path d="M8 2v5"/><path d="M4.7 4.6a5 5 0 1 0 6.6 0"/><path d="m3 13 10-10"/></svg>',
    trash: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 4.5h10M6.5 4.5V3h3v1.5M5 4.5l.6 8h4.8l.6-8M7 7v3.5M9 7v3.5"/></svg>',
    folder: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" aria-hidden="true"><path d="M2 4.5h4l1.3 1.6H14v6.4H2z"/></svg>',
    file: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 2h5l3 3v9H4z"/><path d="M9 2v3h3"/></svg>',
};

function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
function escapeJs(s) { return String(s ?? "").replace(/\\/g, "\\\\").replace(/'/g, "\\'"); }
function statusTag(status) {
    const map = { completed: ["done", "已完成"], failed: ["failed", "失败"], recording: ["recording", "录制中"] };
    const [tone, label] = map[status] || ["off", status || "未知"];
    return `<span class="tag ${tone}">${escapeHtml(label)}</span>`;
}
function pad2(n) { return String(n).padStart(2, "0"); }
function actionBtn(label, onclick, tone, icon) {
    return `<button class="btn sm ${tone || ""}" title="${escapeHtml(label)}" onclick="${onclick}">${icon ? ICONS[icon] : ""}<span>${label}</span></button>`;
}

// ---------- 统一下拉组件 ----------
function closeAllSelects() { allSelects.forEach(s => s.close()); }

function createSelect(root, options, value, opts = {}) {
    if (typeof root === "string") root = $(root);
    const placeholder = opts.placeholder || "请选择";
    root.classList.add("ui-select");
    root.innerHTML = `
        <button type="button" class="ui-select-trigger" aria-haspopup="listbox" aria-expanded="false">
            <span class="ui-select-value"></span>${CHEVRON}
        </button>
        <div class="ui-select-menu" role="listbox"></div>`;
    const trigger = root.querySelector(".ui-select-trigger");
    const menu = root.querySelector(".ui-select-menu");
    const labelEl = root.querySelector(".ui-select-value");
    const state = { options: [], value: "" };

    function normalize(list) {
        return list.map(o => typeof o === "object"
            ? { value: String(o.value ?? ""), label: String(o.label ?? "") }
            : { value: String(o), label: String(o) });
    }
    function renderMenu() {
        menu.innerHTML = state.options.length
            ? state.options.map(o => `<button type="button" class="ui-option ${o.value === state.value ? "selected" : ""}" role="option" data-value="${escapeHtml(o.value)}" data-label="${escapeHtml(o.label)}"><span>${escapeHtml(o.label)}</span>${o.value === state.value ? CHECK : ""}</button>`).join("")
            : '<div class="ui-option is-empty">暂无选项</div>';
    }
    function setValue(v, silent = false) {
        state.value = String(v ?? "");
        const current = state.options.find(o => o.value === state.value);
        labelEl.textContent = current ? current.label : placeholder;
        trigger.classList.toggle("is-placeholder", !current);
        renderMenu();
        if (!silent && typeof opts.onChange === "function") opts.onChange(state.value);
    }
    function setOptions(list, v, silent = true) {
        state.options = normalize(list);
        const next = v === undefined ? state.value : String(v ?? "");
        setValue(state.options.some(o => o.value === next) ? next : "", silent);
    }
    function close() {
        root.classList.remove("is-open");
        trigger.setAttribute("aria-expanded", "false");
    }
    function open() {
        closeAllSelects();
        root.classList.add("is-open");
        trigger.setAttribute("aria-expanded", "true");
        const active = menu.querySelector(".ui-option.selected");
        if (active) active.scrollIntoView({ block: "nearest" });
    }
    trigger.addEventListener("click", e => {
        e.stopPropagation();
        root.classList.contains("is-open") ? close() : open();
    });
    menu.addEventListener("click", e => {
        const item = e.target.closest(".ui-option[data-value]");
        if (!item) return;
        setValue(item.dataset.value);
        close();
    });
    document.addEventListener("click", e => { if (!root.contains(e.target)) close(); });
    document.addEventListener("keydown", e => { if (e.key === "Escape") close(); });

    const api = {
        root, open, close, setOptions, setValue,
        getValue: () => state.value,
        getLabel: () => (state.options.find(o => o.value === state.value) || {}).label || "",
    };
    root._uiSelect = api;
    allSelects.push(api);
    setOptions(options, value, true);
    return api;
}
function uiValue(selector) { const el = typeof selector === "string" ? $(selector) : selector; return el && el._uiSelect ? el._uiSelect.getValue() : ""; }
function uiSet(selector, value, silent) { const el = typeof selector === "string" ? $(selector) : selector; if (el && el._uiSelect) el._uiSelect.setValue(value, silent); }

function mountTimePicker(selector, initial = "") {
    const root = $(selector);
    root.classList.add("time-picker");
    root.innerHTML = '<div class="time-pair"><div class="time-part hour"></div><span class="time-colon">:</span><div class="time-part minute"></div></div>';
    const unlimited = { value: "", label: "不限" };
    const hours = [unlimited, ...Array.from({ length: 24 }, (_, i) => ({ value: pad2(i), label: pad2(i) }))];
    const minutes = [unlimited, ...Array.from({ length: 60 }, (_, i) => ({ value: pad2(i), label: pad2(i) }))];
    const [h = "", m = ""] = (initial || "").split(":");
    createSelect(root.querySelector(".hour"), hours, h, { placeholder: "时" });
    createSelect(root.querySelector(".minute"), minutes, m, { placeholder: "分" });
    return {
        read() {
            const hh = uiValue(root.querySelector(".hour"));
            const mm = uiValue(root.querySelector(".minute"));
            if (!hh && !mm) return { ok: true, value: "" };
            if (hh && mm) return { ok: true, value: `${hh}:${mm}` };
            return { ok: false, value: "" };
        },
        set(value) {
            const [vh = "", vm = ""] = (value || "").split(":");
            uiSet(root.querySelector(".hour"), vh, true);
            uiSet(root.querySelector(".minute"), vm, true);
        },
    };
}

// ---------- 工具 ----------
function fmtSize(b) { if (!b) return "-"; if (b < 1024) return b + "B"; if (b < 1048576) return (b / 1024).toFixed(1) + "KB"; return (b / 1048576).toFixed(1) + "MB"; }
function fmtDur(s) { if (!s) return "-"; const m = Math.floor(s / 60), r = s % 60; if (m < 60) return m + "m" + r + "s"; const h = Math.floor(m / 60); return h + "h" + (m % 60) + "m"; }
function today() { const d = new Date(); return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); }
function isToday(ts) { return (ts || "").startsWith(today()); }

let toastTimer = null;
function toast(msg, type) {
    const el = $("#toast");
    el.textContent = msg;
    el.className = "toast " + (type || "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.add("hidden"), 3000);
}

async function api(url, opt) {
    const r = await fetch(url, opt);
    if (!r.ok) {
        let msg = await r.text();
        try { const j = JSON.parse(msg); msg = j.detail || j.message || msg; } catch (e) { /* 保留原始响应 */ }
        throw new Error(msg);
    }
    return r.json();
}

// ---------- Tab 切换 ----------
function switchTab(name) {
    document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === name));
    document.querySelectorAll("main > section").forEach(s => s.classList.add("hidden"));
    $("#page-" + name).classList.remove("hidden");
    if (name === "dashboard") loadDashboard();
    if (name === "tasks") loadTasks();
    if (name === "recordings") loadRecordings();
}
document.querySelectorAll(".tab").forEach(t => t.onclick = () => switchTab(t.dataset.tab));

// ---------- 状态栏 ----------
async function loadStatus() {
    try {
        const s = await api("/api/status");
        const ready = s.recorder_device_ready;
        const label = s.capture_mode === "browser" ? "浏览器音频采集"
            : (s.capture_mode === "loopback" ? "系统音频回环" : "声卡");
        $("#status-bar").innerHTML = `<span class="dot ${ready ? 'ok' : 'bad'}" title="${escapeHtml(s.device_hint || "")}"></span> ${label}${ready ? '就绪' : '未就绪'}` +
            (s.running.length ? ` · <span style="color:#f87171">录制中 ${s.running.length}</span>` : "");
    } catch (e) { $("#status-bar").innerHTML = '<span class="dot bad"></span> 服务未连接'; }
}

// ---------- 看板 ----------
async function loadDashboard() {
    try {
        const d = await api("/api/dashboard");
        const cards = [
            { label: "任务总数", value: d.task_total, sub: `启用 ${d.task_enabled}` },
            { label: "今日产物", value: d.today_count, sub: fmtDur(d.today_duration), accent: true },
            { label: "累计产物", value: d.rec_total, sub: `成功 ${d.rec_completed} / 失败 ${d.rec_failed}` },
            { label: "累计时长", value: fmtDur(d.total_duration), sub: "" },
            { label: "累计大小", value: fmtSize(d.total_size), sub: "" },
        ];
        $("#stat-cards").innerHTML = cards.map(c =>
            `<div class="card ${c.accent ? 'accent' : ''}"><div class="label">${c.label}</div><div class="value">${c.value}</div><div class="sub">${c.sub || '&nbsp;'}</div></div>`
        ).join("");

        // 正在录制
        const run = d.running_tasks || [];
        $("#running-list").innerHTML = run.length
            ? run.map(t => {
                const controls = t.paused
                    ? actionBtn("恢复", `resumeTask(${t.id})`, "btn-resume", "resume") + actionBtn("停止", `stopTask(${t.id})`, "danger btn-stop", "stop")
                    : actionBtn("暂停", `pauseTask(${t.id})`, "btn-pause", "pause") + actionBtn("停止", `stopTask(${t.id})`, "danger btn-stop", "stop");
                return `<div class="running-item"><span class="pulse"></span><b>${escapeHtml(t.name)}</b>${t.paused ? '<span class="tag off">已暂停</span>' : '<span class="tag recording">录制中</span>'}<span class="tag off">${escapeHtml(t.platform)}</span><span>${escapeHtml(t.anchor_name || "")}</span><span class="running-actions">${controls}</span></div>`;
            }).join("")
            : '<div class="empty">当前无正在录制的任务</div>';

        // 今日产物
        const todayRecs = (d.recent || []).filter(r => isToday(r.start_time));
        $("#dash-recent").innerHTML = todayRecs.length
            ? todayRecs.map(recRow).join("")
            : '<tr><td colspan="6" class="empty">今日暂无产物</td></tr>';
    } catch (e) { toast("看板加载失败: " + e.message, "err"); }
}

function recRow(r) {
    return `<tr>
        <td><span class="task-ref">任务 #${r.task_id}</span></td>
        <td class="mono">${r.start_time || "-"}</td>
        <td class="mono">${fmtDur(r.duration)}</td>
        <td class="mono">${fmtSize(r.file_size)}</td>
        <td>${statusTag(r.status)}</td>
        <td><div class="row-actions">${recOps(r)}</div></td>
    </tr>`;
}

function recOps(r) {
    const btns = [];
    if (r.file_exists && r.file_url) {
        btns.push(actionBtn("试听", `playRec('${escapeJs(r.file_url)}')`, "ghost btn-listen", "play"));
        btns.push(actionBtn("打开", `openRec(${r.id})`, "btn-open", "file"));
        btns.push(actionBtn("进文件夹", `revealRec(${r.id})`, "btn-open", "folder"));
    } else if (r.id) {
        btns.push('<span class="file-missing" title="录制失败或文件已被删除">文件缺失</span>');
    }
    if (r.id) btns.push(actionBtn("删除", `delRec(${r.id})`, "danger btn-delete", "trash"));
    return btns.join("") || '<span class="muted">-</span>';
}

// 试听：用浮动 audio 播放
function playRec(url) {
    let a = $("#float-audio");
    if (!a) {
        a = document.createElement("audio");
        a.id = "float-audio"; a.controls = true; a.style.cssText = "position:fixed;bottom:16px;left:16px;z-index:300;width:320px;";
        document.body.appendChild(a);
    }
    a.src = url; a.play();
}

// ---------- 任务 ----------
let formFrequency = null;
let formCron = "";
let timePickers = {};

function minutesFromCron(cron, interval) {
    if (INTERVALS.includes(Number(interval))) return Number(interval);
    const c = (cron || "").trim();
    const step = c.match(/^\*\/(\d+)\s+\*\s+\*\s+\*\s+\*$/);
    if (step && INTERVALS.includes(Number(step[1]))) return Number(step[1]);
    if (/^0\s+\*\s+\*\s+\*\s+\*$/.test(c)) return 60;
    if (/^0\s+\*\/2\s+\*\s+\*\s+\*$/.test(c)) return 120;
    return null;
}
function cronFromMinutes(n) {
    if (n === 60) return "0 * * * *";
    if (n === 120) return "0 */2 * * *";
    return `*/${n} * * * *`;
}
function frequencyText(t) {
    const m = minutesFromCron(t.cron, t.interval_minutes);
    return m ? `<span class="freq-pill">每 ${m} 分钟</span>` : `<span class="muted mono" title="${escapeHtml(t.cron)}">自定义 cron</span>`;
}
function scanRangeText(t) {
    const s = t.scan_start || "", e = t.scan_end || "";
    if (!s && !e) return '<span class="muted">全天</span>';
    const cross = s && e && s > e;
    return `<span class="mono">${s || "不限"}</span><span class="range-arrow">→</span><span class="mono">${e || "不限"}</span>${cross ? '<span class="tag tiny next-day">次日</span>' : ""}`;
}

function initSelects() {
    createSelect("#f-platform", [], "", { placeholder: "选择平台" });
    createSelect("#f-frequency", [{ value: "", label: "请选择频率" }, ...INTERVALS.map(n => ({ value: String(n), label: `每 ${n} 分钟` }))], "10", { placeholder: "选择频率" });
    timePickers = { start: mountTimePicker("#f-scan-start"), end: mountTimePicker("#f-scan-end") };
    createSelect("#filter-task", [{ value: "", label: "全部任务" }], "", { placeholder: "全部任务", onChange: loadRecordings });
}

async function loadPlatforms() {
    const list = await api("/api/platforms");
    const options = list.map(p => ({ value: p.name, label: p.label }));
    const current = uiValue("#f-platform") || (options[0] || {}).value || "";
    $("#f-platform")._uiSelect.setOptions(options, current, true);
}

async function loadTasks() {
    const tasks = await api("/api/tasks");
    $("#task-tbody").innerHTML = tasks.length ? tasks.map(t => {
        const st = t.running
            ? (t.paused ? '<span class="tag off">已暂停</span>' : '<span class="tag recording">录制中</span>')
            : `<span class="tag ${t.enabled ? 'on' : 'off'}">${t.enabled ? '启用' : '停用'}</span>`;
        return `<tr>
            <td class="mono muted">${t.id}</td>
            <td><div class="cell-primary">${escapeHtml(t.name)}</div><div class="cell-sub">${escapeHtml(t.anchor_home)}</div></td>
            <td><span class="tag off">${escapeHtml(t.platform)}</span></td>
            <td>${escapeHtml(t.anchor_name || "-")}</td>
            <td>${frequencyText(t)}</td>
            <td>${scanRangeText(t)}</td>
            <td>${st}</td>
            <td><span class="count-badge">${t.recording_count}</span></td>
            <td><div class="row-actions">${taskOps(t)}</div></td>
        </tr>`;
    }).join("") : '<tr><td colspan="9" class="empty">暂无任务，点右上角「新增任务」</td></tr>';

    const options = [{ value: "", label: "全部任务" }, ...tasks.map(t => ({ value: String(t.id), label: t.name }))];
    $("#filter-task")._uiSelect.setOptions(options, uiValue("#filter-task"), true);
}

function taskOps(t) {
    if (t.running) {
        return t.paused
            ? actionBtn("恢复", `resumeTask(${t.id})`, "btn-resume", "resume") + actionBtn("停止", `stopTask(${t.id})`, "danger btn-stop", "stop")
            : actionBtn("暂停", `pauseTask(${t.id})`, "btn-pause", "pause") + actionBtn("停止", `stopTask(${t.id})`, "danger btn-stop", "stop");
    }
    return actionBtn("检查", `runTask(${t.id})`, "btn-check", "scan")
        + actionBtn("编辑", `editTask(${t.id})`, "btn-edit", "edit")
        + actionBtn(t.enabled ? "停用" : "启用", `toggleTask(${t.id}, ${t.enabled ? 0 : 1})`,
            t.enabled ? "btn-power btn-power-on" : "btn-power btn-power-off", t.enabled ? "powerOff" : "power")
        + actionBtn("删除", `delTask(${t.id}, ${t.recording_count})`, "danger btn-delete", "trash");
}

async function pauseTask(id) {
    try { await api(`/api/tasks/${id}/pause`, { method: "POST" }); loadTasks(); loadDashboard(); toast("已暂停", "ok"); }
    catch (e) { toast("暂停失败: " + e.message, "err"); }
}
async function resumeTask(id) {
    try { await api(`/api/tasks/${id}/resume`, { method: "POST" }); loadTasks(); loadDashboard(); toast("已恢复", "ok"); }
    catch (e) { toast("恢复失败: " + e.message, "err"); }
}
async function stopTask(id) {
    if (!confirm("确认停止当前录制？已录部分会保留。")) return;
    try {
        await api(`/api/tasks/${id}/stop`, { method: "POST" });
        toast("已请求停止，稍后结束", "ok");
        setTimeout(() => { loadTasks(); loadDashboard(); loadRecordings(); }, 4000);
    } catch (e) { toast("停止失败: " + e.message, "err"); }
}

function showForm() { $("#task-form").classList.remove("hidden"); }
function hideForm() { $("#task-form").classList.add("hidden"); $("#f-id").value = ""; }
function resetForm() {
    formFrequency = null;
    formCron = "";
    $("#f-id").value = "";
    $("#f-name").value = "";
    $("#f-home").value = "";
    $("#f-anchor").value = "";
    uiSet("#f-frequency", "10", true);
    const firstPlatform = $("#f-platform")._uiSelect?.root.querySelector(".ui-option[data-value]")?.dataset.value || "";
    uiSet("#f-platform", firstPlatform, true);
    timePickers.start.set("");
    timePickers.end.set("");
}

$("#btn-add").onclick = () => { resetForm(); showForm(); };

async function editTask(id) {
    const tasks = await api("/api/tasks");
    const t = tasks.find(x => x.id === id);
    if (!t) return;
    formFrequency = minutesFromCron(t.cron, t.interval_minutes);
    formCron = t.cron || "";
    $("#f-id").value = t.id;
    $("#f-name").value = t.name;
    uiSet("#f-platform", t.platform, true);
    $("#f-home").value = t.anchor_home;
    $("#f-anchor").value = t.anchor_name || "";
    uiSet("#f-frequency", formFrequency === null ? "" : String(formFrequency), true);
    timePickers.start.set(t.scan_start || "");
    timePickers.end.set(t.scan_end || "");
    showForm();
}

async function saveTask() {
    const id = $("#f-id").value;
    const start = timePickers.start.read();
    const end = timePickers.end.read();
    const minutes = Number(uiValue("#f-frequency"));
    if (!INTERVALS.includes(minutes)) { toast("请选择检查频率", "err"); return; }
    if (!start.ok || !end.ok) { toast("时分需同时选择，或起始/结束都选「不限」", "err"); return; }
    const body = {
        name: $("#f-name").value.trim(),
        platform: uiValue("#f-platform"),
        anchor_home: $("#f-home").value.trim(),
        anchor_name: $("#f-anchor").value.trim(),
        cron: minutes === formFrequency ? formCron : cronFromMinutes(minutes),
        interval_minutes: minutes,
        scan_start: start.value,
        scan_end: end.value,
    };
    if (!body.name || !body.anchor_home) { toast("任务名 / 主播主页为必填", "err"); return; }
    try {
        if (id) await api(`/api/tasks/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        else await api("/api/tasks", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        hideForm(); loadTasks(); toast("任务已保存", "ok");
    } catch (e) { toast("保存失败: " + e.message, "err"); }
}

async function delTask(id, recCount) {
    if (!confirm("确认删除该任务？")) return;
    let delFiles = false;
    if (recCount > 0) delFiles = confirm("该任务有 " + recCount + " 个产物，是否同时删除本地音频文件？\n（点「取消」仅删任务记录，保留文件）");
    try {
        await api(`/api/tasks/${id}?delete_files=${delFiles}`, { method: "DELETE" });
        loadTasks(); loadRecordings(); toast("任务已删除" + (delFiles ? "（含产物文件）" : ""), "ok");
    } catch (e) { toast("删除失败: " + e.message, "err"); }
}

async function toggleTask(id, enabled) {
    await api(`/api/tasks/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled: !!enabled }) });
    loadTasks();
}

async function runTask(id) {
    try {
        const j = await api(`/api/tasks/${id}/run`, { method: "POST" });
        toast(j.msg || "已触发检查", j.ok ? "ok" : "err");
        setTimeout(loadStatus, 3000);
        setTimeout(loadDashboard, 15000);
    } catch (e) { toast("触发失败: " + e.message, "err"); }
}

// ---------- 产物 ----------
async function loadRecordings() {
    const tid = uiValue("#filter-task");
    const list = await api(tid ? `/api/recordings?task_id=${tid}` : "/api/recordings");
    $("#recording-tbody").innerHTML = list.length ? list.map(r => `
        <tr>
            <td class="mono muted">${r.id}</td>
            <td><span class="task-ref">任务 #${r.task_id}</span></td>
            <td class="mono">${r.start_time || "-"}</td>
            <td class="mono">${r.end_time || "-"}</td>
            <td class="mono">${fmtDur(r.duration)}</td>
            <td class="mono">${fmtSize(r.file_size)}</td>
            <td>${statusTag(r.status)}</td>
            <td><div class="row-actions">${recOps(r)}</div></td>
        </tr>`).join("") : '<tr><td colspan="8" class="empty">暂无产物</td></tr>';
}

async function openRec(id) {
    try { await api(`/api/recordings/${id}/open`, { method: "POST" }); toast("已用默认应用打开", "ok"); }
    catch (e) { toast("打开失败: " + e.message, "err"); }
}
async function revealRec(id) {
    try { await api(`/api/recordings/${id}/reveal`, { method: "POST" }); toast("已在文件管理器显示", "ok"); }
    catch (e) { toast("失败: " + e.message, "err"); }
}
async function delRec(id) {
    if (!confirm("确认删除该产物？将同时删除本地音频文件，不可恢复。")) return;
    try { await api(`/api/recordings/${id}`, { method: "DELETE" }); loadRecordings(); loadDashboard(); toast("产物已删除", "ok"); }
    catch (e) { toast("删除失败: " + e.message, "err"); }
}
async function openFolder() {
    try { await api("/api/recordings/folder", { method: "POST" }); toast("已打开产物文件夹", "ok"); }
    catch (e) { toast("失败: " + e.message, "err"); }
}

// ---------- 初始化 ----------
initSelects();
loadStatus();
loadPlatforms();
loadDashboard();
setInterval(() => { loadStatus(); if (!$("#page-dashboard").classList.contains("hidden")) loadDashboard(); }, 15000);
