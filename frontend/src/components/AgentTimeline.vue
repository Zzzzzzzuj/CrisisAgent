<script setup>
defineProps({
  trace: {
    type: Array,
    default: () => [],
  },
});

function durationMs(item) {
  if (item.duration_ms !== undefined && item.duration_ms !== null) {
    return `${item.duration_ms} ms`;
  }
  if (!item.start_time || !item.end_time) {
    return "-";
  }
  const start = Date.parse(item.start_time);
  const end = Date.parse(item.end_time);
  if (Number.isNaN(start) || Number.isNaN(end)) {
    return "-";
  }
  return `${Math.max(0, end - start)} ms`;
}

function outputSummary(output) {
  if (!output) {
    return "无输出";
  }
  const text = JSON.stringify(output);
  return text.length > 180 ? `${text.slice(0, 180)}...` : text;
}

function summary(item) {
  return item.output_summary || outputSummary(item.output);
}
</script>

<template>
  <article class="timeline-card">
    <div class="page-header">
      <div>
        <p class="eyebrow">Execution Timeline</p>
        <h3>Agent 执行时间线</h3>
      </div>
      <span class="status-pill">{{ trace.length }} steps</span>
    </div>

    <div v-if="trace.length === 0" class="empty-state">暂无 trace。</div>

    <div v-for="(item, index) in trace" :key="`${item.agent}-${index}`" class="timeline-item">
      <div class="timeline-dot" :class="{ failed: item.status !== 'success' && item.status !== 'approved' }"></div>
      <div class="timeline-body">
        <div class="timeline-head">
          <strong>{{ item.agent || "unknown" }}</strong>
          <span class="status-pill">{{ item.status }}</span>
        </div>
        <p class="muted">{{ item.reason || "无说明" }}</p>
        <p><strong>duration:</strong> {{ durationMs(item) }}</p>
        <p v-if="item.input_summary"><strong>input:</strong> {{ item.input_summary }}</p>
        <p class="summary"><strong>output:</strong> {{ summary(item) }}</p>
        <p v-if="item.error" class="error"><strong>error:</strong> {{ item.error }}</p>
      </div>
    </div>
  </article>
</template>
