# GitHub Auth Runbook

## Current state

- Repository remote has been converted from HTTPS to SSH.
- Local SSH key file:
  - `~/.ssh/id_ed25519_github_northern_lights`
- Local SSH config uses GitHub over port 443:
  - host: `github.com`
  - endpoint: `ssh.github.com:443`

## Why port 443 is used

Some networks block outbound SSH on port 22. GitHub supports SSH over 443 through `ssh.github.com`.

## Public key that must exist in GitHub

```ssh
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAywUcMmv2TzhGShMpWJRwZnLiEMBuhkUAd0KnUUKDM3 zhaozihangbehappy-gif@github-northern-lights
```

## GitHub UI path

- Avatar
- Settings
- SSH and GPG keys
- New SSH key
- Paste the public key

## Verification command

```bash
ssh -T git@github.com
```

Expected success shape:

```text
Hi <username>! You've successfully authenticated, but GitHub does not provide shell access.
```

## Current failure shape if not fully configured

```text
git@ssh.github.com: Permission denied (publickey).
```

If that appears, verify:

1. the key was added to the correct GitHub account
2. the pasted key exactly matches the local `.pub` file
3. no extra spaces or truncation were introduced
4. GitHub finished saving the key

## Token note

A previously used classic token was exposed in chat and should be revoked from GitHub settings.
