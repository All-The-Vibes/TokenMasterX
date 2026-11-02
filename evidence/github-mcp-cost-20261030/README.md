# What the built-in GitHub MCP server adds to each Copilot CLI request (2026-10-30)

`probe.py` captures the first request of a stock Copilot CLI session without a model call; `billing.py` then reads
what GitHub bills for the same comparison (four real calls). Every TokenMaster study passed `--disable-builtin-mcps`
in both arms, and the launcher does not add it, so no study measured this slice.

Setup: Copilot CLI 1.0.105 pinned with `COPILOT_CLI_DIST_DIR`; an isolated home signed in to the operator's account
(its `config.json` names the account, the token stays in Credential Manager); BYOK mode left online (no
`COPILOT_OFFLINE`) and pointed at a local server that records each request and answers 502. The two arms differ only
in `--disable-builtin-mcps`. Two sessions per arm and wire; each session sent its request 6 times (retries) with
identical sizes. Sizes are cl100k tokens as sent (compact JSON). Lanes and raw captures are in
`C:\tm-lanes\gh-mcp-probe`, outside the repository.

| Wire, model | Arm | Request | Tool definitions | Deferred | Tools |
|---|---|---:|---:|---:|---:|
| OpenAI Responses, `gpt-6-astra` | built-in MCPs on | 21,388 to 21,393 | 14,527 | 6,086 | 23 |
| | off | 14,397 to 14,399 | 8,001 | 0 | 20 |
| Anthropic Messages, `claude-opus-5.5` | on | 20,851 to 20,853 | 14,681 | 6,093 | 41 |
| | off | 13,690 | 7,956 | 0 | 21 |

What "on" adds on the OpenAI wire (`results-openai-1.0.105.json`):

- a `namespace` tool named `github-mcp-server` holding 18 functions, each with `defer_loading: true` (6,095 tokens,
  6,086 of them the functions);
- `web_search` (425) and `{"type": "tool_search"}` (6);
- a `<github-mcp-server-*>` guidance block in the system message (+226 to +232);
- a `<system_reminder>` user item that lists the deferred tools and tells the model to search first (241).

Request difference, each run against its own counterpart: +6,991 to +6,994. With the deferred functions deleted
from the body: +924 to +927 (counting them one by one gives 6,086 and +905 to +908).

On the Anthropic wire (`results-anthropic-1.0.105.json`): the same 18 functions as flat tools with
`defer_loading: true` (6,093 counted one by one), a client-side function `tool_search_tool` (223), `web_search`
(418), system text +214 to +216, and the same reminder as a text block in the first user message (221). The
`cache_control` marker moves from `task` to `tool_search_tool`, so `task` counts 9 tokens fewer. Request
difference: +7,161 to +7,163. With the deferred tools deleted: +1,086 to +1,088.

Copilot CLI's own count in `session.shutdown` includes the deferred definitions: `toolDefinitionsTokens` 13,738 vs
7,238 on the OpenAI wire and 16,839 vs 9,039 on the Anthropic wire, in every run.

What deferral means for cost, from the providers' documentation (not measured here):

- OpenAI, https://developers.openai.com/api/docs/guides/tools-tool-search: for a namespace "the model sees only the
  namespace or server name and description at the beginning" (a standalone deferred function still shows its name
  and description; Copilot sent a namespace). The page does not state how deferred definitions are billed.
- Anthropic, https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool: "`defer_loading`
  controls what enters the context window, not what you send in the request"; the API "excludes deferred tools from
  the system-prompt prefix", and definitions that a search loads "count as input tokens like any other tool
  definition". A custom search tool that returns `tool_reference` blocks is supported, which is what
  `tool_search_tool` appears to be.

So the server's up-front cost is about 0.9k (OpenAI wire) to 1.1k (Anthropic wire) cl100k tokens per request if the
backend honors deferral, and about 7.0k to 7.2k if it does not. Neither page says outright that unloaded definitions
are not billed, so that step is inferred. The billed check below settles it for default routing.

## What GitHub bills under default routing (`billing.py`, `billing-1.0.105.json`)

One real session per arm and model (four calls, $0.51 in total), Copilot CLI 1.0.105, default GitHub routing, each in
its own signed-in lane; the prompt asks for a one-word reply and every session made one main call and replied "ok".
Input tokens are GitHub's own (`assistant_usage_events.input_tokens`); "estimate" is Copilot CLI's own
`session.shutdown.currentTokens` for the same session.

| Model, endpoint | Billed input, server on | off | Server's billed cost | Estimate on / off | Estimate's difference |
|---|---:|---:|---:|---:|---:|
| `gpt-6-astra`, `ws:/responses` | 14,663 | 13,544 | +1,119 (+8.3%) | 20,703 / 13,765 | +6,938 |
| `claude-opus-5.5`, `/v1/messages` | 24,773 | 22,944 | +1,829 (+8.0%) | 24,500 / 16,172 | +8,328 |

The server was loaded under default routing. In the "on" arm the session checkpoint lists all 18
`github-mcp-server-*` tools (none in "off"), the request grew by 31,117 bytes (gpt-6-astra) and 31,406 bytes
(claude-opus-5.5), and `toolDefinitionsTokens` rose by 6,500 and 7,800, as in the captures. Each session made one
call, and model, prices and premium-request multiplier match within each pair. GitHub billed +1,119 and +1,829 input
tokens for the server, far less than the deferred definitions would add if they were charged, so they are not billed
up front on either model. The bill cannot tell deferral from GitHub dropping the deferred definitions, and whether a
tool search can load them under default routing was not tested.

Copilot CLI's own `currentTokens` estimate against the bill, per session:

- gpt-6-astra: 13,765 vs 13,544 without the server (+221), 20,703 vs 14,663 with it (+6,040).
- claude-opus-5.5: 16,172 vs 22,944 without the server (-6,772), 24,500 vs 24,773 with it (-273).

Copilot's per-call `toolTokenCount` rose only 430 (gpt-6-astra) and 775 (claude-opus-5.5) with the server on.

Compare input tokens, not dollars: the claude-opus-5.5 "on" call read 17,374 tokens from GitHub's prompt cache,
warmed by something outside this check, and cost $0.04 against $0.11 for the "off" call. The $0.51 is AI credits
(token billing). Each call also counted the same premium requests in both arms (1 for gpt-6-astra, 15 for
claude-opus-5.5), so under premium-request billing the server adds nothing. One call per arm, first call only: later
calls carry the same tokens mostly as cache reads (0.1 times the input price for gpt-6-astra, 0.05 for
claude-opus-5.5), and tool definitions that a search loads are not included.

Limits of the capture: BYOK, not default routing (default routing goes to GitHub's API, which the capture server never sees); one CLI
version; one account, on GitHub Enterprise Cloud (microsoft.ghe.com), whose remote server supplied the 18 tools and
`web_search`, so a github.com account may differ; first request only, so definitions a search loads, which then ride
on every later call, are not counted; text a provider adds for its own tool search is not visible. Copilot's own
counts differ from cl100k by -10% (OpenAI wire) to +14% (Anthropic wire) on the same tool sets, so the gap between the
wires is within tokenizer error. The lane path names the arm but adds no tokens; runs of one arm differ by up to 5
tokens (random session id and `prompt_cache_key`). An earlier pair of OpenAI-wire sessions per arm (raw captures in
`C:\tm-lanes\gh-mcp-probe\1.0.105`) gave the same sizes within 9 tokens; its results file was replaced by
`results-openai-1.0.105.json`.
