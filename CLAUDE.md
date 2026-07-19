# Claude project guidance

Read and follow `AGENTS.md` as the shared repository guidance. Then read
`docs/ai/README.md`, `README.md`, the accepted ADRs under `docs/adr/`, the
delivery specification, and the nearest area-specific `README.md` before
changing files.

The product, initial technology stack, and first vertical slice are accepted.
Follow `docs/delivery/0001-first-vertical-slice.md`; do not replace or add
technology for breadth without updating the relevant ADR or specification.
Use `python scripts/verify.py`, the same verification entrypoint used by human
contributors, Codex, and GitHub Actions.

The repository-owned AI contract defines authorized actors, bounded live-state
checks, comment-only independent review, and evidence reconciliation. Local
memory and prior task conversation are non-authoritative orientation only.
