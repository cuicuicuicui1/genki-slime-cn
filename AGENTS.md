# Contributor / agent constraints

- GBA first game only. Do not mix NDS tools or data.
- Keep the exact source SHA gate; no ROM/BIOS/save downloads or uploads.
- Build only with `tools/project.py` into a NEW `--out` directory; never overwrite originals or existing deliveries.
- Public entry points must not depend on private history directories, machine paths, old ROMs or manifests.
- `data/gba-font-ids.json` is append-only: save names contain persistent u16 IDs.
- Preserve source controls/dynamic fields and source-qualified canonical name guards.
- ARM7TDMI/ARMv4T only; verify veneers and branch range, avoid accidental Thumb-2/BLX.
- GBA byte VRAM stores are not ordinary RAM. Preserve BG/OBJ sharing, tile0 and dynamic digit/name scratch.
- Source/caller fingerprints, paired atlas/map loading, write bounds and final readback are required.
- Published root BPS and v20 Release are immutable artifacts. Candidates do not inherit old runtime evidence.
- Run ROM-free tests and public-tree audit. Optional source/native checks require the owner's ROM locally, never in CI secrets.
- Separate static, controlled-fixture and natural-input evidence; do not claim full playthrough/save compatibility.
- Upstream is a pinned fetched dependency, not vendored. Preserve font notices and avoid a blanket font license for the repo.
