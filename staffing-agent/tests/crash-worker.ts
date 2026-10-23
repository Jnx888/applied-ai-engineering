import { Workflow } from '../src/workflow.ts';
const workflow = new Workflow(process.argv[2]);
if (!workflow.claim(1000, 100)) process.exit(2);
// Deliberate process death after the claim commit, before search/checkpoint completion.
process.exit(17);
