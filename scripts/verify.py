from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from pathlib import PurePosixPath
from uuid import UUID


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PROJECT_NAME = "reactorfront-portfolio"
ARTIFACT_DIRECTORY = REPOSITORY_ROOT / "artifacts" / "verification"

VERIFICATION_GROUPS = (
    "contracts",
    "docs",
    "compose",
    "web-static",
    "api-static",
    "ml-static",
    "web-runtime",
    "api-runtime",
    "ml-runtime",
)
ALL_GROUPS = frozenset(VERIFICATION_GROUPS)
STATIC_GROUPS = frozenset(VERIFICATION_GROUPS[:6])
RUNTIME_GROUPS = frozenset(VERIFICATION_GROUPS[6:])
DOCKER_GROUPS = frozenset({"compose"}) | RUNTIME_GROUPS
EXPECTED_COMPOSE_SERVICES = frozenset(
    {
        "postgres",
        "minio",
        "rabbitmq",
        "api",
        "api-outbox",
        "api-events",
        "ml-worker",
        "web",
    }
)
GROUP_DEPENDENCIES = {
    "web-runtime": frozenset({"compose", "web-static"}),
    "api-runtime": frozenset({"compose", "api-static"}),
    "ml-runtime": frozenset({"compose", "ml-static"}),
}


class VerificationPlan:
    def __init__(
        self,
        *,
        groups: frozenset[str],
        changed_files: tuple[str, ...],
        reason: str,
        base: str | None = None,
        carried_groups: frozenset[str] = frozenset(),
    ) -> None:
        if not groups <= ALL_GROUPS or not carried_groups <= ALL_GROUPS:
            raise ValueError("Verification plan contains an unknown group.")
        if groups & carried_groups:
            raise ValueError("Executed and carried groups must be disjoint.")
        self.groups = groups
        self.carried_groups = carried_groups
        self.changed_files = changed_files
        self.reason = reason
        self.base = base

    @property
    def skipped_groups(self) -> frozenset[str]:
        return ALL_GROUPS - self.groups - self.carried_groups


def plan_with_baseline_evidence(
    plan: VerificationPlan,
    *,
    baseline_proven: bool,
    baseline_skipped_groups: frozenset[str] = frozenset(),
) -> VerificationPlan:
    if not baseline_skipped_groups <= ALL_GROUPS:
        raise ValueError("Baseline evidence contains an unknown group.")
    if baseline_skipped_groups and not baseline_proven:
        raise ValueError("Baseline skips require proven baseline evidence.")
    carried = (
        ALL_GROUPS - plan.groups - baseline_skipped_groups
        if baseline_proven
        else frozenset()
    )
    return VerificationPlan(
        groups=plan.groups,
        carried_groups=carried,
        changed_files=plan.changed_files,
        reason=plan.reason,
        base=plan.base,
    )


def move_groups_to_skipped(
    plan: VerificationPlan, groups: frozenset[str]
) -> VerificationPlan:
    carried = groups & plan.carried_groups
    if carried:
        raise RuntimeError(
            "Cannot relabel carried baseline evidence as skipped: "
            f"{', '.join(ordered_groups(carried))}"
        )
    return VerificationPlan(
        groups=plan.groups - groups,
        carried_groups=plan.carried_groups,
        changed_files=plan.changed_files,
        reason=plan.reason,
        base=plan.base,
    )


def apply_skip_lineage(
    plan: VerificationPlan,
    *,
    baseline_skipped_groups: frozenset[str],
    current_skipped_groups: frozenset[str],
) -> VerificationPlan:
    inherited = baseline_skipped_groups - plan.groups
    missing = inherited - current_skipped_groups
    if missing:
        raise RuntimeError(
            "Current Verification-Skip omits inherited skipped groups that are "
            f"not selected for execution: {', '.join(ordered_groups(missing))}"
        )
    if not current_skipped_groups:
        return plan
    return move_groups_to_skipped(plan, current_skipped_groups)


def expand_group_dependencies(groups: set[str] | frozenset[str]) -> frozenset[str]:
    expanded = set(groups)
    for group in tuple(expanded):
        expanded.update(GROUP_DEPENDENCIES.get(group, ()))
    return frozenset(expanded)


def ordered_groups(groups: set[str] | frozenset[str]) -> tuple[str, ...]:
    return tuple(group for group in VERIFICATION_GROUPS if group in groups)


def groups_for_changed_path(raw_path: str) -> frozenset[str] | None:
    normalized = raw_path.strip().replace("\\", "/")
    path = PurePosixPath(normalized)
    parts = path.parts
    if not normalized or path.is_absolute() or ".." in parts:
        return None

    if path.suffix.lower() == ".md":
        return frozenset({"docs"})

    if normalized == "scripts/verify.py" or normalized.startswith(".github/workflows/"):
        return ALL_GROUPS

    if normalized.startswith("packages/contracts/"):
        return ALL_GROUPS

    if normalized in {
        ".node-version",
        ".python-version",
        "package.json",
        "pnpm-lock.yaml",
        "pnpm-workspace.yaml",
        "pyproject.toml",
    }:
        return ALL_GROUPS

    if normalized == "compose.yaml":
        return ALL_GROUPS

    if normalized == "scripts/check_docs.py":
        return frozenset({"docs", "api-static"})

    api_runtime_helpers = {
        "scripts/prepare_integration.py",
        "scripts/verify_outbox_runtime.py",
        "scripts/verify_result_consumer_runtime.py",
    }
    if normalized in api_runtime_helpers:
        return expand_group_dependencies({"api-runtime"})

    if normalized in {
        "scripts/pdf_fixture.py",
        "scripts/verify_ml_runtime.py",
    }:
        return expand_group_dependencies({"ml-runtime"})

    if normalized == "scripts/verify_ml_model.py":
        return frozenset({"ml-static"})

    if normalized == "scripts/check_ml_compose_boundary.py":
        return frozenset({"compose", "ml-static"})

    if normalized.startswith("apps/web/"):
        groups = {"web-static"}
        if normalized in {
            "apps/web/next.config.ts",
            "apps/web/package.json",
            "apps/web/src/app/health/route.ts",
        }:
            groups.add("web-runtime")
        return expand_group_dependencies(groups)

    if normalized.startswith("apps/api/tests/"):
        if normalized == "apps/api/tests/test_integration.py":
            return expand_group_dependencies({"api-runtime"})
        return frozenset({"api-static"})

    if normalized.startswith("apps/api/"):
        return expand_group_dependencies({"api-runtime"})

    if normalized.startswith("apps/ml/tests/"):
        return frozenset({"ml-static"})

    if normalized.startswith("apps/ml/"):
        return expand_group_dependencies({"ml-runtime"})

    if normalized.startswith("infra/docker/web/"):
        return expand_group_dependencies({"web-runtime"})

    if normalized.startswith("infra/docker/api/"):
        return expand_group_dependencies({"api-runtime"})

    if normalized.startswith("infra/docker/ml/"):
        return expand_group_dependencies({"ml-runtime"})

    if normalized.startswith("infra/docker/"):
        return ALL_GROUPS

    if normalized.startswith(("tests/integration/", "tests/e2e/")):
        return ALL_GROUPS

    return None


def plan_for_paths(
    changed_files: list[str] | tuple[str, ...],
    *,
    base: str | None = None,
    baseline_proven: bool = False,
    baseline_skipped_groups: frozenset[str] = frozenset(),
) -> VerificationPlan:
    normalized = tuple(dict.fromkeys(path.replace("\\", "/") for path in changed_files))
    if not normalized:
        return plan_with_baseline_evidence(
            VerificationPlan(
                groups=ALL_GROUPS,
                changed_files=normalized,
                reason="No changed path was available; full verification is required.",
                base=base,
            ),
            baseline_proven=baseline_proven,
            baseline_skipped_groups=baseline_skipped_groups,
        )

    selected: set[str] = set()
    for path in normalized:
        path_groups = groups_for_changed_path(path)
        if path_groups is None or path_groups == ALL_GROUPS:
            return plan_with_baseline_evidence(
                VerificationPlan(
                    groups=ALL_GROUPS,
                    changed_files=normalized,
                    reason=(
                        f"{path} is cross-cutting or unmapped; "
                        "fail closed to full verification."
                    ),
                    base=base,
                ),
                baseline_proven=baseline_proven,
                baseline_skipped_groups=baseline_skipped_groups,
            )
        selected.update(path_groups)

    return plan_with_baseline_evidence(
        VerificationPlan(
            groups=expand_group_dependencies(selected),
            changed_files=normalized,
            reason="Selected from the changed path boundaries.",
            base=base,
        ),
        baseline_proven=baseline_proven,
        baseline_skipped_groups=baseline_skipped_groups,
    )


def paths_from_name_status(output: bytes) -> list[str]:
    fields = [field for field in output.split(b"\0") if field]
    paths: list[str] = []
    index = 0
    while index < len(fields):
        status = os.fsdecode(fields[index])
        index += 1
        path_count = 2 if status.startswith(("R", "C")) else 1
        if (
            not status
            or status[0] not in "ACDMRTUXB"
            or index + path_count > len(fields)
        ):
            raise ValueError("Git returned malformed --name-status -z output.")
        for field in fields[index : index + path_count]:
            paths.append(os.fsdecode(field))
        index += path_count
    return paths


def changed_files_from_git(
    *, base: str | None = None, staged: bool = False
) -> list[str]:
    command = [
        "git",
        "diff",
        "--name-status",
        "--find-renames",
        "--find-copies",
        "--find-copies-harder",
        "--diff-filter=ACDMRTUXB",
        "-z",
    ]
    if staged:
        command.append("--cached")
    elif base is not None:
        command.append(f"{base}...HEAD")
    else:
        raise ValueError("A Git base or --staged is required.")

    result = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    return paths_from_name_status(result.stdout)


def plan_from_git(
    *,
    base: str | None = None,
    staged: bool = False,
    baseline_proven: bool = False,
    baseline_skipped_groups: frozenset[str] = frozenset(),
) -> VerificationPlan:
    try:
        changed_files = changed_files_from_git(base=base, staged=staged)
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        return VerificationPlan(
            groups=ALL_GROUPS,
            changed_files=(),
            reason=f"Git diff was unavailable ({error}); fail closed to full verification.",
            base=base,
        )
    return plan_for_paths(
        changed_files,
        base=base,
        baseline_proven=baseline_proven,
        baseline_skipped_groups=baseline_skipped_groups,
    )


def test_file_inventory() -> tuple[tuple[str, str], ...]:
    inventory: list[tuple[str, str]] = []
    web_root = REPOSITORY_ROOT / "apps" / "web"
    for directory, child_directories, filenames in os.walk(web_root):
        child_directories[:] = [
            name for name in child_directories if name not in {"node_modules", ".next"}
        ]
        for filename in filenames:
            if ".test." in filename or ".spec." in filename:
                path = Path(directory) / filename
                relative = path.relative_to(REPOSITORY_ROOT)
                inventory.append(("web-static", relative.as_posix()))
    for service, group in (("api", "api-static"), ("ml", "ml-static")):
        for path in (REPOSITORY_ROOT / "apps" / service / "tests").glob("test_*.py"):
            inventory.append((group, path.relative_to(REPOSITORY_ROOT).as_posix()))
    for path in (REPOSITORY_ROOT / "tests" / "e2e").glob("*.spec.ts"):
        inventory.append(("web-runtime", path.relative_to(REPOSITORY_ROOT).as_posix()))
    return tuple(sorted(inventory))


def selected_test_files(groups: frozenset[str]) -> tuple[str, ...]:
    selected_owners = groups & {
        "web-static",
        "api-static",
        "ml-static",
        "web-runtime",
    }
    return tuple(
        path for owner, path in test_file_inventory() if owner in selected_owners
    )


def plan_lines(plan: VerificationPlan) -> list[str]:
    selected = ordered_groups(plan.groups)
    carried = ordered_groups(plan.carried_groups)
    skipped = ordered_groups(plan.skipped_groups)
    inventory = test_file_inventory()
    tests = selected_test_files(plan.groups)
    lines = [
        f"Verification groups: {len(selected)}/{len(VERIFICATION_GROUPS)} selected",
        f"Test files: {len(tests)}/{len(inventory)} selected",
        f"Selected: {', '.join(selected) or 'none'}",
        f"Executed on success: {', '.join(selected) or 'none'}",
        f"Carried from successful baseline: {', '.join(carried) or 'none'}",
        f"Skipped without evidence: {', '.join(skipped) or 'none'}",
        f"Reason: {plan.reason}",
    ]
    if plan.base is not None:
        lines.append(f"Base: {plan.base}")
    lines.append(f"Changed files: {len(plan.changed_files)}")
    return lines


def write_plan_outputs(plan: VerificationPlan, path: Path) -> None:
    selected = set(plan.groups)
    values = {
        "groups": ",".join(ordered_groups(plan.groups)),
        "executed_groups": ",".join(ordered_groups(plan.groups)),
        "carried_groups": ",".join(ordered_groups(plan.carried_groups)),
        "skipped_groups": ",".join(ordered_groups(plan.skipped_groups)),
        "docker_groups": ",".join(ordered_groups(plan.groups & DOCKER_GROUPS)),
        "has_execution": bool(selected),
        "needs_node": bool(selected & {"contracts", "web-static"}),
        "needs_python": bool(selected),
        "needs_uv": bool(selected & {"api-static", "ml-static"})
        or bool(selected & RUNTIME_GROUPS),
        "needs_api": "api-static" in selected or bool(selected & RUNTIME_GROUPS),
        "needs_ml": bool(selected & {"ml-static", "ml-runtime"}),
        "needs_docker": bool(selected & DOCKER_GROUPS),
        "needs_runtime": bool(selected & RUNTIME_GROUPS),
        "needs_e2e": RUNTIME_GROUPS <= selected,
    }
    with path.open("a", encoding="utf-8") as output:
        for key, value in values.items():
            rendered = str(value).lower() if isinstance(value, bool) else value
            output.write(f"{key}={rendered}\n")


def write_plan_summary(plan: VerificationPlan, path: Path) -> None:
    with path.open("a", encoding="utf-8") as summary:
        summary.write("## Selective verification plan\n\n")
        for line in plan_lines(plan):
            summary.write(f"- {line}\n")


def require_command(command: str) -> str:
    resolved = shutil.which(command)
    if resolved is None:
        raise RuntimeError(f"Required command is not available: {command}")
    return resolved


def run(
    label: str, command: list[str], *, check: bool = True
) -> subprocess.CompletedProcess[bytes]:
    print(f"\n==> {label}", flush=True)
    return subprocess.run(command, cwd=REPOSITORY_ROOT, check=check)


def compose_command(docker: str, *arguments: str) -> list[str]:
    return [docker, "compose", "-p", COMPOSE_PROJECT_NAME, *arguments]


def static_checks(
    *,
    pnpm: str,
    uv: str,
    docker: str,
    groups: frozenset[str] = STATIC_GROUPS,
) -> list[tuple[str, list[str]]]:
    checks = [
        ("Validate canonical contracts", [pnpm, "contracts:check"]),
        ("Validate documentation links", [sys.executable, "scripts/check_docs.py"]),
        (
            "Validate the isolated Compose definition",
            compose_command(docker, "config", "--quiet"),
        ),
        (
            "Lint Web source and tests",
            [pnpm, "--filter", "@reactorfront/web", "lint"],
        ),
        (
            "Check Web formatting",
            [pnpm, "--filter", "@reactorfront/web", "format:check"],
        ),
        (
            "Type-check Web source",
            [pnpm, "--filter", "@reactorfront/web", "typecheck"],
        ),
        (
            "Run Web branch-aware tests",
            [pnpm, "--filter", "@reactorfront/web", "test:coverage"],
        ),
        (
            "Build the production Web application",
            [pnpm, "--filter", "@reactorfront/web", "build"],
        ),
        (
            "Audit the pinned Web production dependency set",
            [
                pnpm,
                "audit",
                "--prod",
                "--audit-level",
                "moderate",
            ],
        ),
        (
            "Check browser E2E formatting",
            [pnpm, "e2e:format:check"],
        ),
        (
            "Type-check browser E2E source",
            [pnpm, "e2e:typecheck"],
        ),
        (
            "Lint API source and tests",
            [
                uv,
                "run",
                "--project",
                "apps/api",
                "ruff",
                "check",
                "apps/api/src",
                "apps/api/alembic",
                "apps/api/tests",
                "scripts/verify.py",
                "scripts/prepare_integration.py",
                "scripts/verify_outbox_runtime.py",
                "scripts/verify_result_consumer_runtime.py",
                "scripts/check_docs.py",
            ],
        ),
        (
            "Check API formatting",
            [
                uv,
                "run",
                "--project",
                "apps/api",
                "ruff",
                "format",
                "--check",
                "apps/api/src",
                "apps/api/alembic",
                "apps/api/tests",
                "scripts/verify.py",
                "scripts/prepare_integration.py",
                "scripts/verify_outbox_runtime.py",
                "scripts/verify_result_consumer_runtime.py",
                "scripts/check_docs.py",
            ],
        ),
        (
            "Type-check API source",
            [
                uv,
                "run",
                "--project",
                "apps/api",
                "mypy",
                "--config-file",
                "apps/api/pyproject.toml",
                "apps/api/src",
            ],
        ),
        (
            "Audit the installed pinned API dependency set",
            [
                uv,
                "run",
                "--project",
                "apps/api",
                "pip-audit",
                "--local",
                "--skip-editable",
                "--progress-spinner=off",
            ],
        ),
        (
            "Lint ML source, tests, and verification helpers",
            [
                uv,
                "run",
                "--project",
                "apps/ml",
                "ruff",
                "check",
                "apps/ml/src",
                "apps/ml/tests",
                "scripts/pdf_fixture.py",
                "scripts/check_ml_compose_boundary.py",
                "scripts/verify_ml_model.py",
                "scripts/verify_ml_runtime.py",
            ],
        ),
        (
            "Check ML formatting",
            [
                uv,
                "run",
                "--project",
                "apps/ml",
                "ruff",
                "format",
                "--check",
                "apps/ml/src",
                "apps/ml/tests",
                "scripts/pdf_fixture.py",
                "scripts/check_ml_compose_boundary.py",
                "scripts/verify_ml_model.py",
                "scripts/verify_ml_runtime.py",
            ],
        ),
        (
            "Type-check ML source",
            [
                uv,
                "run",
                "--project",
                "apps/ml",
                "mypy",
                "--config-file",
                "apps/ml/pyproject.toml",
                "apps/ml/src",
            ],
        ),
        (
            "Audit the installed pinned ML dependency set",
            [
                uv,
                "run",
                "--project",
                "apps/ml",
                "pip-audit",
                "--local",
                "--skip-editable",
                "--progress-spinner=off",
            ],
        ),
        (
            "Audit the normalized PyTorch CPU release identity",
            [
                uv,
                "run",
                "--project",
                "apps/ml",
                "pip-audit",
                "--requirement",
                "apps/ml/audit-requirements.txt",
                "--disable-pip",
                "--progress-spinner=off",
            ],
        ),
        (
            "Prove deterministic ML model generation",
            [
                uv,
                "run",
                "--project",
                "apps/ml",
                "python",
                "scripts/verify_ml_model.py",
            ],
        ),
        (
            "Validate deployable Compose boundaries",
            [sys.executable, "scripts/check_ml_compose_boundary.py"],
        ),
    ]
    check_groups = {
        "Validate canonical contracts": "contracts",
        "Validate documentation links": "docs",
        "Validate the isolated Compose definition": "compose",
        "Lint Web source and tests": "web-static",
        "Check Web formatting": "web-static",
        "Type-check Web source": "web-static",
        "Run Web branch-aware tests": "web-static",
        "Build the production Web application": "web-static",
        "Audit the pinned Web production dependency set": "web-static",
        "Check browser E2E formatting": "web-static",
        "Type-check browser E2E source": "web-static",
        "Lint API source and tests": "api-static",
        "Check API formatting": "api-static",
        "Type-check API source": "api-static",
        "Audit the installed pinned API dependency set": "api-static",
        "Lint ML source, tests, and verification helpers": "ml-static",
        "Check ML formatting": "ml-static",
        "Type-check ML source": "ml-static",
        "Audit the installed pinned ML dependency set": "ml-static",
        "Audit the normalized PyTorch CPU release identity": "ml-static",
        "Prove deterministic ML model generation": "ml-static",
        "Validate deployable Compose boundaries": "compose",
    }
    filtered = [check for check in checks if check_groups[check[0]] in groups]
    if "api-static" in groups:
        filtered.append(
            ("Run API unit tests", pytest_command(uv, include_integration=False))
        )
    if "ml-static" in groups:
        filtered.append(("Run ML unit tests", pytest_ml_command(uv)))
    return filtered


def pytest_command(uv: str, *, include_integration: bool) -> list[str]:
    command = [
        uv,
        "run",
        "--project",
        "apps/api",
        "pytest",
        "apps/api/tests",
    ]
    if not include_integration:
        command.extend(["-m", "not integration"])
    command.extend(
        [
            "--cov=reactorfront_api",
            "--cov-branch",
            "--cov-report=term-missing",
            "--cov-report=xml:artifacts/verification/api-coverage.xml",
            "--cov-fail-under=90",
            "--junitxml=artifacts/verification/api-pytest.xml",
        ]
    )
    return command


def pytest_ml_command(uv: str) -> list[str]:
    return [
        uv,
        "run",
        "--project",
        "apps/ml",
        "pytest",
        "apps/ml/tests",
        "--cov=reactorfront_ml",
        "--cov-branch",
        "--cov-report=term-missing",
        "--cov-report=xml:artifacts/verification/ml-coverage.xml",
        "--cov-fail-under=90",
        "--junitxml=artifacts/verification/ml-pytest.xml",
    ]


def prove_complete_compose_readiness(docker: str) -> None:
    result = subprocess.run(
        compose_command(docker, "ps", "--services", "--status", "running"),
        cwd=REPOSITORY_ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    running = frozenset(result.stdout.decode("utf-8").splitlines())
    if running != EXPECTED_COMPOSE_SERVICES:
        missing = EXPECTED_COMPOSE_SERVICES - running
        unexpected = running - EXPECTED_COMPOSE_SERVICES
        raise RuntimeError(
            "Complete Compose readiness did not expose the exact eight services; "
            f"missing={','.join(sorted(missing)) or 'none'}, "
            f"unexpected={','.join(sorted(unexpected)) or 'none'}."
        )
    capture_runtime_diagnostic(
        label="Record complete eight-service readiness",
        command=compose_command(docker, "ps", "--all"),
        filename="compose-ready.txt",
    )


def _e2e_upload_correlation(payload: object, phase: str) -> str:
    if not isinstance(payload, dict):
        raise RuntimeError("Browser E2E evidence is not a JSON object.")
    phase_evidence = payload.get(phase)
    if not isinstance(phase_evidence, dict):
        raise RuntimeError(f"Browser E2E evidence is missing {phase}.")
    correlation = phase_evidence.get("uploadCorrelation")
    if not isinstance(correlation, dict):
        raise RuntimeError(
            f"Browser E2E evidence is missing {phase} upload correlation."
        )
    request_id = correlation.get("request")
    response_id = correlation.get("response")
    if not isinstance(request_id, str) or request_id != response_id:
        raise RuntimeError(f"Browser E2E {phase} correlation is inconsistent.")
    try:
        UUID(request_id)
    except ValueError as error:
        raise RuntimeError(f"Browser E2E {phase} correlation is not a UUID.") from error
    return request_id


def prove_e2e_correlation(docker: str) -> None:
    evidence_path = ARTIFACT_DIRECTORY / "e2e-result.json"
    try:
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("Browser E2E result evidence is unavailable.") from error
    correlations = {
        phase: _e2e_upload_correlation(payload, phase)
        for phase in ("completed", "failed")
    }
    proof: dict[str, dict[str, bool]] = {}
    for service in ("api-outbox", "ml-worker", "api-events"):
        result = subprocess.run(
            compose_command(docker, "logs", "--no-color", service),
            cwd=REPOSITORY_ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        output = result.stdout.decode("utf-8", errors="replace")
        observations = {
            phase: correlation in output for phase, correlation in correlations.items()
        }
        if not all(observations.values()):
            missing = [
                phase for phase, observed in observations.items() if not observed
            ]
            raise RuntimeError(
                f"{service} logs lack E2E correlation evidence for {', '.join(missing)}."
            )
        proof[service] = observations
    (ARTIFACT_DIRECTORY / "e2e-correlation-proof.json").write_text(
        json.dumps(proof, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("E2E correlations crossed api-outbox, ml-worker, and api-events.")


def run_runtime_checks(
    *, groups: frozenset[str], pnpm: str, uv: str, docker: str
) -> None:
    full_e2e = RUNTIME_GROUPS <= groups
    if full_e2e:
        run(
            "Build every source-owned Compose image with fresh bases",
            compose_command(docker, "build", "--pull"),
        )
    run(
        "Build and start isolated PostgreSQL, MinIO, and RabbitMQ",
        compose_command(
            docker,
            "up",
            "--detach",
            "--build",
            "--wait",
            "postgres",
            "minio",
            "rabbitmq",
        ),
    )
    run(
        "Create the deterministic integration bucket",
        [
            uv,
            "run",
            "--project",
            "apps/api",
            "python",
            "scripts/prepare_integration.py",
        ],
    )
    run(
        "Apply API database migrations",
        [
            uv,
            "run",
            "--project",
            "apps/api",
            "alembic",
            "-c",
            "apps/api/alembic.ini",
            "upgrade",
            "head",
        ],
    )
    run(
        "Check migration metadata drift",
        [
            uv,
            "run",
            "--project",
            "apps/api",
            "alembic",
            "-c",
            "apps/api/alembic.ini",
            "check",
        ],
    )
    run(
        "Build and start the migrated API container",
        compose_command(docker, "up", "--detach", "--build", "--wait", "api"),
    )
    if "web-runtime" in groups:
        run(
            "Build and start the source-owned Web container",
            compose_command(docker, "up", "--detach", "--build", "--wait", "web"),
        )
        run(
            "Prove the Web container is healthy and non-root",
            compose_command(
                docker,
                "exec",
                "-T",
                "web",
                "node",
                "-e",
                "if (process.getuid?.() === 0) process.exit(1); "
                "fetch('http://127.0.0.1:3000/health')"
                ".then((response) => { if (!response.ok) process.exit(1); })"
                ".catch(() => process.exit(1));",
            ),
        )
    if "api-runtime" in groups:
        run(
            "Run API unit and real-service integration tests",
            pytest_command(uv, include_integration=True),
        )
        run(
            "Prove outbox and RabbitMQ restart recovery",
            [
                uv,
                "run",
                "--project",
                "apps/api",
                "python",
                "scripts/verify_outbox_runtime.py",
            ],
        )
        run(
            "Prove API-owned result-event consumption and terminal persistence",
            [
                uv,
                "run",
                "--project",
                "apps/api",
                "python",
                "scripts/verify_result_consumer_runtime.py",
            ],
        )
    if "ml-runtime" in groups:
        run(
            "Prove the real ML worker and result-event boundary",
            [
                uv,
                "run",
                "--project",
                "apps/ml",
                "python",
                "scripts/verify_ml_runtime.py",
            ],
        )
    if full_e2e:
        run(
            "Start the complete eight-service Compose environment",
            compose_command(
                docker,
                "up",
                "--detach",
                "--wait",
                *sorted(EXPECTED_COMPOSE_SERVICES),
            ),
        )
        prove_complete_compose_readiness(docker)
        run(
            "Prove browser-to-ML-to-browser completed and failed workflows",
            [pnpm, "e2e:test"],
        )
        prove_e2e_correlation(docker)


def capture_runtime_diagnostic(
    *,
    label: str,
    command: list[str],
    filename: str,
) -> None:
    print(f"\n==> {label}", flush=True)
    result = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = result.stdout or b""
    sys.stdout.buffer.write(output)
    sys.stdout.flush()
    ARTIFACT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIRECTORY / filename).write_bytes(output)


def show_runtime_diagnostics(docker: str) -> None:
    capture_runtime_diagnostic(
        label="Show isolated Compose state",
        command=compose_command(docker, "ps", "--all"),
        filename="compose-ps.txt",
    )
    capture_runtime_diagnostic(
        label="Show isolated service logs",
        command=compose_command(
            docker,
            "logs",
            "--no-color",
            "--timestamps",
            "--tail",
            "500",
        ),
        filename="compose-logs.txt",
    )
    capture_runtime_diagnostic(
        label="Show ML worker dependency readiness",
        command=compose_command(
            docker,
            "exec",
            "-T",
            "ml-worker",
            "python",
            "-m",
            "reactorfront_ml.health",
            "--check",
        ),
        filename="ml-readiness.txt",
    )
    capture_runtime_diagnostic(
        label="Show API event-consumer dependency readiness",
        command=compose_command(
            docker,
            "exec",
            "-T",
            "api-events",
            "python",
            "-m",
            "reactorfront_api.events_main",
            "--check",
        ),
        filename="api-events-readiness.txt",
    )
    capture_runtime_diagnostic(
        label="Show Web process health",
        command=compose_command(
            docker,
            "exec",
            "-T",
            "web",
            "node",
            "-e",
            "fetch('http://127.0.0.1:3000/health')"
            ".then(async (response) => { console.log(await response.text()); "
            "if (!response.ok) process.exit(1); })"
            ".catch(() => process.exit(1));",
        ),
        filename="web-health.txt",
    )


def cleanup_runtime(docker: str) -> None:
    remove_volumes = os.environ.get("GITHUB_ACTIONS") == "true"
    scope = f"Compose project {COMPOSE_PROJECT_NAME}"
    if remove_volumes:
        scope += " including its three project-scoped data volumes"
    print(f"\n==> Cleanup target: {scope}", flush=True)
    arguments = ["down", "--remove-orphans"]
    if remove_volumes:
        arguments.append("--volumes")
    run("Stop the isolated runtime", compose_command(docker, *arguments))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run canonical repository verification."
    )
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="Skip container startup and real-service integration tests.",
    )
    parser.add_argument(
        "--groups",
        help="Run a comma-separated verification group selection.",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Print a verification plan without running checks.",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--base", help="Plan from the merge-base diff to HEAD.")
    source.add_argument(
        "--staged",
        action="store_true",
        help="Plan from the exact staged diff.",
    )
    source.add_argument(
        "--full",
        action="store_true",
        help="Select every verification group.",
    )
    source.add_argument(
        "--carry-all",
        action="store_true",
        help="Carry every group from a proven identical baseline.",
    )
    parser.add_argument(
        "--baseline-proven",
        action="store_true",
        help="Mark unselected groups as carried from a successful baseline.",
    )
    parser.add_argument(
        "--baseline-skipped-groups",
        help=(
            "Comma-separated groups skipped without evidence by the proven baseline; "
            "they remain skipped unless selected by the current delta."
        ),
    )
    parser.add_argument(
        "--carried-groups",
        help="Comma-separated unaffected groups carried into explicit-run evidence.",
    )
    parser.add_argument(
        "--skipped-groups",
        help="Comma-separated selected groups intentionally skipped without evidence.",
    )
    parser.add_argument(
        "--github-output",
        type=Path,
        help="Append machine-readable selection outputs for GitHub Actions.",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        help="Append the human-readable plan to a Markdown summary.",
    )
    return parser.parse_args()


def parse_group_selection(
    value: str, *, expand_dependencies: bool = True
) -> frozenset[str]:
    requested = {group.strip() for group in value.split(",") if group.strip()}
    unknown = requested - ALL_GROUPS
    if unknown:
        raise RuntimeError(f"Unknown verification groups: {', '.join(sorted(unknown))}")
    if not requested:
        raise RuntimeError("At least one verification group is required.")
    if expand_dependencies:
        return expand_group_dependencies(requested)
    return frozenset(requested)


def resolve_selection(args: argparse.Namespace) -> VerificationPlan:
    if args.baseline_skipped_groups and (
        args.groups or args.static_only or args.carry_all
    ):
        raise RuntimeError(
            "--baseline-skipped-groups is only valid with --base or --staged."
        )
    if args.groups:
        if args.skipped_groups:
            raise RuntimeError("--skipped-groups is only valid while planning.")
        carried = (
            parse_group_selection(args.carried_groups, expand_dependencies=False)
            if args.carried_groups
            else frozenset()
        )
        selected = parse_group_selection(args.groups)
        overlap = selected & carried
        if overlap:
            raise RuntimeError(
                "Executed and carried groups overlap: "
                f"{', '.join(ordered_groups(overlap))}"
            )
        return VerificationPlan(
            groups=selected,
            carried_groups=carried,
            changed_files=(),
            reason="Explicit verification group selection.",
        )
    if args.static_only:
        return VerificationPlan(
            groups=STATIC_GROUPS,
            changed_files=(),
            reason="Static-only verification requested.",
        )
    if args.carry_all:
        if not args.baseline_proven:
            raise RuntimeError("--carry-all requires --baseline-proven.")
        skipped = (
            parse_group_selection(args.skipped_groups, expand_dependencies=False)
            if args.skipped_groups
            else frozenset()
        )
        return VerificationPlan(
            groups=frozenset(),
            carried_groups=ALL_GROUPS - skipped,
            changed_files=(),
            reason="Identical tree is covered by a successful exact-head baseline.",
        )
    baseline_skipped = (
        parse_group_selection(args.baseline_skipped_groups, expand_dependencies=False)
        if args.baseline_skipped_groups
        else frozenset()
    )
    if baseline_skipped and not args.baseline_proven:
        raise RuntimeError("--baseline-skipped-groups requires --baseline-proven.")
    if baseline_skipped and not (args.base or args.staged):
        raise RuntimeError(
            "--baseline-skipped-groups is only valid with --base or --staged."
        )
    if args.base or args.staged:
        plan = plan_from_git(
            base=args.base,
            staged=args.staged,
            baseline_proven=args.baseline_proven,
            baseline_skipped_groups=baseline_skipped,
        )
    else:
        plan = VerificationPlan(
            groups=ALL_GROUPS,
            changed_files=(),
            reason="Full canonical verification requested.",
        )
    if args.carried_groups:
        raise RuntimeError(
            "--carried-groups is only valid with --groups for explicit-run evidence."
        )
    current_skipped = (
        parse_group_selection(args.skipped_groups, expand_dependencies=False)
        if args.skipped_groups
        else frozenset()
    )
    return apply_skip_lineage(
        plan,
        baseline_skipped_groups=baseline_skipped,
        current_skipped_groups=current_skipped,
    )


def main() -> int:
    args = parse_args()
    selection_modes = sum(
        (
            bool(args.groups),
            args.static_only,
            bool(args.base or args.staged or args.full or args.carry_all),
        )
    )
    if selection_modes > 1:
        print(
            "\nVerification failed: choose only one selection mode.",
            file=sys.stderr,
        )
        return 1
    if args.plan and not (args.base or args.staged or args.full or args.carry_all):
        print(
            "\nVerification failed: --plan requires --base, --staged, or --full.",
            file=sys.stderr,
        )
        return 1

    try:
        plan = resolve_selection(args)
    except RuntimeError as error:
        print(f"\nVerification failed: {error}", file=sys.stderr)
        return 1
    for line in plan_lines(plan):
        print(line)
    if args.github_output is not None:
        write_plan_outputs(plan, args.github_output)
    if args.summary is not None:
        write_plan_summary(plan, args.summary)
    if args.plan:
        return 0

    ARTIFACT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    runtime_started = False
    verification_error: RuntimeError | subprocess.CalledProcessError | None = None
    cleanup_error: subprocess.CalledProcessError | None = None
    docker = ""
    try:
        pnpm = (
            require_command("pnpm") if plan.groups & {"contracts", "web-static"} else ""
        )
        uv = (
            require_command("uv")
            if plan.groups & {"api-static", "ml-static"} or plan.groups & RUNTIME_GROUPS
            else ""
        )
        docker = require_command("docker") if plan.groups & DOCKER_GROUPS else ""

        for label, command in static_checks(
            pnpm=pnpm,
            uv=uv,
            docker=docker,
            groups=plan.groups,
        ):
            run(label, command)

        if plan.groups & RUNTIME_GROUPS:
            runtime_started = True
            run_runtime_checks(groups=plan.groups, pnpm=pnpm, uv=uv, docker=docker)
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"\nVerification failed: {error}", file=sys.stderr)
        verification_error = error
        if runtime_started:
            show_runtime_diagnostics(docker)
    finally:
        if runtime_started:
            try:
                cleanup_runtime(docker)
            except subprocess.CalledProcessError as error:
                cleanup_error = error
                print(f"\nRuntime cleanup failed: {error}", file=sys.stderr)

    if verification_error is not None or cleanup_error is not None:
        return 1

    print("\nVerification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
