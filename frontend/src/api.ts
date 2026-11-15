import type { components } from './api.generated';
export type Run = components['schemas']['RunDetail'];
export type RunEvent = components['schemas']['RunEventResponse'];
export type RunPage = components['schemas']['RunPage'];
export type Summary = components['schemas']['DashboardSummary'];
export type Review = components['schemas']['ReviewView'];
export type ReviewBody = components['schemas']['ReviewResponse'];
export type Intake = components['schemas']['IntakeResponse'];
export type POPage = components['schemas']['POPage'];
export type POLedger = components['schemas']['POLedgerView'];
export type Access = components['schemas']['AccessView'];
export type SubmitterRun = components['schemas']['SubmitterRunDetail'];
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function request(path: string, token: string, init: RequestInit = {}) {
  let response: Response;
  try {
    response = await fetch('/api/v1' + path, {
      ...init,
      headers: { ...init.headers, Authorization: `Bearer ${token}` },
      cache: 'no-store',
    });
  } catch (e) {
    if (init.signal?.aborted) throw e;
    throw new ApiError(0, 'Cannot reach the server. Check your connection and try again.');
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const detail =
      typeof data?.detail === 'string'
        ? data.detail
        : typeof data?.detail?.message === 'string'
          ? data.detail.message
          : typeof data?.detail?.[0]?.msg === 'string'
            ? data.detail[0].msg
            : undefined;
    const messages: Record<number, string> = {
      401: 'Workspace access was rejected. Re-enter your workspace token.',
      403: 'Reviewer access was rejected. Use the separate authorized reviewer token.',
      404: 'This record is no longer available. Refresh the workspace.',
      409: 'The record changed or a response is already recorded. Refresh before taking another action.',
    };
    throw new ApiError(
      response.status,
      (data?.detail?.code === 'ROLE_FORBIDDEN' ? detail : messages[response.status]) ??
        detail ??
        `Request failed (${response.status}).`,
    );
  }
  return response;
}
export async function api<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  return (await request(path, token, init)).json() as Promise<T>;
}
export function mergeEvents(current: RunEvent[], incoming: RunEvent[]) {
  const values = new Map(current.map((e) => [e.seq, e]));
  for (const event of incoming) values.set(event.seq, event);
  return [...values.values()].sort((a, b) => a.seq - b.seq);
}
export async function streamEvents(
  runId: string,
  token: string,
  cursor: number,
  signal: AbortSignal,
  onEvent: (event: RunEvent) => void,
  onOpen: () => void,
) {
  const response = await request(`/runs/${runId}/events/stream?after_seq=${cursor}`, token, {
    signal,
    headers: { Accept: 'text/event-stream', 'Last-Event-ID': String(cursor) },
  });
  if (!response.body || !response.headers.get('content-type')?.includes('text/event-stream'))
    throw new Error('Live stream unavailable');
  onOpen();
  const reader = response.body.getReader(),
    decoder = new TextDecoder();
  let buffer = '',
    kind = '',
    id = '',
    data: string[] = [],
    end = 'reconnect';
  function line(value: string) {
    value = value.replace(/\r$/, '');
    if (!value) {
      if (kind === 'run-event' && data.length) {
        const event: RunEvent = JSON.parse(data.join('\n'));
        if (event.run_id !== runId || event.seq !== Number(id) || !Number.isSafeInteger(event.seq))
          throw new Error('Invalid persisted event envelope');
        if (event.seq > cursor) {
          cursor = event.seq;
          onEvent(event);
        }
      } else if (kind === 'stream-end' && data.length) end = JSON.parse(data.join('\n')).reason;
      kind = '';
      id = '';
      data = [];
    } else if (value.startsWith('event:')) kind = value.slice(6).trimStart();
    else if (value.startsWith('id:')) id = value.slice(3).trimStart();
    else if (value.startsWith('data:')) data.push(value.slice(5).trimStart());
  }
  try {
    while (!signal.aborted) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let index: number;
      while ((index = buffer.indexOf('\n')) >= 0) {
        line(buffer.slice(0, index));
        buffer = buffer.slice(index + 1);
      }
      if (done) break;
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
  return end;
}
export const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : 'Something went wrong. Try again.';
export const dateTime = (value: string) =>
  new Date(value).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
export const duration = (ms: number | null | undefined) =>
  ms == null ? 'Not measured' : ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
export function money(value: string | null | undefined, currency = 'INR') {
  if (value == null) return 'Unknown';
  if (!currency) return `Currency missing · ${value}`;
  if (!/^\d+(\.\d+)?$/.test(value)) return `${currency} ${value}`;
  const [whole, fraction = '00'] = value.split('.');
  return `${currency === 'INR' ? '₹' : currency + ' '}${new Intl.NumberFormat('en-IN').format(BigInt(whole))}.${fraction.padEnd(2, '0')}`;
}
