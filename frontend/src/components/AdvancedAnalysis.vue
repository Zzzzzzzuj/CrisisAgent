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

function yesNo(value) {
  if (value === true) {
    return "Yes";
  }
  if (value === false) {
    return "No";
  }
  return "Unknown";
}

function formatList(value) {
  return Array.isArray(value) && value.length > 0 ? value.join(" / ") : "None";
}

function retrievalLabel(rag = {}) {
  if (rag.retrieval_status === "skipped_by_gate" || rag.retrieval_skipped === true) {
    return "无需检索 / Retriever 未执行";
  }
  if (rag.retrieval_executed === true && Number(rag.count || 0) === 0) {
    return "已执行检索，但未命中相关知识";
  }
  if (rag.retrieval_executed === true && Number(rag.count || 0) > 0) {
    return "已执行检索，并命中知识来源";
  }
  if (rag.hit === true) {
    return "已命中知识来源";
  }
  return "暂无检索状态";
}

function retrievalClass(rag = {}) {
  if (rag.retrieval_status === "skipped_by_gate" || rag.retrieval_skipped === true) {
    return "skipped";
  }
  if (rag.retrieval_executed === true && Number(rag.count || 0) === 0) {
    return "no-hit";
  }
  if (rag.retrieval_executed === true && Number(rag.count || 0) > 0) {
    return "hit";
  }
  return "unknown";
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
        <details v-for="(item, index) in ragItems" :key="`rag-${index}`" class="nested-json rag-trace-card">
          <summary>{{ item.agent || "RAG" }} 检索详情</summary>
          <div class="rag-status-row">
            <span :class="['rag-status-pill', retrievalClass(item.rag)]">
              {{ retrievalLabel(item.rag) }}
            </span>
            <span>Count: {{ item.rag?.count ?? 0 }}</span>
            <span>Fallback: {{ yesNo(item.rag?.fallback_used) }}</span>
          </div>

          <section class="rag-section">
            <h5>Retrieval Gate</h5>
            <div class="rag-field-grid">
              <span>Need RAG: <strong>{{ yesNo(item.rag?.gate?.need_rag) }}</strong></span>
              <span>Current Incident: <strong>{{ yesNo(item.rag?.gate?.current_incident) }}</strong></span>
              <span>Task Intent: <strong>{{ item.rag?.gate?.task_intent || "Unknown" }}</strong></span>
              <span>Decision Path: <strong>{{ item.rag?.gate?.decision_path || "Unknown" }}</strong></span>
              <span>Intent: <strong>{{ item.rag?.gate?.intent || "Unknown" }}</strong></span>
              <span>Decision Score: <strong>{{ item.rag?.gate?.decision_score ?? "Unknown" }}</strong></span>
            </div>
            <p class="muted rag-reason">
              {{ item.rag?.gate?.reason || "旧 session 或当前 trace 未包含 Gate 解释。" }}
            </p>
            <div class="rag-signal-grid">
              <span>Current Signals: {{ formatList(item.rag?.gate?.current_incident_signals) }}</span>
              <span>Matched Signals: {{ formatList(item.rag?.gate?.matched_signals) }}</span>
              <span>Negative Signals: {{ formatList(item.rag?.gate?.negative_signals) }}</span>
            </div>
          </section>

          <section class="rag-section">
            <h5>Retrieval</h5>
            <div class="rag-field-grid">
              <span>Status: <strong>{{ item.rag?.retrieval_status || "Unknown" }}</strong></span>
              <span>Skipped: <strong>{{ yesNo(item.rag?.retrieval_skipped) }}</strong></span>
              <span>Executed: <strong>{{ yesNo(item.rag?.retrieval_executed) }}</strong></span>
              <span>Retrieval Type: <strong>{{ item.rag?.retrieval_type || "Unknown" }}</strong></span>
            </div>
            <div class="rag-sources">
              <p><strong>Sources:</strong> {{ formatList(item.rag?.sources) }}</p>
              <p><strong>Rerank Scores:</strong> {{ formatList(item.rag?.rerank_scores) }}</p>
            </div>
          </section>

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
