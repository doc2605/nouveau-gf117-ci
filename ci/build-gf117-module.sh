#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
cd "$repo"
mkdir -p ci-output work
exec > >(tee ci-output/build.log) 2>&1
[[ "$(clang -dumpversion)" == 23.1.1 ]] || {
    echo "Expected Clang 23.1.1; found $(clang -dumpversion)" >&2; exit 1;
}
clang --version
(cd ci && sha256sum -c kernel-7.2.9-2-headers.sha256)
tar --zstd -xf ci/kernel-7.2.9-2-headers.tar.zst -C work
curl --fail --location --retry 3 --output work/source.tar.gz \
    https://github.com/CachyOS/linux/releases/download/cachyos-7.2.9-2/cachyos-7.2.9-2.tar.gz
printf '%s  %s\n' 2da9e6ffe31436657f46909db059059946dac22c2ac6cde05e49a66d61acfcba work/source.tar.gz | sha256sum -c -
tar -xzf work/source.tar.gz -C work cachyos-7.2.9-2/drivers/gpu/drm/nouveau
src="$repo/work/cachyos-7.2.9-2"
for patch in "$repo"/patches/nouveau/*.patch; do
    patch --batch --fuzz=0 -d "$src" -p1 -i "$patch"
done
for test in core ram vga crtc; do
    python "tools/test-gf117-$test-source.py" "$src"
done
python tools/test-gf117-core-helper.py
bash -n tools/test-gf117-core-once.sh
make -C "$repo/work/build" LLVM=1 LLVM_IAS=1 -j"$(nproc)" \
    M="$src/drivers/gpu/drm/nouveau" modules
module="$src/drivers/gpu/drm/nouveau/nouveau.ko"
[[ "$(modinfo -F vermagic "$module" | xargs)" == '7.2.9-2-cachyos SMP preempt mod_unload' ]]
python - "$module" <<'MANIFEST'
import hashlib,json,os,subprocess,sys
from pathlib import Path
module=Path(sys.argv[1]);root=Path.cwd()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=dict(kernel='7.2.9-2-cachyos',commit=os.environ.get('GITHUB_SHA'),
    module_sha256=sha(module),source_sha256=sha(root/'work/source.tar.gz'),
    headers_sha256=sha(root/'ci/kernel-7.2.9-2-headers.tar.zst'),
    config_sha256=sha(root/'work/build/.config'),
    symvers_sha256=sha(root/'work/build/Module.symvers'),
    compiler=subprocess.check_output(['clang','--version'],text=True).splitlines()[0],
    vermagic=subprocess.check_output(['modinfo','-F','vermagic',str(module)],text=True).strip(),
    patches={p.name:sha(p) for p in sorted((root/'patches/nouveau').glob('*.patch'))})
(root/'ci-output/manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest,indent=2))
MANIFEST
zstd -T0 -6 -o ci-output/nouveau.ko.zst "$module"
sha256sum ci-output/nouveau.ko.zst > ci-output/nouveau.ko.zst.sha256
