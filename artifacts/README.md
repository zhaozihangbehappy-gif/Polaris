# Artifacts Index

## Purpose

This folder is a lightweight index, not the main storage location for large binary outputs.

The canonical delivery payload currently lives outside this repository on the Windows side.

## Canonical external delivery folder

- `D:\Administrator\Documents\Playground\openclaw-upstream\artifacts\delivery\`

## Known delivery files

- `cabinet-12cell-concept.blend`
- `cabinet-12cell-parameter-summary.txt`
- `2026-03-12-work-summary.md`
- `CAM_Assembly_Iso.png`
- `CAM_Exploded.png`
- `CAM_Front.png`
- `CAM_Part_A.png`
- `CAM_Part_B.png`
- `CAM_Top.png`

## Why these are not committed here yet

- the current repository is being kept lean while structure stabilizes
- some assets are large binaries or generated outputs
- this repo currently acts as an index and planning surface for the broader local workflow

## Included index files

- `cabinet-12cell-manifest.md`
  - per-file manifest for the 12-cell cabinet delivery set
  - records purpose, output type, and current status for each known artifact

## Related external artifact folders

The broader local workflow also now writes evidence outside this repo under the Windows-side upstream tree, for example:

- `D:\Administrator\Documents\Playground\openclaw-upstream\artifacts\captures\`
- `D:\Administrator\Documents\Playground\openclaw-upstream\artifacts\pywinauto-runs\`

## Recommended next step

Add richer second-layer manifests later, for example:

- source file
- generated date
- producing script or workflow
- validation status
- whether a smaller public-safe copy should live in Git
- file size / checksum / provenance details
