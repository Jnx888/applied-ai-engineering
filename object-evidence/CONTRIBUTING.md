# Contributing

This is an independent reference sample. Keep contributions small, inspectable and evidence-backed.

1. Run `python -m unittest discover -s tests -v` before changing behavior. Tests also support `pytest` when you install it in your own isolated environment.
2. Add a regression case for a substantive behavioral change, especially source scope, deletion, incomplete listing, stale evidence or model-output validation.
3. Run `python -m object_evidence evaluate` and compare failures, not just aggregate scores. Do not tune the fixture set to erase inconvenient examples.
4. Keep cloud tests opt-in; standard tests use injected clients and must not read real credentials or make outbound requests.
5. Use fictional text only in fixtures and public proof. Do not submit account names, application materials, job descriptions, private resumes, endpoint tokens or logs from real users.
6. Update architecture/tradeoff notes if the trust boundary changes. A cloud/runtime integration that was not tested should remain explicitly unverified.

The repository includes a GitHub Actions workflow definition; it has not been run on GitHub merely by existing in this directory. A maintainer should review optional dependencies, pin a reviewed lockfile and configure branch protection before operating a public project.

Workflow actions are pinned to full commits from the official [checkout v7.0.1 release](https://github.com/actions/checkout/releases/tag/v7.0.1) and [setup-python v7.1.0 release](https://github.com/actions/setup-python/releases/tag/v7.1.0), checked on 2026-10-22. Review action updates deliberately; pinning is not a substitute for future advisory monitoring.

For a potentially sensitive security issue, do not open an issue containing secrets or private data. Share a minimal synthetic reproducer through the repository owner's chosen private security channel once one is configured. No public security contact or hosted service is claimed here.
