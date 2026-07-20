# Contributing

Thank you for helping improve the ReactorFront Portfolio. Contributions should
preserve its role as a focused, reproducible public engineering record.

## Before proposing a change

1. Read [`README.md`](README.md), the accepted
   [ADRs](docs/adr/README.md), and the relevant
   [delivery specification](docs/delivery/0001-first-vertical-slice.md).
2. Search existing Issues and open or select one focused Issue that states the
   outcome, scope, non-targets, failure model, and acceptance criteria.
3. Do not submit client, employer, personal, licensed-without-permission, or
   confidential material. Tests and examples must use repository-owned
   synthetic fixtures.
4. Report suspected vulnerabilities privately under
   [`SECURITY.md`](SECURITY.md); never demonstrate them in a public Issue or PR.

## Development workflow

- Branch from the latest clean `main` and keep one focused concern per PR.
- Preserve the modular boundaries: Web uses public API contracts, ML does not
  access the API-owned database, and the API owns durable application state.
- Keep dependency versions and generated artifacts reproducible. Commit the
  required lock files and contract updates together with their consumers.
- Explain observable behavior, failure handling, verification evidence, and
  known limitations in the PR description.
- Keep commits reviewable and do not rewrite unrelated contributor work.

## Verification

Install the pinned dependencies and run the repository-owned non-Docker path:

```console
pnpm install --frozen-lockfile
uv sync --project apps/api --frozen
uv sync --project apps/ml --frozen
python scripts/verify.py --static-only
```

GitHub Actions is the authoritative runtime environment. It runs the same
entrypoint without `--static-only` and owns the ephemeral Compose project.
AI agents must not start or mutate local Docker Desktop. Human contributors are
not required to start it and may choose to run the full verifier only when they
explicitly own that local action. Never use Docker prune or an unscoped cleanup
command; teardown must target only `reactorfront-portfolio` resources created by
the verification run.

## Pull requests

A PR should link its focused Issue, remain Draft until its evidence is current,
and include the exact head SHA and Actions result used for review. Address the
cause of a failure and add a durable regression guard instead of only retrying
the workflow. Changes to accepted architecture or delivery scope must update
the governing ADR or specification in the same reviewed change.

By contributing, you agree that your original contribution is licensed under
the repository's [MIT License](LICENSE) unless a file clearly states otherwise.
