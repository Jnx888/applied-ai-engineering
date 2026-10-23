# Architecture and review notes

```text
Local UTF-8 documents ─┐
                      ├─> bounded read-only Source ─> complete candidate manifest
B2 list/get adapter ──┘                    │
                                          ├─> unchanged revision: reuse verified content
                                          └─> changed revision: get, validate, SHA-256
                                                       │
                                      atomic snapshot + explicit freshness status
                                                       │
                             lexical retrieval ─> cited source excerpts
                                      │                     │
                      optional LangChain Document     optional local Ollama
                                                      exact-quote selection
                                                             │
                                               independent ID/substring gate
```

## Why this shape

Object storage is often the source of an AI corpus, but a demo that only downloads a file hides important operating decisions. The `Source` protocol separates storage reads from retrieval; the snapshot format separates deterministic evidence from probabilistic generation. A standard-library core makes the integration inspectable and runnable without accounts, keys, or package installation.

The index is deliberately small and local. A JSON snapshot makes provenance transparent and enables a same-directory atomic replacement. It is not a distributed vector store or a multi-user service. Corpus limits cap memory use. The lexical ranker is a baseline that can run without model downloads and provides a clear comparator for future embeddings.

## Source identity, revision and citation identity

- A B2 namespace hashes endpoint, bucket and prefix. A default local namespace hashes the resolved root. An explicit local namespace is an operator assertion that the same identity refers to the same corpus.
- Local revisions hash bounded file content; remote revisions combine ETag, size and last-modified metadata. These answer “should we fetch again?” and are not all cryptographic integrity guarantees.
- Fetched bytes receive a SHA-256 digest. Citations bind namespace, key, content digest and line range. Changed content therefore receives a changed citation identity.
- An index generation hashes the schema, namespace, documents and tombstones. It does not contain wall-clock timing, so identical inputs and history produce identical generations.
- Stored digests detect accidental index corruption. They are not signatures against a malicious local operator who can rewrite both content and hashes.

## Failure, deletion and restart behavior

The source must list the whole permitted scope within the configured budgets. Any incomplete page chain, duplicate/out-of-prefix key, read error, invalid UTF-8 or oversize object rejects the candidate. Source-read failures preserve the old snapshot byte-for-byte. A status record marks that last attempt failed, so default queries reject stale evidence. `query --allow-stale` is an explicit operator inspection mode and always labels stale results.

A successful authoritative sync removes absent objects from active retrieval and records a tombstone. A totally empty replacement of an existing corpus requires `--allow-empty`, because a mistaken prefix should not silently erase all active evidence. Tombstones contain prior content hashes and keys; deleted text is absent from the new snapshot. Earlier backups and operating-system storage require an independent retention/erasure policy.

The snapshot uses `fsync` and same-directory `os.replace`. Status and snapshot are two files: a process/disk failure between publication and status completion may leave a complete new snapshot with an incomplete status; queries then fail closed. This is atomic file publication, not a multi-file transaction or a power-loss durability guarantee on every filesystem. No partial JSON candidate is treated as ready.

An exclusive `sync.lock` blocks concurrent writers. It also blocks queries while a writer is active. A killed process can leave a lock: **first verify that no writer is still running**, preserve a backup of the state directory, then remove only that stale lock and perform a fresh complete sync. Do not delete it on a timer or bypass stale status. The tool does not silently steal locks.

## Threat model

| Boundary | Implemented control | Remaining limit |
|---|---|---|
| Remote endpoint | Fixed regional HTTPS allowlist, before-send host verification, no configured proxies | DNS/TLS/host trust and SDK correctness remain dependencies |
| Storage access | Nonempty prefix; returned-key check; list/get only; no ACL mutation | Operator must provision genuinely restricted key and private bucket; no live permissions test was performed |
| Resource exhaustion | Object/page/byte/line limits; connect/read timeouts; bounded SDK retries | No distributed quotas; workflow wall time depends on bounded retries and number of calls |
| Local file access | Reject traversal, symlinks, devices and FIFOs; bounded reads; POSIX no-follow/nonblocking flags where available | The operator must own/trust the source directory against concurrent ancestor replacement |
| Local state | Scope-bound generations, hash checks, exclusive writer, atomic snapshot | No encryption at rest, multi-tenant authorization or hostile-local-user protection; use OS permissions/full-disk encryption |
| Untrusted source instructions | Retriever treats content as data; no execution/tool channel | LangChain/model consumers must preserve the same trust boundary |
| Optional local model | Structured schema, token/socket/response-size limits, cited exact-quote validator, no tools | Selection relevance and source truth are not guaranteed; validation is not universal prompt-injection immunity |
| Public proof | Only bundled fictional fixture reports are exported | Never publish arbitrary private index state or query outputs |

The default CLI does not expose a network server, admin interface, upload endpoint, authentication flow, payment flow or tenant API. Consequently this sample does not claim to implement controls for those nonexistent surfaces. A hosted multi-tenant adaptation must authorize retrieval **before** providing documents to a model, isolate indexes, limit endpoints, monitor operations, and manage retention and secrets explicitly.

## Deliberate tradeoffs

- Lexical retrieval misses synonyms and context beyond the chunk. Compare it to an embedding baseline on a held-out labeled corpus before upgrading.
- Eight-line chunks are simple and auditable but can cut semantic sections; line-size and byte limits bound worst cases. A structure-aware chunker should preserve citation offsets.
- Metadata-based B2 reuse relies on object revision hints. Periodic full revalidation could trade more reads for stronger freshness confidence.
- Complete local snapshots trade scalability for simple atomic publication. Large deployments should consider an ACID store, version-pinned object reads and isolated per-tenant queues.
- No background sync runs automatically. The operator owns cadence, freshness targets, access and release decisions.
