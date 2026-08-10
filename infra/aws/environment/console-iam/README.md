# Console-owned environment IAM

These documents define the persistent IAM objects that an account owner creates
and maintains in the AWS Console. They include one credential-only Noel IAM
user, its exact assume-role policies, and the deployment and read-only roles.
Terraform in `../` consumes the resulting role ARNs by reference and never
creates, updates, detaches, or deletes IAM objects. `manifest.json`, the JSON
documents, and `static-contract-digests.json` are the canonical persistent
contract. Drift stops deployment; the deployment path never repairs it.

`ReactorFrontPortfolioOperatorPermissions` and
`ReactorFrontPortfolioOperatorBoundary` are deliberately separate managed
policies. `OperatorPermissions` holds backend, image, exact PassRole, and
destroy-role-assumption authority. The operator's environment authority is
split into two more static managed policies: one for exact ownership tags at
creation and one for reads plus exact-ARN or ownership-tagged operations. This
keeps every document below the managed-policy quota without widening an
action to unrelated account resources. The boundary is only the maximum
authority that any of the six roles may receive. Never attach the boundary as
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

The static verifier is AWS-free by default:

```text
python scripts/verify_aws_static_iam.py
```

`--live` is an explicit read-only mode. It takes account, partition, region,
prefix, environment, repository identity, and state-bucket name as command
arguments; these deployment inputs never come from `awsinfo`. It uses the
standard AWS credential chain only to identify the existing source user,
assumes the exact operator, keeps the STS credential in process memory, and
prints only sanitized counts and hashes.

## One-time Console installation or maintenance

1. In IAM **Roles**, create the four service-linked roles listed in
   `manifest.json` if the account does not already contain them. This is a
   one-time account prerequisite; the operator role never receives
   `iam:CreateServiceLinkedRole`.
2. In IAM **Policies**, create the twelve customer-managed policies named by
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
   A local `awsinfo` store, when used, supplies only that existing user's access
   key material. Role ARNs, backend settings, ECR URLs, Terraform variables,
   and deployment targets come from the checked-in contract and AWS outputs,
   never from `awsinfo`.
4. Create the six roles named by the manifest and paste each rendered trust
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
8. Verify that the operator has exactly the four identity policies listed by
   the manifest, exactly one separately named boundary, and no inline policy.
   `StaticIamAttestation` is read-only and is restricted to the one source
   user, six persistent roles, and twelve managed policies by exact ARN.
   Verify that the destroy role has only `OperatorPermissions` and
   `DestroyPolicy`. Verify that the old
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
so that one action is isolated as the only unconditioned global destroy write;
it is absent from `OperatorPermissions` and the destroy role remains unable to
mutate IAM or its own policies.
