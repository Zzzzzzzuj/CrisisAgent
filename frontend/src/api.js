import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "",
  timeout: 120000,
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

export function getRuntimeMetrics() {
  return api.get("/api/metrics/runtime").then((response) => response.data);
}

export function approveDynamicSession(sessionId, payload) {
  return api.post(`/api/dynamic/${sessionId}/approve`, payload).then((response) => response.data);
}

export function rejectDynamicSession(sessionId, payload) {
  return api.post(`/api/dynamic/${sessionId}/reject`, payload).then((response) => response.data);
}

export function listSources() {
  return api.get("/api/sources").then((response) => response.data);
}

export function createSource(payload) {
  return api.post("/api/sources", payload).then((response) => response.data);
}

export function updateSource(sourceId, payload) {
  return api.patch(`/api/sources/${sourceId}`, payload).then((response) => response.data);
}

export function testSource(sourceId) {
  return api.post(`/api/sources/${sourceId}/test`).then((response) => response.data);
}

export function runIngestion(payload) {
  return api.post("/api/ingestion/run", payload).then((response) => response.data);
}

export function listIngestionRuns() {
  return api.get("/api/ingestion/runs").then((response) => response.data);
}

export function getIngestionRun(runId) {
  return api.get(`/api/ingestion/runs/${runId}`).then((response) => response.data);
}

export function createEventFromIngestionRun(payload) {
  return api.post("/api/events/from-ingestion-run", payload).then((response) => response.data);
}

export function listEvents(query = {}) {
  return api.get("/api/events", { params: query }).then((response) => response.data);
}

export function getEvent(eventId) {
  return api.get(`/api/events/${eventId}`).then((response) => response.data);
}

export function updateEvent(eventId, payload) {
  return api.patch(`/api/events/${eventId}`, payload).then((response) => response.data);
}

export function archiveEvent(eventId) {
  return api.post(`/api/events/${eventId}/archive`).then((response) => response.data);
}

export function runEventAgent(eventId, payload = {}) {
  return api.post(`/api/events/${eventId}/run`, payload).then((response) => response.data);
}

export function getEventRun(eventId) {
  return api.get(`/api/events/${eventId}/run`).then((response) => response.data);
}

export function getEventTrace(eventId) {
  return api.get(`/api/events/${eventId}/trace`).then((response) => response.data);
}

export function getEventReview(eventId) {
  return api.get(`/api/events/${eventId}/review`).then((response) => response.data);
}

export function getEventReport(eventId, format = "json") {
  return api.get(`/api/events/${eventId}/report`, { params: { format } }).then((response) => response.data);
}

export function getDashboardOverview() {
  return api.get("/api/dashboard/overview").then((response) => response.data);
}

export function getDashboardSeverity() {
  return api.get("/api/dashboard/severity").then((response) => response.data);
}

export function getDashboardTrends() {
  return api.get("/api/dashboard/trends").then((response) => response.data);
}

export function getDashboardSourceHealth() {
  return api.get("/api/dashboard/source-health").then((response) => response.data);
}

export function getDashboardReviewQueue() {
  return api.get("/api/dashboard/review-queue").then((response) => response.data);
}
