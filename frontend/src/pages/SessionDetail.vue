<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";

import {
  approveDynamicSession,
  getDynamicMetrics,
  getDynamicSession,
  rejectDynamicSession,
} from "../api";
import AdvancedAnalysis from "../components/AdvancedAnalysis.vue";
import CaseStepper from "../components/CaseStepper.vue";
import HumanReviewPanel from "../components/HumanReviewPanel.vue";

const props = defineProps({
  sessionId: {
    type: String,
    default: "",
  },
});

const route = useRoute();
const session = ref(null);
const metrics = ref(null);
const loading = ref(false);
const actionLoading = ref(false);
const error = ref("");

const activeSessionId = computed(() => props.sessionId || String(route.params.sessionId || ""));
const sentiment = computed(() => session.value?.results?.sentiment || {});
const decision = computed(() => session.value?.results?.decision || {});
const approval = computed(() => session.value?.approval || {});
const finalStatement = computed(() => decision.value.final_statement || "暂无 AI 生成声明。");
const riskLevel = computed(
  () => sentiment.value.risk_level || session.value?.metadata?.planner_input?.risk_level || "待分析",
);
const auditStatus = computed(() => formatStatus(session.value?.status));
const crisisTitle = computed(() => buildTitle(session.value?.event || ""));
const keywordsText = computed(() => {
  const keywords = sentiment.value.keywords || [];
  return keywords.length > 0 ? keywords.join(" / ") : "暂无关键词";
});

async function loadCase() {
  const sessionId = activeSessionId.value;
  if (!sessionId) {
    error.value = "缺少案例 ID，无法加载详情。";
    return;
  }

  loading.value = true;
  error.value = "";
  session.value = null;
  metrics.value = null;

  try {
    session.value = await getDynamicSession(sessionId);
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || "加载危机案例失败";
    loading.value = false;
    return;
  }

  try {
    metrics.value = await getDynamicMetrics(sessionId);
  } catch {
    metrics.value = null;
  } finally {
    loading.value = false;
  }
}

async function submitReview(decisionType, payload) {
  const sessionId = activeSessionId.value;
  if (!sessionId) {
    error.value = "缺少案例 ID，无法提交审核。";
    return;
  }

  actionLoading.value = true;
  error.value = "";
  try {
    const result =
      decisionType === "approve"
        ? await approveDynamicSession(sessionId, payload)
        : await rejectDynamicSession(sessionId, payload);
    await loadCase();
    if (result?.status === "error") {
      error.value = result.error;
    }
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || "审核操作失败";
  } finally {
    actionLoading.value = false;
  }
}

function buildTitle(text) {
  if (!text) {
    return "危机案例详情";
  }
  return text.length > 34 ? `${text.slice(0, 34)}...` : text;
}

function formatStatus(status) {
  const map = {
    WAITING_HUMAN: "待人工审核",
    COMPLETED: "已完成",
    FAILED: "已终止",
    RUNNING: "处理中",
    INIT: "待处理",
  };
  return map[status] || status || "未知";
}

onMounted(loadCase);
watch(activeSessionId, loadCase);
</script>

<template>
  <section class="case-detail dashboard-detail">
    <p v-if="loading" class="muted">正在加载案例...</p>
    <p v-if="error" class="error">{{ error }}</p>

    <template v-if="session">
      <div class="case-brief compact-case-brief">
        <div class="case-title-block">
          <p class="eyebrow">Crisis Case</p>
          <h2>{{ crisisTitle }}</h2>
          <p class="muted compact-event">{{ session.event }}</p>
        </div>
        <div class="brief-badges compact-badges">
          <span class="risk-badge">{{ riskLevel }}</span>
          <span class="status-pill">{{ auditStatus }}</span>
        </div>
      </div>

      <CaseStepper :status="session.status" />

      <div class="detail-main-grid">
        <div class="insight-column">
          <article class="page-card compact-card">
            <p class="eyebrow">Risk Analysis</p>
            <h3>风险分析</h3>
            <strong class="large-risk">{{ riskLevel }}</strong>
            <div class="compact-facts">
              <span>情绪：{{ sentiment.public_emotion || "待分析" }}</span>
              <span>语气：{{ sentiment.recommended_tone || "待建议" }}</span>
              <span>关键词：{{ keywordsText }}</span>
            </div>
            <p class="muted">{{ sentiment.analysis_summary || "系统已完成初步事件分析。" }}</p>
          </article>

          <article class="page-card compact-card">
            <p class="eyebrow">Current State</p>
            <h3>当前状态</h3>
            <strong class="large-status">{{ auditStatus }}</strong>
            <p class="muted">{{ approval.reason || decision.decision_summary || "当前案例可继续查看声明和审核记录。" }}</p>
          </article>
        </div>

        <article class="page-card statement-card dashboard-statement">
          <div class="page-header compact-page-header">
            <div>
              <p class="eyebrow">AI Statement</p>
              <h3>AI 生成声明</h3>
            </div>
            <span class="status-pill">{{ auditStatus }}</span>
          </div>
          <p class="statement">{{ finalStatement }}</p>
        </article>
      </div>

      <HumanReviewPanel
        :approval="approval"
        :final-statement="finalStatement"
        :status="session.status"
        :loading="actionLoading"
        @approve="submitReview('approve', $event)"
        @reject="submitReview('reject', $event)"
      />

      <AdvancedAnalysis :session="session" :metrics="metrics" />
    </template>
  </section>
</template>
