<script setup>
import { computed } from "vue";

const props = defineProps({
  status: { type: String, default: "" },
  waitType: { type: String, default: "" },
  trace: { type: Array, default: () => [] },
  failedAgents: { type: Array, default: () => [] },
});

const steps = ["事件分析", "声明草稿", "风险与合规", "人工处理", "完成"];

const states = computed(() => {
  if (props.status === "COMPLETED") return steps.map(() => "completed");
  if (props.status === "WAITING_HUMAN") {
    const current = props.waitType === "FACT_INPUT" ? 2 : 3;
    return steps.map((_, index) => (index < current ? "completed" : index === current ? "current" : "pending"));
  }

  const failed = props.status === "FAILED" || props.status === "REJECTED";
  const failedTrace = props.trace.find((item) => item?.status === "failed" || item?.error);
  const failedIndex = failed ? locateStep(traceName(failedTrace) || props.failedAgents.join(" ")) : -1;
  if (failed) {
    const target = props.status === "REJECTED" ? 3 : failedIndex < 0 ? 2 : failedIndex;
    return steps.map((_, index) => (index < target ? "completed" : index === target ? "failed" : "pending"));
  }

  const latest = [...props.trace].reverse().find((item) => item && locateStep(traceName(item)) >= 0);
  const currentIndex = latest ? locateStep(traceName(latest)) : 0;
  return steps.map((_, index) => (index < currentIndex ? "completed" : index === currentIndex ? "current" : "pending"));
});

function traceName(item) {
  return [item?.agent, item?.agent_name, item?.name, item?.node].filter(Boolean).join(" ").toLowerCase();
}

function locateStep(value) {
  const name = String(value || "").toLowerCase();
  if (name.includes("sentiment") || name.includes("情感") || name.includes("triage")) return 0;
  if (name.includes("writer") && !name.includes("v2")) return 1;
  if (name.includes("redteam") || name.includes("legal") || name.includes("法务")) return 2;
  if (name.includes("writer_v2") || name.includes("writer v2") || name.includes("decision") || name.includes("review")) return 2;
  return -1;
}
</script>

<template>
  <nav class="workflow-stepper" aria-label="危机响应流程进度">
    <div v-for="(step, index) in steps" :key="step" class="workflow-step" :class="`step-${states[index]}`" :aria-current="states[index] === 'current' ? 'step' : undefined">
      <span class="workflow-step-marker" aria-hidden="true">
        {{ states[index] === "completed" ? "✓" : states[index] === "failed" ? "!" : index + 1 }}
      </span>
      <span class="workflow-step-label">{{ step }}</span>
    </div>
  </nav>
</template>
