import { mkdtempSync, rmSync, writeFileSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createOllama } from '../src/ollama.ts';
import { validateToolCall } from '../src/planner.ts';
import { Workflow } from '../src/workflow.ts';
import type { Principal } from '../src/workflow.ts';
import { profiles, scenarios } from './evaluate.ts';
if (!process.argv.includes('--allow-local-model')) throw new Error('explicit --allow-local-model required');
const model = process.argv[process.argv.indexOf('--model') + 1];
if (!process.argv.includes('--model') || !model) throw new Error('--model locally-installed-model required');
const adapter = createOllama({ allowLocalModel: true, chatModel: model, embeddingModel: 'not-configured-not-called', timeoutMs: 60_000 });
const dir = mkdtempSync(join(tmpdir(), 'staffing-live-local-')), workflow = new Workflow(join(dir, 'state.sqlite'));
const principal: Principal = { tenantId: 'hospital-demo-a', subject: 'fictional-model-evaluator', roles: ['operator', 'approver'] };
const results: unknown[] = [];
try {
  for (const scenario of [scenarios[0], scenarios[5]]) {
    const { tenantId, ...request } = scenario.request;
    const id = workflow.submit(principal, request, scenario.id);
    let validatedProposal: unknown = null;
    const planner = { name: adapter.planner.name, async plan(r: typeof scenario.request) { const proposal = await adapter.planner.plan(r); validatedProposal = validateToolCall(proposal, r); return proposal; } };
    const started = performance.now();
    await workflow.tick(profiles, { planner, leaseMs: 120_000 });
    const job = workflow.load(principal, id);
    const passed = job.status === (scenario.expectedAbstention ? 'abstained' : 'awaiting_approval');
    results.push({ scenario: scenario.id, status: job.status, passed, elapsedMs: Math.round(performance.now() - started), validatedProposal, resultCount: job.result?.results.length ?? 0, outboxCount: workflow.outbox(principal).length, trace: job.events.map(e => ({ kind: e.kind, detail: e.detail })) });
    if (!passed) break; // Never loop on an unresponsive local model.
  }
  let malformedGuard = false;
  try { validateToolCall({ name: 'send_email', arguments: {} }, scenarios[0].request); } catch { malformedGuard = true; }
  const report = { schemaVersion: 1, generatedAt: new Date().toISOString(), model, endpoint: 'loopback Ollama', modelExecution: 'actual local structured-output calls; fictional inputs only', embeddingExecution: 'not run; chat model embedding capability not assumed', promptPolicy: 'Return one unchanged search_profiles proposal; server validates tool name, exact argument keys and unchanged approved scope.', results, malformedGuard: { passed: malformedGuard, source: 'deterministic injected unknown-tool proposal, not a model-generated attack' }, limitations: ['Two functional smoke cases, not model quality benchmarking.', 'No model downloads, external recruiting actions or learned embedding experiment.', 'Local endpoint alone is not proof of server configuration; operator must use installed local-only models.'] };
  mkdirSync(new URL('../evidence/', import.meta.url), { recursive: true });
  writeFileSync(new URL('../evidence/live-model.json', import.meta.url), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify(report, null, 2));
  if (results.length !== 2 || results.some((r: any) => !r.passed)) process.exitCode = 1;
} finally { workflow.close(); rmSync(dir, { recursive: true, force: true }); }
