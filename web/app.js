const $ = (selector) => document.querySelector(selector);
const paths = {
  play: '<path d="m8 5 11 7-11 7z" fill="currentColor" stroke="none"/>',
  pause: '<path d="M9 6v12m6-12v12" stroke-width="3"/>',
  volume: '<path d="M3 9h4l5-4v14l-5-4H3zM16 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/>',
  muted: '<path d="M3 9h4l5-4v14l-5-4H3zM16 9l5 6m0-6-5 6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  dots: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  search: '<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',
  dashboard:
    '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  tasks: '<rect x="4" y="3" width="16" height="18" rx="3"/><path d="M8 8h8m-8 4h8m-8 4h5"/>',
  library: '<path d="M4 5v15m5-17v17m5-15v15m3-14 4 13"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  audio: '<path d="M3 10v4m4-8v12m5-16v20m5-16v12m4-8v4"/>',
  radio:
    '<circle cx="12" cy="12" r="2"/><path d="M7 7a7 7 0 0 0 0 10m10-10a7 7 0 0 1 0 10M4 4a11 11 0 0 0 0 16M20 4a11 11 0 0 1 0 16"/>',
  refresh: '<path d="M20 10a8 8 0 1 0-1 7m1-13v6h-6"/>',
};
function icon(name) {
  return '<svg viewBox="0 0 24 24" aria-hidden="true">' + paths[name] + "</svg>";
}
for (const el of document.querySelectorAll("[data-icon]")) {
  el.innerHTML = icon(el.dataset.icon);
  el.ariaHidden = "true";
}
for (let n = 0; n < 57; n++) {
  const bar = document.createElement("span");
  bar.style.height = 9 + Math.abs(Math.sin(n * 0.22) * Math.cos(n * 0.36)) * 90 + "%";
  $(".meter").append(bar);
}
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
const intervalOptions = [5, 10, 15, 20, 30, 45, 60, 90, 120];
const titles = { dashboard: "录制总览", tasks: "录制任务", recordings: "录音与文稿" };
const transcriptStates = {
  queued: "等待转写",
  running: "正在转写",
  completed: "文稿已就绪",
  failed: "转写失败",
  unavailable: "尚未转写",
};
let tasks = [],
  records = [],
  editing,
  reading,
  readerState,
  pendingConfirm,
  toastTimer,
  revision = 0;
let tab = "tasks";
let selectedTask = null;
let selectedRecord = null;
let sentenceEnd = null;
let desktopFiles = false;
const audio = $("#player");
function duration(seconds) {
  const n = Math.max(0, Math.floor(seconds || 0));
  return (
    (n >= 3600 ? Math.floor(n / 3600) + ":" : "") +
    String(Math.floor(n / 60) % 60).padStart(2, "0") +
    ":" +
    String(n % 60).padStart(2, "0")
  );
}
function size(n) {
  return n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.round((n || 0) / 1024) + " KB";
}
function notify(msg) {
  $("#toast").textContent = msg;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("#toast").textContent = ""), 3800);
}
async function api(path, method = "GET", data) {
  const response = await fetch("/api/" + path, {
    method,
    headers: data ? { "Content-Type": "application/json" } : {},
    body: data ? JSON.stringify(data) : undefined,
  });
  const result = await response.json();
  if (!response.ok || result?.ok === false) {
    const detail = result.detail || result.msg;
    throw new Error(
      Array.isArray(detail)
        ? detail.map((e) => e.msg).join(" · ")
        : detail || "操作未成功，请刷新后重试",
    );
  }
  return result;
}
function updateHTML(selector, html) {
  const el = $(selector);
  if (el._markup !== html) {
    const active = el.contains(document.activeElement) ? document.activeElement.dataset : null;
    const action = active?.action,
      id = active?.id;
    el.innerHTML = html;
    el._markup = html;
    if (action)
      [...el.querySelectorAll("[data-action]")]
        .find((b) => b.dataset.action === action && b.dataset.id === id)
        ?.focus({ preventScroll: true });
  }
}
function action(name, label, id, tone = "") {
  return (
    '<button class="' +
    tone +
    '" data-action="' +
    name +
    '" data-id="' +
    Number(id) +
    '">' +
    label +
    "</button>"
  );
}
function badge(text, tone = "") {
  return '<span class="badge ' + tone + '">' + esc(text) + "</span>";
}
function empty(iconName, title, sub) {
  return (
    '<div class="empty"><i aria-hidden="true" data-icon="' +
    iconName +
    '">' +
    icon(iconName) +
    "</i><strong>" +
    title +
    "</strong><p>" +
    sub +
    "</p></div>"
  );
}
function identity(iconName, title, sub) {
  return (
    '<span class="identity"><span class="record-icon"><i data-icon="' +
    iconName +
    '">' +
    icon(iconName) +
    '</i></span><span class="identity-copy"><strong>' +
    esc(title) +
    '</strong><span class="sub">' +
    esc(sub) +
    "</span></span></span>"
  );
}
function recordingLabel(r) {
  if (r.status === "completed") return transcriptStates[r.transcript_status || "unavailable"];
  return r.status === "failed" ? "录制失败" : "录制中";
}
function recRow(r) {
  const st = r.transcript_status || "unavailable";
  const tone = [r.status, st].includes("failed")
    ? "failed"
    : ["queued", "running"].includes(st) || r.status === "recording"
      ? "busy"
      : "";
  return (
    '<article class="row">' +
    identity(
      "audio",
      r.task_name || "任务 #" + r.task_id,
      [r.start_time, duration(r.duration), size(r.file_size)].join(" · "),
    ) +
    badge(recordingLabel(r), tone) +
    action("read", st === "completed" ? "查看文稿" : "录音详情", r.id) +
    "</article>"
  );
}
function freq(t) {
  return t.interval_minutes ? "每 " + t.interval_minutes + " 分钟" : "计划 " + t.cron;
}
function taskStatus(t) {
  if (!t.running) return t.enabled ? "已启用" : "已停用";
  if (!t.capturing) return "检查开播中";
  return t.paused ? "已暂停" : "录制中";
}
function renderTaskList() {
  $("#clear-search").hidden = !$("#task-search").value;
  const query = $("#task-search").value.trim().toLowerCase();
  const visible = tasks.filter((t) =>
    [t.name, t.anchor_name].some((n) => n?.toLowerCase().includes(query)),
  );
  $("#task-count").textContent = tasks.length;
  updateHTML(
    "#task-list",
    visible
      .map(
        (t) =>
          '<button class="task-item" data-action="select-task" data-id="' +
          t.id +
          '" aria-pressed="' +
          (t.id === selectedTask) +
          '">' +
          identity("audio", t.name, taskStatus(t) + " · " + t.recording_count + " 条录音") +
          "</button>",
      )
      .join("") || empty("tasks", tasks.length ? "没有匹配的任务" : "还没有录制任务", ""),
  );
}
function renderWorkspace() {
  renderTaskList();
  const t = tasks.find((t) => t.id === selectedTask);
  $("#task-detail").hidden = !t;
  $("#task-empty").hidden = Boolean(t);
  if (!t) {
    clearReader();
    updateHTML(
      "#task-empty",
      empty("tasks", "添加第一个录制任务", "点击右上角「新建任务」，填写主播主页和检查频率。"),
    );
    return;
  }
  $("#task-title").textContent = t.name;
  const windowLabel =
    t.scan_start || t.scan_end
      ? (t.scan_start || "不限") +
        " 至 " +
        (t.scan_end || "不限") +
        (t.scan_start && t.scan_end && t.scan_start > t.scan_end ? "（次日）" : "")
      : "全天";
  $("#task-meta").textContent = [
    t.anchor_name || "抖音直播",
    freq(t),
    windowLabel,
    taskStatus(t),
  ].join(" · ");
  $("#task-result").hidden = t.running || !t.last_result;
  $("#task-result").textContent = t.last_result ? "最近检查 · " + t.last_result : "";
  const controls = t.running
    ? t.capturing
      ? action(t.paused ? "resume" : "pause", t.paused ? "恢复" : "暂停", t.id) +
        action("stop", "停止", t.id)
      : badge("正在检查开播", "busy")
    : action("edit", "编辑", t.id) +
      action("run", "立即检查", t.id, "primary") +
      '<details class="more"><summary aria-label="更多任务操作">' +
      icon("dots") +
      "</summary><div>" +
      action("toggle", t.enabled ? "停用" : "启用", t.id) +
      action("delete-task", "删除", t.id, "danger") +
      "</div></details>";
  updateHTML("#task-actions", controls);
  $("#record-count").textContent = "（" + records.length + "）";
  const record = records.find((r) => r.id === selectedRecord) || records[0];
  $("#task-record").hidden = !record;
  $("#record-empty").hidden = Boolean(record);
  if (!record) {
    if (choiceOwner === $("#task-record")) closeChoice();
    clearReader();
    updateHTML(
      "#record-empty",
      empty("audio", "此任务暂无录音", "定时检查或点击「立即检查」，开播后自动录制。"),
    );
    return;
  }
  setChoices(
    $("#task-record"),
    records.map((r) => [r.id, r.start_time + " · " + recordingLabel(r)]),
    record.id,
  );
  if (
    !reading ||
    reading.id !== record.id ||
    reading.status !== record.status ||
    reading.file_url !== record.file_url
  ) {
    openReader(record, true);
  } else if (record.transcript_status && readerState !== record.transcript_status) {
    loadTranscript();
  }
}
async function refresh() {
  const current = ++revision;
  const filter = $("#filter-task").value;
  try {
    const [all, data] = await Promise.all([
      api("tasks"),
      tab === "dashboard"
        ? api("dashboard")
        : tab === "recordings"
          ? api("recordings" + (filter ? "?task_id=" + encodeURIComponent(filter) : ""))
          : selectedTask
            ? api("recordings?task_id=" + selectedTask)
            : Promise.resolve([]),
    ]);
    if (current !== revision) return;
    tasks = all;
    setChoices($("#filter-task"), [["", "全部任务"], ...tasks.map((t) => [t.id, t.name])], filter);
    if (filter && !$("#filter-task").value && tab === "recordings") return refresh();
    if (tab === "tasks") {
      if (tasks.length && !tasks.some((t) => t.id === selectedTask)) {
        selectedTask = tasks[0].id;
        selectedRecord = null;
        return refresh();
      }
      if (!tasks.length) selectedTask = null;
      records = data;
      renderWorkspace();
    } else if (tab === "dashboard") {
      const run = data.running_tasks;
      updateHTML(
        "#running-list",
        run.length
          ? run
              .map(
                (t) =>
                  esc(t.name) +
                  "<small>" +
                  (t.capturing ? (t.paused ? "已暂停" : "正在录制") : "正在检查开播状态") +
                  "</small>",
              )
              .join("")
          : "当前没有进行中的录制<small>" + data.task_enabled + " 个任务已启用定时检查</small>",
      );
      const stats = [
        ["今日录音", data.today_count, "合计 " + duration(data.today_duration)],
        ["录制任务", data.task_total, "已启用 " + data.task_enabled + " 个"],
        ["累计录音", data.rec_total, "完成 " + data.rec_completed + " · 失败 " + data.rec_failed],
        ["录音总时长", duration(data.total_duration), "占用 " + size(data.total_size)],
      ];
      updateHTML(
        "#stat-cards",
        stats
          .map(
            ([label, value, hint]) =>
              '<div class="metric"><span class="metric-label">' +
              label +
              "</span><strong>" +
              value +
              "</strong><small>" +
              hint +
              "</small></div>",
          )
          .join(""),
      );
      records = data.recent;
      updateHTML(
        "#dash-recent",
        records.map(recRow).join("") ||
          empty("audio", "暂无录音", "录制结束后，可在这里收听录音并阅读文稿。"),
      );
    } else {
      records = data;
      updateHTML(
        "#recording-list",
        records.map(recRow).join("") ||
          empty("library", "暂无匹配的录音", "可检查筛选条件或前往录制任务。"),
      );
    }
    if (tab !== "tasks" && reading?.status === "recording") {
      const latest = records.find((r) => r.id === reading.id);
      if (latest && latest.status !== "recording") openReader(latest);
    }
    $("#load-error").hidden = true;
  } catch (e) {
    if (current === revision) {
      $("#load-error").textContent = "加载失败，正在等待重试。" + e.message;
      $("#load-error").hidden = false;
    }
  }
}
function navigate() {
  const key = location.hash.slice(1);
  if ($("#reader").open) $("#reader").close();
  clearReader();
  tab = Object.hasOwn(titles, key) ? key : "tasks";
  for (const link of document.querySelectorAll("[data-tab]")) {
    link.dataset.tab === tab
      ? link.setAttribute("aria-current", "page")
      : link.removeAttribute("aria-current");
    $("#page-" + link.dataset.tab).hidden = link.dataset.tab !== tab;
  }
  document.title = titles[tab] + " · 声序";
  refresh();
}
async function status() {
  try {
    const s = await api("status");
    if (desktopFiles !== s.desktop_files) {
      desktopFiles = s.desktop_files;
      if (reading) renderFileActions(reading);
    }
    $("[data-action=folder]").hidden = !desktopFiles;
    const modes = { browser: "浏览器采集", system: "系统声卡", loopback: "系统回环" };
    $("#status-bar").textContent =
      modes[s.capture_mode] + (s.recorder_device_ready ? "已就绪" : "未就绪");
    $(".system").classList.toggle("ready", s.recorder_device_ready);
    $(".system").title = s.device_hint;
  } catch {
    $("#status-bar").textContent = "服务未连接";
    $(".system").classList.remove("ready");
  }
}
const clockUnits = [24, 60].map((max) =>
  Array.from({ length: max }, (_, i) => {
    const digits = String(i).padStart(2, "0");
    return [digits, digits];
  }),
);
function setClock(field, value) {
  field.dataset.time = value;
  const parts = value.split(":");
  field.querySelectorAll(".choice").forEach((button, i) => {
    setChoices(button, [["", i === 0 ? "时" : "分"], ...clockUnits[i]], parts[i] || "");
  });
  field.querySelector(".clear-clock").disabled = !value;
}
for (const field of document.querySelectorAll(".clock-field")) {
  const label = document.getElementById(field.getAttribute("aria-labelledby")).textContent;
  field.innerHTML =
    '<i data-icon="clock">' +
    icon("clock") +
    "</i>" +
    '<button type="button" class="choice" aria-label="' +
    label +
    '小时"></button><span aria-hidden="true">:</span>' +
    '<button type="button" class="choice" aria-label="' +
    label +
    '分钟"></button>' +
    '<button type="button" class="clear-clock" aria-label="清除' +
    label +
    '时间">' +
    icon("close") +
    "</button>";
  field.onchange = (event) => {
    const parts = [...field.querySelectorAll(".choice")].map((button) => button.value || "00");
    setClock(field, event.target.value ? parts.join(":") : "");
  };
  field.querySelector(".clear-clock").onclick = () => {
    setClock(field, "");
    field.querySelector(".choice").focus();
  };
}
function invalidField(field, message) {
  field.closest("label").after($("#form-error"));
  field.setAttribute("aria-invalid", "true");
  field.setAttribute("aria-describedby", "form-error");
  field.focus();
  throw new Error(message);
}

async function editor(t) {
  const platforms = await api("platforms");
  editing = t;
  $("#task-form").reset();
  $("#task-form .form-body").append($("#form-error"));
  $("#editor-title").textContent = t ? "编辑任务" : "新建任务";
  $("#form-error").hidden = true;
  setChoices(
    $("#f-platform"),
    platforms.map((p) => [p.name, p.label]),
    t?.platform,
  );
  const frequencies = intervalOptions.map((n) => [n, "每 " + n + " 分钟"]);
  if (t && !t.interval_minutes) frequencies.push(["legacy", "保留原计划 · " + t.cron]);
  setChoices($("#f-frequency"), frequencies, t ? t.interval_minutes || "legacy" : 10);
  $("#f-name").value = t?.name || "";
  $("#f-home").value = t?.anchor_home || "";
  $("#f-anchor").value = t?.anchor_name || "";
  setClock($("#f-scan-start"), t?.scan_start || "");
  setClock($("#f-scan-end"), t?.scan_end || "");
  for (const field of $("#task-form").querySelectorAll("[aria-invalid]")) {
    field.removeAttribute("aria-invalid");
    field.removeAttribute("aria-describedby");
  }
  $("#editor").showModal();
}
$("#task-form").oninput = (event) => {
  event.target.removeAttribute("aria-invalid");
  event.target.removeAttribute("aria-describedby");
  $("#form-error").hidden = true;
};
$("#task-form").onsubmit = async (event) => {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  try {
    $("#task-form .form-body").append($("#form-error"));
    const home = $("#f-home").value.trim();
    const body = {
      name: $("#f-name").value.trim(),
      anchor_home: home,
      anchor_name: $("#f-anchor").value.trim(),
      platform: $("#f-platform").value,
      scan_start: $("#f-scan-start").dataset.time,
      scan_end: $("#f-scan-end").dataset.time,
    };
    if (!body.name) invalidField($("#f-name"), "请输入任务名称");
    if (!/^https?:\/\/(www\.)?douyin\.com\/user\/[^/?#]+(?:[/?#]|$)/i.test(home))
      invalidField($("#f-home"), "请填写抖音主播主页，例如 https://www.douyin.com/user/…");
    const value = $("#f-frequency").value;
    if (value !== "legacy") body.interval_minutes = Number(value);
    const saved = await api(
      editing ? "tasks/" + editing.id : "tasks",
      editing ? "PUT" : "POST",
      body,
    );
    selectedTask = editing ? editing.id : saved.id;
    selectedRecord = null;
    $("#task-search").value = "";
    $("#editor").close();
    location.hash = "tasks";
    await refresh();
    notify("任务已保存");
  } catch (e) {
    $("#form-error").hidden = false;
    $("#form-error").textContent = e.message;
  } finally {
    button.disabled = false;
  }
};
function confirmAction(title, message, run, files = false) {
  $("#confirm-title").textContent = title;
  $("#confirm-message").textContent = message;
  $("#confirm-submit").textContent = title;
  $("#delete-files").checked = false;
  $(".check").hidden = !files;
  pendingConfirm = run;
  $("#confirm-dialog").returnValue = "cancel";
  $("#confirm-dialog").showModal();
}
$("#confirm-dialog").onclose = async () => {
  if ($("#confirm-dialog").returnValue !== "confirm") return;
  try {
    await pendingConfirm($("#delete-files").checked);
    await refresh();
  } catch (e) {
    notify(e.message);
  }
};
let sentenceButtons = [];
let highlighted;
let manuscript = "";

function clearReader() {
  reading = null;
  readerState = null;
  sentenceEnd = null;
  if (audio.hasAttribute("src")) {
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
  }
  $("#reader-content").hidden = true;
}
function renderFileActions(r) {
  const links =
    (r.file_url
      ? '<a download href="' +
        esc(r.file_url) +
        '">下载音频</a>' +
        (desktopFiles ? action("open", "系统播放", r.id) + action("reveal", "定位文件", r.id) : "")
      : "") + (r.status !== "recording" ? action("delete-rec", "删除录音", r.id, "danger") : "");
  updateHTML("#file-actions", links);
}
function openReader(r, inline = false) {
  clearReader();
  const content = $("#reader-content");
  (inline ? $("#inline-reader") : $("#reader-home")).append(content);
  content.hidden = false;
  $("#paragraph-view").setAttribute("aria-pressed", "true");
  $("#speech-map").hidden = true;
  sentenceButtons = [];
  highlighted = null;
  manuscript = "";
  $("#reader-tools").hidden = true;
  $("#asr-progress").hidden = true;
  $("#sentence-view").setAttribute("aria-pressed", "false");
  $("#transcript-body").classList.remove("sentences");
  reading = r;
  readerState = null;
  $("#reader-title").textContent = r.task_name || "任务 #" + r.task_id;
  $("#record-meta").textContent = [
    r.start_time,
    r.end_time ? "结束 " + r.end_time : "",
    duration(r.duration),
    size(r.file_size),
  ]
    .filter(Boolean)
    .join(" · ");
  $("#audio-panel").hidden = !r.file_url;
  if (r.file_url) audio.src = r.file_url;
  renderFileActions(r);
  $("#transcript-status").textContent =
    r.status === "recording"
      ? "录制结束后将自动转写"
      : r.status === "failed"
        ? "本次录制失败" + (r.error ? " · " + r.error : "")
        : "正在读取转写状态…";
  $("#transcript-body").replaceChildren();
  if (!inline && !$("#reader").open) $("#reader").showModal();
  if (r.status === "completed") loadTranscript();
}
let pendingTranscript = null;
async function loadTranscript() {
  const rec = reading;
  if (!rec || rec.status !== "completed" || pendingTranscript === rec) return;
  pendingTranscript = rec;
  try {
    const data = await api("recordings/" + rec.id + "/transcript");
    if (reading !== rec) return;
    const groups = data.paragraphs;
    const label = transcriptStates[data.status];
    readerState = data.status;
    $("#transcript-status").textContent =
      data.status === "completed"
        ? groups.length
          ? label +
            " · " +
            groups.length +
            " 段 · " +
            groups.reduce((n, g) => n + g.length, 0) +
            " 句"
          : "转写完成，未识别到语音。"
        : data.status === "failed"
          ? "转写失败 · " + data.error
          : data.status === "running"
            ? data.processed
              ? "正在转写 · 已处理至 " + duration(data.processed)
              : "正在识别语音，完成后将自动显示文稿。"
            : label;
    $("#asr-progress").hidden = data.status !== "running";
    const progress = $("#asr-progress");
    if (data.status === "running" && data.processed > 0 && rec.duration > 0) {
      progress.max = rec.duration;
      progress.value = Math.min(data.processed, rec.duration);
    } else progress.removeAttribute("value");
    if (data.status === "completed") {
      $("#reader-tools").hidden = !groups.length;
      $("#sentence-view").hidden = !rec.file_url;
      manuscript = groups.map((group) => group.map((line) => line.text).join(" ")).join("\n\n");
      $("#transcript-body").innerHTML = groups
        .map((group) => {
          const lines = group
            .map((line) =>
              rec.file_url
                ? `<button class="sentence" data-start="${Number(line.start)}" data-end="${Number(line.end)}" data-time="${duration(line.start)}" title="从 ${duration(line.start)} 播放">${esc(line.text)}</button>`
                : esc(line.text),
            )
            .join(" ");
          return `<div class="passage"><time>${duration(group[0].start)}</time><p>${lines}</p></div>`;
        })
        .join("");
      sentenceButtons = Array.from($("#transcript-body").querySelectorAll(".sentence"));
      const map = $("#speech-map");
      const ctx = map.getContext("2d");
      if (ctx && groups.length && rec.duration > 0) {
        ctx.clearRect(0, 0, map.width, map.height);
        ctx.fillStyle = "#bad7ed";
        const scale = map.width / rec.duration;
        for (const group of groups) {
          for (const line of group) {
            ctx.fillRect(
              line.start * scale,
              10,
              Math.max(1, (line.end - line.start) * scale - 1),
              10,
            );
          }
        }
        map.hidden = false;
      }
    } else {
      $("#transcript-body").innerHTML =
        ["unavailable", "failed"].includes(data.status) && rec.file_exists
          ? action("retry", data.status === "failed" ? "重试转写" : "生成文稿", rec.id)
          : "";
    }
  } catch (e) {
    if (reading === rec) {
      readerState = null;
      $("#transcript-status").textContent = "读取失败，将自动重试。" + e.message;
    }
  } finally {
    if (pendingTranscript === rec) pendingTranscript = null;
  }
}
function sentenceMode(enabled) {
  $("#transcript-body").classList.toggle("sentences", enabled);
  $("#sentence-view").setAttribute("aria-pressed", String(enabled));
  $("#paragraph-view").setAttribute("aria-pressed", String(!enabled));
  sentenceEnd = null;
}
$("#sentence-view").onclick = () => sentenceMode(true);
$("#paragraph-view").onclick = () => sentenceMode(false);
$("#copy-text").onclick = async () => {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(manuscript);
    } else {
      const field = document.createElement("textarea");
      field.value = manuscript;
      $("#reader-content").append(field);
      field.select();
      const copied = document.execCommand("copy");
      field.remove();
      $("#copy-text").focus();
      if (!copied) throw new Error();
    }
    $("#transcript-status").textContent = "全文已复制";
  } catch {
    $("#transcript-status").textContent = "无法访问剪贴板，请选择文稿后复制。";
  }
};
const rates = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2];
function syncTransport() {
  const total = Number.isFinite(audio.duration) ? audio.duration : 0;
  const track = $("#play-position");
  track.disabled = !total;
  track.max = total;
  track.value = audio.currentTime || 0;
  track.style.setProperty("--fill", (total ? (100 * audio.currentTime) / total : 0) + "%");
  track.setAttribute("aria-valuetext", duration(audio.currentTime) + " / " + duration(total));
  $("#play-duration").textContent = duration(total);
  $("#play-time").textContent = duration(audio.currentTime);
}
function syncPlayButton() {
  const button = $("#play-audio");
  button.setAttribute("aria-label", audio.paused ? "播放录音" : "暂停回听");
  button.innerHTML = icon(audio.paused ? "play" : "pause");
}
$("#play-audio").onclick = async () => {
  sentenceEnd = null;
  if (!audio.paused) return audio.pause();
  try {
    await audio.play();
  } catch {
    $("#transcript-status").textContent = "播放失败，请检查音频文件是否可用。";
  }
};
$("#play-position").oninput = (event) => {
  sentenceEnd = null;
  audio.currentTime = Number(event.target.value);
  syncTransport();
};
$("#mute").onclick = () => {
  if (!audio.volume) {
    audio.volume = 1;
    audio.muted = false;
  } else audio.muted = !audio.muted;
};
$("#volume").oninput = (event) => {
  audio.volume = Number(event.target.value);
  audio.muted = audio.volume === 0;
};
function syncVolume() {
  const muted = audio.muted || audio.volume === 0;
  $("#mute").setAttribute("aria-label", muted ? "取消静音" : "静音");
  $("#mute").setAttribute("aria-pressed", String(muted));
  $("#mute").innerHTML = icon(muted ? "muted" : "volume");
  $("#volume").value = audio.muted ? 0 : audio.volume;
  $("#volume").style.setProperty("--fill", $("#volume").value * 100 + "%");
}
audio.addEventListener("volumechange", syncVolume);
syncVolume();
$("#speed").onchange = (e) => {
  audio.defaultPlaybackRate = audio.playbackRate = Number(e.target.value);
};
setChoices(
  $("#speed"),
  rates.map((rate) => [rate, rate + "×"]),
  1,
);
for (const event of ["loadedmetadata", "durationchange", "emptied", "timeupdate"])
  audio.addEventListener(event, syncTransport);
for (const event of ["play", "pause", "ended", "emptied"])
  audio.addEventListener(event, syncPlayButton);
audio.onplay = () => {
  if (tab === "tasks" && reading) selectedRecord = reading.id;
};
audio.ontimeupdate = () => {
  if (sentenceEnd !== null && audio.currentTime >= sentenceEnd) {
    audio.pause();
    sentenceEnd = null;
  }
  let left = 0,
    right = sentenceButtons.length;
  while (left < right) {
    const middle = Math.floor((left + right) / 2);
    if (Number(sentenceButtons[middle].dataset.start) <= audio.currentTime) left = middle + 1;
    else right = middle;
  }
  const candidate = sentenceButtons[left - 1];
  const next = candidate && audio.currentTime < Number(candidate.dataset.end) ? candidate : null;
  if (next !== highlighted) {
    highlighted?.classList.remove("current");
    next?.classList.add("current");
    highlighted = next;
  }
};
$("#reader").onclose = () => {
  if (!$("#reader").open && $("#reader-home").contains($("#reader-content"))) clearReader();
};
async function operate(name, id) {
  const t = tasks.find((t) => t.id === id);
  if (name === "select-task") {
    if (selectedTask === id) return;
    selectedTask = id;
    selectedRecord = null;
    records = [];
    renderWorkspace();
    return refresh();
  }
  if (name === "edit") return editor(t);
  if (name === "read") return openReader(records.find((r) => r.id === id));
  if (name === "refresh") return refresh();
  if (name === "folder") {
    await api("recordings/folder", "POST");
    return notify("已请求打开录音目录");
  }
  if (name === "open" || name === "reveal") {
    await api("recordings/" + id + "/" + name, "POST");
    return;
  }
  if (name === "retry") {
    await api("recordings/" + id + "/transcript", "POST");
    await loadTranscript();
    return refresh();
  }
  if (name === "delete-task")
    return confirmAction(
      "删除任务",
      "将删除「" + t.name + "」及关联的录音记录和文稿。",
      (files) => api("tasks/" + id + "?delete_files=" + files, "DELETE"),
      t.recording_count > 0,
    );
  if (name === "delete-rec")
    return confirmAction("删除录音", "本地音频和转写文稿将一并删除。", async () => {
      await api("recordings/" + id, "DELETE");
      if ($("#reader").open) $("#reader").close();
      clearReader();
    });
  if (name === "stop")
    return confirmAction("停止录制", "保存已录音频后，系统会自动开始转写。", () =>
      api("tasks/" + id + "/stop", "POST"),
    );
  if (name === "toggle") await api("tasks/" + id, "PUT", { enabled: !t.enabled });
  else {
    const result = await api("tasks/" + id + "/" + name, "POST");
    notify(result.msg || (name === "pause" ? "已请求暂停" : "已请求恢复"));
  }
  await refresh();
}
document.addEventListener("click", async (event) => {
  const b = event.target.closest("button");
  if (!b) return;
  if (b.hasAttribute("data-close")) {
    b.closest("dialog").close();
    return;
  }
  if (b.classList.contains("sentence")) {
    sentenceEnd = $("#transcript-body").classList.contains("sentences")
      ? Number(b.dataset.end)
      : null;
    audio.currentTime = Number(b.dataset.start);
    try {
      await audio.play();
    } catch (e) {
      $("#transcript-status").textContent = "播放失败 · " + e.message;
    }
    return;
  }
  if (b.id !== "btn-add" && !b.dataset.action) return;
  const dialogId =
    b.id === "btn-add" || b.dataset.action === "edit"
      ? "editor"
      : b.dataset.action === "read"
        ? "reader"
        : ["delete-task", "delete-rec", "stop"].includes(b.dataset.action)
          ? "confirm-dialog"
          : null;
  if (dialogId)
    document.getElementById(dialogId).returnFocus =
      b.closest(".more")?.querySelector("summary") || b;
  if (b.closest(".more")) {
    closeMore();
    $("#task-actions summary")?.focus();
  }
  if (b.dataset.action !== "select-task") b.disabled = true;
  try {
    if (b.id === "btn-add") await editor();
    else await operate(b.dataset.action, Number(b.dataset.id));
  } catch (e) {
    if ($("#reader").open) $("#transcript-status").textContent = e.message;
    else notify(e.message);
  } finally {
    b.disabled = false;
  }
});
document.addEventListener(
  "close",
  (event) => {
    const opener = event.target.returnFocus;
    if (opener?.isConnected && opener.getClientRects().length)
      opener.focus({ preventScroll: true });
    delete event.target.returnFocus;
  },
  true,
);
$("#task-search").oninput = renderTaskList;
$("#clear-search").onclick = () => {
  $("#task-search").value = "";
  renderTaskList();
  $("#task-search").focus();
};
$("#task-record").onchange = (event) => {
  selectedRecord = Number(event.target.value);
  renderWorkspace();
};
function closeMore() {
  const more = document.querySelector(".more[open]");
  if (more) more.open = false;
}
document.addEventListener("click", (e) => {
  if (!e.target.closest(".more") || e.target.closest(".more button")) closeMore();
});
document.addEventListener("keydown", (e) => {
  const more = document.querySelector(".more[open]");
  if (e.key === "Escape" && more) {
    closeMore();
    more.querySelector("summary").focus();
  }
});
$("#filter-task").onchange = refresh;
window.addEventListener("hashchange", () => {
  navigate();
  $("#main").focus();
});
$("#page-date").textContent = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "long",
  day: "numeric",
  weekday: "long",
}).format(new Date());
navigate();
status();
setInterval(() => {
  if (!document.hidden) {
    refresh();
    if (reading && !["completed", "failed", "unavailable"].includes(readerState)) loadTranscript();
  }
}, 3500);
setInterval(() => {
  if (!document.hidden) status();
}, 30000);
