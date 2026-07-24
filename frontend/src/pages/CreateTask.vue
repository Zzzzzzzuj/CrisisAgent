<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";

import { runDynamicTask } from "../api";

const router = useRouter();
const event = ref("某食品品牌被爆使用过期原料，偷拍视频在网上传播，网友要求监管介入。");
const loading = ref(false);
const error = ref("");
const result = ref(null);

async function submitTask() {
  error.value = "";
  result.value = null;
  loading.value = true;
  try {
    result.value = await runDynamicTask(event.value);
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || "创建任务失败";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <section class="page-card hero-card">
    <p class="eyebrow">Create Runtime</p>
    <h2>创建动态 Agent 任务</h2>
    <p class="muted">输入企业危机事件，触发 Planner、Executor、AgentState 和 Human Gate。</p>

    <label class="field-label" for="event">危机事件</label>
    <textarea id="event" v-model="event" rows="6" placeholder="输入危机事件描述" />

    <button class="primary-button" :disabled="loading || !event.trim()" @click="submitTask">
      {{ loading ? "运行中..." : "启动 Dynamic Runtime" }}
    </button>

    <p v-if="error" class="error">{{ error }}</p>

    <div v-if="result" class="result-panel">
      <p><strong>session_id:</strong> {{ result.session_id }}</p>
      <p><strong>status:</strong> <span class="status-pill">{{ result.state_status || result.status }}</span></p>
      <button class="ghost-button" @click="router.push(`/sessions/${result.session_id}`)">查看详情</button>
    </div>
  </section>
</template>
