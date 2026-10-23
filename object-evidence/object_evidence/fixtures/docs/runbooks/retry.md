# Fictional Aster Archive: bounded network failure
This is a fictional runbook for the sample integration.

The client uses a five-second connection timeout and a ten-second read timeout.
Standard SDK retries are capped at three total attempts per request.
If the network is unavailable, keep the last successful index unchanged and mark the latest sync attempt failed.
Queries reject stale snapshots by default. An operator may explicitly inspect stale evidence, which stays labeled stale.
Never log credentials, complete response bodies, or provider exception messages in a public demo.
