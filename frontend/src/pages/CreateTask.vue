<script setup>
import { ref, watch } from "vue";
import { useRouter } from "vue-router";

import { runDynamicTask } from "../api";

const router = useRouter();
const event = ref("");
const loading = ref(false);
const error = ref("");
const REQUEST_STORAGE_KEY = "crisisagent.pending-create-request";
let memoryRequest = null;

async function fingerprint(value) {
  const bytes = new TextEncoder().encode(value.trim());
  if (globalThis.crypto?.subtle) {
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    return [...new Uint8Array(digest)].map((part) => part.toString(16).padStart(2, "0")).join("");
  }
  return Array.from(bytes).reduce((hash, byte) => ((hash * 31 + byte) >>> 0), 2166136261).toString(16);
}

async function getClientRequestId(value) {
  const contentFingerprint = await fingerprint(value);
  try {
    const saved = JSON.parse(sessionStorage.getItem(REQUEST_STORAGE_KEY) || "null");
    if (saved?.fingerprint === contentFingerprint && saved?.id) return saved.id;
  } catch {
    if (memoryRequest?.fingerprint === contentFingerprint) return memoryRequest.id;
  }
  const id = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  memoryRequest = { id, fingerprint: contentFingerprint };
  try {
    sessionStorage.setItem(REQUEST_STORAGE_KEY, JSON.stringify(memoryRequest));
  } catch {
    // Keep retry protection for this page lifetime if browser storage is unavailable.
  }
  return id;
}

watch(event, () => {
  error.value = "";
});

async function submitCase() {
  error.value = "";
  loading.value = true;
  try {
    const clientRequestId = await getClientRequestId(event.value);
    const result = await runDynamicTask(event.value, clientRequestId);
    try {
      sessionStorage.removeItem(REQUEST_STORAGE_KEY);
    } catch {
      // The successful response already provides the durable session ID.
    }
    memoryRequest = null;
    router.push(`/cases/${result.session_id}`);
  } catch (err) {
    error.value = err.code === "ECONNABORTED"
      ? "暂时没有收到创建确认。任务可能仍在受理中；再次点击会复用本次请求标识，不会重复启动同一任务。"
      : err.response?.data?.detail || err.message || "创建请求未成功，请稍后重试。";
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
