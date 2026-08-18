<script setup>
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";

import { getDynamicSession, getRuntimeMetrics, listDynamicSessions } from "../api";
import CaseCard from "../components/CaseCard.vue";

const cases = ref([]);
const runtimeMetrics = ref(null);
const loading = ref(false);
const error = ref("");
const metricsError = ref("");

const totalCases = computed(() => cases.value.length);
const highRiskCases = computed(
  () => cases.value.filter((item) => ["high", "critical"].includes(String(item.risk_level || "").toLowerCase())).length,
);
const pendingReview = computed(() => cases.value.filter((item) => item.status === "WAITING_HUMAN").length);
const completedCases = computed(() => cases.value.filter((item) => item.status === "COMPLETED").length);
const recentCases = computed(() => cases.value.slice(0, 6));
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

async function loadCases() {
  loading.value = true;
  error.value = "";
  metricsError.value = "";
  try {
    const [sessions] = await Promise.all([listDynamicSessions(), loadRuntimeMetrics()]);
    cases.value = await Promise.all(sessions.map(enrichCase));
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || "加载危机案例失败";
  } finally {
    loading.value = false;
  }
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
    };
  } catch {
    return {
      ...item,
      risk_level: "待分析",
    };
  }
}

onMounted(loadCases);
</script>

<template>
  <section class="case-home">
    <div class="product-hero dashboard-hero">
      <div>
        <p class="eyebrow">Crisis Dashboard</p>
        <h2>企业危机响应平台</h2>
        <p class="muted">
          统一管理危机案例、风险等级、AI 声明和人工审核状态，让团队快速判断优先级并推进响应。
        </p>
      </div>
      <RouterLink class="primary-button hero-action" to="/new">新建危机案例</RouterLink>
    </div>

    <div class="stats-grid">
      <article class="stat-card">
        <span>Total Cases</span>
        <strong>{{ runtimeMetrics?.total_sessions ?? totalCases }}</strong>
      </article>
      <article class="stat-card alert">
        <span>High Risk Cases</span>
        <strong>{{ highRiskCases }}</strong>
      </article>
      <article class="stat-card pending">
        <span>Pending Review</span>
        <strong>{{ runtimeMetrics?.waiting_human_sessions ?? pendingReview }}</strong>
      </article>
      <article class="stat-card complete">
        <span>Completed Cases</span>
        <strong>{{ runtimeMetrics?.completed_sessions ?? completedCases }}</strong>
      </article>
      <article class="stat-card failed">
        <span>Failed Sessions</span>
        <strong>{{ runtimeMetrics?.failed_sessions ?? 0 }}</strong>
      </article>
      <article
        v-for="[label, value] in runtimeCards"
        :key="label"
        class="stat-card runtime"
      >
        <span>{{ label }}</span>
        <strong>{{ value ?? 0 }}</strong>
      </article>
    </div>
    <p v-if="metricsError" class="muted compact-warning">
      {{ metricsError }}，案例列表仍可正常查看。
    </p>

    <div class="section-heading">
      <div>
        <p class="eyebrow">Recent Cases</p>
        <h3>最近危机案例</h3>
      </div>
      <button class="ghost-button" @click="loadCases">刷新</button>
    </div>

    <p v-if="loading" class="muted">正在加载案例...</p>
    <p v-if="error" class="error">{{ error }}</p>

    <div v-if="!loading && cases.length === 0" class="empty-state">
      暂无危机案例。创建一个案例后，这里会展示风险等级、审核状态和响应进展。
    </div>

    <div class="case-grid">
      <CaseCard v-for="caseItem in recentCases" :key="caseItem.session_id" :case-item="caseItem" />
    </div>
  </section>
</template>
