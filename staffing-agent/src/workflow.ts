import { DatabaseSync } from 'node:sqlite';
import { randomUUID } from 'node:crypto';
import { searchProfiles, searchWithEmbeddings, validateRequest } from './search.ts';
import type { Profile, SearchRequest, SearchResponse, EmbeddingProvider } from './search.ts';
import { referencePlanner, RetryableError, validateToolCall } from './planner.ts';
import type { Planner } from './planner.ts';
export type Principal = { tenantId: string; subject: string; roles: ('operator' | 'approver')[] };
type JobRow = { id: string; tenant_id: string; idempotency_key: string; request: string; status: string; attempts: number; next_at: number; lease_until: number; lease_token: string | null; result: string | null; draft: string | null };
export class Workflow {
  db: DatabaseSync;
  constructor(path: string) {
    this.db = new DatabaseSync(path);
    this.db.exec(`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=3000; PRAGMA foreign_keys=ON;
      CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, idempotency_key TEXT NOT NULL,
        request TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, next_at INTEGER NOT NULL,
        lease_until INTEGER NOT NULL DEFAULT 0, lease_token TEXT, result TEXT, draft TEXT, UNIQUE(tenant_id,idempotency_key));
      CREATE TABLE IF NOT EXISTS events(sequence INTEGER PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), at INTEGER NOT NULL,
        kind TEXT NOT NULL, detail TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS outbox(job_id TEXT PRIMARY KEY REFERENCES jobs(id), tenant_id TEXT NOT NULL,
        approved_at INTEGER NOT NULL, payload TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS jobs_ready ON jobs(status,next_at,lease_until);`);
  }
  close() { this.db.close(); }
  transaction<T>(fn: () => T): T {
    this.db.exec('BEGIN IMMEDIATE');
    try { const result = fn(); this.db.exec('COMMIT'); return result; }
    catch (e) { this.db.exec('ROLLBACK'); throw e; }
  }
  event(id: string, at: number, kind: string, detail: Record<string, unknown> = {}) {
    this.db.prepare('INSERT INTO events(job_id,at,kind,detail) VALUES(?,?,?,?)').run(id, at, kind, JSON.stringify(detail));
  }
  authorize(principal: Principal, role?: 'operator' | 'approver') {
    if (!principal?.tenantId || !principal.subject || !Array.isArray(principal.roles) || (role && !principal.roles.includes(role))) throw new Error('forbidden');
  }
  submit(principal: Principal, request: Omit<SearchRequest, 'tenantId'>, idempotencyKey: string, at = Date.now()) {
    this.authorize(principal, 'operator');
    if (!idempotencyKey || idempotencyKey.length > 100 || Object.hasOwn(request, 'tenantId')) throw new Error('invalid_submission');
    const scoped = { ...request, tenantId: principal.tenantId };
    validateRequest(scoped);
    // Canonical field order makes idempotency independent of object construction order.
    const encoded = JSON.stringify({ tenantId: scoped.tenantId, role: scoped.role, state: scoped.state, shift: scoped.shift, query: scoped.query, minScore: scoped.minScore ?? 0.3 });
    return this.transaction(() => {
      const existing = this.db.prepare('SELECT id,request FROM jobs WHERE tenant_id=? AND idempotency_key=?').get(principal.tenantId, idempotencyKey) as { id: string; request: string } | undefined;
      if (existing) { if (existing.request !== encoded) throw new Error('idempotency_conflict'); return existing.id; }
      const id = randomUUID();
      this.db.prepare("INSERT INTO jobs(id,tenant_id,idempotency_key,request,status,next_at) VALUES(?,?,?,?,'queued',?)").run(id, principal.tenantId, idempotencyKey, encoded, at);
      this.event(id, at, 'queued');
      return id;
    });
  }
  load(principal: Principal, id: string) {
    this.authorize(principal);
    const job = this.db.prepare('SELECT * FROM jobs WHERE id=? AND tenant_id=?').get(id, principal.tenantId) as JobRow | undefined;
    if (!job) throw new Error('not_found');
    return { id: job.id, status: job.status, attempts: job.attempts, nextAt: job.next_at,
      result: job.result ? JSON.parse(job.result) as SearchResponse : null, draft: job.draft ? JSON.parse(job.draft) : null,
      events: this.db.prepare('SELECT at,kind,detail FROM events WHERE job_id=? ORDER BY sequence').all(job.id).map(e => ({ at: e.at, kind: e.kind, detail: JSON.parse(e.detail as string) })) };
  }
  claim(at = Date.now(), leaseMs = 60_000) {
    if (!Number.isFinite(leaseMs) || leaseMs < 1 || leaseMs > 120_000) throw new Error('invalid_lease');
    return this.transaction(() => {
      let job: JobRow | undefined;
      // Exhausted leases are terminalized without hiding later ready work.
      while (true) {
        job = this.db.prepare("SELECT * FROM jobs WHERE ((status IN ('queued','retry') AND next_at<=?) OR (status='running' AND lease_until<=?)) ORDER BY next_at,id LIMIT 1").get(at, at) as JobRow | undefined;
        if (!job) return null;
        if (job.attempts < 3) break;
        this.db.prepare("UPDATE jobs SET status='failed',lease_token=NULL,lease_until=0 WHERE id=?").run(job.id);
        this.event(job.id, at, 'failed', { code: 'attempt_budget_exhausted' });
      }
      const token = randomUUID();
      this.db.prepare("UPDATE jobs SET status='running',attempts=attempts+1,lease_token=?,lease_until=? WHERE id=?").run(token, at + leaseMs, job.id);
      this.event(job.id, at, job.status === 'running' ? 'lease_recovered' : 'claimed', { attempt: job.attempts + 1 });
      return { ...job, status: 'running', attempts: job.attempts + 1, lease_token: token, lease_until: at + leaseMs };
    });
  }
  owns(job: JobRow, at: number) {
    return !!this.db.prepare("SELECT id FROM jobs WHERE id=? AND status='running' AND lease_token=? AND lease_until>?").get(job.id, job.lease_token, at);
  }
  async executeClaim(job: JobRow, profiles: Profile[], options: { planner?: Planner; embeddings?: EmbeddingProvider; now?: () => number } = {}) {
    const now = options.now ?? Date.now;
    try {
      if (!this.owns(job, now())) return { committed: false, reason: 'lease_lost_or_cancelled' };
      const request = JSON.parse(job.request) as SearchRequest;
      if (request.tenantId !== job.tenant_id) throw new Error('corrupt_scope');
      const planner = options.planner ?? referencePlanner;
      validateToolCall(await planner.plan(request), request);
      if (!this.owns(job, now())) return { committed: false, reason: 'lease_lost_or_cancelled' };
      const result = options.embeddings ? await searchWithEmbeddings(profiles, request, options.embeddings) : searchProfiles(profiles, request);
      const draft = result.abstained ? null : { kind: 'internal_review_draft', subject: `Review ${result.results.length} fictional profiles`, profileIds: result.results.map(r => r.profileId), citations: result.results.flatMap(r => r.citations), delivery: 'simulated_only_no_recipient' };
      return this.transaction(() => {
        const at = now();
        if (!this.owns(job, at)) return { committed: false, reason: 'lease_lost_or_cancelled' };
        this.db.prepare('UPDATE jobs SET status=?,result=?,draft=?,lease_token=NULL,lease_until=0 WHERE id=?').run(result.abstained ? 'abstained' : 'awaiting_approval', JSON.stringify(result), draft ? JSON.stringify(draft) : null, job.id);
        this.event(job.id, at, 'search_completed', { count: result.results.length, planner: planner.name, retrieval: result.audit.mode });
        this.event(job.id, at, result.abstained ? 'abstained' : 'approval_required');
        return { committed: true, reason: result.abstained ? 'abstained' : 'awaiting_approval' };
      });
    } catch (error) {
      return this.transaction(() => {
        const at = now();
        if (!this.owns(job, at)) return { committed: false, reason: 'lease_lost_or_cancelled' };
        const retry = error instanceof RetryableError && job.attempts < 3;
        const delay = retry ? Math.min(30_000, 1000 * 2 ** (job.attempts - 1)) : 0;
        this.db.prepare('UPDATE jobs SET status=?,next_at=?,lease_token=NULL,lease_until=0 WHERE id=?').run(retry ? 'retry' : 'failed', at + delay, job.id);
        // Raw exceptions, prompts, tokens and profile text are deliberately absent.
        this.event(job.id, at, retry ? 'retry_scheduled' : 'failed', { code: error instanceof RetryableError ? 'dependency_unavailable' : 'validation_or_execution_rejected', backoffMs: delay });
        return { committed: true, reason: retry ? 'retry' : 'failed' };
      });
    }
  }
  async tick(profiles: Profile[], options: { planner?: Planner; embeddings?: EmbeddingProvider; now?: () => number; leaseMs?: number } = {}) {
    const job = this.claim((options.now ?? Date.now)(), options.leaseMs);
    return job ? this.executeClaim(job, profiles, options) : { committed: false, reason: 'no_work' };
  }
  approve(principal: Principal, id: string, at = Date.now()) {
    this.authorize(principal, 'approver');
    return this.transaction(() => {
      const job = this.db.prepare('SELECT * FROM jobs WHERE id=? AND tenant_id=?').get(id, principal.tenantId) as JobRow | undefined;
      if (!job) throw new Error('not_found');
      if (job.status === 'completed') return 'already_approved';
      if (job.status !== 'awaiting_approval' || !job.draft) throw new Error('not_approvable');
      this.db.prepare('INSERT INTO outbox(job_id,tenant_id,approved_at,payload) VALUES(?,?,?,?)').run(id, principal.tenantId, at, job.draft);
      this.db.prepare("UPDATE jobs SET status='completed' WHERE id=?").run(id);
      this.event(id, at, 'approved_simulated_outbox');
      return 'approved';
    });
  }
  cancel(principal: Principal, id: string, at = Date.now()) {
    this.authorize(principal, 'operator');
    return this.transaction(() => {
      const job = this.db.prepare('SELECT status FROM jobs WHERE id=? AND tenant_id=?').get(id, principal.tenantId) as {status: string} | undefined;
      if (!job) throw new Error('not_found');
      if (['completed', 'abstained', 'failed'].includes(job.status)) throw new Error('terminal_job');
      if (job.status === 'cancelled') return 'already_cancelled';
      this.db.prepare("UPDATE jobs SET status='cancelled',lease_token=NULL,lease_until=0 WHERE id=?").run(id);
      this.event(id, at, 'cancelled'); return 'cancelled';
    });
  }
  outbox(principal: Principal) {
    this.authorize(principal, 'approver');
    return this.db.prepare('SELECT job_id,approved_at,payload FROM outbox WHERE tenant_id=? ORDER BY approved_at').all(principal.tenantId).map(row => ({ jobId: row.job_id, approvedAt: row.approved_at, payload: JSON.parse(row.payload as string) }));
  }
}
