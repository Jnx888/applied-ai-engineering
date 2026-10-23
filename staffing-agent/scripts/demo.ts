import { readFileSync, writeFileSync, mkdirSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { Workflow } from '../src/workflow.ts';
import type { Principal } from '../src/workflow.ts';
import { RetryableError } from '../src/planner.ts';
import { evaluate, profiles, scenarios } from './evaluate.ts';
const tests = spawnSync(process.execPath, ['--test', '--test-reporter=tap', 'tests/*.test.ts'], { cwd: fileURLToPath(new URL('../', import.meta.url)), encoding: 'utf8' });
if (tests.status !== 0) throw new Error('test_suite_failed; run npm test for diagnostics');
const passed = Number(tests.stdout.match(/^# pass (\d+)/m)?.[1]);
const failed = Number(tests.stdout.match(/^# fail (\d+)/m)?.[1]);
if (!Number.isFinite(passed) || failed !== 0) throw new Error('test_summary_missing');
const dir = mkdtempSync(join(tmpdir(), 'staffing-evidence-')), dbPath = join(dir, 'state.sqlite');
const principal: Principal = { tenantId: 'hospital-demo-a', subject: 'fictional-demo-operator', roles: ['operator', 'approver'] };
const { tenantId, ...request } = scenarios[0].request;
let workflow = new Workflow(dbPath);
try {
  const id = workflow.submit(principal, request, 'crash-restart-demo', 1000); workflow.close();
  const crash = spawnSync(process.execPath, [fileURLToPath(new URL('../tests/crash-worker.ts', import.meta.url)), dbPath], { encoding: 'utf8' });
  if (crash.status !== 17) throw new Error('expected_process_death_not_observed');
  workflow = new Workflow(dbPath);
  const afterCrash = workflow.load(principal, id).status;
  await workflow.tick(profiles, { now: () => 1101 });
  const afterRecovery = workflow.load(principal, id).status, outboxBeforeApproval = workflow.outbox(principal).length;
  workflow.approve(principal, id, 1102); workflow.approve(principal, id, 1103);
  const completed = workflow.load(principal, id);
  const retryId = workflow.submit(principal, request, 'retry-demo', 2000);
  await workflow.tick(profiles, { now: () => 2000, planner: { name: 'controlled-transient-failure', async plan() { throw new RetryableError(); } } });
  await workflow.tick(profiles, { now: () => 3000 });
  const retried = workflow.load(principal, retryId);
  const evaluation = evaluate();
  const report = {
    schemaVersion: 1, generatedAt: new Date().toISOString(), title: 'Staffing Workbench',
    plannerStatus: 'deterministic reference planner verified; not a live LLM', modelValidation: 'Optional local-model evidence, if run, is in live-model.json. Learned embedding quality is not validated.',
    fixtureScope: evaluation.fixtureScope, profiles, scenarios: evaluation.scenarios, metrics: evaluation.metrics,
    unitTests: { passed, failed, runtime: process.version, actualChildProcessCrashTest: true },
    durableRuns: [
      { id: 'process-crash-restart', storage: 'SQLite WAL', observedProcessExitCode: crash.status, afterCrash, afterRecovery, afterApproval: completed.status, outboxBeforeApproval, outboxAfterDuplicateApproval: workflow.outbox(principal).length,
        trace: completed.events.map(e => ({ tMs: Number(e.at) - 1000, kind: e.kind, detail: e.detail })) },
      { id: 'transient-failure-retry', status: retried.status, attempts: retried.attempts, trace: retried.events.map(e => ({ tMs: Number(e.at) - 2000, kind: e.kind, detail: e.detail })) }
    ],
    moduleProvenance: { file: 'src/search.ts', sha256: createHash('sha256').update(readFileSync(new URL('../src/search.ts', import.meta.url))).digest('hex') },
    limitations: ['Fictional profiles only; no real candidates, PHI, contact data or outreach.', 'Browser tenant selector is an educational simulation, not authentication.', 'Trusted backend Principal boundary needs real identity-provider integration before deployment.', 'SQLite single-host reference is not a distributed-scale or availability claim.', 'BM25 and hybrid tie on this small fixture; no measured ranking uplift.', 'A simulated internal outbox is not an external mail delivery system.', 'Model and embedding results do not make hiring decisions; human review is required.']
  };
  if (evaluation.metrics.passed !== evaluation.metrics.scenarios) throw new Error('evaluation_failed');
  mkdirSync(new URL('../evidence/', import.meta.url), { recursive: true });
  writeFileSync(new URL('../evidence/demo.json', import.meta.url), JSON.stringify(report, null, 2) + '\n');
  writeFileSync(new URL('../evidence/evaluation.json', import.meta.url), JSON.stringify(evaluation, null, 2) + '\n');
  console.log(JSON.stringify({ tests: report.unitTests, metrics: report.metrics, durableRuns: report.durableRuns.map(r => ({ id: r.id, status: r.afterApproval ?? r.status })), evidence: 'evidence/demo.json' }, null, 2));
} finally { try { workflow.close(); } catch {} rmSync(dir, { recursive: true, force: true }); }
