# Contributing

Use Python 3.12+ and the standard library. Run `python verify.py` before proposing a change. Add a regression that would fail without a security fix, plus a permitted-path test when policy changes.

Keep tool schemas exact, fixture identities fictional, source material synthetic, and evidence free of payloads, tokens and machine paths. Do not add real credentials, employer documents, source datasets or database files. Do not turn the demo into a generic shell/HTTP executor.

Describe changes as tested local behavior. Preserve failure/limitation notes. Do not report unrun cloud, identity, transport or platform verification as passed. For a security report, share only the minimum synthetic reproduction; never include live secrets or third-party private records.

The source layout is intentionally flat for review and straightforward reproduction. No installed package or framework is needed.
