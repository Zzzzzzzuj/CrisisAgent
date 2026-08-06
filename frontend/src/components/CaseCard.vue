<script setup>
defineProps({
  caseItem: {
    type: Object,
    required: true,
  },
});

function caseTitle(event) {
  if (!event) {
    return "未命名危机案例";
  }
  return event.length > 42 ? `${event.slice(0, 42)}...` : event;
}

function formatStatus(status) {
  const map = {
    WAITING_HUMAN: "待审核",
    COMPLETED: "已完成",
    FAILED: "已终止",
    RUNNING: "处理中",
    INIT: "待处理",
  };
  return map[status] || status || "未知";
}

function formatRisk(risk) {
  const map = {
    high: "高风险",
    medium: "中风险",
    low: "低风险",
    critical: "极高风险",
  };
  return map[String(risk || "").toLowerCase()] || risk || "待分析";
}
</script>

<template>
  <article class="case-card">
    <div>
      <p class="eyebrow">Crisis Case</p>
      <h3>{{ caseTitle(caseItem.event) }}</h3>
      <p class="case-description">{{ caseItem.event || "暂无事件描述" }}</p>
    </div>

    <div class="case-card-meta">
      <span class="risk-badge">{{ formatRisk(caseItem.risk_level) }}</span>
      <span class="status-pill">{{ formatStatus(caseItem.status) }}</span>
      <small>{{ caseItem.created_time || "暂无创建时间" }}</small>
    </div>

    <RouterLink
      class="ghost-button details-button"
      :to="caseItem.session_id ? `/cases/${caseItem.session_id}` : '/cases'"
    >
      查看详情
    </RouterLink>
  </article>
</template>
