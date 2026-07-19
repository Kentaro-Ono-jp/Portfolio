from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from reactorfront_ml.model import DocumentClassifier, generate_artifact

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TRAINING_DATA = REPOSITORY_ROOT / "apps" / "ml" / "data" / "training.json"
EXPECTED_CHECKSUM = (
    (REPOSITORY_ROOT / "apps" / "ml" / "model.expected.sha256")
    .read_text(encoding="utf-8")
    .strip()
)
ARTIFACT_DIRECTORY = REPOSITORY_ROOT / "artifacts" / "verification"


def main() -> int:
    first = generate_artifact(TRAINING_DATA)
    second = generate_artifact(TRAINING_DATA)
    if first.content != second.content or first.sha256 != second.sha256:
        raise RuntimeError("Independent model generations did not match")
    if first.sha256 != EXPECTED_CHECKSUM:
        raise RuntimeError("Generated model checksum differs from the reviewed value")

    with TemporaryDirectory(prefix="reactorfront-ml-model-") as directory:
        root = Path(directory)
        artifact_path = root / "model.json"
        checksum_path = root / "model.sha256"
        artifact_path.write_bytes(first.content)
        checksum_path.write_text(f"{first.sha256}\n", encoding="utf-8")
        classifier = DocumentClassifier(
            artifact_path=artifact_path,
            checksum_path=checksum_path,
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
        "modelSha256": first.sha256,
        "trainingAccuracy": first.training_accuracy,
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
