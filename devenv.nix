{ pkgs, ... }:

let
  # Kubernetes baseline for local validation. Keep in sync with
  # .github/workflows/validate.yaml.
  kubernetesVersion = "1.35.0";
in
{
  packages = [
    # Kubernetes and GitOps
    pkgs.kubectl
    pkgs.kubernetes-helm
    pkgs.kustomize
    pkgs.kubeconform
    pkgs.kubeseal
    pkgs.argocd
    pkgs.argo-rollouts
    pkgs.k9s
    pkgs.kubectx # kubectx and kubens for switching cluster and namespace
    pkgs.stern # tail logs across pods

    # Manifest and data wrangling
    pkgs.yq
    pkgs.jq

    # Build, scripting and repository tooling
    pkgs.bazelisk
    pkgs.git
    pkgs.curl
    (pkgs.python3.withPackages (ps: [ ps.pyyaml ]))
    pkgs.uv
    pkgs.helm-docs
  ];

  env.KUBERNETES_VERSION = kubernetesVersion;

  # Local equivalent of the "Validate Kubernetes" CI job.
  scripts.validate = {
    exec = "python3 tools/validate_k8s.py";
    description = "Render and kubeconform-validate the tracked ArgoCD sources";
  };

  enterShell = ''
    echo "homelab devenv ready — Kubernetes ${kubernetesVersion} validation baseline"
    alias k=kubectl
    alias h=helm
    alias kctx=kubectx
    alias kns=kubens
  '';
}
