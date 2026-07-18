from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
IGNORED_PREFIXES = ("#", "http://", "https://", "mailto:")


def iter_markdown_files() -> list[Path]:
    excluded = {".git", "node_modules"}
    return sorted(
        path
        for path in REPOSITORY_ROOT.rglob("*.md")
        if not excluded.intersection(path.relative_to(REPOSITORY_ROOT).parts)
    )


def local_target(raw_target: str) -> str | None:
    target = raw_target.strip().strip("<>").split(maxsplit=1)[0]
    if target.startswith(IGNORED_PREFIXES):
        return None
    return unquote(target.split("#", maxsplit=1)[0])


def main() -> int:
    failures: list[str] = []
    checked_links = 0

    for document in iter_markdown_files():
        content = document.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK.finditer(content):
            target = local_target(match.group(1))
            if not target:
                continue
            checked_links += 1
            resolved = (document.parent / target).resolve()
            if not resolved.exists():
                relative_document = document.relative_to(REPOSITORY_ROOT)
                failures.append(f"{relative_document}: missing link target {target}")

    if failures:
        print("Documentation link validation failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(
        f"Validated {checked_links} local links across "
        f"{len(iter_markdown_files())} Markdown files."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
