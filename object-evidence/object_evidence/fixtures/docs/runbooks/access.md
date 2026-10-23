# Fictional Aster Archive: retrieval access
This document is an illustrative operating rule for a fictional team.

Use a dedicated read-only application key restricted to the archive-help/ prefix and the intended private bucket.
The ingestion job needs list and read capabilities; it does not need write, delete, or public ACL changes.
Keep storage credentials on the server or local operator environment. Do not place them in a browser bundle.
Application authorization must be checked before retrieving documents for a user or tenant.
A citation identifies evidence; it does not grant permission to view its source.
