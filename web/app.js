// 前端逻辑：任务管理 + 产物查看
const $ = (s) => document.querySelector(s);

function fmtSize(bytes) {
    if (!bytes) return "0";
    if (bytes < 1024) return bytes + "B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + "KB";
    return (bytes / 1024 / 1024).toFixed(1) + "MB";
}
function fmtDur(sec) {
    if (!sec) return "0s";
    const m = Math.floor(sec / 60), s = sec % 60;
    if (m < 60) return `${m}m${s}s`;
    const h = Math.floor(m / 60);
    return `${h}h${m % 60}m`;
}

async function loadStatus() {
    try {
        const r = await fetch("/api/status");
        const s = await r.json();
        const ready = s.recorder_device_ready;
        const el = $("#status-bar");
        el.innerHTML = `
            ffmpeg: ${s.ffmpeg} &nbsp;|&nbsp;
            声卡: <span class="${ready ? 'ok' : 'bad'}">${ready ? '已就绪' : '未就绪(' + s.device_hint + ')'}</span>
            &nbsp;|&nbsp; 录制中任务: ${s.running.length ? s.running.join(',') : '无'}`;
    } catch (e) {
        $("#status-bar").textContent = "状态加载失败";
    }
}

async function loadPlatforms() {
    const r = await fetch("/api/platforms");
    const list = await r.json();
    const sel = $("#f-platform");
    sel.innerHTML = list.map(p => `<option value="${p.name}">${p.label}</option>`).join("");
}

async function loadTasks() {
    const r = await fetch("/api/tasks");
    const tasks = await r.json();
    const tbody = $("#task-tbody");
    tbody.innerHTML = tasks.map(t => `
        <tr>
            <td>${t.id}</td>
            <td>${t.name}</td>
            <td>${t.platform}</td>
            <td>${t.anchor_name || '-'}</td>
            <td>${t.cron}</td>
            <td><span class="tag ${t.enabled ? 'on' : 'off'}">${t.enabled ? '启用' : '停用'}</span></td>
            <td>${t.recording_count}</td>
            <td>${t.running ? '<span class="tag recording">录制中</span>' : '-'}</td>
            <td>
                <button class="btn sm" onclick="runTask(${t.id})">立即检查</button>
                <button class="btn sm" onclick="editTask(${t.id})">编辑</button>
                <button class="btn sm" onclick="toggleTask(${t.id}, ${t.enabled ? 0 : 1})">${t.enabled ? '停用' : '启用'}</button>
                <button class="btn sm danger" onclick="delTask(${t.id})">删除</button>
            </td>
        </tr>`).join("") || '<tr><td colspan="9" style="text-align:center;color:#999">暂无任务，点右上角新增</td></tr>';

    // 产物筛选下拉
    const filter = $("#filter-task");
    filter.innerHTML = '<option value="">全部任务</option>' +
        tasks.map(t => `<option value="${t.id}">${t.name}</option>`).join("");
}

function showForm() { $("#task-form").classList.remove("hidden"); }
function hideForm() { $("#task-form").classList.add("hidden"); $("#f-id").value = ""; }

function onPreset(sel) {
    if (sel.value) $("#f-cron").value = sel.value;
}

function editTask(id) {
    fetch("/api/tasks").then(r => r.json()).then(tasks => {
        const t = tasks.find(x => x.id === id);
        if (!t) return;
        $("#f-id").value = t.id;
        $("#f-name").value = t.name;
        $("#f-platform").value = t.platform;
        $("#f-home").value = t.anchor_home;
        $("#f-anchor").value = t.anchor_name || "";
        $("#f-cron").value = t.cron;
        showForm();
    });
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
    if (!body.name || !body.anchor_home || !body.cron) { alert("任务名/主页/频率必填"); return; }
    if (id) {
        await fetch(`/api/tasks/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    } else {
        await fetch("/api/tasks", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    }
    hideForm();
    loadTasks();
}

async function delTask(id) {
    if (!confirm("确认删除该任务？产物文件保留")) return;
    await fetch(`/api/tasks/${id}`, { method: "DELETE" });
    loadTasks();
}

async function toggleTask(id, enabled) {
    await fetch(`/api/tasks/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled: !!enabled }) });
    loadTasks();
}

async function runTask(id) {
    const r = await fetch(`/api/tasks/${id}/run`, { method: "POST" });
    const j = await r.json();
    alert(j.msg || "已触发");
    setTimeout(loadStatus, 3000);
    setTimeout(loadRecordings, 15000);
}

async function loadRecordings() {
    const tid = $("#filter-task").value;
    const url = tid ? `/api/recordings?task_id=${tid}` : "/api/recordings";
    const r = await fetch(url);
    const list = await r.json();
    const tbody = $("#recording-tbody");
    tbody.innerHTML = list.map(x => `
        <tr>
            <td>${x.id}</td>
            <td>任务#${x.task_id}</td>
            <td>${x.start_time || '-'}</td>
            <td>${x.end_time || '-'}</td>
            <td>${fmtDur(x.duration)}</td>
            <td>${fmtSize(x.file_size)}</td>
            <td><span class="tag ${x.status === 'completed' ? 'done' : (x.status === 'failed' ? 'failed' : 'recording')}">${x.status}</span></td>
            <td>${x.file_url ? `<audio controls src="${x.file_url}"></audio>` : '-'}</td>
        </tr>`).join("") || '<tr><td colspan="8" style="text-align:center;color:#999">暂无产物</td></tr>';
}

$("#btn-add").onclick = showForm;

// 初始化 + 定时刷新
loadStatus();
loadPlatforms();
loadTasks();
loadRecordings();
setInterval(() => { loadStatus(); loadTasks(); loadRecordings(); }, 15000);
