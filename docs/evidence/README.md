# Synthetic Controller receipts

The CLI emits one JSON record to stdout. `ATTEMPTED` means one fake-client handoff, `FAILED_SUBMISSION` means one failed handoff, and `REFUSED` means no client submission. These records are local telemetry, **not** canonical NOEMA world evidence. A fake success is not world acceptance or settlement.

Fields are allowlisted: `status`, `result`, pinned `source_sha`, `claim_label=SPECULATIVE`, `client_version=UNVERIFIED`, and `device_metrics=NOT_COMPUTABLE`. A validated hosted run may include `profile=hosted`; a handoff may include `transport=fake` and the fixed `action=LOOK`. No fixture fields, arbitrary profile input, proposal payload, exception, token, private cognition, client response, raw identifier, or authorization header belongs in a receipt. No automatic upload occurs. Do not promote these synthetic records to physical, hosted-world, or offline-Spark readiness claims.

Generate one by running `PYTHONPATH=src python3 -m noema_orin --profile hosted --fixture fixtures/hosted-look.json --dry-run`. The record is printed, not persisted. Validate with `PYTHONPATH=src python3 -m unittest discover -s tests -v`.
