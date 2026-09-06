#!/usr/bin/env python3
"""Render tracked ArgoCD sources and validate resources without a cluster."""

import json
import os
from pathlib import Path
import subprocess
import tempfile

import yaml


LOCAL_REPOS = {
    "git@github.com:danjuv/homelab.git",
    "https://github.com/danjuv/homelab.git",
    "https://github.com/danjuv/homelab",
}
KUSTOMIZATIONS = ("kustomization.yaml", "kustomization.yml", "Kustomization")
SCHEMA_REPO = (
    "https://raw.githubusercontent.com/yannh/kubernetes-json-schema/"
    "07b64c5376535fbbd6fb9910621e1a41f7613c14"
)


class UniqueKeyLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        keys = set()
        for key, _ in node.value:
            if key.tag == "tag:yaml.org,2002:merge":
                continue
            value = self.construct_object(key, deep=deep)
            if value in keys:
                raise ValueError(f"Duplicate YAML key {value!r} at {key.start_mark}")
            keys.add(value)
        return super().construct_mapping(node, deep=deep)


def documents(text):
    return [doc for doc in yaml.load_all(text, Loader=UniqueKeyLoader) if doc is not None]


def run(*args, cwd=None):
    print("+", " ".join(map(str, args)), flush=True)
    return subprocess.check_output(list(map(str, args)), cwd=cwd, text=True)


def inside(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes repository: {relative}")
    if not path.exists():
        raise ValueError(f"Missing path: {path}")
    return path


def checkout(source, root, scratch, repos):
    url = source["repoURL"]
    revision = source["targetRevision"]
    if url in LOCAL_REPOS:
        if revision not in {"HEAD", "main"}:
            raise ValueError(f"Cannot validate local repository revision {revision!r}")
        # $values must use the PR checkout, never the default branch on GitHub.
        return root
    key = (url, revision)
    if key not in repos:
        path = scratch / f"repo-{len(repos)}"
        run("git", "init", "--quiet", path)
        run("git", "fetch", "--quiet", "--depth=1", url, revision, cwd=path)
        run("git", "checkout", "--quiet", "--detach", "FETCH_HEAD", cwd=path)
        repos[key] = path
    return repos[key]


def render_helm(app, source, sources, root, scratch, repos, kube_version):
    helm = source.get("helm", {})
    unsupported = set(helm) - {"releaseName", "valueFiles", "skipCrds"}
    if unsupported:
        raise ValueError(f"Unsupported Helm options: {sorted(unsupported)}")
    command = ["helm", "template", helm.get("releaseName", app["metadata"]["name"])]
    if "chart" in source:
        repo = source["repoURL"].rstrip("/")
        chart = source["chart"]
        if repo.startswith(("http://", "https://")):
            command += [chart, "--repo", repo]
        else:
            repo = repo.removeprefix("oci://")
            if repo.rsplit("/", 1)[-1] != chart:
                repo += "/" + chart
            command += ["oci://" + repo]
        command += ["--version", source["targetRevision"]]
    else:
        chart = inside(checkout(source, root, scratch, repos), source["path"])
        metadata = documents((chart / "Chart.yaml").read_text())[0]
        if metadata.get("dependencies"):
            run("helm", "dependency", "build", chart)
        command += [str(chart)]
    command += [
        "--namespace", app["spec"]["destination"]["namespace"],
        "--kube-version", kube_version,
    ]
    if not helm.get("skipCrds", False):
        command += ["--include-crds"]
    for value_file in helm.get("valueFiles", []):
        if not value_file.startswith("$") or "/" not in value_file:
            raise ValueError(f"Expected a repository-referenced values file: {value_file}")
        ref, relative = value_file[1:].split("/", 1)
        matches = [item for item in sources if item.get("ref") == ref]
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one source for ${ref}")
        values_root = checkout(matches[0], root, scratch, repos)
        command += ["--values", str(inside(values_root, relative))]
    rendered = documents(run(*command))
    if not rendered:
        raise ValueError("Helm produced no resources")
    return rendered


def json_schema(schema):
    """Translate OpenAPI-only type markers used in Kubernetes CRD schemas."""
    if isinstance(schema, list):
        return [json_schema(value) for value in schema]
    if not isinstance(schema, dict):
        return schema
    result = {key: json_schema(value) for key, value in schema.items()}
    if result.get("format") == "int-or-string" or result.get("x-kubernetes-int-or-string") is True:
        result.pop("format", None)
        result["type"] = ["integer", "string"]
    if result.get("nullable") is True and "type" in result:
        result.pop("nullable")
        types = result["type"]
        result["type"] = (types if isinstance(types, list) else [types]) + ["null"]
    return result


def main():
    root = Path(__file__).resolve().parent.parent
    kube_version = os.environ.get("KUBERNETES_VERSION", "1.35.0")
    paths = run("git", "ls-files", "-z", "--", "k8s", cwd=root).split("\0")
    resources = []
    applications = []
    kustomizations = set()
    parsed = {}
    for name in paths:
        path = root / name
        if path.suffix not in {".yaml", ".yml"} and path.name != "Kustomization":
            continue
        if path.name in KUSTOMIZATIONS:
            kustomizations.add(path.parent)
        parsed[path] = documents(path.read_text())
        for doc in parsed[path]:
            if not isinstance(doc, dict):
                raise ValueError(f"Expected a YAML mapping in {name}")
            if doc.get("kind") == "Application" and doc.get("apiVersion", "").startswith("argoproj.io/"):
                applications.append(doc)
    values_files = set()
    for app in applications:
        sources = app["spec"].get("sources") or [app["spec"]["source"]]
        for source in sources:
            for value_file in source.get("helm", {}).get("valueFiles", []):
                if value_file.startswith("$") and "/" in value_file:
                    ref, relative = value_file[1:].split("/", 1)
                    if any(item.get("ref") == ref and item["repoURL"] in LOCAL_REPOS for item in sources):
                        values_files.add(inside(root, relative))
    for path, docs in parsed.items():
        if path in values_files or path.name in KUSTOMIZATIONS:
            continue
        for doc in docs:
            if not doc.get("apiVersion") or not doc.get("kind"):
                raise ValueError(f"Resource requires apiVersion and kind: {path}")
            resources.append(doc)
    if not applications:
        raise ValueError("No tracked ArgoCD Applications found")

    errors = []
    with tempfile.TemporaryDirectory(prefix="validate-k8s-") as temp:
        scratch = Path(temp)
        repos = {}
        for app in applications:
            name = app["metadata"]["name"]
            print(f"\nValidating Application {name}", flush=True)
            spec = app["spec"]
            sources = spec.get("sources") or [spec["source"]]
            try:
                for source in sources:
                    if "chart" in source or "helm" in source:
                        resources.extend(render_helm(
                            app, source, sources, root, scratch, repos, kube_version,
                        ))
                    elif source["repoURL"] in LOCAL_REPOS:
                        local = checkout(source, root, scratch, repos)
                        if "path" in source and not inside(local, source["path"]).is_dir():
                            raise ValueError(f"Source path is not a directory: {source['path']}")
                    elif source["repoURL"] not in LOCAL_REPOS and "path" in source:
                        directory = inside(checkout(source, root, scratch, repos), source["path"])
                        if source.get("directory"):
                            raise ValueError("External directory options are not supported")
                        for path in sorted(directory.iterdir()):
                            if path.suffix in {".yaml", ".yml"}:
                                resources.extend(documents(path.read_text()))
                    elif source["repoURL"] not in LOCAL_REPOS:
                        raise ValueError(f"Unsupported source: {source}")
            except (ValueError, KeyError, OSError, subprocess.CalledProcessError, yaml.YAMLError) as error:
                errors.append(f"{name}: {error}")
                print(f"ERROR: {errors[-1]}", flush=True)

        for directory in sorted(kustomizations):
            try:
                resources.extend(documents(run("kustomize", "build", directory)))
            except (subprocess.CalledProcessError, yaml.YAMLError) as error:
                errors.append(f"{directory}: {error}")

        # Use the CRDs from these exact chart/Git versions, not an unrelated schema catalog.
        schemas = scratch / "schemas"
        schemas.mkdir()
        schema_url = f"{SCHEMA_REPO}/v{kube_version}-standalone-strict"
        # The catalog includes CRD definitions only in its combined definitions file.
        crd_schema = json.loads(run("curl", "-fsSL", "--retry", "3", f"{schema_url}/_definitions.json"))
        crd_schema["$schema"] = "http://json-schema.org/draft-04/schema#"
        crd_schema["$ref"] = (
            "#/definitions/io.k8s.apiextensions-apiserver.pkg.apis.apiextensions.v1."
            "CustomResourceDefinition"
        )
        crd_group = schemas / "apiextensions.k8s.io"
        crd_group.mkdir()
        (crd_group / "customresourcedefinition_v1.json").write_text(json.dumps(crd_schema))
        for resource in resources:
            if resource.get("kind") != "CustomResourceDefinition":
                continue
            spec = resource["spec"]
            group = schemas / spec["group"]
            group.mkdir(exist_ok=True)
            for version in spec["versions"]:
                schema = version.get("schema", {}).get("openAPIV3Schema")
                if schema:
                    filename = f"{spec['names']['kind'].lower()}_{version['name']}.json"
                    (group / filename).write_text(json.dumps(json_schema(schema)))
        manifests = scratch / "resources.yaml"
        manifests.write_text(yaml.safe_dump_all(resources))
        try:
            print(run(
                "kubeconform", "-strict", "-summary", "-kubernetes-version", kube_version,
                "-schema-location", str(schemas / "{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json"),
                "-schema-location", schema_url + "/{{.ResourceKind}}{{.KindSuffix}}.json", manifests,
            ), flush=True)
        except subprocess.CalledProcessError as error:
            print(error.output, flush=True)
            errors.append("Kubernetes schema validation failed")
        if errors:
            raise SystemExit("\nValidation failed:\n" + "\n".join(errors))
        print(f"Validated {len(applications)} Applications and {len(resources)} resources.")


if __name__ == "__main__":
    main()
