<script setup>
import { computed, ref, watch } from "vue";

const props = defineProps({
  approval: {
    type: Object,
    default: () => ({}),
  },
  finalStatement: {
    type: String,
    default: "",
  },
  status: {
    type: String,
    default: "",
  },
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: "",
  },
});

const emit = defineEmits(["approve", "reject"]);

const reviewer = ref("企业审核人");
const comment = ref("");
const isWaitingHuman = computed(() => props.status === "WAITING_HUMAN");
const reviewStatus = computed(() => (isWaitingHuman.value ? "待人工审核" : "审核已记录"));

watch(
  () => props.approval,
  (approval) => {
    if (approval?.reviewer) {
      reviewer.value = approval.reviewer;
    }
    if (approval?.comment) {
      comment.value = approval.comment;
    }
  },
  { immediate: true },
);

function submit(decision) {
  emit(decision, {
    reviewer: reviewer.value,
    comment: comment.value,
  });
}
</script>

<template>
  <article class="action-panel review-action-panel" :class="{ pending: isWaitingHuman }">
    <div class="page-header compact-page-header">
      <div>
        <p class="eyebrow">需要你处理</p>
        <h3>{{ isWaitingHuman ? "请审核 AI 响应结果" : "人工审核记录" }}</h3>
      </div>
      <span class="status-pill">{{ reviewStatus }}</span>
    </div>

    <div class="review-note compact-review-note">
      <p><strong>处理原因：</strong>{{ approval.reason || "当前案例无需人工审核或已完成审核。" }}</p>
      <p v-if="approval.reviewer"><strong>审核人：</strong>{{ approval.reviewer }}</p>
      <p v-if="approval.comment"><strong>审核意见：</strong>{{ approval.comment }}</p>
      <p v-if="approval.decision"><strong>审核结果：</strong>{{ approval.decision === "approved" ? "已批准" : approval.decision === "rejected" ? "已拒绝" : approval.decision }}</p>
    </div>

    <details class="review-statement compact-review-statement">
      <summary>查看待审核声明</summary>
      <p>{{ finalStatement || "暂无可审核声明。" }}</p>
    </details>

    <div v-if="isWaitingHuman" class="review-form compact-review-form">
      <input v-model="reviewer" placeholder="审核人" />
      <textarea v-model="comment" rows="2" placeholder="请输入审核意见，例如：同意发布，建议同步客服 FAQ。" />
      <p v-if="error" class="action-error" role="alert">{{ error }}</p>
      <div class="action-panel-footer review-actions">
        <button class="quiet-button" :disabled="loading" @click="submit('reject')">{{ loading ? "正在提交..." : "拒绝" }}</button>
        <button class="primary-button" :disabled="loading" @click="submit('approve')">{{ loading ? "正在提交..." : "批准结果" }}</button>
      </div>
    </div>
    <p v-else-if="error" class="action-error" role="alert">{{ error }}</p>
  </article>
</template>
