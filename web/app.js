// 前端逻辑：看板 / 任务 / 产物 三页管理
const $ = (s) => document.querySelector(s);

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
    if (!r.ok) throw new Error(await r.text());
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
        $("#status-bar").innerHTML = `<span class="dot ${ready ? 'ok' : 'bad'}"></span> 声卡${ready ? '就绪' : '未就绪'}` +
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
            ? run.map(t => `<div class="running-item"><span class="pulse"></span><b>${t.name}</b><span class="tag off">${t.platform}</span><span>${t.anchor_name || ''}</span></div>`).join("")
            : '<div class="empty">当前无正在录制的任务</div>';

        // 今日产物
        const todayRecs = (d.recent || []).filter(r => isToday(r.start_time));
        $("#dash-recent").innerHTML = todayRecs.length
            ? todayRecs.map(recRow).join("")
            : '<tr><td colspan="6" class="empty">今日暂无产物</td></tr>';
    } catch (e) { toast("看板加载失败: " + e.message, "err"); }
}

function recRow(r) {
    const tag = r.status === "completed" ? "done" : (r.status === "failed" ? "failed" : "recording");
    return `<tr>
        <td>任务#${r.task_id}</td>
        <td class="mono">${r.start_time || "-"}</td>
        <td class="mono">${fmtDur(r.duration)}</td>
        <td class="mono">${fmtSize(r.file_size)}</td>
        <td><span class="tag ${tag}">${r.status}</span></td>
        <td>${recOps(r)}</td>
    </tr>`;
}

function recOps(r) {
    const btns = [];
    if (r.file_url) btns.push(`<button class="btn ghost sm" onclick="playRec('${r.file_url}')">试听</button>`);
    if (r.id) {
        btns.push(`<button class="btn sm" onclick="openRec(${r.id})">打开</button>`);
        btns.push(`<button class="btn sm" onclick="revealRec(${r.id})">进文件夹</button>`);
        btns.push(`<button class="btn sm danger" onclick="delRec(${r.id})">删除</button>`);
    }
    return btns.join(" ") || "-";
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
async function loadPlatforms() {
    const list = await api("/api/platforms");
    $("#f-platform").innerHTML = list.map(p => `<option value="${p.name}">${p.label}</option>`).join("");
}

async function loadTasks() {
    const tasks = await api("/api/tasks");
    $("#task-tbody").innerHTML = tasks.length ? tasks.map(t => `
        <tr>
            <td>${t.id}</td>
            <td><b>${t.name}</b></td>
            <td>${t.platform}</td>
            <td>${t.anchor_name || "-"}</td>
            <td class="mono">${t.cron}</td>
            <td>${t.running ? '<span class="tag recording">录制中</span>' : `<span class="tag ${t.enabled ? 'on' : 'off'}">${t.enabled ? '启用' : '停用'}</span>`}</td>
            <td>${t.recording_count}</td>
            <td>
                <button class="btn sm" onclick="runTask(${t.id})">立即检查</button>
                <button class="btn sm" onclick="editTask(${t.id})">编辑</button>
                <button class="btn sm" onclick="toggleTask(${t.id}, ${t.enabled ? 0 : 1})">${t.enabled ? '停用' : '启用'}</button>
                <button class="btn sm danger" onclick="delTask(${t.id}, ${t.recording_count})">删除</button>
            </td>
        </tr>`).join("") : '<tr><td colspan="8" class="empty">暂无任务，点右上角「新增任务」</td></tr>';

    const filter = $("#filter-task");
    filter.innerHTML = '<option value="">全部任务</option>' + tasks.map(t => `<option value="${t.id}">${t.name}</option>`).join("");
}

function showForm() { $("#task-form").classList.remove("hidden"); }
function hideForm() { $("#task-form").classList.add("hidden"); $("#f-id").value = ""; }
function onPreset(sel) { if (sel.value) $("#f-cron").value = sel.value; }

$("#btn-add").onclick = () => { hideForm(); showForm(); };

async function editTask(id) {
    const tasks = await api("/api/tasks");
    const t = tasks.find(x => x.id === id);
    if (!t) return;
    $("#f-id").value = t.id;
    $("#f-name").value = t.name;
    $("#f-platform").value = t.platform;
    $("#f-home").value = t.anchor_home;
    $("#f-anchor").value = t.anchor_name || "";
    $("#f-cron").value = t.cron;
    showForm();
}

async function saveTask() {
    const id = $("#f-id").value;
    const body = {
        name: $("#f-name").value.trim(),
        platform: $("#f-platform").value,
        anchor_home: $("#f-home").value.trim(),
        anchor_name: $("#f-anchor").value.trim(),
        cron: $("#f-cron").value.trim(),
    };
    if (!body.name || !body.anchor_home || !body.cron) { toast("任务名 / 主播主页 / 频率为必填", "err"); return; }
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
    const tid = $("#filter-task").value;
    const list = await api(tid ? `/api/recordings?task_id=${tid}` : "/api/recordings");
    $("#recording-tbody").innerHTML = list.length ? list.map(r => `
        <tr>
            <td>${r.id}</td>
            <td>任务#${r.task_id}</td>
            <td class="mono">${r.start_time || "-"}</td>
            <td class="mono">${r.end_time || "-"}</td>
            <td class="mono">${fmtDur(r.duration)}</td>
            <td class="mono">${fmtSize(r.file_size)}</td>
            <td><span class="tag ${r.status === 'completed' ? 'done' : (r.status === 'failed' ? 'failed' : 'recording')}">${r.status}</span></td>
            <td>${recOps(r)}</td>
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
loadStatus();
loadPlatforms();
loadDashboard();
setInterval(() => { loadStatus(); if (!$("#page-dashboard").classList.contains("hidden")) loadDashboard(); }, 15000);
