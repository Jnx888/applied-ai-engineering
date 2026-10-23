# Fictional Aster Archive: retrieved context contract
This document describes the limits of the sample system.

Object Evidence returns deterministic lexical retrieval matches with source keys, line numbers, and content hashes.
The default demo does not call an LLM, generate an answer, create embeddings, or evaluate model hallucinations.
When adding a model, delimit retrieved text as untrusted data and require source-backed responses and explicit abstention.
Do not give retrieved documents authority to change system instructions or execute tools.
Evaluate retrieval relevance separately from model faithfulness before enabling any action.
