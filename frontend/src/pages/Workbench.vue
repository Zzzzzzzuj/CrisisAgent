<script setup>
import { computed, onMounted, ref } from "vue";

import {
  archiveEvent,
  createEventFromIngestionRun,
  createSource,
  getDashboardOverview,
  getDashboardReviewQueue,
  getDashboardSeverity,
  getDashboardSourceHealth,
  getDashboardTrends,
  getEvalOverview,
  getEvalRegression,
  getEvalRun,
  getEvent,
  getEventReport,
  getEventReview,
  getEventRun,
  getEventTrace,
  getIngestionRun,
  listIngestionWorkers,
  listEvents,
  listEvalRuns,
  listIngestionRuns,
  listSources,
  runEventAgent,
  runEval,
  runIngestion,
  testSource,
  updateSource,
  setWorkspaceDemoUser,
  listAuditLogs,
} from "../api";

const sources = ref([]);
const runs = ref([]);
const events = ref([]);
const selectedRun = ref(null);
const selectedEvent = ref(null);
const eventRun = ref(null);
const eventTrace = ref(null);
const eventReview = ref(null);
const report = ref(null);
const liveFetchOpen = ref(false);
const liveFetchConfirmation = ref("");
const backgroundIngestion = ref(false);
const ingestionWorkers = ref([]);
const loading = ref(false);
const action = ref("");
const error = ref("");
const sourceTestResults = ref({});
const dashboardOverview = ref(null);
const dashboardSeverity = ref(null);
const dashboardTrends = ref([]);
const dashboardSourceHealth = ref([]);
const dashboardReviewQueue = ref([]);
const evalOverview = ref(null);
const evalRegression = ref(null);
const evalRuns = ref([]);
const selectedEvalRun = ref(null);
const auditLogs = ref([]);
const auditLoading = ref(false);
const auditError = ref("");
const workspaceUser = ref({ id: "demo-system", role: "admin" });
const isViewer = computed(() => workspaceUser.value.role === "viewer");
const isSourceManager = computed(() => workspaceUser.value.role === "admin");
const canOperate = computed(() => ["admin", "operator"].includes(workspaceUser.value.role));

const sourceForm = ref({
  source_id: "",
  source_name: "",
  source_type: "rss",
  url: "https://",
  company_keywords: "",
  risk_keywords: "投诉,监管,召回",
});

const eventSummary = computed(() => selectedEvent.value?.event_summary || "暂无事件摘要");
const traceItems = computed(() => eventTrace.value?.trace || []);
const hasReport = computed(() => Boolean(report.value?.markdown_content));
const goldenCaseFailures = computed(() => (
  selectedEvalRun.value?.failed_items?.filter((item) => item.dimension === "golden_case") || []
));
const sourceFailureRate = computed(() => {
  const totals = dashboardSourceHealth.value.reduce(
    (result, source) => {
      result.attempted += source.collected_count + source.no_match_count + source.failed_count + source.skipped_by_robots_count;
      result.failed += source.failed_count + source.skipped_by_robots_count;
      return result;
    },
    { attempted: 0, failed: 0 },
  );
  return totals.attempted ? `${Math.round((totals.failed / totals.attempted) * 100)}%` : "0%";
});
const trendMax = computed(() => Math.max(1, ...dashboardTrends.value.map((item) => item.total)));

onMounted(loadAll);

async function changeWorkspaceRole() {
  setWorkspaceDemoUser(workspaceUser.value);
  await loadAll();
}

async function loadAll() {
  loading.value = true;
  error.value = "";
  try {
    await Promise.all([loadSources(), loadRuns(), loadEvents(), loadDashboard(), loadEvalCenter()]);
    if (workspaceUser.value.role === "admin") await loadAuditLogs();
    else auditLogs.value = [];
  } catch (err) {
    showError(err);
  } finally {
    loading.value = false;
  }
}

async function loadAuditLogs() {
  auditLoading.value = true;
  auditError.value = "";
  try {
    auditLogs.value = (await listAuditLogs({ limit: 50 })).logs || [];
  } catch (err) {
    auditError.value = err.response?.data?.detail || "审计日志加载失败";
  } finally {
    auditLoading.value = false;
  }
}

async function loadSources() {
  const data = await listSources();
  sources.value = data.sources || [];
}

async function loadRuns() {
  const data = await listIngestionRuns();
  runs.value = data.runs || [];
}

async function loadEvents() {
  const data = await listEvents();
  events.value = data.events || [];
}

async function loadDashboard() {
  const [overview, severity, trends, sourceHealth, reviewQueue] = await Promise.all([
    getDashboardOverview(),
    getDashboardSeverity(),
    getDashboardTrends(),
    getDashboardSourceHealth(),
    getDashboardReviewQueue(),
  ]);
  dashboardOverview.value = overview;
  dashboardSeverity.value = severity;
  dashboardTrends.value = trends.buckets || [];
  dashboardSourceHealth.value = sourceHealth.sources || [];
  dashboardReviewQueue.value = reviewQueue.events || [];
}

async function loadEvalCenter() {
  const [overview, regression, runsResponse] = await Promise.all([
    getEvalOverview(),
    getEvalRegression(),
    listEvalRuns(),
  ]);
  evalOverview.value = overview;
  evalRegression.value = regression;
  evalRuns.value = runsResponse.runs || [];
  if (!selectedEvalRun.value && runsResponse.runs?.[0]) {
    selectedEvalRun.value = await getEvalRun(runsResponse.runs[0].eval_run_id);
  }
}

async function runOfflineEval() {
  action.value = "eval";
  error.value = "";
  try {
    selectedEvalRun.value = await runEval({});
    await loadEvalCenter();
  } catch (err) {
    showError(err);
  } finally {
    action.value = "";
  }
}

async function inspectEvalRun(run) {
  try {
    selectedEvalRun.value = await getEvalRun(run.eval_run_id);
  } catch (err) {
    showError(err);
  }
}

async function submitSource() {
  action.value = "source";
  error.value = "";
  try {
    await createSource({
      ...sourceForm.value,
      enabled: false,
      company_keywords: splitKeywords(sourceForm.value.company_keywords),
      risk_keywords: splitKeywords(sourceForm.value.risk_keywords),
      respect_robots: true,
      rate_limit_seconds: 3,
      timeout_seconds: 10,
      max_items: 5,
    });
    sourceForm.value.source_id = "";
    sourceForm.value.source_name = "";
    sourceForm.value.url = "https://";
    sourceForm.value.company_keywords = "";
    await loadSources();
  } catch (err) {
    showError(err);
  } finally {
    action.value = "";
  }
}

async function toggleSource(source) {
  try {
    const updated = await updateSource(source.source_id, { enabled: !source.enabled });
    Object.assign(source, updated);
  } catch (err) {
    showError(err);
  }
}

async function checkSource(source) {
  try {
    sourceTestResults.value[source.source_id] = await testSource(source.source_id);
  } catch (err) {
    showError(err);
  }
}

async function startIngestion(dryRun) {
  action.value = dryRun ? "dry-run" : "ingestion";
  error.value = "";
  try {
    const result = await runIngestion({ live_fetch: false, dry_run: dryRun, background: dryRun ? false : backgroundIngestion.value });
    selectedRun.value = result;
    await Promise.all([loadRuns(), loadDashboard()]);
  } catch (err) {
    showError(err);
  } finally {
    action.value = "";
  }
}

async function startLiveIngestion() {
  action.value = "live-ingestion";
  error.value = "";
  try {
    const result = await runIngestion({ live_fetch: true, dry_run: false, background: backgroundIngestion.value });
    selectedRun.value = result;
    await Promise.all([loadRuns(), loadDashboard()]);
  } catch (err) {
    if (err.response?.status === 403) {
      error.value = "后端未开启 ENABLE_API_LIVE_FETCH=true，本次没有联网。";
    } else {
      showError(err);
    }
  } finally {
    action.value = "";
  }
}

async function inspectRun(run) {
  try {
    selectedRun.value = await fetchRun(run.run_id);
  } catch (err) {
    showError(err);
  }
}

async function refreshSelectedRun() {
  if (!selectedRun.value?.run_id) return;
  action.value = "refresh-run";
  try {
    selectedRun.value = await fetchRun(selectedRun.value.run_id);
    await Promise.all([loadRuns(), loadDashboard()]);
  } catch (err) {
    showError(err);
  } finally {
    action.value = "";
  }
}

async function refreshIngestionWorkers() {
  try {
    ingestionWorkers.value = (await listIngestionWorkers()).workers || [];
  } catch (err) {
    showError(err);
  }
}

async function fetchRun(runId) {
  return getIngestionRun(runId);
}

async function createEvent(cluster) {
  if (!selectedRun.value?.run_id) return;
  action.value = "event";
  try {
    await createEventFromIngestionRun({
      run_id: selectedRun.value.run_id,
      cluster_id: cluster.cluster_id,
    });
    await Promise.all([loadEvents(), loadDashboard()]);
  } catch (err) {
    showError(err);
  } finally {
    action.value = "";
  }
}

async function inspectEvent(event) {
  error.value = "";
  report.value = null;
  eventRun.value = null;
  eventTrace.value = null;
  eventReview.value = null;
  try {
    selectedEvent.value = await getEvent(event.event_id);
    await refreshEventArtifacts();
  } catch (err) {
    showError(err);
  }
}

async function refreshEventArtifacts() {
  if (!selectedEvent.value) return;
  const eventId = selectedEvent.value.event_id;
  try {
    eventRun.value = await getEventRun(eventId);
    eventTrace.value = await getEventTrace(eventId);
    eventReview.value = await getEventReview(eventId);
  } catch {
    eventRun.value = null;
    eventTrace.value = null;
    eventReview.value = null;
  }
}

async function runAgent() {
  if (!selectedEvent.value) return;
  action.value = "agent";
  error.value = "";
  try {
    eventRun.value = await runEventAgent(selectedEvent.value.event_id, {
      mode: "mock",
      runtime_mode: "sync",
      force_rerun: false,
    });
    await Promise.all([loadEvents(), loadDashboard()]);
    selectedEvent.value = await getEvent(selectedEvent.value.event_id);
    eventTrace.value = await getEventTrace(selectedEvent.value.event_id);
    eventReview.value = await getEventReview(selectedEvent.value.event_id);
  } catch (err) {
    showError(err);
  } finally {
    action.value = "";
  }
}

async function archiveSelectedEvent() {
  if (!selectedEvent.value) return;
  try {
    selectedEvent.value = await archiveEvent(selectedEvent.value.event_id);
    await Promise.all([loadEvents(), loadDashboard()]);
  } catch (err) {
    showError(err);
  }
}

async function loadMarkdownReport() {
  if (!selectedEvent.value) return;
  try {
    report.value = await getEventReport(selectedEvent.value.event_id, "markdown");
  } catch (err) {
    showError(err);
  }
}

function splitKeywords(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function showError(err) {
  error.value = err.response?.data?.detail || err.message || "请求失败，请检查后端服务。";
}

function statusText(value) {
  const map = {
    completed: "已完成",
    waiting_human: "待人工审核",
    queued: "已入队",
    partial: "部分完成",
    running: "运行中",
    failed: "失败",
    archived: "已归档",
    new: "新事件",
    ready_for_agent: "待运行 Agent",
  };
  return map[value] || value || "未知";
}

function compactOutput(value) {
  if (!value) return "暂无输出摘要";
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.length > 220 ? `${text.slice(0, 220)}...` : text;
}
</script>

<template>
  <section class="workbench-page">
    <header class="product-hero compact-hero">
      <div>
        <p class="eyebrow">Operations Workbench</p>
        <h2>从舆情来源到危机报告</h2>
        <p class="muted">当前工作台默认使用离线配置和 mock Agent，不会自动开启 live-fetch 或发布声明。</p>
      </div>
      <div class="button-line"><label class="muted tiny-text">演示角色 <select v-model="workspaceUser.role" @change="changeWorkspaceRole"><option value="admin">admin</option><option value="operator">operator</option><option value="legal_reviewer">legal_reviewer</option><option value="viewer">viewer</option></select><small>当前为 MVP 演示角色模拟，不是生产登录系统。</small></label><button class="ghost-button" :disabled="loading" @click="loadAll">刷新全部</button></div>
    </header>

    <p v-if="error" class="error workbench-error">{{ error }}</p>
    <p v-if="loading" class="muted">正在加载工作台数据...</p>

    <article v-if="workspaceUser.role === 'admin'" class="page-card workbench-card audit-card">
      <div class="section-heading"><div><p class="eyebrow">P12 Workspace Security</p><h3>Audit Log 审计日志</h3></div><button class="ghost-button" :disabled="auditLoading" @click="loadAuditLogs">{{ auditLoading ? '加载中...' : '刷新审计日志' }}</button></div>
      <p v-if="auditError" class="error">{{ auditError }}</p>
      <div v-else-if="auditLogs.length" class="audit-list">
        <div v-for="item in auditLogs" :key="item.audit_id" class="audit-row"><small>{{ item.timestamp }}</small><strong>{{ item.actor_id }} · {{ item.actor_role }}</strong><span>{{ item.action }}</span><span>{{ item.resource_type }} / {{ item.resource_id || '-' }}</span><span :class="['status-pill', item.result === 'denied' ? 'status-off' : 'status-on']">{{ item.result }}</span><small>{{ item.reason || '-' }}</small></div>
      </div>
      <p v-else class="empty-inline">暂无审计记录。</p>
    </article>
    <p v-else class="muted tiny-text">当前角色无权查看审计日志。</p>

    <article class="page-card workbench-card crisis-radar">
      <div class="section-heading">
        <div>
          <p class="eyebrow">P8 Crisis Radar</p>
          <h3>危机态势总览</h3>
        </div>
        <span class="status-pill">规则评分 · automatic_publish=false</span>
      </div>
      <div v-if="dashboardOverview" class="radar-metrics">
        <div class="radar-metric"><span>总事件数</span><strong>{{ dashboardOverview.total_events }}</strong></div>
        <div class="radar-metric sev-one"><span>SEV-1</span><strong>{{ dashboardOverview.sev1_count }}</strong></div>
        <div class="radar-metric sev-two"><span>SEV-2</span><strong>{{ dashboardOverview.sev2_count }}</strong></div>
        <div class="radar-metric"><span>待审核</span><strong>{{ dashboardOverview.waiting_human_count }}</strong></div>
        <div class="radar-metric"><span>未核实</span><strong>{{ dashboardOverview.unverified_count }}</strong></div>
        <div class="radar-metric"><span>来源失败率</span><strong>{{ sourceFailureRate }}</strong></div>
      </div>
      <p v-else class="empty-inline">暂无事件数据，创建 CrisisEvent 后会显示危机态势。</p>

      <div class="radar-grid">
        <section>
          <h4>最高优先级事件</h4>
          <div v-if="dashboardOverview?.top_urgent_events?.length" class="radar-list">
            <button
              v-for="event in dashboardOverview.top_urgent_events"
              :key="event.event_id"
              class="radar-event"
              @click="inspectEvent(event)"
            >
              <span :class="['severity-badge', event.severity.toLowerCase()]">{{ event.severity }}</span>
              <span class="radar-event-main"><strong>{{ event.title }}</strong><small>{{ event.company || '未标注企业' }} · {{ event.urgency_score }} 分</small></span>
              <span class="radar-action">{{ event.recommended_action }}</span>
            </button>
          </div>
          <p v-else class="empty-inline">暂无活跃危机事件。</p>
        </section>
        <section>
          <h4>人工审核队列</h4>
          <div v-if="dashboardReviewQueue.length" class="radar-list">
            <button
              v-for="event in dashboardReviewQueue"
              :key="event.event_id"
              class="radar-event"
              @click="inspectEvent(event)"
            >
              <span :class="['severity-badge', event.severity.toLowerCase()]">{{ event.severity }}</span>
              <span class="radar-event-main"><strong>{{ event.title }}</strong><small>{{ event.priority_reasons.join('、') || '需要人工核查' }}</small></span>
            </button>
          </div>
          <p v-else class="empty-inline">当前没有待审核事件。</p>
        </section>
      </div>

      <div class="radar-grid lower-radar-grid">
        <section>
          <h4>来源健康状态</h4>
          <div v-if="dashboardSourceHealth.length" class="source-health-list">
            <div v-for="source in dashboardSourceHealth" :key="source.source_id" class="source-health-row">
              <strong>{{ source.source_id }}</strong>
              <span>{{ source.latest_status }}</span>
              <span>失败 {{ Math.round(source.failure_rate * 100) }}%</span>
              <small>采集 {{ source.collected_count }} · 无匹配 {{ source.no_match_count }} · 失败 {{ source.failed_count }} · robots 跳过 {{ source.skipped_by_robots_count }}</small>
            </div>
          </div>
          <p v-else class="empty-inline">暂无来源运行记录。</p>
        </section>
        <section>
          <h4>事件趋势</h4>
          <div v-if="dashboardTrends.length" class="trend-list">
            <div v-for="item in dashboardTrends" :key="item.bucket" class="trend-row">
              <span>{{ item.bucket }}</span>
              <div class="trend-track"><i :style="{ width: `${(item.total / trendMax) * 100}%` }"></i></div>
              <strong>{{ item.total }}</strong>
              <small>高风险 {{ item.high_risk }} · 待审核 {{ item.waiting_human }}</small>
            </div>
          </div>
          <p v-else class="empty-inline">暂无可聚合的事件趋势。</p>
        </section>
      </div>
    </article>

    <article class="page-card workbench-card eval-center">
      <div class="section-heading">
        <div>
          <p class="eyebrow">P9 Eval Center · P11 CI Gate</p>
          <h3>评估中心</h3>
        </div>
        <button class="primary-button" :disabled="Boolean(action)" @click="runOfflineEval">运行离线评估</button>
      </div>
      <p class="muted tiny-text">只读取已有 runtime store 与确定性规则：no_live_fetch · no_real_llm_call · automatic_publish=false。</p>
      <div v-if="evalOverview" class="eval-metrics">
        <div class="eval-metric"><span>最新通过率</span><strong>{{ evalOverview.latest_pass_rate == null ? "暂无" : `${Math.round(evalOverview.latest_pass_rate * 100)}%` }}</strong></div>
        <div class="eval-metric"><span>评估用例</span><strong>{{ evalOverview.total_cases }}</strong></div>
        <div class="eval-metric"><span>通过 / 失败</span><strong>{{ evalOverview.passed_cases }} / {{ evalOverview.failed_cases }}</strong></div>
        <div class="eval-metric"><span>历史 EvalRun</span><strong>{{ evalOverview.total_runs }}</strong></div>
        <div class="eval-metric"><span>Golden Cases</span><strong>{{ evalOverview.dimensions_summary?.golden_case == null ? "暂无" : `${Math.round(evalOverview.dimensions_summary.golden_case.pass_rate * 100)}%` }}</strong></div>
      </div>

      <div class="eval-grid">
        <section>
          <h4>维度汇总</h4>
          <div v-if="evalOverview && Object.keys(evalOverview.dimensions_summary || {}).length" class="eval-dimensions">
            <div v-for="(summary, name) in evalOverview.dimensions_summary" :key="name" class="eval-dimension-row">
              <strong>{{ name }}</strong>
              <span>{{ Math.round(summary.pass_rate * 100) }}%</span>
              <small>{{ summary.passed_cases }}/{{ summary.total_cases }} 通过</small>
            </div>
          </div>
          <p v-else class="empty-inline">尚未运行评估。</p>
          <p v-if="evalOverview?.top_failed_dimensions?.length" class="error tiny-text">失败维度：{{ evalOverview.top_failed_dimensions.join('、') }}</p>
        </section>
        <section>
          <h4>Regression 对比</h4>
          <div v-if="evalRegression && !evalRegression.not_enough_runs" class="regression-box">
            <strong>{{ Math.round((evalRegression.current_pass_rate || 0) * 100) }}%</strong>
            <span>相较上次 {{ evalRegression.delta >= 0 ? "+" : "" }}{{ Math.round((evalRegression.delta || 0) * 100) }}%</span>
            <small>新增失败：{{ evalRegression.newly_failed_cases?.join('、') || '无' }}</small>
            <small>恢复用例：{{ evalRegression.recovered_cases?.join('、') || '无' }}</small>
          </div>
          <p v-else class="empty-inline">至少运行两次评估后显示回归对比。</p>
        </section>
      </div>

      <div class="eval-grid lower-eval-grid">
        <section>
          <h4>失败项与 Golden Cases</h4>
          <div v-if="goldenCaseFailures.length" class="golden-failure-box">
            <strong>失败 Golden Cases</strong>
            <small>{{ goldenCaseFailures.map((item) => item.case_id).join('、') }}</small>
          </div>
          <div v-if="selectedEvalRun?.failed_items?.length" class="eval-failure-list">
            <div v-for="item in selectedEvalRun.failed_items" :key="item.case_id" class="eval-failure-row">
              <strong>{{ item.dimension }} · {{ item.name }}</strong>
              <p>{{ item.reason }}</p>
            </div>
          </div>
          <p v-else class="empty-inline">最新查看的 EvalRun 没有失败项。</p>
        </section>
        <section>
          <h4>Eval Run 历史</h4>
          <div v-if="evalRuns.length" class="eval-run-list">
            <button v-for="run in evalRuns" :key="run.eval_run_id" class="eval-run-row" @click="inspectEvalRun(run)">
              <span><strong>{{ run.status }}</strong><small>{{ run.eval_run_id }}</small></span>
              <span>{{ Math.round(run.pass_rate * 100) }}% · {{ run.passed_cases }}/{{ run.total_cases }}</span>
            </button>
          </div>
          <p v-else class="empty-inline">暂无持久化 EvalRun。</p>
        </section>
      </div>
    </article>

    <article class="page-card workbench-card">
      <div class="section-heading">
        <div><p class="eyebrow">P1 Source Registry</p><h3>数据源管理</h3></div>
        <span class="status-pill">live-fetch 默认关闭</span>
      </div>
      <form v-if="isSourceManager" class="workbench-form" @submit.prevent="submitSource">
        <input v-model="sourceForm.source_id" placeholder="source_id" required />
        <input v-model="sourceForm.source_name" placeholder="来源名称" required />
        <select v-model="sourceForm.source_type"><option value="rss">rss</option><option value="article_url">article_url</option></select>
        <input v-model="sourceForm.url" placeholder="HTTPS URL" required />
        <input v-model="sourceForm.company_keywords" placeholder="公司关键词，用逗号分隔" />
        <input v-model="sourceForm.risk_keywords" placeholder="风险关键词，用逗号分隔" required />
        <button class="primary-button" :disabled="action === 'source'">新增安全来源</button>
      </form>
      <div v-if="sources.length" class="data-list">
        <div v-for="source in sources" :key="source.source_id" class="data-row">
          <div><strong>{{ source.source_name }}</strong><small>{{ source.source_id }} · {{ source.source_type }}</small></div>
          <span :class="['status-pill', source.enabled ? 'status-on' : 'status-off']">{{ source.enabled ? 'enabled' : 'disabled' }}</span>
          <button v-if="isSourceManager" class="ghost-button small-button" @click="toggleSource(source)">{{ source.enabled ? '禁用' : '启用' }}</button>
          <button v-if="isSourceManager || canOperate" class="ghost-button small-button" @click="checkSource(source)">配置检查</button>
          <span v-if="sourceTestResults[source.source_id]" class="muted tiny-text">
            {{ sourceTestResults[source.source_id].test_status }} · live_fetch={{ sourceTestResults[source.source_id].live_fetch_triggered }}
          </span>
        </div>
      </div>
      <p v-else class="empty-inline">暂无数据源，请先添加一个 HTTPS 白名单来源。</p>
    </article>

    <div class="workbench-columns">
      <article class="page-card workbench-card">
        <div class="section-heading"><div><p class="eyebrow">P2 Ingestion Run</p><h3>采集运行</h3></div></div>
        <div class="button-line">
          <button v-if="canOperate" class="primary-button" :disabled="Boolean(action)" @click="startIngestion(true)">运行 dry-run</button>
          <button v-if="canOperate" class="ghost-button" :disabled="Boolean(action)" @click="startIngestion(false)">运行离线采集</button>
        </div>
        <label v-if="canOperate" class="background-run-toggle"><input v-model="backgroundIngestion" type="checkbox" /> 后台运行（background=true，需要 Redis worker）</label>
        <p v-if="backgroundIngestion" class="muted tiny-text">提交后仅创建 queued 任务；请启动 Redis 和 ingestion worker，再手动刷新状态。Redis 不可用时后端会拒绝本次后台任务，不会降级为进程内执行。</p>
        <p class="muted tiny-text">手动联网采集默认折叠，只有完成确认后才允许提交。</p>
      <details v-if="canOperate"
        class="live-fetch-panel"
        :open="liveFetchOpen"
        @toggle="liveFetchOpen = $event.target.open"
      >
          <summary>高级：手动联网采集</summary>
          <div class="live-fetch-warning">
            <strong>联网采集风险提示</strong>
            <p>只会访问白名单且 enabled=true 的 source；需要后端开启 ENABLE_API_LIVE_FETCH=true。</p>
            <p>采集会遵守 robots、timeout、rate limit 和 max_items，不会自动发布声明。</p>
            <input v-model="liveFetchConfirmation" placeholder="输入：我确认手动联网采集" />
            <button
              class="danger-button"
              :disabled="liveFetchConfirmation !== '我确认手动联网采集' || Boolean(action)"
              @click="startLiveIngestion"
            >手动联网采集 enabled 来源</button>
          </div>
        </details>
        <div v-if="selectedRun" class="run-summary">
          <strong>{{ selectedRun.run_id }}</strong>
          <span>{{ statusText(selectedRun.status) }} · {{ selectedRun.execution_mode || 'sync' }}{{ selectedRun.queue_backend ? `/${selectedRun.queue_backend}` : '' }} · raw {{ selectedRun.raw_count }} · clusters {{ selectedRun.cluster_count }}</span>
          <span v-if="selectedRun.job_id">job_id：{{ selectedRun.job_id }}</span>
          <p v-if="selectedRun.error" class="error tiny-text">任务错误：{{ selectedRun.error }}</p>
          <p v-if="selectedRun.execution_mode === 'background'" class="muted tiny-text">重试 {{ selectedRun.retry_count || 0 }}/{{ selectedRun.max_retries ?? '-' }} · timeout {{ selectedRun.timeout_seconds ?? '-' }}s · worker {{ selectedRun.worker_id || '待分配' }}</p>
          <p v-if="selectedRun.last_error" class="error tiny-text">最近错误：{{ selectedRun.last_error }}{{ selectedRun.dead_lettered_at ? ` · dead letter: ${selectedRun.dead_lettered_at}` : '' }}</p>
          <button v-if="selectedRun.execution_mode === 'background'" class="ghost-button small-button" :disabled="action === 'refresh-run'" @click="refreshSelectedRun">刷新状态</button>
          <div v-if="selectedRun.source_results?.length" class="source-result-list">
            <span v-for="item in selectedRun.source_results" :key="item.source_id">
              {{ item.source_id }}: {{ item.status }}{{ item.failed_reason ? ` (${item.failed_reason})` : '' }}
            </span>
          </div>
        </div>
        <div v-if="canOperate" class="worker-panel"><div class="button-line"><strong>Worker 状态</strong><button class="ghost-button small-button" @click="refreshIngestionWorkers">刷新 Worker</button></div><p v-if="!ingestionWorkers.length" class="muted tiny-text">暂无 heartbeat。启动 Redis Worker 后会显示。</p><div v-for="worker in ingestionWorkers" :key="worker.worker_id" class="muted tiny-text">{{ worker.worker_id }} · {{ worker.queue_name }} · {{ worker.status }} · {{ worker.last_seen_at }}</div></div>
        <div v-if="runs.length" class="data-list compact-list">
          <div v-for="run in runs" :key="run.run_id" class="data-row clickable" @click="inspectRun(run)">
            <div><strong>{{ run.run_id }}</strong><small>{{ statusText(run.status) }} · {{ run.execution_mode || 'sync' }}{{ run.queue_backend ? `/${run.queue_backend}` : '' }} · {{ run.started_at || '尚未开始' }}</small></div>
            <span>clusters {{ run.cluster_count }}</span>
          </div>
        </div>
        <p v-else class="empty-inline">暂无采集记录。</p>
      </article>

      <article class="page-card workbench-card">
        <div class="section-heading"><div><p class="eyebrow">P3 CrisisEvent</p><h3>危机事件</h3></div></div>
        <div v-if="selectedRun?.clusters?.length" class="cluster-list">
          <div v-for="cluster in selectedRun.clusters" :key="cluster.cluster_id" class="cluster-row">
            <div><strong>{{ cluster.company || '未命名公司' }}</strong><p>{{ cluster.event }}</p></div>
            <button v-if="canOperate" class="ghost-button small-button" :disabled="action === 'event'" @click="createEvent(cluster)">沉淀为事件</button>
          </div>
        </div>
        <p v-else class="empty-inline">选择一条采集记录后，可将 cluster 沉淀为 CrisisEvent。</p>
        <div v-if="events.length" class="data-list compact-list">
          <div v-for="event in events" :key="event.event_id" class="data-row clickable" @click="inspectEvent(event)">
            <div><strong>{{ event.title }}</strong><small>{{ event.company }} · {{ event.fact_status }}</small></div>
            <span class="risk-badge">{{ event.risk_level }}</span>
            <span class="status-pill">{{ statusText(event.status) }}</span>
          </div>
        </div>
        <p v-else class="empty-inline">暂无 CrisisEvent。</p>
      </article>
    </div>

    <article v-if="selectedEvent" class="page-card workbench-card event-console">
      <div class="section-heading">
        <div><p class="eyebrow">P4 Event Console</p><h3>{{ selectedEvent.title }}</h3><p class="muted">{{ eventSummary }}</p></div>
        <div class="button-line">
          <button v-if="canOperate" class="primary-button" :disabled="Boolean(action) || selectedEvent.status === 'archived'" @click="runAgent">运行 Agent（mock）</button>
          <button v-if="canOperate" class="ghost-button" :disabled="selectedEvent.status === 'archived'" @click="archiveSelectedEvent">归档</button>
        </div>
      </div>
      <div class="facts-grid">
        <span>风险：{{ selectedEvent.risk_level }}</span><span>事实：{{ selectedEvent.fact_status }}</span><span>事件：{{ selectedEvent.event_status }}</span>
        <span>人工审核：{{ selectedEvent.human_review_required }}</span><span>来源：{{ selectedEvent.source_count }}</span><span>状态：{{ statusText(selectedEvent.status) }}</span>
      </div>
      <p class="muted tiny-text">来源：{{ selectedEvent.source_items?.join('、') || '暂无来源' }}</p>

      <div v-if="eventRun" class="run-result">
        <div class="facts-grid"><span>session_id：{{ eventRun.session_id }}</span><span>状态：{{ statusText(eventRun.status) }}</span><span>trace：{{ eventRun.trace_count }}</span><span>automatic_publish：{{ eventRun.automatic_publish }}</span></div>
        <p class="statement draft-statement">{{ eventRun.final_statement_preview || '暂无声明草稿' }}</p>
        <p>policy triggers：{{ eventRun.policy_triggers?.join('、') || '无' }}</p>
      </div>
      <p v-else class="empty-inline">尚未运行 Agent。</p>

      <div v-if="eventTrace" class="trace-block">
        <h4>Agent Trace</h4>
        <div v-for="(item, index) in traceItems" :key="`${item.agent}-${index}`" class="trace-row">
          <strong>{{ index + 1 }}. {{ item.agent }}</strong><span>{{ item.status }}</span><p>{{ item.output_summary || compactOutput(item.output) }}</p>
        </div>
      </div>
      <div v-if="eventReview" class="review-box">
        <strong>Human Review：{{ eventReview.human_review_required ? '需要人工审核' : '无需人工审核' }}</strong>
        <p>原因：{{ eventReview.review_reason || '无' }}</p>
        <p>允许操作：{{ eventReview.allowed_actions?.join('、') || '无' }}</p>
      </div>
      <div class="report-box">
        <button class="ghost-button" :disabled="!eventRun" @click="loadMarkdownReport">查看 Markdown 报告</button>
        <pre v-if="hasReport">{{ report.markdown_content }}</pre>
        <p v-else class="muted tiny-text">报告基于已有 AgentRun 生成，不会重新运行 Agent。</p>
      </div>
    </article>
  </section>
</template>

<style scoped>
.workbench-page { display: grid; gap: 18px; }
.workbench-card { padding: 22px; }
.workbench-error { margin: 0; }
.crisis-radar { border-top: 4px solid #c55d3d; }
.eval-center { border-top: 4px solid #517d78; }
.eval-metrics { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; margin: 16px 0; }
.eval-metric { display: grid; gap: 5px; padding: 13px; border-radius: 12px; background: #eef5f3; color: #60766d; font-size: 12px; }
.eval-metric strong { color: #214941; font-family: Georgia, serif; font-size: 23px; }
.eval-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 22px; }
.lower-eval-grid { margin-top: 18px; }
.eval-grid h4 { margin: 0 0 10px; color: #294637; }
.eval-dimensions, .eval-failure-list, .eval-run-list { display: grid; gap: 8px; }
.eval-dimension-row, .eval-run-row { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 9px; align-items: center; border-top: 1px solid #e7ece9; padding: 10px 0; font-size: 13px; }
.eval-dimension-row small, .eval-run-row small, .regression-box small { color: #738077; font-size: 12px; }
.regression-box { display: grid; gap: 7px; padding: 14px; border-radius: 12px; background: #f2f7f5; }.regression-box strong { color: #244d43; font-family: Georgia, serif; font-size: 26px; }
.eval-failure-row { border-left: 3px solid #bd6249; padding: 9px 12px; background: #fff7f4; }.eval-failure-row p { margin: 5px 0 0; color: #765a51; font-size: 12px; }
.golden-failure-box { display: grid; gap: 5px; padding: 10px 12px; margin-bottom: 10px; border-left: 3px solid #a84f3b; background: #fff6f1; color: #765a51; font-size: 13px; }.golden-failure-box small { overflow-wrap: anywhere; }
.eval-run-row { width: 100%; border-right: 0; border-bottom: 0; border-left: 0; background: transparent; color: inherit; text-align: left; cursor: pointer; }.eval-run-row:hover { background: #f5faf6; }.eval-run-row span:first-child { display: grid; gap: 3px; }
.radar-metrics { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 10px; margin: 16px 0 20px; }
.radar-metric { display: grid; gap: 5px; padding: 13px; border-radius: 12px; background: #f1f5f2; color: #607066; font-size: 12px; }
.radar-metric strong { color: #193329; font-family: Georgia, serif; font-size: 25px; }
.radar-metric.sev-one { background: #ffe6df; color: #9a301c; }.radar-metric.sev-one strong { color: #9a301c; }
.radar-metric.sev-two { background: #fff0d8; color: #915e13; }.radar-metric.sev-two strong { color: #915e13; }
.radar-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 22px; }
.radar-grid h4 { margin: 0 0 10px; color: #294637; }
.lower-radar-grid { margin-top: 20px; }
.radar-list, .source-health-list, .trend-list { display: grid; gap: 8px; }
.radar-event { display: flex; gap: 10px; align-items: center; width: 100%; border: 1px solid #e1e8e3; border-radius: 10px; padding: 10px; background: #fff; color: inherit; text-align: left; cursor: pointer; }
.radar-event:hover { background: #f5faf6; }
.radar-event-main { display: grid; min-width: 0; gap: 3px; flex: 1; }
.radar-event-main strong, .radar-event-main small, .radar-action { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.radar-event-main small, .radar-action, .source-health-row small, .trend-row small { color: #738077; font-size: 12px; }
.radar-action { max-width: 140px; color: #607569; font-size: 12px; }
.severity-badge { flex: 0 0 auto; border-radius: 999px; padding: 4px 7px; background: #e9efeb; color: #516158; font-size: 11px; font-weight: 700; }
.severity-badge.sev-1 { background: #ffe0d7; color: #9a301c; }.severity-badge.sev-2 { background: #fff0d7; color: #915e13; }.severity-badge.sev-3 { background: #e7f0df; color: #527036; }
.source-health-row { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 7px 10px; align-items: center; padding: 9px 0; border-top: 1px solid #e7ece9; font-size: 13px; }
.source-health-row small { grid-column: 1 / -1; }
.trend-row { display: grid; grid-template-columns: 88px minmax(60px, 1fr) 24px; gap: 8px; align-items: center; font-size: 12px; }
.trend-row small { grid-column: 2 / -1; }
.trend-track { height: 8px; overflow: hidden; border-radius: 999px; background: #e7ece9; }.trend-track i { display: block; height: 100%; border-radius: inherit; background: #6f9d7e; }
.workbench-columns { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
.workbench-form { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-bottom: 18px; }
.workbench-form input, .workbench-form select { min-width: 0; border: 1px solid #d9dfdc; border-radius: 10px; padding: 10px 12px; background: #fff; }
.button-line { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.small-button { padding: 8px 10px; font-size: 12px; }
.data-list, .cluster-list { display: grid; gap: 8px; }
.data-row, .cluster-row { display: flex; gap: 12px; align-items: center; justify-content: space-between; border-top: 1px solid #e7ece9; padding: 12px 0; }
.data-row > div, .cluster-row > div { min-width: 0; }
.data-row small { display: block; color: #718078; margin-top: 3px; }
.data-row span { flex-shrink: 0; }
.clickable { cursor: pointer; }
.clickable:hover { background: rgba(233, 243, 237, 0.7); }
.status-on { background: #dff3e5; color: #1e6b3e; }
.status-off { background: #eef0ef; color: #6c7772; }
.empty-inline { color: #78847f; padding: 14px 0; }
.tiny-text { font-size: 12px; }
.run-summary, .run-result, .review-box, .report-box { margin-top: 14px; border-radius: 14px; padding: 14px; background: #f5f8f6; }
.live-fetch-panel { margin: 14px 0; border: 1px solid #e4c7a1; border-radius: 12px; padding: 10px 12px; background: #fff8ec; }
.live-fetch-panel summary { cursor: pointer; font-weight: 700; color: #8a4b18; }
.live-fetch-warning { display: grid; gap: 8px; padding-top: 12px; color: #6e5138; font-size: 13px; }
.live-fetch-warning p { margin: 0; }
.live-fetch-warning input { border: 1px solid #d8c2a9; border-radius: 9px; padding: 9px 10px; background: #fff; }
.danger-button { width: fit-content; border: 0; border-radius: 9px; padding: 9px 12px; color: #fff; background: #a84f3b; cursor: pointer; }
.danger-button:disabled { cursor: not-allowed; opacity: .45; }
.source-result-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; font-size: 12px; color: #64736b; }
.background-run-toggle { display: flex; gap: 7px; align-items: center; margin-top: 12px; color: #43584e; font-size: 13px; }
.worker-panel { display: grid; gap: 7px; margin-top: 12px; padding-top: 12px; border-top: 1px solid #e7ece9; }
.cluster-row { align-items: flex-start; }
.cluster-row p { margin: 5px 0 0; color: #68756e; font-size: 13px; }
.facts-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin: 16px 0; }
.facts-grid span { padding: 10px; border-radius: 10px; background: #f1f5f2; font-size: 13px; }
.trace-block { margin-top: 18px; }
.trace-row { border-left: 3px solid #9bc3ad; padding: 10px 14px; margin-top: 8px; background: #fafcfb; }
.trace-row span { float: right; color: #718078; font-size: 12px; }
.trace-row p { margin: 7px 0 0; color: #66736d; font-size: 13px; overflow-wrap: anywhere; }
.draft-statement { line-height: 1.8; margin-bottom: 0; }
.report-box pre { max-height: 360px; overflow: auto; white-space: pre-wrap; margin: 14px 0 0; background: #17231f; color: #edf7f0; padding: 16px; border-radius: 12px; font-size: 12px; }
@media (max-width: 900px) {
  .workbench-columns, .workbench-form, .radar-grid, .eval-grid { grid-template-columns: 1fr; }
  .radar-metrics, .eval-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .facts-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
