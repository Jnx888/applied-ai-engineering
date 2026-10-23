/** Browser-portable reference retrieval. No network, storage or hidden model calls. */
export type Profile = { id: string; tenantId: string; role: string; state: string; shifts: string[]; skills: string[]; summary: string; availableForReview: boolean };
export type SearchRequest = { tenantId: string; role: string; state: string; shift: string; query: string; minScore?: number };
export type SearchHit = { profileId: string; score: number; citations: string[]; rankingFeatures: { bm25: number; lexicalCosine: number; coverage: number; rrf: number; embeddingCosine?: number } };
export type SearchResponse = { results: SearchHit[]; abstained: boolean; audit: { scope: string; eligibleCount: number; mode: string; reason: string; model?: string } };
const tokens = (s: string): string[] => s.toLowerCase().match(/[a-z0-9]+/g) ?? [];
const round = (n: number) => Math.round(n * 100000) / 100000;
export function validateRequest(value: unknown): asserts value is SearchRequest {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('invalid_request');
  const r = value as Record<string, unknown>;
  if (Object.keys(r).some(k => !['tenantId', 'role', 'state', 'shift', 'query', 'minScore'].includes(k))) throw new Error('unknown_request_field');
  for (const k of ['tenantId', 'role', 'state', 'shift', 'query']) if (typeof r[k] !== 'string' || !(r[k] as string).trim() || (r[k] as string).length > (k === 'query' ? 600 : 80)) throw new Error('invalid_request');
  if (r.minScore !== undefined && (typeof r.minScore !== 'number' || !Number.isFinite(r.minScore) || r.minScore < 0 || r.minScore > 1)) throw new Error('invalid_threshold');
}
export function scopedProfiles(profiles: Profile[], request: SearchRequest): Profile[] {
  validateRequest(request);
  // This must run BEFORE corpus statistics, embeddings, scoring or prompting.
  return profiles.filter(p => p.tenantId === request.tenantId && p.availableForReview === true && p.role === request.role && p.state === request.state && p.shifts.includes(request.shift));
}
function cosine(a: Map<string, number>, b: Map<string, number>) {
  let dot = 0, aa = 0, bb = 0;
  for (const [k, v] of a) { dot += v * (b.get(k) ?? 0); aa += v * v; }
  for (const v of b.values()) bb += v * v;
  return aa && bb ? dot / Math.sqrt(aa * bb) : 0;
}
function counts(words: string[]) { const out = new Map<string, number>(); for (const w of words) out.set(w, (out.get(w) ?? 0) + 1); return out; }
export function searchProfiles(profiles: Profile[], request: SearchRequest, ranking: 'hybrid' | 'bm25' = 'hybrid'): SearchResponse {
  if (!['hybrid', 'bm25'].includes(ranking)) throw new Error('invalid_ranking_mode');
  const candidates = scopedProfiles(profiles, request);
  const query = [...new Set(tokens(request.query))];
  const docs = candidates.map(p => tokens([...p.skills, p.summary].join(' ')));
  const averageLength = docs.reduce((n, d) => n + d.length, 0) / (docs.length || 1);
  const measured = candidates.map((p, i) => {
    const termCounts = counts(docs[i]);
    const bm25 = query.reduce((sum, term) => {
      const frequency = termCounts.get(term) ?? 0;
      const df = docs.filter(d => d.includes(term)).length;
      const idf = Math.log(1 + (docs.length - df + 0.5) / (df + 0.5));
      return sum + idf * (frequency * 2.2) / (frequency + 1.2 * (0.25 + 0.75 * docs[i].length / (averageLength || 1)));
    }, 0);
    const coverage = query.length ? query.filter(t => termCounts.has(t)).length / query.length : 0;
    return { p, bm25, lexicalCosine: cosine(counts(query), termCounts), coverage };
  });
  const rankedBm = [...measured].sort((a, b) => b.bm25 - a.bm25 || a.p.id.localeCompare(b.p.id));
  const rankedCos = [...measured].sort((a, b) => b.lexicalCosine - a.lexicalCosine || a.p.id.localeCompare(b.p.id));
  const results = measured.filter(x => x.coverage >= (request.minScore ?? 0.3) && x.bm25 > 0).map(x => {
    const rrf = 1 / (60 + rankedBm.indexOf(x) + 1) + 1 / (60 + rankedCos.indexOf(x) + 1);
    return { profileId: x.p.id, score: round(ranking === 'bm25' ? x.bm25 : rrf), citations: [`${x.p.id}: role=${x.p.role}; state=${x.p.state}; shift=${request.shift}`, `${x.p.id}: skills=${x.p.skills.join(', ')}`], rankingFeatures: { bm25: round(x.bm25), lexicalCosine: round(x.lexicalCosine), coverage: round(x.coverage), rrf: round(rrf) } };
  }).sort((a, b) => b.score - a.score || a.profileId.localeCompare(b.profileId)).slice(0, 5);
  return { results, abstained: !results.length, audit: { scope: request.tenantId, eligibleCount: candidates.length, mode: ranking === 'bm25' ? 'independent BM25 baseline; no learned embeddings' : 'BM25 + lexical term-frequency cosine + RRF; no learned embeddings', reason: results.length ? 'review_required' : candidates.length ? 'insufficient_query_evidence' : 'no_eligible_profiles' } };
}

export type EmbeddingProvider = { model: string; embed: (texts: string[]) => Promise<number[][]> };
function denseCosine(a: number[], b: number[]) { const aa = a.reduce((s, x) => s + x * x, 0), bb = b.reduce((s, x) => s + x * x, 0); return aa && bb ? a.reduce((s, x, i) => s + x * b[i], 0) / Math.sqrt(aa * bb) : 0; }
/** Opt-in learned reranker. The conservative lexical evidence gate remains in effect. */
export async function searchWithEmbeddings(profiles: Profile[], request: SearchRequest, provider: EmbeddingProvider): Promise<SearchResponse> {
  const baseline = searchProfiles(profiles, request);
  if (baseline.abstained) return baseline;
  const candidates = scopedProfiles(profiles, request).filter(p => baseline.results.some(h => h.profileId === p.id));
  const vectors = await provider.embed([request.query, ...candidates.map(p => [...p.skills, p.summary].join(' '))]);
  if (vectors.length !== candidates.length + 1 || !vectors[0]?.length || vectors.some(v => v.length !== vectors[0].length || v.some(x => !Number.isFinite(x)))) throw new Error('invalid_embeddings');
  const semantic = candidates.map((p, i) => ({ id: p.id, score: denseCosine(vectors[0], vectors[i + 1]) })).sort((a, b) => b.score - a.score || a.id.localeCompare(b.id));
  const results = baseline.results.map((h, index) => {
    const found = semantic.find(x => x.id === h.profileId)!;
    const rrf = 1 / (61 + index) + 1 / (61 + semantic.indexOf(found));
    return { ...h, score: round(rrf), rankingFeatures: { ...h.rankingFeatures, embeddingCosine: round(found.score), rrf: round(rrf) } };
  }).sort((a, b) => b.score - a.score || a.profileId.localeCompare(b.profileId));
  return { ...baseline, results, audit: { ...baseline.audit, mode: 'lexical evidence gate + learned embedding rerank + RRF', model: provider.model } };
}
