# Local Windows UI merge verification (12 October 2026)

The installed local RC is Minkops **0.6.7**, built from merge `ef123a9` on
`platform-ai/complete-discovery-scope`. It combines Discovery progress and run
controls with Bill Entry selection, settings and destination-PC routing.

Validation passed: 282 backend tests and 49 subtests, 31 frontend unit tests,
76 native tests, the three Bill Entry/destination browser regressions, frontend
build/lint and Windows NSIS packaging. Additional browser checks cover Discovery
confirmation, 13-company pagination/search, interrupted polling, four themes,
reduced motion, Pause/Resume/Stop and 320 px layout. A PostgreSQL integration check
also combines pinned-PC saves with Pause/Stop and a late verified receipt.

The installer replaced 0.6.5 in the existing per-user installation. Runtime checks
confirmed the installed `app.asar`, version 0.6.7, `Minkops Local Demo` profile,
compiled UI at `http://127.0.0.1:3018` and working local API at port 8018. Desktop
and Start Menu shortcuts start the local services and pass `--local-demo`.
Existing account credentials and production profile were retained. The local
profile opens at sign-in. No production deployment or financial import was run.

The chosen dev database is `minkops_parallel_local_20261011` on the existing local
PostgreSQL server at port 5433. It had the newest development history and no
queued/executing native or hosted jobs. It was backed up before applying migrations
0003 and 0004. Other databases were retained: `minkops_app` is the empty Compose
default; MIN-124 live/restore, baseline, Attention UI and parallel rehearsal
databases contain earlier manual validation fixtures or restored snapshots.
`postgres` is the standard server administration database. Automated pytest
databases remain disposable and are removed after their owning run.

Installer SHA-256:
`C70C6E4338E3BBAEF37DD6685C9BBB4AE48EF6DE61982995CDC21BD06B2C8DE4`.
The installer is unsigned, consistent with the local RC packaging policy.
