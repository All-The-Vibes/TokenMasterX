# Retracted: V5 isolated sandbox savings report

**Retracted on October 18, 2026.** This report claimed whole-task savings of up to
83.29% for `request-policy-v5` combined with graph routing. It also reported
73.19% for v5 alone, 44.20% on Copilot CLI and 43.14% on `claude-sonnet-5.5`.
All of these numbers are withdrawn.

## Why

1. The synthetic modules were padded with 238 repetitive lines per function, so
   compaction removed about 99% of each file. Real repository files compact about
   77% per file.
2. Arms without graph routing were told to read 7 files in a fixed order,
   including decoys.
3. The questions asked only for top-level constants, and the prompt told the model
   not to call recovery.
4. Baseline arms were also given two unused recovery tools.
5. The first Headroom adapter never compressed anything. The second one overrode
   Headroom's default tool exclusions.
6. Prompt caching was ignored. Baseline input was 99.9% cached, because an
   identical earlier run had warmed the prefixes. v5 rewrites earlier messages,
   which breaks the cache.

## What replaced it

A pre-registered study on real tasks: [PRS1_RESULTS.md](PRS1_RESULTS.md), with
its protocol in [PRS1_PROTOCOL.md](PRS1_PROTOCOL.md). Across 12 real tasks and 252
live sessions:

- No TokenMaster configuration significantly reduced total tokens.
- v5 raised cache-weighted cost by 61.6% (95% CI +19.6% to +111.0%).

The original evidence remains in `evidence/isolated-sandbox-savings-20261017/` for audit.
