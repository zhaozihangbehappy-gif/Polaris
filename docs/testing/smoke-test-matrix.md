# Smoke Test Matrix

## Purpose

This matrix defines the smallest test surface needed to push the execution layer toward 100/100 reliability.

## Test groups

### A. Git / GitHub auth
- SSH auth over 443 succeeds
- repository remote is correct
- fetch succeeds
- push dry-run or safe push path succeeds

### B. Desktop bridge
- bridge endpoint reachable
- auth accepted
- window enumeration works
- target window activation works
- capture works
- harmless move/click works with foreground verification enabled

### C. Blender bridge
- Blender launches
- bridge/addon available
- simple query succeeds
- simple write/read-back succeeds

### D. Hybrid GUI + scene-state
- Blender window found
- desktop input performed
- Blender state query confirms expected result

## Minimum pass rule

No workflow should be promoted to "stable" until:

- all prerequisite smoke tests pass
- the workflow passes at least 3 consecutive runs in its target environment

## Recommended next extension

Expand later into a regression matrix covering:

- DPI variation
- window size variation
- focus loss
- modal interruption
- unexpected layout state
