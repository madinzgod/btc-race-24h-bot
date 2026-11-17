# Patient — a crash-guarded cbBTC trading bot

[![make.fun bounty](https://make.fun/badge/btc-race-24h-20261117-0603.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603)
[![rank](https://make.fun/badge/btc-race-24h-20261117-0603/madinzgod/btc-race-24h-bot/rank.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603)
[![reward](https://make.fun/badge/btc-race-24h-20261117-0603/madinzgod/btc-race-24h-bot/reward.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603)

An entry for make.fun's [btc-race-24h-20261117-0603](https://make.fun/bounty/btc-race-24h-20261117-0603):
race a BTC trading bot live for 24 hours. The bot trades Coinbase Wrapped
BTC (cbBTC) against USDC on one-minute on-chain bars with 1,000 USDC of
paper money, speaking the `agent-fun/bars-replay/v1` protocol — one JSON
line per minute in, one reply with its orders out.

## Strategy

Every round trip pays roughly 40 bps in fees, slippage and the pool
impact of its own fills, so the bot trades as rarely as it can:

1. **Patient entry.** Instead of buying the first open, it waits up to
   240 bars for a dip of 40 bps below the first close and buys that dip;
   if no dip comes, it buys anyway when the patience runs out. One
   position, taken with the whole account, then held for whatever drift
   the window brings.
2. **Crash guard.** While holding, if the trailing 240-bar return falls
   to −160 bps — a sustained break, not a wick — it sells, and a
   trailing 30-bar return of −200 bps (a fast crash) sells it at once.
   While out after a guard exit, it re-enters when the trailing return
   recovers to −30 bps.

On the competition's published dev window this makes one trade and a
net PnL of **+$5.45** on the 1,000 USDC start (max drawdown 2.12%),
which clears the dev gate; the unseen 24-hour race window decides the
ranking.

## Layout

- `main.py` — the bot (Python 3.13, standard library only). Run as
  `python3 -P -s main.py`; it reads the protocol on stdin and answers
  on stdout.
- `vendor/makefun_bars.py` — the competition kit's Python SDK shim,
  copied byte for byte; it owns the wire format, the bot supplies the
  decisions.

Decisions are taken on each bar's close and fill at the next bar's
open. The bot is deterministic: no clock, no network, no files, no
randomness — two runs on the same bars produce byte-identical replies.

## License

MIT — see [LICENSE](LICENSE).
