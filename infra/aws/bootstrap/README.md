# AWS persistent bootstrap

This Terraform root implements the persistent state, ECR, Permissions
Boundary, role, trust, pass-role, and environment-isolation contracts described
in the [portable AWS bootstrap guide](../../../AWS_BOOTSTRAP.md).

For the maintainer account, this root is a one-time provisioning/reference
implementation. The selected live contract is the Console-owned static IAM
inventory in `../environment/console-iam/`. Normal deployment must not plan or
apply this root, recalculate IAM quota, generate policy documents, change a
permissions boundary, or repair drift. It only assumes the already-fixed
operator and performs exact read-only attestation. A third-party account owner
may still use this root once to establish its own portable prerequisites.

- `versions.tf` pins Terraform and the AWS provider.
- `variables.tf` rejects ambiguous account, partition, region, name,
  repository, state-key, principal, and workflow inputs.
- `state.tf` owns the protected S3 backend bucket.
- `ecr.tf` owns independent immutable Web/API/ML repositories and cleanup.
- `iam.tf`, `iam-policies.tf`, and `locals.tf` own the fixed boundary,
  purpose roles, separately managed lifecycle-control/lifecycle-destroy
  authority, quota preconditions, and trust documents.
- `controller.tf` owns persistent artifact-free image and destroy CodeBuild
  projects, their retained control-plane log groups, and one exact lifecycle
  schedule group per environment.
- `policy-matrix.json` is the versioned positive/negative simulation contract.
- The fixed boundary keeps durable service/purpose, persistent-resource, IAM,
  and exact PassRole guardrails. Bootstrap-owned non-replaceable identity
  policies enforce generated-resource ownership, leaving quota headroom for
  later application-service follow-up without broadening effective authority.
- Operator control-plane proof uses actual create, inventory, mutation, and
  multi-resource Cloud Map contexts, restricts ownership tag keys, and rejects
  cross-environment/repository plus unowned Cognito cases; PassRole proof also
  synthesizes undeclared wildcard-matching targets.
- EC2 subnet, Security Group, route-table, and endpoint creation separately
  authorizes the existing ownership-tagged VPC; the new resource still
  requires the exact request-tag tuple.
- GitHub trust requires the documented repository-level customized OIDC
  subject before the Step 6 workflow can assume the automation role. The
  workflow accepts only `workflow_dispatch` and `schedule` from the exact
  `main` workflow/environment identity.
- `tests/bootstrap.tftest.hcl` uses a mocked AWS provider and creates no
  resource.
- `terraform.tfvars.example` is synthetic and non-authorizing.

Generated backend files, real variable files, provider data, plans, and state
are ignored. Do not add application-environment resources to this root; the
ephemeral Step 4 state is a separate Terraform ownership boundary.
