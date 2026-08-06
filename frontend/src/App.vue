<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div>
        <p class="eyebrow">CrisisAgent</p>
        <h1>企业危机响应平台</h1>
        <p class="sidebar-copy">
          面向公关、法务和管理层的危机案例工作台，聚焦风险研判、AI 声明、人工审核和响应复盘。
        </p>
      </div>

      <nav>
        <RouterLink to="/cases">危机案例</RouterLink>
        <RouterLink to="/new">新建案例</RouterLink>
      </nav>
    </aside>

    <main class="content">
      <RouterView />
    </main>
  </div>
</template>
