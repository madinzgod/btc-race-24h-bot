"""Patient-entry, take-profit, crash-guarded long bot for bars-replay/v1.

cbBTC/USDC on one-minute bars, 1,000 USDC of paper money, long only.
Every round trip pays roughly 40 bps in fees, slippage and the pool
impact of its own fills, so this bot trades only on moves that dwarf
that cost:

  1. Patient entry. Rather than buying the first open, it waits up to
     PATIENCE bars for a dip of DIP_BPS below the first close and buys
     that dip; if no dip comes it buys anyway when the patience runs
     out. One position, taken with the whole account.
  2. Take profit. While holding, if the close reaches TAKE_PROFIT_BPS
     above the close at which the buy was decided -- about four times
     the cost of a round trip -- it sells and banks the gain instead of
     riding the position back down. After banking, patience no longer
     forces a buy: it re-enters only on a fresh DIP_BPS dip below the
     first close, so each later cycle has to earn its own entry.
  3. Crash guard. While holding, if the trailing GUARD_LB-bar return
     falls to -GUARD_OFF_BPS -- a sustained break, not a wick -- it
     sells, and if the trailing 30-bar return falls to -FAST_OFF_BPS
     (a fast crash) it sells at once. While out after a guard exit it
     re-enters when the trailing return recovers to -GUARD_ON_BPS.

Decisions are taken on each bar's close and fill at the next bar's
open. The bot is deterministic: it reads nothing but the hello and the
batches, keeps no clock, opens no file and draws no random number.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import makefun_bars

# --- Tunables (bars are one minute) ---------------------------------------
PATIENCE = 240          # bars to wait for a dip before buying anyway
DIP_BPS = 40            # dip below the first close that triggers the buy
TAKE_PROFIT_BPS = 150   # sell when the close gains this on the entry close
GUARD_LB = 240          # lookback of the crash guard's trailing return
GUARD_OFF_BPS = 160     # exit when the trailing return reaches -this
GUARD_ON_BPS = 30       # re-enter when it recovers to -this
FAST_OFF_BPS = 200      # exit when the trailing 30-bar return reaches -this
SIZE_FRAC_NUM = 100     # go in with the whole account
SIZE_FRAC_DEN = 100
SLIPPAGE_BPS = 250      # max_slippage_bps sent with every order
BPS = 10_000


class PatientBot:
    """Memory: the closes, the first close, the entry close of the open
    position, whether a take-profit has been banked, and whether the
    guard fired."""

    def __init__(self):
        self.symbol = None
        self.closes = []
        self.first_close = None
        self.entry_close = None    # close at which the current buy was decided
        self.holding = False
        self.banked = False        # flat because a take-profit exit filled the day
        self.guarded_out = False   # flat because the guard fired (not pre-entry)

    def on_hello(self, state):
        self.symbol = next(iter(state.symbols))

    def _trailing_bps(self, close, lookback):
        """The trailing return over lookback bars, in bps (floor), or None."""
        if len(self.closes) <= lookback:
            return None
        old = self.closes[-lookback - 1]
        return close * BPS // old - BPS

    def _dipped(self, close):
        """True when the close is at least DIP_BPS below the first close."""
        return close * BPS <= self.first_close * (BPS - DIP_BPS)

    def on_batch(self, state, batch):
        bar = state.latest.get(self.symbol)
        if bar is None:
            return None
        close = int(bar["c"])
        self.closes.append(close)
        if self.first_close is None:
            self.first_close = close

        held = state.positions.get(self.symbol)
        self.holding = held is not None and held.qty > 0

        if state.warming_up:
            return None

        if self.holding:
            return self._while_holding(state, held, close)
        if self.guarded_out:
            ret = self._trailing_bps(close, GUARD_LB)
            if ret is not None and ret >= -GUARD_ON_BPS:
                self.guarded_out = False
                return self._buy(state)
            return None
        if self.banked:
            # Banked a take-profit: only a fresh dip earns a re-entry.
            if self._dipped(close):
                return self._buy(state)
            return None
        # Pre-entry: buy the dip, or buy anyway once patience runs out.
        if self._dipped(close) or state.seq >= PATIENCE:
            return self._buy(state)
        return None

    def _while_holding(self, state, held, close):
        # Take profit first: a banked gain cannot be ridden back down.
        if self.entry_close is not None and \
                close * BPS >= self.entry_close * (BPS + TAKE_PROFIT_BPS):
            self.banked = True
            return [self._sell_all(held)]
        return self._guard_exit(state, held, close)

    def _guard_exit(self, state, held, close):
        ret = self._trailing_bps(close, GUARD_LB)
        leave = ret is not None and ret <= -GUARD_OFF_BPS
        if not leave:
            fast = self._trailing_bps(close, 30)
            leave = fast is not None and fast <= -FAST_OFF_BPS
        if not leave:
            return None
        self.guarded_out = True
        return [self._sell_all(held)]

    def _sell_all(self, held):
        return {
            "side": "sell",
            "symbol": self.symbol,
            "qty": held.qty,
            "max_slippage_bps": SLIPPAGE_BPS,
        }

    def _buy(self, state):
        room = state.weight_room(self.symbol)
        want = state.equity * SIZE_FRAC_NUM // SIZE_FRAC_DEN
        notional = min(state.cash, room, want)
        if notional < 1_000_000:  # the replay's minimum buy is 1 USDC
            return None
        self.entry_close = self.closes[-1]
        return [{
            "side": "buy",
            "symbol": self.symbol,
            "notional_quote_units": notional,
            "max_slippage_bps": SLIPPAGE_BPS,
        }]


BOT = PatientBot()


def on_batch(state, batch):
    return BOT.on_batch(state, batch)


if __name__ == "__main__":
    makefun_bars.run(on_batch, on_hello=BOT.on_hello)
