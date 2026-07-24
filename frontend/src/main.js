import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";

import App from "./App.vue";
import CreateTask from "./pages/CreateTask.vue";
import SessionDetail from "./pages/SessionDetail.vue";
import SessionList from "./pages/SessionList.vue";
import "./styles.css";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/new" },
    { path: "/new", component: CreateTask },
    { path: "/sessions", component: SessionList },
    { path: "/sessions/:sessionId", component: SessionDetail, props: true },
  ],
});

createApp(App).use(router).mount("#app");
