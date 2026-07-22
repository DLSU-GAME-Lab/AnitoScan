# Architecture Documentation

These documents define the target architecture of AnitoScan. They describe the intended system after the refactor rather than the current implementation or migration history.

## Document ownership

| Document | Authoritative for |
|---|---|
| [`ipc_protocol.md`](ipc_protocol.md) | Transport framing, message schemas, numeric phase values, and protocol sequencing. |
| [`editor_backend_integration.md`](editor_backend_integration.md) | Mapping backend events and editor intents to backend and run state. |
| [`filesystem_layout.md`](filesystem_layout.md) | Directory layout, artifact naming, path rules, and filesystem ownership. |
| [`pipeline_architecture.md`](pipeline_architecture.md) | Python backend structure, pipeline orchestration, configuration ownership, and phase responsibilities. |
| [`editor_architecture.md`](editor_architecture.md) | C++ editor components, ownership, dependencies, and threading. |
| [`ui_workflow.md`](ui_workflow.md) | Workflow screens, navigation, presentation, and control behavior. |

## Maintenance rules

1. Update the authoritative document for a concern and link to it elsewhere instead of repeating its rules.
2. Keep wire schemas in `ipc_protocol.md`; other documents should refer to message types without redefining their fields.
3. Keep filesystem conventions in `filesystem_layout.md`; other documents should consume reported artifact paths without restating naming rules.
4. Keep component responsibilities in the relevant architecture document; workflow documentation should describe user-visible behavior only.
5. Keep implementation history, temporary mismatches, and migration tasks outside these target-state contracts.
6. When a decision affects more than one document, change the authoritative contract first and then update only the affected references.
