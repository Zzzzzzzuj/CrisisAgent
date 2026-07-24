<script setup>
import { onMounted, ref } from "vue";
import { RouterLink } from "vue-router";

import { listDynamicSessions } from "../api";

const sessions = ref([]);
const loading = ref(false);
const error = ref("");

async function loadSessions() {
  loading.value = true;
  error.value = "";
  try {
    sessions.value = await listDynamicSessions();
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || "加载 Session 失败";
  } finally {
    loading.value = false;
  }
}

onMounted(loadSessions);
</script>

<template>
  <section class="page-card">
    <div class="page-header">
      <div>
        <p class="eyebrow">Runtime Sessions</p>
        <h2>Session 列表</h2>
      </div>
      <button class="ghost-button" @click="loadSessions">刷新</button>
    </div>

    <p v-if="loading" class="muted">加载中...</p>
    <p v-if="error" class="error">{{ error }}</p>

    <div v-if="!loading && sessions.length === 0" class="empty-state">暂无动态任务，先创建一个。</div>

    <div v-for="session in sessions" :key="session.session_id" class="session-row">
      <div>
        <RouterLink class="session-link" :to="`/sessions/${session.session_id}`">
          {{ session.session_id }}
        </RouterLink>
        <p class="muted">{{ session.event || "无事件摘要" }}</p>
      </div>
      <div class="row-meta">
        <span class="status-pill">{{ session.status || "UNKNOWN" }}</span>
        <small>{{ session.created_time || "created_time 未记录" }}</small>
      </div>
    </div>
  </section>
</template>
