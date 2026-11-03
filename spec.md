# Implementation Plan: Trading Signal Agent

**Status:** Draft  **Updated:** 03/11/2026

Anything unknown is marked `[NEEDS CONFIRMATION]` instead of being guessed. The biggest blocker right now: **the conditions of the trading plan have not been written as a checklist**. Without it, the AI will improvise its own interpretation and the entire system loses its value.

**Overall flow:**

```
Python captures the chart window (10 seconds before the 5-minute candle closes)
  + fetches raw prices from MT5
  → Argon (via Antigravity CLI) scores the checklist, returns JSON
  → Code validates the JSON and decides IDLE / WATCH / READY
  → Telegram (early heads-up / conditions met, clearly labeled "before candle close")
  → When the candle closes, code re-checks using raw MT5 prices and reports if the signal is invalidated
  → You decide whether to enter the trade yourself
```

---

## 1. Problem, goals, biggest risks

**Problem:** You can't watch the chart every 5 minutes all day. You want the AI to watch for you, alert only when **all conditions of the plan are met**, give an early heads-up when it is close, and leave the decision to enter a trade to you.

**User:** only you, trading manually on MT5 mobile.

### Success criteria

| Criterion | How to measure | Threshold |
|---|---|---|
| READY signals match the plan | % of READY signals you label ✅ | proposed ≥ 80% `[NEEDS CONFIRMATION]` |
| No missed setups | Compared with setups you review yourself at end of day | `[NEEDS CONFIRMATION]` |
| Latency | From request sent (T-10s) to the Telegram message | `[NEEDS CONFIRMATION]`, depends on measurements in ST-001 |
| Signals invalidated at candle close | % of READY signals flagged invalid by FR-11 | `[NEEDS CONFIRMATION]` |
| Stability | % of cycles that run successfully | proposed ≥ 98% `[NEEDS CONFIRMATION]` |
| Guardrail | Number of Telegram messages per day | must not exceed the level you accept |

### Riskiest assumptions

| Assumption | If wrong | How to verify |
|---|---|---|
| Argon reads chart images accurately enough to score the checklist | Junk signals or missed setups | Run shadow mode, label ✅/❌ |
| Antigravity CLI can run automatically and quota is enough for 288 calls/day | Must switch to the Gemini API | Spike ST-001 |

---

## 2. Scope

### Functional requirements

- **FR-1:** Capture the chart window and send the analysis request **10 seconds before the 5-minute candle closes** (default T-10s, configurable), only within the configured time window.
- **FR-2:** Fetch raw prices from MT5 (current price, 15-minute high/low) so the AI doesn't have to read numbers from the image.
- **FR-3:** Send the image, raw prices and plan checklist to Argon, and receive JSON in a fixed schema.
- **FR-4:** Validate the JSON. If invalid, retry once; if still invalid, log it and do not send a signal.
- **FR-5:** State flow IDLE → WATCH (almost met, early heads-up) → READY (all met). Only **code** decides the state; the AI only fills in the checklist.
- **FR-6:** Code calculates entry, SL (15-minute high/low), TP (2× SL) and lot size for a fixed loss of $250.
- **FR-7:** Telegram sends WATCH and READY messages with the image, with duplicate prevention and cooldown.
- **FR-8:** Log every cycle (image, JSON, decision), heartbeat, and alerts when the system fails.
- **FR-9:** `/pause` and `/resume` commands. The system **does not place orders itself**.
- **FR-10:** ✅/❌ buttons directly in Telegram so you can label signals, then aggregate accuracy.
- **FR-11:** When the candle closes, code re-checks the conditions that can be verified numerically (close price, high/low) using raw MT5 prices. If a signal already sent is invalidated, immediately send one Telegram message.

### Out of scope (this time)

- Automatic order entry, because the final decision belongs to you and The5ers' rules are also involved.
- Calculating indicators in code, because you want the AI to analyze from the chart image only.
- Multiple symbols at once, because it is not yet known whether the AI can read a chart for one symbol well enough.

### Risks

| Risk | Type | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| AI misreads the chart | Product | High | High | Raw prices from MT5, JSON checklist, shadow mode |
| CLI quota or terms don't allow automated use | Technical | Medium | High | ST-001, fallback to Gemini API |
| Machine off or screen locked, black image | Operational | Medium | High | Windows VPS, heartbeat, black-image check |
| Analyzing before the candle closes: the last 10 seconds can change the result | Technical | High | High | Re-check with raw prices at candle close (FR-11), clearly label "before candle close" on the message, measure invalidation rate |
| Model responds slower than 10 seconds, so the message arrives after the candle has closed | Technical | Medium | Medium | Measure latency in ST-001, adjust T-10s to T-20s if needed |
| Spam or missed signals | Product | Medium | Medium | Cooldown, measure precision/recall |
| Telegram token or API key leaked | Security | Low | High | `.env`, never commit to git |

---

## 3. Backlog (MoSCoW) and order of work

| Epic | Content | MoSCoW |
|---|---|---|
| **PRE-01** | You write the plan as a checklist of conditions (your task, not the developer's) | Must, blocks everything |
| EP-01 | CLI spike | Must (MVP) |
| EP-02 | Screen capture + raw MT5 prices | Must (MVP) |
| EP-03 | Argon analysis + JSON validation | Must (MVP) |
| EP-04 | Telegram READY + log + labeling + re-check at candle close | Must (MVP) |
| EP-05 | WATCH early heads-up + state machine + cooldown | Should (v1) |
| EP-06 | Calculate entry/SL/TP/lot | Should (v1) |
| EP-07 | `/pause`, heartbeat, error alerts | Should (v1) |
| EP-08 | Accuracy report, replay of old images | Could (v2) |
| EP-09 | Multiple symbols, second model for verification | Could (v2) |

WATCH and order parameters are placed in v1 because the MVP only needs to answer one question: **does the AI score the checklist correctly?** Those two parts are cheap to add once the answer is yes.

### Dependencies

- PRE-01 → ST-004 (hard block: without the checklist there is nothing to score)
- ST-001 → ST-004 (decision to use CLI or Gemini API)
- ST-002, ST-003 → ST-004
- ST-004 → ST-005 → ST-006
- ST-003, ST-005 → ST-008

---

## 4. User stories for the MVP

### ST-001 (Spike, timebox 1–2 sessions): Verify calling Argon automatically from Python

- **AC-1:** Given the CLI is installed and logged in, When a Python script runs a command with one image and a prompt, Then JSON is received on stdout with exit code 0.
- **AC-2:** Given 20 consecutive calls, When checking `/usage`, Then record how much quota decreased and the average time per call.
- **AC-3:** Go/no-go conclusion: use the CLI or switch to the Gemini API.

### ST-002: Capture the chart window and send the analysis request 10 seconds before the 5-minute candle closes

- **AC-1:** Given the chart window is open and within the time window, When 10 seconds (configurable) remain before the 5-minute candle closes, Then capture, save a PNG image named by timestamp, and send the analysis request immediately.
- **AC-2:** Given the window is not found or the image is black, When capturing, Then log the error, send a system alert and do not call the model.
- **AC-3:** Given outside the configured time window, When the 5-minute mark arrives, Then do not capture.

### ST-003: Fetch raw prices from MT5

- **AC-1:** Given MT5 is logged in, When the cycle runs, Then save the current price and the most recent 15-minute high/low.
- **AC-2:** Given MT5 loses connection, When fetching prices, Then mark the cycle as failed and do not send a signal.

### ST-004: Score the checklist with Argon (depends on PRE-01)

- **AC-1:** Given the image, raw prices and checklist, When calling the model, Then receive JSON in the correct schema (each condition has true/false and a one-sentence reason).
- **AC-2:** Given JSON in the wrong schema, When validating, Then retry once; if still wrong, log "invalid" and do not send a signal.
- **AC-3:** Given the model exceeds the time limit, When it times out, Then cancel the call and the next cycle still runs normally.

### ST-005: Send the READY signal via Telegram

- **AC-1:** Given all required conditions are true, When the cycle ends, Then send one message with the image, trade direction and the list of conditions.
- **AC-2:** Given at least one condition is false, When the cycle ends, Then do not send.
- **AC-3:** Given the same setup was already sent within the cooldown period, When it appears again, Then do not send again.

### ST-006: Label signals

- **AC-1:** Given a READY message has been sent, When you press ✅ or ❌, Then save the label together with the image and JSON of that cycle.
- **AC-2:** Given a day has ended, When you call `/stats`, Then receive the number of READY signals, number of ✅ and number of ❌.

### ST-007: Log and heartbeat

- **AC-1:** Each cycle writes one line containing the timestamp, image path, JSON and decision.
- **AC-2:** Given 15 minutes within the time window with no successful cycle, When the deadline passes, Then send a system alert.

### ST-008: Re-check the signal when the candle closes

- **AC-1:** Given a READY signal was sent before the candle closed, When the candle closes, Then fetch raw prices from MT5 and re-check the conditions that can be verified numerically.
- **AC-2:** Given a condition is no longer true after the candle closes, When the check finishes, Then send a "signal invalidated" message with the reason and flag that signal in the log.
- **AC-3:** Given all verifiable conditions are still true, When the check finishes, Then send a short confirmation message "confirmed after candle close".
- **AC-4:** Given MT5 loses connection at candle close, When checking, Then log the error and send an alert that confirmation could not be completed.

---

## 5. Roadmap

| Milestone | Goal (outcome) | Epics | Timeline | Confidence |
|---|---|---|---|---|
| **MVP** | Prove Argon scores the checklist correctly | EP-01 → 04 | no date yet | High |
| **v1** | Usable every day: early heads-up, order parameters, safety | EP-05 → 07 | no date yet | Medium |
| **v2** | Expand and optimize (hypothesis) | EP-08, 09 | no date yet | Low |

### MVP

- **Assumption to verify:** the AI reads the chart accurately enough.
- **Exit condition:** has run in shadow mode for enough trading days `[NEEDS CONFIRMATION]` and has enough ✅/❌ labels.
- **Decision gate:**
  - Continue if precision reaches the threshold.
  - Adjust the prompt or checklist if it is low but trending upward.
  - Stop or change approach (e.g. add numeric data instead of images only) if it stays low for a long time.

### v1

Add WATCH, state machine, entry/SL/TP/lot calculation, `/pause`, error alerts. If ST-001 results in no-go, switch to the Gemini API at this milestone.

### v2

Replay old images to measure accuracy, multiple symbols, second model for cross-verification.

---

## 6. MVP release plan

- **Readiness condition:** all ACs of ST-001 through ST-008 pass, PRE-01 is done.
- **How to run:** shadow mode, send to your own private Telegram chat, do not enter trades based on signals yet.
- **Rollback:** stop the service; no impact on MT5 or the account.
- **Monitoring:** each end of day, spend about 10 minutes reviewing `/stats` and compare with the setups you spotted yourself.
- **Rules:** re-read The5ers' terms about using signal-assist tools `[NEEDS CONFIRMATION]`.

---

## 7. Questions to settle

1. **What do the plan's condition checklist items currently include?**
   - A) You paste them here.
   - B) You describe them, then ask for help turning them into a checklist.
   - C) Not written down yet, need to be asked step by step.
2. **Symbol and trading hours?**
   - A) One symbol.
   - B) Multiple symbols.
   - Include the desired running hours.
3. **Machine running the system?**
   - A) Home Windows PC on 24/7.
   - B) Windows VPS.
   - C) Not decided yet.