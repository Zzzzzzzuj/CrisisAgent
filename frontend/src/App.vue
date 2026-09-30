<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();
const isCasesRoute = computed(() =>
  route.path === "/" || route.path === "/cases" || route.path.startsWith("/cases/") || route.path.startsWith("/sessions"),
);
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="sidebar-brand">
        <p class="eyebrow">CrisisAgent</p>
        <h1>危机响应<br />工作台</h1>
        <p class="sidebar-copy">企业舆情风险研判与响应协作</p>
      </div>

      <nav class="sidebar-nav" aria-label="主导航">
        <p class="sidebar-section-label">工作台</p>
        <RouterLink to="/cases" :class="{ 'router-link-active': isCasesRoute }">
          <span class="nav-icon" aria-hidden="true">▦</span>危机案例
        </RouterLink>
        <RouterLink to="/new">
          <span class="nav-icon" aria-hidden="true">＋</span>新建案例
        </RouterLink>
        <span class="sidebar-divider" aria-hidden="true"></span>
        <p class="sidebar-section-label">分析与治理</p>
        <RouterLink to="/workbench">
          <span class="nav-icon" aria-hidden="true">◫</span>运营工作台
        </RouterLink>
      </nav>

      <p class="sidebar-footnote">证据驱动 · 人工把关</p>
    </aside>

    <main class="content">
      <RouterView />
    </main>
  </div>
</template>
