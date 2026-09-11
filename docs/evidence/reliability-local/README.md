# Retained local reliability capture

[Incident report](incident.md) · [Structured evidence](incident.json) ·
[Raw requests](samples.jsonl) · [Metric export](metrics.prom) ·
[Reproduce the lab](../../reliability-lab.md)

One paced rehearsal completed at 2026-09-11T11:37:12.519411+00:00 in the build workspace:
Linux x86_64, Python 3.12.14. This is not a capture from Bailey's Windows laptop.
All 37 repository tests passed locally, including 8 reliability tests.

| Observation | Recorded value |
| --- | --- |
| Baseline | 12 measured requests, all HTTP 200 |
| Injected incident | 4 measured requests, all HTTP 503 |
| Alert | Fired on the fourth failed request after two breached windows |
| Recovery | 12 measured requests, all HTTP 200; restored version 1.0.0 |
| Observed fault to alert | 0.308622 seconds |
| Alert to verified recovery | 1.244646 seconds |

The capture retains original files. All three artifact hashes in `incident.json`
and all six source-file hashes matched before publication. Its own SHA-256 is:

`b2e46c7f5d1ec3053be14958925394a89aabbaa125a8247e674c9fc08ac3021c`

Request status counts were checked against every retained sample. Event times
were ordered, and alert decisions were tested separately against isolated errors,
sustained errors and slow successful responses.

The fault is a harness-injected health response; the application bytes are the
same in both fixture packages. The monitor uses short sample windows. Worker
transitions are unsampled, and readiness/version probes are not traffic samples.
These timings describe this single local attempt, not a production SLO or MTTR.

The evidence is unsigned. Hashes identify bytes and do not authenticate execution.
The lab uses checksum-only local state helpers; it does not demonstrate signature
verification, cloud deployment, external paging or database recovery.
