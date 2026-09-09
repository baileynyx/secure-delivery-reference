# Validation

September 9, 2026: `python -m unittest discover -s tests -v` passed all **10 tests**, covering an actual loopback HTTP health request, version/unknown-route responses, reproducible ZIP bytes, overwrite refusal, invalid release metadata, tamper rejection, rollback, repeated promotion and unavailable/corrupted previous releases.

`python rehearse.py` completed a local release-state simulation: version 1.0.0 was recorded, 1.1.0 was promoted, and rollback restored the original 1.0.0 digest. Synthetic commit identifiers are explicitly confined to the rehearsal and tests.

Docker build/run, hosted GitHub Actions, CodeQL and the release workflow have not been executed. No security scan result is claimed. A live deployment target and health-gated rollback are not implemented; promotion records state only.
