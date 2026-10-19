# Copilot CLI bridge (opt-in)

`brainspace_copilot_bridge.py` runs GitHub Copilot CLI through a local TokenMaster bridge.
The bridge applies the two request changes that PRS-4 measured: the cache-stable system
prompt and v6 shaping. Copilot CLI keeps its full tool set.

## How it works

- Copilot CLI has a bring-your-own-key (BYOK) mode. In this mode, it sends every model
  request to `COPILOT_PROVIDER_BASE_URL`.
- The launcher starts the bridge on `127.0.0.1`. It sets `COPILOT_PROVIDER_BASE_URL` to the
  bridge for the Copilot CLI process only.
- The bridge forwards each request to one upstream. The upstream is `--upstream`, or the
  `COPILOT_PROVIDER_BASE_URL` that was set before the launcher started.
- The bridge changes each Responses request in two ways:
  1. **Cache-stable system prompt.** The bridge moves Copilot CLI's `Session folder:` line
     from the system prompt to the first user message. Every session in a repository then
     sends the same system prompt. A new session's first call can read it from the provider's
     cache.
  2. **v6 shaping.** The bridge shapes grep, glob and whole-file view results with
     request-policy-v6. Other tool results, such as shell output, pass through unchanged.
- Both changes are deterministic. The bridge applies them again on every call, so each call
  of a session sends the same bytes for its earlier messages. The provider's prefix cache
  stays valid.
- The bridge does not read, store or add credentials. It forwards the client's headers,
  including `Authorization`, to the upstream.
- With `--log <file>`, the bridge writes one JSON line per model request. The line holds
  usage numbers and hashes only. It holds no request or response content.

## Install and run

1. Install TokenMaster for Copilot:
   `python brainspace_setup.py --host copilot --python <runtime> --tokenizer-file <cl100k_base.tiktoken>`.
   This step copies the bridge and the verified tokenizer to `<COPILOT_HOME>/token-master/`.
2. Configure the Copilot CLI BYOK provider as usual: `COPILOT_PROVIDER_BASE_URL`,
   `COPILOT_MODEL` and the provider key variable. The provider must accept OpenAI Responses
   requests at `<base URL>/responses`.
3. Start Copilot CLI through the bridge:
   `python <COPILOT_HOME>/token-master/brainspace_copilot_bridge.py -- copilot`

To run the bridge without Copilot CLI, omit `-- copilot`. The bridge then prints the base URL
to use.

## Requirements and limits

- The bridge works in BYOK mode only. Copilot CLI's default GitHub model routing has no setting
  for its API URL, so the bridge cannot sit in front of it.
- `COPILOT_PROVIDER_TYPE` must be `openai` (the default). The launcher sets
  `COPILOT_PROVIDER_WIRE_API=responses` and refuses other provider types and wire APIs.
- v6 shaping needs the verified cl100k tokenizer. Without it, the bridge still applies the
  cache-stable system prompt, and it prints a warning.
- The cache saving needs another session in the same repository within the provider's cache
  lifetime. The cache probes put that lifetime between 6.5 and 31 minutes.
- Copilot CLI keeps the unshaped results in its own history. The bridge changes only what the
  provider receives.
- The bridge does not supply credentials for any provider. The live check below used the GitHub
  Copilot API through an evaluation relay that added the credential, as the PRS studies did.
  TokenMaster does not ship that relay.

## Evidence

- PRS-4 measured both changes at request level (arm `tm8`). Under continuous use, billed cost
  per finished task fell 49.8% against stock (95% CI −57.1% to −42.9%). See
  [PRS4_RESULTS.md](PRS4_RESULTS.md).
- Live checks ran the real Copilot CLI with `gpt-6-astra` on October 18, 2026
  ([evidence](../../evidence/copilot-bridge-20261018/)). They are functional checks with one
  session per task, not a savings study.
  - Runs 1 and 2 and the interactive check ran Copilot CLI 1.0.78-3. The WinGet launcher
    runs this bundled build when it finds no installed package. Run 3 ran the installed
    Copilot CLI 1.0.98.
  - Without the bridge, every session sent its own system prompt. In 3 runs, 6 sessions sent 6
    different prefixes, and no first call read from the cache.
  - With the bridge, every session in a run sent the same prefix. In each run, the first bridge
    session wrote the cache. Each later bridge session's first call read 13,406 to 13,410 of
    about 13,550 input tokens from the cache.
  - The real Copilot CLI prefix (system prompt and tool definitions) was about 13,500 tokens.
    The PRS-4 study prompt was about 3,600 tokens.
  - Through the bridge, Copilot CLI made a one-line edit in runs 2 and 3. Each time,
    `git diff` showed that line and no other change. v6 shaping changed tool results in those
    sessions.
  - One short task cost 3,255 billed units (run 2) and 3,322 units (run 3) through the bridge
    with a warm start. Without the bridge, it cost 18,674 and 18,654 units. These are single
    pairs of sessions, not a measured saving.
  - An interactive Copilot CLI session in a terminal ran through the launcher. Its 2 model calls
    both had the cache-stable system prompt. It answered correctly, and `/exit` ended it with
    exit code 0.
