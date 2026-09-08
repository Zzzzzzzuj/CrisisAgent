<script setup>
import { computed, onMounted, ref } from "vue";

import {
  archiveEvent,
  createEventFromIngestionRun,
  createSource,
  getEvent,
  getEventReport,
  getEventReview,
  getEventRun,
  getEventTrace,
  getIngestionRun,
  listEvents,
  listIngestionRuns,
  listSources,
  runEventAgent,
  runIngestion,
  testSource,
  updateSource,
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
const loading = ref(false);
const action = ref("");
const error = ref("");
const sourceTestResults = ref({});

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

onMounted(loadAll);

async function loadAll() {
  loading.value = true;
  error.value = "";
  try {
    await Promise.all([loadSources(), loadRuns(), loadEvents()]);
  } catch (err) {
    showError(err);
  } finally {
    loading.value = false;
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
    const result = await runIngestion({ live_fetch: false, dry_run: dryRun });
    selectedRun.value = result;
    await loadRuns();
  } catch (err) {
    showError(err);
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
    await loadEvents();
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
    await loadEvents();
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
    await loadEvents();
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
      <button class="ghost-button" :disabled="loading" @click="loadAll">刷新全部</button>
    </header>

    <p v-if="error" class="error workbench-error">{{ error }}</p>
    <p v-if="loading" class="muted">正在加载工作台数据...</p>

    <article class="page-card workbench-card">
      <div class="section-heading">
        <div><p class="eyebrow">P1 Source Registry</p><h3>数据源管理</h3></div>
        <span class="status-pill">live-fetch 默认关闭</span>
      </div>
      <form class="workbench-form" @submit.prevent="submitSource">
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
          <button class="ghost-button small-button" @click="toggleSource(source)">{{ source.enabled ? '禁用' : '启用' }}</button>
          <button class="ghost-button small-button" @click="checkSource(source)">配置检查</button>
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
          <button class="primary-button" :disabled="Boolean(action)" @click="startIngestion(true)">运行 dry-run</button>
          <button class="ghost-button" :disabled="Boolean(action)" @click="startIngestion(false)">运行离线采集</button>
        </div>
        <p class="muted tiny-text">工作台不提供 live_fetch=true 操作；真实采集仍需受控脚本显式开启。</p>
        <div v-if="selectedRun" class="run-summary">
          <strong>{{ selectedRun.run_id }}</strong>
          <span>{{ statusText(selectedRun.status) }} · raw {{ selectedRun.raw_count }} · clusters {{ selectedRun.cluster_count }}</span>
        </div>
        <div v-if="runs.length" class="data-list compact-list">
          <div v-for="run in runs" :key="run.run_id" class="data-row clickable" @click="inspectRun(run)">
            <div><strong>{{ run.run_id }}</strong><small>{{ statusText(run.status) }} · {{ run.started_at }}</small></div>
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
            <button class="ghost-button small-button" :disabled="action === 'event'" @click="createEvent(cluster)">沉淀为事件</button>
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
          <button class="primary-button" :disabled="Boolean(action) || selectedEvent.status === 'archived'" @click="runAgent">运行 Agent（mock）</button>
          <button class="ghost-button" :disabled="selectedEvent.status === 'archived'" @click="archiveSelectedEvent">归档</button>
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
  .workbench-columns, .workbench-form { grid-template-columns: 1fr; }
  .facts-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
