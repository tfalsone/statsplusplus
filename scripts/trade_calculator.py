"""
trade_calculator.py — Trade surplus balance calculator.
Usage:
  python3 scripts/trade_calculator.py --trade '<json>'

Trade JSON format:
  {
    "angels_send": [
      {"player_id": 35149, "retention": 0.15},
      {"player_id": 48517}
    ],
    "angels_receive": [
      {"player_id": 99999}
    ]
  }

  For prospects (minor league contracts), add "is_prospect": true and supply
  fv/age/level/bucket if not in prospect_history.json:
      {"player_id": 99999, "is_prospect": true, "fv": 45, "age": 22, "level": "AA", "bucket": "SP"}

Implements Step 4 of docs/trade_analysis_guide.md.
"""

import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from player_utils import dollars_per_war
from contract_value import contract_value, get_player_info
from prospect_value import prospect_surplus_with_option, find_player

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Player valuation dispatcher
# ---------------------------------------------------------------------------

def value_player(spec):
    """
    Given a trade spec entry, return a valuation dict.
    Detects whether the player is on an MLB contract or a minor league contract.
    """
    pid        = spec["player_id"]
    retention  = spec.get("retention", 0.0)
    is_prospect = spec.get("is_prospect", False)

    # Try MLB contract first (unless explicitly flagged as prospect)
    if not is_prospect:
        result = contract_value(pid, retention_pct=retention)
        if result:
            return {"type": "contract", "data": result}

    # Prospect path — pull from DB
    fv, level, bucket, db_age, fv_plus = find_player(pid)

    fv_raw  = spec.get("fv") or fv
    fv_plus = str(fv_raw).endswith("+") if isinstance(fv_raw, str) else fv_plus
    fv_int  = int(str(fv_raw).rstrip("+")) if fv_raw else None
    level   = spec.get("level")  or level
    bucket  = spec.get("bucket") or bucket
    age     = spec.get("age")    or db_age

    if not all([fv_int, level, bucket, age]):
        return {"type": "unknown", "player_id": pid,
                "error": f"Insufficient data for player {pid}. Provide fv/age/level/bucket in trade spec."}

    # Look up ovr/pot for certainty multiplier
    import db as _db
    conn = _db.get_conn()
    row = conn.execute("SELECT name, age FROM players WHERE player_id=?", (pid,)).fetchone()
    name = row["name"] if row else str(pid)
    rr = conn.execute("SELECT ovr, pot FROM ratings WHERE player_id=? ORDER BY snapshot_date DESC LIMIT 1", (pid,)).fetchone()
    conn.close()
    ovr = rr["ovr"] if rr else None
    pot = rr["pot"] if rr else None

    SENSITIVITY = {"pessimistic": 0.85, "base": 1.00, "optimistic": 1.15}
    base_surplus = prospect_surplus_with_option(fv_int, age, level, bucket,
                                                 ovr=ovr, pot=pot, fv_plus=fv_plus)
    total_surplus = {s: max(0, round(base_surplus * mult)) for s, mult in SENSITIVITY.items()}

    fv_display = f"{fv_int}+" if fv_plus else str(fv_int)

    return {"type": "prospect", "data": {
        "player_id": pid, "name": name, "bucket": bucket,
        "fv": fv_int, "fv_display": fv_display, "level": level, "age": age,
        "total_surplus": total_surplus,
    }}

# ---------------------------------------------------------------------------
# Trade balance
# ---------------------------------------------------------------------------

def evaluate_trade(trade_spec):
    angels_send    = trade_spec.get("angels_send", [])
    angels_receive = trade_spec.get("angels_receive", [])

    send_valuations    = [value_player(s) for s in angels_send]
    receive_valuations = [value_player(s) for s in angels_receive]

    def net_surplus(valuations):
        total = {"pessimistic": 0, "base": 0, "optimistic": 0}
        for v in valuations:
            if v["type"] in ("contract", "prospect"):
                t = v["data"]["total_surplus"]
                for s in total:
                    total[s] += t.get(s, t.get("base", 0))
        return total

    angels_receive_surplus = net_surplus(receive_valuations)
    angels_send_surplus    = net_surplus(send_valuations)

    angels_net = {s: angels_receive_surplus[s] - angels_send_surplus[s]
                  for s in ("pessimistic", "base", "optimistic")}
    other_net  = {s: -angels_net[s] for s in angels_net}

    return {
        "angels_send":         send_valuations,
        "angels_receive":      receive_valuations,
        "angels_net":          angels_net,
        "other_team_net":      other_net,
    }

# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def fmt_millions(n):
    return f"${n/1_000_000:.1f}M" if abs(n) >= 1_000_000 else f"${n:,}"

def player_summary_line(v, sent=False):
    if v["type"] == "contract":
        d = v["data"]
        t = d["total_surplus"]
        flags = f"  [{', '.join(d['flags'])}]" if d["flags"] else ""
        ret   = f"  (Angels retain {d['retention_pct']*100:.0f}%)" if d["retention_pct"] else ""
        surplus_str = f"base {fmt_millions(t['base'])} | pessimistic {fmt_millions(t['pessimistic'])} | optimistic {fmt_millions(t['optimistic'])}"
        return f"  {d['name']:25s} | {d['bucket']:4s} | Age {d['age']} | {d['years_left']} yrs left{ret}{flags}\n    Surplus: {surplus_str}"
    elif v["type"] == "prospect":
        d = v["data"]
        t = d["total_surplus"]
        fv_str = d.get("fv_display", d["fv"])
        surplus_str = f"base {fmt_millions(t['base'])} | pessimistic {fmt_millions(t['pessimistic'])} | optimistic {fmt_millions(t['optimistic'])}"
        return f"  {d['name']:25s} | {d['bucket']:4s} | FV {fv_str} | {d['level']} | Age {d['age']}\n    Surplus: {surplus_str}"
    else:
        return f"  [ERROR] Player {v['player_id']}: {v.get('error', 'unknown error')}"

def verdict(angels_net):
    b = angels_net["base"]
    p = angels_net["pessimistic"]
    o = angels_net["optimistic"]
    if b > 0 and p > 0:
        return f"Angels win in all scenarios (base: {fmt_millions(b)})"
    elif b > 0 and p < 0:
        return f"Angels win in base/optimistic, lose in pessimistic (base: {fmt_millions(b)})"
    elif b < 0 and o > 0:
        return f"Angels lose in base/pessimistic, win only in optimistic (base: {fmt_millions(b)})"
    else:
        return f"Angels lose in all scenarios (base: {fmt_millions(b)})"

def print_trade(result):
    print("\n" + "="*60)
    print("TRADE SUMMARY")
    print("="*60)

    print("\nANGELS SEND:")
    for v in result["angels_send"]:
        print(player_summary_line(v, sent=True))

    print("\nANGELS RECEIVE:")
    for v in result["angels_receive"]:
        print(player_summary_line(v))

    an = result["angels_net"]
    on = result["other_team_net"]
    print(f"\nANGELS NET:      pessimistic {fmt_millions(an['pessimistic'])} | base {fmt_millions(an['base'])} | optimistic {fmt_millions(an['optimistic'])}")
    print(f"OTHER TEAM NET:  pessimistic {fmt_millions(on['pessimistic'])} | base {fmt_millions(on['base'])} | optimistic {fmt_millions(on['optimistic'])}")

    print(f"\nVERDICT: {verdict(an)}")
    print("="*60)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Trade surplus balance calculator")
    parser.add_argument("--trade", required=True,
                        help='JSON trade definition. See script docstring for format.')
    args = parser.parse_args()

    try:
        trade_spec = json.loads(args.trade)
    except json.JSONDecodeError as e:
        print(f"Invalid trade JSON: {e}")
        sys.exit(1)

    result = evaluate_trade(trade_spec)
    print_trade(result)

if __name__ == "__main__":
    main()
