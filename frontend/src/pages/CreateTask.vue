<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";

import { runDynamicTask } from "../api";

const router = useRouter();
const event = ref("");
const loading = ref(false);
const error = ref("");

async function submitCase() {
  error.value = "";
  loading.value = true;
  try {
    const result = await runDynamicTask(event.value);
    router.push(`/cases/${result.session_id}`);
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || "创建危机案例失败";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <section class="case-center">
    <div class="product-hero compact-hero">
      <div>
        <p class="eyebrow">New Crisis Case</p>
        <h2>创建危机响应案例</h2>
        <p class="muted">录入正在发生的危机事件，系统会生成风险研判、AI 声明和审核流程。</p>
      </div>
    </div>

    <article class="page-card intake-card single-intake">
      <h3>事件输入</h3>
      <label class="field-label" for="event">危机事件描述</label>
      <textarea
        id="event"
        v-model="event"
        rows="10"
        placeholder="例如：某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。"
      />
      <button class="primary-button" :disabled="loading || !event.trim()" @click="submitCase">
        {{ loading ? "正在生成响应方案..." : "生成响应方案并进入详情" }}
      </button>
      <p v-if="error" class="error">{{ error }}</p>
    </article>
  </section>
</template>
