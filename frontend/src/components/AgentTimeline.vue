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

function formatJson(value) {
  return JSON.stringify(value || {}, null, 2);
}

function isFailed(item) {
  return item.status && !["success", "approved", "completed"].includes(item.status);
}
</script>

<template>
  <div class="timeline-compact-list">
    <div v-if="trace.length === 0" class="empty-state">暂无执行记录。</div>

    <details
      v-for="(item, index) in trace"
      :key="`${item.agent}-${index}`"
      class="timeline-compact-item"
      :class="{ failed: isFailed(item) }"
    >
      <summary>
        <span class="timeline-agent">{{ item.agent || item.name || "unknown" }}</span>
        <span class="status-pill">{{ item.status || "unknown" }}</span>
        <span class="timeline-duration">{{ durationMs(item) }}</span>
      </summary>

      <div class="timeline-details">
        <p v-if="item.name" class="muted">{{ item.name }}</p>
        <p v-if="item.reason"><strong>说明：</strong>{{ item.reason }}</p>
        <p v-if="item.input_summary"><strong>输入摘要：</strong>{{ item.input_summary }}</p>
        <p class="summary"><strong>输出摘要：</strong>{{ summary(item) }}</p>
        <p v-if="item.error" class="error"><strong>失败原因：</strong>{{ item.error }}</p>

        <details class="nested-json">
          <summary>查看 input / output 原始内容</summary>
          <pre>{{ formatJson({ input: item.input, output: item.output, error: item.error }) }}</pre>
        </details>
      </div>
    </details>
  </div>
</template>
