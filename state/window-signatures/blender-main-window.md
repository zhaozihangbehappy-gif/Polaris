# Blender Main Window Signature

## Primary match
- title pattern: `*Blender*`
- class name: `GHOST_WindowClass`

## Current use
This signature is currently used for:
- Blender window discovery
- window activation
- capture targeting
- foreground-verified desktop input

## Matching notes
- prefer class-name match plus title pattern together
- do not rely on title alone if multiple Blender-related windows may exist
- store future process-name checks here when available

## Future extensions
Add when known:
- process name
- workspace-specific title variants
- false-positive cases
- preferred ranking when multiple windows match
