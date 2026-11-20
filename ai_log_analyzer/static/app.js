const $ = (selector) => document.querySelector(selector);

const elements = {
  input: $("#logInput"),
  gutter: $("#lineGutter"),
  inputStats: $("#inputStats"),
  file: $("#fileInput"),
  dropZone: $("#dropZone"),
  sample: $("#sampleButton"),
  clear: $("#clearButton"),
  analyze: $("#analyzeButton"),
  aiToggle: $("#aiToggle"),
  aiHint: $("#aiHint"),
  codePicker: $("#codePicker"),
  codeProject: $("#codeProject"),
  empty: $("#emptyState"),
  loading: $("#loadingState"),
  loadingText: $("#loadingText"),
  results: $("#results"),
  toast: $("#toast"),
};

const sampleLog = `2026-11-20 14:32:08.441 INFO  [payment-api] [traceId=7d82a39f] Request POST /api/orders/confirm
2026-11-20 14:32:08.502 DEBUG [payment-api] [traceId=7d82a39f] Loading order orderId=PO202611200031
2026-11-20 14:32:08.644 WARN  [payment-api] [traceId=7d82a39f] inventory-service response time=2100ms
2026-11-20 14:32:11.651 ERROR [payment-api] [traceId=7d82a39f] Payment confirmation failed
java.net.SocketTimeoutException: Read timed out
    at java.base/sun.nio.ch.NioSocketImpl.timedRead(NioSocketImpl.java:288)
    at okhttp3.internal.http2.Http2Stream$StreamTimeout.newTimeoutException(Http2Stream.kt:675)
    at com.acme.payment.client.InventoryClient.reserve(InventoryClient.java:87)
    at com.acme.payment.service.OrderService.confirm(OrderService.java:214)
    at com.acme.payment.controller.OrderController.confirm(OrderController.java:96)
Caused by: java.util.concurrent.TimeoutException: inventory-service deadline exceeded after 3000ms
2026-11-20 14:32:11.655 ERROR [payment-api] [traceId=7d82a39f] POST /api/orders/confirm status=500 duration=3214ms`;

let lastReport = null;
let toastTimer = null;

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function updateInputStats() {
  const text = elements.input.value;
  const lines = text ? text.split("\n").length : 0;
  const bytes = new Blob([text]).size;
  elements.inputStats.textContent = `${lines} 行 · ${formatBytes(bytes)}`;
  const visibleLines = Math.min(Math.max(lines, 1), 300);
  elements.gutter.textContent = Array.from({ length: visibleLines }, (_, i) => i + 1).join("\n");
}

function showToast(message, error = false) {
  clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.className = `toast show${error ? " error" : ""}`;
  toastTimer = setTimeout(() => elements.toast.className = "toast", 2600);
}

function setLoading(loading) {
  elements.analyze.disabled = loading;
  elements.analyze.querySelector("span").textContent = loading ? "分析中…" : "开始分析";
  elements.empty.classList.toggle("hidden", loading);
  elements.loading.classList.toggle("hidden", !loading);
  if (loading) elements.results.classList.add("hidden");
}

function escapeHtml(value = "") {
  const node = document.createElement("div");
  node.textContent = String(value);
  return node.innerHTML;
}

function severityMeta(severity) {
  return {
    critical: { label: "严重", className: "", symbol: "!!" },
    high: { label: "高风险", className: "", symbol: "!" },
    medium: { label: "中风险", className: "medium", symbol: "!" },
    low: { label: "低风险", className: "low", symbol: "✓" },
  }[severity] || { label: "待确认", className: "medium", symbol: "?" };
}

function renderMetrics(report) {
  const stats = report.stats || {};
  const levelCounts = stats.levels || {};
  const errors = (levelCounts.ERROR || 0) + (levelCounts.FATAL || 0);
  const timeRange = stats.time_range;
  const exceptionCount = (report.exceptions || []).reduce((sum, item) => sum + item.count, 0);
  const values = [
    ["日志行数", stats.lines ?? 0],
    ["错误记录", errors],
    ["异常命中", exceptionCount],
    ["已脱敏项", stats.redacted_items ?? 0],
  ];
  if (timeRange && timeRange.start !== timeRange.end) values[3] = ["时间跨度", `${timeRange.start.slice(11, 19)} — ${timeRange.end.slice(11, 19)}`];
  $("#metrics").innerHTML = values.map(([label, value]) => `<div class="metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("");
}

function renderAI(report) {
  const card = $("#aiCard");
  const content = $("#aiContent");
  const references = $("#codeReferences");
  if (!report.ai_analysis && !report.ai_error) {
    card.classList.add("hidden");
    return;
  }
  card.classList.remove("hidden");
  if (report.code_context) {
    const context = report.code_context;
    const files = (context.files || []).map(item => `<span>${escapeHtml(item.path)}:${escapeHtml(item.matched_line || `${item.start_line}-${item.end_line}`)}</span>`).join("");
    const trace = (context.trace || []).map(item => `${escapeHtml(item.step)}. ${escapeHtml(item.tool)}${item.reason ? ` — ${escapeHtml(item.reason)}` : ""}`).join("<br>");
    references.classList.remove("hidden");
    references.innerHTML = `<strong>智能代码调查：${escapeHtml(context.project.name)}</strong> · ${escapeHtml(context.stats.rounds)} 轮 · ${escapeHtml(context.stats.tool_calls)} 次只读工具调用 · 引用 ${escapeHtml(context.stats.matched_files)} 个文件
      <div class="code-reference-list">${files || "调查未引用具体源码文件"}</div>
      ${trace ? `<details class="investigation-trace"><summary>查看调查轨迹</summary><div>${trace}</div></details>` : ""}`;
  } else {
    references.classList.add("hidden");
    references.innerHTML = "";
  }
  if (report.ai_error) {
    content.innerHTML = `<div class="ai-error">AI 深度分析未完成：${escapeHtml(report.ai_error)}。本地分析结果不受影响。</div>`;
    return;
  }
  const ai = report.ai_analysis;
  const reasoning = (ai.reasoning || []).map(item => `<li>${escapeHtml(item)}</li>`).join("");
  const actions = (ai.actions || []).map(item => `<li><strong>${escapeHtml(item.title || "操作")}</strong>：${escapeHtml(item.detail || "")}</li>`).join("");
  const verification = (ai.verification || []).map(item => `<li>${escapeHtml(item)}</li>`).join("");
  const risks = (ai.risk_notes || []).map(item => `<li>${escapeHtml(item)}</li>`).join("");
  content.innerHTML = `<div class="ai-content-grid">
    <div>
      <div class="ai-block"><h4>${escapeHtml(ai.summary || "AI 分析结论")}</h4><p>${escapeHtml(ai.root_cause || "")}</p></div>
      ${reasoning ? `<div class="ai-block"><h4>证据链</h4><ul>${reasoning}</ul></div>` : ""}
    </div>
    <div>
      ${actions ? `<div class="ai-block"><h4>具体操作</h4><ul>${actions}</ul></div>` : ""}
      ${verification ? `<div class="ai-block"><h4>验证方式</h4><ul>${verification}</ul></div>` : ""}
      ${risks ? `<div class="ai-block"><h4>风险与不确定性</h4><ul>${risks}</ul></div>` : ""}
    </div>
  </div>`;
}

function renderReport(report) {
  lastReport = report;
  const meta = severityMeta(report.severity);
  const orb = $("#severityOrb");
  const badge = $("#severityBadge");
  orb.className = `severity-orb ${meta.className}`;
  orb.querySelector("span").textContent = meta.symbol;
  badge.className = `severity-badge ${meta.className}`;
  badge.textContent = meta.label;
  const modeLabels = {
    "ai+investigation+local": `AI 智能代码调查 · ${report.ai_analysis?.model || "模型"}`,
    "ai+code+local": `AI + 代码关联 · ${report.ai_analysis?.model || "模型"}`,
    "ai+local": `AI + 本地分析 · ${report.ai_analysis?.model || "模型"}`,
    "local": "本地规则分析",
  };
  $("#modeBadge").textContent = modeLabels[report.analysis_mode] || "本地规则分析";
  $("#confidenceLabel").textContent = `置信度 ${report.confidence}%`;
  $("#summaryTitle").textContent = report.likely_causes?.[0]?.title || "分析结论";
  $("#summaryText").textContent = report.summary;

  renderMetrics(report);
  $("#causesList").innerHTML = (report.likely_causes || []).map(item => `
    <div class="cause-item">
      <div class="cause-top"><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.confidence)}% · ${escapeHtml(item.category)}</span></div>
      <p>${escapeHtml(item.explanation)}</p>
      <div class="evidence-quote">${escapeHtml(item.evidence)}</div>
    </div>`).join("");

  $("#actionList").innerHTML = (report.actions || []).map(item => `<li>${escapeHtml(item.title)}</li>`).join("");
  const evidence = report.evidence || [];
  $("#evidenceList").innerHTML = evidence.length ? evidence.map(item => `<div class="log-line"><span class="number">${item.line}</span><span class="code">${escapeHtml(item.text)}</span></div>`).join("") : '<p class="empty-evidence">没有提取到明确的错误行，请补充错误上下文。</p>';
  renderAI(report);
  elements.loading.classList.add("hidden");
  elements.empty.classList.remove("hidden");
  elements.results.classList.remove("hidden");
  elements.results.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function analyze() {
  const log = elements.input.value.trim();
  if (!log) {
    showToast("请先粘贴或上传日志", true);
    elements.input.focus();
    return;
  }
  if (new Blob([log]).size > 1_000_000) {
    showToast("日志超过 1 MB，请截取关键片段", true);
    return;
  }
  setLoading(true);
  const useCode = elements.aiToggle.checked && Boolean(elements.codeProject.value);
  elements.loadingText.textContent = useCode ? "AI 正在多轮调查源码、调用链与配置…" : (elements.aiToggle.checked ? "本地提取完成后将请求 AI 深度分析…" : "提取异常与关键堆栈…");
  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        log,
        use_ai: elements.aiToggle.checked,
        code_project_id: useCode ? elements.codeProject.value : null,
      }),
    });
    const data = await response.json().catch(() => ({ error: "服务响应格式异常" }));
    if (!response.ok) throw new Error(data.error || `分析失败 (${response.status})`);
    renderReport(data);
    if (data.ai_error) showToast("本地分析已完成，AI 分析未成功", true);
  } catch (error) {
    elements.loading.classList.add("hidden");
    elements.empty.classList.remove("hidden");
    showToast(error.message || "分析失败，请检查服务状态", true);
  } finally {
    elements.analyze.disabled = false;
    elements.analyze.querySelector("span").textContent = "开始分析";
  }
}

function reportAsMarkdown(report) {
  const causes = (report.likely_causes || []).map((item, index) => `${index + 1}. **${item.title}**（置信度 ${item.confidence}%）\n   - ${item.explanation}\n   - 证据：${item.evidence}`).join("\n");
  const actions = (report.actions || []).map((item, index) => `${index + 1}. ${item.title}`).join("\n");
  const evidence = (report.evidence || []).map(item => `- L${item.line}: \`${item.text.replace(/`/g, "'")}\``).join("\n");
  let ai = "";
  if (report.ai_analysis) {
    const item = report.ai_analysis;
    ai = `\n## AI 深度分析\n\n${item.summary || ""}\n\n${item.root_cause || ""}\n`;
  }
  const code = report.code_context ? `\n## 关联代码\n\n${report.code_context.files.map(item => `- ${item.path}:${item.matched_line || item.start_line}`).join("\n")}\n` : "";
  return `# 日志分析报告\n\n- 严重程度：${severityMeta(report.severity).label}\n- 置信度：${report.confidence}%\n- 分析方式：${report.analysis_mode}\n\n## 结论\n\n${report.summary}\n\n## 可能原因\n\n${causes}\n\n## 建议操作\n\n${actions}${ai}${code}\n## 关键日志\n\n${evidence}\n`;
}

async function readFile(file) {
  if (!file) return;
  if (file.size > 1_000_000) {
    showToast("文件超过 1 MB，请先截取关键片段", true);
    return;
  }
  try {
    elements.input.value = await file.text();
    updateInputStats();
    showToast(`已载入 ${file.name}`);
  } catch (_) {
    showToast("文件读取失败，请选择文本日志", true);
  }
}

elements.input.addEventListener("input", updateInputStats);
elements.input.addEventListener("scroll", () => { elements.gutter.scrollTop = elements.input.scrollTop; });
elements.input.addEventListener("keydown", event => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") analyze();
  if (event.key === "Tab") {
    event.preventDefault();
    const start = elements.input.selectionStart;
    elements.input.setRangeText("  ", start, elements.input.selectionEnd, "end");
    updateInputStats();
  }
});
elements.file.addEventListener("change", event => readFile(event.target.files[0]));
elements.sample.addEventListener("click", () => { elements.input.value = sampleLog; updateInputStats(); showToast("示例日志已载入"); });
elements.clear.addEventListener("click", () => { elements.input.value = ""; updateInputStats(); elements.results.classList.add("hidden"); elements.input.focus(); });
elements.analyze.addEventListener("click", analyze);
elements.aiToggle.addEventListener("change", () => {
  elements.codeProject.disabled = !elements.aiToggle.checked;
  if (!elements.aiToggle.checked) elements.codeProject.value = "";
});

for (const eventName of ["dragenter", "dragover"]) {
  elements.dropZone.addEventListener(eventName, event => { event.preventDefault(); elements.dropZone.classList.add("dragging"); });
}
for (const eventName of ["dragleave", "drop"]) {
  elements.dropZone.addEventListener(eventName, event => { event.preventDefault(); elements.dropZone.classList.remove("dragging"); });
}
elements.dropZone.addEventListener("drop", event => readFile(event.dataTransfer.files[0]));

$("#copyButton").addEventListener("click", async () => {
  if (!lastReport) return;
  try {
    await navigator.clipboard.writeText(reportAsMarkdown(lastReport));
    showToast("Markdown 报告已复制");
  } catch (_) {
    showToast("复制失败，请检查浏览器权限", true);
  }
});

$("#themeButton").addEventListener("click", () => {
  const isDark = document.documentElement.dataset.theme === "dark";
  document.documentElement.dataset.theme = isDark ? "light" : "dark";
  localStorage.setItem("tracelens-theme", isDark ? "light" : "dark");
});

async function initialize() {
  const savedTheme = localStorage.getItem("tracelens-theme");
  if (savedTheme) document.documentElement.dataset.theme = savedTheme;
  updateInputStats();
  try {
    const response = await fetch("/api/status");
    const status = await response.json();
    elements.aiToggle.disabled = !status.ai_configured;
    elements.aiHint.textContent = status.ai_configured ? `使用 ${status.model}` : "配置 API Key 后可用";
    const projectsResponse = await fetch("/api/code-projects");
    const projectsStatus = await projectsResponse.json();
    if (projectsStatus.enabled) {
      elements.codePicker.classList.remove("hidden");
      elements.codeProject.innerHTML = '<option value="">不读取代码</option>' + projectsStatus.projects.map(project => `<option value="${escapeHtml(project.id)}">${escapeHtml(project.name)}</option>`).join("");
      elements.codeProject.disabled = !elements.aiToggle.checked;
    }
  } catch (_) {
    elements.aiToggle.disabled = true;
    elements.aiHint.textContent = "服务状态不可用";
  }
}

initialize();

