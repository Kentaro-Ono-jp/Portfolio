# AWS persistent bootstrap

This Terraform root implements the persistent state, ECR, Permissions
Boundary, role, trust, pass-role, and environment-isolation contracts described
in the [portable AWS bootstrap guide](../../../AWS_BOOTSTRAP.md).

- `versions.tf` pins Terraform and the AWS provider.
- `variables.tf` rejects ambiguous account, partition, region, name,
  repository, state-key, principal, and workflow inputs.
- `state.tf` owns the protected S3 backend bucket.
- `ecr.tf` owns independent immutable Web/API/ML repositories and cleanup.
- `iam.tf`, `iam-policies.tf`, and `locals.tf` own the fixed boundary,
  purpose roles, policies, quota preconditions, and trust documents.
- `policy-matrix.json` is the versioned positive/negative simulation contract.
- The fixed boundary keeps durable service/purpose, persistent-resource, IAM,
  and exact PassRole guardrails. Bootstrap-owned non-replaceable identity
  policies enforce generated-resource ownership, leaving quota headroom for
  later application-service follow-up without broadening effective authority.
- Operator control-plane proof uses actual create, inventory, mutation, and
  multi-resource Cloud Map contexts, restricts ownership tag keys, and rejects
  cross-environment/repository plus unowned Cognito cases; PassRole proof also
  synthesizes undeclared wildcard-matching targets.
- GitHub trust requires the documented repository-level customized OIDC
  subject before the future Step 6 workflow can assume the automation role.
- `tests/bootstrap.tftest.hcl` uses a mocked AWS provider and creates no
  resource.
- `terraform.tfvars.example` is synthetic and non-authorizing.

Generated backend files, real variable files, provider data, plans, and state
are ignored. Do not add application-environment resources to this root; the
ephemeral Step 4 state is a separate Terraform ownership boundary.
