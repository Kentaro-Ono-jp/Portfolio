locals {
  boundary_environment_token = "$${aws:PrincipalTag/PortfolioEnvironment}"
  boundary_environment_role_arns = [
    for role in values(local.environment_roles) :
    "${local.iam_prefix}:role${local.role_path}${role.name}"
  ]
  boundary_environment_resources = [
    "arn:${var.aws_partition}:apigateway:${var.aws_region}::/apis/*",
    "arn:${var.aws_partition}:codebuild:${var.aws_region}:${var.aws_account_id}:project/${var.name_prefix}-${local.boundary_environment_token}-destroy",
    "arn:${var.aws_partition}:cognito-idp:${var.aws_region}:${var.aws_account_id}:userpool/*",
    "arn:${var.aws_partition}:ecs:${var.aws_region}:${var.aws_account_id}:cluster/${var.name_prefix}-${local.boundary_environment_token}",
    "arn:${var.aws_partition}:ecs:${var.aws_region}:${var.aws_account_id}:service/${var.name_prefix}-${local.boundary_environment_token}/*",
    "arn:${var.aws_partition}:ecs:${var.aws_region}:${var.aws_account_id}:task-definition/${var.name_prefix}-${local.boundary_environment_token}-*:*",
    "arn:${var.aws_partition}:logs:${var.aws_region}:${var.aws_account_id}:log-group:/portfolio/${var.name_prefix}/${local.boundary_environment_token}/*",
    "arn:${var.aws_partition}:logs:${var.aws_region}:${var.aws_account_id}:log-group:/portfolio/${var.name_prefix}/${local.boundary_environment_token}/*:*",
    "arn:${var.aws_partition}:mq:${var.aws_region}:${var.aws_account_id}:broker:${var.name_prefix}-${local.boundary_environment_token}-*:*",
    "arn:${var.aws_partition}:rds:${var.aws_region}:${var.aws_account_id}:db:${var.name_prefix}-${local.boundary_environment_token}-*",
    "arn:${var.aws_partition}:scheduler:${var.aws_region}:${var.aws_account_id}:schedule/*/${var.name_prefix}-${local.boundary_environment_token}-destroy-*",
    "arn:${var.aws_partition}:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.name_prefix}-${local.boundary_environment_token}-*",
    "arn:${var.aws_partition}:servicediscovery:${var.aws_region}:${var.aws_account_id}:namespace/*",
    "arn:${var.aws_partition}:servicediscovery:${var.aws_region}:${var.aws_account_id}:service/*",
  ]

  permissions_boundary_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "AllowCallerIdentity"
        Effect   = "Allow"
        Action   = "sts:GetCallerIdentity"
        Resource = "*"
      },
      {
        Sid    = "AllowEnvironmentStateObjects"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
        ]
        Resource = [
          "${local.state_bucket_arn}/environments/${local.boundary_environment_token}/terraform.tfstate",
          "${local.state_bucket_arn}/environments/${local.boundary_environment_token}/terraform.tfstate.tflock",
        ]
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = ["operator-deployment", "codebuild-destroy"]
          }
        }
      },
      {
        Sid      = "AllowEnvironmentStateListing"
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = local.state_bucket_arn
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = ["operator-deployment", "codebuild-destroy"]
          }
          StringLike = {
            "s3:prefix" = [
              "environments/${local.boundary_environment_token}/terraform.tfstate",
              "environments/${local.boundary_environment_token}/terraform.tfstate.tflock",
            ]
          }
        }
      },
      {
        Sid    = "AllowEnvironmentApplicationObjects"
        Effect = "Allow"
        Action = [
          "s3:ListBucket",
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:DeleteBucket",
        ]
        Resource = [
          "arn:${var.aws_partition}:s3:::${var.name_prefix}-${local.boundary_environment_token}-documents",
          "arn:${var.aws_partition}:s3:::${var.name_prefix}-${local.boundary_environment_token}-documents/*",
        ]
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = ["api-workload", "ml-workload", "destroy"]
          }
        }
      },
      {
        Sid      = "AllowEcrAuthorization"
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = ["operator-deployment", "task-execution"]
          }
        }
      },
      {
        Sid    = "AllowOwnedEcrImages"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:BatchGetImage",
          "ecr:CompleteLayerUpload",
          "ecr:DescribeImages",
          "ecr:GetDownloadUrlForLayer",
          "ecr:InitiateLayerUpload",
          "ecr:ListImages",
          "ecr:PutImage",
          "ecr:UploadLayerPart",
        ]
        Resource = values(local.ecr_repository_arns)
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = ["operator-deployment", "task-execution"]
          }
        }
      },
      {
        Sid    = "AllowEnvironmentLogsAndSecrets"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:DeleteLogGroup",
          "logs:DescribeLogStreams",
          "logs:PutLogEvents",
          "secretsmanager:CreateSecret",
          "secretsmanager:DeleteSecret",
          "secretsmanager:DescribeSecret",
          "secretsmanager:GetSecretValue",
          "secretsmanager:PutSecretValue",
          "secretsmanager:TagResource",
          "secretsmanager:UpdateSecret",
        ]
        Resource = [
          "arn:${var.aws_partition}:logs:${var.aws_region}:${var.aws_account_id}:log-group:/portfolio/${var.name_prefix}/${local.boundary_environment_token}/*",
          "arn:${var.aws_partition}:logs:${var.aws_region}:${var.aws_account_id}:log-group:/portfolio/${var.name_prefix}/${local.boundary_environment_token}/*:*",
          "arn:${var.aws_partition}:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.name_prefix}-${local.boundary_environment_token}-*",
        ]
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = ["operator-deployment", "task-execution", "codebuild-destroy", "destroy"]
          }
        }
      },
      {
        Sid    = "AllowEnvironmentServiceLifecycle"
        Effect = "Allow"
        Action = [
          "apigateway:DELETE",
          "apigateway:GET",
          "apigateway:PATCH",
          "apigateway:POST",
          "apigateway:PUT",
          "codebuild:StartBuild",
          "cognito-idp:CreateUserPool",
          "cognito-idp:DeleteUserPool",
          "cognito-idp:DescribeUserPool",
          "ecs:CreateCluster",
          "ecs:CreateService",
          "ecs:DeleteCluster",
          "ecs:DeleteService",
          "ecs:DeregisterTaskDefinition",
          "ecs:DescribeClusters",
          "ecs:DescribeServices",
          "ecs:DescribeTaskDefinition",
          "ecs:RegisterTaskDefinition",
          "ecs:TagResource",
          "ecs:UpdateService",
          "mq:CreateBroker",
          "mq:DeleteBroker",
          "mq:DescribeBroker",
          "rds:CreateDBInstance",
          "rds:DeleteDBInstance",
          "rds:DescribeDBInstances",
          "rds:ModifyDBInstance",
          "scheduler:CreateSchedule",
          "scheduler:DeleteSchedule",
          "scheduler:GetSchedule",
          "scheduler:UpdateSchedule",
          "servicediscovery:CreateHttpNamespace",
          "servicediscovery:CreateService",
          "servicediscovery:DeleteNamespace",
          "servicediscovery:DeleteService",
          "servicediscovery:GetNamespace",
          "servicediscovery:GetService",
        ]
        Resource = local.boundary_environment_resources
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = ["operator-deployment", "scheduler", "destroy"]
          }
        }
      },
      {
        Sid    = "AllowTaggedEnvironmentEc2Creation"
        Effect = "Allow"
        Action = [
          "ec2:AllocateAddress",
          "ec2:CreateInternetGateway",
          "ec2:CreateRoute",
          "ec2:CreateRouteTable",
          "ec2:CreateSecurityGroup",
          "ec2:CreateSubnet",
          "ec2:CreateTags",
          "ec2:CreateVpc",
          "ec2:CreateVpcEndpoint",
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose"   = "operator-deployment"
            "aws:RequestTag/PortfolioManaged"     = "true"
            "aws:RequestTag/PortfolioPersistent"  = "false"
            "aws:RequestTag/PortfolioEnvironment" = local.boundary_environment_token
          }
        }
      },
      {
        Sid      = "AllowEc2Inventory"
        Effect   = "Allow"
        Action   = "ec2:Describe*"
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = ["operator-deployment", "destroy"]
          }
        }
      },
      {
        Sid    = "AllowTaggedEnvironmentEc2Mutation"
        Effect = "Allow"
        Action = [
          "ec2:AssociateRouteTable",
          "ec2:AttachInternetGateway",
          "ec2:AuthorizeSecurityGroupEgress",
          "ec2:AuthorizeSecurityGroupIngress",
          "ec2:DeleteInternetGateway",
          "ec2:DeleteRoute",
          "ec2:DeleteRouteTable",
          "ec2:DeleteSecurityGroup",
          "ec2:DeleteSubnet",
          "ec2:DeleteVpc",
          "ec2:DeleteVpcEndpoints",
          "ec2:DetachInternetGateway",
          "ec2:DisassociateRouteTable",
          "ec2:ModifySubnetAttribute",
          "ec2:ModifyVpcAttribute",
          "ec2:ReleaseAddress",
          "ec2:RevokeSecurityGroupEgress",
          "ec2:RevokeSecurityGroupIngress",
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose"    = ["operator-deployment", "destroy"]
            "aws:ResourceTag/PortfolioManaged"     = "true"
            "aws:ResourceTag/PortfolioPersistent"  = "false"
            "aws:ResourceTag/PortfolioEnvironment" = local.boundary_environment_token
          }
        }
      },
      {
        Sid      = "AllowExactPassRoleTargets"
        Effect   = "Allow"
        Action   = "iam:PassRole"
        Resource = local.boundary_environment_role_arns
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = "operator-deployment"
          }
        }
      },
      {
        Sid    = "AllowExactRoleAssumption"
        Effect = "Allow"
        Action = "sts:AssumeRole"
        Resource = concat(
          local.boundary_environment_role_arns,
          values(local.global_role_arns),
        )
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = ["automation", "codebuild-destroy"]
          }
        }
      },
      {
        Sid    = "AllowBoundedRoleCreation"
        Effect = "Allow"
        Action = [
          "iam:CreateRole",
          "iam:PutRolePermissionsBoundary",
        ]
        Resource = local.boundary_environment_role_arns
        Condition = {
          ArnEquals = { "iam:PermissionsBoundary" = local.boundary_policy_arn }
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose"  = "iam-manager"
            "aws:RequestTag/PortfolioManaged"    = "true"
            "aws:RequestTag/PortfolioPersistent" = "true"
            "aws:RequestTag/PortfolioPurpose" = [
              "operator-deployment",
              "task-execution",
              "web-workload",
              "api-workload",
              "ml-workload",
              "scheduler",
              "codebuild-destroy",
              "destroy",
            ]
            "aws:RequestTag/PortfolioRepository" = var.repository_identity
          }
        }
      },
      {
        Sid    = "AllowBoundedRolePolicyMaintenance"
        Effect = "Allow"
        Action = [
          "iam:DeleteRole",
          "iam:DeleteRolePolicy",
          "iam:GetRole",
          "iam:GetRolePolicy",
          "iam:ListRolePolicies",
          "iam:PutRolePolicy",
        ]
        Resource = local.boundary_environment_role_arns
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = "iam-manager"
          }
        }
      },
      {
        Sid      = "AllowRoleInventory"
        Effect   = "Allow"
        Action   = "iam:ListRoles"
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = "iam-manager"
          }
        }
      },
      {
        Sid    = "DenyIdentityAndAccountAdministration"
        Effect = "Deny"
        Action = [
          "account:*",
          "aws-portal:*",
          "billing:*",
          "iam:*AccessKey*",
          "iam:*Group*",
          "iam:*LoginProfile*",
          "iam:*User*",
          "organizations:*",
        ]
        Resource = "*"
      },
      {
        Sid    = "DenyBoundaryAndRoleTagWeakening"
        Effect = "Deny"
        Action = [
          "iam:DeleteRolePermissionsBoundary",
          "iam:TagRole",
          "iam:UntagRole",
        ]
        Resource = local.boundary_environment_role_arns
      },
      {
        Sid    = "DenyBoundaryPolicyMutation"
        Effect = "Deny"
        Action = [
          "iam:CreatePolicyVersion",
          "iam:DeletePolicy",
          "iam:DeletePolicyVersion",
          "iam:SetDefaultPolicyVersion",
        ]
        Resource = local.boundary_policy_arn
      },
      {
        Sid      = "DenyPersistentStateBucketDeletion"
        Effect   = "Deny"
        Action   = "s3:DeleteBucket"
        Resource = local.state_bucket_arn
      },
      {
        Sid      = "DenyPersistentRepositoriesDeletion"
        Effect   = "Deny"
        Action   = "ecr:DeleteRepository"
        Resource = values(local.ecr_repository_arns)
      },
    ]
  })

  iam_manager_statements = concat(
    [
      for key in sort(keys(local.environment_roles)) : {
        Sid    = "Create${title(replace(replace(key, "/", ""), "-", ""))}RoleWithBoundary"
        Effect = "Allow"
        Action = [
          "iam:CreateRole",
          "iam:PutRolePermissionsBoundary",
        ]
        Resource = local.environment_role_arns[key]
        Condition = {
          ArnEquals = { "iam:PermissionsBoundary" = local.boundary_policy_arn }
          StringEquals = {
            "aws:RequestTag/PortfolioEnvironment" = local.environment_roles[key].environment
            "aws:RequestTag/PortfolioManaged"     = "true"
            "aws:RequestTag/PortfolioPersistent"  = "true"
            "aws:RequestTag/PortfolioPurpose"     = local.environment_roles[key].purpose
            "aws:RequestTag/PortfolioRepository"  = var.repository_identity
          }
        }
      }
    ],
    [{
      Sid    = "MaintainOnlyExactEnvironmentRoles"
      Effect = "Allow"
      Action = [
        "iam:DeleteRole",
        "iam:DeleteRolePolicy",
        "iam:GetRole",
        "iam:GetRolePolicy",
        "iam:ListRolePolicies",
        "iam:PutRolePolicy",
      ]
      Resource = local.boundary_environment_role_arns
    }],
    [{
      Sid      = "InventoryRoles"
      Effect   = "Allow"
      Action   = "iam:ListRoles"
      Resource = "*"
    }],
  )

  global_identity_policies = {
    iam_manager = jsonencode({
      Version   = "2012-10-17"
      Statement = local.iam_manager_statements
    })
    automation = jsonencode({
      Version = "2012-10-17"
      Statement = [{
        Sid    = "AssumeExactDeploymentAndDestroyRoles"
        Effect = "Allow"
        Action = "sts:AssumeRole"
        Resource = concat(
          [for environment in keys(var.environment_state_keys) : local.environment_role_arns["${environment}/operator-deployment"]],
          [for environment in keys(var.environment_state_keys) : local.environment_role_arns["${environment}/destroy"]],
        )
      }]
    })
  }

  operator_policies = {
    for environment, key in var.environment_state_keys : environment => jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Sid      = "ListExactEnvironmentState"
          Effect   = "Allow"
          Action   = "s3:ListBucket"
          Resource = local.state_bucket_arn
          Condition = {
            StringLike = { "s3:prefix" = [key, "${key}.tflock"] }
          }
        },
        {
          Sid      = "UseExactEnvironmentState"
          Effect   = "Allow"
          Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
          Resource = [local.environment_state_arns[environment], local.environment_lock_arns[environment]]
        },
        {
          Sid      = "AuthorizeEcr"
          Effect   = "Allow"
          Action   = "ecr:GetAuthorizationToken"
          Resource = "*"
        },
        {
          Sid    = "PublishOwnedImages"
          Effect = "Allow"
          Action = [
            "ecr:BatchCheckLayerAvailability",
            "ecr:BatchGetImage",
            "ecr:CompleteLayerUpload",
            "ecr:DescribeImages",
            "ecr:GetDownloadUrlForLayer",
            "ecr:InitiateLayerUpload",
            "ecr:ListImages",
            "ecr:PutImage",
            "ecr:UploadLayerPart",
          ]
          Resource = values(local.ecr_repository_arns)
        },
        {
          Sid    = "PassEcsRolesOnlyToEcs"
          Effect = "Allow"
          Action = "iam:PassRole"
          Resource = [
            local.environment_role_arns["${environment}/task-execution"],
            local.environment_role_arns["${environment}/web-workload"],
            local.environment_role_arns["${environment}/api-workload"],
            local.environment_role_arns["${environment}/ml-workload"],
          ]
          Condition = { StringEquals = { "iam:PassedToService" = local.ecs_service_principal } }
        },
        {
          Sid       = "PassSchedulerRoleOnlyToScheduler"
          Effect    = "Allow"
          Action    = "iam:PassRole"
          Resource  = local.environment_role_arns["${environment}/scheduler"]
          Condition = { StringEquals = { "iam:PassedToService" = local.scheduler_service_principal } }
        },
        {
          Sid       = "PassCodeBuildRoleOnlyToCodeBuild"
          Effect    = "Allow"
          Action    = "iam:PassRole"
          Resource  = local.environment_role_arns["${environment}/codebuild-destroy"]
          Condition = { StringEquals = { "iam:PassedToService" = local.codebuild_service_principal } }
        },
        {
          Sid    = "ManageExactEnvironmentServices"
          Effect = "Allow"
          Action = [
            "apigateway:GET", "apigateway:PATCH", "apigateway:POST", "apigateway:PUT",
            "cognito-idp:CreateUserPool", "cognito-idp:DescribeUserPool",
            "ecs:CreateCluster", "ecs:CreateService", "ecs:DescribeClusters", "ecs:DescribeServices",
            "ecs:DescribeTaskDefinition", "ecs:RegisterTaskDefinition", "ecs:TagResource", "ecs:UpdateService",
            "logs:CreateLogGroup", "logs:CreateLogStream", "logs:DescribeLogStreams", "logs:PutLogEvents",
            "mq:CreateBroker", "mq:DescribeBroker",
            "rds:CreateDBInstance", "rds:DescribeDBInstances", "rds:ModifyDBInstance",
            "scheduler:CreateSchedule", "scheduler:GetSchedule", "scheduler:UpdateSchedule",
            "secretsmanager:CreateSecret", "secretsmanager:DescribeSecret", "secretsmanager:PutSecretValue",
            "secretsmanager:TagResource", "secretsmanager:UpdateSecret",
            "servicediscovery:CreateHttpNamespace", "servicediscovery:CreateService",
            "servicediscovery:GetNamespace", "servicediscovery:GetService",
          ]
          Resource = [
            "arn:${var.aws_partition}:apigateway:${var.aws_region}::/apis/*",
            "arn:${var.aws_partition}:cognito-idp:${var.aws_region}:${var.aws_account_id}:userpool/*",
            "arn:${var.aws_partition}:ecs:${var.aws_region}:${var.aws_account_id}:cluster/${var.name_prefix}-${environment}",
            "arn:${var.aws_partition}:ecs:${var.aws_region}:${var.aws_account_id}:service/${var.name_prefix}-${environment}/*",
            "arn:${var.aws_partition}:ecs:${var.aws_region}:${var.aws_account_id}:task-definition/${var.name_prefix}-${environment}-*:*",
            "arn:${var.aws_partition}:logs:${var.aws_region}:${var.aws_account_id}:log-group:/portfolio/${var.name_prefix}/${environment}/*",
            "arn:${var.aws_partition}:logs:${var.aws_region}:${var.aws_account_id}:log-group:/portfolio/${var.name_prefix}/${environment}/*:*",
            "arn:${var.aws_partition}:mq:${var.aws_region}:${var.aws_account_id}:broker:${var.name_prefix}-${environment}-*:*",
            "arn:${var.aws_partition}:rds:${var.aws_region}:${var.aws_account_id}:db:${var.name_prefix}-${environment}-*",
            "arn:${var.aws_partition}:scheduler:${var.aws_region}:${var.aws_account_id}:schedule/*/${var.name_prefix}-${environment}-destroy-*",
            "arn:${var.aws_partition}:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.name_prefix}-${environment}-*",
            "arn:${var.aws_partition}:servicediscovery:${var.aws_region}:${var.aws_account_id}:namespace/*",
            "arn:${var.aws_partition}:servicediscovery:${var.aws_region}:${var.aws_account_id}:service/*",
          ]
        },
        {
          Sid      = "CreateTaggedEnvironmentNetwork"
          Effect   = "Allow"
          Action   = ["ec2:Create*", "ec2:Describe*", "ec2:Modify*", "ec2:AssociateRouteTable", "ec2:AttachInternetGateway"]
          Resource = "*"
          Condition = {
            StringEquals = {
              "aws:RequestTag/PortfolioEnvironment" = environment
              "aws:RequestTag/PortfolioManaged"     = "true"
              "aws:RequestTag/PortfolioPersistent"  = "false"
            }
          }
        },
      ]
    })
  }

  task_execution_policies = {
    for environment in keys(var.environment_state_keys) : environment => jsonencode({
      Version = "2012-10-17"
      Statement = [
        { Sid = "AuthorizeEcr", Effect = "Allow", Action = "ecr:GetAuthorizationToken", Resource = "*" },
        {
          Sid      = "PullOwnedImages"
          Effect   = "Allow"
          Action   = ["ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
          Resource = values(local.ecr_repository_arns)
        },
        {
          Sid      = "WriteExactEnvironmentLogs"
          Effect   = "Allow"
          Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
          Resource = "arn:${var.aws_partition}:logs:${var.aws_region}:${var.aws_account_id}:log-group:/portfolio/${var.name_prefix}/${environment}/*:*"
        },
        {
          Sid      = "ReadExactEnvironmentSecrets"
          Effect   = "Allow"
          Action   = ["secretsmanager:DescribeSecret", "secretsmanager:GetSecretValue"]
          Resource = "arn:${var.aws_partition}:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.name_prefix}-${environment}-*"
        },
      ]
    })
  }

  web_workload_policies = {
    for environment in keys(var.environment_state_keys) : environment => jsonencode({
      Version   = "2012-10-17"
      Statement = [{ Sid = "IdentityOnly", Effect = "Allow", Action = "sts:GetCallerIdentity", Resource = "*" }]
    })
  }

  api_workload_policies = {
    for environment in keys(var.environment_state_keys) : environment => jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Sid      = "ListExactApplicationBucket"
          Effect   = "Allow"
          Action   = "s3:ListBucket"
          Resource = local.environment_app_bucket_arns[environment]
        },
        {
          Sid      = "OwnExactApplicationObjects"
          Effect   = "Allow"
          Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
          Resource = "${local.environment_app_bucket_arns[environment]}/*"
        },
      ]
    })
  }

  ml_workload_policies = {
    for environment in keys(var.environment_state_keys) : environment => jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Sid      = "ListExactApplicationBucket"
          Effect   = "Allow"
          Action   = "s3:ListBucket"
          Resource = local.environment_app_bucket_arns[environment]
        },
        {
          Sid      = "ReadAndWriteExactApplicationObjects"
          Effect   = "Allow"
          Action   = ["s3:GetObject", "s3:PutObject"]
          Resource = "${local.environment_app_bucket_arns[environment]}/*"
        },
      ]
    })
  }

  scheduler_policies = {
    for environment in keys(var.environment_state_keys) : environment => jsonencode({
      Version = "2012-10-17"
      Statement = [{
        Sid      = "StartExactDestroyProject"
        Effect   = "Allow"
        Action   = "codebuild:StartBuild"
        Resource = "arn:${var.aws_partition}:codebuild:${var.aws_region}:${var.aws_account_id}:project/${var.name_prefix}-${environment}-destroy"
      }]
    })
  }

  codebuild_destroy_policies = {
    for environment, key in var.environment_state_keys : environment => jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Sid       = "ListExactEnvironmentState"
          Effect    = "Allow"
          Action    = "s3:ListBucket"
          Resource  = local.state_bucket_arn
          Condition = { StringLike = { "s3:prefix" = [key, "${key}.tflock"] } }
        },
        {
          Sid      = "UseExactEnvironmentState"
          Effect   = "Allow"
          Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
          Resource = [local.environment_state_arns[environment], local.environment_lock_arns[environment]]
        },
        {
          Sid      = "WriteExactDestroyLogs"
          Effect   = "Allow"
          Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
          Resource = "arn:${var.aws_partition}:logs:${var.aws_region}:${var.aws_account_id}:log-group:/portfolio/${var.name_prefix}/${environment}/destroy:*"
        },
        {
          Sid      = "AssumeExactDestroyRole"
          Effect   = "Allow"
          Action   = "sts:AssumeRole"
          Resource = local.environment_role_arns["${environment}/destroy"]
        },
      ]
    })
  }

  destroy_policies = {
    for environment in keys(var.environment_state_keys) : environment => jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Sid    = "DeleteOnlyExactNamedEnvironmentResources"
          Effect = "Allow"
          Action = [
            "apigateway:DELETE", "cognito-idp:DeleteUserPool",
            "ecs:DeleteCluster", "ecs:DeleteService", "ecs:DeregisterTaskDefinition",
            "logs:DeleteLogGroup", "mq:DeleteBroker", "rds:DeleteDBInstance",
            "secretsmanager:DeleteSecret", "servicediscovery:DeleteNamespace", "servicediscovery:DeleteService",
          ]
          Resource = [
            "arn:${var.aws_partition}:apigateway:${var.aws_region}::/apis/*",
            "arn:${var.aws_partition}:cognito-idp:${var.aws_region}:${var.aws_account_id}:userpool/*",
            "arn:${var.aws_partition}:ecs:${var.aws_region}:${var.aws_account_id}:cluster/${var.name_prefix}-${environment}",
            "arn:${var.aws_partition}:ecs:${var.aws_region}:${var.aws_account_id}:service/${var.name_prefix}-${environment}/*",
            "arn:${var.aws_partition}:ecs:${var.aws_region}:${var.aws_account_id}:task-definition/${var.name_prefix}-${environment}-*:*",
            "arn:${var.aws_partition}:logs:${var.aws_region}:${var.aws_account_id}:log-group:/portfolio/${var.name_prefix}/${environment}/*",
            "arn:${var.aws_partition}:mq:${var.aws_region}:${var.aws_account_id}:broker:${var.name_prefix}-${environment}-*:*",
            "arn:${var.aws_partition}:rds:${var.aws_region}:${var.aws_account_id}:db:${var.name_prefix}-${environment}-*",
            "arn:${var.aws_partition}:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.name_prefix}-${environment}-*",
            "arn:${var.aws_partition}:servicediscovery:${var.aws_region}:${var.aws_account_id}:namespace/*",
            "arn:${var.aws_partition}:servicediscovery:${var.aws_region}:${var.aws_account_id}:service/*",
          ]
        },
        {
          Sid      = "DeleteExactApplicationObjectsAndBucket"
          Effect   = "Allow"
          Action   = ["s3:DeleteObject", "s3:DeleteBucket"]
          Resource = [local.environment_app_bucket_arns[environment], "${local.environment_app_bucket_arns[environment]}/*"]
        },
        {
          Sid      = "DeleteOnlyTaggedEnvironmentNetwork"
          Effect   = "Allow"
          Action   = ["ec2:Delete*", "ec2:DetachInternetGateway", "ec2:DisassociateRouteTable", "ec2:ReleaseAddress", "ec2:RevokeSecurityGroupEgress", "ec2:RevokeSecurityGroupIngress"]
          Resource = "*"
          Condition = {
            StringEquals = {
              "aws:ResourceTag/PortfolioEnvironment" = environment
              "aws:ResourceTag/PortfolioManaged"     = "true"
              "aws:ResourceTag/PortfolioPersistent"  = "false"
            }
          }
        },
      ]
    })
  }

  environment_identity_policies = {
    for key, role in local.environment_roles : key => (
      role.purpose == "operator-deployment" ? local.operator_policies[role.environment] :
      role.purpose == "task-execution" ? local.task_execution_policies[role.environment] :
      role.purpose == "web-workload" ? local.web_workload_policies[role.environment] :
      role.purpose == "api-workload" ? local.api_workload_policies[role.environment] :
      role.purpose == "ml-workload" ? local.ml_workload_policies[role.environment] :
      role.purpose == "scheduler" ? local.scheduler_policies[role.environment] :
      role.purpose == "codebuild-destroy" ? local.codebuild_destroy_policies[role.environment] :
      local.destroy_policies[role.environment]
    )
  }
}
