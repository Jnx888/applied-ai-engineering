import type { SearchRequest } from './search.ts';
export type ToolCall = { name: 'search_profiles'; arguments: { role: string; state: string; shift: string; query: string } };
export type Planner = { name: string; plan: (request: SearchRequest) => Promise<unknown> };
export const referencePlanner: Planner = {
  name: 'deterministic-reference-planner (not an LLM)',
  async plan(request) { return { name: 'search_profiles', arguments: { role: request.role, state: request.state, shift: request.shift, query: request.query } }; }
};
export function validateToolCall(value: unknown, request: SearchRequest): ToolCall {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('invalid_tool_call');
  const call = value as Record<string, unknown>;
  if (Object.keys(call).sort().join(',') !== 'arguments,name' || call.name !== 'search_profiles') throw new Error('unknown_tool');
  if (!call.arguments || typeof call.arguments !== 'object' || Array.isArray(call.arguments)) throw new Error('invalid_tool_arguments');
  const args = call.arguments as Record<string, unknown>;
  if (Object.keys(args).sort().join(',') !== 'query,role,shift,state') throw new Error('invalid_tool_arguments');
  // A planner proposes only an allowlisted lookup. It cannot expand the user-approved scope.
  for (const key of ['role', 'state', 'shift', 'query'] as const) if (args[key] !== request[key]) throw new Error('scope_change_rejected');
  return value as ToolCall;
}
export class RetryableError extends Error { constructor() { super('transient_dependency_failure'); } }
