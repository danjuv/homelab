{ pkgs, lib, config, inputs, ... }:

{
  packages = [
    pkgs.git
    pkgs.kubectl
    pkgs.kubernetes-helm
    pkgs.kustomize
    pkgs.kubeseal
    pkgs.argocd
    pkgs.k9s
    pkgs.bazelisk
    pkgs.claude-code
    pkgs.python3
    pkgs.uv
  ];
}
