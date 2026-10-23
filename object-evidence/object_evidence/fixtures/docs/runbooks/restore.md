# Fictional Aster Archive: restore verification
This document belongs to a fictional demo organization. It is not a vendor policy.

Before a restore drill, select the expected object version and record its SHA-256 digest in the incident record.
Download into an isolated temporary workspace and recompute the SHA-256 digest before restoring files.
If the downloaded digest differs, stop the restore and investigate the source version; never replace the expected digest with the observed value.
After integrity verification, run a representative application read and record the recovery outcome.
The fictional exercise target is a 30-minute recovery window; no measured recovery time is claimed.
