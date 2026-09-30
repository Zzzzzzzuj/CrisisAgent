<script setup>
import { computed, ref, watch } from "vue";

const props = defineProps({
  request: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  error: { type: String, default: "" },
});

const emit = defineEmits(["provided", "unavailable"]);
const factText = ref("");
const canRespond = computed(() => Boolean(props.request?.request_id));

const question = computed(() => {
  const raw = String(props.request?.question || props.request?.claim || "请补充当前尚未确认的企业事实。");
  return raw
    .replace(/FACT_UNAVAILABLE/g, "我无法确认")
    .replace(/FACT_PROVIDED/g, "我可以提供信息")
    .replace(/FACT_INPUT|WAITING_HUMAN/gi, "待补充信息")
    .replace(/claim_index/gi, "相关事项")
    .replace(/\bP32\b/gi, "系统建议")
    .replace(/\bCoverage\b/gi, "证据覆盖情况")
    .replace(/\bCheckpoint\b/gi, "运行记录")
    .replace(/\bAgentState\b/gi, "运行状态");
});

watch(
  () => props.request?.request_id,
  () => {
    factText.value = "";
  },
);

function submitProvided() {
  const value = factText.value.trim();
  if (!value || props.loading) return;
  emit("provided", value);
}

function submitUnavailable() {
  if (props.loading) return;
  emit("unavailable");
}
</script>

<template>
  <section class="action-panel fact-action-panel" aria-labelledby="fact-action-title">
    <div class="action-panel-heading">
      <span class="action-symbol" aria-hidden="true">!</span>
      <div>
        <p class="eyebrow">需要你处理</p>
        <h3 id="fact-action-title">请补充企业内部事实</h3>
      </div>
      <span class="action-state-badge">等待补充</span>
    </div>

    <div class="fact-question">
      <span>系统需要确认</span>
      <p>{{ question }}</p>
    </div>
    <p v-if="!canRespond" class="action-error" role="alert">当前补充请求信息不完整，请刷新案例后重试。</p>

    <p class="fact-privacy-note">
      你提供的信息会作为人工提供的内容记录，不代表系统已经独立核实。暂时无法确认时，可以选择“我无法确认”。
    </p>

    <label class="fact-input-label" for="human-fact-response">补充你目前掌握的信息</label>
    <textarea
      id="human-fact-response"
      v-model="factText"
      rows="3"
      :disabled="loading"
      placeholder="请填写已知情况；如果尚无结论，请选择“我无法确认”"
    />

    <p v-if="error" class="action-error" role="alert">{{ error }}</p>
    <div class="action-panel-footer">
      <button class="quiet-button" :disabled="loading || !canRespond" @click="submitUnavailable">
        {{ loading ? "正在继续分析..." : "我无法确认" }}
      </button>
      <button class="primary-button" :disabled="loading || !canRespond || !factText.trim()" @click="submitProvided">
        {{ loading ? "正在继续分析..." : "提交并继续" }}
        <span v-if="!loading" aria-hidden="true">→</span>
      </button>
    </div>
  </section>
</template>
