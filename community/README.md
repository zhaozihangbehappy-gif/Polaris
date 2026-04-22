# Community channel

This directory holds the community-verification state for Polaris.

## Three pools, one runtime library

The Polaris lookup tool loads all three of these at runtime; each match carries a `tier` field so the caller can tell them apart.

- `experience-packs-v4/` — **official**. Entries here went through the internal `evidence_writer` verified-live path (real agent on hermetic harness). This is the A-tier verified_live pool — not touched by the community channel.
- `experience-packs-v4-community/` — **community**. Candidates that received ≥ 2 independent confirmations through this channel land here. They ship to users on update but are tagged `tier: community`, not `tier: official`.
- `experience-packs-v4-candidates/` — **candidate**. Sandbox-reproducible or freshly submitted patterns, not yet confirmed. Surfaced by lookup with `tier: candidate` so users can try them and report back.

Promotion through this channel moves a pattern from `candidates/` to `community/`. It does **not** write to `experience-packs-v4/`, and does not change the A/B/D validator metrics, which remain governed by the internal evidence_writer contract.

## Flow

1. A user submits a candidate pattern → lands directly in `experience-packs-v4-candidates/community/<timestamp>-<hash>.json` (shape check must pass). Shape-invalid submissions are quarantined in `community/inbox/`.
2. Other users who run into the same failure and find the candidate helped them log a confirmation → `community/validations/<pattern_id>.jsonl`.
3. Users who find a candidate wrong or harmful log a reject → `community/rejects/<pattern_id>.jsonl`.
4. A candidate is eligible for promotion to `experience-packs-v4-community/` when:
   - it has ≥ 2 confirmations from **distinct** `validator_fingerprint`s,
   - none of those fingerprints equals the original `contributor_fingerprint` (upstream-authored records carry the sentinel `upstream_authored`, so no real user fingerprint can collide),
   - it has zero reject entries.
5. Run `scripts/polaris_community.py promote`. Promoted candidates are moved out of the candidate pool into the community pool and logged in `community/promoted/`.
6. A promoted pattern can be demoted back to candidate by a maintainer by deleting its record from `experience-packs-v4-community/` and restoring it to the candidate shard; accumulated rejects persist.

## Identity and trust

`contributor_fingerprint` and `validator_fingerprint` are sha256 prefixes of a per-host salt file at `~/.polaris/contributor_salt`. This is a light sybil deterrent, not a strong one. A determined attacker with multiple machines or VMs can produce multiple fingerprints. The intent is to make accidental self-confirmation impossible and casual farming annoying, not to resist a motivated adversary. Promotion is human-reviewable (`promote --verbose`), not an automatic merge.

## Files

- `inbox/` — quarantined submissions that failed shape check.
- `validations/<pattern_id>.jsonl` — one line per confirmation.
- `rejects/<pattern_id>.jsonl` — one line per reject.
- `promoted/<pattern_id>.json` — audit log for each promotion.
