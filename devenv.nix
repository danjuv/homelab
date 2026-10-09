{ pkgs, lib, config, inputs, ... }:

{
  packages = [
    pkgs.git
    pkgs.kubectl
    pkgs.kubernetes-helm
    pkgs.kustomize
    pkgs.kubeconform
    pkgs.kubeseal
    pkgs.argocd
    pkgs.k9s
    pkgs.bazelisk
    (pkgs.python3.withPackages (ps: [ ps.pyyaml ]))
    pkgs.uv
    pkgs.helm-docs
    pkgs.argo-rollouts
  ];

  # Keep in sync with .github/workflows/validate.yaml
  env.KUBERNETES_VERSION = "1.35.0";
}
