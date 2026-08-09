# Portable AWS bootstrap and least privilege

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
| Environment operator/deployment | Uses only that environment state key, publishes to the three owned ECR repositories, passes exact task/fallback role ARNs to exact AWS services, inventories EC2 without fabricated tags, and creates or mutates only request-tagged/resource-tagged environment resources. |
| Task execution | Pulls owned images, writes the environment log groups, and reads only environment-prefixed injected secrets. |
| Web workload | Has caller-identity proof only and no application-data authority. |
| API workload | Owns only the exact environment application bucket objects. PostgreSQL remains an application connection boundary, not an IAM administration grant. |
| ML workload | Reads/writes only the exact environment application objects; it cannot delete them and receives no PostgreSQL or Cognito administration authority. |
| Future automation | GitHub OIDC trust requires the exact audience, repository, `main` ref, protected environment, workflow name/ref, and a customized subject that encodes only `workflow_dispatch` or `schedule`. It can assume only exact environment operator/destroy roles. |
| Scheduler fallback | Starts only that environment's future CodeBuild destroy project. |
| CodeBuild fallback | Uses only that environment state and lock objects, writes its exact destroy log, and assumes only that environment destroy role. |
| Destroy | Deletes only exact environment-named or correctly tagged application resources. It cannot mutate state, ECR, IAM, the boundary, or another environment. |

Every delegable role carries the same fixed boundary. The boundary is the
durable safety guardrail: it fixes role purposes, persistent state/ECR
namespaces, IAM creation and mutation limits, application service families,
and exact `iam:PassRole` role/service pairs. Bootstrap-owned inline identity
policies are not replaceable by the delegated IAM manager; they bind generated
application resources to the exact environment, repository, managed, and
nonpersistent ownership tuple. The effective permission is always the
intersection of these two layers.

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

The future GitHub workflow and repository OIDC customization are Step 6
non-targets. Before that workflow requests a token, the repository owner must
configure GitHub's OIDC subject template with `use_default: false` and the
ordered `include_claim_keys` value `repo`, `context`, `job_workflow_ref`,
`event_name`. The `github_oidc_repository_subject` input must match the
resulting `repo:` segment, including owner/repository IDs when immutable GitHub
subjects are enabled. AWS does not expose `event_name` as a direct GitHub OIDC
condition key, so the trust document matches the two complete customized
subjects ending in `event_name:workflow_dispatch` and `event_name:schedule`.

When implemented, the workflow must use the protected environment named by
the bootstrap inputs. Until then, the trust document is a fail-closed contract,
not a claim that deployment automation or GitHub customization exists.
Ordinary pushes and verification, pull requests, forks, Dependabot, and
unapproved refs have no AWS credential or write path.

## Owner inputs and local safety

Use Terraform `1.15.8` and the locked AWS provider `6.58.0`. Copy the visibly
synthetic example to an ignored owner file and replace every value:

```console
cp infra/aws/bootstrap/terraform.tfvars.example infra/aws/bootstrap/owner.auto.tfvars
```

The owner role and GitHub OIDC provider must already exist in the target
account. `github_oidc_repository_subject` is an explicit trust input rather
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

This repository-owned evaluator is static contract proof, not AWS IAM Access
Analyzer or the live IAM Policy Simulator. A later owner-authorized AWS
simulation may add read-only sanitized evidence, but it must not mutate IAM or
create a resource. Static proof now covers both this persistent bootstrap and
the Step 4
[managed-environment definition](infra/aws/environment/README.md). It does not
claim that either root has been applied, or that the Step 5 lifecycle, Step 6
automation, or Step 7 real-AWS cycle exists.
