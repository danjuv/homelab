{ pkgs, lib, config, inputs, ... }:

{
  packages = [ 
    pkgs.git 
    pkgs.kubectl
    pkgs.helm
    pkgs.k9s
    pkgs.claude-code
    pkgs.python3
  ];
}
