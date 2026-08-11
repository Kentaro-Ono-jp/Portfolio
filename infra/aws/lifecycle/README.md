# AWS TTL-first lifecycle

This directory implements Delivery Specification 0004 Step 5 and is the
shared execution surface for the Step 6 GitHub automation. The public
entrypoint is:

```text
python scripts/aws_lifecycle.py <command>
```

The lifecycle consumes the frozen persistent IAM and controller contract. A
normal command never creates, updates, versions, attaches, detaches, repairs,
or recalculates IAM. Static IAM maintenance remains a separately reviewed
owner-admin operation; the accepted result persists after an environment is
destroyed or this focused Issue closes.

The one non-IAM controller maintenance exception is the image project's inline
buildspec. When every other image-project field, role, input, log target, and
ownership tag is already exact, preflight may update only that exact project's
buildspec from the checked-out repository. It then reads back the normalized
SHA-256 before starting a build and reports the write plus before/after hashes.
Destroy-project drift, any other project drift, and any IAM or service-role
change still fail closed. The operator has no CodeBuild `iam:PassRole` grant.

## Ordered interface

```text
configure
-> preflight
-> publish-images
-> register-fallback
-> apply
-> migrate
-> seed
-> smoke
-> status / extend
-> destroy
-> sweep
```

`deploy` composes the construction commands through authenticated smoke but
deliberately leaves the verified fallback in place. `destroy --mode manual`
uses the exact operator-to-destroy-role path. `destroy --mode scheduled`
moves the already verified one-time fallback to an imminent time so the real
Scheduler-to-CodeBuild path can be proved without waiting for the original
maximum deadline. `controller-destroy` is reserved for the exact persistent
CodeBuild project and rejects any other caller.

## Credential and configuration boundary

The CLI uses the standard AWS credential chain for one of two explicit caller
modes. `source-user` preserves the existing exact credential-only human user;
`github-automation` accepts only the exact `reactorfront-automation` assumed
role and `portfolio-github-<run-id>` session shape. The configured GitHub event
must map exactly from `workflow_dispatch` to `manual` or from `schedule` to
`monthly`. Both modes assume their exact operator and perform frozen
static-IAM plus persistent-controller attestation before lifecycle work. An
arbitrary pre-assumed session is rejected, and configuration is never read
from a credential file.

`configure` derives account-bound role ARNs, ECR URLs, state key, controller
names, and ownership identities from explicit public inputs plus the sanitized
source-account identity. The generated configuration is stored below the
repository's `.git` directory and is never committed. It contains no AWS
credential or application secret.

The remote S3 control capsule is encrypted and bound to the exact environment,
state key, source SHA, repository, image digests, and controller. A separate
encrypted synthetic-reviewer capsule exists only between seed and proved
zero-residue cleanup. Neither capsule is public evidence.

## Persistent controller

`controller-contract.json` defines two artifact-free, environment-specific
CodeBuild projects outside the environment state:

- the privileged image project clones the exact public commit, builds the
  repository Dockerfiles, and pushes only to the three exact persistent ECR
  repositories;
- the non-privileged destroy project clones the exact public commit, verifies
  the selected Python and AWS CLI v2 entrypoints, reads both exact controller
  inputs, proves its exact caller, and preflights the one allowed destroy-role
  assumption before downloading tools. The CodeBuild role cannot mutate
  lifecycle or Terraform state itself. The assumed destroy role destroys the
  exact remote state, deletes the three exact published image digests from the
  persistent repositories, and performs the service/tag sweep. The project has
  two static automatic retries because Scheduler delivery proves only that
  CodeBuild accepted the start request, not that the build itself succeeded.

Only the exact image project is operator-reconcilable. This avoids an
owner-admin browser stop whenever its repository-owned buildspec advances,
without granting mutation of the destroy project or a path to pass another
service role. The reconciliation is not a hidden preflight: it is allowed only
after every non-buildspec field passes and is included in sanitized effect
evidence.

The fixed EventBridge Scheduler schedule targets only the destroy project and
lives in an environment-specific persistent schedule group. The execution-role
trust uses that exact schedule-group ARN because Scheduler does not support an
individual schedule ARN as `aws:SourceArn`. Its action-after-completion is
`NONE`: target invocation is not proof of
successful destroy, so the schedule, lease, and remote checkpoint survive
until Terraform state, the exact deployment images, and every service-specific
residue category are zero.

## Lease, retry, and TTL

The lifecycle lease is acquired with an S3 `If-None-Match: *` conditional
write. A conflicting manual/monthly/apply/destroy path therefore fails closed.
Every remote checkpoint update uses the previous ETag. Missing, stale, foreign,
or interrupted state is never relabeled as success. If lease creation alone
succeeded before the first configuration checkpoint, only the same exact
source SHA may recover that isolated lease; a configuration checkpoint without
its matching lease is always rejected.

The source-wide lease is not treated as operation ownership. Before the first
Cognito or credential-capsule mutation, `seed` conditionally checkpoints a
random invocation owner and `running` status with the current configuration
ETag. A stale or foreign owner therefore fails before external effects. The
matching owner is retained only in the checkout-private runtime directory, and
an OS-released local lock prevents two processes in that checkout from using it
at once. After interruption, only that exact local owner may resume the remote
intent; another checkout fails closed. Successful seed removes both the remote
intent and the local recovery identity only after the credential capsule,
Cognito user, and final `seed=passed` checkpoint agree.

Every checkout-private runtime path is resolved to an absolute path before
Terraform receives `-chdir`. The copied root, backend configuration, variable
file, saved plan, apply, state operations, and destroy therefore share one
path origin even when the workflow supplies a repository-relative config path.
Terraform emits no-color diagnostics, and only a public-safe `Error:` line may
leave the private diagnostic boundary.

The GitHub workflow installs the pinned Node, pnpm lockfile dependencies, and
Chromium Playwright runtime before OIDC credential acquisition. Lifecycle
preflight and resume also require both Node and pnpm, while smoke repeats the
command check before using the private reviewer credential capsule.

Destroy also handles an interruption before all three image digests were
checkpointed: it resolves the deterministic immutable tag in each exact
repository, validates any digest already recorded, removes any partial image,
and skips Terraform only when apply could not yet have created resources.
Terraform destroy deliberately uses the remote state without a provider-wide
refresh so the destroy role does not need application-secret or broad metadata
read authority. Before destroy, the two exact secret-version addresses are
detached from Terraform state; deleting each still-managed parent secret
removes its versions without ever granting the destroy role `GetSecretValue`.
The subsequent service-specific and tag sweep is the
independent, fail-closed proof of actual absence. Provider delete waiters retain
only the exact owned/named read actions they require; they do not gain general
secret-value authority. Stale Resource Groups Tagging API mappings, including
deleted security-group rules, are ignored only when the exact owning-service
inventory has independently proved their parent resource absent; unknown tagged
resource kinds remain blocking.
Exact environment-prefixed Secrets Manager deletion does not depend on a
resource tag that disappears during forced deletion, so an interrupted delete
remains idempotent without granting another environment's secret ARN.

Fallback registration first creates a fresh create-only Terraform plan, then
registers and reads back the one-time schedule before apply. Normal `deploy`
and `register-fallback` calls default to 60 minutes. Explicit values from 15 to
120 minutes remain valid; the change to the normal default does not introduce
a 60-minute-only restriction. The accepted maximum remains 120 minutes from
registration. `extend` remains valid only for an active fallback and cannot
cross that original maximum. Manual destroy may begin at any earlier time.

## GitHub automation

`.github/workflows/aws-deploy.yml` is the only deployment workflow. It accepts
only owner-started `workflow_dispatch` and repository-owned `schedule` events,
uses `contents: read` plus `id-token: write`, checks out the exact `main` SHA,
and obtains two short-lived OIDC sessions: one for deploy and one for cleanup.
It never consumes an AWS access-key secret. Manual and monthly runs share one
non-cancelling GitHub concurrency group while their AWS names, state keys,
controls, roles, controller projects, and ownership tags stay isolated.

The permanent schedule starts at 13:00 `Asia/Tokyo` on the first day of each
month. A separately recorded temporary cron may be added to `main` only long
enough to prove a real `schedule` event; it maps to the same `monthly` path and
is removed after the accepted proof. The `aws-deployment` environment has no
required reviewer and no wait timer, so neither event has a per-run manual
approval. The independent 60-minute AWS fallback is a cleanup deadline, not a
GitHub job-duration limit.

The first live OIDC/IAM/environment installation is a separate owner-admin
maintenance operation. `scripts/aws_automation_maintenance.py` renders the two
checked-in static profiles, changes only their named persistent objects when
run with the recorded owner checkpoint, and then reads the monthly controller,
ECR, and state contracts back. The normal deployment workflow never calls that
maintenance script and never repairs IAM.

## Verification

AWS-free proof covers phase ordering, idempotent same-phase retry, failure and
resume identity, exact configuration binding, immutable image identities,
TTL/extend bounds, truthful unknown state, and public-output redaction:

```text
python scripts/verify.py --groups aws-static
```

Real commands report sanitized direct-AWS-CLI call/write/tracked-create effects
and explicitly mark Terraform-provider plus controller-internal effects as
excluded from that scope. Live evidence records those other surfaces
separately; it never relabels the direct-call subtotal as a lifecycle total.
Raw provider, Terraform, CodeBuild, browser, credential, state, secret,
account, and private path values are retained only in their private execution
surfaces and are never copied into public evidence.

The final tag sweep treats an unknown tagged resource kind as residue. For a
known kind, its owning service-specific inventory is authoritative because the
Resource Groups Tagging API can temporarily retain a mapping after the resource
has already been deleted.

## Issue 114 live checkpoint

The owner-authorized Step 7 cycle completed the public lifecycle through three
immutable images, verified fallback, apply, three healthy ECS tasks, migration,
synthetic seed, authenticated external-HTTPS asynchronous smoke, manual
destroy, and 27-category zero residue. The fallback and remote controls were
removed only after that proof. A single billing-read Cost Explorer page
returned an estimated `$0.000415` for the scoped two-day window; its accepted
API-query charge and delayed estimate are supporting evidence only.

The implementation history is not rewritten as uniformly green. Seven real
Scheduler-to-CodeBuild destroy invocations failed before the first complete
automatic destroy. The first retained a checksum filename that no longer
matched the downloaded Terraform archive. The next four exposed the complete
CodeBuild runtime binding: the default `python3` was 3.10, while the supported
`python: 3.13` selection is implemented by `pyenv global` but the build shell
could still resolve the OS interpreter ahead of the selected shim, including
through `python` and `pyenv exec`. The following two reached the exact Python
runtime and exposed that the frozen Console IAM policy allowed the controller
configuration object but not the equally required lifecycle lease. The
buildspec now preserves the official archive filename, invokes the exact
Python 3.13 and AWS CLI v2 paths defined by the pinned image, and preflights the
exact caller, both controller inputs, and the one destroy-role assumption. The
CodeBuild identity policy now reads those two exact objects and cannot mutate
them or Terraform state. The next scheduled invocation passed install, build,
Terraform destroy, the 27-category residue sweep, and control cleanup; an
independent read-only sweep also reported zero residual resources. Focused
PR/Issue evidence keeps that successful run separate from all diagnostics.
