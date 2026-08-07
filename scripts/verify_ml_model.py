from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from reactorfront_ml.model import DocumentClassifier
from reactorfront_ml.promotion import load_promoted_model

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EVALUATION_ROOT = REPOSITORY_ROOT / "apps" / "ml" / "evaluation"
PROMOTION_MANIFEST = EVALUATION_ROOT / "promoted-model-v1.json"
PROMOTION_SCHEMA = EVALUATION_ROOT / "promoted-model-v1.schema.json"
ARTIFACT_DIRECTORY = REPOSITORY_ROOT / "artifacts" / "verification"


def main() -> int:
    first = load_promoted_model(
        PROMOTION_MANIFEST,
        PROMOTION_SCHEMA,
        repository_root=REPOSITORY_ROOT,
    )
    second = load_promoted_model(
        PROMOTION_MANIFEST,
        PROMOTION_SCHEMA,
        repository_root=REPOSITORY_ROOT,
    )
    if (
        first.artifact.content != second.artifact.content
        or first.artifact.sha256 != second.artifact.sha256
        or first.manifest_sha256 != second.manifest_sha256
    ):
        raise RuntimeError("Independent promoted-model generations did not match")

    with TemporaryDirectory(prefix="reactorfront-ml-model-") as directory:
        root = Path(directory)
        artifact_path = root / "model.json"
        checksum_path = root / "model.sha256"
        artifact_path.write_bytes(first.artifact.content)
        checksum_path.write_text(f"{first.artifact.sha256}\n", encoding="utf-8")
        classifier = DocumentClassifier(
            artifact_path=artifact_path,
            checksum_path=checksum_path,
            expected_model_name=first.model_name,
            expected_model_version=first.model_version,
        )
        invoice = classifier.classify(
            "Invoice INV-9001 bill to customer subtotal tax total amount due payment terms"
        )
        report = classifier.classify(
            "Quarterly report executive summary findings analysis risks recommendations"
        )

    if invoice.classification != "invoice" or invoice.confidence < 0.70:
        raise RuntimeError(
            "Canonical invoice classification did not meet its threshold"
        )
    if report.classification != "report" or report.confidence < 0.70:
        raise RuntimeError("Canonical report classification did not meet its threshold")

    ARTIFACT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    metadata = {
        "manifestSha256": first.manifest_sha256,
        "modelSha256": first.artifact.sha256,
        "modelVersion": first.model_version,
        "selectionType": first.selection_type,
        "trainingAccuracy": first.artifact.training_accuracy,
        "invoice": {
            "classification": invoice.classification,
            "confidence": invoice.confidence,
        },
        "report": {
            "classification": report.classification,
            "confidence": report.confidence,
        },
    }
    (ARTIFACT_DIRECTORY / "ml-model-proof.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(metadata, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
