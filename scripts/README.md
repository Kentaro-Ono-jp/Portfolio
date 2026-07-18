# Project scripts

This directory will provide a small number of platform-conscious entrypoints
for setup, verification, seed data, and diagnostics.

The accepted first-slice specification names `scripts/verify.py` as the
canonical verification entrypoint used by humans, coding agents, and GitHub
Actions.

Run it from the repository root after `pnpm install`:

```console
python scripts/verify.py
```

The current entrypoint validates contracts, local Markdown links, and the
isolated Compose definition without starting Docker. It will expand in the same
file as executable services and end-to-end checks are introduced.

Supporting scripts are implementation details of that entrypoint:

- `check_docs.py` rejects broken local Markdown links.
- `validate-events.mjs` validates canonical event examples and representative
  rejection cases against the versioned JSON Schemas.
- `stamp-generated-contract.mjs` records the canonical source and regeneration
  command in the generated TypeScript contract header.
