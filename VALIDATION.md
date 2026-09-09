# Validation

September 9, 2026: `python -m unittest discover -s tests -v` passed all **10 tests**, covering an actual loopback HTTP health request, version/unknown-route responses, reproducible ZIP bytes, overwrite refusal, invalid release metadata, tamper rejection, rollback, repeated promotion and unavailable/corrupted previous releases.

`python rehearse.py` completed a local release-state simulation: version 1.0.0 was recorded, 1.1.0 was promoted, and rollback restored the original 1.0.0 digest. Synthetic commit identifiers are explicitly confined to the rehearsal and tests.

The [first hosted delivery workflow](https://github.com/baileynyx/secure-delivery-reference/actions/runs/34357996018) passed for source commit `684aaf553a29f193202cf894cf491732455802b8`: tests, the local rehearsal, Docker image build and CodeQL initialization/analysis all completed successfully. Successful analysis does not establish that no security alerts exist.

The manual release job was correctly skipped on this push. Container runtime checks, manual release packaging on GitHub and live deployment have not been executed. A live deployment target and health-gated rollback are not implemented; promotion records state only.
