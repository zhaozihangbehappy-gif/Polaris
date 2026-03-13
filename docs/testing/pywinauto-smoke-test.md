# pywinauto Smoke Test

## One-command path

```bash
scripts/windows/run-pywinauto-smoke-from-wsl.sh
```

## Expected output

The script prints a Windows-side artifact directory under:

- `D:\Administrator\Documents\Playground\openclaw-upstream\artifacts\pywinauto-runs\<run-id>`

Expected files:
- `manifest.json`
- `windows.json`
- optional `error.txt`

## Pass condition

A smoke run passes if:
- Windows Python imports `pywinauto`
- UIA desktop enumeration succeeds
- window evidence is written
