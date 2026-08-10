locals {
  boundary_environment_token = "$${aws:PrincipalTag/PortfolioEnvironment}"
  boundary_requested_role_arn = (
    "${local.iam_prefix}:role${local.role_path}${var.name_prefix}-$${aws:RequestTag/PortfolioEnvironment}-$${aws:RequestTag/PortfolioPurpose}"
  )
  boundary_same_environment_scheduler_role_arn = "${local.iam_prefix}:role${local.role_path}${var.name_prefix}-${local.boundary_environment_token}-scheduler"
  boundary_same_environment_destroy_role_arn   = "${local.iam_prefix}:role${local.role_path}${var.name_prefix}-${local.boundary_environment_token}-destroy"
  boundary_same_environment_ecs_role_arns = [
    for purpose in ["task-execution", "web-workload", "api-workload", "ml-workload"] :
    "${local.iam_prefix}:role${local.role_path}${var.name_prefix}-${local.boundary_environment_token}-${purpose}"
  ]

  permissions_boundary_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = local.state_bucket_arn
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = ["operator-deployment", "codebuild-image", "codebuild-destroy", "destroy"]
          }
          StringLike = {
            "s3:prefix" = [
              "environments/${local.boundary_environment_token}/terraform.tfstate*",
              "controls/${var.name_prefix}/${local.boundary_environment_token}/*",
            ]
          }
        }
      },
      {
        Effect = "Allow"
        Action = ["s3:GetBucket*", "s3:GetEncryptionConfiguration", "s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = [
          local.state_bucket_arn,
          "${local.state_bucket_arn}/environments/${local.boundary_environment_token}/terraform.tfstate*",
          "${local.state_bucket_arn}/controls/${var.name_prefix}/${local.boundary_environment_token}/*",
        ]
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = ["operator-deployment", "codebuild-image", "codebuild-destroy", "destroy"]
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
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:*Image*",
          "ecr:*Layer*",
          "ecr:DescribeRepositories",
          "ecr:GetLifecyclePolicy",
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = ["operator-deployment", "task-execution", "codebuild-image", "destroy"]
          }
        }
      },
      {
        Effect = "Allow"
        Action = [
          "codebuild:*",
          "ecs:*",
          "logs:*",
          "mq:*",
          "rds:*",
          "scheduler:*",
          "secretsmanager:*",
        ]
        Resource = "arn:${var.aws_partition}:*:${var.aws_region}:${var.aws_account_id}:*${var.name_prefix}*${local.boundary_environment_token}*"
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = [
              "operator-deployment",
              "task-execution",
              "scheduler",
              "codebuild-image",
              "codebuild-destroy",
              "destroy",
            ]
          }
        }
      },
      {
        Effect = "Allow"
        Action = [
          "apigateway:*",
          "cognito-idp:Admin*",
          "cognito-idp:*UserPool*",
          "cognito-idp:TagResource",
          "mq:CreateBroker",
          "servicediscovery:*",
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = "operator-deployment"
          }
        }
      },
      {
        Effect = "Allow"
        Action = [
          "apigateway:DELETE",
          "cognito-idp:DeleteUserPool",
          "servicediscovery:Delete*",
          "servicediscovery:List*",
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = "destroy"
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
            "aws:PrincipalTag/PortfolioPurpose" = "operator-deployment"
          }
        }
      },
      {
        Effect   = "Allow"
        Action   = ["ec2:Describe*", "logs:DescribeLogGroups"]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = ["operator-deployment", "destroy"]
          }
        }
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:AssociateRouteTable",
          "ec2:AttachInternetGateway",
          "ec2:AuthorizeSecurityGroupEgress",
          "ec2:AuthorizeSecurityGroupIngress",
          "ec2:CreateRoute",
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = "operator-deployment"
          }
        }
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:Delete*",
          "ec2:DetachInternetGateway",
          "ec2:DisassociateRouteTable",
          "ec2:ReleaseAddress",
          "ec2:RevokeSecurityGroupEgress",
          "ec2:RevokeSecurityGroupIngress",
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/PortfolioPurpose" = "destroy"
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
            "codebuild-image",
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

  lifecycle_operator_policies = {
    for environment in keys(var.environment_state_keys) : environment => jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Sid      = "UseExactLifecycleControl"
          Effect   = "Allow"
          Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
          Resource = "${local.state_bucket_arn}/controls/${var.name_prefix}/${environment}/*"
        },
        {
          Sid      = "InspectPersistentStateBucket"
          Effect   = "Allow"
          Action   = ["s3:GetBucketLocation", "s3:GetBucketPublicAccessBlock", "s3:GetBucketVersioning", "s3:GetEncryptionConfiguration"]
          Resource = local.state_bucket_arn
        },
        {
          Sid    = "UseExactPersistentController"
          Effect = "Allow"
          Action = [
            "codebuild:BatchGetBuilds",
            "codebuild:BatchGetProjects",
            "codebuild:StartBuild",
          ]
          Resource = [
            "arn:${var.aws_partition}:codebuild:${var.aws_region}:${var.aws_account_id}:project/${var.name_prefix}-${environment}-image-build",
            "arn:${var.aws_partition}:codebuild:${var.aws_region}:${var.aws_account_id}:project/${var.name_prefix}-${environment}-destroy",
            "arn:${var.aws_partition}:codebuild:${var.aws_region}:${var.aws_account_id}:build/${var.name_prefix}-${environment}-image-build:*",
          ]
        },
        {
          Sid      = "ReconcileExactImageBuildspec"
          Effect   = "Allow"
          Action   = "codebuild:UpdateProject"
          Resource = "arn:${var.aws_partition}:codebuild:${var.aws_region}:${var.aws_account_id}:project/${var.name_prefix}-${environment}-image-build"
        },
        {
          # HTTP API access logging uses account-level delivery permissions that
          # expose neither a resource ARN nor a scoping condition.
          Sid    = "ManageApiGatewayLogDeliveryDependency"
          Effect = "Allow"
          Action = [
            "logs:CreateLogDelivery",
            "logs:DeleteLogDelivery",
            "logs:DescribeResourcePolicies",
            "logs:GetLogDelivery",
            "logs:ListLogDeliveries",
            "logs:PutResourcePolicy",
            "logs:UpdateLogDelivery",
          ]
          Resource = "*"
        },
        {
          Sid      = "InspectExactImageRepositories"
          Effect   = "Allow"
          Action   = ["ecr:DescribeRepositories", "ecr:GetLifecyclePolicy"]
          Resource = values(local.ecr_repository_arns)
        },
        {
          Sid      = "InspectPersistentControllerLogs"
          Effect   = "Allow"
          Action   = "logs:DescribeLogGroups"
          Resource = "*"
        },
        {
          Sid    = "InspectExactControllerLogTags"
          Effect = "Allow"
          Action = "logs:ListTagsForResource"
          Resource = [
            "arn:${var.aws_partition}:logs:${var.aws_region}:${var.aws_account_id}:log-group:/portfolio/${var.name_prefix}/${environment}/controller/image",
            "arn:${var.aws_partition}:logs:${var.aws_region}:${var.aws_account_id}:log-group:/portfolio/${var.name_prefix}/${environment}/controller/destroy",
          ]
        },
        {
          Sid      = "InspectExactLifecycleScheduleGroup"
          Effect   = "Allow"
          Action   = ["scheduler:GetScheduleGroup", "scheduler:ListTagsForResource"]
          Resource = "arn:${var.aws_partition}:scheduler:${var.aws_region}:${var.aws_account_id}:schedule-group/${var.name_prefix}-${environment}-lifecycle"
        },
        {
          Sid       = "PassSchedulerRoleOnlyToScheduler"
          Effect    = "Allow"
          Action    = "iam:PassRole"
          Resource  = local.environment_role_arns["${environment}/scheduler"]
          Condition = { StringEquals = { "iam:PassedToService" = local.scheduler_service_principal } }
        },
        {
          Sid    = "ManageExactFallbackSchedule"
          Effect = "Allow"
          Action = ["scheduler:CreateSchedule", "scheduler:DeleteSchedule", "scheduler:GetSchedule", "scheduler:UpdateSchedule"]
          Resource = (
            "arn:${var.aws_partition}:scheduler:${var.aws_region}:${var.aws_account_id}:schedule/${var.name_prefix}-${environment}-lifecycle/${var.name_prefix}-${environment}-destroy"
          )
        },
        {
          Sid      = "RunExactMigrationTask"
          Effect   = "Allow"
          Action   = "ecs:RunTask"
          Resource = "arn:${var.aws_partition}:ecs:${var.aws_region}:${var.aws_account_id}:task-definition/${var.name_prefix}-${environment}-migration:*"
          Condition = {
            ArnEquals = {
              "ecs:cluster" = "arn:${var.aws_partition}:ecs:${var.aws_region}:${var.aws_account_id}:cluster/${var.name_prefix}-${environment}"
            }
          }
        },
        {
          Sid      = "DeregisterSupersededTaskDefinitionAwsGlobalOnly"
          Effect   = "Allow"
          Action   = "ecs:DeregisterTaskDefinition"
          Resource = "*"
        },
        {
          Sid      = "TagMigrationTaskOnCreate"
          Effect   = "Allow"
          Action   = "ecs:TagResource"
          Resource = "arn:${var.aws_partition}:ecs:${var.aws_region}:${var.aws_account_id}:task/${var.name_prefix}-${environment}/*"
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
          Sid      = "InspectAndStopExactEnvironmentTasks"
          Effect   = "Allow"
          Action   = ["ecs:DescribeTasks", "ecs:ListTasks", "ecs:StopTask"]
          Resource = "*"
          Condition = {
            ArnEquals = {
              "ecs:cluster" = "arn:${var.aws_partition}:ecs:${var.aws_region}:${var.aws_account_id}:cluster/${var.name_prefix}-${environment}"
            }
          }
        },
        {
          Sid    = "ManageBoundedSyntheticReviewer"
          Effect = "Allow"
          Action = [
            "cognito-idp:AdminAddUserToGroup",
            "cognito-idp:AdminCreateUser",
            "cognito-idp:AdminDeleteUser",
            "cognito-idp:AdminGetUser",
            "cognito-idp:AdminListGroupsForUser",
            "cognito-idp:AdminSetUserPassword",
          ]
          Resource = "arn:${var.aws_partition}:cognito-idp:${var.aws_region}:${var.aws_account_id}:userpool/*"
          Condition = {
            StringEquals = {
              "aws:ResourceTag/PortfolioEnvironment" = environment
              "aws:ResourceTag/PortfolioManaged"     = "true"
              "aws:ResourceTag/PortfolioPersistent"  = "false"
              "aws:ResourceTag/PortfolioRepository"  = var.repository_identity
            }
          }
        },
      ]
    })
  }

  lifecycle_destroy_policies = {
    for environment, key in var.environment_state_keys : environment => jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Sid      = "InspectPersistentStateBucket"
          Effect   = "Allow"
          Action   = ["s3:GetBucketLocation", "s3:GetBucketPublicAccessBlock", "s3:GetBucketVersioning", "s3:GetEncryptionConfiguration"]
          Resource = local.state_bucket_arn
        },
        {
          Sid      = "ListExactLifecycleAndState"
          Effect   = "Allow"
          Action   = "s3:ListBucket"
          Resource = local.state_bucket_arn
          Condition = {
            StringLike = { "s3:prefix" = [key, "${key}.tflock", "controls/${var.name_prefix}/${environment}/*"] }
          }
        },
        {
          Sid      = "UseExactEnvironmentState"
          Effect   = "Allow"
          Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
          Resource = [local.environment_state_arns[environment], local.environment_lock_arns[environment]]
        },
        {
          Sid      = "UseExactLifecycleControl"
          Effect   = "Allow"
          Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
          Resource = "${local.state_bucket_arn}/controls/${var.name_prefix}/${environment}/*"
        },
        {
          Sid      = "RemoveExactCompletedFallback"
          Effect   = "Allow"
          Action   = ["scheduler:DeleteSchedule", "scheduler:GetSchedule"]
          Resource = "arn:${var.aws_partition}:scheduler:${var.aws_region}:${var.aws_account_id}:schedule/${var.name_prefix}-${environment}-lifecycle/${var.name_prefix}-${environment}-destroy"
        },
        {
          Sid      = "RemoveExactPublishedImages"
          Effect   = "Allow"
          Action   = ["ecr:BatchDeleteImage", "ecr:DescribeImages"]
          Resource = values(local.ecr_repository_arns)
        },
        {
          Sid    = "ReadGlobalProviderDestroyState"
          Effect = "Allow"
          Action = [
            "cognito-idp:DescribeUserPoolDomain",
            "ec2:DescribeNetworkAcls",
            "ec2:DescribePrefixLists",
            "ec2:DescribeSecurityGroupRules",
            "ec2:DescribeVpcAttribute",
            "servicediscovery:GetOperation",
            "sts:GetCallerIdentity",
          ]
          Resource = "*"
        },
        {
          Sid    = "ReadOwnedProviderDestroyState"
          Effect = "Allow"
          Action = [
            "cognito-idp:DescribeManagedLoginBranding",
            "cognito-idp:DescribeManagedLoginBrandingByClient",
            "cognito-idp:DescribeResourceServer",
            "cognito-idp:DescribeUserPool",
            "cognito-idp:DescribeUserPoolClient",
            "cognito-idp:GetGroup",
            "cognito-idp:GetUserPoolMfaConfig",
            "cognito-idp:ListTagsForResource",
            "cognito-idp:ListUserPoolClients",
            "servicediscovery:GetNamespace",
            "servicediscovery:GetService",
            "servicediscovery:ListInstances",
            "servicediscovery:ListTagsForResource",
          ]
          Resource = [
            "arn:${var.aws_partition}:cognito-idp:${var.aws_region}:${var.aws_account_id}:userpool/*",
            "arn:${var.aws_partition}:servicediscovery:${var.aws_region}:${var.aws_account_id}:namespace/*",
            "arn:${var.aws_partition}:servicediscovery:${var.aws_region}:${var.aws_account_id}:service/*",
          ]
          Condition = {
            StringEquals = {
              "aws:ResourceTag/PortfolioEnvironment" = environment
              "aws:ResourceTag/PortfolioManaged"     = "true"
              "aws:ResourceTag/PortfolioPersistent"  = "false"
              "aws:ResourceTag/PortfolioRepository"  = var.repository_identity
            }
          }
        },
        {
          Sid    = "ReadExactNamedProviderDestroyState"
          Effect = "Allow"
          Action = [
            "logs:ListTagsForResource",
            "secretsmanager:DescribeSecret",
            "secretsmanager:GetResourcePolicy",
          ]
          Resource = [
            "arn:${var.aws_partition}:logs:${var.aws_region}:${var.aws_account_id}:log-group:/portfolio/${var.name_prefix}/${environment}/*",
            "arn:${var.aws_partition}:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.name_prefix}-${environment}-database-*",
            "arn:${var.aws_partition}:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.name_prefix}-${environment}-broker-*",
          ]
        },
        {
          Sid    = "ReadServiceSpecificResidue"
          Effect = "Allow"
          Action = [
            "apigateway:GET",
            "cognito-idp:ListUserPools",
            "ec2:DescribeInternetGateways",
            "ec2:DescribeNetworkInterfaces",
            "ec2:DescribeRouteTables",
            "ec2:DescribeSecurityGroups",
            "ec2:DescribeSubnets",
            "ec2:DescribeVpcEndpoints",
            "ec2:DescribeVpcs",
            "ecs:DescribeClusters",
            "ecs:DescribeServices",
            "ecs:DescribeTaskDefinition",
            "ecs:DescribeTasks",
            "ecs:ListClusters",
            "ecs:ListServices",
            "ecs:ListTaskDefinitions",
            "ecs:ListTasks",
            "logs:DescribeLogGroups",
            "mq:DescribeBroker",
            "mq:ListBrokers",
            "rds:DescribeDBInstances",
            "rds:DescribeDBSubnetGroups",
            "route53:ListHostedZonesByName",
            "secretsmanager:ListSecrets",
            "servicediscovery:ListNamespaces",
            "servicediscovery:ListServices",
            "tag:GetResources",
          ]
          Resource = "*"
        },
      ]
    })
  }

  operator_policies = {
    for environment, key in var.environment_state_keys : environment => jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          # ListExactEnvironmentState
          Effect   = "Allow"
          Action   = "s3:ListBucket"
          Resource = local.state_bucket_arn
          Condition = {
            StringLike = { "s3:prefix" = [key, "${key}.tflock"] }
          }
        },
        {
          # UseExactEnvironmentState
          Effect   = "Allow"
          Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
          Resource = [local.environment_state_arns[environment], local.environment_lock_arns[environment]]
        },
        {
          # PassEcsRolesOnlyToEcs
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
          # CreateTaggedApiGatewayResources
          Effect = "Allow"
          Action = "apigateway:POST"
          Resource = [
            "arn:${var.aws_partition}:apigateway:${var.aws_region}::/apis",
            "arn:${var.aws_partition}:apigateway:${var.aws_region}::/vpclinks",
          ]
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
          # CreateStage/CreateVpcLink dependent TagResource reuses these create resources
          # without exposing either request or resource ownership tags.
          Effect = "Allow"
          Action = "apigateway:TagResource"
          Resource = [
            "arn:${var.aws_partition}:apigateway:${var.aws_region}::/apis/*/stages",
            "arn:${var.aws_partition}:apigateway:${var.aws_region}::/vpclinks",
          ]
        },
        {
          # API Gateway dependent TagResource omits both request and resource tags.
          Effect   = "Allow"
          Action   = ["apigateway:POST", "apigateway:PUT"]
          Resource = "arn:${var.aws_partition}:apigateway:${var.aws_region}::/tags/*"
        },
        {
          # The same dependent authorization requires PATCH on the new target.
          Effect = "Allow"
          Action = "apigateway:PATCH"
          Resource = [
            "arn:${var.aws_partition}:apigateway:${var.aws_region}::/apis/*",
            "arn:${var.aws_partition}:apigateway:${var.aws_region}::/vpclinks/*",
          ]
        },
        {
          # CreateTaggedIdEnvironmentServices
          Effect = "Allow"
          Action = [
            "cognito-idp:CreateUserPool",
            "mq:CreateBroker",
            "servicediscovery:CreatePrivateDnsNamespace",
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
          # AuthorizeOwnedCloudMapNamespace
          Effect   = "Allow"
          Action   = "servicediscovery:CreateService"
          Resource = "arn:${var.aws_partition}:servicediscovery:${var.aws_region}:${var.aws_account_id}:namespace/*"
          Condition = {
            StringEquals = {
              "aws:ResourceTag/PortfolioEnvironment" = environment
              "aws:ResourceTag/PortfolioManaged"     = "true"
              "aws:ResourceTag/PortfolioPersistent"  = "false"
              "aws:ResourceTag/PortfolioRepository"  = var.repository_identity
            }
          }
        },
        {
          # CreateTaggedCloudMapService
          Effect   = "Allow"
          Action   = "servicediscovery:CreateService"
          Resource = "arn:${var.aws_partition}:servicediscovery:${var.aws_region}:${var.aws_account_id}:service/*"
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
          # TagOwnedCognitoUserPool
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
          # TagCloudMapOwnershipKeys
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
          # MutateOwnedHttpApiResources
          Effect   = "Allow"
          Action   = ["apigateway:PATCH", "apigateway:POST", "apigateway:PUT"]
          Resource = "arn:${var.aws_partition}:apigateway:${var.aws_region}::*"
          Condition = {
            StringEquals = {
              "aws:ResourceTag/PortfolioEnvironment" = environment
              "aws:ResourceTag/PortfolioManaged"     = "true"
              "aws:ResourceTag/PortfolioPersistent"  = "false"
              "aws:ResourceTag/PortfolioRepository"  = var.repository_identity
            }
          }
        },
        {
          # DescribeTaskDefinition has no resource type in the ECS authorization table.
          Effect   = "Allow"
          Action   = "ecs:DescribeTaskDefinition"
          Resource = "*"
        },
        {
          # ManageExactEnvironmentServices
          Effect = "Allow"
          Action = [
            "apigateway:GET",
            "cognito-idp:DescribeUserPool",
            "ecs:CreateCluster", "ecs:CreateService", "ecs:DescribeClusters", "ecs:DescribeServices",
            "ecs:RegisterTaskDefinition", "ecs:TagResource", "ecs:UpdateService",
            "logs:CreateLogGroup", "logs:CreateLogStream", "logs:DescribeLogStreams", "logs:PutLogEvents",
            "mq:DescribeBroker",
            "rds:CreateDBInstance", "rds:ModifyDBInstance",
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
            "arn:${var.aws_partition}:scheduler:${var.aws_region}:${var.aws_account_id}:schedule/${var.name_prefix}-${environment}-lifecycle/${var.name_prefix}-${environment}-destroy",
            "arn:${var.aws_partition}:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.name_prefix}-${environment}-*",
            "arn:${var.aws_partition}:servicediscovery:${var.aws_region}:${var.aws_account_id}:namespace/*",
            "arn:${var.aws_partition}:servicediscovery:${var.aws_region}:${var.aws_account_id}:service/*",
          ]
        },
        {
          # CreateTaggedEnvironmentNetwork
          Effect = "Allow"
          Action = [
            "ec2:AllocateAddress",
            "ec2:CreateInternetGateway",
            "ec2:CreateRouteTable",
            "ec2:CreateSecurityGroup",
            "ec2:CreateSubnet",
            "ec2:CreateVpc",
            "ec2:CreateVpcEndpoint",
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
          # Authorize multi-resource create calls against only the owned VPC.
          Effect = "Allow"
          Action = [
            "ec2:CreateRouteTable",
            "ec2:CreateSecurityGroup",
            "ec2:CreateSubnet",
            "ec2:CreateVpcEndpoint",
          ]
          Resource = [
            "arn:${var.aws_partition}:ec2:${var.aws_region}:${var.aws_account_id}:route-table/*",
            "arn:${var.aws_partition}:ec2:${var.aws_region}:${var.aws_account_id}:vpc/*",
          ]
          Condition = {
            StringEquals = {
              "aws:ResourceTag/PortfolioEnvironment" = environment
              "aws:ResourceTag/PortfolioManaged"     = "true"
              "aws:ResourceTag/PortfolioPersistent"  = "false"
              "aws:ResourceTag/PortfolioRepository"  = var.repository_identity
            }
          }
        },
        {
          # TagOnlyDuringEnvironmentNetworkCreation
          Effect   = "Allow"
          Action   = "ec2:CreateTags"
          Resource = "arn:${var.aws_partition}:ec2:${var.aws_region}:${var.aws_account_id}:*/*"
          Condition = {
            StringEquals = {
              "aws:RequestTag/PortfolioEnvironment" = environment
              "aws:RequestTag/PortfolioManaged"     = "true"
              "aws:RequestTag/PortfolioPersistent"  = "false"
              "aws:RequestTag/PortfolioRepository"  = var.repository_identity
              "ec2:CreateAction" = [
                "AllocateAddress",
                "AuthorizeSecurityGroupEgress",
                "AuthorizeSecurityGroupIngress",
                "CreateInternetGateway",
                "CreateRouteTable",
                "CreateSecurityGroup",
                "CreateSubnet",
                "CreateVpc",
                "CreateVpcEndpoint",
              ]
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
          # InspectEnvironmentNetwork
          Effect   = "Allow"
          Action   = ["ec2:Describe*", "rds:DescribeDBInstances"]
          Resource = "*"
        },
        {
          # ManageTaggedEnvironmentNetwork
          Effect = "Allow"
          Action = [
            "ec2:AssociateRouteTable",
            "ec2:AttachInternetGateway",
            "ec2:AuthorizeSecurityGroupEgress",
            "ec2:AuthorizeSecurityGroupIngress",
            "ec2:CreateRoute",
            "ec2:RevokeSecurityGroupEgress",
            "ec2:RevokeSecurityGroupIngress",
          ]
          Resource = "*"
          Condition = {
            StringEquals = {
              "aws:ResourceTag/PortfolioEnvironment" = environment
              "aws:ResourceTag/PortfolioManaged"     = "true"
              "aws:ResourceTag/PortfolioPersistent"  = "false"
              "aws:ResourceTag/PortfolioRepository"  = var.repository_identity
            }
          }
        },
        {
          # CreateTaggedSecurityGroupRules
          Effect = "Allow"
          Action = [
            "ec2:AuthorizeSecurityGroupEgress",
            "ec2:AuthorizeSecurityGroupIngress",
          ]
          Resource = "arn:${var.aws_partition}:ec2:${var.aws_region}:${var.aws_account_id}:security-group-rule/*"
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
          Sid      = "UseExactLifecycleControl"
          Effect   = "Allow"
          Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
          Resource = "${local.state_bucket_arn}/controls/${var.name_prefix}/${environment}/*"
        },
        {
          Sid      = "WriteExactDestroyLogs"
          Effect   = "Allow"
          Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
          Resource = "arn:${var.aws_partition}:logs:${var.aws_region}:${var.aws_account_id}:log-group:/portfolio/${var.name_prefix}/${environment}/controller/destroy:*"
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

  codebuild_image_policies = {
    for environment in keys(var.environment_state_keys) : environment => jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Sid      = "ReadExactLifecycleConfiguration"
          Effect   = "Allow"
          Action   = "s3:GetObject"
          Resource = "${local.state_bucket_arn}/controls/${var.name_prefix}/${environment}/configuration.json"
        },
        {
          Sid      = "AuthorizeEcr"
          Effect   = "Allow"
          Action   = "ecr:GetAuthorizationToken"
          Resource = "*"
        },
        {
          Sid    = "PublishExactImages"
          Effect = "Allow"
          Action = [
            "ecr:BatchCheckLayerAvailability",
            "ecr:CompleteLayerUpload",
            "ecr:DescribeImages",
            "ecr:GetDownloadUrlForLayer",
            "ecr:InitiateLayerUpload",
            "ecr:PutImage",
            "ecr:UploadLayerPart",
          ]
          Resource = values(local.ecr_repository_arns)
        },
        {
          Sid      = "WriteExactImageBuildLogs"
          Effect   = "Allow"
          Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
          Resource = "arn:${var.aws_partition}:logs:${var.aws_region}:${var.aws_account_id}:log-group:/portfolio/${var.name_prefix}/${environment}/controller/image:*"
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
              "aws:ResourceTag/PortfolioRepository"  = var.repository_identity
            }
          }
        },
        {
          Sid    = "RemoveApiGatewayLogDeliveryDependency"
          Effect = "Allow"
          Action = [
            "logs:DeleteLogDelivery",
            "logs:GetLogDelivery",
            "logs:ListLogDeliveries",
          ]
          Resource = "*"
        },
        {
          Sid      = "DeleteExactApplicationObjectsAndBucket"
          Effect   = "Allow"
          Action   = ["s3:DeleteObject", "s3:DeleteBucket"]
          Resource = [local.environment_app_bucket_arns[environment], "${local.environment_app_bucket_arns[environment]}/*"]
        },
        {
          Sid      = "RemoveExactPublishedImages"
          Effect   = "Allow"
          Action   = ["ecr:BatchDeleteImage", "ecr:DescribeImages"]
          Resource = values(local.ecr_repository_arns)
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
              "aws:ResourceTag/PortfolioRepository"  = var.repository_identity
            }
          }
        },
      ]
    })
  }

  environment_inline_policies = {
    for key, role in local.environment_roles : key => (
      role.purpose == "operator-deployment" ? local.operator_policies[role.environment] :
      role.purpose == "task-execution" ? local.task_execution_policies[role.environment] :
      role.purpose == "web-workload" ? local.web_workload_policies[role.environment] :
      role.purpose == "api-workload" ? local.api_workload_policies[role.environment] :
      role.purpose == "ml-workload" ? local.ml_workload_policies[role.environment] :
      role.purpose == "scheduler" ? local.scheduler_policies[role.environment] :
      role.purpose == "codebuild-image" ? local.codebuild_image_policies[role.environment] :
      role.purpose == "codebuild-destroy" ? local.codebuild_destroy_policies[role.environment] :
      local.destroy_policies[role.environment]
    )
  }

  environment_identity_policies = {
    for key, role in local.environment_roles : key => (
      role.purpose == "operator-deployment" ? jsonencode({
        Version = "2012-10-17"
        Statement = concat(
          jsondecode(local.operator_policies[role.environment]).Statement,
          jsondecode(local.lifecycle_operator_policies[role.environment]).Statement,
        )
        }) : role.purpose == "destroy" ? jsonencode({
        Version = "2012-10-17"
        Statement = concat(
          jsondecode(local.destroy_policies[role.environment]).Statement,
          jsondecode(local.lifecycle_destroy_policies[role.environment]).Statement,
        )
      }) : local.environment_inline_policies[key]
    )
  }
}
