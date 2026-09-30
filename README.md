# adversary

Argues against your change or plan. Not a reviewer: opposing counsel.

Most AI tools remove friction. This one adds the useful kind: the single strongest objection, the assumption you didn't notice making, at most five challenges, and what should have been built instead. Built from the Contexta seed *build the adversary, not the assistant*.

Two rules keep the friction productive instead of noisy:

- **Every challenge quotes its evidence.** No quote from your input, no challenge.
- **Every challenge says how to prove it wrong.** A refutation test you can run quickly -- an unfalsifiable objection is just noise you learn to ignore.

Then you argue back. `rebut` rules on each challenge: **concede** (your evidence refuted it), **hold** (you didn't address it), or **escalate** (your answer revealed something worse). It concedes to evidence, never to confidence.

## Usage

```bash
adversary review                      # uncommitted changes vs HEAD
adversary review --range HEAD~1 -c "what this change is meant to do"
adversary pitch idea.md               # a plan, pitch, or idea -- PRFAQ-style, problem before solution
cat idea.md | adversary pitch
adversary rebut "1: ran the test, it passes. 3: that's intentional because ..."
```

Standard flags: `--provider`, `--model`, `--json`, `--dry-run` (don't save the session), `--no-llm` (mock output, implies `--dry-run`).

Defaults to `--provider claude-code --model sonnet` (subscription, reasoning tier): small local models make agreeable, vague adversaries. Override per call or in `~/.config/local-first/adversary.toml`.

The last review/pitch is saved to `~/.local/state/adversary/last.json` (override with `ADVERSARY_STATE_DIR`) so `rebut` can answer it.

## First real use

Run against local-first-common's new `claude-code` provider (31c7120), it raised five challenges. Checking them: one was refuted (model IDs resolve), one was right about the wrong mechanism (the retry heuristic matches only "429" -- but the CLI's usage-limit message embeds a reset epoch that can contain "429"), two were plain bugs (orphaned subprocess on cancellation, inconsistent token accounting), and one suggested fix would have silently broken everything (`--system-prompt-file` is ignored outside `--bare`). Its unconceded point -- no real-CLI test -- led to an integration test that caught the calling repo leaking into every prompt. Fixed in ccbdcfd.
