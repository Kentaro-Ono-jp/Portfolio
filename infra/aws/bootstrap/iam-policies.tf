locals {
  boundary_environment_token = "$${aws:PrincipalTag/PortfolioEnvironment}"
  boundary_requested_role_arn = (
    "${local.iam_prefix}:role${local.role_path}${var.name_prefix}-$${aws:RequestTag/PortfolioEnvironment}-$${aws:RequestTag/PortfolioPurpose}"
  )
  boundary_same_environment_scheduler_role_arn = "${local.iam_prefix}:role${local.role_path}${var.name_prefix}-${local.boundary_environment_token}-scheduler"
  boundary_same_environment_codebuild_role_arn = "${local.iam_prefix}:role${local.role_path}${var.name_prefix}-${local.boundary_environment_token}-codebuild-destroy"
  boundary_same_environment_destroy_role_arn   = "${local.iam_prefix}:role${local.role_path}${var.name_prefix}-${local.boundary_environment_token}-destroy"
  boundary_same_environment_ecs_role_arns = [
    for purpose in ["task-execution", "web-workload", "api-workload", "ml-workload"] :
    "${local.iam_prefix}:role${local.role_path}${var.name_prefix}-${local.boundary_environment_token}-${purpose}"
  ]

  permissions_boundary_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "s3:*Object"
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
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = local.state_bucket_arn
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = ["operator-deployment", "codebuild-destroy"]
          }
          StringLike = {
            "s3:prefix" = "environments/${local.boundary_environment_token}/terraform.tfstate*"
          }
        }
      },
      {
        Effect = "Allow"
        Action = "s3:*"
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
        Effect   = "Allow"
        Action   = ["ecr:*Image*", "ecr:*Layer*"]
        Resource = values(local.ecr_repository_arns)
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = ["operator-deployment", "task-execution"]
          }
        }
      },
      {
        Effect = "Allow"
        Action = [
          "codebuild:StartBuild",
          "ecs:*",
          "logs:*",
          "mq:*",
          "rds:*",
          "scheduler:*",
          "secretsmanager:*",
        ]
        Resource = "arn:${var.aws_partition}:*:${var.aws_region}:${var.aws_account_id}:*${var.name_prefix}-${local.boundary_environment_token}*"
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = [
              "operator-deployment",
              "task-execution",
              "scheduler",
              "codebuild-destroy",
              "destroy",
            ]
          }
        }
      },
      {
        Effect = "Allow"
        Action = [
          "apigateway:POST",
          "cognito-idp:CreateUserPool",
          "servicediscovery:*",
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose"   = "operator-deployment"
            "aws:RequestTag/PortfolioEnvironment" = local.boundary_environment_token
            "aws:RequestTag/PortfolioManaged"     = "true"
            "aws:RequestTag/PortfolioPersistent"  = "false"
          }
        }
      },
      {
        Effect = "Allow"
        Action = [
          "apigateway:*",
          "cognito-idp:*UserPool*",
          "cognito-idp:TagResource",
          "servicediscovery:*",
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose"    = ["operator-deployment", "destroy"]
            "aws:ResourceTag/PortfolioEnvironment" = local.boundary_environment_token
            "aws:ResourceTag/PortfolioManaged"     = "true"
            "aws:ResourceTag/PortfolioPersistent"  = "false"
          }
        }
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:AllocateAddress",
          "ec2:Create*",
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose"   = "operator-deployment"
            "aws:RequestTag/PortfolioEnvironment" = local.boundary_environment_token
            "aws:RequestTag/PortfolioManaged"     = "true"
            "aws:RequestTag/PortfolioPersistent"  = "false"
          }
        }
      },
      {
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
        Effect   = "Allow"
        Action   = "ec2:*"
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose"    = ["operator-deployment", "destroy"]
            "aws:ResourceTag/PortfolioEnvironment" = local.boundary_environment_token
            "aws:ResourceTag/PortfolioManaged"     = "true"
            "aws:ResourceTag/PortfolioPersistent"  = "false"
          }
        }
      },
      {
        Effect   = "Allow"
        Action   = "iam:PassRole"
        Resource = local.boundary_same_environment_ecs_role_arns
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = "operator-deployment"
            "iam:PassedToService"               = local.ecs_service_principal
          }
        }
      },
      {
        Effect   = "Allow"
        Action   = "iam:PassRole"
        Resource = local.boundary_same_environment_scheduler_role_arn
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = "operator-deployment"
            "iam:PassedToService"               = local.scheduler_service_principal
          }
        }
      },
      {
        Effect   = "Allow"
        Action   = "iam:PassRole"
        Resource = local.boundary_same_environment_codebuild_role_arn
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = "operator-deployment"
            "iam:PassedToService"               = local.codebuild_service_principal
          }
        }
      },
      {
        Effect = "Allow"
        Action = "sts:AssumeRole"
        Resource = [
          "arn:${var.aws_partition}:iam::${var.aws_account_id}:role${local.role_path}${var.name_prefix}-*-operator-deployment",
          "arn:${var.aws_partition}:iam::${var.aws_account_id}:role${local.role_path}${var.name_prefix}-*-destroy",
        ]
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = "automation"
          }
        }
      },
      {
        Effect   = "Allow"
        Action   = "sts:AssumeRole"
        Resource = local.boundary_same_environment_destroy_role_arn
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = "codebuild-destroy"
          }
        }
      },
      {
        Effect   = "Allow"
        Action   = "iam:CreateRole"
        Resource = local.boundary_requested_role_arn
        Condition = {
          ArnEquals = {
            "iam:PermissionsBoundary" = local.boundary_policy_arn
          }
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose"   = "iam-manager"
            "aws:RequestTag/PortfolioEnvironment" = sort(keys(var.environment_state_keys))
          }
        }
      },
    ]
  })

  iam_manager_statements = [
    {
      Sid      = "CreateExactTaggedRoleWithBoundary"
      Effect   = "Allow"
      Action   = "iam:CreateRole"
      Resource = local.boundary_requested_role_arn
      Condition = {
        ArnEquals = { "iam:PermissionsBoundary" = local.boundary_policy_arn }
        StringEquals = {
          "aws:RequestTag/PortfolioEnvironment" = sort(keys(var.environment_state_keys))
          "aws:RequestTag/PortfolioManaged"     = "true"
          "aws:RequestTag/PortfolioPersistent"  = "true"
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
  ]

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
          Sid      = "CreateTaggedHttpApi"
          Effect   = "Allow"
          Action   = "apigateway:POST"
          Resource = "arn:${var.aws_partition}:apigateway:${var.aws_region}::/apis"
          Condition = {
            StringEquals = {
              "aws:RequestTag/PortfolioEnvironment" = environment
              "aws:RequestTag/PortfolioManaged"     = "true"
              "aws:RequestTag/PortfolioPersistent"  = "false"
            }
          }
        },
        {
          Sid    = "CreateTaggedIdEnvironmentServices"
          Effect = "Allow"
          Action = [
            "cognito-idp:CreateUserPool",
            "servicediscovery:CreateHttpNamespace",
            "servicediscovery:CreateService",
          ]
          Resource = "*"
          Condition = {
            StringEquals = {
              "aws:RequestTag/PortfolioEnvironment" = environment
              "aws:RequestTag/PortfolioManaged"     = "true"
              "aws:RequestTag/PortfolioPersistent"  = "false"
              "aws:RequestTag/PortfolioRepository"  = var.repository_identity
            }
            "ForAllValues:StringEquals" = {
              "aws:TagKeys" = [
                "PortfolioEnvironment",
                "PortfolioManaged",
                "PortfolioPersistent",
                "PortfolioRepository",
              ]
            }
          }
        },
        {
          Sid      = "TagOwnedCognitoUserPool"
          Effect   = "Allow"
          Action   = "cognito-idp:TagResource"
          Resource = "arn:${var.aws_partition}:cognito-idp:${var.aws_region}:${var.aws_account_id}:userpool/*"
          Condition = {
            StringEquals = {
              "aws:RequestTag/PortfolioEnvironment"  = environment
              "aws:RequestTag/PortfolioManaged"      = "true"
              "aws:RequestTag/PortfolioPersistent"   = "false"
              "aws:RequestTag/PortfolioRepository"   = var.repository_identity
              "aws:ResourceTag/PortfolioEnvironment" = environment
              "aws:ResourceTag/PortfolioManaged"     = "true"
              "aws:ResourceTag/PortfolioPersistent"  = "false"
              "aws:ResourceTag/PortfolioRepository"  = var.repository_identity
            }
            "ForAllValues:StringEquals" = {
              "aws:TagKeys" = [
                "PortfolioEnvironment",
                "PortfolioManaged",
                "PortfolioPersistent",
                "PortfolioRepository",
              ]
            }
          }
        },
        {
          Sid      = "TagCloudMapOwnershipKeys"
          Effect   = "Allow"
          Action   = "servicediscovery:TagResource"
          Resource = "*"
          Condition = {
            StringEquals = {
              "aws:RequestTag/PortfolioEnvironment" = environment
              "aws:RequestTag/PortfolioManaged"     = "true"
              "aws:RequestTag/PortfolioPersistent"  = "false"
              "aws:RequestTag/PortfolioRepository"  = var.repository_identity
            }
            "ForAllValues:StringEquals" = {
              "aws:TagKeys" = [
                "PortfolioEnvironment",
                "PortfolioManaged",
                "PortfolioPersistent",
                "PortfolioRepository",
              ]
            }
          }
        },
        {
          Sid    = "ManageExactEnvironmentServices"
          Effect = "Allow"
          Action = [
            "apigateway:GET", "apigateway:PATCH", "apigateway:POST", "apigateway:PUT",
            "cognito-idp:DescribeUserPool",
            "ecs:CreateCluster", "ecs:CreateService", "ecs:DescribeClusters", "ecs:DescribeServices",
            "ecs:DescribeTaskDefinition", "ecs:RegisterTaskDefinition", "ecs:TagResource", "ecs:UpdateService",
            "logs:CreateLogGroup", "logs:CreateLogStream", "logs:DescribeLogStreams", "logs:PutLogEvents",
            "mq:CreateBroker", "mq:DescribeBroker",
            "rds:CreateDBInstance", "rds:DescribeDBInstances", "rds:ModifyDBInstance",
            "scheduler:CreateSchedule", "scheduler:GetSchedule", "scheduler:UpdateSchedule",
            "secretsmanager:CreateSecret", "secretsmanager:DescribeSecret", "secretsmanager:PutSecretValue",
            "secretsmanager:TagResource", "secretsmanager:UpdateSecret",
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
          Action   = ["ec2:AllocateAddress", "ec2:Create*"]
          Resource = "*"
          Condition = {
            StringEquals = {
              "aws:RequestTag/PortfolioEnvironment" = environment
              "aws:RequestTag/PortfolioManaged"     = "true"
              "aws:RequestTag/PortfolioPersistent"  = "false"
            }
          }
        },
        {
          Sid      = "InspectEnvironmentNetwork"
          Effect   = "Allow"
          Action   = "ec2:Describe*"
          Resource = "*"
        },
        {
          Sid    = "ManageTaggedEnvironmentNetwork"
          Effect = "Allow"
          Action = [
            "ec2:AssociateRouteTable",
            "ec2:AttachInternetGateway",
            "ec2:AuthorizeSecurityGroupEgress",
            "ec2:AuthorizeSecurityGroupIngress",
            "ec2:CreateRoute",
            "ec2:Modify*",
          ]
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
            "ecs:DeleteCluster",
            "ecs:DeleteService",
            "ecs:DeregisterTaskDefinition",
            "logs:DeleteLogGroup",
            "mq:DeleteBroker",
            "rds:DeleteDBInstance",
            "secretsmanager:DeleteSecret",
          ]
          Resource = [
            "arn:${var.aws_partition}:ecs:${var.aws_region}:${var.aws_account_id}:cluster/${var.name_prefix}-${environment}",
            "arn:${var.aws_partition}:ecs:${var.aws_region}:${var.aws_account_id}:service/${var.name_prefix}-${environment}/*",
            "arn:${var.aws_partition}:ecs:${var.aws_region}:${var.aws_account_id}:task-definition/${var.name_prefix}-${environment}-*:*",
            "arn:${var.aws_partition}:logs:${var.aws_region}:${var.aws_account_id}:log-group:/portfolio/${var.name_prefix}/${environment}/*",
            "arn:${var.aws_partition}:mq:${var.aws_region}:${var.aws_account_id}:broker:${var.name_prefix}-${environment}-*:*",
            "arn:${var.aws_partition}:rds:${var.aws_region}:${var.aws_account_id}:db:${var.name_prefix}-${environment}-*",
            "arn:${var.aws_partition}:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.name_prefix}-${environment}-*",
          ]
        },
        {
          Sid    = "DeleteOnlyTaggedIdEnvironmentResources"
          Effect = "Allow"
          Action = [
            "apigateway:DELETE",
            "cognito-idp:DeleteUserPool",
            "servicediscovery:DeleteNamespace",
            "servicediscovery:DeleteService",
          ]
          Resource = "*"
          Condition = {
            StringEquals = {
              "aws:ResourceTag/PortfolioEnvironment" = environment
              "aws:ResourceTag/PortfolioManaged"     = "true"
              "aws:ResourceTag/PortfolioPersistent"  = "false"
            }
          }
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
