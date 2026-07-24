<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div>
        <p class="eyebrow">CrisisAgent v2.0</p>
        <h1>Agent Dashboard</h1>
        <p class="sidebar-copy">观察 Dynamic Runtime 从任务创建、Agent 执行到 Human Gate 的完整生命周期。</p>
      </div>
      <nav>
        <RouterLink to="/new">创建任务</RouterLink>
        <RouterLink to="/sessions">Session 列表</RouterLink>
      </nav>
    </aside>
    <main class="content">
      <RouterView />
    </main>
  </div>
</template>
