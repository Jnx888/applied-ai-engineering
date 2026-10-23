import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { Workflow } from '../src/workflow.ts';
import type { Principal } from '../src/workflow.ts';
import { RetryableError } from '../src/planner.ts';
import type { Profile } from '../src/search.ts';
const profiles: Profile[] = JSON.parse(readFileSync(new URL('../data/profiles.json', import.meta.url), 'utf8'));
const operator: Principal = { tenantId: 'hospital-demo-a', subject: 'fictional-operator', roles: ['operator'] };
const approver: Principal = { ...operator, subject: 'fictional-reviewer', roles: ['approver'] };
const other: Principal = { tenantId: 'hospital-demo-b', subject: 'fictional-other', roles: ['operator', 'approver'] };
const request = { role: 'RN', state: 'CA', shift: 'night', query: 'ICU ventilator ACLS' };
function fixture(t: { after: (fn: () => void) => void }) {
  const dir = mkdtempSync(join(tmpdir(), 'staffing-reference-'));
  const path = join(dir, 'state.sqlite'); const db = new Workflow(path);
  t.after(() => { try { db.close(); } catch {} rmSync(dir, { recursive: true, force: true }); });
  return { db, path };
}
test('human approval is required; approval and outbox are idempotent and tenant scoped', async t => {
  const { db } = fixture(t), id = db.submit(operator, request, 'demo', 1000);
  assert.equal(db.submit(operator, { query: request.query, shift: 'night', state: 'CA', role: 'RN' }, 'demo', 1000), id);
  assert.throws(() => db.submit(operator, { ...request, query: 'other' }, 'demo', 1000), /idempotency_conflict/);
  assert.equal(db.outbox(approver).length, 0);
  assert.throws(() => db.approve(approver, id), /not_approvable/);
  await db.tick(profiles, { now: () => 1000 });
  assert.equal(db.load(operator, id).status, 'awaiting_approval');
  assert.equal(db.outbox(approver).length, 0);
  assert.throws(() => db.load(other, id), /not_found/);
  assert.throws(() => db.approve(other, id), /not_found/);
  assert.throws(() => db.cancel(other, id), /not_found/);
  assert.throws(() => db.approve(operator, id), /forbidden/);
  assert.throws(() => db.submit(operator, { ...request, tenantId: 'hospital-demo-b' } as never, 'scope'), /invalid_submission/);
  assert.equal(db.approve(approver, id, 1001), 'approved');
  assert.equal(db.approve(approver, id, 1002), 'already_approved');
  assert.equal(db.outbox(approver).length, 1); assert.equal(db.outbox(other).length, 0);
});
test('approval transaction rolls back outbox if terminal checkpoint fails', async t => {
  const { db } = fixture(t), id = db.submit(operator, request, 'atomic', 1000);
  await db.tick(profiles, { now: () => 1000 });
  db.db.exec("CREATE TRIGGER reject_completion BEFORE UPDATE OF status ON jobs WHEN NEW.status='completed' BEGIN SELECT RAISE(ABORT,'injected failure'); END");
  assert.throws(() => db.approve(approver, id, 1001));
  assert.equal(db.outbox(approver).length, 0); assert.equal(db.load(operator, id).status, 'awaiting_approval');
});
test('actual child-process death recovers committed lease from SQLite after restart', async t => {
  const { db, path } = fixture(t), id = db.submit(operator, request, 'crash', 1000);
  const child = spawnSync(process.execPath, [fileURLToPath(new URL('./crash-worker.ts', import.meta.url)), path], { encoding: 'utf8' });
  assert.equal(child.status, 17);
  const restarted = new Workflow(path);
  try {
    assert.equal(restarted.load(operator, id).status, 'running');
    assert.equal((await restarted.tick(profiles, { now: () => 1050 })).reason, 'no_work');
    await restarted.tick(profiles, { now: () => 1101 });
    const result = restarted.load(operator, id);
    assert.equal(result.status, 'awaiting_approval'); assert.equal(result.attempts, 2);
    assert.ok(result.events.some(e => e.kind === 'lease_recovered'));
  } finally { restarted.close(); }
});
test('two SQLite connections cannot own same lease; stale completion is fenced', async t => {
  const { db, path } = fixture(t), id = db.submit(operator, request, 'fencing', 1000);
  const second = new Workflow(path);
  try {
    const stale = db.claim(1000, 10)!; assert.equal(second.claim(1001, 10), null);
    const fresh = second.claim(1011, 10)!;
    assert.equal((await db.executeClaim(stale, profiles, { now: () => 1012 })).committed, false);
    assert.equal((await second.executeClaim(fresh, profiles, { now: () => 1012 })).committed, true);
    assert.equal(db.load(operator, id).status, 'awaiting_approval');
  } finally { second.close(); }
});
test('cancel interrupts an in-flight worker and is idempotent', async t => {
  const { db } = fixture(t), id = db.submit(operator, request, 'cancel', 1000), claim = db.claim(1000)!;
  db.cancel(operator, id, 1001); assert.equal(db.cancel(operator, id, 1002), 'already_cancelled');
  assert.equal((await db.executeClaim(claim, profiles, { now: () => 1002 })).committed, false);
  assert.equal(db.load(operator, id).status, 'cancelled'); assert.equal(db.outbox(approver).length, 0);
});
test('cancelled claims skip adapters; cancellation during planning skips embeddings', async t => {
  const { db } = fixture(t), id = db.submit(operator, request, 'cancel-before-model', 1000), claim = db.claim(1000)!;
  db.cancel(operator, id, 1001);
  let calls = 0;
  await db.executeClaim(claim, profiles, { planner: { name: 'spy', async plan() { calls++; return null; } }, now: () => 1002 });
  assert.equal(calls, 0);
  const secondId = db.submit(operator, request, 'cancel-during-model', 1003), second = db.claim(1003)!;
  await db.executeClaim(second, profiles, {
    planner: { name: 'cancel-during-plan', async plan() { db.cancel(operator, secondId, 1004); return { name: 'search_profiles', arguments: request }; } },
    embeddings: { model: 'spy', async embed() { calls++; return []; } }, now: () => 1004
  });
  assert.equal(calls, 0);
});
test('exhausted stale lease does not hide another ready job', t => {
  const { db } = fixture(t), exhausted = db.submit(operator, request, 'exhausted', 1000);
  db.claim(1000, 1); db.claim(1001, 1); db.claim(1002, 1);
  const ready = db.submit(operator, request, 'ready', 1003);
  assert.equal(db.claim(1003, 10)?.id, ready); assert.equal(db.load(operator, exhausted).status, 'failed');
});
test('transient failures back off, recover and stop after bounded budget', async t => {
  const { db } = fixture(t), id = db.submit(operator, request, 'retry', 1000);
  const failing = { name: 'fault-injection-test', async plan() { throw new RetryableError(); } };
  await db.tick(profiles, { planner: failing, now: () => 1000 });
  assert.equal(db.load(operator, id).nextAt, 2000);
  assert.equal((await db.tick(profiles, { now: () => 1999 })).reason, 'no_work');
  await db.tick(profiles, { now: () => 2000 }); assert.equal(db.load(operator, id).status, 'awaiting_approval');
  const stop = db.submit(operator, request, 'budget', 3000);
  await db.tick(profiles, { planner: failing, now: () => 3000 });
  await db.tick(profiles, { planner: failing, now: () => 4000 });
  await db.tick(profiles, { planner: failing, now: () => 6000 });
  assert.equal(db.load(operator, stop).status, 'failed'); assert.equal(db.load(operator, stop).attempts, 3);
});
test('unknown tools, malformed and tenant-expanding tool arguments fail closed', async t => {
  const { db } = fixture(t);
  const invalid = [ { name: 'send_email', arguments: {} }, { name: 'search_profiles', arguments: { ...request, tenantId: other.tenantId } }, { name: 'search_profiles', arguments: { ...request, state: 'TX' } }, null ];
  for (const [i, proposal] of invalid.entries()) {
    const id = db.submit(operator, request, `invalid-${i}`, 1000);
    await db.tick(profiles, { planner: { name: 'adversarial-test', async plan() { return proposal; } }, now: () => 1000 });
    assert.equal(db.load(operator, id).status, 'failed');
  }
  assert.equal(db.outbox(approver).length, 0);
});
test('abstention produces no draft or approvable action; SQL-like input remains data', async t => {
  const { db } = fixture(t), id = db.submit(operator, { ...request, query: "'; DROP TABLE jobs;--" }, 'sql-data', 1000);
  await db.tick(profiles, { now: () => 1000 });
  assert.equal(db.load(operator, id).status, 'abstained'); assert.equal(db.load(operator, id).draft, null);
  assert.throws(() => db.approve(approver, id), /not_approvable/);
  assert.ok(db.submit(operator, request, 'table-still-exists', 1000));
});
