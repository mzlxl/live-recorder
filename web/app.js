const $ = (selector) => document.querySelector(selector);
const paths = {
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
let tab = "dashboard";
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
    '<div class="identity"><span class="record-icon"><i data-icon="' +
    iconName +
    '">' +
    icon(iconName) +
    "</i></span><div><strong>" +
    esc(title) +
    '</strong><span class="sub">' +
    esc(sub) +
    "</span></div></div>"
  );
}
function recRow(r) {
  const st = r.transcript_status || "unavailable";
  const status =
    r.status === "completed" ? transcriptStates[st] : r.status === "failed" ? "录制失败" : "录制中";
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
    badge(status, tone) +
    action("read", st === "completed" ? "查看文稿" : "录音详情", r.id) +
    "</article>"
  );
}
function freq(t) {
  return t.interval_minutes ? "每 " + t.interval_minutes + " 分钟" : "计划 " + t.cron;
}
function taskRow(t) {
  const sub = [
    t.anchor_name || "抖音",
    freq(t),
    t.scan_start || t.scan_end
      ? (t.scan_start || "不限") +
        " 至 " +
        (t.scan_end || "不限") +
        (t.scan_end && t.scan_start > t.scan_end ? "（次日）" : "")
      : "全天",
    t.recording_count + " 条录音",
  ].join(" · ");
  const st = t.running
    ? t.capturing
      ? t.paused
        ? "已暂停"
        : "录制中"
      : "检查开播中"
    : t.enabled
      ? "已启用"
      : "已停用";
  const controls = t.running
    ? t.capturing
      ? action(t.paused ? "resume" : "pause", t.paused ? "恢复" : "暂停", t.id) +
        action("stop", "停止", t.id)
      : ""
    : action("run", "立即检查", t.id) +
      action("edit", "编辑", t.id) +
      action("toggle", t.enabled ? "停用" : "启用", t.id) +
      action("delete-task", "删除", t.id);
  return (
    '<article class="row">' +
    identity("tasks", t.name, sub) +
    badge(st, t.running ? "busy" : "neutral") +
    '<div class="actions">' +
    controls +
    "</div>" +
    (!t.running && t.last_result
      ? '<small class="last-result">最近检查 · ' + esc(t.last_result) + "</small>"
      : "") +
    "</article>"
  );
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
          : Promise.resolve(null),
    ]);
    if (current !== revision) return;
    tasks = all;
    const options =
      '<option value="">全部任务</option>' +
      tasks.map((t) => '<option value="' + t.id + '">' + esc(t.name) + "</option>").join("");
    updateHTML("#filter-task", options);
    $("#filter-task").value = tasks.some((t) => String(t.id) === filter) ? filter : "";
    if (filter && !$("#filter-task").value && tab === "recordings") return refresh();
    if (tab === "tasks") {
      $("#task-count").textContent = tasks.length + " 个任务";
      updateHTML(
        "#task-list",
        tasks.map(taskRow).join("") ||
          empty("tasks", "还没有录制任务", "点击「新建任务」，添加要关注的主播。"),
      );
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
    if (reading?.status === "recording") {
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
  tab = Object.hasOwn(titles, key) ? key : "dashboard";
  for (const link of document.querySelectorAll("[data-tab]")) {
    link.dataset.tab === tab
      ? link.setAttribute("aria-current", "page")
      : link.removeAttribute("aria-current");
    $("#page-" + link.dataset.tab).hidden = link.dataset.tab !== tab;
  }
  $("#page-title").textContent = titles[tab];
  document.title = titles[tab] + " · 声序";
  refresh();
}
async function status() {
  try {
    const s = await api("status");
    desktopFiles = s.desktop_files;
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
async function editor(t) {
  const platforms = await api("platforms");
  editing = t;
  $("#task-form").reset();
  $("#editor-title").textContent = t ? "编辑任务" : "新建任务";
  $("#form-error").hidden = true;
  $("#f-platform").replaceChildren(...platforms.map((p) => new Option(p.label, p.name)));
  $("#f-frequency").replaceChildren(...intervalOptions.map((n) => new Option("每 " + n + " 分钟", n)));
  if (t && !t.interval_minutes) $("#f-frequency").add(new Option("保留原计划 · " + t.cron, "legacy"));
  $("#f-frequency").value = t ? t.interval_minutes || "legacy" : 10;
  for (const [field, key] of Object.entries({
    name: "name",
    home: "anchor_home",
    platform: "platform",
    anchor: "anchor_name",
    "scan-start": "scan_start",
    "scan-end": "scan_end",
  })) {
    if (t) $("#f-" + field).value = t[key] || "";
  }
  $("#editor").showModal();
}
$("#task-form").onsubmit = async (event) => {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  try {
    const home = $("#f-home").value.trim();
    const body = {
      name: $("#f-name").value.trim(),
      anchor_home: home,
      anchor_name: $("#f-anchor").value.trim(),
      platform: $("#f-platform").value,
      scan_start: $("#f-scan-start").value,
      scan_end: $("#f-scan-end").value,
    };
    if (!body.name) throw new Error("请输入任务名称");
    if (!/^https?:\/\/(www\.)?douyin\.com\/user\/[^/?#]+(?:[/?#]|$)/i.test(home))
      throw new Error("请填写抖音主播主页，例如 https://www.douyin.com/user/…");
    const value = $("#f-frequency").value;
    if (value !== "legacy") body.interval_minutes = Number(value);
    await api(editing ? "tasks/" + editing.id : "tasks", editing ? "PUT" : "POST", body);
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

function openReader(r) {
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
  audio.hidden = !r.file_url;
  if (r.file_url) audio.src = r.file_url;
  $("#file-actions").innerHTML =
    (r.file_url
      ? '<a download href="' +
        esc(r.file_url) +
        '">下载音频</a>' +
        (desktopFiles ? action("open", "系统播放", r.id) + action("reveal", "定位文件", r.id) : "")
      : "") + (r.status !== "recording" ? action("delete-rec", "删除录音", r.id, "danger") : "");
  $("#transcript-status").textContent =
    r.status === "recording"
      ? "录制结束后将自动转写"
      : r.status === "failed"
        ? r.error || "录制失败"
        : "正在读取转写状态…";
  $("#transcript-body").replaceChildren();
  if (!$("#reader").open) $("#reader").showModal();
  if (r.status === "completed") loadTranscript();
}
async function loadTranscript() {
  const rec = reading;
  if (!rec || rec.status !== "completed") return;
  try {
    const data = await api("recordings/" + rec.id + "/transcript");
    if (reading !== rec) return;
    const groups = data.paragraphs;
    const label = transcriptStates[data.status];
    readerState = data.status;
    $("#transcript-status").textContent =
      data.status === "completed"
        ? groups.length
          ? label + " · " + groups.length + " 段 · " + groups.reduce((n, g) => n + g.length, 0) + " 句"
          : "转写完成，未识别到语音。"
        : data.status === "failed"
          ? "转写失败 · " + data.error
          : data.status === "running"
            ? data.processed
              ? "正在转写 · 已处理至 " + duration(data.processed)
              : "正在转写，可关闭窗口，稍后从资料库查看。"
            : label;
    $("#asr-progress").hidden = data.status !== "running";
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
      sentenceButtons = Array.from(document.querySelectorAll(".sentence"));
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
  }
}
$("#sentence-view").onclick = (event) => {
  const enabled = $("#transcript-body").classList.toggle("sentences");
  event.currentTarget.setAttribute("aria-pressed", String(enabled));
};
$("#copy-text").onclick = async () => {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(manuscript);
    } else {
      const field = document.createElement("textarea");
      field.value = manuscript;
      $("#reader").append(field);
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
audio.ontimeupdate = () => {
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
  reading = null;
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
};
async function operate(name, id) {
  const t = tasks.find((t) => t.id === id);
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
      $("#reader").close();
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
    audio.currentTime = Number(b.dataset.start);
    try {
      await audio.play();
    } catch (e) {
      $("#transcript-status").textContent = "播放失败 · " + e.message;
    }
    return;
  }
  if (b.id !== "btn-add" && !b.dataset.action) return;
  b.disabled = true;
  try {
    if (b.id === "btn-add") await editor();
    else await operate(b.dataset.action, Number(b.dataset.id));
  } catch (e) {
    if (reading) $("#transcript-status").textContent = e.message;
    else notify(e.message);
  } finally {
    b.disabled = false;
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
