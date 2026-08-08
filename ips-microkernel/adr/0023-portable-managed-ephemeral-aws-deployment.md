# ADR-0023: Adopt a portable managed-ephemeral AWS deployment profile

- Status: Accepted
- Date: 2026-08-09
- Related decisions:
  - [ADR-0001: Adopt a modular monorepo](0001-modular-monorepo.md)
  - [ADR-0003: Adopt the initial technology stack](0003-initial-technology-stack.md)
  - [ADR-0004: Keep state ownership in the API and use a transactional outbox](0004-api-state-ownership-and-transactional-outbox.md)
  - [ADR-0007: Define the authentication, session, and API authorization boundary](0007-authentication-session-and-api-authorization.md)
  - [ADR-0021: Govern human feedback, model evaluation, and promotion](0021-govern-human-feedback-model-evaluation-and-promotion.md)
- Governing delivery:
  [Delivery Specification 0004](../delivery/0004-portable-managed-ephemeral-aws-deployment.md)

## Context

The repository already provides two independent evaluation paths. GitHub
Actions reconstructs and verifies the complete system on a clean runner, and a
clone can run the nine-service Docker Compose environment without an AWS
account. Neither path proves that the same three deployable application areas
can be operated through managed cloud services.

The fourth vertical slice needs a public, reproducible AWS deployment path
without converting this MIT repository into an account-specific hosted
product. A third party must deploy a clone only into the third party's AWS
account and own the resulting credentials, state, resources, and cost. The
maintainer proof is deliberately short-lived rather than an availability or
SaaS claim.

The current application boundaries must survive that deployment. The Web is
the browser-facing session boundary, the API owns PostgreSQL application state
and the transactional outbox, and the ML worker receives neither PostgreSQL
credentials nor end-user identity. Local MinIO, RabbitMQ, and Dex remain
deterministic local and CI fixtures even when managed AWS adapters are added.

## Decision

### Preserve three independent experiences

Keep all of these repository experiences:

1. normal pull requests and `main` merges run AWS-free GitHub Actions;
2. a clone runs the deterministic AWS-free Docker Compose environment; and
3. an authorized operator explicitly deploys that clone into an independently
   owned AWS account.

Merge alone never creates AWS resources. Normal pull requests, fork pull
requests, Dependabot, and ordinary `main` verification receive no AWS
credential or AWS write authority. AWS deployment is a separately authorized
manual lifecycle or the accepted bounded monthly schedule.

### Use one managed ephemeral profile

Adopt Terraform and the following initial AWS mapping:

- API Gateway HTTP API provides its generated HTTPS endpoint;
- a VPC Link and AWS Cloud Map route private ingress to one Web ECS/Fargate
  service;
- Web reaches a private API-area ECS/Fargate service through Cloud Map;
- the API area keeps migration, FastAPI, outbox, and result-consumer processes
  as distinct containers in one task definition;
- the ML worker remains an independent ECS/Fargate service;
- RDS for PostgreSQL stores API-owned application state;
- S3 replaces MinIO for environment-owned document objects;
- Amazon MQ for RabbitMQ 4.2 preserves the accepted Celery and asynchronous
  request/result contracts; and
- Amazon Cognito provides the managed OIDC deployment adapter.

Web, API, and ML remain independently deployable areas. The API stays the sole
PostgreSQL owner, and the ML service continues to receive only the bounded
document and processing identities required by the accepted event contracts.

### Keep the initial proof NAT-free and inbound-closed

Place Fargate tasks in public task subnets with public addresses only for
outbound access. Security Groups allow no direct Internet inbound traffic.
VPC Link reaches only the Web port, Web reaches only the API port, API reaches
only PostgreSQL, and API/ML reach only RabbitMQ and required HTTPS services.
RDS and Amazon MQ stay in isolated service subnets. An S3 gateway endpoint
serves the task subnets.

Do not require a NAT Gateway, ALB, CloudFront, Route 53, ACM, WAF, or custom
domain for the initial short-lived proof. This is a cost-bounded evaluation
profile, not the default architecture for a future always-on service.

### Adapt identity, storage, and secrets without static workload keys

Keep Cognito behind the accepted OIDC boundary. The Web uses Authorization
Code with PKCE and an explicitly trusted authorization endpoint. The API
validates exact issuer, resource-bound audience, access-token purpose, time and
signature, and reviewer-group capability. An ID token is never accepted as an
API access token.

AWS-mode S3 adapters use the standard credential chain and task roles. Local
MinIO retains its deterministic endpoint and fixture credentials. Application
tasks receive no long-term AWS access key. Database and broker secrets are
injected through the task execution boundary from an AWS-managed secret store;
secret values and Terraform state are never public evidence.

### Separate persistent bootstrap from ephemeral application state

Keep only low-cost control resources in a persistent bootstrap layer: the
encrypted and versioned S3 state backend and lockfile, ECR repositories with
lifecycle cleanup, bounded IAM and workload roles, and the independent
destroy controller.

Put network, ingress, discovery, ECS, RDS, S3 application data, Amazon MQ,
Cognito, runtime secrets, and environment logs in an environment-specific
ephemeral layer. Manual and monthly environments use distinct names, state
keys, and tags. Public modules and instructions must not require the
maintainer's account, identity, credentials, state, or machine-local files.

### Register destroy authority before billable apply

Before creating billable application resources, register a one-time two-hour
fallback outside the state it destroys. EventBridge Scheduler invokes a
persistent CodeBuild destroy project bound to the exact source, backend, state
key, and environment, then deletes the completed schedule.

The normal lifecycle is preflight, immutable image publication, fallback
registration, Terraform apply, migration, synthetic seed, health and
authenticated smoke, external HTTPS check, manual destroy, and tag plus
service-specific residual inventory. The fallback remains available if the
operator path is interrupted. A successful `terraform destroy` exit code,
Budget alert, or schedule invocation alone is not proof that spending stopped.

### Bound authority, cost, and evidence

Deployment, IAM-management, automation, workload, execution, and destroy roles
have separate purposes. Permissions Boundaries and exact `iam:PassRole`
conditions constrain role creation and assignment. Scheduled automation uses
short-lived GitHub OIDC or another separately accepted short-lived trust, not
a maintainer long-term key.

The maintainer construction proof permits at most three attempts that begin
billable application-resource creation. A partial failed apply counts. Static
work, tests, validation, read-only inventory, and plan-only work do not. Cost
estimates are assumptions rather than guarantees; TTL, destroy, residual
inventory, and the deploying account's cost boundary remain authoritative.

Each focused increment records exact review endpoints, successful
authoritative workflow evidence or a complete governed qualified limitation,
independent review, merge, merged-main evidence or the corresponding
limitation, and reconciliation. Workflow absence is never passing evidence.
AWS lifecycle proof uses repository-owned synthetic documents and sanitized
identities only.

### Record acceptance separately from implementation

This ADR accepts the target profile and its boundaries. It does not claim that
Terraform, IAM roles, managed-service adapters, deployment automation, or an
AWS environment already exists. Those capabilities proceed through the
focused increments and completion gates in Delivery Specification 0004.

## Consequences

### Positive

- The public repository remains cloneable and useful without AWS.
- A third party can reproduce the complete lifecycle without sharing the
  maintainer's AWS account or private state.
- Managed deployment preserves the accepted Web, API, ML, OIDC, outbox, and
  model-lineage boundaries.
- Short-lived infrastructure, schedule-first fallback, and residual inventory
  make destroyability part of the proof rather than an operational afterthought.
- The profile demonstrates managed AWS delivery without the fixed hourly cost
  of an initial ALB, NAT Gateway, or always-on application environment.

### Costs

- Cognito, task-role S3, RabbitMQ 4.2, and Fargate sizing require compatibility
  work before a real deployment.
- Public task subnets trade private-subnet isolation for a bounded low-cost
  profile and require strict inbound Security Groups.
- Persistent bootstrap and ephemeral application state require separate
  Terraform ownership and recovery procedures.
- Complete proof includes IAM simulation, cost preflight, fallback recovery,
  external smoke, destroy, and service-specific residue checks.

## Rejected alternatives

- Replace local Compose or ordinary GitHub Actions with an AWS-only path.
- Require third parties to use the maintainer's AWS account, IAM identities,
  state, credentials, or private files.
- Keep the managed application running continuously to prove deployment.
- Put every Compose process in one undifferentiated ECS task or grant the ML
  worker PostgreSQL or end-user credentials.
- Inject long-term AWS access keys into tasks or GitHub workflows.
- Use an ALB, NAT Gateway, custom domain, CloudFront, WAF, EKS, Kubernetes,
  Helm, or service mesh before a separately measured need exists.
- Treat apply, destroy exit status, a Budget alert, or an absent workflow as
  sufficient proof.

## Revisit when

- an always-on service needs high availability, stable branded ingress,
  private task subnets, VPC endpoints, NAT, WAF, or multi-region recovery;
- measured application load requires independent scaling of API-area process
  roles or durable shared Web sessions;
- a managed broker or identity provider no longer preserves the accepted
  application contract; or
- repeated real deployments show that another topology materially improves
  cost, safety, operability, or portability.
