export interface Target {
  id: number;
  name: string;
  url?: string | null;
  notes?: string | null;
  created_at: string;
}

export interface RunResult {
  target?: { name?: string; url?: string; notes?: string };
  [key: string]: unknown;
}

export interface Run {
  id: number;
  target_id?: number | null;
  status: string;
  result?: RunResult | null;
  error?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface Finding {
  id: number;
  run_id?: number | null;
  target_id?: number | null;
  title: string;
  description?: string | null;
  severity?: string | null;
  category?: string | null;
  affected?: string | null;
  cvss_score?: number | null;
  cvss_vector?: string | null;
  cves?: string[] | null;
  known_exploits?: string[] | null;
  remediation?: string | null;
  references?: string[] | null;
  confidence: number;
  status: string;
  score?: number | null;
  requires_human_review: boolean;
  validated_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface StreamEvent {
  node: string;
  update: Record<string, unknown>;
}

export interface ActiveRunInfo {
  active: boolean;
  run_id?: number | null;
  status?: string | null;
}

export interface TraceStep {
  node?: string;
  action?: string;
  provider?: string | null;
  model?: string | null;
  duration_ms?: number;
  tokens?: number;
  cost?: number;
  confidence_after?: number | null;
  [key: string]: unknown;
}

export interface HistoryEntry {
  agent?: string;
  action?: string;
  reasoning?: string;
  decision?: string;
  provider?: string | null;
  model?: string | null;
  tokens?: number;
  cost?: number;
  [key: string]: unknown;
}

export interface ChatMessage {
  agent: string;
  action: string;
  reasoning: string;
}

export interface RunLogLine {
  node: string;
  text: string;
}

export interface RunFinding {
  id?: string | number;
  title?: string;
  description?: string | null;
  severity?: string | null;
  category?: string | null;
  affected?: string | null;
  cvss_score?: number | null;
  cvss_vector?: string | null;
  cves?: string[] | null;
  known_exploits?: string[] | null;
  remediation?: string | null;
  references?: string[] | null;
  confidence?: number;
  status?: string;
  requires_human_review?: boolean;
}

export interface RunMeta {
  tokens?: number;
  cost?: number;
  target?: string;
  durationMs?: number;
  stopReason?: string;
}

export interface RunEndSignal {
  run_id: number;
  status: string;
}

export type ReportFormat = 'json' | 'markdown' | 'csv' | 'sarif';

export interface ReportSummary {
  total_findings: number;
  by_severity: Record<string, number>;
  pending_review: number;
}

export interface ReportObservability {
  tokens_used?: number;
  cost?: number;
  confidence?: number;
  stop_reason?: string;
}

export interface PendingReview {
  id: string;
  kind: string;
  context?: string;
  proposal?: Record<string, unknown>;
  created_at?: string;
}

export interface ReviewPayload {
  approval_id: string;
  approved: boolean;
  note?: string;
}

export interface Report {
  run_id: number;
  target?: string;
  status: string;
  generated_at?: string;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms?: number | null;
  summary: ReportSummary;
  findings: RunFinding[];
  observability: ReportObservability;
  trace?: TraceStep[];
  history?: HistoryEntry[];
  pending_review?: PendingReview | null;
}

export interface RunStreamOptions {
  signal?: AbortSignal;
  onStart?: (runId: number) => void;
}

export interface Composition {
  id: number;
  name: string;
  target_id?: number | null;
  status: string;
  config?: {
    archetypes?: string[];
    target?: { name?: string; url?: string; notes?: string } | null;
    devil_mode?: boolean;
  } | null;
  created_at: string;
}

export interface ExecuteResult {
  run_id: number;
  status: string;
}

export interface DashboardRun {
  id: number;
  status: string;
  target?: string | null;
  findings: number;
  by_severity?: Record<string, number>;
  cost: number;
  tokens: number;
  stop_reason?: string | null;
  created_at?: string | null;
  finished_at?: string | null;
}

export interface DashboardSummary {
  runs: { total: number; by_status: Record<string, number> };
  pending_reviews: number;
  findings: {
    total: number;
    by_severity: Record<string, number>;
    by_status: Record<string, number>;
  };
  costs: {
    total_cost: number;
    total_tokens: number;
    trace_tokens: number;
    trace_cost: number;
  };
}

export interface ProviderConfig {
  provider: string;
  models: string[];
  price_in: number;
  price_out: number;
  base_url: string;
  has_api_key: boolean;
  key_source?: 'db' | 'env' | null;
  enabled: boolean;
  usage_tokens: number;
  usage_cost: number;
}

export interface ProvidersResponse {
  providers: ProviderConfig[];
  has_encryption_configured: boolean;
}

export function listProviders(): Promise<ProvidersResponse> {
  return request<ProvidersResponse>('/providers').then((data) => ({
    providers: data.providers || [],
    has_encryption_configured: data.has_encryption_configured ?? false,
  }));
}

export function setProviderApiKey(provider: string, key: string): Promise<{ status: string }> {
  return fetch(`${BASE_URL}/providers/${provider}/api-key`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key }),
  }).then((res) => {
    if (!res.ok) return res.json().then((j) => { throw new Error(j.detail || 'Failed'); });
    return res.json();
  });
}

export function setProviderEnabled(provider: string, enabled: boolean): Promise<{ status: string }> {
  return fetch(`${BASE_URL}/providers/${provider}/enabled`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  }).then((res) => {
    if (!res.ok) return res.json().then((j) => { throw new Error(j.detail || 'Failed'); });
    return res.json();
  });
}

const BASE_URL = '/api/v1';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    ...init,
  });
  if (!response.ok) {
    let detail = `API ${path} failed: ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === 'string') detail = body.detail;
    } catch {
      // keep status-based detail
    }
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

export function listTargets(): Promise<Target[]> {
  return request<Target[]>('/targets');
}

export function createTarget(input: {
  name: string;
  url?: string;
  notes?: string;
}): Promise<Target> {
  return request<Target>('/targets', { method: 'POST', body: JSON.stringify(input) });
}

export function createRun(input: {
  target?: { name: string; url?: string; notes?: string };
  devil_mode?: boolean;
}): Promise<Run> {
  return request<Run>('/runs', { method: 'POST', body: JSON.stringify(input) });
}

export function listRuns(): Promise<Run[]> {
  return request<Run[]>('/runs');
}

export function getRun(runId: number): Promise<Run> {
  return request<Run>(`/runs/${runId}`);
}

export function listFindings(runId: number): Promise<Finding[]> {
  return request<Finding[]>(`/runs/${runId}/findings`);
}

export function getReport(runId: number): Promise<Report> {
  return request<Report>(`/runs/${runId}/report`);
}

export function getReportExport(runId: number, format: ReportFormat): Promise<string> {
  return fetch(`${BASE_URL}/runs/${runId}/export?format=${format}`, {
    credentials: 'include',
  }).then((res) => {
    if (!res.ok) {
      return res.json().then((j) => {
        throw new Error(j.detail || `Export ${format} falhou: ${res.status}`);
      });
    }
    return res.text();
  });
}

export function reviewRun(runId: number, payload: ReviewPayload): Promise<Run> {
  return request<Run>(`/runs/${runId}/review`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function listCompositions(): Promise<Composition[]> {
  return request<Composition[]>('/compositions');
}

export function getComposition(compositionId: number): Promise<Composition> {
  return request<Composition>(`/compositions/${compositionId}`);
}

export function createComposition(input: {
  name: string;
  archetypes: string[];
  target?: { name: string; url?: string; notes?: string } | null;
  devil_mode?: boolean;
}): Promise<Composition> {
  return request<Composition>('/compositions', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export function deleteComposition(compositionId: number): Promise<void> {
  return fetch(`${BASE_URL}/compositions/${compositionId}`, { method: 'DELETE' }).then(
    () => undefined,
  );
}

export function executeComposition(compositionId: number): Promise<ExecuteResult> {
  return request<ExecuteResult>(`/compositions/${compositionId}/execute`, {
    method: 'POST',
    body: JSON.stringify({}),
  });
}

export function getDashboardSummary(): Promise<DashboardSummary> {
  return request<DashboardSummary>('/dashboard/summary');
}

export function getDashboardRuns(): Promise<DashboardRun[]> {
  return request<DashboardRun[]>('/dashboard/runs');
}

export function streamRun(
  target: string,
  devilMode: boolean,
  archetypes: string[],
  onEvent: (event: StreamEvent) => void,
  onDone: (runId: number, status: string) => void,
): () => void {
  const params = new URLSearchParams({ target, devil_mode: String(devilMode) });
  if (archetypes.length > 0) {
    params.set('archetypes', archetypes.join(','));
  }
  const controller = new AbortController();
  void runStream(`/runs/stream?${params.toString()}`, onEvent, { signal: controller.signal }).then(
    (signal) => onDone(signal.run_id, signal.status),
    () => onDone(-1, 'error'),
  );
  return () => controller.abort();
}

export function getActiveRun(): Promise<ActiveRunInfo> {
  return request<ActiveRunInfo>('/runs/active');
}

export function login(password: string): Promise<{ authenticated: boolean }> {
  return request<{ authenticated: boolean }>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ password }),
  });
}

export function logout(): Promise<{ authenticated: boolean }> {
  return request<{ authenticated: boolean }>('/auth/logout', { method: 'POST' });
}

export function getMe(): Promise<{ authenticated: boolean; ui_enabled: boolean }> {
  return request<{ authenticated: boolean; ui_enabled: boolean }>('/auth/me');
}

export function cancelRun(runId: number): Promise<{ status: string; run_id: number; run_status: string }> {
  return request(`/runs/${runId}/cancel`, { method: 'POST' });
}

export async function runStream(
  path: string,
  onEvent: (event: StreamEvent) => void,
  options: RunStreamOptions = {},
): Promise<RunEndSignal> {
  const { signal, onStart } = options;
  const response = await fetch(`${BASE_URL}${path}`, { signal, credentials: 'include' });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === 'string') detail = body.detail;
    } catch {
      // keep status-based detail
    }
    throw new Error(detail);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error('Stream sem corpo de resposta.');

  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep = buffer.indexOf('\n\n');
    while (sep !== -1) {
      const raw = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const lines = raw.split('\n');
      const eventName = lines.find((l) => l.startsWith('event: '))?.slice(7);
      const data = lines.find((l) => l.startsWith('data: '))?.slice(6);
      if (eventName === 'start' && data) {
        const { run_id } = JSON.parse(data) as { run_id: number };
        onStart?.(run_id);
      } else if (eventName === 'node' && data) {
        onEvent(JSON.parse(data) as StreamEvent);
      } else if (eventName === 'done' && data) {
        return JSON.parse(data) as RunEndSignal;
      }
      sep = buffer.indexOf('\n\n');
    }
  }
  throw new Error('Stream encerrado sem evento de conclusão.');
}
