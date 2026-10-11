#!/usr/bin/env python3

import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parent.parent
HOMEPAGE = ROOT / "k8s" / "apps" / "homepage"
VALUES = HOMEPAGE / "values.yaml"
SEALED_SECRET = HOMEPAGE / "sealedsecret.yaml"

PLACEHOLDER = re.compile(r"\{\{(HOMEPAGE_VAR_[A-Z0-9_]+)\}\}")
CREDENTIAL_HINTS = ("key", "apikey", "password", "token", "secret")


def load(path):
    return yaml.safe_load(path.read_text())


def walk(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)
    elif isinstance(value, str):
        yield value


def ingress_text():
    chunks = []
    for path in sorted((ROOT / "k8s").rglob("*")):
        if path.suffix not in {".yaml", ".yml"}:
            continue
        if HOMEPAGE in path.parents or path == SEALED_SECRET:
            continue
        chunks.append(path.read_text())
    return "\n".join(chunks)


def main():
    errors = []
    warnings = []

    values = load(VALUES)
    sealed = load(SEALED_SECRET)
    encrypted = (sealed.get("spec") or {}).get("encryptedData") or {}

    config = values.get("config") or {}
    services = config.get("services") or []
    settings = config.get("settings") or {}
    layout = settings.get("layout") or {}

    declared_groups = []
    for entry in services:
        if not isinstance(entry, dict) or len(entry) != 1:
            errors.append(f"service group is not a single-key mapping: {entry!r}")
            continue
        (group, members), = entry.items()
        declared_groups.append(group)
        if not members:
            errors.append(f"group {group!r} has no services")
        if group not in layout:
            errors.append(f"group {group!r} has no settings.layout entry")
    for group in layout:
        if group not in declared_groups:
            errors.append(f"settings.layout group {group!r} has no services")

    hosts_text = ingress_text()
    names = Counter()
    for entry in services:
        if not isinstance(entry, dict) or len(entry) != 1:
            continue
        (group, members), = entry.items()
        for card in members or []:
            if not isinstance(card, dict) or len(card) != 1:
                errors.append(f"service in {group!r} is not a single-key mapping: {card!r}")
                continue
            (name, body), = card.items()
            names[name] += 1
            body = body or {}
            href = body.get("href")
            if not href:
                errors.append(f"{name!r} has no href")
                continue
            parsed = urlparse(href)
            if parsed.scheme != "https":
                errors.append(f"{name!r} href is not https: {href}")
            if not parsed.hostname or parsed.hostname not in hosts_text:
                errors.append(
                    f"{name!r} href host {parsed.hostname!r} is not declared "
                    f"anywhere under k8s/"
                )
            if not body.get("description"):
                warnings.append(f"{name!r} has no description")
            if not body.get("icon"):
                warnings.append(f"{name!r} has no icon")

    for name, count in names.items():
        if count > 1:
            errors.append(f"duplicate service name {name!r} ({count} cards)")

    for entry in services:
        if not isinstance(entry, dict) or len(entry) != 1:
            continue
        for card in list(entry.values())[0] or []:
            if not isinstance(card, dict) or len(card) != 1:
                continue
            (name, body), = card.items()
            widget = (body or {}).get("widget") or {}
            if not widget:
                continue
            if not widget.get("type"):
                errors.append(f"{name!r} widget has no type")
            if not widget.get("url"):
                errors.append(f"{name!r} widget has no url")
            for field, value in widget.items():
                if any(hint in field.lower() for hint in CREDENTIAL_HINTS):
                    if not isinstance(value, str) or not PLACEHOLDER.fullmatch(value):
                        errors.append(
                            f"{name!r} widget field {field!r} must use a "
                            f"{{{{HOMEPAGE_VAR_*}}}} placeholder, not {value!r}"
                        )

    referenced = set()
    for value in walk(config):
        referenced.update(PLACEHOLDER.findall(value))
    for ref in sorted(referenced):
        if ref not in encrypted:
            errors.append(f"placeholder {{{{{ref}}}}} has no key in sealedsecret.yaml")
    for key in sorted(set(encrypted) - referenced):
        warnings.append(f"sealedsecret key {key!r} is not referenced by any service")

    for warning in warnings:
        print(f"warning: {warning}")
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors:
        raise SystemExit(f"Homepage validation failed with {len(errors)} error(s)")
    print(
        f"Homepage config OK: {len(declared_groups)} groups, "
        f"{sum(names.values())} services, {len(referenced)} secret reference(s)."
    )


if __name__ == "__main__":
    main()
