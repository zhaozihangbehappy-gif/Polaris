# Candidate pool

Patterns in this directory are **candidates**. They are loaded at runtime by the lookup tool and surfaced alongside official and community-verified patterns, but each match is tagged `tier: candidate` so callers can weight them accordingly.

- Upstream-authored candidates (currently: the 21 sandbox-valid entries under `node/`) carry `contributor_fingerprint: "upstream_authored"` — a sentinel that blocks any real user fingerprint from counting as the "original contributor" during promotion checks.
- Community-submitted candidates land under `community/` and carry the submitter's real `contributor_fingerprint`.
- To promote a candidate, it must receive ≥ 2 confirmations from distinct non-contributor fingerprints and zero rejects. Promotion moves it to `experience-packs-v4-community/`, not to `experience-packs-v4/`. See `community/README.md`.
