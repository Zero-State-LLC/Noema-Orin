# Decisions and gates

## D-001: Two isolated Controller targets (2026-10-31)

Operator selected **both paths, explicitly separate, with no live-world cutover**. The `hosted` profile retains Cloudflare Durable Objects live serialization and Supabase Postgres canonical durability. The `offline-spark` research profile remains a separate target. Neither profile is a fallback for the other.

## D-002: Private initial repository (2026-10-31)

Operator selected private visibility. This is a privacy posture for development, not permission to store credentials or private prompts in Git.

## D-003: Reuse the official client (2026-10-31)

Accepted RFC-0116 identifies `scrimshawlife-ctrl/noema-client` as the official first-party Controller package. This repository integrates that package instead of forking it or introducing another Player class. A scripted adapter is sufficient for a first executable proof; a specific NVIDIA model is not a prerequisite.

## G-001: Offline authority defect, BLOCKED

Spec 014 is SPECULATIVE. Its statement that Spark is the sole WorldState writer conflicts with `Noema-Specs/CONTEXT.md` for the hosted Platform. Before offline execution or any promotion, record a canonical decision that explicitly scopes Spark to a non-canonical offline chamber, defines its identity and interfaces, and states what evidence can and cannot be promoted. Do not edit the source spec in this repository or call the defect resolved.

## G-002: Physical hardware evidence, NOT_COMPUTABLE

Exact Orin model, memory, JetPack/L4T version, storage, power supply/profile, reachable network, compatible quantization and model license are not confirmed here. Measure these before choosing a model or promising throughput. An offline fake-client test proves only orchestration logic.

## G-003: Hosted live admission and campaign, BLOCKED

No automated live enrollment, Controller attach, PSR-1 candidate, production deployment or credential provisioning is authorized by this repository. Verify current production pin, scoped credential, device-code human approval, discovery, live seal and operator stop before any separately authorized test. The source PSR-1 gate remains blocked on retained outside-operator enrollment receipts. Orin-owned first-party Controllers do not meet the independently operated path by themselves.

## G-004: Pocock ticket graph, APPROVED FOR PUBLICATION

The operator approved T1–T6 granularity and blocking edges for publication on 2026-10-31. This approval concerns the **issue graph only**. T1–T3 may be marked `ready-for-agent` for local synthetic work; T4 isolated integration, T5 physical access and T6 offline-Spark authority retain their explicit gates. No ticket label authorizes production attach, deployment or a canon change.
