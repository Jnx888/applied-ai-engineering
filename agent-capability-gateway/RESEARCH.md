# Research and design rationale

Primary sources inspected October 22/23, 2026. These sources motivate the design; none certifies this implementation. The project applies established ideas and makes no novelty claim.

| Source and publication date | Design implication | Counterargument or limit |
|---|---|---|
| [OWASP Top 10 for Agentic Applications 2026](https://genai.owasp.org/download/52117/?tmstv=1765059207), December 2025 edition | Task-limited authority, explicit tool checks, identity scope and factual approval previews inform the action envelope. | A risk taxonomy is not a security certification or a test suite. |
| [Anthropic: How we contain Claude across products](https://www.anthropic.com/research/how-we-contain-claude), May 25, 2026 | An approved API hostname can still point to an attacker's account. Bind account and operation, not only domain. | Approval fatigue and enforcement bugs remain. This sample does not provide the OS/VM containment described in the source. |
| [OpenAI: Self-replicating prompt injections exist](https://alignment.openai.com/misalignment-reports/self-replicating-prompt-injections-exist/), disclosed/updated September 25, 2026 | Treat retrieved instructions as untrusted data and constrain resulting tool effects independently. | The reported propagation occurred in simulated tools; the source reports no impact outside the simulated training/evaluation setting. |
| [Microsoft: Agents are your newest insiders](https://www.microsoft.com/en-us/security/blog/2026/10/19/agents-are-your-newest-insiders-security-must-move-at-their-speed/), October 19, 2026 | Put deterministic authority checks outside the model and recheck revocation during execution. | Product announcements do not establish this sample's efficacy or the availability of a commercial plan. |
| [MITRE ATLAS OpenClaw Investigation](https://www.mitre.org/sites/default/files/2026-02/PR-26-00176-1-MITRE-ATLAS-OpenClaw-Investigation.pdf), February 9, 2026 | Test the chain from untrusted content to unauthorized tool invocation and persistent context. | These fixtures cover selected boundary conditions, not the full ATLAS matrix. |

Related prior art: [CaMeL](https://arxiv.org/abs/2503.18813), submitted March 24 and revised June 24, 2025, separates control/data flow and enforces policies around tool use. Its current abstract reports lower task completion in its defended setup than its undefended comparator, illustrating a security/utility tradeoff. The [official research implementation](https://github.com/google-research/camel-prompt-injection) explicitly has unsupported research status. This project does not reproduce CaMeL's interpreter or evaluation and should not inherit its results.

The conservative source-label union here deliberately overblocks some harmless derived text. We chose an inspectable restriction instead of allowing the model to decide what is public. A future declassification workflow would need independent authorization and tests; making labels less restrictive to improve a demo would weaken the claim.

No research paper's percentages are used as this project's performance metrics. Its public evidence comes only from its own executed local scenarios and test suite.
