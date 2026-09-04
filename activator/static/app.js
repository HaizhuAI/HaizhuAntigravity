const queue = [];
let lastStatus = {};

function $(id) { return document.getElementById(id); }
function show(id, on) { $(id).classList.toggle("hidden", !on); }
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function api(path, opts) {
  const r = await fetch(path, Object.assign({ credentials: "same-origin" }, opts || {}));
  const j = await r.json().catch(() => ({ ok: false, error: "bad json" }));
  if (r.status === 401) throw Object.assign(new Error("unauthorized"), { code: 401, body: j });
  return j;
}

async function boot() {
  const s = await api("/api/auth/status");
  if (s.need_setup) {
    $("gateTitle").textContent = "设置管理员密码";
    $("gateHint").textContent = "第一次使用先设管理员密码，之后都靠它进控制台。至少 6 位。";
    show("setupExtra", true);
    show("loginExtra", false);
    show("gate", true);
    show("app", false);
    $("setupPassword").focus();
    return;
  }
  if (!s.authenticated) {
    $("gateTitle").textContent = "管理员登录";
    $("gateHint").textContent = "输入管理员密码进入激活台。";
    show("setupExtra", false);
    show("loginExtra", true);
    show("gate", true);
    show("app", false);
    $("loginPassword").focus();
    return;
  }
  show("gate", false);
  show("app", true);
  $("email").focus();
  tick();
}

async function submitGate(event) {
  if (event) event.preventDefault();
  $("gateErr").textContent = "";
  try {
    const s = await api("/api/auth/status");
    let j;
    if (s.need_setup) {
      j = await api("/api/auth/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          password: $("setupPassword").value,
          confirm: $("setupConfirm").value,
        }),
      });
    } else {
      j = await api("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: $("loginPassword").value }),
      });
    }
    if (!j.ok) { $("gateErr").textContent = j.error || "失败"; return; }
    await boot();
  } catch (e) {
    $("gateErr").textContent = (e.body && e.body.error) ? e.body.error : e.message;
  }
}

async function logout() {
  await api("/api/auth/logout", { method: "POST" });
  location.reload();
}

function addAccount(fromActivate) {
  $("formErr").textContent = "";
  const email = $("email").value.trim();
  const password = $("password").value;
  const totp = $("totp").value.trim();
  const proxy = $("proxy").value.trim();
  if (!email || !password) {
    if (!fromActivate) $("formErr").textContent = "邮箱和密码必填";
    return false;
  }
  if (queue.some(x => x.email.toLowerCase() === email.toLowerCase())) {
    $("formErr").textContent = "队列里已经有这个邮箱";
    return false;
  }
  queue.push({ email, password, totp, proxy });
  $("email").value = "";
  $("password").value = "";
  $("totp").value = "";
  renderQueue();
  return true;
}

function removeAccount(i) {
  queue.splice(i, 1);
  renderQueue();
}

function clearQueue() {
  queue.splice(0, queue.length);
  renderQueue();
}

function resultOf(email) {
  return (lastStatus.results || []).find(x => (x.email || "").toLowerCase() === email.toLowerCase());
}

function renderQueue() {
  const tb = $("rows");
  if (!queue.length) {
    tb.innerHTML = '<tr><td class="empty" colspan="5">队列是空的。填完可以直接一键激活当前这一条，或先加入队列再批量跑。</td></tr>';
    return;
  }
  tb.innerHTML = queue.map((x, i) => {
    const r = resultOf(x.email);
    const st = r ? r.status : (lastStatus.running && lastStatus.current === x.email ? "running" : "queued");
    const msg = r ? (r.message || "") : "";
    return `<tr>
      <td>${escapeHtml(x.email)}</td>
      <td>${x.totp ? "有" : "无"}</td>
      <td>${escapeHtml(x.proxy || "-")}</td>
      <td class="${st}">${st}${msg ? " / " + escapeHtml(msg) : ""}</td>
      <td><button class="btn-ghost" type="button" onclick="removeAccount(${i})">删除</button></td>
    </tr>`;
  }).join("");
}

async function activateNow() {
  $("formErr").textContent = "";
  if ($("email").value.trim() && $("password").value) addAccount(true);
  if (!queue.length) {
    $("formErr").textContent = "先填一条账号，或加入队列";
    return;
  }
  $("igniteBtn").disabled = true;
  const j = await api("/api/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      accounts: queue,
      headed: true,
      channel: $("channel").value,
      timeout: Number($("timeout").value || 180),
      resume: false,
    }),
  }).catch(e => e.body || { ok: false, error: e.message });
  if (!j.ok) {
    $("formErr").textContent = j.error || "启动失败";
    $("igniteBtn").disabled = false;
  }
}

async function stopJob() {
  await api("/api/stop", { method: "POST" });
}

function applyStatus(j) {
  lastStatus = j;
  const running = !!j.running;
  $("statusPill").classList.toggle("running", running);
  $("statusText").textContent = running ? ("running" + (j.current ? " · " + j.current : "")) : "idle";
  $("meta").textContent = `队列 ${queue.length} 条，已完成 ${(j.results || []).length} 条` + (j.current ? `，正在处理 ${j.current}` : "");
  $("igniteBtn").disabled = running;
  $("stopBtn").disabled = !running;
  const logs = j.logs || [];
  $("logs").textContent = logs.length ? logs.join("\n") : "等待任务...";
  $("logs").scrollTop = 99999;
  renderQueue();
}

async function tick() {
  if ($("app").classList.contains("hidden")) return;
  try {
    applyStatus(await api("/api/status"));
  } catch (e) {
    if (e.code === 401) boot();
  }
}

window.submitGate = submitGate;
window.logout = logout;
window.addAccount = addAccount;
window.removeAccount = removeAccount;
window.clearQueue = clearQueue;
window.activateNow = activateNow;
window.stopJob = stopJob;

$("email").addEventListener("keydown", e => { if (e.key === "Enter") addAccount(); });
setInterval(tick, 800);
boot();
