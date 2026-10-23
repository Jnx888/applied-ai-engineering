import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { searchProfiles } from '../src/search.ts';
import type { Profile, SearchRequest } from '../src/search.ts';
export const profiles: Profile[] = JSON.parse(readFileSync(new URL('../data/profiles.json', import.meta.url), 'utf8'));
export const scenarios: { id: string; request: SearchRequest; relevantIds: string[]; expectedAbstention: boolean }[] = JSON.parse(readFileSync(new URL('../data/scenarios.json', import.meta.url), 'utf8'));
export function evaluate() {
  const rows = scenarios.map(s => {
    const result = searchProfiles(profiles, s.request);
    const bm25 = searchProfiles(profiles, s.request, 'bm25').results;
    const rank = result.results.findIndex(h => s.relevantIds.includes(h.profileId));
    const baselineRank = bm25.findIndex(h => s.relevantIds.includes(h.profileId));
    const violations = result.results.filter(h => {
      const p = profiles.find(p => p.id === h.profileId)!;
      return p.tenantId !== s.request.tenantId || !p.availableForReview || p.role !== s.request.role || p.state !== s.request.state || !p.shifts.includes(s.request.shift);
    }).length;
    return { id: s.id, request: s.request, relevantIds: s.relevantIds, expectedAbstention: s.expectedAbstention, result, hybridReciprocalRank: rank < 0 ? 0 : 1 / (rank + 1), bm25ReciprocalRank: baselineRank < 0 ? 0 : 1 / (baselineRank + 1), hardFilterViolations: violations, passed: result.abstained === s.expectedAbstention && !violations && (s.expectedAbstention || rank === 0) };
  });
  const answerable = rows.filter(r => !r.expectedAbstention);
  return { schemaVersion: 1, fixtureScope: '8 curated synthetic smoke scenarios; not a representative hiring or production benchmark', scenarios: rows,
    metrics: { scenarios: rows.length, passed: rows.filter(r => r.passed).length, answerableQueries: answerable.length,
      hybridMRR: answerable.reduce((s, r) => s + r.hybridReciprocalRank, 0) / answerable.length,
      bm25MRR: answerable.reduce((s, r) => s + r.bm25ReciprocalRank, 0) / answerable.length,
      abstentionAccuracy: rows.filter(r => r.result.abstained === r.expectedAbstention).length / rows.length,
      hardFilterViolations: rows.reduce((s, r) => s + r.hardFilterViolations, 0) },
    interpretation: 'Same eligibility and lexical evidence gate for both ranking methods. This curated fixture does not establish semantic improvement, model quality, fairness or business impact.' };
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const result = evaluate(); mkdirSync(new URL('../evidence/', import.meta.url), { recursive: true });
  writeFileSync(new URL('../evidence/evaluation.json', import.meta.url), JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify(result.metrics, null, 2)); if (result.metrics.passed !== result.metrics.scenarios) process.exitCode = 1;
}
