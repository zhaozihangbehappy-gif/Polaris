# Blender Focus Recovery

## Trigger
Use this playbook when:
- foreground verification fails
- another application steals focus
- desktop input would be unsafe if continued blindly

## Recovery sequence
1. stop further unsafe input
2. re-enumerate windows
3. locate Blender by class/title signature
4. activate Blender explicitly
5. capture current window state
6. confirm expected window rect and title
7. retry only the bounded next action, not the whole sequence blindly

## Safety rule
If Blender cannot be re-targeted with high confidence, fail closed and require operator review instead of guessing.

## Why this exists
Focus loss is one of the main causes of GUI automation fragility. This playbook turns that common failure into a standard recovery path.
