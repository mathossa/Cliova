# External source provenance

This registry records substantial external implementation sources considered for Cliova. The operational reuse policy is defined in [`AGENTS.md`](../../AGENTS.md#5-copyadapt-first-mandatory-open-source-gate). This registry is an engineering/provenance record, not legal advice or a claim of formal clean-room certification.

Record serious candidates when they materially influence a subsystem decision, including rejected and reference-only candidates. Keep entries short and update them prospectively if new licensing or provenance evidence appears.

For each candidate record:

- **Upstream** — repository/project and relevant subsystem.
- **Revision** — exact commit, tag or version inspected where practical.
- **License/SPDX** — verified license identifier, or `unknown` when no applicable permission has been established.
- **Classification** — `licensed-reusable`, `reference-only` or `rejected`.
- **Reuse mode** — `dependency`, `copied/adapted code`, `reference-only` or `rejected`.
- **Attribution/NOTICE** — obligations that apply to Cliova's chosen reuse mode.
- **Rationale** — concise fit/provenance decision, including rejection reasons where applicable.

## Current decisions

### `tan-zhuo/genesis`

- **Upstream:** `tan-zhuo/genesis`; potentially relevant to simulation concepts, phase ordering and observable game behavior.
- **Revision:** `main` at `72ce49343c3bc464a195a44375ee9f7deb3a190f` (inspected for provenance decision on 2026-09-15).
- **License/SPDX:** `unknown`; no explicit compatible reusable license or direct permission has been verified for Cliova.
- **Classification:** `reference-only`.
- **Reuse mode:** `reference-only`.
- **Attribution/NOTICE:** no source is incorporated under this decision; if permission or a compatible license is established later, reassess obligations before any prospective reuse.
- **Rationale:** useful as a research reference for high-level concepts, abstract algorithms, behavioral requirements, simulation phases and externally observable behavior. Do not copy source, comments, tests, constants/tables with unclear rights, translate/port source, or preserve distinctive implementation structure through paraphrase. Any implementation materially informed by Genesis must proceed through an implementation-neutral specification and independent Cliova implementation.

This classification may be reviewed prospectively if an explicit compatible license or direct permission is later verified. Existing reference-only work does not become retroactively copied/adapted work merely because the upstream licensing status later changes.
