# Object Evidence

A small, working developer integration that turns private object-storage documents into a reproducible retrieval index. It demonstrates the less glamorous parts of an AI integration: scoped ingestion, incremental sync, deletion semantics, provenance, failure handling, a framework bridge, and an optional local-model output gate.

**Independent sample.** No employer commissioned or deployed this work. All bundled documents describe a fictional organization. This is not an official Backblaze or LangChain integration and makes no customer, production-uptime, or cloud-cost claims.

## Run it without installing anything

Requires Python 3.12 or newer. From this project directory, the following works on Windows PowerShell and POSIX shells:

```sh
python -m object_evidence demo --output evidence/demo.json
python -m object_evidence evaluate --output evidence/evaluation.json
python -m unittest discover -s tests -v
```

Use `py -3.12` on Windows or `python3` on POSIX if that is your Python command. The default demo makes **zero cloud calls and zero model calls**. The reports contain actual fixture executions, rather than simulated execution logs.

Try your own local text documents:

```sh
python -m object_evidence sync-local --source object_evidence/fixtures/docs --state .state/local --namespace example:archive
python -m object_evidence query --state .state/local "How do we verify a restore digest?"
```

Use a unique namespace for each independent corpus; keep it stable when that same corpus changes. The Python API derives a root-specific identity when no namespace is supplied. Store state outside public web roots. State contains source text, keys and hashes and is **private**, even if a storage bucket is private.

## What the working sample does

1. A complete, bounded source listing establishes the candidate corpus.
2. Unchanged source revisions reuse validated local content; changed objects are fetched, decoded and hashed.
3. A complete candidate snapshot atomically replaces the prior snapshot. Its generation is a deterministic SHA-256 digest.
4. Deleted objects disappear from retrieval. Tombstones retain key/hash provenance, without retaining deleted text.
5. A corrupt object, truncated listing, timeout or budget failure rejects the candidate. The previous snapshot remains available only through explicit, labeled stale inspection.
6. A BM25-style lexical ranker returns exact excerpts, line numbers, source keys, source namespace and content SHA-256. It does not present excerpts as a generated answer.

An unchanged fixture run reports **six reused objects and zero object fetches**. Local listing still reads documents to compute revisions; this is not a claim of zero disk I/O. B2 instead uses ETag/size/last-modified metadata to decide whether to fetch. ETags are treated as opaque revision hints, never as content SHA-256.

## Evidence and honest limits

The checked-in `evidence/` files are safe to display because their only corpus is the bundled fictional fixture set. Regenerate them to verify the results on your machine.

| Evidence | What it establishes | What it does not establish |
|---|---|---|
| `demo.json` | Actual initial/repeated sync, citations and four recorded scenarios | A live cloud connection or a browser-hosted Python runtime |
| `evaluation.json` | Eight authored retrieval cases and seven failure/deletion checks | Generalization to unseen enterprise documents |
| `local-model.json` | Two actual local Qwen3 calls producing validated source quotations | Broad semantic accuracy, a model benchmark or production latency |
| `tests.json` | Offline test outcomes and explicit skips on the execution host | Live B2 credentials, permissions or service compatibility |
| `package-smoke.json` | Wheel contains fixtures and runs from an extracted isolated directory | A published PyPI package |

The initial fixture evaluation is deliberately small and in-sample. Perfect scores here are a regression check, not evidence of real-world retrieval quality. No user interviews or production adoption metrics were collected. Live B2 integration remains **not run**. The optional LangChain runtime is tested only if installed; an unavailable dependency is reported rather than fabricated as a pass.

## Optional local AI integration

When an already installed Ollama service and local model are available, the following explicitly enables model use:

```sh
python -m object_evidence extract --state .state/local --local-model qwen3:4b-instruct "How many days are diagnostic exports kept?"
```

The only endpoint is `http://127.0.0.1:11434/api/chat`. There is no model download, browser API, hosted inference, tool execution, or credential requirement. Input is bounded; output uses a JSON schema, a 384-token cap and a 45-second socket timeout. The model selects an existing citation and a short exact quotation. A separate deterministic gate rejects unknown citation IDs, invented quotes, extra fields and malformed responses. No unverified generated factual prose is displayed.

Explicit cloud model names are rejected. A loopback endpoint by itself cannot prove how an independently configured Ollama service executes an alias: verify the selected model is already installed and runs locally before sending private text. Reported client external calls count only requests made directly by this Python client.

This verifies **quote membership**, not relevance or truth of the source. The model can still select a poor or malicious quotation; source text remains untrusted. A production assistant would need separate relevance/faithfulness evaluation and authorization before retrieval. See [the local-model evidence](evidence/local-model.json) for the actual two-case run, including both observed elapsed times.

## Optional Backblaze B2 adapter

The adapter uses the B2 S3-compatible API through `boto3`. Core execution needs no dependencies. If you choose to enable cloud use in an isolated environment:

```sh
python -m venv .venv
# PowerShell: .venv\Scripts\Activate.ps1
# POSIX: . .venv/bin/activate
python -m pip install '.[b2]'
```

Copy `config.b2.example.json` to ignored `local-config.json`. Replace the region, bucket and prefix with your own dedicated **private test** scope. Configure a restricted application key with only list/read capabilities. Do not use a master key. The example values are placeholders, not a working account.

Supply `OBJECT_EVIDENCE_B2_KEY_ID` and `OBJECT_EVIDENCE_B2_APPLICATION_KEY` through your local secret manager or process environment. Never commit a key or paste real values into a notebook or shell history. The client deliberately does not discover shared AWS profiles or instance-metadata credentials.

```sh
python -m object_evidence sync-b2 --config local-config.json --state .state/b2 --allow-network
python -m object_evidence query --state .state/b2 "restore verification"
```

Cloud requests may incur provider charges. This project has not made a cloud request. Before real use, review the dependency versions resolved in your environment, your key capabilities and the provider's current API support. Optional dependency ranges are compatibility declarations, not audited lockfiles.

The adapter accepts only an HTTPS regional endpoint matching `s3.<region>.backblazeb2.com`, uses path-style bucket addressing, and rejects endpoint changes at the SDK send boundary. It exposes only `ListObjectsV2` and `GetObject`, scopes every listing to a nonempty prefix, checks returned keys, and uses conditional `IfMatch` reads. Default budgets are 100 objects, 256 KB per object, 2 MB per corpus and 10 listing pages. SDK timeouts are 5 seconds connect/10 seconds read with at most 3 total attempts per call. Credentials and provider exception details are never printed by the CLI.

Only UTF-8 `.md`/`.txt` files belong in the B2 prefix. Unsupported content fails closed rather than being silently dropped. Listing is not a transactional cross-object snapshot; metadata/read races are detected where possible, but concurrent remote edits can still require another sync. A future version-pinned adapter would need additional provider-specific version-listing semantics.

## Optional LangChain document bridge

Install the `langchain` extra only if you need it, then:

```python
from object_evidence import EvidenceIndex
from object_evidence.langchain_adapter import ObjectEvidenceLoader

loader = ObjectEvidenceLoader(EvidenceIndex('.state/local'))
for document in loader.lazy_load():
    print(document.metadata['citation_id'])
```

This exports `langchain_core.documents.Document` objects with provenance metadata. It does not choose embeddings, start a model, upload documents, or provide a vector database. Those are separate integration choices with separate privacy and evaluation requirements.

## Further reading

- [Architecture, failure semantics and threat model](docs/ARCHITECTURE.md)
- [Five-minute interview walkthrough and customization guide](docs/WALKTHROUGH.md)
- [Notebook tutorial](notebooks/01_object_evidence.ipynb)
- [Contributing and verification](CONTRIBUTING.md)

Primary documentation consulted on **2026-10-22**: [Backblaze S3-compatible API](https://www.backblaze.com/docs/cloud-storage-s3-compatible-api), [Boto3 list_objects_v2](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/list_objects_v2.html), [Boto3 get_object](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/get_object.html), [Ollama chat API](https://docs.ollama.com/api/chat), [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs). Provider support can change; read these before adapting the sample to a real account.
