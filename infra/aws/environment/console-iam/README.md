# Console-owned environment IAM

These documents define the persistent IAM objects that an account owner creates
and maintains in the AWS Console. Terraform in `../` consumes the resulting role
ARNs by reference and never creates, updates, detaches, or deletes IAM objects.

`ReactorFrontPortfolioOperatorPermissions` and
`ReactorFrontPortfolioOperatorBoundary` are deliberately separate managed
policies. The permissions policy is the operator's current action grant. The
boundary is only the maximum authority that any of the six roles may receive.
Never attach the boundary as an identity policy, and never use the permissions
policy as a permissions boundary.

## Literal substitutions

Before pasting a JSON document into the Console, replace every `${...}` token
with one explicit value owned by the target account:

- `AWS_ACCOUNT_ID`, `AWS_PARTITION`, and `AWS_REGION`
- `NAME_PREFIX`, `ENVIRONMENT`, and `REPOSITORY_IDENTITY`
- `STATE_BUCKET_NAME` and `OWNER_PRINCIPAL_ARN`

For the maintained proof, the stable names are `reactorfront`, `manual`, and
`environments/manual/terraform.tfstate`. Do not commit a rendered account file.

## Console procedure

1. In IAM **Roles**, create the four service-linked roles listed in
   `manifest.json` if the account does not already contain them. This is a
   one-time account prerequisite; the operator role never receives
   `iam:CreateServiceLinkedRole`.
2. In IAM **Policies**, create the six customer-managed policies named by
   `manifest.json`, pasting the corresponding rendered JSON document.
3. Create the six roles named by the manifest and paste each rendered trust
   policy. Require MFA for the human operator trust.
4. Set `ReactorFrontPortfolioOperatorBoundary` as the permissions boundary of
   every role.
5. Attach only the policies listed for that role. The Web workload role has no
   identity policy. Its empty authority is intentional.
6. Add the four ownership tags from the manifest and set
   `PortfolioPurpose` to the role purpose.
7. Verify that the operator has exactly one identity policy, exactly one
   separately named boundary, and no inline policy. Verify that the old
   combined policy has zero attachments and zero boundary usages before
   deleting it.

The documents contain no explicit `Deny`. Effective authority is the
intersection of a role's identity policy and its static boundary. State-bucket
deletion, state-object deletion, arbitrary IAM mutation, and passing the
operator or destroy role are absent from that intersection.
