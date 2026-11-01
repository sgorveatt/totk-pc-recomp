# Experimental PR builds with GitHub Actions

This fork's **Experimental PR public components** workflow is manual (`workflow_dispatch`)
and callable from another workflow (`workflow_call`). It checks out the complete upstream
PR head at a reviewed commit, not a patch applied to the fork's main branch. It never merges
or publishes the experimental changes upstream.

The first target is [PR 89](https://github.com/valentderah/totk-pc-recomp/pull/89), commit
`195746a58a8051451c22e3e42757881e8e958f3c`, based on 0.2.8. This contains `shadow_scale`,
`shadow_range`, `contact_shadows`, `pcss`, `aniso` and translator patches
`0010-pcss-for-cascade-compares.patch` and `0011-shadow-filter-spread.patch`.

## Run in GitHub

Open the fork's Actions tab, enable Actions if GitHub presents the fork notice, select
**Experimental PR public components**, then **Run workflow** on `main`. Leave PR number
`89` and its full commit hash for the initial run. For a later PR revision, inspect its
changes and enter the new full head hash. A changed PR head stops the workflow rather
than silently building different code. Other PRs may require adapting the split builder
if they add new dependencies or generated-header consumers.

The Windows job uses GitHub's `windows-2025` runner, .NET 10 and MSYS2 UCRT64. It builds:

- `totk_xlate.exe` and `totk_xlate.id` from the PR's patched translator source, then runs
  upstream's synthetic shader smoke test and SPIR-V validator.
- The pinned, patched hactool, including its no-keys startup check.
- `libtotkrt-public.a`, a partial runtime archive. It excludes `romfs.c`, `patches.c`,
  `ov_zstd.c`, `memory.c`, `loader.c` and `frame_rate.c`; these need locally generated
  headers. It also excludes generated modules and module glue.

The helper directly uses `tools/build_game.py`'s Ninja generator. Calling upstream's
`--make-runtime-lib` unchanged would still require `generated/<version>/layout.json`,
module manifests and layout headers. No synthetic game layout is supplied in Actions.

The artifact contains only explicitly staged public binaries, the finish helper, checksums,
source/compile metadata and licenses. It expires after seven days. No game input is accepted;
no game extraction, lifting, game shader preparation, portable game packaging or executable
linking runs in Actions. There are no game-file secrets, self-hosted runners or build-output
caches. The jobs have read-only repository permission, and checkout credentials are removed.
Existing upstream Actions consist only of `.github/workflows/content-guard.yml`.

## Finish on Windows, in a new folder

The artifact is **not a playable build or a complete installer**. Substantial game-generated
C compilation remains local. Do not copy these files into your working installation or run
an installer against it. Use a new source folder and a new save/profile directory throughout.

1. Download the successful run's `public-windows-pr-89-...` artifact and extract it to a new
   folder, for example `C:\TotK-Shadow-Test\public-components`.
2. Create a separate source checkout at the artifact's exact commit:

   ```powershell
   git clone https://github.com/valentderah/totk-pc-recomp.git C:\TotK-Shadow-Test\source
   Set-Location C:\TotK-Shadow-Test\source
   git fetch origin pull/89/head
   git checkout --detach 195746a58a8051451c22e3e42757881e8e958f3c
   ```

3. Follow `docs/building.md` in that checkout for MSYS2 UCRT64 dependencies and the two
   Python environments. Use the artifact's `msys2-packages.txt` and compiler version in
   `manifest.json` to match the build tools. This archive uses MSYS2's C++ runtime; do not
   mix it with an llvm-mingw release/installer toolchain. If exact package versions are no
   longer available, use a normal local runtime rebuild instead of assuming compatibility.
   With the prebuilt translator, the local finish does not itself require NativeAOT/.NET
   or Visual Studio. Extraction and generated-C compilation still need local tools.
4. In this **new checkout only**, copy `config.example.toml` to `config.local.toml` and set
   the paths to your own base game, update and console keys. Enter paths locally; do not
   paste key values into chat, GitHub or logs. Run the documented extraction step. Do not
   create a junction or hardlink to the existing installation's build or save folders.
5. Copy the public tools into the new checkout and generate your game code locally:

   ```powershell
   New-Item -ItemType Directory -Force build\xlate,toolchain\hactool | Out-Null
   Copy-Item ..\public-components\totk_xlate.exe, ..\public-components\totk_xlate.id build\xlate
   Copy-Item ..\public-components\hactool.exe toolchain\hactool
   # Extraction, with config.local.toml already set:
   .venv-py314\Scripts\python tools\extract.py
   .venv\Scripts\python recomp\gen.py --exefs build\extracted\v143\exefs --out generated\v143 --patches recomp\patches-v143.txt
   .venv-py314\Scripts\python tools\make_romfs_patches.py --version v143
   # Finish helper verifies the commit, runtime source files and artifact checksums.
   .venv\Scripts\python ..\public-components\ci_public_build.py finish --source . --artifact ..\public-components --jobs 2 --version v143 --out build\shadow-test --profile build\shadow-test-profile
   .venv-py314\Scripts\python tools\prepare_shaders.py build\shadow-test --version v143
   ```

   Fetch the pinned reference project using `tools/fetch_refs.sh` as documented before
   shader preparation. Use `v121` or `v111` consistently if needed, but PR 89's cascade
   range patch is only implemented for 1.4.3. Two compile jobs keep memory pressure lower
   on a 16 GB machine. Follow the disk requirements in `docs/building.md` (about 60 GB).

6. Run `build\shadow-test\totk.exe --selftest`, then the runtime probes described in
   `docs/building.md`, and launch that new executable. It uses its own profile path above.
   If testing an existing save, make a separate copy into the new profile; retain the original.
   Shader preparation and GPU pipeline warming must happen on the local machine.

## Visual testing

Keep a baseline with `shadow_scale=1`, `shadow_range=100`, `contact_shadows=0`, `pcss=0`
and `aniso=game`. Compare the same scene and camera with `shadow_scale=2` first, then
enable each other feature separately. Record frame time, crashes and visual differences.
Test sunlight, night, caves/Depths, distant trees, inventory edges and dense grass.
The PR author reports limited platform/scene coverage; Actions' synthetic test does not
exercise the new PCSS path on game shaders, the contact pass, GPU drivers or gameplay.
Do not redistribute the final executable, lifted code, extracted files or game shader caches.

## Verification and limits

Success in Actions proves that the public source compiles and the translator passes its
synthetic smoke test. It does not prove that the final game links or runs. The partial
archive/finish integration still requires a local game build for end-to-end validation.
If it fails, retain the isolated test folder and logs and rebuild normally using the same
source commit; do not overwrite the working installation. A full local build is the fallback:

```powershell
.venv\Scripts\python tools\build_game.py --version v143 --jobs 2 --out build\shadow-test-full --profile build\shadow-test-full-profile
```

