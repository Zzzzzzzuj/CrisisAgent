<script setup>
import { computed, onMounted, ref } from "vue";

import {
  approveDynamicSession,
  getDynamicMetrics,
  getDynamicSession,
  rejectDynamicSession,
} from "../api";
import AgentTimeline from "../components/AgentTimeline.vue";

const props = defineProps({
  sessionId: {
    type: String,
    required: true,
  },
});

const session = ref(null);
const metrics = ref(null);
const loading = ref(false);
const actionLoading = ref(false);
const error = ref("");
const reviewer = ref("human");
const comment = ref("");

const finalResult = computed(() => session.value?.results?.decision || {});
const approval = computed(() => session.value?.approval || {});
const isWaitingHuman = computed(() => session.value?.status === "WAITING_HUMAN");

async function loadSession() {
  loading.value = true;
  error.value = "";
  try {
    const [sessionData, metricsData] = await Promise.all([
      getDynamicSession(props.sessionId),
      getDynamicMetrics(props.sessionId),
    ]);
    session.value = sessionData;
    metrics.value = metricsData;
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || "加载详情失败";
  } finally {
    loading.value = false;
  }
}

async function review(decision) {
  actionLoading.value = true;
  error.value = "";
  try {
    const payload = { reviewer: reviewer.value, comment: comment.value };
    const result =
      decision === "approve"
        ? await approveDynamicSession(props.sessionId, payload)
        : await rejectDynamicSession(props.sessionId, payload);
    await loadSession();
    if (result?.status === "error") {
      error.value = result.error;
    }
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || "审核操作失败";
  } finally {
    actionLoading.value = false;
  }
}

onMounted(loadSession);
</script>

<template>
  <section class="page-card">
    <p class="eyebrow">Runtime Detail</p>
    <h2>Session 详情</h2>
    <p class="muted">{{ sessionId }}</p>

    <p v-if="loading" class="muted">加载中...</p>
    <p v-if="error" class="error">{{ error }}</p>

    <template v-if="session">
      <div class="detail-grid">
        <article class="info-card">
          <h3>AgentState</h3>
          <p><strong>status:</strong> <span class="status-pill">{{ session.status }}</span></p>
          <p><strong>plan_id:</strong> {{ session.plan_id }}</p>
          <p><strong>event:</strong> {{ session.event }}</p>
        </article>

        <article class="info-card">
          <h3>Approval</h3>
          <pre>{{ JSON.stringify(approval, null, 2) }}</pre>
        </article>
      </div>

      <article v-if="metrics" class="info-card">
        <h3>Observability Metrics</h3>
        <div class="metric-grid">
          <span>total_duration: {{ metrics.total_duration }} ms</span>
          <span>agent_count: {{ metrics.agent_count }}</span>
          <span>failed_agents: {{ metrics.failed_agents?.length || 0 }}</span>
          <span>rag_hits: {{ metrics.rag_hits }}</span>
          <span>memory_hits: {{ metrics.memory_hits }}</span>
          <span>tool_calls: {{ metrics.tool_calls }}</span>
        </div>
      </article>

      <article v-if="isWaitingHuman" class="human-gate">
        <p class="eyebrow">Human Gate</p>
        <h3>需要人工审核</h3>
        <p><strong>审核原因：</strong>{{ approval.reason || "未提供原因" }}</p>
        <div class="review-form">
          <input v-model="reviewer" placeholder="reviewer" />
          <input v-model="comment" placeholder="comment" />
          <button class="primary-button" :disabled="actionLoading" @click="review('approve')">Approve</button>
          <button class="danger-button" :disabled="actionLoading" @click="review('reject')">Reject</button>
        </div>
      </article>

      <AgentTimeline :trace="session.trace || []" />

      <article class="info-card">
        <h3>Final Result</h3>
        <p class="statement">{{ finalResult.final_statement || "暂无最终声明" }}</p>
        <div class="score-grid">
          <span>legal_safety: {{ finalResult.scores?.legal_safety ?? "-" }}</span>
          <span>empathy: {{ finalResult.scores?.empathy ?? "-" }}</span>
          <span>robustness: {{ finalResult.scores?.robustness ?? "-" }}</span>
        </div>
      </article>

      <article class="info-card">
        <h3>Results JSON</h3>
        <pre>{{ JSON.stringify(session.results, null, 2) }}</pre>
      </article>
    </template>
  </section>
</template>
