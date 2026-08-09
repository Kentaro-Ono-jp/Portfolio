# AWS managed ephemeral environment

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
backend, image, PassRole, and destroy-role-assumption authority; two additional
static managed policies split tag-on-create operations from exact-ARN and
ownership-tagged environment operations. The boundary remains a separate
maximum ceiling shared by all roles. The Console procedure contains no
explicit deny, dynamic attachment, inline policy, or Terraform-managed IAM
object.

The separate destroy identity policy enforces the full ownership tuple on
generated identifiers, exact environment-name ARN patterns where the service
supports them, and AWS-supplied forward-access context for Cloud Map's Route 53
creation dependencies and Amazon MQ's EC2 cleanup dependencies. The static
proof pairs each owned allow
with cross-environment, cross-repository, unmanaged, persistent, direct-call,
and wrong-delegating-service negatives and also enforces rendered IAM quotas.

Cloud Map ownership tags are immutable after creation. AWS provider 6.58.0
places them directly on `CreatePrivateDnsNamespace` and `CreateService`, while
the static operator identity and boundary intentionally omit standalone
`TagResource`; AWS exposes no resource-level or prior-resource-tag condition
that could prevent that API from relabeling an unrelated namespace or service.

All taggable environment resources receive exactly these provider default
tags:

- `PortfolioEnvironment=<environment>`
- `PortfolioManaged=true`
- `PortfolioPersistent=false`
- `PortfolioRepository=<owner/name>`

Step 5 will generate ignored partial S3 backend files with the bootstrap
bucket/region and this exact key. Keeping the backend declaration outside the
checked-in root allows deterministic local plan proof without reading or
writing remote state.

## Topology

- `modules/network` owns one VPC, Internet Gateway, two public task subnets,
  two isolated service subnets, public and isolated route tables, the S3
  gateway endpoint, and exact Security Group edges. It creates no NAT or
  Internet-facing inbound rule.
- `modules/ingress` owns the generated API Gateway HTTP API endpoint, VPC Link,
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
  accepted `reactorfront-reviewers` group. No user is seeded in Step 4.

Fargate tasks use public task subnets plus explicit public IP assignment only
for outbound access. Direct Internet ingress to task ENIs, RDS, and MQ is
absent. The allowed application edges are API Gateway VPC Link to Web, Web to
API, API to PostgreSQL, and API/ML to RabbitMQ over TLS. Web receives no
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

An AWS-free verification run is never deployment authority. A live plan or
apply requires a separately approved operator session, exact remote backend,
immutable image digests, and account-owned rendered role ARNs. Lifecycle,
TTL-first fallback, destroy, and residual-sweep automation remain separate
delivery increments.

## Exploratory live evaluation record

An owner-authorized manual evaluation of this static root consumed all `3/3`
governed construction attempts without reaching a successful hosted cycle. It
was used to correct provider-dependent tag, refresh, delegated-service, enum,
and destroy cleanup authority in the static contract; it is not Step 7 green
proof and does not authorize a fourth construction apply.

The partial environment was then destroyed through the separate destroy role.
Terraform state returned to zero, a fresh live plan contained 81 creates and no
updates or deletes, and a service-specific sweep found no application VPC,
subnet, Security Group, route table, Internet Gateway, VPC endpoint, network
interface, RDS, Amazon MQ, log, API Gateway, Cognito, Cloud Map, Route 53, active
ECS, Secrets Manager, or application-bucket residue. Persistent state, ECR,
Console IAM, and service-linked prerequisites remain intentionally outside this
environment state root.
