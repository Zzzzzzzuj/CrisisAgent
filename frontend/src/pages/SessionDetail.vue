<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";

import {
  approveDynamicSession,
  getDynamicMetrics,
  getDynamicSession,
  rejectDynamicSession,
  respondDynamicFact,
} from "../api";
import AdvancedAnalysis from "../components/AdvancedAnalysis.vue";
import CaseStepper from "../components/CaseStepper.vue";
import HumanFactPanel from "../components/HumanFactPanel.vue";
import HumanReviewPanel from "../components/HumanReviewPanel.vue";

const props = defineProps({
  sessionId: { type: String, default: "" },
});

const route = useRoute();
const session = ref(null);
const metrics = ref(null);
const loading = ref(false);
const actionLoading = ref(false);
const error = ref("");
const actionError = ref("");
const copyState = ref("");
let pollTimer;

const activeSessionId = computed(() => props.sessionId || String(route.params.sessionId || ""));
const metadata = computed(() => session.value?.metadata || {});
const sentiment = computed(() => session.value?.results?.sentiment || {});
const decision = computed(() => session.value?.results?.decision || {});
const approval = computed(() => session.value?.approval || {});
const status = computed(() => session.value?.status || "");
const waitType = computed(() => metadata.value.human_wait_type || "");
const isFactInput = computed(() => status.value === "WAITING_HUMAN" && waitType.value === "FACT_INPUT");
const isFinalReview = computed(
  () => status.value === "WAITING_HUMAN" && (waitType.value === "FINAL_REVIEW" || !waitType.value),
);
const humanFactRequest = computed(() => metadata.value.human_fact?.request || session.value?.human_fact_request || null);
const finalStatement = computed(
  () => decision.value.final_statement || session.value?.results?.writer_v2?.statement || session.value?.results?.writer?.statement || "",
);
const riskLevel = computed(
  () => sentiment.value.risk_level || metadata.value.planner_input?.risk_level || "unknown",
);
const title = computed(() => firstSentence(session.value?.event || "") || "危机案例详情");
const eventTime = computed(() => {
  const trace = session.value?.trace || [];
  return trace.at(-1)?.end_time || trace.at(-1)?.start_time || session.value?.created_time || "";
});
const statusLabel = computed(() => {
  const labels = {
    WAITING_HUMAN: isFactInput.value ? "等待补充事实" : "等待人工审核",
    COMPLETED: "已完成",
    FAILED: "失败",
    REJECTED: "已拒绝",
    RUNNING: "处理中",
    QUEUED: "排队中",
    CREATED: "待处理",
    INIT: "待处理",
  };
  return labels[status.value] || status.value || "未知状态";
});
const statusClass = computed(() => {
  if (isFactInput.value || isFinalReview.value) return "waiting";
  if (status.value === "COMPLETED") return "done";
  if (["FAILED", "REJECTED"].includes(status.value)) return "failed";
  return "active";
});
const riskLabel = computed(() => {
  const labels = { high: "高风险", critical: "极高风险", medium: "中风险", low: "低风险" };
  return labels[String(riskLevel.value).toLowerCase()] || "待分析";
});
const failureSummary = computed(() => {
  if (metadata.value.runtime_failure?.summary) return metadata.value.runtime_failure.summary;
  const traceFailure = [...(session.value?.trace || [])].reverse().find((item) => item.status === "failed" || item.error);
  return traceFailure?.error || "本次运行未能完成，请稍后重试或联系管理员。";
});
const stateMessage = computed(() => {
  if (isFactInput.value) return "补充或确认必要事实后，系统会继续后续分析。";
  if (isFinalReview.value) return "AI 已完成分析，等待你审核最终结果。";
  if (status.value === "COMPLETED") return "响应流程已结束，可查看结果与分析记录。";
  if (status.value === "FAILED") return "本次运行未完成，请查看失败原因和运行记录。";
  if (status.value === "RUNNING" || status.value === "QUEUED") return "AI 正在分析该事件，你可以稍后返回查看结果。";
  return "查看当前风险、响应内容和处理进度。";
});
const statementEmptyMessage = computed(() => {
  if (isFactInput.value) return "声明尚未生成。系统正在等待必要事实确认，完成后会继续处理。";
  if (status.value === "FAILED") return "本次处理未能生成声明，请先查看右侧失败状态与运行记录。";
  if (status.value === "RUNNING" || status.value === "QUEUED") return "声明正在准备中，请稍后刷新。";
  return "当前流程没有生成最终声明。可在运行记录中查看已完成的处理步骤。";
});

async function loadCase({ preserve = false } = {}) {
  const sessionId = activeSessionId.value;
  if (!sessionId) {
    error.value = "缺少案例编号，无法加载详情。";
    return;
  }

  if (!preserve) {
    loading.value = true;
    session.value = null;
    metrics.value = null;
  }
  error.value = "";

  try {
    session.value = await getDynamicSession(sessionId);
    try {
      metrics.value = await getDynamicMetrics(sessionId);
    } catch {
      metrics.value = null;
    }
  } catch (err) {
    error.value = typeof err.response?.data?.detail === "string" ? err.response.data.detail : "加载失败，请重试。";
  } finally {
    loading.value = false;
    schedulePoll();
  }
}

function schedulePoll() {
  window.clearTimeout(pollTimer);
  if (["QUEUED", "RUNNING", "CREATED", "INIT"].includes(status.value)) {
    pollTimer = window.setTimeout(() => loadCase({ preserve: true }), 2500);
  }
}

async function submitFact(responseType, factText = "") {
  if (!humanFactRequest.value?.request_id || actionLoading.value) return;
  actionLoading.value = true;
  actionError.value = "";
  try {
    await respondDynamicFact(activeSessionId.value, {
      request_id: humanFactRequest.value.request_id,
      response_type: responseType,
      fact_text: responseType === "FACT_PROVIDED" ? factText : "",
    });
    await loadCase({ preserve: true });
  } catch (err) {
    actionError.value = typeof err.response?.data?.detail === "string" ? err.response.data.detail : "提交失败，请重试。";
  } finally {
    actionLoading.value = false;
  }
}

async function submitReview(decisionType, payload) {
  if (actionLoading.value) return;
  actionLoading.value = true;
  actionError.value = "";
  try {
    if (decisionType === "approve") await approveDynamicSession(activeSessionId.value, payload);
    else await rejectDynamicSession(activeSessionId.value, payload);
    await loadCase({ preserve: true });
  } catch (err) {
    actionError.value = typeof err.response?.data?.detail === "string" ? err.response.data.detail : "审核提交失败，请重试。";
  } finally {
    actionLoading.value = false;
  }
}

async function copyStatement() {
  if (!finalStatement.value) return;
  try {
    await navigator.clipboard.writeText(finalStatement.value);
    copyState.value = "已复制";
  } catch {
    copyState.value = "复制失败，请手动选择正文";
  }
  window.setTimeout(() => (copyState.value = ""), 2200);
}

function firstSentence(text) {
  const value = String(text || "").trim();
  if (!value) return "";
  const sentence = value.split(/[。！？.!?\n]/, 1)[0].trim();
  return sentence || value;
}

function formatTime(value) {
  if (!value) return "时间未知";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(date).replaceAll("/", "-");
}

onMounted(() => loadCase());
watch(activeSessionId, () => {
  window.clearTimeout(pollTimer);
  loadCase();
});
onBeforeUnmount(() => window.clearTimeout(pollTimer));
</script>

<template>
  <section class="case-detail detail-page">
    <template v-if="loading && !session">
      <div class="detail-skeleton-head"><span></span><i></i><b></b></div>
      <div class="detail-skeleton-stepper"></div>
      <div class="detail-skeleton-layout"><div></div><aside></aside></div>
      <span class="sr-only" role="status">正在加载危机案例...</span>
    </template>

    <div v-else-if="error && !session" class="detail-load-error" role="alert">
      <strong>暂时无法打开这个案例</strong>
      <span>{{ error }}</span>
      <button class="quiet-button" @click="loadCase()">重试</button>
    </div>

    <template v-else-if="session">
      <header class="detail-header">
        <RouterLink class="back-link" to="/cases"><span aria-hidden="true">←</span> 返回危机案例</RouterLink>
        <div class="detail-title-row">
          <div class="detail-title-copy">
            <p class="eyebrow">危机事件</p>
            <h1 :title="session.event">{{ title }}</h1>
            <details class="event-source">
              <summary>查看事件原始描述</summary>
              <p>{{ session.event || "暂无事件描述" }}</p>
            </details>
          </div>
          <div class="detail-head-meta">
            <span class="case-badge risk" :class="`risk-${String(riskLevel).toLowerCase()}`">{{ riskLabel }}</span>
            <span class="case-badge status" :class="`status-${statusClass}`">{{ statusLabel }}</span>
            <time :datetime="eventTime || undefined">更新于 {{ formatTime(eventTime) }}</time>
          </div>
        </div>
      </header>

      <CaseStepper
        :status="status"
        :wait-type="waitType"
        :trace="session.trace || []"
        :failed-agents="session.failed_agents || []"
      />

      <div class="detail-workspace">
        <main class="detail-primary-column">
          <article class="glass-panel statement-panel">
            <div class="panel-heading">
              <div>
                <p class="eyebrow">响应草稿</p>
                <h2>AI 响应声明</h2>
              </div>
              <button v-if="finalStatement" class="quiet-button copy-button" @click="copyStatement">
                {{ copyState || "复制正文" }}
              </button>
            </div>
            <p v-if="finalStatement" class="statement-body">{{ finalStatement }}</p>
            <div v-else class="statement-empty" :class="{ 'needs-fact': isFactInput }">
              <span class="statement-empty-mark" aria-hidden="true">{{ isFactInput ? "…" : "i" }}</span>
              <p>{{ statementEmptyMessage }}</p>
            </div>
          </article>

          <HumanFactPanel
            v-if="isFactInput"
            :request="humanFactRequest"
            :loading="actionLoading"
            :error="actionError"
            @provided="submitFact('FACT_PROVIDED', $event)"
            @unavailable="submitFact('FACT_UNAVAILABLE')"
          />

          <HumanReviewPanel
            v-else-if="isFinalReview"
            :approval="approval"
            :final-statement="finalStatement"
            :status="status"
            :loading="actionLoading"
            :error="actionError"
            @approve="submitReview('approve', $event)"
            @reject="submitReview('reject', $event)"
          />

          <div v-else-if="actionError" class="inline-action-error" role="alert">{{ actionError }}</div>

          <details class="result-details">
            <summary>查看 Agent 分析与运行记录</summary>
            <div class="result-summary">
              <h3>风险研判</h3>
              <p>{{ sentiment.analysis_summary || "暂无风险分析摘要。" }}</p>
              <div class="detail-fact-chips">
                <span>公众情绪：{{ sentiment.public_emotion || "待分析" }}</span>
                <span>建议语气：{{ sentiment.recommended_tone || "待建议" }}</span>
                <span>关键词：{{ (sentiment.keywords || []).join(" / ") || "暂无" }}</span>
              </div>
            </div>
            <AdvancedAnalysis :session="session" :metrics="metrics" />
          </details>
        </main>

        <aside class="detail-side-column">
          <section class="glass-panel status-panel" :class="`status-panel-${statusClass}`">
            <div class="panel-heading compact">
              <div><p class="eyebrow">当前进度</p><h2>{{ statusLabel }}</h2></div>
              <span class="state-indicator" aria-hidden="true"></span>
            </div>
            <p>{{ stateMessage }}</p>
            <p v-if="status === 'FAILED'" class="failure-copy">{{ failureSummary }}</p>
            <div v-if="approval.reason" class="state-reason">
              <span>处理说明</span><p>{{ approval.reason }}</p>
            </div>
          </section>

          <section class="glass-panel risk-panel">
            <p class="eyebrow">风险概览</p>
            <div class="risk-summary-row">
              <strong>{{ riskLabel }}</strong>
              <span class="risk-meter" :class="`risk-meter-${String(riskLevel).toLowerCase()}`"><i></i></span>
            </div>
            <p>{{ sentiment.analysis_summary || "系统尚未生成风险分析摘要。" }}</p>
          </section>

          <section class="detail-meta-list">
            <div><span>案例编号</span><code>{{ session.session_id }}</code></div>
            <div><span>最近更新</span><time>{{ formatTime(eventTime) }}</time></div>
            <div v-if="metadata.harness_spec?.metadata?.version"><span>运行配置</span><span>v{{ metadata.harness_spec.metadata.version }}</span></div>
          </section>
        </aside>
      </div>
    </template>
  </section>
</template>
