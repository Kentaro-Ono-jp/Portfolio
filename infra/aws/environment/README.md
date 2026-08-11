# AWS managed ephemeral environment

Start with the repository-root
[portable managed-ephemeral AWS operations guide](../../../AWS_OPERATIONS_GUIDE.md)
for the hiring-oriented overview, complete operating order, recovery, cost,
limitations, and exact evidence. This document is the component-level
Terraform topology reference.

This Terraform root implements Delivery Specification 0004 Step 4 as one
independent, NAT-free, environment-owned state boundary. It is static
infrastructure definition with AWS-free proof. It never performs IAM mutation
and does not automatically perform `apply`, migration, seed, smoke, extend, or
destroy operations.

## Ownership boundary

Every resource in this directory is owned by the one explicit
`environment_state_key`, which must equal
`environments/<environment>/terraform.tfstate`. The persistent state bucket,
ECR repositories, operator permissions, Permissions Boundary, deployment
roles, workload roles, and destroy controller remain persistent and are owned
either by `../bootstrap/` or by the static account-owner procedure in
`console-iam/`; this root consumes only their explicit ARNs and repository
URLs. It has no `terraform_remote_state` or AWS discovery data source.

`console-iam/manifest.json` keeps `OperatorPermissions` and `OperatorBoundary`
as independently named and versioned managed policies. The former holds
backend, PassRole, and destroy-role-assumption authority; the separate
CodeBuild image role alone publishes images. Two additional static managed
policies split tag-on-create operations from exact-ARN and
ownership-tagged environment operations. The boundary remains a separate
maximum ceiling shared by all roles. The Console procedure contains no
explicit deny, dynamic attachment, inline policy, or Terraform-managed IAM
object.

The Console-owned IAM objects are a frozen prerequisite, not a deployment
phase. Static maintenance is performed once by an owner-admin principal and
includes quota proof plus live Console read-back. Normal deployment verifies
the existing source identity, assumes the exact operator, and uses the
separate exact-ARN `StaticIamAttestation` policy to compare the live user,
roles, trusts, boundaries, attachments, and default managed-policy documents
with the checked-in contract. Drift fails closed. Deployment cannot generate,
attach, version, repair, or otherwise mutate IAM and does not recalculate IAM
quota or invoke the bootstrap IAM root.

The Console-owned existing `ReactorFrontNoel` source user has no Console
login and no AWS resource authority. Its three static identity policies permit
only `sts:AssumeRole` on the exact operator, billing-read, and observer roles.
The latter two preserve explicitly approved price and observation sessions;
destroy and every other role remain unavailable. The operator role trusts only
the same-account source user without MFA. All plan/apply calls use the resulting
short-lived operator STS credentials.
The maintainer-private Portfolio AWS context vault may supply only that existing
user's access-key material. Role ARNs, backend settings, ECR URLs, Terraform
variables, and construction targets remain explicit repository or AWS-output
inputs and never depend on that private context.

The separate destroy identity policy enforces the full ownership tuple on
generated identifiers, exact environment-name ARN patterns where the service
supports them, and AWS-supplied forward-access context for Cloud Map's Route 53
creation dependencies and Amazon MQ's EC2 cleanup dependencies. The static
proof pairs each owned allow
with cross-environment, cross-repository, unmanaged, persistent, direct-call,
and wrong-delegating-service negatives and also enforces rendered IAM quotas.

AWS maps both Cloud Map create operations to their create action plus
`servicediscovery:TagResource`, even though provider 6.58.0 places the tags in
the create payload. The static operator identity and its separate boundary
therefore grant that companion action at `Resource: "*"`, limited to the exact
four request tags and tag-key set. AWS exposes neither resource-level nor prior
resource-tag conditions for it, so the same exact request can relabel an
unrelated Cloud Map namespace or service. The account owner accepts that
service limitation only for this dedicated deployment account and trusted
human operator. Cloud Map inventory must be empty of unrelated resources
before and after use; any unrelated target stops the procedure for owner
review. Environment Terraform still consumes role ARNs and never mutates IAM.

All taggable environment resources receive exactly these provider default
tags:

- `PortfolioEnvironment=<environment>`
- `PortfolioManaged=true`
- `PortfolioPersistent=false`
- `PortfolioRepository=<owner/name>`

Step 5 copies this root into a private runtime directory and adds the partial S3
backend declaration there with the bootstrap bucket/region and this exact key.
Keeping the live backend declaration outside the checked-in root preserves the
deterministic local plan proof without reading or writing remote state.

## Topology

- `modules/network` owns one VPC, Internet Gateway, two public task subnets,
  two isolated service subnets, public and isolated route tables, the S3
  gateway endpoint, and exact Security Group edges. It creates no NAT or
  Internet-facing inbound rule.
- `modules/ingress` owns the two generated API Gateway HTTP API endpoints, one VPC Link,
  private Cloud Map namespace, Web/API services, throttling, and bounded access
  logs. There is no Terraform-managed ALB, custom domain, certificate, Route
  53, CloudFront, or WAF resource. Cloud Map delegates private hosted-zone
  creation to Route 53 under the caller, so the Console-owned operator contract
  models the documented service-dependent create/read actions. Namespace
  deletion requires only Cloud Map authority and grants no Route 53 delete.
- `modules/runtime` owns independent Web, API-area, and ML Fargate services.
  API-area contains FastAPI, outbox publisher, and result consumer containers;
  migration is a separate task definition and is not run here. Task sizing is
  read from `../runtime-sizing.json`, images require `repository@sha256:digest`,
  and execution/workload roles remain distinct.
- `modules/managed-state` owns encrypted Single-AZ RDS PostgreSQL 18, an
  encrypted Single Instance Amazon MQ RabbitMQ 4.2 broker, an encrypted and
  public-blocked S3 application bucket with bounded lifecycle, generated
  DB/MQ connection secrets, and immediate environment destroy settings.
- `modules/identity` owns an admin-seed-only Cognito pool, public
  Authorization Code/PKCE client, resource audience, managed login v2, and the
  accepted `reactorfront-reviewers` group. Web sends that resource audience in
  the authorize request so Cognito binds the access-token `aud` claim. No user
  is seeded in Step 4.

Fargate tasks use public task subnets plus explicit public IP assignment only
for outbound access. Direct Internet ingress to task ENIs, RDS, and MQ is
absent. The allowed application edges are API Gateway VPC Link to Web and API,
API to PostgreSQL, and API/ML to RabbitMQ over TLS. Web reaches API through the
second generated HTTPS endpoint and receives no
application-store credentials; ML receives neither PostgreSQL credentials nor
end-user identity.

## Portable static proof

`terraform.tfvars.example` is visibly synthetic and non-authorizing. The root
verifier initializes the checked-in lock without a backend, validates and
lints every local module, runs mocked-provider tests, and makes a fail-closed
plan against an unreachable endpoint. It publishes only sanitized counts and
contract digests; binary plans, state, generated passwords, credentials, and
private values are never evidence.

Run the repository-owned entrypoint:

```text
python scripts/verify.py --groups aws-static
```

The default static-IAM proof is also directly available as
`python scripts/verify_aws_static_iam.py`. Its optional `--live` mode performs
only source-identity check, exact operator assumption, and read-only IAM
attestation. All deployment configuration is explicit repository or AWS-output
input; only the existing source access-key material may come from the private
credential store.

An AWS-free verification run is never deployment authority. A live plan or
apply requires a separately approved operator session, exact remote backend,
immutable image digests, and account-owned rendered role ARNs. The sibling
`../lifecycle/` root implements the TTL-first lifecycle, independent destroy
fallback, and residual sweep while consuming this Terraform root by copy.

## Exploratory live evaluation record

An owner-authorized manual evaluation of this static root historically consumed
all `3/3` governed construction attempts without reaching a successful hosted cycle. It
was used to correct provider-dependent tag, refresh, delegated-service, enum,
and destroy cleanup authority in the static contract; it is not Step 7 green
proof. Issue #114 supersedes that former numeric ceiling with a
completion-first serialized-attempt boundary; the historical `3/3` record is
immutable evidence, not a current cap.

The partial environment was then destroyed through the separate destroy role.
Terraform state returned to zero, a fresh live plan contained 81 creates and no
updates or deletes, and a service-specific sweep found no application VPC,
subnet, Security Group, route table, Internet Gateway, VPC endpoint, network
interface, RDS, Amazon MQ, log, API Gateway, Cognito, Cloud Map, Route 53, active
ECS, Secrets Manager, or application-bucket residue. Persistent state, ECR,
Console IAM, and service-linked prerequisites remain intentionally outside this
environment state root.
