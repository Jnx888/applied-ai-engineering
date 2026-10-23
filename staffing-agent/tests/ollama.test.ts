import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createOllama } from '../src/ollama.ts';
import { validateToolCall } from '../src/planner.ts';
import { RetryableError } from '../src/planner.ts';
test('optional adapter emits documented local structured-output and embedding protocol (mock only)', async () => {
  const requests: {url: string; body: any}[] = [];
  const request = { tenantId: 'hospital-demo-a', role: 'RN', state: 'CA', shift: 'night', query: 'ICU' };
  const fake: typeof fetch = async (url, init) => {
    const body = JSON.parse(init!.body as string); requests.push({ url: String(url), body });
    assert.equal(init!.redirect, 'error');
    return Response.json(String(url).endsWith('/api/chat') ? { message: { content: JSON.stringify({ name: 'search_profiles', arguments: { role: 'RN', state: 'CA', shift: 'night', query: 'ICU' } }) } } : { embeddings: [[1, 0]] });
  };
  const adapter = createOllama({ allowLocalModel: true, chatModel: 'local-test-model', embeddingModel: 'local-test-embed', fetcher: fake });
  validateToolCall(await adapter.planner.plan(request), request); await adapter.embeddings.embed(['ICU']);
  assert.equal(requests[0].url, 'http://127.0.0.1:11434/api/chat'); assert.equal(requests[0].body.stream, false);
  assert.equal(requests[0].body.format.additionalProperties, false); assert.equal(requests[1].body.truncate, false);
});
test('mid-stream transport failure is retryable; malformed JSON is terminal', async () => {
  const interrupted = createOllama({ allowLocalModel: true, chatModel: 'a', embeddingModel: 'b', fetcher: async () => new Response(new ReadableStream({ start(controller) { controller.error(new Error('transport interrupted')); } })) });
  await assert.rejects(() => interrupted.embeddings.embed(['ICU']), RetryableError);
  const malformed = createOllama({ allowLocalModel: true, chatModel: 'a', embeddingModel: 'b', fetcher: async () => new Response('{invalid') });
  await assert.rejects(() => malformed.embeddings.embed(['ICU']), SyntaxError);
});
test('adapter requires opt-in, disallows cloud model names, and rejects oversized output', async () => {
  assert.throws(() => createOllama({ allowLocalModel: false, chatModel: 'a', embeddingModel: 'b' } as never), /opt_in/);
  assert.throws(() => createOllama({ allowLocalModel: true, chatModel: 'cloud-model', embeddingModel: 'b' }), /local_model_required/);
  const adapter = createOllama({ allowLocalModel: true, chatModel: 'a', embeddingModel: 'b', fetcher: async () => new Response('x'.repeat(1_000_001)) });
  await assert.rejects(() => adapter.embeddings.embed(['a']), /model_response_too_large/);
});
