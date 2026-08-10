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

The fixed EventBridge Scheduler schedule targets only the destroy project.
Its action-after-completion is `NONE`: target invocation is not proof of
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
