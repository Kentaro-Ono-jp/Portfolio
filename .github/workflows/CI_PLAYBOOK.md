# GitHub Actions CI playbook

This guide turns verified runner failures into reusable preflight checks. It
hardens how an accepted test runs; it never decides what the test must prove.
The canonical entrypoint remains [`scripts/verify.py`](../../scripts/verify.py),
and GitHub Actions remains the authoritative runtime environment.

## When to use it

### Staged pre-commit hardening

Do not use this guide to design the feature or its tests. First derive test
intent from accepted design and the focused Issue, then finish the
implementation and verification scripts.

1. Inspect the complete intended diff and stage the exact candidate without
   committing.
2. Read the change-driven checks below and inspect only the applicable
   boundaries.
3. Correct portability, dependency, real-service, recovery, evidence, or
   teardown risks without weakening the intended proof.
4. Rerun the required verification after any correction.
5. Inspect and stage the corrected candidate again. Commit only that verified
   staged state.

The first staging is a review snapshot, not permission to commit stale index
content after later edits.

### Local rehearsal boundaries

Treat a missing command or host-tool version mismatch as a local preflight
condition, not as a product or Actions failure.

- Resolve `pnpm`, `uv`, and `docker` before starting the canonical verifier.
  Compare the available Node and Python versions with `.node-version` and
  `.python-version`, and use the `uv` version pinned by the workflow.
- When the host must remain unchanged, install a missing exact-version tool in
  a unique, verified system temporary directory. Remove only that directory
  after verification and confirm that it no longer exists.
- Do not impose an arbitrary 60-second process timeout on
  `scripts/verify.py --static-only`. Give the verifier enough lifetime for
  dependency audits, model proof, and both test suites; yield or poll output
  without terminating the subprocess. External timeout termination is not
  verification evidence.
- Disclose a local runtime mismatch instead of hiding it. GitHub Actions on the
  repository-pinned versions remains the authoritative proof.

These are local orchestration rules, not additional failed Actions runs in the
historical ledger.

### Owner-approved docs-only CI skip

A final correction may use `[skip ci]` only when every condition below holds:

1. The owner explicitly approves the skip for that correction.
2. The immediately preceding PR head completed the canonical runtime workflow
   successfully.
3. Every path changed from that passing head to the final head ends in `.md`.
   The changes are limited to non-executable wording, evidence, links, or review
   cleanup guidance; no workflow, script, test, configuration, dependency, or
   application behavior changes.
4. `python scripts/check_docs.py` and `git diff --check` pass on the final head.
5. The final commit carries a GitHub-supported skip instruction and receives an
   independent exact-head review.

Update the PR description before re-review with:

- the final head
- the owner's docs-only skip approval
- the preceding passing head and workflow link
- the exact Markdown file count and path list since that passing head
- the final-head local documentation results
- an explicit statement that no exact-head Actions run exists or is claimed

The reviewer independently verifies the file boundary and reports the missing
exact-head run as an approved limitation, not as passing evidence. Any failed
condition restores the normal exact-head Actions requirement. This exception
never skips the required default-branch workflow after merge.

#### Squash merge message boundary

[GitHub skip instructions](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs)
suppress both `pull_request` and `push` workflows when the triggering commit
message contains `[skip ci]`, `[ci skip]`, `[no ci]`, `[skip actions]`,
`[actions skip]`, or a `skip-checks` trailer. A generated default squash body
may copy the final correction's subject and carry that instruction into the
new `main` commit.

When an approved docs-only correction used a skip instruction and the
established merge method is squash:

1. Pin the merge to the independently reviewed PR head.
2. Supply an explicit squash subject and body that summarize the reviewed PR
   without copying component commit subjects. Require both fields to contain
   none of the supported skip strings and no `skip-checks` trailer.
3. Do not accept the hosting service's generated default squash body.
4. After merge, read the exact merge commit message and require the same clean
   boundary before waiting for its automatic `push` workflow.

The PR-head skip remains valid; only the new default-branch commit must be free
of the instruction so its mandatory workflow can start.

### Post-merge knowledge reconciliation

After every feature PR merge, and before the next feature increment:

1. Require the exact merge commit's automatic `push` workflow to complete.
2. Audit that PR's failed runs and the corrective commits that followed them.
3. Separate reusable runner knowledge from product defects and review-only
   corrections.
4. Prefer an executable regression guard in code, tests, image builds, or the
   canonical verifier. Add or revise this guide only when the reusable decision
   rule is new.
5. Record the outcome in the merged feature's focused Issue. If new knowledge
   exists, link its focused playbook-update Issue and publish that reviewed
   update before the next feature increment. If none exists, add `CI knowledge
   reconciliation: no new reusable finding` to completion evidence; do not
   create an empty documentation change.

#### Bounded `workflow_dispatch` recovery

If an automatic `push` run is absent, inspect the exact merge message before
mutating anything. Manual recovery is allowed only for the known case where a
legacy or generated squash message carried one of the supported skip
instructions despite an otherwise valid docs-only exception.

1. Require the remote `main` head to remain the same exact merge SHA.
2. Require `verify.yml` to support `workflow_dispatch`, and query all runs for
   that SHA. Refuse recovery when a suitable run is queued, active, or already
   completed.
3. Dispatch `verify.yml` once on `main`; do not create an empty trigger commit,
   rerun an unrelated workflow, or dispatch repeatedly.
4. Require the resulting run to report event `workflow_dispatch`, branch
   `main`, and the same exact merge SHA. Require canonical verification and
   unconditional project-scoped teardown to succeed.
5. Record the run as bounded manual recovery, never as an automatic `push`
   run, and promote the newly observed failure mode through this playbook's
   reconciliation workflow.

If the merge message is clean, `main` moved, the absence has another cause, or
the exact-SHA query is ambiguous, stop and diagnose instead of dispatching.

## Change-driven first-push checks

| Changed boundary | Inspect after staging | Durable protection |
|---|---|---|
| Python imports or dependency groups | A runtime module must not import a dev- or type-only package. | Isolate type imports with `TYPE_CHECKING`; smoke-import the installed application inside its production image. |
| Directly executed Python scripts | Resolve imports using the exact documented command and working directory, without an unrecorded `PYTHONPATH`. | Exercise the same script path through the canonical verifier; lint every verification helper. |
| Persistence and migrations | Check real PostgreSQL constraints, transaction order, commit/rollback boundaries, and server-specific types. | Flush dependency rows explicitly where ordering is contractual; prove the order and the real database path. |
| Runtime fixtures and fault data | A check must select records it created, not whichever global row happens to match. | Use deterministic identifiers and clean owned data both before the check and in `finally`. |
| RabbitMQ or Celery topology | Check the pinned broker's queue durability, exclusivity, auto-delete behavior, and removed/deprecated features. | Keep business queues durable; make transient control/event queues exclusive; disable cluster topology the worker does not use. |
| Health and readiness | The health timeout must exceed the legitimate worst-case probe duration. Recovery may precede Docker's aggregate health update. | Budget the full probe; after fault injection poll the affected dependency's direct liveness signal. |
| Retry and recovery proof | Broad faults plus automatic requeue can create connection churn and obscure the one transition under test. | Capture the exact semantic event, quiesce the actor, restore the dependency, then restart only the target service when possible. |
| Diagnostics, artifacts, and teardown | The first causal failure must survive even when diagnostics or cleanup also fail. | Sanitize and upload evidence; keep teardown unconditional and scoped only to `reactorfront-portfolio`. |

Do not add compatibility flags merely to make a pinned service accept obsolete
behavior. Remove unused topology or correct the application contract instead.
Do not replace bounded readiness polling with an unexplained fixed sleep.

## Failed-run triage and promotion

1. Pin the exact PR head and failed run. Read the failing step, retained
   artifacts, and the first causal service error before reacting to teardown
   noise.
2. Classify the failure as product semantics, dependency/image parity,
   invocation portability, real-service behavior, timing, state isolation,
   recovery orchestration, or evidence/cleanup.
3. Reproduce only through safe, authorized checks. Local Docker is optional and
   must not be started merely because Actions failed.
4. Fix the root cause and add the smallest executable regression protection.
5. Run the allowed canonical verification, push the corrected head, and require
   its exact workflow result.
6. Promote only a new reusable decision rule to this guide. Link stable GitHub
   evidence; do not copy raw logs or preserve a one-off workaround.

## Historical evidence ledger

This ledger accounts for every failed PR run through PR #12. PRs
[#2](https://github.com/Kentaro-Ono-jp/Portfolio/pull/2),
[#10](https://github.com/Kentaro-Ono-jp/Portfolio/pull/10), and
[#12](https://github.com/Kentaro-Ono-jp/Portfolio/pull/12) had no failed PR run.

| Failure class and signal | Root cause and durable rule | Current executable guard | Evidence |
|---|---|---|---|
| Production import failed with `ModuleNotFoundError: mypy_boto3_s3`. | A type-only dependency leaked into runtime. Separate type imports and smoke-import the production install. | [`storage.py`](../../apps/api/src/reactorfront_api/storage.py) and the [API Dockerfile](../../infra/docker/api/Dockerfile) | PR #4 [failed run 29639639004](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29639639004), [fix `df47d81`](https://github.com/Kentaro-Ono-jp/Portfolio/commit/df47d81f2f932132801285c2bab3dce9315fffb0), chain closed by [run 29639908626](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29639908626). |
| Real submission returned 503 with a PostgreSQL `ForeignKeyViolation`; a later review correction reproduced it. | ORM insertion order was not the FK contract. Explicitly flush document, job, then outbox rows and lock that sequence with a regression test. | [`persistence.py`](../../apps/api/src/reactorfront_api/persistence.py) and [`test_persistence.py`](../../apps/api/tests/test_persistence.py) | PR #4 [failed runs 29639776329](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29639776329) and [29641893290](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29641893290); fixes [`2cecec2`](https://github.com/Kentaro-Ono-jp/Portfolio/commit/2cecec26e82e3034ffbae3f73f6f4db29bfc2425) and [`05b3532`](https://github.com/Kentaro-Ono-jp/Portfolio/commit/05b35322f2bf07a4757eaf0791e5a9c0e5d6ab7a); successful runs [29639908626](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29639908626) and [29642127264](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29642127264). |
| The outbox verifier could not create its simulated crashed-dispatcher lease. | Runtime proof shared stale database state. Own deterministic records and clean before and in `finally`. | [`test_integration.py`](../../apps/api/tests/test_integration.py) and [`verify_outbox_runtime.py`](../../scripts/verify_outbox_runtime.py) | PR #6 [failed run 29666718552](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29666718552), [fix `58be144`](https://github.com/Kentaro-Ono-jp/Portfolio/commit/58be144ae074da5616f6907c563a2007793aaba6), [successful run 29666913637](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29666913637). |
| Direct ML verifier execution could not import `scripts.pdf_fixture`. | Direct script execution placed `scripts/`, not the repository root package assumption, on the import path. Use imports valid for the exact invocation. | [`verify_ml_runtime.py`](../../scripts/verify_ml_runtime.py) is linted and executed by [`verify.py`](../../scripts/verify.py). | PR #8 [failed run 29672537036](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29672537036), [fix `549d088`](https://github.com/Kentaro-Ono-jp/Portfolio/commit/549d0889f03f3d7a471c31263fd5cb60656299f0); the next run advanced to RabbitMQ startup and the chain closed at [29674130187](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29674130187). |
| RabbitMQ 4.3 rejected transient non-exclusive Celery control and event queues. | Deprecated topology survived in two observed layers. Make transient control/event queues exclusive rather than weakening broker policy. | [`celery_app.py`](../../apps/ml/src/reactorfront_ml/celery_app.py) and [`test_celery_app.py`](../../apps/ml/tests/test_celery_app.py) | PR #8 [failed runs 29672715519](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29672715519) and [29673187660](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29673187660); fixes [`640ddbd`](https://github.com/Kentaro-Ono-jp/Portfolio/commit/640ddbd9fc9dadc864cbc9d72c85ed8ff16135ab) and [`674fd1b`](https://github.com/Kentaro-Ono-jp/Portfolio/commit/674fd1b5e96e0e700b2e06b284395671cecf28aa). The next run advanced past the recorded queue rejection before failing worker readiness. |
| Compose timed out waiting for the ML worker and reported it unhealthy; the log did not contain a RabbitMQ queue rejection. | The corrective commit removed unused gossip/mingle bootsteps and the next run passed. Treat that causal link as bounded historical inference, while retaining the independently justified rule that a single-purpose worker must not enable unused cluster topology. | The [ML Dockerfile](../../infra/docker/ml/Dockerfile) and [`check_ml_compose_boundary.py`](../../scripts/check_ml_compose_boundary.py) | PR #8 [failed run 29673641464](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29673641464), [correction `1826afd`](https://github.com/Kentaro-Ono-jp/Portfolio/commit/1826afd4cea1ac3eda2595e0db983f49cc9a37a4), [successful run 29674130187](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29674130187). |
| Compose marked the ML worker unhealthy although the full readiness command could complete. | The timeout did not cover model, object-storage, and broker probes on the runner. Budget the complete legitimate probe. | ML healthcheck in [`compose.yaml`](../../compose.yaml) and readiness behavior in [`health.py`](../../apps/ml/src/reactorfront_ml/health.py) | PR #8 [failed run 29675397127](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29675397127), [fix `1f5c4b7`](https://github.com/Kentaro-Ono-jp/Portfolio/commit/1f5c4b7db49dd3c4ed0e4f50bee60650cec4faea); the next run passed readiness, and the chain closed at [29676610655](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29676610655). |
| After pause/unpause fault injection, Compose still observed MinIO as unhealthy. | Dependency liveness recovered before aggregate Docker health converged. Poll the affected service directly before dependent restart. | `wait_for_minio_liveness` in [`verify_ml_runtime.py`](../../scripts/verify_ml_runtime.py) | PR #8 [failed run 29675923281](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29675923281), [fix `d7e59e1`](https://github.com/Kentaro-Ono-jp/Portfolio/commit/d7e59e115a361558198cf41bd624e3e50cf7c130); the next run reached retry recovery, and the chain closed at [29676610655](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29676610655). |
| Broker/result fault caused repeated `reject requeue=True` churn during recovery. | The verifier left the actor retrying while a broad fault was restored. Capture one semantic requeue, stop the worker, restore liveness, then restart only that worker with no dependency restart. | Fault and restart orchestration in [`verify_ml_runtime.py`](../../scripts/verify_ml_runtime.py) | PR #8 [failed run 29676215101](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29676215101), [fix `3276457`](https://github.com/Kentaro-Ono-jp/Portfolio/commit/3276457a7429bd885c626a6d41b2ac03a9a25a3c), [successful run 29676610655](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29676610655). |

The 3 PR #4 failures, 1 PR #6 failure, and 7 PR #8 failures total 11. A
successful later run proves the whole chain, while the linked corrective commit
and disappearance of the earlier signal identify the individual fix.
