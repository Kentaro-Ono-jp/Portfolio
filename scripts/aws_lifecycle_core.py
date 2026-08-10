from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = 1
MAX_TTL_MINUTES = 120
MIN_TTL_MINUTES = 15
CONFIG_KEY_PATTERN = re.compile(
    r"^controls/[a-z][a-z0-9-]{1,18}[a-z0-9]/[a-z][a-z0-9-]{0,14}[a-z0-9]/configuration\.json$"
)
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
ACCOUNT_PATTERN = re.compile(r"^[0-9]{12}$")
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,18}[a-z0-9]$")
ENVIRONMENT_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,14}[a-z0-9]$")
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class LifecycleError(RuntimeError):
    pass


class Phase(StrEnum):
    CONFIGURED = "configured"
    PREFLIGHTED = "preflighted"
    IMAGES_PUBLISHED = "images-published"
    FALLBACK_REGISTERED = "fallback-registered"
    APPLYING = "applying"
    APPLIED = "applied"
    MIGRATED = "migrated"
    SEEDED = "seeded"
    SMOKE_PASSED = "smoke-passed"
    DESTROYING = "destroying"
    ZERO_RESIDUE = "zero-residue"
    FAILED = "failed"


FORWARD_PHASES = (
    Phase.CONFIGURED,
    Phase.PREFLIGHTED,
    Phase.IMAGES_PUBLISHED,
    Phase.FALLBACK_REGISTERED,
    Phase.APPLYING,
    Phase.APPLIED,
    Phase.MIGRATED,
    Phase.SEEDED,
    Phase.SMOKE_PASSED,
    Phase.DESTROYING,
    Phase.ZERO_RESIDUE,
)
PHASE_INDEX = {phase: index for index, phase in enumerate(FORWARD_PHASES)}


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        raise LifecycleError("Lifecycle timestamps must be timezone-aware.")
    return (
        value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )


def parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise LifecycleError("Lifecycle timestamp is invalid.") from error
    if parsed.tzinfo is None:
        raise LifecycleError("Lifecycle timestamp must include a timezone.")
    return parsed.astimezone(UTC)


def canonical_json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class LifecycleConfig:
    account_id: str
    partition: str
    region: str
    availability_zones: tuple[str, str]
    name_prefix: str
    environment: str
    repository_identity: str
    repository_url: str
    source_sha: str
    state_bucket: str
    state_key: str
    control_prefix: str
    source_user_name: str
    roles: Mapping[str, str]
    projects: Mapping[str, str]
    ecr_repository_urls: Mapping[str, str]
    vpc_cidr: str = "10.42.0.0/16"
    rds_instance_class: str = "db.t4g.micro"
    mq_instance_type: str = "mq.m7g.large"
    log_retention_days: int = 3
    object_expiration_days: int = 2
    reviewer_group_name: str = "reactorfront-reviewers"
    oidc_api_audience: str = "https://api.reactorfront.invalid/api"

    def __post_init__(self) -> None:
        if ACCOUNT_PATTERN.fullmatch(self.account_id) is None:
            raise LifecycleError("accountId must be exactly twelve digits.")
        if self.partition not in {"aws", "aws-us-gov", "aws-cn"}:
            raise LifecycleError("Unsupported AWS partition.")
        if NAME_PATTERN.fullmatch(self.name_prefix) is None or "--" in self.name_prefix:
            raise LifecycleError("namePrefix is invalid.")
        if (
            ENVIRONMENT_PATTERN.fullmatch(self.environment) is None
            or "--" in self.environment
        ):
            raise LifecycleError("environment is invalid.")
        if REPOSITORY_PATTERN.fullmatch(self.repository_identity) is None:
            raise LifecycleError("repositoryIdentity is invalid.")
        if self.repository_url != f"https://github.com/{self.repository_identity}.git":
            raise LifecycleError(
                "repositoryUrl must be derived from repositoryIdentity."
            )
        if SHA_PATTERN.fullmatch(self.source_sha) is None:
            raise LifecycleError("sourceSha must be a full lowercase Git commit SHA.")
        expected_state = f"environments/{self.environment}/terraform.tfstate"
        if self.state_key != expected_state:
            raise LifecycleError("stateKey is not bound to the exact environment.")
        expected_prefix = f"controls/{self.name_prefix}/{self.environment}"
        if self.control_prefix != expected_prefix:
            raise LifecycleError("controlPrefix is not deterministic.")
        if len(self.availability_zones) != 2 or len(set(self.availability_zones)) != 2:
            raise LifecycleError(
                "Exactly two distinct availability zones are required."
            )
        if any(not zone.startswith(self.region) for zone in self.availability_zones):
            raise LifecycleError(
                "Availability zones must belong to the configured region."
            )
        required_roles = {
            "operator_deployment",
            "task_execution",
            "web_workload",
            "api_workload",
            "ml_workload",
            "scheduler",
            "codebuild_image",
            "codebuild_destroy",
            "destroy",
        }
        if set(self.roles) != required_roles:
            raise LifecycleError("Lifecycle role inventory is incomplete.")
        required_projects = {"image", "destroy"}
        if set(self.projects) != required_projects:
            raise LifecycleError("Lifecycle project inventory is incomplete.")
        if set(self.ecr_repository_urls) != {"web", "api", "ml"}:
            raise LifecycleError("Lifecycle ECR inventory is incomplete.")
        if CONFIG_KEY_PATTERN.fullmatch(self.configuration_key) is None:
            raise LifecycleError("Lifecycle configuration key is invalid.")

    @property
    def configuration_key(self) -> str:
        return f"{self.control_prefix}/configuration.json"

    @property
    def lease_key(self) -> str:
        return f"{self.control_prefix}/lease.json"

    @property
    def secret_key(self) -> str:
        return f"{self.control_prefix}/synthetic-reviewer.json"

    @property
    def schedule_name(self) -> str:
        return f"{self.name_prefix}-{self.environment}-destroy"

    @property
    def image_tag(self) -> str:
        return f"sha-{self.source_sha[:12]}"

    @property
    def ownership_tags(self) -> dict[str, str]:
        return {
            "PortfolioEnvironment": self.environment,
            "PortfolioManaged": "true",
            "PortfolioPersistent": "false",
            "PortfolioRepository": self.repository_identity,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "accountId": self.account_id,
            "partition": self.partition,
            "region": self.region,
            "availabilityZones": list(self.availability_zones),
            "namePrefix": self.name_prefix,
            "environment": self.environment,
            "repositoryIdentity": self.repository_identity,
            "repositoryUrl": self.repository_url,
            "sourceSha": self.source_sha,
            "stateBucket": self.state_bucket,
            "stateKey": self.state_key,
            "controlPrefix": self.control_prefix,
            "sourceUserName": self.source_user_name,
            "roles": dict(self.roles),
            "projects": dict(self.projects),
            "ecrRepositoryUrls": dict(self.ecr_repository_urls),
            "vpcCidr": self.vpc_cidr,
            "rdsInstanceClass": self.rds_instance_class,
            "mqInstanceType": self.mq_instance_type,
            "logRetentionDays": self.log_retention_days,
            "objectExpirationDays": self.object_expiration_days,
            "reviewerGroupName": self.reviewer_group_name,
            "oidcApiAudience": self.oidc_api_audience,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> LifecycleConfig:
        if value.get("schemaVersion") != SCHEMA_VERSION:
            raise LifecycleError("Unsupported lifecycle configuration schema.")
        zones = value.get("availabilityZones")
        roles = value.get("roles")
        projects = value.get("projects")
        repositories = value.get("ecrRepositoryUrls")
        if not isinstance(zones, list) or len(zones) != 2:
            raise LifecycleError("Lifecycle availability-zone inventory is invalid.")
        if not all(isinstance(item, str) for item in zones):
            raise LifecycleError("Lifecycle availability zones must be strings.")
        for label, candidate in (
            ("roles", roles),
            ("projects", projects),
            ("ecrRepositoryUrls", repositories),
        ):
            if not isinstance(candidate, dict) or not all(
                isinstance(key, str) and isinstance(item, str)
                for key, item in candidate.items()
            ):
                raise LifecycleError(f"Lifecycle {label} inventory is invalid.")
        return cls(
            account_id=str(value.get("accountId", "")),
            partition=str(value.get("partition", "")),
            region=str(value.get("region", "")),
            availability_zones=(zones[0], zones[1]),
            name_prefix=str(value.get("namePrefix", "")),
            environment=str(value.get("environment", "")),
            repository_identity=str(value.get("repositoryIdentity", "")),
            repository_url=str(value.get("repositoryUrl", "")),
            source_sha=str(value.get("sourceSha", "")),
            state_bucket=str(value.get("stateBucket", "")),
            state_key=str(value.get("stateKey", "")),
            control_prefix=str(value.get("controlPrefix", "")),
            source_user_name=str(value.get("sourceUserName", "")),
            roles=roles,
            projects=projects,
            ecr_repository_urls=repositories,
            vpc_cidr=str(value.get("vpcCidr", "10.42.0.0/16")),
            rds_instance_class=str(value.get("rdsInstanceClass", "db.t4g.micro")),
            mq_instance_type=str(value.get("mqInstanceType", "mq.m7g.large")),
            log_retention_days=int(value.get("logRetentionDays", 3)),
            object_expiration_days=int(value.get("objectExpirationDays", 2)),
            reviewer_group_name=str(
                value.get("reviewerGroupName", "reactorfront-reviewers")
            ),
            oidc_api_audience=str(
                value.get("oidcApiAudience", "https://api.reactorfront.invalid/api")
            ),
        )


@dataclass
class LifecycleState:
    deployment_id: str
    config_digest: str
    phase: Phase = Phase.CONFIGURED
    revision: int = 0
    created_at: str = field(default_factory=lambda: isoformat(utc_now()))
    updated_at: str = field(default_factory=lambda: isoformat(utc_now()))
    images: dict[str, str] = field(default_factory=dict)
    plan: dict[str, object] = field(default_factory=dict)
    fallback: dict[str, object] = field(default_factory=dict)
    checkpoints: dict[str, object] = field(default_factory=dict)
    last_failure: dict[str, str] | None = None

    def transition(
        self,
        target: Phase,
        *,
        now: datetime | None = None,
        checkpoint: Mapping[str, object] | None = None,
    ) -> None:
        instant = now or utc_now()
        if target == self.phase:
            if checkpoint:
                self.checkpoints.update(checkpoint)
            self.updated_at = isoformat(instant)
            return
        if target == Phase.FAILED:
            raise LifecycleError("Use record_failure to enter the failed phase.")
        if target == Phase.DESTROYING:
            if self.phase in {Phase.CONFIGURED, Phase.ZERO_RESIDUE}:
                raise LifecycleError(
                    "Destroy cannot start before a remote lifecycle exists."
                )
        elif self.phase == Phase.FAILED:
            raise LifecycleError(
                "A failed lifecycle must resume or destroy explicitly."
            )
        elif PHASE_INDEX[target] != PHASE_INDEX[self.phase] + 1:
            raise LifecycleError(
                f"Invalid lifecycle transition: {self.phase.value} -> {target.value}."
            )
        self.phase = target
        self.revision += 1
        self.updated_at = isoformat(instant)
        self.last_failure = None
        if checkpoint:
            self.checkpoints.update(checkpoint)

    def record_failure(self, operation: str, *, now: datetime | None = None) -> None:
        if not operation or any(character.isspace() for character in operation):
            raise LifecycleError("Failure operation must be a stable token.")
        previous = self.phase.value
        self.phase = Phase.FAILED
        self.revision += 1
        self.updated_at = isoformat(now or utc_now())
        self.last_failure = {"operation": operation, "fromPhase": previous}

    def resume(self, target: Phase, *, now: datetime | None = None) -> None:
        if self.phase != Phase.FAILED or self.last_failure is None:
            raise LifecycleError("Only a recorded failure can be resumed.")
        expected = Phase(self.last_failure["fromPhase"])
        if target != expected:
            raise LifecycleError(
                "Resume target must match the failed operation boundary."
            )
        self.phase = target
        self.revision += 1
        self.updated_at = isoformat(now or utc_now())
        self.last_failure = None

    def set_images(self, images: Mapping[str, str]) -> None:
        if set(images) != {"web", "api", "ml"} or any(
            DIGEST_PATTERN.fullmatch(value) is None for value in images.values()
        ):
            raise LifecycleError(
                "Image proof requires exact Web/API/ML SHA-256 digests."
            )
        self.images = dict(images)

    def set_fallback(
        self,
        *,
        schedule_name: str,
        registered_at: datetime,
        expires_at: datetime,
    ) -> None:
        if expires_at <= registered_at:
            raise LifecycleError("Fallback expiry must be after registration.")
        if expires_at > registered_at + timedelta(minutes=MAX_TTL_MINUTES):
            raise LifecycleError("Fallback exceeds the accepted two-hour maximum.")
        if expires_at < registered_at + timedelta(minutes=MIN_TTL_MINUTES):
            raise LifecycleError(
                "Fallback is too short for a safe construction attempt."
            )
        self.fallback = {
            "scheduleName": schedule_name,
            "registeredAt": isoformat(registered_at),
            "expiresAt": isoformat(expires_at),
            "verified": True,
        }

    def extend_fallback(
        self, new_expiry: datetime, *, now: datetime | None = None
    ) -> None:
        if not self.fallback.get("verified"):
            raise LifecycleError("An active verified fallback is required.")
        registered_at = parse_time(str(self.fallback["registeredAt"]))
        current_expiry = parse_time(str(self.fallback["expiresAt"]))
        instant = now or utc_now()
        if current_expiry <= instant:
            raise LifecycleError("An expired fallback cannot be extended.")
        if new_expiry <= current_expiry or new_expiry <= instant:
            raise LifecycleError("Extend must move an active fallback later.")
        if new_expiry > registered_at + timedelta(minutes=MAX_TTL_MINUTES):
            raise LifecycleError("Extend exceeds the accepted two-hour maximum.")
        self.fallback["expiresAt"] = isoformat(new_expiry)

    def to_dict(self, config: LifecycleConfig) -> dict[str, object]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "deploymentId": self.deployment_id,
            "configDigest": self.config_digest,
            "configuration": config.to_dict(),
            "phase": self.phase.value,
            "revision": self.revision,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "images": dict(self.images),
            "plan": dict(self.plan),
            "fallback": dict(self.fallback),
            "checkpoints": dict(self.checkpoints),
            "lastFailure": self.last_failure,
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> tuple[LifecycleConfig, LifecycleState]:
        config_value = value.get("configuration")
        if not isinstance(config_value, dict):
            raise LifecycleError("Remote lifecycle configuration is missing.")
        config = LifecycleConfig.from_dict(config_value)
        config_digest = str(value.get("configDigest", ""))
        if config_digest != sha256_json(config.to_dict()):
            raise LifecycleError("Remote lifecycle configuration digest drifted.")
        try:
            phase = Phase(str(value.get("phase", "")))
            revision = int(value.get("revision", 0))
        except (TypeError, ValueError) as error:
            raise LifecycleError(
                "Remote lifecycle phase or revision is invalid."
            ) from error
        if revision < 0:
            raise LifecycleError("Remote lifecycle revision cannot be negative.")
        mappings: dict[str, dict[str, Any]] = {}
        for key in ("images", "plan", "fallback", "checkpoints"):
            candidate = value.get(key, {})
            if not isinstance(candidate, dict):
                raise LifecycleError(f"Remote lifecycle {key} must be an object.")
            mappings[key] = dict(candidate)
        last_failure = value.get("lastFailure")
        if last_failure is not None:
            if (
                not isinstance(last_failure, dict)
                or not isinstance(last_failure.get("operation"), str)
                or not isinstance(last_failure.get("fromPhase"), str)
            ):
                raise LifecycleError("Remote lifecycle failure checkpoint is invalid.")
            try:
                Phase(last_failure["fromPhase"])
            except ValueError as error:
                raise LifecycleError(
                    "Remote lifecycle failure origin is invalid."
                ) from error
        if (phase == Phase.FAILED) != (last_failure is not None):
            raise LifecycleError("Remote lifecycle failure phase is inconsistent.")
        state = cls(
            deployment_id=str(value.get("deploymentId", "")),
            config_digest=config_digest,
            phase=phase,
            revision=revision,
            created_at=str(value.get("createdAt", "")),
            updated_at=str(value.get("updatedAt", "")),
            images=mappings["images"],
            plan=mappings["plan"],
            fallback=mappings["fallback"],
            checkpoints=mappings["checkpoints"],
            last_failure=last_failure,
        )
        if SHA_PATTERN.fullmatch(state.deployment_id) is None:
            raise LifecycleError("Remote deployment identity is invalid.")
        parse_time(state.created_at)
        parse_time(state.updated_at)
        if state.images:
            state.set_images(state.images)
        if state.fallback:
            if (
                state.fallback.get("scheduleName") != config.schedule_name
                or state.fallback.get("verified") is not True
            ):
                raise LifecycleError("Remote lifecycle fallback identity drifted.")
            registered = parse_time(str(state.fallback.get("registeredAt", "")))
            expires = parse_time(str(state.fallback.get("expiresAt", "")))
            state.set_fallback(
                schedule_name=config.schedule_name,
                registered_at=registered,
                expires_at=expires,
            )
        return config, state


SENSITIVE_KEY = re.compile(
    r"(?i)(access.?key|secret|session.?token|password|authorization|cookie|credential|account.?id|source.?text|private.?path)"
)
AWS_ACCOUNT_VALUE = re.compile(r"(?<![0-9])[0-9]{12}(?![0-9])")
AWS_KEY_VALUE = re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}")
PRIVATE_PATH_VALUE = re.compile(r"(?i)(?:[A-Z]:\\|/home/|/Users/)[^\s\"']+")


def assert_public_safe(value: object, *, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if SENSITIVE_KEY.search(str(key)):
                raise LifecycleError(
                    f"Sanitized output contains a sensitive field at {path}."
                )
            assert_public_safe(item, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            assert_public_safe(item, path=f"{path}[{index}]")
        return
    if isinstance(value, str) and (
        AWS_ACCOUNT_VALUE.search(value)
        or AWS_KEY_VALUE.search(value)
        or PRIVATE_PATH_VALUE.search(value)
    ):
        raise LifecycleError(f"Sanitized output contains a private value at {path}.")


def sanitized_status(state: LifecycleState | None) -> dict[str, object]:
    if state is None:
        result: dict[str, object] = {
            "schemaVersion": SCHEMA_VERSION,
            "phase": "not-attempted",
            "remoteCheckpoint": False,
            "fallback": "unknown",
            "residue": "unknown",
        }
    else:
        result = {
            "schemaVersion": SCHEMA_VERSION,
            "phase": state.phase.value,
            "remoteCheckpoint": True,
            "sourceRevision": state.deployment_id,
            "images": len(state.images),
            "fallback": (
                "verified" if state.fallback.get("verified") is True else "missing"
            ),
            "migration": state.checkpoints.get("migration", "not-attempted"),
            "seed": state.checkpoints.get("seed", "not-attempted"),
            "smoke": state.checkpoints.get("smoke", "not-attempted"),
            "residue": state.checkpoints.get("residue", "unknown"),
            "failure": (
                state.last_failure.get("operation") if state.last_failure else None
            ),
        }
    assert_public_safe(result)
    return result
