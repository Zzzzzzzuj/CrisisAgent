<script setup>
const props = defineProps({
  status: {
    type: String,
    default: "",
  },
});

const steps = [
  "事件分析",
  "回应生成",
  "合规审核",
  "人工审批",
  "完成",
];

function stepState(index) {
  if (props.status === "FAILED") {
    return index <= 3 ? "done" : "blocked";
  }
  if (props.status === "WAITING_HUMAN") {
    return index < 3 ? "done" : index === 3 ? "active" : "pending";
  }
  if (props.status === "COMPLETED") {
    return "done";
  }
  if (props.status === "RUNNING") {
    return index <= 2 ? "active" : "pending";
  }
  return index === 0 ? "active" : "pending";
}
</script>

<template>
  <article class="page-card stepper-card">
    <p class="eyebrow">Response Workflow</p>
    <h3>业务流程</h3>
    <div class="stepper">
      <div v-for="(step, index) in steps" :key="step" class="step" :class="stepState(index)">
        <span>{{ index + 1 }}</span>
        <strong>{{ step }}</strong>
      </div>
    </div>
  </article>
</template>
