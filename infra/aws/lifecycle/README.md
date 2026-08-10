# AWS TTL-first lifecycle

This directory implements Delivery Specification 0004 Step 5. The public
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

The CLI uses the standard AWS credential chain only for the existing weak
source-user authentication material. It verifies that identity, assumes the
exact operator, and performs frozen static-IAM plus persistent-controller
attestation before lifecycle work. It never reads deployment configuration
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
  the pinned Terraform archive, assumes only the exact destroy role, destroys
  the exact remote state, deletes the three exact published image digests from
  the persistent repositories, and performs the service/tag sweep. The project
  has two static automatic retries because Scheduler delivery proves only that
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
registers and reads back the one-time schedule before apply. The accepted
maximum is 120 minutes from registration. `extend` is valid only for an active
fallback and cannot cross that original maximum. Manual destroy may begin at
any earlier time.

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

The implementation history is not rewritten as uniformly green. An earlier
real Scheduler-to-CodeBuild destroy invocation failed before destroy because
the downloaded Terraform archive had been renamed while its official checksum
line retained the original filename. The buildspec now downloads, verifies,
extracts, and removes the same pinned filename. The focused PR/Issue evidence
records the subsequent exact-head automatic-path result separately from that
failed diagnostic run.
