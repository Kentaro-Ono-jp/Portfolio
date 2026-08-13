from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "verify.yml"
CODECOV_PATH = REPOSITORY_ROOT / "codecov.yml"
README_PATH = REPOSITORY_ROOT / "README.md"

CODECOV_ACTION = "codecov/codecov-action@fb8b3582c8e4def4969c97caa2f19720cb33a72f"
CODECOV_CLI_VERSION = "v11.3.1"


def test_coverage_publication_is_secretless_pinned_and_complete() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert workflow.count("id-token: write") == 1
    assert "CODECOV_TOKEN" not in workflow
    assert workflow.count(f"uses: {CODECOV_ACTION}") == 3
    assert workflow.count(f"version: {CODECOV_CLI_VERSION}") == 3
    assert workflow.count("name: coverage-${{ github.run_id }}") == 2
    assert "name: coverage-${{ github.run_id }}-${{ github.run_attempt }}" not in workflow
    assert "overwrite: true" in workflow

    expected_uploads = {
        "web": "artifacts/verification/web-coverage/lcov.info",
        "api": "artifacts/verification/api-coverage.xml",
        "ml": "artifacts/verification/ml-coverage.xml",
    }
    for flag, report in expected_uploads.items():
        assert f"files: {report}" in workflow
        assert f"flags: {flag}" in workflow


def test_codecov_preserves_selective_monorepo_coverage() -> None:
    configuration = yaml.safe_load(CODECOV_PATH.read_text(encoding="utf-8"))

    assert configuration["coverage"]["status"]["project"]["default"] == {
        "target": "90%",
        "threshold": "0%",
        "if_ci_failed": "error",
    }
    assert configuration["comment"] is False
    assert configuration["fixes"] == ["src/::apps/web/src/"]
    assert configuration["flags"] == {
        "web": {"paths": ["apps/web/src/"], "carryforward": True},
        "api": {"paths": ["apps/api/src/"], "carryforward": True},
        "ml": {"paths": ["apps/ml/src/"], "carryforward": True},
    }


def test_readme_badges_link_to_inspectable_default_branch_evidence() -> None:
    readme = README_PATH.read_text(encoding="utf-8")

    assert "verify.yml/badge.svg?branch=main&event=push" in readme
    assert (
        "github/actions/workflow/status/Kentaro-Ono-jp/Portfolio/aws-deploy.yml"
        "?branch=main&event=schedule&label=Managed%20AWS%20lifecycle"
    ) in readme
    assert (
        "raw.githubusercontent.com%2FKentaro-Ono-jp%2FPortfolio%2Fmain%2Fapps%2Fml%2F"
        "evaluation%2Fcandidate-comparison-v1.json&query=%24.eligible"
    ) in readme
    assert (
        "img.shields.io/codecov/c/github/Kentaro-Ono-jp/Portfolio?label=Overall%20coverage"
    ) in readme
    assert (
        "img.shields.io/codecov/c/github/Kentaro-Ono-jp/Portfolio?flag=ml&label=ML%20coverage"
    ) in readme
    assert "img.shields.io/github/license/Kentaro-Ono-jp/Portfolio" in readme
