#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
pkg_dir=$(mktemp -d)
trap 'rm -rf "$pkg_dir"' EXIT
cd "$pkg_dir"
for package in clang llvm llvm-libs lld; do
    file="$package-23.1.1-1-x86_64.pkg.tar.zst"
    url="https://archive.archlinux.org/packages/${package:0:1}/$package/$file"
    curl --fail --location --retry 3 --output "$file" "$url"
    curl --fail --location --retry 3 --output "$file.sig" "$url.sig"
done
sha256sum -c "$repo/ci/toolchain.sha256"
pacman -U --noconfirm ./*.pkg.tar.zst
clang --version
[[ "$(clang -dumpversion)" == 23.1.1 ]]
