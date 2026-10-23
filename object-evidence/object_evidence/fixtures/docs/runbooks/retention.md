# Fictional Aster Archive: retention and deletion
This document is sample content, not legal or provider guidance.

The sample retention policy keeps diagnostic exports for 14 days.
Deletion requests remove an object from the active retrieval corpus after a complete successful sync.
A tombstone records the deleted key and its previous content digest without retaining deleted text.
A failed or incomplete listing must not be interpreted as deletion; retain the previous snapshot and mark it stale.
Historical local backups need their own deletion policy because a tombstone does not erase prior backups.
