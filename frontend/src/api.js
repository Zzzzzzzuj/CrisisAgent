import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "",
  timeout: 20000,
});

export function runDynamicTask(event) {
  return api.post("/api/dynamic/run", { event }).then((response) => response.data);
}

export function listDynamicSessions() {
  return api.get("/api/dynamic/sessions").then((response) => response.data);
}

export function getDynamicSession(sessionId) {
  return api.get(`/api/dynamic/${sessionId}`).then((response) => response.data);
}

export function getDynamicMetrics(sessionId) {
  return api.get(`/api/dynamic/${sessionId}/metrics`).then((response) => response.data);
}

export function approveDynamicSession(sessionId, payload) {
  return api.post(`/api/dynamic/${sessionId}/approve`, payload).then((response) => response.data);
}

export function rejectDynamicSession(sessionId, payload) {
  return api.post(`/api/dynamic/${sessionId}/reject`, payload).then((response) => response.data);
}
