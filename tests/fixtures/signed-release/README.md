# Historical signed release fixture

`app.py` is an exact copy from commit
`c934bcc1f10c5e88034539e788e09842ff84e5c4`. Do not update it with the live service.
Packaging it as version `1.0.0` with that source commit reproduces SHA-256
`8700ea411ffee5c1054b8a7d6a00e8969f768be0eb32f8a91d4a2aa124ff74a9`.

[Run 34428439084](https://github.com/baileynyx/secure-delivery-reference/actions/runs/34428439084)
signed and published [attestation 46441745](https://github.com/baileynyx/secure-delivery-reference/attestations/46441745)
before its verification step failed because of mutually exclusive CLI flags.

`check_provenance.py` downloads the existing public proof and exercises the real
verifier and rejection cases against the reconstructed bytes. It never executes
this fixture or signs the current checkout. The recorded digest prevents a changed
fixture from silently becoming accepted test input. GitHub/Sigstore availability
is a required dependency of this integration check.
