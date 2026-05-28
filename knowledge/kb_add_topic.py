"""
kb_add_topic.py — Register a new topic in the Mimir Knowledge Base

Usage:
    python kb_add_topic.py <domain_path> <topic_name>

Arguments:
    domain_path   Forward-slash path relative to the knowledge root.
                  The new topic folder will be created under this path.
                  Example: "technology/cybersecurity"

    topic_name    Slug name for the new topic folder (lowercase, hyphens).
                  Example: "incident-response"

Full example:
    python kb_add_topic.py technology/cybersecurity incident-response

What it does:
    1. Creates knowledge/<domain_path>/<topic_name>/ if it doesn't exist.
    2. Writes a _README.md with the standard frontmatter template.
    3. Adds an entry to kb_progress.json with status "pending".
    4. Logs the addition with a timestamp to kb_add_topic.log.

Run from the knowledge/ directory or any location — the script resolves
all paths relative to its own location.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


PROGRESS_FILE = "kb_progress.json"
LOG_FILE = "kb_add_topic.log"

README_TEMPLATE = """\
---
title: {title}
domain: {domain}
subdomain: {subdomain}
tags:
source: original
last_updated:
---

# {title}

Add content files to this folder following the frontmatter format below.

## How to add content here

Create `.md` files in this folder with the following frontmatter header:

```yaml
---
title: Your Document Title
domain: {domain}
subdomain: {subdomain}
tags: tag1, tag2, tag3
source: where this came from (book, website, personal experience)
last_updated: YYYY-MM-DD
---
```

Then write your content in Markdown below the frontmatter.
"""


def normalize_path(raw: str) -> str:
    """Normalize to forward-slash, strip leading/trailing slashes."""
    return raw.replace("\\", "/").strip("/")


def load_progress(progress_path: Path) -> list:
    if not progress_path.exists():
        return []
    with progress_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_progress(progress_path: Path, entries: list) -> None:
    with progress_path.open("w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)
        f.write("\n")


def log_action(log_path: Path, message: str) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] {message}\n"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line)
    print(line, end="")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Register a new topic in the Mimir Knowledge Base.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python kb_add_topic.py technology/cybersecurity incident-response\n"
            "  python kb_add_topic.py health-medicine/medications antibiotic-reference\n"
            "  python kb_add_topic.py legal-financial land-rights-overview\n"
        ),
    )
    parser.add_argument(
        "domain_path",
        help="Forward-slash path to the parent folder (relative to knowledge root).",
    )
    parser.add_argument(
        "topic_name",
        help="Slug name for the new topic folder (lowercase, hyphens).",
    )
    args = parser.parse_args()

    knowledge_root = Path(__file__).parent.resolve()
    progress_path = knowledge_root / PROGRESS_FILE
    log_path = knowledge_root / LOG_FILE

    domain_path = normalize_path(args.domain_path)
    topic_name = normalize_path(args.topic_name)

    if "/" in topic_name:
        print(f"ERROR: topic_name should be a single folder name, not a path. Got: {topic_name}")
        sys.exit(1)

    full_rel_path = f"{domain_path}/{topic_name}" if domain_path else topic_name
    topic_dir = knowledge_root / Path(full_rel_path.replace("/", "\\"))

    # --- 1. Create folder ---
    if topic_dir.exists():
        print(f"Folder already exists: {full_rel_path}")
    else:
        topic_dir.mkdir(parents=True, exist_ok=True)
        print(f"Created folder: {full_rel_path}")

    # --- 2. Write _README.md (never overwrites) ---
    readme_path = topic_dir / "_README.md"
    if readme_path.exists():
        print(f"_README.md already exists — skipping.")
    else:
        parts = full_rel_path.split("/")
        domain = parts[0]
        subdomain = parts[-1]
        title = subdomain.replace("-", " ").title()
        content = README_TEMPLATE.format(
            title=title,
            domain=domain,
            subdomain=subdomain,
        )
        readme_path.write_text(content, encoding="utf-8")
        print(f"Created _README.md in: {full_rel_path}")

    # --- 3. Update kb_progress.json ---
    entries = load_progress(progress_path)
    existing_paths = {e["path"] for e in entries}

    if full_rel_path in existing_paths:
        print(f"Already tracked in kb_progress.json: {full_rel_path}")
        log_action(log_path, f"SKIP (already tracked): {full_rel_path}")
        return

    new_entry = {
        "path": full_rel_path,
        "status": "pending",
        "files_created": 0,
        "last_updated": None,
    }
    entries.append(new_entry)
    save_progress(progress_path, entries)
    print(f"Added to kb_progress.json: {full_rel_path}")

    # --- 4. Log ---
    log_action(
        log_path,
        f"ADD: {full_rel_path} | parent: {domain_path} | topic: {topic_name}",
    )


if __name__ == "__main__":
    main()
