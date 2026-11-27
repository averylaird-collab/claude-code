"""Control for lag_live_test.py: same entry times on NDX, but a random direction (coin flip).
If random directions make similar $ under the $10 account rules, the $ come from the account structure
(losses capped at the floor, profits claimed), not from the lag signal.  Usage: python3 lag_live_control.py <scratchpad>"""
import random, sys
sys.argv = sys.argv[:2]
src = open(__file__.replace("lag_live_control.py", "lag_live_test.py")).read().split('if __name__ == "__main__":')[0]
exec(src.replace("d = 1 if sig > 0 else -1;", "d = random.choice((1, -1)) if RANDOM else (1 if sig > 0 else -1);"))
for VS in ("NDX-USD-PERP", "SPX-USD-PERP", "RTY-USD-PERP"):
  for lev in (20, 50):
      RANDOM = False
      tr, c, a, p = run(VS, 1, 3, 2, 500 * lev)
      real_net = c - a * COST
      RANDOM = True; nets = []
      for seed in range(100):
          random.seed(seed); tr, c, a, p = run(VS, 1, 3, 2, 500 * lev); nets.append(c - a * COST)
      nets.sort()
      print(f"{VS[:3]} {lev}x: signal net ${real_net:+.2f} | random-direction net: median ${nets[50]:+.2f}, "
            f"5%..95% ${nets[5]:+.2f}..${nets[95]:+.2f}, share of random runs beating the signal {sum(n >= real_net for n in nets)/100:.0%}")
