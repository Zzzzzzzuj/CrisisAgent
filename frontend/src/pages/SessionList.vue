<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";

import { getDynamicSession, getRuntimeMetrics, listDynamicSessions } from "../api";
import CaseCard from "../components/CaseCard.vue";

const cases = ref([]);
const runtimeMetrics = ref(null);
const loading = ref(false);
const refreshing = ref(false);
const error = ref("");
const metricsError = ref("");
const searchQuery = ref("");
const statusFilter = ref("all");
const riskFilter = ref("all");
const page = ref(1);
const pageSize = 10;

const totalCases = computed(() => cases.value.length);
const highRiskCases = computed(
  () => cases.value.filter((item) => ["high", "critical"].includes(String(item.risk_level || "").toLowerCase())).length,
);
const pendingReview = computed(() => cases.value.filter((item) => item.status === "WAITING_HUMAN").length);
const completedCases = computed(() => cases.value.filter((item) => item.status === "COMPLETED").length);
const failedCases = computed(() => cases.value.filter((item) => ["FAILED", "REJECTED"].includes(item.status)).length);
const runtimeCards = computed(() => {
  const metrics = runtimeMetrics.value || {};
  return [
    ["LLM Fallback", metrics.llm_fallback_count],
    ["Guardrail Hits", metrics.guardrail_trigger_count],
    ["RAG Hits", metrics.rag_hit_count],
    ["RAG Fallback", metrics.rag_fallback_count],
    ["Approvals", metrics.approval_count],
    ["Rejections", metrics.rejection_count],
  ];
});

const filteredCases = computed(() => {
  const query = searchQuery.value.trim().toLocaleLowerCase();
  return cases.value.filter((item) => {
    const text = [item.event, item.title, item.final_statement_preview].filter(Boolean).join(" ").toLocaleLowerCase();
    const matchesSearch = !query || text.includes(query);
    const matchesStatus = statusFilter.value === "all" || statusMatches(item.status, statusFilter.value);
    const risk = String(item.risk_level || "").toLowerCase();
    const matchesRisk = riskFilter.value === "all" || (riskFilter.value === "high" ? ["high", "critical"].includes(risk) : risk === riskFilter.value);
    return matchesSearch && matchesStatus && matchesRisk;
  });
});

const pageCount = computed(() => Math.max(1, Math.ceil(filteredCases.value.length / pageSize)));
const visibleCases = computed(() => filteredCases.value.slice((page.value - 1) * pageSize, page.value * pageSize));

watch([searchQuery, statusFilter, riskFilter], () => {
  page.value = 1;
});

function statusMatches(status, filter) {
  if (filter === "pending") return status === "WAITING_HUMAN";
  if (filter === "processing") return ["RUNNING", "QUEUED", "CREATED", "INIT"].includes(status);
  if (filter === "completed") return status === "COMPLETED";
  if (filter === "failed") return ["FAILED", "REJECTED"].includes(status);
  return true;
}

async function loadCases({ quiet = false } = {}) {
  if (quiet) refreshing.value = true;
  else loading.value = true;
  error.value = "";
  metricsError.value = "";
  try {
    void loadRuntimeMetrics();
    const sessions = await listDynamicSessions();
    const enriched = await mapWithConcurrency(sessions, 8, enrichCase);
    cases.value = enriched.sort((left, right) => parseTime(right.created_time) - parseTime(left.created_time));
    page.value = 1;
  } catch (err) {
    error.value = typeof err.response?.data?.detail === "string" ? err.response.data.detail : "加载失败，请重试。";
  } finally {
    loading.value = false;
    refreshing.value = false;
  }
}

async function mapWithConcurrency(items, limit, mapper) {
  const results = new Array(items.length);
  let nextIndex = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (nextIndex < items.length) {
      const index = nextIndex++;
      results[index] = await mapper(items[index]);
    }
  });
  await Promise.all(workers);
  return results;
}

async function loadRuntimeMetrics() {
  try {
    runtimeMetrics.value = await getRuntimeMetrics();
  } catch (err) {
    runtimeMetrics.value = null;
    metricsError.value = err.response?.data?.detail || err.message || "Runtime Metrics 暂不可用";
  }
}

async function enrichCase(item) {
  try {
    const detail = await getDynamicSession(item.session_id);
    return {
      ...item,
      risk_level:
        detail.results?.sentiment?.risk_level ||
        detail.metadata?.planner_input?.risk_level ||
        "待分析",
      status: detail.status || item.status,
      updated_time: detail.trace?.at(-1)?.end_time || item.created_time,
    };
  } catch {
    return {
      ...item,
      risk_level: "待分析",
    };
  }
}

function applyQuickFilter(filter) {
  statusFilter.value = filter.status || "all";
  riskFilter.value = filter.risk || "all";
  searchQuery.value = "";
}

function parseTime(value) {
  const parsed = value ? new Date(value).getTime() : 0;
  return Number.isFinite(parsed) ? parsed : 0;
}

onMounted(loadCases);
</script>

<template>
  <section class="case-home">
    <header class="home-heading">
      <div>
        <p class="eyebrow">CRISIS RESPONSE</p>
        <h2>企业危机响应平台</h2>
        <p class="muted">快速找到需要关注的事件，并继续处理尚未完成的响应。</p>
      </div>
      <RouterLink class="primary-button hero-action" to="/new"><span aria-hidden="true">＋</span> 新建危机案例</RouterLink>
    </header>

    <div class="case-stat-strip" aria-label="案例概览">
      <button class="case-stat" :class="{ selected: statusFilter === 'all' && riskFilter === 'all' }" :aria-pressed="statusFilter === 'all' && riskFilter === 'all'" @click="applyQuickFilter({})">
        <span>全部案例</span><strong>{{ totalCases }}</strong>
      </button>
      <button class="case-stat high" :class="{ selected: riskFilter === 'high' }" :aria-pressed="riskFilter === 'high'" @click="applyQuickFilter({ risk: 'high' })">
        <span>高风险</span><strong>{{ highRiskCases }}</strong>
      </button>
      <button class="case-stat pending" :class="{ selected: statusFilter === 'pending' }" :aria-pressed="statusFilter === 'pending'" @click="applyQuickFilter({ status: 'pending' })">
        <span>待审核</span><strong>{{ pendingReview }}</strong>
      </button>
      <button class="case-stat complete" :class="{ selected: statusFilter === 'completed' }" :aria-pressed="statusFilter === 'completed'" @click="applyQuickFilter({ status: 'completed' })">
        <span>已完成</span><strong>{{ completedCases }}</strong>
      </button>
      <button class="case-stat failed" :class="{ selected: statusFilter === 'failed' }" :aria-pressed="statusFilter === 'failed'" @click="applyQuickFilter({ status: 'failed' })">
        <span>失败</span><strong>{{ failedCases }}</strong>
      </button>
    </div>

    <section class="case-list-panel" aria-labelledby="case-list-heading">
      <div class="case-toolbar">
        <label class="case-search">
          <span class="sr-only">搜索案例</span>
          <span aria-hidden="true" class="search-mark">⌕</span>
          <input v-model="searchQuery" type="search" placeholder="搜索事件关键词..." />
        </label>
        <label class="filter-control">
          <span class="sr-only">按状态筛选</span>
          <select v-model="statusFilter" aria-label="状态筛选">
            <option value="all">全部状态</option>
            <option value="pending">待审核</option>
            <option value="processing">处理中</option>
            <option value="completed">已完成</option>
            <option value="failed">失败</option>
          </select>
        </label>
        <label class="filter-control">
          <span class="sr-only">按风险筛选</span>
          <select v-model="riskFilter" aria-label="风险筛选">
            <option value="all">全部风险</option>
            <option value="high">高风险</option>
            <option value="medium">中风险</option>
            <option value="low">低风险</option>
          </select>
        </label>
        <button class="refresh-button" :disabled="loading || refreshing" @click="loadCases({ quiet: true })">
          {{ refreshing ? "刷新中..." : "刷新" }}
        </button>
      </div>

      <div class="case-list-heading">
        <div>
          <p class="eyebrow">CASE QUEUE</p>
          <h3 id="case-list-heading">危机案例</h3>
        </div>
        <span class="list-count">{{ filteredCases.length }} 条结果</span>
      </div>

      <div v-if="loading" class="case-list-skeleton" role="status" aria-label="正在加载危机案例">
        <div v-for="index in 7" :key="index" class="skeleton-row">
          <i></i><span></span><b></b><em></em>
        </div>
      </div>
      <div v-else-if="error" class="list-message error-state" role="alert">
        <span>{{ error }}</span><button class="text-button" @click="loadCases()">重试</button>
      </div>
      <div v-else-if="cases.length === 0" class="list-message empty-state">
        <strong>暂无危机案例</strong>
        <span>创建第一个危机事件，CrisisAgent 将帮助你完成风险分析、响应生成和人工审核。</span>
        <RouterLink to="/new" class="primary-button empty-create-link"><span aria-hidden="true">＋</span> 新建危机案例</RouterLink>
      </div>
      <div v-else-if="filteredCases.length === 0" class="list-message empty-state">
        没有符合条件的案例，试试调整关键词或筛选条件。
      </div>
      <div v-else class="case-list" role="list">
        <CaseCard v-for="caseItem in visibleCases" :key="caseItem.session_id" :case-item="caseItem" role="listitem" />
      </div>

      <footer v-if="filteredCases.length > pageSize" class="list-pagination">
        <span>第 {{ page }} / {{ pageCount }} 页</span>
        <div>
          <button class="refresh-button" :disabled="page <= 1" @click="page -= 1">上一页</button>
          <button class="refresh-button" :disabled="page >= pageCount" @click="page += 1">下一页</button>
        </div>
      </footer>
    </section>

    <details class="runtime-metrics-panel">
      <summary>系统运行指标 <span>仅供运营与排障参考</span></summary>
      <p v-if="metricsError" class="muted compact-warning">{{ metricsError }}</p>
      <div v-else class="runtime-metrics-grid">
        <div v-for="[label, value] in runtimeCards" :key="label">
          <span>{{ label }}</span><strong>{{ value ?? 0 }}</strong>
        </div>
      </div>
    </details>
  </section>
</template>
