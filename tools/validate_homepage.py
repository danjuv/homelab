#!/usr/bin/env python3
"""Validate the Homepage dashboard configuration without a cluster.

Homepage's chart renders `config.*` from k8s/apps/homepage/values.yaml into
the services.yaml / widgets.yaml / settings.yaml / kubernetes.yaml config
files. This script checks that configuration against the deployed Homepage
version (v2.5.0) and the rest of the repository:

  * every `config.*` file round-trips through YAML;
  * every service has an `icon` and an `href`;
  * every `href` hostname is declared by another manifest in this repo;
  * every `{{HOMEPAGE_VAR_*}}` reference has a SealedSecret key;
  * info widgets and the service widgets in use only carry options the
    deployed Homepage understands;
  * every layout group names a real service group.

Pass `--check-icons` to also resolve each icon in the same CDN sets the
deployed Homepage uses (requires network; skipped offline).

Usage:
    python3 tools/validate_homepage.py [--check-icons]
"""

import argparse
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
VALUES = ROOT / "k8s/apps/homepage/values.yaml"
SEALED = ROOT / "k8s/apps/homepage/sealedsecret.yaml"
CONFIG_FILES = ("bookmarks", "services", "widgets", "settings", "kubernetes", "docker")

VAR_REF = re.compile(r"\{\{(HOMEPAGE_VAR_[A-Z0-9_]+)\}\}")
HOSTNAME = re.compile(r"\b[a-z0-9][a-z0-9.-]*\.home\.lab\b")

# Options accepted by the info widgets used in config.widgets, pinned to the
# deployed Homepage version (src/components/widgets, v2.5.0).
INFO_WIDGETS = {
    "resources": {
        "expanded", "cpu", "memory", "disk", "network", "cputemp", "tempmin",
        "tempmax", "units", "uptime", "refresh", "diskUnits", "label",
    },
    "kubernetes": {"cluster", "nodes"},
    "longhorn": {"expanded", "total", "labels", "nodes", "include"},
    "search": {"provider", "focus", "showSearchSuggestions", "target", "url", "suggestionUrl"},
}

# Required and accepted options for the service widgets in use, pinned to the
# deployed Homepage version (docs/widgets/services, v2.5.0).
SERVICE_WIDGETS = {
    "sonarr": ({"url", "key"}, {"enableQueue"}),
    "radarr": ({"url", "key"}, {"enableQueue"}),
    "prowlarr": ({"url", "key"}, set()),
    "qbittorrent": ({"url"}, {"username", "password", "key", "enableLeechProgress", "enableLeechSize"}),
    "tautulli": ({"url", "key"}, set()),
    "seerr": ({"url", "key"}, {"fields"}),
}


class Error(Exception):
    pass


def load_yaml(path):
    try:
        return yaml.safe_load(path.read_text())
    except yaml.YAMLError as error:
        raise Error(f"{path.relative_to(ROOT)} is not valid YAML: {error}") from error


def round_trip(value, label):
    """The chart serialises config.* to YAML; make sure that stays valid."""
    try:
        yaml.safe_load(yaml.safe_dump(value))
    except yaml.YAMLError as error:
        raise Error(f"{label} does not round-trip through YAML: {error}") from error


def repo_hostnames():
    """Every `*.home.lab` hostname declared by a tracked manifest, except
    Homepage's own hrefs (which are what we are checking)."""
    names = set()
    for path in ROOT.glob("k8s/**/*.yaml"):
        if path.resolve() == VALUES.resolve():
            continue
        try:
            text = path.read_text()
        except OSError:
            continue
        names.update(HOSTNAME.findall(text))
    return names


def service_entries(services):
    """Yield (group, name, spec) triples from config.services."""
    if not isinstance(services, list):
        raise Error("config.services must be a list of groups")
    for group in services:
        if not isinstance(group, dict) or len(group) != 1:
            raise Error(f"each services group must be a single-key map, got {group!r}")
        ((group_name, entries),) = group.items()
        if not isinstance(entries, list):
            raise Error(f"services group {group_name!r} must be a list")
        for entry in entries:
            if not isinstance(entry, dict) or len(entry) != 1:
                raise Error(f"each service in {group_name!r} must be a single-key map")
            ((name, spec),) = entry.items()
            if not isinstance(spec, dict):
                raise Error(f"service {name!r} must map to a mapping")
            yield group_name, name, spec


def check_services(config, hostnames, errors):
    services = config.get("services")
    groups = set()
    for group, name, spec in service_entries(services):
        groups.add(group)
        if not spec.get("icon"):
            errors.append(f"service {name!r} has no icon")
        href = spec.get("href")
        if not href:
            errors.append(f"service {name!r} has no href")
            continue
        host = urllib.parse.urlparse(href).hostname
        if host not in hostnames:
            errors.append(f"service {name!r} href host {host!r} is not declared by any repo manifest")

        widget = spec.get("widget")
        if widget is None:
            continue
        if not isinstance(widget, dict):
            errors.append(f"service {name!r} widget must be a mapping")
            continue
        check_service_widget(name, widget, errors)
    return groups


def check_service_widget(name, widget, errors):
    kind = widget.get("type")
    if not kind:
        errors.append(f"service {name!r} widget has no type")
        return
    if kind not in SERVICE_WIDGETS:
        # A widget this script does not know about: keep the check honest
        # rather than guessing its schema.
        return
    required, optional = SERVICE_WIDGETS[kind]
    keys = set(widget)
    missing = required - keys
    if missing:
        errors.append(f"service {name!r} {kind} widget is missing {sorted(missing)}")
    unknown = keys - required - optional - {"type"}
    if unknown:
        errors.append(f"service {name!r} {kind} widget has unknown options {sorted(unknown)}")


def check_widgets(config, errors):
    widgets = config.get("widgets")
    if not isinstance(widgets, list):
        errors.append("config.widgets must be a list")
        return
    for widget in widgets:
        if not isinstance(widget, dict) or len(widget) != 1:
            errors.append(f"each widget must be a single-key map, got {widget!r}")
            continue
        ((kind, options),) = widget.items()
        if kind not in INFO_WIDGETS:
            errors.append(f"unknown info widget {kind!r}")
            continue
        if options is None:
            options = {}
        if not isinstance(options, dict):
            errors.append(f"info widget {kind!r} options must be a mapping")
            continue
        unknown = set(options) - INFO_WIDGETS[kind]
        if unknown:
            errors.append(f"info widget {kind!r} has options the deployed Homepage does not accept: {sorted(unknown)}")


def check_layout(config, groups, errors):
    settings = config.get("settings") or {}
    layout = settings.get("layout") or {}
    if not isinstance(layout, dict):
        errors.append("config.settings.layout must be a mapping")
        return
    for name in layout:
        if name not in groups:
            errors.append(f"layout group {name!r} has no matching services group")


def check_secrets(text, sealed, errors):
    wanted = set(VAR_REF.findall(text))
    keys = set((sealed.get("spec") or {}).get("encryptedData") or {})
    missing = wanted - keys
    if missing:
        errors.append(f"references to HOMEPAGE_VAR_* without a SealedSecret key: {sorted(missing)}")
    # An extra SealedSecret key is not an error: sealing a value ahead of the
    # service that uses it is a normal order of operations.
    unused = keys - wanted
    if unused:
        print(f"note: SealedSecret keys with no service references: {sorted(unused)}")


def icon_url(icon):
    """Mirror src/components/resolvedicon.jsx from Homepage v2.5.0."""
    if icon.startswith("http") or icon.startswith("/"):
        return icon
    if icon.split("-")[0] == "sh":
        name = icon.removeprefix("sh-").removesuffix(".png").removesuffix(".svg").removesuffix(".webp")
        ext = icon.rsplit(".", 1)[-1] if icon.endswith((".svg", ".webp")) else "png"
        return f"https://cdn.jsdelivr.net/gh/selfhst/icons@main/{ext}/{name}.{ext}"
    prefix = icon.split("-")[0]
    if prefix in {"mdi", "si"}:
        base = "https://cdn.jsdelivr.net/npm/@mdi/svg@latest/svg/" if prefix == "mdi" else "https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/"
        return f"{base}{icon.removeprefix(prefix + '-').removesuffix('.svg')}.svg"
    ext = "svg" if icon.endswith(".svg") else "webp" if icon.endswith(".webp") else "png"
    name = icon.removesuffix(f".{ext}")
    return f"https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/{ext}/{name}.{ext}"


def check_icons(config, errors):
    for _, name, spec in service_entries(config.get("services")):
        icon = spec.get("icon")
        if not icon:
            continue
        url = icon_url(icon)
        request = urllib.request.Request(url, method="HEAD")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                status = response.status
        except urllib.error.HTTPError as error:
            errors.append(f"service {name!r} icon {icon!r} does not resolve ({error.code}): {url}")
            continue
        except urllib.error.URLError as error:
            raise Error(f"icon check needs network and could not reach the CDN: {error}") from error
        if status != 200:
            errors.append(f"service {name!r} icon {icon!r} does not resolve ({status}): {url}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-icons", action="store_true", help="resolve icons over the network")
    args = parser.parse_args()

    values = load_yaml(VALUES)
    config = values.get("config")
    if not isinstance(config, dict):
        raise Error("values.yaml has no config mapping")

    errors = []
    for key in config:
        if key not in CONFIG_FILES:
            errors.append(f"unknown config key {key!r}")
        else:
            round_trip(config[key], f"config.{key}")

    hostnames = repo_hostnames()
    groups = check_services(config, hostnames, errors)
    check_widgets(config, errors)
    check_layout(config, groups, errors)

    # Every config file is serialised together, so scan them as one blob.
    check_secrets(yaml.safe_dump(config), load_yaml(SEALED), errors)

    if args.check_icons:
        check_icons(config, errors)
    else:
        print("skipping icon resolution (pass --check-icons to enable)")

    if errors:
        print("Homepage configuration invalid:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"Homepage configuration valid ({len(groups)} groups, {len(hostnames)} known hosts).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Error as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
