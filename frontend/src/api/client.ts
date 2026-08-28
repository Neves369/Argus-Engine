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

const BASE_URL = '/api/v1';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!response.ok) {
    throw new Error(`API ${path} failed: ${response.status}`);
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
  const source = new EventSource(`${BASE_URL}/runs/stream?${params.toString()}`);

  source.addEventListener('node', (rawEvent) => {
    const event = rawEvent as MessageEvent;
    onEvent(JSON.parse(event.data as string) as StreamEvent);
  });

  source.addEventListener('done', (rawEvent) => {
    const event = rawEvent as MessageEvent;
    const data = JSON.parse(event.data as string) as { run_id: number; status: string };
    onDone(data.run_id, data.status);
    source.close();
  });

  source.onerror = () => {
    source.close();
  };

  return () => source.close();
}
