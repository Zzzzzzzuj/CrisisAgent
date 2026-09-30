<script setup>
import { computed } from "vue";
import { RouterLink } from "vue-router";

const props = defineProps({
  caseItem: {
    type: Object,
    required: true,
  },
});

const detailUrl = computed(() => (props.caseItem.session_id ? `/cases/${props.caseItem.session_id}` : "/cases"));
const eventText = computed(() => String(props.caseItem.event || "未命名危机案例").trim());
const displayTitle = computed(() => {
  const [first] = eventText.value.split(/[。！？.!?\n]/, 1);
  return first || eventText.value;
});
const displaySummary = computed(() => {
  if (props.caseItem.summary) return props.caseItem.summary;
  const remainder = eventText.value.slice(displayTitle.value.length).replace(/^[。！？.!?\s]+/, "");
  return remainder || "";
});

function formatStatus(status) {
  const labels = {
    WAITING_HUMAN: "待审核",
    COMPLETED: "已完成",
    FAILED: "失败",
    REJECTED: "已拒绝",
    RUNNING: "处理中",
    QUEUED: "排队中",
    CREATED: "待处理",
    INIT: "待处理",
  };
  return labels[status] || status || "未知状态";
}

function statusClass(status) {
  if (status === "WAITING_HUMAN") return "waiting";
  if (status === "COMPLETED") return "done";
  if (["FAILED", "REJECTED"].includes(status)) return "failed";
  if (["RUNNING", "QUEUED"].includes(status)) return "active";
  return "neutral";
}

function formatRisk(risk) {
  const labels = { high: "高风险", critical: "极高风险", medium: "中风险", low: "低风险" };
  return labels[String(risk || "").toLowerCase()] || "待分析";
}

function riskClass(risk) {
  const value = String(risk || "").toLowerCase();
  if (["high", "critical"].includes(value)) return "high";
  if (value === "medium") return "medium";
  if (value === "low") return "low";
  return "unknown";
}

function formatTime(value) {
  if (!value) return "时间未知";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间未知";

  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const dateDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const dayOffset = Math.round((today - dateDay) / 86400000);
  const clock = new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
  if (dayOffset === 0) return `今天 ${clock}`;
  if (dayOffset === 1) return `昨天 ${clock}`;
  const day = new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
  return day.replace("/", "-");
}
</script>

<template>
  <RouterLink class="case-row" :to="detailUrl" :title="caseItem.event || '打开案例详情'">
    <div class="case-row-copy">
      <span class="case-risk-point" :class="`point-${riskClass(caseItem.risk_level)}`" aria-hidden="true"></span>
      <div class="case-row-text">
        <h4 class="case-row-title">{{ displayTitle }}</h4>
        <p v-if="displaySummary" class="case-row-summary">{{ displaySummary }}</p>
      </div>
    </div>
    <span class="case-badge risk" :class="`risk-${riskClass(caseItem.risk_level)}`">{{ formatRisk(caseItem.risk_level) }}</span>
    <span class="case-badge status" :class="`status-${statusClass(caseItem.status)}`">{{ formatStatus(caseItem.status) }}</span>
    <time class="case-row-time" :datetime="caseItem.updated_time || caseItem.created_time || undefined">
      {{ formatTime(caseItem.updated_time || caseItem.created_time) }}
    </time>
    <span class="case-row-action" aria-hidden="true">→</span>
  </RouterLink>
</template>
