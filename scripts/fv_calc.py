#!/usr/bin/env python3
"""
fv_calc.py — League-wide FV and surplus calculation.

Prospects (non-MLB, age ≤ 24): FV → prospect_fv
MLB players: surplus value → player_surplus

Angels org prospects are included — farm_analysis.py will overwrite them
with authoritative values when it runs.

Usage: python3 scripts/fv_calc.py
"""

import json, os, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "scripts"))

import db as _db
from league_config import config as _cfg
from player_utils import (assign_bucket, calc_fv, LEVEL_NORM_AGE,
                           dollars_per_war, league_minimum,
                           peak_war_from_ovr, aging_mult)
from prospect_value import prospect_surplus_with_option as _prospect_surplus_opt
from contract_value import contract_value as _contract_value
from contract_value import contract_value as _contract_value

LEVEL_INT_KEY   = {2:"aaa", 3:"aa", 4:"a", 5:"a-short", 6:"usl", 8:"intl"}
LEVEL_INT_LABEL = {1:"MLB", 2:"AAA", 3:"AA", 4:"A", 5:"A-Short", 6:"Rookie", 8:"International"}

RATINGS_SQL = """
    SELECT r.player_id AS ID,
           p.name AS Name, p.age AS Age, p.team_id, p.parent_team_id, p.level, p.pos, p.role,
           r.ovr AS Ovr, r.pot AS Pot,
           r.cntct AS Cntct, r.gap AS Gap, r.pow AS Pow, r.eye AS Eye, r.ks AS Ks,
           r.speed AS Speed, r.steal AS Steal,
           r.stf AS Stf, r.mov AS Mov, r.ctrl AS Ctrl, r.ctrl_r AS Ctrl_R, r.ctrl_l AS Ctrl_L,
           r.fst AS Fst, r.snk AS Snk, r.crv AS Crv, r.sld AS Sld, r.chg AS Chg,
           r.splt AS Splt, r.cutt AS Cutt, r.cir_chg AS CirChg, r.scr AS Scr,
           r.frk AS Frk, r.kncrv AS Kncrv, r.knbl AS Knbl, r.stm AS Stm, r.vel AS Vel,
           r.pot_stf AS PotStf, r.pot_mov AS PotMov, r.pot_ctrl AS PotCtrl,
           r.pot_fst AS PotFst, r.pot_snk AS PotSnk, r.pot_crv AS PotCrv,
           r.pot_sld AS PotSld, r.pot_chg AS PotChg, r.pot_splt AS PotSplt,
           r.pot_cutt AS PotCutt, r.pot_cir_chg AS PotCirChg, r.pot_scr AS PotScr,
           r.pot_frk AS PotFrk, r.pot_kncrv AS PotKncrv, r.pot_knbl AS PotKnbl,
           r.pot_cntct AS PotCntct, r.pot_gap AS PotGap, r.pot_pow AS PotPow,
           r.pot_eye AS PotEye, r.pot_ks AS PotKs,
           r.c AS C, r.ss AS SS, r.second_b AS "2B", r.third_b AS "3B",
           r.first_b AS "1B", r.lf AS LF, r.cf AS CF, r.rf AS RF,
           r.pot_c AS PotC, r.pot_ss AS PotSS, r.pot_second_b AS Pot2B,
           r.pot_third_b AS Pot3B, r.pot_first_b AS Pot1B,
           r.pot_lf AS PotLF, r.pot_cf AS PotCF, r.pot_rf AS PotRF,
           r.ofa AS OFA, r.ifa AS IFA, r.c_arm AS CArm, r.c_blk AS CBlk, r.c_frm AS CFrm,
           r.ifr AS IFR, r.ofr AS OFR, r.ife AS IFE, r.ofe AS OFE, r.tdp AS TDP,
           r.cntct_l AS Cntct_L, r.cntct_r AS Cntct_R,
           r.stf_l AS Stf_L, r.stf_r AS Stf_R,
           r.int_ AS Int, r.wrk_ethic AS WrkEthic, r.greed AS Greed,
           r.loy AS Loy, r.lead AS Lead, r.acc AS Acc,
           r.league_id AS LeagueId
    FROM ratings r
    JOIN players p ON r.player_id = p.player_id
    WHERE r.snapshot_date = (
        SELECT MAX(r2.snapshot_date) FROM ratings r2 WHERE r2.player_id = r.player_id
    )
"""



def run():
    from league_context import get_league_dir
    league_dir = get_league_dir()
    conn = _db.get_conn(league_dir)
    _db.init_schema(league_dir)

    state_path = league_dir / "config" / "state.json"
    with open(state_path) as f:
        game_date = json.load(f)["game_date"]
    role_map = {str(k): v for k, v in _cfg.role_map.items()}

    # Pre-load stat history once for batch contract_value calls
    from player_utils import load_stat_history
    bat_hist, pit_hist, two_way = load_stat_history(conn, game_date)
    _cv_hist = (bat_hist, pit_hist, two_way)

    # Career service for rookie eligibility (130 AB / 50 IP)
    _career_ab = dict(conn.execute(
        "SELECT player_id, SUM(ab) FROM batting_stats WHERE split_id=1 GROUP BY player_id"
    ).fetchall())
    _career_ip = dict(conn.execute(
        "SELECT player_id, SUM(ip) FROM pitching_stats WHERE split_id=1 GROUP BY player_id"
    ).fetchall())

    rows = conn.execute(RATINGS_SQL).fetchall()

    prospect_rows = []
    surplus_rows  = []

    for rat in rows:
        p = dict(rat)
        pid   = p["ID"]
        age   = p["Age"]
        level = p["level"]

        role_str = role_map.get(str(p.get("role") or 0), "position_player")
        p["_role"] = role_str
        p["Pos"]   = str(p.get("pos") or "")
        p["_is_pitcher"] = (p["Pos"] == "P" or role_str in ("starter", "reliever", "closer"))
        bucket = assign_bucket(p)
        p["_bucket"] = bucket

        # Defensive potential for position-adjusted scarcity
        _DEF_KEY = {'CF':'PotCF','SS':'PotSS','C':'PotC','2B':'Pot2B','3B':'Pot3B'}
        def_rating = p.get(_DEF_KEY.get(bucket)) or 0

        # Skip foreign/independent league players (not in MLB pipeline)
        if int(level) == 7:
            continue

        if int(level) == 1:
            ovr      = int(p.get("Ovr") or 0)
            surplus = 0
            cv = _contract_value(pid, _conn=conn, _hist=_cv_hist)
            if cv:
                surplus = cv["total_surplus"].get("base", 0)
            surplus_rows.append((
                pid, game_date, p["Name"], bucket, age,
                ovr, ovr, str(ovr), surplus,
                "MLB", p["team_id"], p["parent_team_id"]
            ))
            # Rookie-eligible: <130 career AB AND <50 career IP, age ≤ 24
            if age <= 24 and _career_ab.get(pid, 0) < 130 and _career_ip.get(pid, 0) < 50:
                p["_norm_age"] = LEVEL_NORM_AGE["aaa"]
                p["_level"] = "aaa"
                fv_base, fv_plus = calc_fv(p)
                fv_str = f"{fv_base}+" if fv_plus else str(fv_base)
                if bucket == "RP":
                    raw_pot = p["Pot"]
                    p["_bucket"] = "SP"
                    raw_fv, raw_plus = calc_fv(p)
                    p["_bucket"] = bucket
                else:
                    raw_fv, raw_plus = fv_base, fv_plus
                p_surplus = _prospect_surplus_opt(
                    raw_fv, age, "MLB", bucket, fv_plus=raw_plus,
                    ovr=p.get("Ovr"), pot=p.get("Pot"), def_rating=def_rating
                )
                prospect_rows.append((
                    pid, game_date, fv_base, fv_str,
                    "MLB", bucket, p_surplus
                ))
        elif age <= 24:
            level_key = LEVEL_INT_KEY.get(int(level))
            if not level_key:
                continue
            p["_norm_age"] = LEVEL_NORM_AGE[level_key]
            p["_level"] = level_key
            fv_base, fv_plus = calc_fv(p)
            fv_str = f"{fv_base}+" if fv_plus else str(fv_base)
            level_label = LEVEL_INT_LABEL.get(int(level), str(level))

            # For surplus, use raw FV (before RP Pot discount) so the RP WAR
            # table is the sole positional adjustment — avoids double-discounting.
            if bucket == "RP":
                raw_pot = p["Pot"]
                p["_bucket"] = "SP"          # temporarily remove RP treatment
                raw_fv, raw_plus = calc_fv(p)
                p["_bucket"] = bucket
            else:
                raw_fv, raw_plus = fv_base, fv_plus

            surplus = _prospect_surplus_opt(
                raw_fv, age, level_label, bucket, fv_plus=raw_plus,
                ovr=p.get("Ovr"), pot=p.get("Pot"), def_rating=def_rating
            )
            prospect_rows.append((
                pid, game_date, fv_base, fv_str,
                level_label, bucket, surplus
            ))

    conn.execute("DELETE FROM prospect_fv")
    conn.execute("DELETE FROM player_surplus")
    conn.executemany("INSERT INTO prospect_fv VALUES (?,?,?,?,?,?,?)", prospect_rows)
    conn.executemany("INSERT INTO player_surplus VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", surplus_rows)
    conn.commit()
    conn.close()

    print(f"fv_calc: {len(prospect_rows)} prospects, {len(surplus_rows)} MLB players — eval_date {game_date}")


if __name__ == "__main__":
    run()
