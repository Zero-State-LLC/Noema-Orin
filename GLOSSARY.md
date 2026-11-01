# NOEMA Orin Controller foundation

Local terminology for the synthetic Controller-host foundation. Canonical NOEMA identity and world terms remain defined by [Noema-Specs GLOSSARY](https://github.com/Zero-State-LLC/Noema-Specs/blob/619d0674518761aa08462d3f5d5966a917259aa1/GLOSSARY.md); this glossary does not redefine them.

## Language

**Target profile**:
The operator's explicit choice of which Controller environment a run is intended for. An unrecognized or absent choice does not select another environment.
_Avoid_: Default world, fallback target

**Submission attempt**:
A Controller's handoff of a proposed action to its chosen client boundary, regardless of whether that boundary accepts or fails. It is not evidence of a world action or settlement.
_Avoid_: Accepted action, world mutation

**Refusal record**:
The local account of a run stopped before an action is submitted. It is not a submission attempt or canonical world evidence.
_Avoid_: Attempted action, accepted action

**Failed submission attempt**:
A proposed action handed to the chosen client boundary that fails there. It is distinct from a pre-submission refusal and does not establish acceptance, retry, or settlement.
_Avoid_: Refusal, accepted action

**Dry-run receipt**:
The local account of a synthetic Controller run and its outcome. It is telemetry rather than canonical NOEMA evidence, even when a submission attempt is recorded.
_Avoid_: World receipt, settlement proof

**Fixture observation**:
A synthetic observation used to exercise the Controller decision boundary without representing a live world observation.
_Avoid_: Live observation, production evidence
