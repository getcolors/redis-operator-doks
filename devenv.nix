{ pkgs, ... }:
{
  languages.clojure.enable = true;
  # kubectl drives the operator installation; the controller image is built
  # with the host's docker, outside this shell.
  packages = with pkgs; [ babashka bun uv curl jq kubectl ];
}
