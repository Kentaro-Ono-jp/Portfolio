# Prompt: cold task bootstrap

Use this prompt to start a portfolio task without relying on earlier chat or
local agent memory.

```text
Work on the public ReactorFront Portfolio repository as a completely fresh
task.

Repository: <repository URL>
Requested outcome: <owner request>
Known focused Issue or PR, if any: <public URL or none>

Before changing durable state:

1. Read AGENTS.md and docs/ai/README.md.
2. Follow the source-of-truth order there. Read README.md, accepted ADRs in
   numeric order, Delivery Specification 0001, and the nearest area README.
3. Run git status --short --branch.
4. Read umbrella Issue #1 and only the focused Issue, PR, review verdict, and
   Actions run relevant to this request.
5. When branching or mutating remote state, fetch the relevant remote and
   verify the exact main or PR head first.
6. Do not enumerate every Issue, branch, comment, workflow, or file merely to
   detect an unknown writer while the declared actor model is consistent.
7. If state is dirty, missing, stale, contradictory, or outside the actor
   model, stop the intended mutation and report the narrow discrepancy.
8. Do not start or mutate local Docker unless the owner explicitly requests a
   local runtime check. GitHub Actions is the authoritative runtime proof.

Treat local memory and this prompt as orientation, not as current project
state. Lead with the verified baseline, intended scope, explicit non-targets,
failure model, acceptance criteria, and proof plan. Do not implement until the
owner has supplied the authority required by the focused workflow.
```

## Expected result

The agent should reconstruct the task from tracked guidance and narrow live
GitHub records, identify any authority still needed, and avoid both stale
handoff assumptions and an unnecessary broad audit.
