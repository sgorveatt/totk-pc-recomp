"""Build only public runtime sources, or finish their split build locally.

The partial archive omits every translation unit that needs generated game headers.
Run from an isolated source checkout matching the artifact's source commit.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

LOCAL_ONLY = {'memory.c', 'loader.c', 'frame_rate.c'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=['build', 'finish'])
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--artifact', type=Path, required=True)
    ap.add_argument('--jobs', type=int, default=2)
    args, remaining = ap.parse_known_args()
    source, artifact = args.source.resolve(), args.artifact.resolve()
    os.chdir(source)
    sys.path.insert(0, str(source / 'tools'))
    import build_game as bg
    if not bg.WIN:
        ap.error('this artifact targets Windows UCRT64')
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    # Keep these files local both when making the partial archive and consuming it.
    bg.INSTALL_SIDE = bg.INSTALL_SIDE | LOCAL_ONLY
    if args.mode == 'finish':
        manifest = json.loads((artifact / 'manifest.json').read_text())
        if sha != manifest['source_commit']:
            sys.exit('Source commit differs from artifact. Use the exact recorded commit.')
        for rel, expected in manifest['runtime_sources'].items():
            if digest(source / rel) != expected:
                sys.exit(f'Source differs from artifact: {rel}')
        for rel, expected in manifest['files'].items():
            if digest(artifact / rel) != expected:
                sys.exit(f'Artifact checksum mismatch: {rel}')
        if set(manifest['local_only']) != LOCAL_ONLY:
            sys.exit('Artifact and finish helper disagree on local source files')
        sys.argv = ['build_game.py', '--runtime-lib', str(artifact / 'libtotkrt-public.a'),
                    '--jobs', str(args.jobs), *remaining]
        bg.main()
        return
    if remaining:
        ap.error('unknown build arguments: ' + ' '.join(remaining))
    # A fresh checkout must have no locally extracted or generated game material.
    for name in ('generated', 'config.local.toml', 'build/extracted'):
        if (source / name).exists():
            sys.exit(f'Cloud build refuses {name}')
    if artifact.exists():
        sys.exit('Artifact staging directory already exists; use a fresh directory')
    work = source / 'build' / 'ci-public-runtime'
    work.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PATH=str(bg.UCRT) + os.pathsep + os.environ.get('PATH', ''))
    # ninja_file can build the runtime alone without going through main(), which
    # requires layout.json and emits modules.c even for --make-runtime-lib.
    text, objects, library = bg.ninja_file(source / 'generated', work, {}, args.jobs, make_lib=True)
    (work / 'build.ninja').write_text(text, encoding='utf-8')
    subprocess.run([str(bg.NINJA), '-f', str(work / 'build.ninja'), '-j', str(args.jobs)],
                   env=env, check=True)
    artifact.mkdir(parents=True)
    shutil.copy2(library, artifact / 'libtotkrt-public.a')
    for rel, dest in [('build/xlate/totk_xlate.exe', 'totk_xlate.exe'),
                      ('build/xlate/totk_xlate.id', 'totk_xlate.id'),
                      ('toolchain/hactool/hactool.exe', 'hactool.exe')]:
        shutil.copy2(source / rel, artifact / dest)
    licenses = artifact / 'licenses'
    licenses.mkdir()
    for rel, dest in [('LICENSE', 'TotK-LICENSE.txt'),
                      ('THIRD_PARTY_NOTICES.md', 'THIRD_PARTY_NOTICES.md'),
                      ('tools/vendor/ryujinx/LICENSE.txt', 'Ryujinx-LICENSE.txt'),
                      ('toolchain/hactool/LICENSE', 'hactool-LICENSE.txt')]:
        p = source / rel
        if not p.is_file():
            sys.exit(f'Missing license: {rel}')
        shutil.copy2(p, licenses / dest)
    for root in [source / 'runtime', source / 'tools/vendor/ryujinx',
                 source / 'toolchain/src/hactool']:
        for p in root.rglob('*'):
            if p.is_file() and p.name.upper().startswith(('LICENSE', 'COPYING', 'PATENTS')):
                dest = licenses / p.relative_to(source)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)
    shutil.copy2(Path(__file__), artifact / 'ci_public_build.py')
    # Scan each staged file using upstream's content boundary check. Upload only
    # this small staging directory, never build/, generated/, caches or logs.
    import check_content
    for p in artifact.rglob('*'):
        if p.is_file():
            problems = check_content.problems_for(p, allow_large=True)
            if problems:
                sys.exit(f'Artifact content check failed: {p.name}: {problems}')
    files = {p.relative_to(artifact).as_posix(): digest(p)
             for p in artifact.rglob('*') if p.is_file()}
    runtime = {p.relative_to(source).as_posix(): digest(p)
               for p in (source / 'runtime').rglob('*') if p.is_file()}
    manifest = {'source_commit': sha, 'target': 'Windows x86-64, MSYS2 UCRT64',
                'local_only': sorted(LOCAL_ONLY), 'files': files,
                'runtime_sources': runtime,
                'compiler': subprocess.check_output([str(bg.CLANG), '--version'], text=True),
                'runtime_object_count': sum(len(v) for v in objects.values()),
                'note': 'Partial runtime only. No game executable or game shader cache.'}
    (artifact / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(f'Public archive: {manifest["runtime_object_count"]} runtime objects, source {sha}')


if __name__ == '__main__':
    main()

