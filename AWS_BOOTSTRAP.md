# Portable AWS bootstrap and bounded runtime authority

Start with the canonical
[portable managed-ephemeral AWS operations guide](AWS_OPERATIONS_GUIDE.md) for
the visual overview, complete third-party order, lifecycle, recovery, cost,
limitations, and evidence. This document is the deeper reference for the
persistent bootstrap and static authority boundary.

This guide covers the persistent control layer for the fourth vertical slice.
It creates only an encrypted Terraform state bucket, three immutable ECR
repositories, one fixed Permissions Boundary, and purpose-specific IAM roles.
It does not create an application environment, publish an image, register a
destroy schedule, run deployment automation, or prove a live AWS lifecycle.

The deploying account owner supplies every account, region, name, repository,
state-key, owner-principal, and GitHub trust input. The public implementation
does not read a maintainer profile, private overlay, credential file, state
file, or machine-local note. All AWS resources, retained versions, images, and
cost belong to the deploying account.

## Persistent static IAM lifecycle

Bootstrap is a one-time account-owner operation, not the first phase of every
deployment. In the maintainer account the selected live implementation is the
Console-owned contract under `infra/aws/environment/console-iam/`; the
Terraform bootstrap remains the portable equivalent for a new third-party
account. After installation, normal deployment treats IAM as immutable:

```text
exact source user or GitHub automation session
-> exact environment operator AssumeRole
-> read-only static IAM attestation
-> deployment preflight
-> deploy
```

It must never perform quota calculation, policy generation or splitting,
policy-version creation, attachment changes, boundary changes, bootstrap IAM
apply, or drift repair. Any mismatch with the checked-in canonical document
digests fails closed and returns to a separately approved static-IAM
maintenance operation by an `owner-admin principal`. The exact administrator
IAM user name is private and is never a public contract or evidence field.

## Persistent resources

- one owner-named S3 bucket with versioning, AES-256 server-side encryption,
  Bucket Owner Enforced ownership, all four Block Public Access settings,
  secure-transport and encrypted-write bucket-policy guards, bounded
  noncurrent-version retention, and Terraform's S3 lockfile contract;
- independent `${prefix}/web`, `${prefix}/api`, and `${prefix}/ml` ECR
  repositories with tag immutability, encryption, scan-on-push, seven-day
  untagged cleanup, and a maximum of twenty tagged images;
- one `${prefix}-permissions-boundary` managed policy under the fixed
  `/${prefix}/` path; and
- two shared roles plus eight one-purpose roles for every explicitly declared
  environment.

The Terraform lifecycle prevents accidental deletion of the state bucket,
ECR repositories, boundary, and roles. That protection is deliberate: later
environment destroy authority cannot remove persistent bootstrap resources.

## Authority map

| Authority | Scope |
|---|---|
| IAM manager | Creates only the exact declared, tagged environment roles with the fixed boundary. Terraform retains role deletion and inline-policy ownership. The manager cannot attach, replace, or delete policies; create users, groups, access keys, login profiles, arbitrary managed policies, or global roles; or remove/replace a boundary. |
| Environment operator/deployment | Uses the isolated environment state/control keys, publishes to the three owned ECR repositories, and passes exact task/fallback roles. Issue #116 deliberately grants broad Portfolio runtime-service actions inside the fixed permissions boundary instead of maintaining a per-API allowlist. |
| Task execution | Pulls owned images, writes the environment log groups, and reads only environment-prefixed injected secrets. |
| Web workload | Has caller-identity proof only and no application-data authority. |
| API workload | Owns only the exact environment application bucket objects. PostgreSQL remains an application connection boundary, not an IAM administration grant. |
| ML workload | Reads/writes only the exact environment application objects; it cannot delete them and receives no PostgreSQL or Cognito administration authority. |
| GitHub automation | GitHub OIDC trust requires the exact audience, repository, `main` ref, protected environment, workflow name/ref, and customized `repo/context/job_workflow_ref/event_name` subject. The short-lived role can assume only the exact manual/monthly operator and destroy roles. |
| Scheduler fallback | Uses the exact persistent environment schedule group and starts only that environment's destroy project. The trust SourceArn remains the exact group ARN. |
| CodeBuild fallback | Reads the exact environment lifecycle inputs, writes its exact log, and assumes the exact destroy role. Terraform state and lifecycle mutation begin only after the separate destroy role is assumed. |
| Destroy | Receives broad application-service actions inside the fixed boundary so cleanup does not fail one API at a time. It still cannot mutate IAM or the boundary, and the lifecycle accepts success only after the isolated state and residual inventories are empty. |

Every delegable role carries the same fixed boundary. The boundary is the
durable safety guardrail: it fixes role purposes, persistent state/ECR
namespaces, IAM creation and mutation limits, application service families,
and exact `iam:PassRole` role/service pairs. Bootstrap-owned inline identity
policies are not replaceable by the delegated IAM manager; they bind generated
application resources to the expected Portfolio topology. Issue #116 accepts
broad identity-policy service actions for operator, destroy, and controller
roles; the effective permission is always the intersection with the fixed
boundary. Exact GitHub OIDC trust, environment/state separation, TTL-first
fallback, mandatory destroy, and zero-residue proof carry the runtime safety
decision instead of a fragile per-API deployment allowlist.

This separation is deliberate. Duplicating every generated-resource ownership
predicate in the one fixed boundary consumed nearly all of AWS's managed-policy
quota and would have made later service corrections unsafe. Required positives
must pass identity, boundary, and their intersection. Ownership inverses must
fail the immutable identity policy and the effective intersection; the broader
service/purpose boundary is reported as such instead of being mistaken for the
ownership-enforcement layer. IAM mutation and PassRole remain exact adversarial
boundary tests because those are delegation and escalation ceilings.

Terraform and the AWS-free verifier reject generated policies before any AWS
write when the fixed managed boundary exceeds 5,632 characters, deliberately
reserving at least 512 characters below AWS's 6,144-character quota; they also
reserve 512 characters below the 10,240-character aggregate inline-policy
quota and reject trust policies above the portable 2,048-character default. The
delegated-authority proof combines
an adversarial wildcard `iam:PassRole` identity policy with the boundary across
every source role, declared target, synthesized undeclared same-path target,
global/external target, and supported/wrong service. Only a same-environment
operator passing one of the exact declared workload, Scheduler, or CodeBuild
role ARNs to its exact service remains effective.

Operator control-plane proof uses the action's real authorization context:
creation uses supported request tags and the actual HTTP API collection or
resource-less create resource; EC2 inventory carries no fabricated request
tags; `ec2:CreateTags` requires an approved `ec2:CreateAction` and cannot take
ownership of an existing EC2 resource; security-group mutation proves the
existing group resource-tag context and the optional new rule request-tag plus
dependent-tagging contexts separately; every rendered HTTP API write verb on
an existing API or child resource requires the complete ownership resource-tag
tuple; and Cognito and Cloud Map tagging actions are exercised separately.
Cloud Map `CreateService` proves both required authorizations independently:
the existing namespace must carry the complete ownership tuple and the new
service ARN must receive exactly the four ownership tags. Cognito retagging
requires the existing pool to carry that tuple. Request-tagged creation rejects
cross-environment, cross-repository, and undeclared fifth-key variants. Every
request is evaluated independently at identity, boundary, and effective layers
with expectations that name the actual enforcing layer.

API Gateway V2 tagged creates also have a companion authorization. Live AWS
execution proved that this dependent `TagResource` authorization exposes
neither request nor resource ownership tags. It uses `apigateway:POST` + `PUT`
on `/tags/*`, `PATCH` on the new target, and—for `CreateStage` and
`CreateVpcLink`—the literal `apigateway:TagResource` action on the same
`/apis/*/stages` and `/vpclinks` collection resource used by the create. The
Service Authorization table maps standalone tagging to HTTP verbs, but repeated
live creates still requested this literal dependent action after all three
mapped verbs were present; the IAM Console validator currently labels the
literal action unknown even though IAM stores it and the live service consumes
it. The static identity therefore grants only those
exact action/resource pairs without a tag condition; target `POST` + `PUT` and
all later operations retain resource-tag conditions. Because these resources
expose neither a distinguishable create-only action nor a prior-resource-tag
condition, static proof records this as the same kind of owner-accepted
creation-time tagging limitation described below
for Cloud Map, rather than claiming foreign-target isolation. RDS provider
polling uses the wildcard resource for the read-only
`rds:DescribeDBInstances` list operation; that action is isolated as global
metadata read and does not grant RDS mutation or secret access.

HTTP API access logging has a separate CloudWatch Logs dependency. AWS's
official logging guide requires the account-level log-delivery actions, and the
Service Authorization table exposes no resource type or scoping condition for
them. The operator therefore grants only `CreateLogDelivery`,
`DeleteLogDelivery`, `DescribeResourcePolicies`, `GetLogDelivery`,
`ListLogDeliveries`, `PutResourcePolicy`, and `UpdateLogDelivery` at
`Resource: "*"`; log-group creation, tagging, retention, and later access stay
bound to the exact `/portfolio/${NAME_PREFIX}/${ENVIRONMENT}/*` log groups.
The destroy role receives only the corresponding `ListLogDeliveries`,
`GetLogDelivery`, and `DeleteLogDelivery` account-level subset needed to remove
that Stage delivery; it does not receive the create/update/resource-policy
actions.

ECS `DescribeTaskDefinition` is another resource-less read in AWS's Service
Authorization table. It therefore uses `Resource: "*"` only in the global
metadata-read statement; registration, tagging, and service mutation remain
scoped to the environment task-definition and service ARNs.

Amazon MQ `CreateBroker` is resource-less at authorization time. The fixed
boundary therefore permits only that action for the environment-operator
purpose, while its bootstrap-owned identity policy requires the complete four
request tags and exact tag-key set. Wrong, missing, or additional ownership
tags fail the immutable identity layer and effective intersection; workload
roles fail the boundary as well.

AWS maps `CreatePrivateDnsNamespace` and `CreateService` to each create action
plus `servicediscovery:TagResource`; provider 6.58.0 passing tags directly in
the create payload does not remove that dependent authorization. The operator
identity and its separately generated boundary therefore both permit
`TagResource` at `Resource: "*"`, with the identity limited to the exact four
request tags and tag-key set. AWS exposes no resource-level or prior-resource-
tag condition for that API, so the same exact request can overwrite the tuple
on an unrelated existing namespace or service. Static proof records that
foreign-target allow rather than claiming isolation, while rejecting wrong,
missing, or additional ownership tags.

The selected live path is the persistent Console-owned IAM contract; it is not
reset or replaced by this bootstrap root. The bootstrap-generated equivalent
retains the same accepted Cloud Map exception so both implementations describe
the same authority. The exception is limited to a dedicated deployment account
and trusted account-owner operator. Inventory Cloud Map before and after use,
proceed only when unrelated namespaces and services are absent, and stop for
owner review otherwise. Exact namespace ownership still gates service creation
and exact ownership still gates destroy.

The Step 6 GitHub workflow requires the repository owner to configure GitHub's
OIDC subject template with `use_default: false` and the
ordered `include_claim_keys` value `repo`, `context`, `job_workflow_ref`,
`event_name`, with `use_immutable_subject: true`. The checked-in automation
contract records the exact stable owner and repository IDs, and
`github_oidc_repository_subject` must match the resulting immutable `repo:`
segment. AWS does not expose `event_name` as a direct GitHub OIDC
condition key, so the trust document matches the two complete customized
subjects ending in `event_name:workflow_dispatch` and `event_name:schedule`.
Owner maintenance, the workflow claim guard, and the live read-only static-IAM
attestor all consume this same immutable subject contract; the attestor cannot
fall back to the legacy name-only subject.

`.github/workflows/aws-deploy.yml` uses that exact protected environment,
short-lived OIDC role, and `main` workflow identity. Before requesting OIDC,
it installs the repository-pinned Node, pnpm dependencies, and Chromium
Playwright runtime required by authenticated smoke, so a missing toolchain
cannot create AWS resources. Owner-started dispatch
maps only to `manual`; repository schedules map only to `monthly`. The
permanent schedule is the first day of every month at 13:00 `Asia/Tokyo`, and
the environment has no required reviewer or wait timer. Ordinary pushes and
verification, pull requests, forks, Dependabot, and unapproved refs have no
AWS credential or write path. Initial repository/OIDC/static-IAM configuration
is still a separately recorded owner-admin operation; normal workflow runs
never perform it or self-heal drift.

## Owner inputs and local safety

Use Terraform `1.15.8` and the locked AWS provider `6.58.0`. Copy the visibly
synthetic example to an ignored owner file and replace every value:

```console
cp infra/aws/bootstrap/terraform.tfvars.example infra/aws/bootstrap/owner.auto.tfvars
```

The exact owner principal (an IAM user or role) and GitHub OIDC provider must
already exist in the target account. Human operator trust does not require MFA;
deployment authority remains on the assumed role rather than the source IAM
user. `github_oidc_repository_subject` is an explicit trust input rather
than a value inferred from a maintainer profile. Terraform's
`allowed_account_ids` check fails closed if the active standard AWS credential
chain targets another account. Do not place access keys, tokens, secrets,
backend credentials, or secret values in Terraform variables. Do not publish a
real variable file, plan, state, backend file, or unfiltered provider error.

Each environment key must have the exact form
`environments/<environment>/terraform.tfstate`. The bootstrap key must remain
under `bootstrap/`. Reusing a key across environments is rejected.

## First initialization and backend handoff

The S3 bucket cannot store Terraform state before it exists. The first apply
therefore uses Terraform's implicit local backend, then migrates that exact
state into the newly created bucket. Review the plan privately before the
explicit owner-authorized apply:

```console
terraform -chdir=infra/aws/bootstrap init
terraform -chdir=infra/aws/bootstrap plan -out=bootstrap.tfplan
terraform -chdir=infra/aws/bootstrap apply bootstrap.tfplan
```

An apply is an AWS write and is not performed by ordinary repository
verification. It creates only the persistent bootstrap resources; it does not
consume one of the three billable application construction attempts.

After the successful initial apply, generate the ignored partial backend
files from the exact output values, then migrate the same state:

```console
python scripts/aws_bootstrap_backend.py \
  --bucket example-owner-chosen-state-bucket \
  --region us-east-1 \
  --key bootstrap/terraform.tfstate
cd infra/aws/bootstrap
terraform init -migrate-state -backend-config=backend.hcl
terraform state pull
```

On PowerShell, place the three Python arguments on one line or use PowerShell's
normal continuation syntax. The generated `backend_override.tf` declares only
the S3 backend type. `backend.hcl` contains only bucket, key, region,
`encrypt = true`, and `use_lockfile = true`; it never stores credentials. Both
files are ignored and reproducible from explicit inputs.

Confirm the remote state and a successful no-change plan before archiving the
initial local state in owner-controlled secure storage. Never delete or
overwrite the only known-good state during handoff.

## Repeated execution, adoption, and recovery

For a later public clone whose backend already contains the migrated bootstrap
state:

1. recreate the ignored owner variables;
2. run `scripts/aws_bootstrap_backend.py` with the same exact bucket, region,
   and bootstrap key;
3. run `terraform init -reconfigure -backend-config=backend.hcl`; and
4. require `terraform plan` to report only reviewed intentional drift.

Repeated apply is idempotent when inputs and AWS state agree. If the bucket
exists but remote state is absent, stop: recover the original local state or
perform an explicit resource-by-resource import before apply. Never create a
second bucket or guess ownership. S3 versioning is the recovery boundary for
accidental state-object replacement; the `.tflock` object is the concurrency
boundary. Do not delete a live lock without proving that no Terraform process
owns it.

ECR and IAM adoption follows the same rule: import an existing exactly owned
resource into the canonical state rather than renaming, recreating, or
silently taking ownership. Changing account, partition, region, prefix,
repository identity, state key, role path, boundary, or trust is a reviewed
bootstrap change.

## AWS-free verification and policy proof

Canonical local and GitHub verification performs no AWS API call:

```console
python scripts/verify.py --groups aws-static
```

The emitted machine fields are explicitly named `staticVerifierAwsApiCalls`,
`staticVerifierAwsWrites`, and, for the environment proof,
`staticVerifierAwsResourcesCreated`. They describe only that verifier process;
`liveAwsHistoryIncluded=false` prevents those zeros from being read as Issue-
wide totals. The real history includes persistent IAM creation, boundary and
role configuration, operator assumption, the bounded `3/3` construction
attempts, and cleanup.

That group checks Terraform formatting, provider lock, `validate`, TFLint,
mock-provider plans, backend-generation contracts, and the versioned
allow/deny matrix in
[`infra/aws/bootstrap/policy-matrix.json`](infra/aws/bootstrap/policy-matrix.json).
The matrix combines each identity policy with the fixed boundary and separately
evaluates trust policies. It proves intended positives and privilege-
escalation, cross-environment, persistent-resource, wrong-service, fork, pull-
request, push-event, audience, repository, workflow, and ref negatives. Tagged
HTTP API, Cognito user-pool, and Cloud Map namespace/service deletion is paired
with cross-environment, cross-repository, unmanaged, and persistent negatives
even though those resource IDs do not encode the environment name. The verifier
also records exact generated policy sizes for both the synthetic example and
the maximum accepted 20-character prefix, the complete 1,656-case delegated
`iam:PassRole` ceiling, 60 tagged-destroy layer/context decisions, and 336
operator control-plane layer/context decisions.

EC2 create authorization is multi-resource as well: subnet, Security Group,
and route-table creation each requires request-tag authority for the new
resource plus resource-tag authority for the already-owned VPC. VPC-endpoint
creation additionally requires the already-owned route table. The
managed-environment verifier removes every VPC and route-table companion row in
turn and requires each mutation to fail closed.

This repository-owned evaluator is static contract proof, not AWS IAM Access
Analyzer or the live IAM Policy Simulator. A later owner-authorized AWS
simulation may add read-only sanitized evidence, but it must not mutate IAM or
create a resource. Static proof now covers both this persistent bootstrap and
the Step 4
[managed-environment definition](infra/aws/environment/README.md), plus the
Step 5 lifecycle and Step 6 workflow contracts. Its AWS-free zero counters do
not claim that a root has been applied, a live OIDC/environment configuration
exists, or a real workflow/lifecycle run passed.
