> *Plain-language summary of this phase: see [the build story](README.md#entry-34), entry 34.*

# Prompt 34 — A cap on model calls: plan

**Status:** approved by Dermot on 18 November 2026: D1 to D11 as recommended (the daily ceiling 30); O1 yes; O2 yes (a per-caller share of the day, 12); O3 no. Each step that writes to a deployed system waits for his go-ahead at the time. The plan below is as it was approved.

**Written:** 18 November 2026.

---

## Summary

Two limits, both kept in the database, both checked before anything else happens:

- **per caller:** 5 model-calling actions in any 10-minute window;
- **across everyone:** 30 model-calling actions per day (UTC).

A refused action gets HTTP 429 with one of two sentences, writes nothing, and calls no model. The caller is identified by a daily salted hash of the network address; the address itself is never stored or logged. If the counter cannot be read, the action is refused (fail closed). Dermot runs his own demonstration by raising the daily setting for the day with one command.

Decisions for Dermot are in §13. The two I most want read are **D3** (what the hash protects and what it does not) and **D9** (how this work sits on `main` beside the held branch).

---

## 1. Every route that causes a model call, and where each is counted

Surveyed from the code. A model is called in exactly four places, the four agents' `self._provider.complete(...)` (`agents/doc_parser.py`, `validator.py`, `adjuster.py`, `guardrail.py`). Those are reached by seven entry points and no others:

| Entry point | Model calls | Counted as | Where the count is taken |
|---|---|---|---|
| `POST /api/pipeline/run/{claim_id}` | 4 (3 for a fixture claim) | 1 action | first statement of `run_pipeline` |
| `POST /api/pipeline/replay/{claim_id}` | 4 (3 for a fixture claim) | 1 action | first statement of `replay_pipeline` |
| `POST /api/agents/test/doc-parser` | 1 | 1 action | first statement of the handler |
| `POST /api/agents/test/validator` | 1 | 1 action | first statement of the handler |
| `POST /api/agents/test/adjuster` | 1 | 1 action | first statement of the handler |
| `POST /api/agents/test/guardrail` | 1 | 1 action | first statement of the handler |
| MCP `run_scenario` | 4 (3 for the fixture scenario) | 1 action | first statement of the tool body, before the claim is submitted |

`run_scenario` and the two pipeline endpoints all end in `execute_run`, but the count is **not** taken there: `run_scenario` submits a new claim before it reaches `execute_run`, and the prompt requires that a refused action writes no claim. So each entry point reserves its own action, and `execute_run` counts nothing. No entry point calls another, so nothing is counted twice.

**Not counted, and never limited** (no model call): every `GET`; `POST /api/claims` (stores a claim, calls no model); `POST /api/claims/{id}/human-decision`; `GET /api/pipeline/stream/{id}`; `GET /api/agents/{agent}/prompt`; `GET /api/audit/verify/{id}`; the eight read tools of the MCP server, `verify_chain` among them; `/health`; CORS preflight requests. The Validator's embedding of the claim text runs inside the backend on its own processor and costs nothing at the provider.

### What each special case counts as

| Case | Counts as | Why |
|---|---|---|
| A run that includes the demonstration fixture's Adjuster step | 1 action | The other three agents still call the model |
| A run that aborts part-way, or whose provider call fails | 1 action | Calls were made or attempted |
| A request refused by the limit itself | nothing | Nothing was started |
| A request that passes the limit and is then refused before a run starts: unknown claim or variant (404), a claim closed by a person or with a run in flight (409), the tool's `not_a_scripted_claim`, `claim_closed`, `run_in_flight` | nothing: the reservation is given back | No model was called |
| A request whose body fails validation (422) | nothing | FastAPI refuses it before the handler runs |

**Unit: one action, unweighted.** A test-bench probe (one call) counts the same as a run (four). Simple to state, simple to explain in a sentence, and conservative: the arithmetic in §4 assumes every action is a full run. The alternative, counting model calls (a run 4, a probe 1), is **D2**.

### Reserve, then confirm or give back

One mechanism for all seven entry points:

```
reservation = limiter.reserve(caller)      # atomic; raises LimitReached → 429. Nothing else has run.
... the existing checks, unchanged, in their existing order ...
reservation.confirm()                      # immediately before the model-calling work
# leaving the block without confirm() gives the reservation back
```

This satisfies three of the prompt's requirements at once: the refusal comes before the checks that would start a run; an action is counted where the call is caused; and a request refused for another reason costs the caller nothing. If giving back fails (the database drops between the two steps), the count stays spent and a warning is logged: the error is in the safe direction.

---

## 2. The caller's address: how it is obtained, what is trusted, what is stored

### How it is obtained

Uvicorn is started without proxy settings on both deployments (`Dockerfile`, `render.yaml`), so `request.client` is the address of the proxy in front, not the visitor. Both front doors pass the visitor's address in the `X-Forwarded-For` header, a comma-separated list to which each proxy appends the address it received the connection from.

The rule: **count in from the right.** A new setting, `rate_limit.trusted_proxy_hops`, says how many proxies stand in front of the backend. The caller's address is the entry that many places from the right-hand end of the list. Everything to the left of it was supplied by the caller and is ignored.

| Deployment | Expected hops | Basis |
|---|---|---|
| Local | 0 (the default): the header is ignored and the socket's peer address is used | no proxy |
| Azure Container Apps | 1 | one managed ingress in front; it appends the peer address |
| Render | not known; to be measured | Render's proxy, with a content-delivery network in front of it |

I am not asserting the Azure or Render numbers from memory. **They are measured before they are set**, by a method that reveals no address: the limiter's log line (below) carries the *number* of entries in the header, never their values. One ordinary request from Dermot's browser to each deployment gives the hop count. A second request to Azure with a made-up left-hand entry confirms that the ingress appends and does not replace (the count rises by one and the limiter's behaviour does not change). Until the value is set on a deployment the default of 0 applies there, which means every visitor shares one per-caller count: stricter than intended, never looser.

### What a caller could forge, and what happens

| Attempt | Result |
|---|---|
| Sends their own `X-Forwarded-For` | Their entries sit to the left of the trusted ones and are ignored |
| The setting is one too high (an operator's error) | The caller's forged entry would be trusted, and the per-caller limit could be escaped. The daily ceiling still holds. This is why the value is measured, and why a test covers it |
| The setting is one too low | Every visitor is counted as the proxy: one shared count. Safe |
| The header is absent or has fewer entries than the setting | The socket's peer address is used. Safe: shared count |
| The entry is not an address | One shared key, `unknown`. Safe |
| Changes address (a VPN, a mobile network, many machines) | The per-caller limit is escaped. **The daily ceiling is the limit that holds against this**, and is the reason there are two |
| An IPv6 caller cycling through their own block | Before hashing, an IPv6 address is cut to its first 64 bits, the block one subscriber is normally given, so the whole block is one caller |

Several visitors behind one office or mobile address share a count. Accepted for a demonstration.

The MCP tool body has no request, so `run_scenario` has no address to read. Its caller key is the token's label (`mcp:shared-token`), which is not personal data and is stored as it is. It counts against the same daily ceiling as everyone.

### What is stored

Never the address. The key stored for a caller is

```
HMAC-SHA256(key = that day's salt, message = the normalised address), as 64 hexadecimal characters
```

- **The salt** is 32 random bytes, made by the first counted request of each UTC day and kept in the database (`usage_salts`), because a salt held in memory would differ between replicas and vanish on restart, and the counts would be wrong for the reason the prompt gives.
- **How long:** a caller's count row is useful for ten minutes and kept until the day after its window. A salt is useful for its own day.
- **How it is removed:** the first counted request of each UTC day, and each start-up, deletes every salt for an earlier day and every count row whose window began more than a day ago. Once a day's salt is deleted, that day's hashes cannot be recomputed by anyone; the rows that held them are deleted in the same statement.
- **Logs:** the limiter writes one structured line per decision: the route, the outcome (`allowed`, `refused_caller`, `refused_daily`, `unavailable`), the two counts after the decision, and the number of entries in the forwarding header. No address and no hash.
- **Audit trail, `mcp_tool_calls`, repository:** unchanged; nothing about the caller is written to them.

**What this does not protect against, stated plainly (D3).** During the day, the salt and the hashes are in the same database. A person with access to that database on that day could try all four billion IPv4 addresses against a hash in minutes and recover the address. After the day's clean-up they could not. Any scheme that lets two replicas agree on a caller has this property unless part of the key is kept outside the database. The option is a second, fixed secret from Key Vault mixed into the key, so that the database alone is never enough; it costs one more secret on each deployment. I recommend the salt alone, which is the shape the prompt names, and offer the second secret as **D3**.

If the system is idle for days (scaled to zero), the last active day's salt and rows remain until the next start-up, which happens on the next request.

---

## 3. The table, the migration, the atomic update, the clean-up

**Migration `0004_usage_limits`** (additive; no existing table or column changes; the downgrade drops both tables, which loses at most one day of counts):

```sql
CREATE TABLE usage_counters (
    scope         TEXT        NOT NULL CHECK (scope IN ('caller', 'global')),
    key           TEXT        NOT NULL CHECK (length(key) > 0),   -- the hash, the MCP label, or 'all'
    window_start  TIMESTAMPTZ NOT NULL,
    count         INTEGER     NOT NULL CHECK (count >= 0),
    PRIMARY KEY (scope, key, window_start)
);

CREATE TABLE usage_salts (
    day   DATE  PRIMARY KEY,
    salt  BYTEA NOT NULL CHECK (octet_length(salt) = 32)
);
```

Windows are fixed, not sliding: the per-caller window starts at the clock time rounded down to the period; the global window starts at 00:00 UTC. A fixed window lets a caller use the end of one window and the start of the next (up to ten actions close together). A sliding window would need a row per action; the gain is not worth the storage of more data about callers.

**The atomic update.** One statement per counter, in one transaction:

```sql
INSERT INTO usage_counters (scope, key, window_start, count)
VALUES (%(scope)s, %(key)s, %(window_start)s, 1)
ON CONFLICT (scope, key, window_start)
DO UPDATE SET count = usage_counters.count + 1
   WHERE usage_counters.count < %(limit)s
RETURNING count;
```

A row comes back when the action is allowed; none when the limit is already met. PostgreSQL takes the row's lock for the update, so two requests arriving together are served one after the other, and with a limit of one exactly one of them gets a row. The transaction increments the global counter first, then the caller's; if either returns nothing the transaction is rolled back, so a refusal changes neither count. Giving a reservation back is the reverse in one transaction (`count = count - 1 WHERE count > 0`).

A limit of zero is handled before the statement (the insert would otherwise admit one): a zero limit refuses everything, which is the off-switch for model calls.

**Why not the audit trail or `mcp_tool_calls`.** The test bench writes to neither, by design. A run's audit rows are written as the run proceeds, not before it starts, so a count read from them would let two requests through together. The audit chain records decisions on claims and must not carry bookkeeping about visitors. `mcp_tool_calls` records only MCP calls. Neither holds anything about the caller, and neither should.

**Clean-up** as in §2, inside the limiter, once per UTC day and at start-up. `conftest.py`'s `TRUNCATE` list gains the two tables.

---

## 4. The settings, their defaults, and the numbers

A new block, in `settings.py` (`RateLimitSettings`) and `settings.yaml.template`, each overridable by environment variable in the usual way:

| Setting | Environment variable | Default | Bounds |
|---|---|---|---|
| `rate_limit.enabled` | `RATE_LIMIT__ENABLED` | `true` | |
| `rate_limit.per_caller_limit` | `RATE_LIMIT__PER_CALLER_LIMIT` | `5` | ≥ 0 |
| `rate_limit.per_caller_period_s` | `RATE_LIMIT__PER_CALLER_PERIOD_S` | `600` | 60 to 86,400 |
| `rate_limit.daily_ceiling` | `RATE_LIMIT__DAILY_CEILING` | `30` | ≥ 0 |
| `rate_limit.trusted_proxy_hops` | `RATE_LIMIT__TRUSTED_PROXY_HOPS` | `0` | 0 to 5 |

**Safe when nothing is set:** the limits are on, at the proposed numbers, and no forwarding header is trusted. A deployment that receives the code and no configuration is limited, more strictly than intended (§2).

**On Azure** the five go through Bicep as the Adjuster temperature does: parameters in `main.bicep` and `main.bicepparam`, passed to `modules/containerapps.bicep`, set as plain environment values (none is a secret). **On Render** Dermot sets `RATE_LIMIT__TRUSTED_PROXY_HOPS` in the dashboard once it is measured; the other four stay at their defaults; the report records what was set.

### The arithmetic

- **Measured:** Prompt 33 measured 223 model calls at under one US dollar: under $0.0045 a call, so **under $0.018 for a four-call run**.
- **Daily ceiling of 30, held every day of a 31-day month, every action a full run:** 30 × $0.018 × 31 = **$16.74**, under the $20 limit with $3.26 to spare for Dermot's own gated tests and replays, which use the same account.
- **The theoretical worst case** is higher than the measurement: each agent's answer is capped (512, 1,024, 768 and 512 tokens: 2,816 in all) and a description may be 5,000 characters. If every answer filled its cap on every run, a run would cost about $0.026 at the provider's list prices as I recall them (to be checked against the provider's price page during the build, not relied on from memory), and 30 a day would reach about $24. The agents' answers are short structured records and do not approach their caps, so I treat the measurement as the working figure. A ceiling of **24** is under $20 even on the theoretical worst case (24 × $0.026 × 31 = $19.34). This is **D1**: 30 recommended, 24 if you want the bound to hold whatever the models do.
- **In ordinary use** most days will see a handful of actions, and test-bench probes cost a quarter of a run.

**Per caller, 5 in 10 minutes.** The three scripted scenarios are three actions; a strict re-run and a probe make five. A visitor exploring normally does not meet it; a script does at once.

One thing the per-caller limit cannot do: at 5 every 10 minutes, a single patient caller can use the whole day's 30 in an hour. A limit measured in minutes cannot prevent that, whatever its number. A per-caller share of the day (for example, no caller more than 12 of the 30) would; it is one more counter row and one more sentence. Offered as **O2**, not in the prompt.

---

## 5. The refusal in full

### The sentences, for approval

| When | Sentence |
|---|---|
| The daily ceiling is met | **Today's limit for this demonstration has been reached. Please try again tomorrow.** |
| The caller's limit is met | **You have started several runs in a short time. Please wait a few minutes and try again.** |
| The count cannot be read or written (§7) | **The system cannot check its usage limit at the moment, so nothing was started. Please try again in a minute.** |

They live once, in `backend/app/limits/messages.py`, and are used by the API and the MCP tool, so the two cannot differ. Two notes on the wording. "Tomorrow" means after midnight UTC, which for a visitor west of Greenwich is this evening; I think the plain word is better than the exact one, and say so here in case you disagree. And on the test bench the visitor has started probes, not runs; the prompt asks for the same sentence wherever it is met, so "runs" stands.

When both limits are met at once, the daily sentence is given: it is the one that tells the visitor the truth about when to come back.

### From the API

| | Daily ceiling | Caller's limit | Count unavailable |
|---|---|---|---|
| Status | 429 | 429 | 503 |
| `Retry-After` | seconds until 00:00 UTC | seconds until the caller's window ends | `60` |
| Body | `{"detail": "<the sentence>"}` | the same shape | the same shape |

Raised as one exception type, `LimitReached`, turned into the response by one handler registered in `create_app`. The body has the shape every other refusal in the API has.

### From `run_scenario`

In the tool's existing `code: message` style, raised as a `ToolError` from the first statement of the tool body, and therefore recorded by the existing wrapper in `mcp_tool_calls`, the log line and the Integrations feed with `outcome = 'error'`, as `claim_closed` is:

- `limit_reached: Today's limit for this demonstration has been reached. Please try again tomorrow.`
- `limit_reached: You have started several runs in a short time. Please wait a few minutes and try again.`
- `limit_unavailable: The system cannot check its usage limit at the moment, so nothing was started. Please try again in a minute.`

The tool's description gains one sentence: "The demonstration limits how many runs may be started in a day; when the limit is reached the tool answers `limit_reached` and nothing is run." `docs/demo-mcp.md` says the same.

### In the frontend

| Where | Today | Proposed |
|---|---|---|
| **Claims page** (*Process*, *Run again*, *Strict re-run*) | The page moves to the run page at once and sends the request from there; a refusal appears in the run page's banner | See below (**D5**) |
| **Run page banner** | "Could not start the run: " followed by the backend's text | For a 429 or the limit's 503, the sentence alone, with no prefix, followed by a link *Back to the Claims list* |
| **Agents test bench** | The backend's text in red beneath the button | The sentence, in the same place, in the notice style the other pages use. No change of behaviour, only of dress |

The Claims page needs a decision because of how it works: pressing the button navigates to the run page before the answer arrives, since the answer to a successful request arrives only when the run has finished. So the visitor who pressed the button on the Claims page meets the refusal one page on. Two ways to honour "shown where the visitor pressed the button":

- **A (recommended).** The sentence appears in the run page's banner, as every other refusal to start a run does today (a closed claim, a run in flight), with the link back. One code path, consistent with what exists.
- **B.** On a limit refusal the run page sends the visitor back to the Claims page, which shows the sentence above the table. Truer to the prompt's words, and it avoids leaving the visitor on the page of a run that does not exist; it adds a redirect and a notice that only this case uses.

The frontend learns that a refusal is the limit from the status (`ApiError.status`), which the Claims page's trigger does not keep today; it will. No sentence is written in the frontend: it shows the backend's `detail`. `Retry-After` is not read by the page (a browser hides it from a cross-origin page unless the server names it as exposed, and the page has no use for it).

**A refused action writes nothing:** no claim, no run, no audit row, no row in `mcp_tool_calls` other than the record of the refused tool call itself, and no change to either count. Tests assert each.

---

## 6. Interface-stability acknowledgement

All additive. To be recorded under *Locked interface extensions* at close-out.

1. **A new 429** on six endpoints: `POST /api/pipeline/run/{claim_id}`, `POST /api/pipeline/replay/{claim_id}`, and the four `POST /api/agents/test/*`. Body `{"detail": "<sentence>"}`, header `Retry-After`. It is returned before every other check, the 404s included, so a caller over a limit learns nothing about whether a claim exists.
2. **A new 503** on the same six, same body shape, `Retry-After: 60`, when the count cannot be read or written.
3. **Two new errors from MCP `run_scenario`:** `limit_reached` and `limit_unavailable`. The nine-tool catalogue is otherwise unchanged; the tool's description gains a sentence.
4. **Two new tables**, `usage_counters` and `usage_salts` (migration `0004_usage_limits`).
5. **Five new settings** under `rate_limit` (§4).
6. **One new log line** per limiter decision on the logger `backend.app.limits`.

**Unchanged:** the agents, the audit chain, every audit payload, every SSE event, every 200 body, every existing status code, `mcp_tool_calls`' shape, and every route that calls no model. **No new dependency:** the standard library's `hmac`, `hashlib`, `secrets` and `ipaddress`, and the existing database driver, cover it.

---

## 7. When the counter cannot be read

**Fail closed.** If the limiter cannot read or write its count (the database is down, slow past the statement timeout, or the tables are missing), the action is refused with the 503 above and the reason is logged with the error's class. Nothing is started.

The reasons: it is the project's standard; a run needs the database anyway, so failing open would start nothing useful; and for the test bench, which does not need the database for three of its four agents, failing open would turn a database fault into a period of unlimited model calls, which is the exact thing this prompt exists to prevent.

One consequence to accept: **the migration must reach each deployed database before the code does** (§10). Code that arrives first would find no table and refuse every run until the migration is applied. That is a safe failure and an avoidable one.

Switching the limits off (`RATE_LIMIT__ENABLED=false`) is the deliberate way to run without them, and it never touches the database.

---

## 8. The owner's demonstration

| Option | What it is | For | Against |
|---|---|---|---|
| **A. Raise the setting for the day** (recommended) | One command sets `RATE_LIMIT__DAILY_CEILING` (and, if wanted, the per-caller limit) on the Container App; a second puts it back. On Render, the same variable in the dashboard | No new surface, no new secret, nothing in the frontend; works for the pages and the connector alike; the day's count is kept, so putting it back restores the real position | Needs a shell signed in to Azure; each change starts a new revision (about a minute, and the first request after it wakes a replica) |
| B. A separate allowance for the MCP token | `run_scenario` draws on its own small daily count, which strangers cannot use up | Nothing to do on the day | Covers only the connector, not the pages, which is where a demonstration mostly happens; a leaked token gains its own budget |
| C. An owner's token on the API | A request carrying a secret header is exempt | Works from scripts | The pages cannot send it without holding a secret, which the prompt rules out |
| D. A reset command | An authenticated endpoint that clears today's count | Quick | A new write surface on a system being assessed for exactly that |

**Recommendation: A.** The two commands go into the README's *Before a demo* note, and the deployed verification in §10 rehearses them, so the route is proven before it is needed. A raised ceiling raises the possible spend for that day only; the provider's $20 limit remains the backstop.

Dermot's own address is subject to the per-caller limit like any other. Five in ten minutes covers the three scenarios; a longer session raises that setting too, in the same command.

---

## 9. Files, tests, mutation proofs

### Backend

| File | Change |
|---|---|
| `backend/app/limits/__init__.py` | new package |
| `backend/app/limits/caller.py` | new: the address from the request (hops rule, normalisation, the IPv6 cut), the keyed hash, the MCP key |
| `backend/app/limits/repository.py` | new: the two conditional updates, giving back, the salt (create or read), the clean-up |
| `backend/app/limits/limiter.py` | new: `UsageLimiter.reserve(...)` returning a `Reservation`; `LimitReached`; windows and `Retry-After`; fail-closed handling; the decision log line |
| `backend/app/limits/messages.py` | new: the three sentences and the two error codes |
| `backend/app/api/limits.py` | new: the FastAPI dependency that builds the caller key from the request, and the exception handler |
| `backend/app/api/pipeline.py` | `run_pipeline`, `replay_pipeline`: reserve first, confirm before `execute_run` |
| `backend/app/api/agents_test.py` | the four handlers: reserve first, confirm before the agent is called |
| `backend/app/mcp/tools.py` | `run_scenario`: reserve first, confirm before `execute_run`; the description's sentence |
| `backend/app/main.py` | the limiter built in the lifespan; the handler registered; start-up clean-up |
| `backend/settings.py`, `backend/settings.yaml.template` | `RateLimitSettings` |
| `backend/db/migrations/versions/0004_usage_limits.py` | new |
| `backend/tests/conftest.py` | the two tables in the `TRUNCATE` list; the suite's default settings switch the limits off, so that the 552 existing tests are not counted against each other; the new tests switch them on. One test asserts that the shipped default is on |

Every function under 50 lines; guard clauses commented with the reason; no address in any exception message.

### Frontend

`api/client.ts` (unchanged shape; `ApiError` already carries the status), `pages/ClaimsPage.tsx` (the trigger keeps the status with the message), `pages/RunDetailPage.tsx` (`RunNotices`: the sentence alone and the link, for a limit refusal), `components/AgentTestPanel.tsx` (the notice style), `copy/run.ts` or `copy/notices.ts` (the link's label only; no limit sentence is written in the frontend).

### Infrastructure and documents

`infra/bicep/main.bicep`, `main.bicepparam`, `modules/containerapps.bicep` (five parameters and five environment values); `infra/bicep/README.md`; `README.md` (*Before a demo*: the two commands; the settings); `docs/demo-mcp.md`; `docs/walkthrough.md` if it promises unlimited runs (to be checked); `pyproject.toml` and `uv.lock` (the version); and the close-out documents.

### Tests, in the existing style

Backend, about 45 new tests in five modules:

- **`test_limits_caller.py`:** hops 0, 1 and 2; forged left-hand entries ignored; a header shorter than the setting falls back to the peer; a hop count one too high trusts the forged entry (the documented hazard, pinned); IPv6 cut to 64 bits; a non-address gives `unknown`; the same address gives the same key within a day and a different key under another day's salt; the key is 64 hexadecimal characters and the address appears nowhere in it.
- **`test_limits_repository.py`:** a first action creates the row; the limit is exact; **two requests racing a limit of one** on two connections released together by a barrier, exactly one allowed, repeated; a refusal changes neither count; giving back; a zero limit refuses; window roll-over; the daily window at the UTC boundary; the salt is created once under a race; clean-up removes yesterday's salt and old rows and leaves today's.
- **`test_limits_limiter.py`:** **the limit holds across a simulated restart** (a second limiter and a second application built on the same database continue the count); `Retry-After` for each case; the daily sentence wins when both are met; **fail closed** when the database is unreachable and when the tables are missing; the switch off touches no table; the log line carries no address and no hash (asserted on the captured records).
- **`test_api_limits.py`:** **each counted route** refused with 429, the header and the sentence, for the caller's limit and for the daily ceiling, with the model provider stubbed as the existing tests stub it; **each uncounted route stays open** while both limits are met (every `GET`, claim submission, the human decision, `verify`, the stream, `/health`); **the refusal writes nothing** (row counts of `claims`, `audit_log`, `mcp_tool_calls` and both usage tables before and after); 404 and 409 give the reservation back; a 422 counts nothing; a fixture run counts one; an aborted run counts one; the limit is checked before the 404.
- **`test_mcp_limits.py`:** `run_scenario` refused with `limit_reached`, recorded in `mcp_tool_calls` as an error, and **no claim submitted**; the read tools answer while the limits are met; a refused `claim_closed` gives the reservation back; the tool counts under its label.
- Extended: the migration tests (0004 up and down), the settings tests (defaults, template parity, environment override, bounds).

Frontend, about 8 new tests: the run page shows the sentence alone with the link for a 429 and keeps its prefix for a 409; the Claims trigger keeps the status; the test bench shows the sentence in the notice style; nothing is shown twice.

**Mutation proofs** (applied, observed, reverted, recorded in the report):

1. **The per-caller limit:** the `WHERE usage_counters.count < limit` condition removed from the caller's update. Expected: the racing test, the exact-limit test and the per-caller API tests fail.
2. **The daily ceiling:** the global update skipped. Expected: the daily-ceiling tests fail in the repository, API and MCP modules.
3. A third, cheap and worth having: the reservation taken *after* `_prepare_scenario_claim`. Expected: the "no claim submitted" test fails.

The gating run before each commit is the full backend suite, the frontend suite, ruff, mypy, `tsc`, ESLint and the build, each run unfiltered with its output written to a file and its exit code read, never piped through `head`, `tail` or `grep`.

**Local commands name their database explicitly.** The local `.env` points `DATABASE_URL` at a deployed database, so no local command relies on it. The test suite uses `TEST_DATABASE_URL` from `.env.test`, and its fixtures refuse a deployed host. Any other local command (a migration, a local server) is run with `DATABASE_URL` set on its own command line to the local test database, and is preceded by a one-line check that prints the resolved host and database name, never the address in full. This is what Prompt 33 did.

---

## 10. The version, and the deployed verification

### Version

**`0.10.3 → 0.10.4`.** The project's recent practice gives the third figure to an additive change in the API's behaviour (`0.10.2` a new refusal, `0.10.3` a new endpoint). This adds refusals, a table and settings, changes no existing body, and removes nothing. `pyproject.toml` and `uv.lock` are changed together.

### Order of deployment

Each step that writes to a deployed system is named here and waits for Dermot at the time.

1. **Migration `0004` on the Azure database and on Neon**, from a developer shell, the address taken into the process environment only (from Key Vault for Azure), the resolved host printed first. Additive; the running code does not notice. **Needs Dermot's go-ahead on the day.**
2. Push to `main`. CI runs; the two workflows deploy Azure; Render deploys itself. The limits are now on everywhere at their defaults, with no header trusted (one shared per-caller count on each deployment).
3. Measure the hop count on each deployment from the log line (§2). Read-only.
4. **Set the values:** on Azure by the Bicep pass from Dermot's shell (`scripts/azure-deploy.sh`), preceded by a what-if that should show the Container App's environment as the one real change; on Render by Dermot in the dashboard. **Needs Dermot.**

### Verification with Dermot on the Azure frontend

Designed to cost about two cents and to leave the site open afterwards.

| | Step | Cost | Expected |
|---|---|---|---|
| 1 | Read `/health` and today's counts from the limiter's log | none | `0.10.4` |
| 2 | **The per-caller limit, on the Agents test bench:** five Doc-Parser probes with a one-line description, then a sixth | five single calls, about two cents | Five answers; the sixth shows the caller's sentence in the notice |
| 3 | At once, press *Process* on a claim on the Claims page | none | The same sentence on the run page, with the link back; no run appears on the claim, no audit row is written (read from `GET /api/runs` before and after) |
| 4 | While refused: open the Claims list, a run page, the Audit page, *Verify chain*, the Policy page | none | All work |
| 5 | **The daily ceiling, and the owner's route in one:** Dermot runs the command that sets `RATE_LIMIT__DAILY_CEILING` to `1`. The day's count is already at least five, so the ceiling is met with no further call | none | A new revision; *Process* is refused with the daily sentence; `Retry-After` is the seconds to midnight UTC (read with a direct request) |
| 6 | Through the Claude connector, `run_scenario` | none | `limit_reached` with the daily sentence, shown on the Integrations feed as an error; no new claim in the Claims list |
| 7 | Dermot runs the second command, **restoring the setting to 30** | none | A new revision; the day's count stands at five or so of 30 |
| 8 | Wait out the ten-minute window, then *Process* on the Harborline scenario | one run, under two cents | It runs and settles as it does today |
| 9 | Read back: the Container App's environment shows the Bicep values; the two usage tables hold today's rows only, and no address (read through the application's log line, and a read-only count by Dermot's leave) | none | As stated |

Steps 5 and 7 are the commands of §8, so the verification is also the rehearsal of the owner's route, and step 7 is the restoration: nothing is left lowered. If step 7 fails for any reason, the fallback is the Bicep pass, which sets every value from the parameter file.

The same check on Render is steps 1, 2, 3 and 8 only, after Dermot has set the hop count there.

---

## 11. How this work sits beside the held branch

### The position

- `main` (= `origin/main`, `a739df6`) carries Prompt 33's prompt and plan and nothing else of it.
- The local branch `prompt-33-security-assessment` (three commits ahead, not pushed) carries the assessment, its close-out, `SECURITY.md`, build-story entry 33 and register entry R-28.

### Which branch each commit goes on

| Commit | Branch | Pushed |
|---|---|---|
| This prompt and this plan | `main` | yes, once you have read the plan's wording (**D9**) |
| The build, its fixes and Prompt 34's close-out | `main` | yes |
| The assessment's own section on this finding, changed to *found 18 November 2026, fixed* with the date, and its *Built so far* line | `prompt-33-security-assessment` | no |

### Three things on `main` that need handling

1. **The build story needs an entry 33 before it can have a 34.** The regeneration script refuses a gap in the numbering, and it should. `main` has entries to 32. Also, the Prompt 33 prompt and plan already on `main` carry a signpost to `#entry-33`, which leads nowhere there today. **Proposal:** `main` gets a short entry 33 that says only what `main` already says in public: that on 18 November 2026 the system was assessed against three OWASP Top 10 lists, that the assessment is held until its main fixes are deployed, and that the fixes begin with Prompt 34. No rating, no finding, no attack. It carries the same number, title and date as the full entry on the held branch, which replaces it at publication.
2. **The register.** The held branch uses R-28. `main`'s entry for this prompt's gate decisions is therefore **R-29**, and R-28 is left free on `main` until publication. The alternative, using R-28 on `main` and renumbering the branch's entry, changes a record already written.
3. **`CLAUDE.md` on `main`** still says the Agents page is next as Prompt 33. It is corrected in this prompt's first commit to say what the prompt's close-out asks: the prevention prompt next (its plan reviewed before anything is built), then the two escalation rules, then publication of the assessment, with the Agents page after.

### Keeping the two consistent, and what happens at publication

**After each fix is closed out on `main`, `main` is merged into the held branch, locally.** Never the other way. The conflicts are small and predictable, and resolving them one fix at a time is easier than all at once: `CLAUDE.md` (the branch's status paragraph is kept and brought up to date), the build story (the branch's full entry 33 replaces `main`'s short one; the table and `README_TLDR.md` are then regenerated by the script, never merged by hand), the backlog (the branch's findings section is kept and the fix marked done), the build log (the branch's *Prompt 33* entry stays before *Prompt 34*).

**At publication** nothing is rebased. The branch already contains everything on `main`, so `main` is fast-forwarded to it and pushed. A rebase would rewrite the three commits that record when the assessment was written, and I recommend against it.

### What `main` may say

`main`'s documents for this prompt say what the prompt says and no more: the site is public with no sign-in; nothing limited how many model calls a visitor could cause; the assessment names this the first fix; 223 calls were measured at under one US dollar; a $20 monthly limit with a notice at $10 was set at the provider on 18 November. They say nothing of any other finding, any rating beyond this one, or any attack. This plan has been written to that rule, and I ask you to read it with that in mind before it is pushed.

---

## 12. What in the record contradicts this prompt, and other things to know

1. **"May run more than one replica."** Today neither deployment does: `maxReplicas` is 1 in the Bicep parameters, and Render runs one instance. The backend does scale to zero, so the first half of the prompt's reason holds, and the design keeps the counts in the database as asked, so it is correct if the replica count is ever raised.
2. **"In the frontend, the sentence shown where the visitor pressed the button: the Claims page."** The Claims page navigates to the run page before the request is answered, so a refusal is first seen on the run page (§5, D5).
3. **"A refused action writes no claim."** `run_scenario` submits its claim before it runs it, so the limit is checked before the tool does anything, not at the point where the run starts.
4. **The build story on `main` has no entry 33**, and the script refuses a gap (§11).
5. **The register's next number on `main` is R-28, which the held branch has used** (§11).
6. **The suite's default.** The prompt asks for defaults that are safe when nothing is set, so the limits ship on. The existing tests start runs freely; the suite's settings switch the limits off and the new tests switch them on (§9).
7. **Uvicorn's own proxy support is not used.** It trusts every entry of the header from a trusted peer, which is the reverse of what is wanted here. The limiter reads the header itself by the hop rule.
8. **The MCP caller has no address** inside a tool; the token's label is used (§2).
9. **Things this prompt leaves as they are, noted so they are not thought overlooked:** claim submission is not limited (it calls no model); opening progress streams is not limited; the telemetry sent to Application Insights is not changed by this work, and whether it records caller addresses was not examined here.
10. **Prices.** The provider's list prices are used only for the theoretical worst case in §4, and I have not relied on memory for the working figure, which is the prompt's own measurement.

---

## 13. Decisions for Dermot

| | Decision | Recommendation |
|---|---|---|
| D1 | The daily ceiling: 30 (under $20 on the measured cost), or 24 (under $20 even if every answer filled its cap) | 30 |
| D2 | The unit: one action whatever it is, or weighted by model calls (a run 4, a probe 1) | One action |
| D3 | The caller's key: a daily salt kept in the database (recoverable on the day by someone with the database, not afterwards), or the salt plus a fixed secret from Key Vault | The daily salt alone |
| D4 | Per caller: 5 actions in 10 minutes | Yes |
| D5 | The Claims page's refusal: in the run page's banner with a link back (A), or sent back to the Claims page with the sentence above the table (B) | A |
| D6 | The three sentences in §5, as drafted, "tomorrow" included | Yes |
| D7 | Fail closed with a 503 when the count cannot be read | Yes |
| D8 | The owner's route: raise the setting for the day (A) | A |
| D9 | The handling of `main`: a short entry 33 with no findings; R-29 on `main`; `main` merged into the held branch after each fix; a fast-forward at publication. And: this prompt and plan committed and pushed to `main` once you have read the plan's wording | Yes to each |
| D10 | Version `0.10.4` | Yes |
| D11 | The order in §10: the migration on both deployed databases first, on your go-ahead on the day; then the push; then the measurement; then the Bicep pass and the Render variable | Yes |

### Optional, not in the prompt

- **O1.** One sentence on the Guide, under *Try it*: "To keep the demonstration's cost bounded, the system limits how many runs can be started in a day and by one visitor in a short time." A visitor who meets the refusal has then been told. Recommended.
- **O2.** A per-caller share of the day (no caller more than 12 of the 30), so that one patient caller cannot use the whole day in an hour (§4). One more counter row, one more test group, and the daily sentence serves. Recommended, but it is an addition and yours to decide.
- **O3.** A read-only `GET /api/limits` giving today's count and ceiling, so the pages could warn before a button is pressed. Not recommended now: it publishes how close the site is to refusing.

---

## 14. Risks

- **The hop count is the one value that can make the per-caller limit worthless** if set too high. It is measured, tested and recorded, and the daily ceiling does not depend on it.
- **The migration and the code are separate steps on two deployed databases.** Code first means every run refused until the migration lands (§7). The order in §10 avoids it.
- **A raised ceiling that is not put back** raises the possible spend until someone notices. The verification rehearses the restoration; the provider's limit bounds the worst case.
- **A fixed window** allows ten actions close together across a boundary (§3). Accepted.
- **Merging `main` into the held branch** repeatedly touches the same five documents. The conflicts are mechanical, and the regeneration script, the anonymisation test and the link check are run on the branch after each merge.
- **Nothing here makes a model harder to mislead.** This prompt bounds cost and availability only.
