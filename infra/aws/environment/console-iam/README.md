# Console-owned environment IAM

These documents define the persistent IAM objects that an account owner creates
and maintains in the AWS Console. They include one credential-only Noel IAM
user, its exact assume-role policies, and the deployment and read-only roles.
Terraform in `../` consumes the resulting role ARNs by reference and never
creates, updates, detaches, or deletes IAM objects. `manifest.json`, the JSON
documents, and `static-contract-digests.json` are the canonical persistent IAM
contract. IAM drift stops deployment; the deployment path never repairs it.

`ReactorFrontPortfolioOperatorPermissions` and
`ReactorFrontPortfolioOperatorBoundary` are deliberately separate managed
policies. `OperatorPermissions` holds backend, exact PassRole, and
destroy-role-assumption authority. Image publication belongs only to the
separate CodeBuild image role. The operator's environment authority is
split into two more static managed policies: one for exact ownership tags at
creation and one for reads plus exact-ARN or ownership-tagged operations. This
keeps every document below the managed-policy quota without widening an
action to unrelated account resources. The boundary is only the maximum
authority that any of the nine roles may receive. Never attach the boundary as
an identity policy, and never use any permissions policy as a permissions
boundary.

## Literal substitutions

Before pasting a JSON document into the Console, replace every `${...}` token
with one explicit value owned by the target account:

- `AWS_ACCOUNT_ID`, `AWS_PARTITION`, and `AWS_REGION`
- `NAME_PREFIX`, `ENVIRONMENT`, and `REPOSITORY_IDENTITY`
- `STATE_BUCKET_NAME`

For the maintained proof, the stable names are `reactorfront`, `manual`, and
`environments/manual/terraform.tfstate`. Do not commit a rendered account file.

## Frozen lifecycle

Static IAM installation or maintenance is a separate, governed
operation. An `owner-admin principal` renders the checked-in documents, proves
their quotas once, changes only the named IAM objects in the AWS Console, and
then performs live read-back. The exact administrator user name is private and
must not appear in repository files, Issues, PRs, logs, or evidence.

Normal deployment does none of that work. It verifies the existing source
credential, assumes the exact operator role, reads the fixed IAM objects using
`StaticIamAttestation`, compares them with the checked-in canonical digests,
and fails closed on any mismatch. It never recalculates quota, generates or
splits a policy, creates a policy version, changes a boundary, changes an
attachment, invokes the bootstrap IAM root, or attempts self-healing.

The lifecycle policy separately permits `codebuild:UpdateProject` on only the
exact persistent image-build project. This is not IAM self-healing: when all
other project fields already match, preflight may synchronize only its inline
repository-owned buildspec and must read back its exact normalized SHA-256.
The destroy project and every foreign project remain denied, and the operator
has no CodeBuild `iam:PassRole` grant, so it cannot replace the project service
role. This one-time static permission remains installed between deployments;
normal deployment never changes the permission itself.

The static verifier is AWS-free by default:

```text
python scripts/verify_aws_static_iam.py
```

`--live` is an explicit read-only mode. It takes account, partition, region,
prefix, environment, repository identity, and state-bucket name as command
arguments; these deployment inputs never come from private credential context. It uses the
standard AWS credential chain only to identify the existing source user,
assumes the exact operator, keeps the STS credential in process memory, and
prints only sanitized counts and hashes.

## One-time Console installation or maintenance

1. In IAM **Roles**, create the four service-linked roles listed in
   `manifest.json` if the account does not already contain them. This is a
   one-time account prerequisite; the operator role never receives
   `iam:CreateServiceLinkedRole`.
2. In IAM **Policies**, create the seventeen customer-managed policies named by
   `manifest.json`, pasting the corresponding rendered JSON document.
3. Select the existing `ReactorFrontNoel` credential-only IAM user; do not
   create a second deployment user. It must have no Console access, group,
   inline policy, permissions boundary, or AWS resource permission. Attach only
   the three Noel policies from the manifest. Each contains one
   `sts:AssumeRole` statement for exactly one approved role: operator,
   billing-read, or observer. The latter two are explicitly retained for price
   and observation sessions and do not provide a deployment path. Reuse the
   user's one existing access key from the owner's private credential store;
   never commit or publish it.
   The maintainer-private Portfolio AWS context vault, when used, supplies only
   that existing user's access-key material. Role ARNs, backend settings, ECR
   URLs, Terraform variables, and deployment targets come from the checked-in
   contract and AWS outputs, never from that private context.
4. Create the nine roles named by the manifest and paste each rendered trust
   policy. The operator trust accepts only the exact Noel Deployment user in
   the same account; it does not require MFA. Source access keys and login
   material remain external to Terraform and the public repository.
5. Set `ReactorFrontPortfolioOperatorBoundary` as the permissions boundary of
   every role.
6. Attach only the policies listed for that role. The Web workload role has no
   identity policy. Its empty authority is intentional.
7. Add exactly the five tags in that role's manifest `tags` object. Extra
   tags, a missing tag, or any wrong value (including `PortfolioPurpose`) are
   contract drift and stop deployment attestation.
8. Verify that the operator has exactly the five identity policies listed by
   the manifest, exactly one separately named boundary, and no inline policy.
   `StaticIamAttestation` is read-only and is restricted to the one source
   user, nine persistent roles, and seventeen managed policies by exact ARN.
   Verify that the destroy role has only `OperatorPermissions`,
   `DestroyPolicy`, and `LifecycleDestroyPolicy`. Verify that Scheduler,
   CodeBuild image, and CodeBuild destroy each have only their one exact
   lifecycle policy. The CodeBuild destroy policy must read both exact
   controller inputs (`configuration.json` and `lease.json`), must not mutate
   lifecycle or Terraform state itself, and must assume only the exact destroy
   role before any mutation. Verify that the old
   combined policy has zero attachments and zero boundary usages before
   deleting it.
9. Verify the Noel user has no Console login, group, inline policy, boundary,
   or permission other than the three exact role assumptions. The destroy role
   and every unlisted role must remain unavailable.
10. Only during a separately approved static-IAM maintenance operation, when a
   checked-in policy document changes, create a new customer-managed
   policy version in the Console and make it the default. Do not dynamically
   attach an allow, attach a deny, or let Terraform mutate either policy.

The documents contain no explicit `Deny`. Effective authority is the union of
the role's listed identity policies intersected with its static boundary.
The Noel user is deliberately outside that union: it can obtain only one of the
three approved short-lived role sessions and cannot call AWS resource APIs
directly. All deployment activity uses the operator session.
State-bucket
deletion, state-object deletion, arbitrary IAM mutation, and passing the
operator or destroy role are absent from that intersection.

The AWS-free verifier renders every document before use and compares its
canonical SHA-256 digest with `static-contract-digests.json`. Each customer-managed
policy must remain within AWS IAM's 6,144-character limit with at least 512
characters reserved; each role trust policy must remain within the default
2,048-character limit with at least 256 characters reserved. Whitespace is not
counted, matching IAM's quota semantics. These quota checks govern static-IAM
design and maintenance; they are not repeated by the normal deployment
preflight.

The two managed-environment identity policies bind every write to exact
creation tags, the complete existing ownership tuple, or deterministic
environment ARN patterns. Their inverse proof rejects cross-environment,
cross-repository, unmanaged, persistent, missing/additional-tag, and foreign
resource cases at both the identity and effective layers.

API Gateway V2 authorizes tags included by `CreateApi`, `CreateStage`, and
`CreateVpcLink` through `apigateway:POST` + `PUT` on `/tags/*`, `PATCH` on the
new target, and—for stage and VPC-link creation—the literal
`apigateway:TagResource` action on the same `/apis/*/stages` and `/vpclinks`
collection resource used by the create. The Service Authorization table maps
standalone tagging to HTTP verbs, but repeated live creates still requested
this literal dependent action after all three mapped verbs were present. The
IAM Console validator currently labels it unknown even though IAM stores it and
the live service consumes it. Live
AWS execution proved that the dependent call exposes neither request nor
resource ownership tags. The operator therefore receives only these exact
action/resource pairs without a tag condition, while target `POST` + `PUT` and
later operations retain the full ownership tuple. As with the Cloud Map
exception below, this could create, relabel, or patch an unrelated API Gateway
resource in the dedicated account; it is an
owner-accepted static limitation for the dedicated deployment account, not a
foreign-target isolation claim. The lifecycle's before/after service inventory
and zero-residue proof remain mandatory.

Enabling HTTP API access logging also invokes CloudWatch Logs' account-level
delivery control plane. AWS documents seven delivery actions whose Service
Authorization entries expose no resource type or scoping condition, so only
`CreateLogDelivery`, `DeleteLogDelivery`, `DescribeResourcePolicies`,
`GetLogDelivery`, `ListLogDeliveries`, `PutResourcePolicy`, and
`UpdateLogDelivery` use `Resource: "*"`. Log-group creation, tagging,
retention, and later data access remain bound to the exact environment log
groups. This is an owner-accepted service dependency, not a general Logs write
grant.
The destroy role receives only the corresponding `ListLogDeliveries`,
`GetLogDelivery`, and `DeleteLogDelivery` account-level subset used to remove
the Stage delivery, not the create/update/resource-policy actions.

ECS `DescribeTaskDefinition` exposes no resource type in AWS's Service
Authorization table. The operator therefore reads it through the global
metadata statement, while registration, tagging, and service mutation remain
bound to the exact environment task-definition and service ARNs.

The tagged one-off migration uses `RunTask` on only the exact migration task
definition and exact cluster. Because the new task has no existing resource
tags at create time, its dependent `ecs:TagResource` authorization is kept in
`LifecycleControlPolicy` and binds the exact environment task ARN pattern to
the complete four-key request-tag tuple.

Terraform updates deregister superseded task-definition revisions. AWS exposes
no resource type or scoping condition for `DeregisterTaskDefinition`, so that
single action uses `Resource: "*"` in `LifecycleControlPolicy`. Registration,
service updates, migration runs, tagging, and PassRole remain exact; the global
deregister operation is an owner-accepted dependency of the dedicated account.

Cloud Map remains SRV-only for both ECS services. Separate generated HTTPS
HTTP APIs route to the Web and API services through the shared VPC Link, so
API Gateway performs `DiscoverInstances` for both targets while the Web server
uses the API-specific generated endpoint for authenticated upstream calls.

`rds:DescribeDBInstances` is a read-only list operation whose provider request
uses the wildcard DB resource rather than the eventual exact DB ARN, so it is
isolated in the global metadata-read statement. It grants no RDS mutation or
secret value. EC2 VPC endpoint creation is authorized independently for the new
request-tagged endpoint and for both existing dependencies: the owned VPC and
owned route table.

AWS's operation-to-IAM mapping requires `servicediscovery:TagResource` alongside
both Cloud Map create actions, although provider 6.58.0 sends the tags in each
create payload. `ManagedEnvironmentPermissions` and the separately managed
`OperatorBoundary` therefore grant that companion action at `Resource: "*"`
with exactly the four request tags and no additional tag key. AWS exposes no
resource-level or prior-resource-tag condition for this API: an exact request
can also relabel an unrelated namespace or service. This is an owner-accepted
static exception, not an ownership-isolation claim. It is usable only by the
trusted account-owner operator in the dedicated deployment account. Inventory
Cloud Map immediately before and after use, proceed only when no unrelated
namespace or service exists, and stop for owner review otherwise. Do not add a
dynamic allow, dynamic deny, inline policy, or Terraform IAM mutation.

`DestroyPolicy` binds generated network, API Gateway, Cognito, and Cloud Map
identifiers to the complete four-tag ownership tuple. Exact-name services use
environment-encoded ARN patterns, and Cloud Map's Route 53 creation dependencies
plus Amazon MQ's EC2 cleanup dependencies are allowed only when AWS supplies the
matching `aws:CalledVia` forward-access context. Direct calls do not satisfy
those grants. Route 53 deletion is not granted because AWS documents
`DeleteNamespace` as needing only Cloud Map authority. AWS documents
`ecs:DeregisterTaskDefinition` as not supporting resource-level permissions,
so it and the account-level `logs:DeleteLogDelivery` cleanup dependency are the
only unconditioned global destroy writes. The operator receives deregistration
only through the separately named `LifecycleControlPolicy`; the destroy role
remains unable to mutate IAM or its own policies.
