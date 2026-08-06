<script setup>
import { computed } from "vue";

import AgentTimeline from "./AgentTimeline.vue";

const props = defineProps({
  session: {
    type: Object,
    required: true,
  },
  metrics: {
    type: Object,
    default: null,
  },
});

const trace = computed(() => props.session.trace || []);
const ragItems = computed(() => trace.value.filter((item) => item.rag));
const memoryItems = computed(() => trace.value.filter((item) => item.memory));

function formatJson(value) {
  return JSON.stringify(value || {}, null, 2);
}
</script>

<template>
  <details class="debug-panel">
    <summary>高级分析：Agent Trace / RAG / Memory / Metrics / JSON</summary>

    <div v-if="metrics" class="metric-grid advanced-metrics">
      <span>总耗时：{{ metrics.total_duration }} ms</span>
      <span>处理节点：{{ metrics.agent_count }}</span>
      <span>失败节点：{{ metrics.failed_agents?.length || 0 }}</span>
      <span>RAG 命中：{{ metrics.rag_hits }}</span>
      <span>Memory 命中：{{ metrics.memory_hits }}</span>
      <span>工具调用：{{ metrics.tool_calls }}</span>
    </div>

    <div class="analysis-grid">
      <article class="analysis-card">
        <h4>RAG</h4>
        <p v-if="ragItems.length === 0" class="muted">暂无 RAG 记录。</p>
        <details v-for="(item, index) in ragItems" :key="`rag-${index}`" class="nested-json">
          <summary>{{ item.agent || "RAG" }} 检索详情</summary>
          <pre>{{ formatJson(item.rag) }}</pre>
        </details>
      </article>

      <article class="analysis-card">
        <h4>Memory</h4>
        <p v-if="memoryItems.length === 0" class="muted">暂无 Memory 记录。</p>
        <details v-for="(item, index) in memoryItems" :key="`memory-${index}`" class="nested-json">
          <summary>{{ item.agent || "Memory" }} 记忆详情</summary>
          <pre>{{ formatJson(item.memory) }}</pre>
        </details>
      </article>
    </div>

    <article class="analysis-card full-span">
      <h4>Agent Trace</h4>
      <AgentTimeline :trace="trace" />
    </article>

    <details class="analysis-card full-span raw-json-panel">
      <summary>Raw Case JSON</summary>
      <pre>{{ formatJson(session) }}</pre>
    </details>
  </details>
</template>
