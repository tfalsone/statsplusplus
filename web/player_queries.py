"""Player detail query — builds the full player dict for the player page."""

import os, sys, json

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "scripts"))
from player_utils import norm as _norm, norm_floor as _norm_floor, height_str as _height_str, display_pos as _display_pos, calc_pap, dollars_per_war as _dollars_per_war
from percentiles import get_hitter_percentiles, get_pitcher_percentiles, get_fielding_percentiles
from web_league_context import get_db, get_cfg, team_abbr_map, team_names_map, level_map, pos_map
from constants import ROLE_MAP


def get_player(pid):
    conn = get_db()
    conn.row_factory = None
    year = get_cfg().year

    # Bio
    p = conn.execute("SELECT player_id, name, age, team_id, parent_team_id, level, pos, role FROM players WHERE player_id=?", (pid,)).fetchone()
    if not p:
        conn.close()
        return None

    player_id, name, age, team_id, parent_team_id, level, pos, role = p
    is_pitcher = role in (11, 12, 13)
    org_id = team_id if parent_team_id == 0 else parent_team_id
    level_str = level_map().get(str(level), str(level))

    # Ratings (latest snapshot) — SELECT * + dict to handle leagues with/without extended columns
    r = conn.execute("SELECT * FROM ratings WHERE player_id=? ORDER BY snapshot_date DESC LIMIT 1", (pid,)).fetchone()
    # Build dict from row
    rd = {}
    if r:
        cols = [d[0] for d in conn.execute("SELECT * FROM ratings LIMIT 0").description]
        rd = dict(zip(cols, r))

    ratings = None
    if rd:
        def g(k): return rd.get(k)

        ovr, pot = g("ovr"), g("pot")
        cntct, gap, pw, eye, ks = g("cntct"), g("gap"), g("pow"), g("eye"), g("ks")
        speed, steal = g("speed"), g("steal")
        stf, mov, ctrl_ovr = g("stf"), g("mov"), g("ctrl")
        ctrl_r, ctrl_l = g("ctrl_r"), g("ctrl_l")
        stm, vel, gb = g("stm"), g("vel"), g("gb")
        ofa, ifa, c_arm, c_blk, c_frm = g("ofa"), g("ifa"), g("c_arm"), g("c_blk"), g("c_frm")
        ifr, ofr, ife, ofe, tdp = g("ifr"), g("ofr"), g("ife"), g("ofe"), g("tdp")
        height, bats, throws = g("height"), g("bats"), g("throws")
        # Extended ratings (may be None if league doesn't have them)
        babip, babip_l, babip_r, pot_babip = g("babip"), g("babip_l"), g("babip_r"), g("pot_babip")
        hra, hra_l, hra_r, pot_hra = g("hra"), g("hra_l"), g("hra_r"), g("pot_hra")
        pbabip, pbabip_l, pbabip_r, pot_pbabip = g("pbabip"), g("pbabip_l"), g("pbabip_r"), g("pot_pbabip")
        prone = g("prone")

        def _char_label(v):
            if v in ("VL", "L", "N", "H", "VH"):
                return {"VL": "Very Low", "L": "Low", "N": "Normal", "H": "High", "VH": "Very High"}[v]
            return None

        # Personality: prefer text values (VL/L/N/H/VH) — numeric values from league export are unreliable
        pers_row = conn.execute(
            "SELECT int_, wrk_ethic, greed, loy, lead FROM ratings "
            "WHERE player_id=? AND wrk_ethic IN ('VL','L','N','H','VH') "
            "ORDER BY snapshot_date DESC LIMIT 1", (pid,)).fetchone()
        if not pers_row:
            pers_row = (g("int_"), g("wrk_ethic"), g("greed"), g("loy"), g("lead"))
        p_int, p_ethic, p_greed, p_loy, p_lead = pers_row

        ratings = {"ovr": ovr, "pot": pot, "height": _height_str(height), "bats": bats, "throws": throws,
                   "personality": {"int": _char_label(p_int), "ethic": _char_label(p_ethic),
                                   "greed": _char_label(p_greed), "loy": _char_label(p_loy), "lead": _char_label(p_lead)},
                   "prone": prone if prone else None}

        if is_pitcher:
            ctrl = ctrl_ovr or (round((ctrl_r + ctrl_l) / 2) if ctrl_r and ctrl_l else ctrl_r or ctrl_l)
            ratings["stuff"] = (_norm(stf), _norm(g("pot_stf")))
            ratings["movement"] = (_norm(mov), _norm(g("pot_mov")))
            ratings["control"] = (_norm(ctrl), _norm(g("pot_ctrl")))
            ratings["stamina"] = _norm(stm)
            ratings["velocity"] = vel
            if gb: ratings["gb"] = gb
            if hra is not None:
                ratings["hra"] = (_norm(hra), _norm(pot_hra))
            if pbabip is not None:
                ratings["pbabip"] = (_norm(pbabip), _norm(pot_pbabip))
            ratings["splits"] = {
                "stuff": (_norm(g("stf_l")), _norm(g("stf_r"))),
                "movement": (_norm(g("mov_l")), _norm(g("mov_r"))),
                "control": (_norm(ctrl_l), _norm(ctrl_r)),
            }
            if hra_l is not None:
                ratings["splits"]["hra"] = (_norm(hra_l), _norm(hra_r))
            if pbabip_l is not None:
                ratings["splits"]["pbabip"] = (_norm(pbabip_l), _norm(pbabip_r))
            pitches = []
            pitch_raw = [
                ("fst", "pot_fst", "Fastball"), ("snk", "pot_snk", "Sinker"), ("crv", "pot_crv", "Curveball"),
                ("sld", "pot_sld", "Slider"), ("chg", "pot_chg", "Changeup"), ("splt", "pot_splt", "Splitter"),
                ("cutt", "pot_cutt", "Cutter"), ("cir_chg", "pot_cir_chg", "Circle Change"),
                ("scr", "pot_scr", "Screwball"), ("frk", "pot_frk", "Forkball"),
                ("kncrv", "pot_kncrv", "Knuckle Curve"), ("knbl", "pot_knbl", "Knuckleball"),
            ]
            for cur_k, fut_k, label in pitch_raw:
                cur, fut = g(cur_k), g(fut_k)
                if cur or fut:
                    pitches.append({"name": label, "cur": _norm(cur), "fut": _norm(fut)})
            pitches.sort(key=lambda x: -(x["cur"] or 0))
            ratings["pitches"] = pitches
        else:
            ratings["hit"] = (_norm(cntct), _norm(g("pot_cntct")))
            ratings["gap"] = (_norm(gap), _norm(g("pot_gap")))
            ratings["power"] = (_norm(pw), _norm(g("pot_pow")))
            ratings["eye"] = (_norm(eye), _norm(g("pot_eye")))
            ratings["krate"] = (_norm(ks), _norm(g("pot_ks")))
            if babip is not None:
                ratings["babip"] = (_norm(babip), _norm(pot_babip))
            ratings["speed"] = _norm(speed)
            ratings["steal"] = _norm(steal)
            ratings["splits"] = {
                "hit": (_norm(g("cntct_l")), _norm(g("cntct_r"))),
                "gap": (_norm(g("gap_l")), _norm(g("gap_r"))),
                "power": (_norm(g("pow_l")), _norm(g("pow_r"))),
                "eye": (_norm(g("eye_l")), _norm(g("eye_r"))),
                "krate": (_norm(g("ks_l")), _norm(g("ks_r"))),
            }
            if babip_l is not None:
                ratings["splits"]["babip"] = (_norm(babip_l), _norm(babip_r))
            c_def, ss_def = g("c"), g("ss")
            second_b, third_b, first_b = g("second_b"), g("third_b"), g("first_b")
            lf, cf_def, rf = g("lf"), g("cf"), g("rf")
            pot_c, pot_ss, pot_2b = g("pot_c"), g("pot_ss"), g("pot_second_b")
            pot_3b, pot_1b = g("pot_third_b"), g("pot_first_b")
            pot_lf, pot_cf, pot_rf = g("pot_lf"), g("pot_cf"), g("pot_rf")
            def_grades = [
                ("C", c_def, pot_c), ("1B", first_b, pot_1b), ("2B", second_b, pot_2b),
                ("3B", third_b, pot_3b), ("SS", ss_def, pot_ss),
                ("LF", lf, pot_lf), ("CF", cf_def, pot_cf), ("RF", rf, pot_rf),
            ]
            ratings["defense"] = [{"pos": lbl, "cur": _norm(c), "fut": _norm(f)}
                                  for lbl, c, f in def_grades if c and c >= 20]
            is_of = pos in (7, 8, 9)
            is_c = pos == 2
            if is_c:
                ratings["arm"] = _norm(c_arm)
            elif is_of:
                ratings["arm"] = _norm(ofa)
                if ofr: ratings["range"] = _norm(ofr)
                if ofe: ratings["error"] = _norm(ofe)
            else:
                ratings["arm"] = _norm(ifa)
                if ifr: ratings["range"] = _norm(ifr)
                if ife: ratings["error"] = _norm(ife)
                if tdp and pos in (3, 4, 5, 6):
                    ratings["tdp"] = _norm(tdp)
            if c_def and c_def >= 20:
                ratings["blocking"] = _norm(c_blk)
                ratings["framing"] = _norm(c_frm)

    # Two-way: build a full hitter ratings dict so the template can render the standard hitter view
    hit_ratings = None
    if is_pitcher and rd and cntct and cntct >= 20:
        c_def, ss_def = g("c"), g("ss")
        second_b, third_b, first_b = g("second_b"), g("third_b"), g("first_b")
        lf, cf_def, rf = g("lf"), g("cf"), g("rf")
        pot_c, pot_ss, pot_2b = g("pot_c"), g("pot_ss"), g("pot_second_b")
        pot_3b, pot_1b = g("pot_third_b"), g("pot_first_b")
        pot_lf, pot_cf, pot_rf = g("pot_lf"), g("pot_cf"), g("pot_rf")
        hit_ratings = {
            "ovr": ratings["ovr"] if ratings else None, "pot": ratings["pot"] if ratings else None,
            "height": ratings.get("height"), "bats": ratings.get("bats"), "throws": ratings.get("throws"),
            "personality": ratings.get("personality") if ratings else None,
            "hit": (_norm(cntct), _norm(g("pot_cntct"))),
            "gap": (_norm(gap), _norm(g("pot_gap"))),
            "power": (_norm(pw), _norm(g("pot_pow"))),
            "eye": (_norm(eye), _norm(g("pot_eye"))),
            "krate": (_norm(ks), _norm(g("pot_ks"))),
            **({"babip": (_norm(babip), _norm(pot_babip))} if babip is not None else {}),
            "speed": _norm(speed), "steal": _norm(steal),
            "splits": {
                "hit": (_norm(g("cntct_l")), _norm(g("cntct_r"))),
                "gap": (_norm(g("gap_l")), _norm(g("gap_r"))),
                "power": (_norm(g("pow_l")), _norm(g("pow_r"))),
                "eye": (_norm(g("eye_l")), _norm(g("eye_r"))),
                "krate": (_norm(g("ks_l")), _norm(g("ks_r"))),
                **({"babip": (_norm(babip_l), _norm(babip_r))} if babip_l is not None else {}),
            },
            "defense": [{"pos": lbl, "cur": _norm(c), "fut": _norm(f)}
                        for lbl, c, f in [("C", c_def, pot_c), ("1B", first_b, pot_1b), ("2B", second_b, pot_2b),
                                           ("3B", third_b, pot_3b), ("SS", ss_def, pot_ss),
                                           ("LF", lf, pot_lf), ("CF", cf_def, pot_cf), ("RF", rf, pot_rf)]
                        if c and c >= 20],
            "arm": _norm(ofa) if pos in (7,8,9) else _norm(ifa),
        }

    # Fielding stats
    fielding_stats = []
    for row in conn.execute(
        "SELECT year, position, g, gs, ip, tc, a, po, e, dp, pb, sba, rto, zr, framing, arm "
        "FROM fielding_stats WHERE player_id=? ORDER BY year, position", (pid,)).fetchall():
        yr, fpos, g, gs, ip, tc, a, po, e, dp, pb, sba, rto, zr, framing, arm = row
        if g == 0:
            continue
        fpct = (po + a) / tc if tc else 0
        fielding_stats.append({
            "year": yr, "pos": pos_map().get(fpos, str(fpos)), "g": g, "gs": gs, "ip": ip,
            "tc": tc, "a": a, "po": po, "e": e, "dp": dp,
            "fpct": fpct, "zr": zr,
            "pb": pb if fpos == 2 else None,
            "sba": sba if fpos == 2 else None,
            "rto": rto if fpos == 2 else None,
            "framing": framing if fpos == 2 else None,
            "arm": arm,
        })

    # Surplus / FV
    ed = conn.execute("SELECT MAX(eval_date) FROM player_surplus").fetchone()[0]
    surplus_row = conn.execute(
        "SELECT bucket, ovr, surplus, fv_str, surplus_yr1 FROM player_surplus WHERE player_id=? AND eval_date=?",
        (pid, ed)).fetchone()
    prospect_row = conn.execute(
        "SELECT bucket, fv, fv_str, prospect_surplus, level FROM prospect_fv WHERE player_id=? AND eval_date=?",
        (pid, ed)).fetchone()

    valuation = {}
    if surplus_row:
        valuation["bucket"] = _display_pos(surplus_row[0])
        valuation["ovr"] = surplus_row[1]
        valuation["surplus"] = round(surplus_row[2] / 1e6, 1) if surplus_row[2] else 0
        valuation["fv_str"] = surplus_row[3]
        valuation["type"] = "MLB"
    elif prospect_row:
        valuation["bucket"] = _display_pos(prospect_row[0])
        valuation["fv"] = prospect_row[1]
        valuation["fv_str"] = prospect_row[2]
        valuation["surplus"] = round(prospect_row[3] / 1e6, 1) if prospect_row[3] else 0
        valuation["type"] = "prospect"
        valuation["level"] = prospect_row[4]
        valuation["ovr"] = ratings["ovr"] if ratings else None
        valuation["pot"] = ratings["pot"] if ratings else None
        _def_keys = {'CF':'pot_cf','SS':'pot_ss','C':'pot_c','2B':'pot_second_b','3B':'pot_third_b'}
        valuation["def_rating"] = rd.get(_def_keys.get(prospect_row[0], "")) or 0 if rd else 0

    # Contract
    contract = None
    c = conn.execute("SELECT years, current_year, salary_0, salary_1, salary_2, salary_3, salary_4, salary_5, salary_6, salary_7, no_trade, last_year_team_option, last_year_player_option FROM contracts WHERE player_id=?", (pid,)).fetchone()
    if c:
        yrs, cur_yr = c[0], c[1]
        game_year = get_cfg().year
        salaries = [c[i] for i in range(2, 10)]
        remaining = [(i, salaries[i]) for i in range(cur_yr, min(yrs, 8)) if salaries[i]]
        contract = {
            "years": yrs, "current_year": cur_yr + 1,
            "remaining": [(str(game_year + i - cur_yr), f"${s/1e6:.1f}M" if s >= 1e6 else f"${s/1e3:.0f}K") for i, s in remaining],
            "no_trade": c[10], "team_option": c[11], "player_option": c[12],
        }
        # Pending extension
        try:
            ext = conn.execute("SELECT years, salary_0, salary_1, salary_2, salary_3, salary_4, salary_5, salary_6, salary_7, salary_8, salary_9, salary_10, salary_11, salary_12, salary_13, salary_14, no_trade, last_year_team_option, last_year_player_option FROM contract_extensions WHERE player_id=?", (pid,)).fetchone()
        except Exception:
            ext = None
        if ext and ext[0] > 0:
            ext_yrs = ext[0]
            cur_remaining = yrs - cur_yr
            ext_start_year = game_year + cur_remaining
            ext_sals = [(str(ext_start_year + i), f"${ext[1+i]/1e6:.1f}M" if ext[1+i] >= 1e6 else f"${ext[1+i]/1e3:.0f}K")
                        for i in range(ext_yrs) if i < 15]
            contract["extension"] = {
                "years": ext_yrs,
                "salaries": ext_sals,
                "no_trade": ext[16],
                "team_option": ext[17],
                "player_option": ext[18],
            }

    # League averages for ERA+/OPS+
    from web_league_context import league_averages as _load_la
    _la = _load_la()
    lg_era = _la["pitching"]["era"]
    lg_ops = _la["batting"]["obp"] + _la["batting"]["slg"]

    def _bat_row(row):
        yr, ab, h, d, t, hr, rbi, bb, k, sb, pa, war, hbp, sf, g, cs = row
        hbp = hbp or 0; sf = sf or 0; g = g or 0; cs = cs or 0
        avg = h / ab if ab else 0
        obp = (h + bb + hbp) / (ab + bb + hbp + sf) if (ab + bb + hbp + sf) else 0
        slg = (h + d + 2 * t + 3 * hr) / ab if ab else 0
        ops = obp + slg
        iso = slg - avg
        babip_denom = ab - k - hr + sf
        babip = (h - hr) / babip_denom if babip_denom > 0 else 0
        bb_pct = bb / pa * 100 if pa else 0
        so_pct = k / pa * 100 if pa else 0
        ops_plus = round(ops / lg_ops * 100) if lg_ops and ops else 0
        return {
            "year": yr, "g": g, "pa": pa, "ab": ab, "h": h, "hr": hr, "rbi": rbi,
            "bb": bb, "k": k, "sb": sb, "cs": cs,
            "war": round(war, 1) if war else 0,
            "avg": avg, "obp": obp, "slg": slg, "iso": iso,
            "ops": ops, "ops_plus": ops_plus, "babip": babip,
            "bb_pct": bb_pct, "so_pct": so_pct,
        }

    _bat_sql = "SELECT year, ab, h, d, t, hr, rbi, bb, k, sb, pa, war, hbp, sf, g, cs FROM batting_stats WHERE player_id=? AND split_id=? ORDER BY year"

    bat_stats = [_bat_row(r) for r in conn.execute(_bat_sql, (pid, 1)).fetchall()]
    bat_splits = {
        "vl": [_bat_row(r) for r in conn.execute(_bat_sql, (pid, 2)).fetchall()],
        "vr": [_bat_row(r) for r in conn.execute(_bat_sql, (pid, 3)).fetchall()],
    }

    # FIP constant
    tp = conn.execute(
        "SELECT SUM(era*ip)/SUM(ip), SUM(hra), SUM(bb), SUM(k), SUM(ip) FROM team_pitching_stats WHERE split_id=1"
    ).fetchone()
    fip_const = (tp[0] - ((13 * tp[1] + 3 * tp[2] - 2 * tp[3]) / tp[4])) if tp and tp[4] else 3.1

    def _pit_row(row):
        yr, ip, era, k, bb, w, l, sv, war, gs, g, hra, bf, hp, ha, hld, bs, qs, gb, fb, r_field, er = row
        hra = hra or 0; bf = bf or 0; hp = hp or 0; ha = ha or 0
        hld = hld or 0; bs = bs or 0; qs = qs or 0
        gb = gb or 0; fb = fb or 0; r_field = r_field or 0; er = er or 0
        k9 = k * 9 / ip if ip else 0
        bb9 = bb * 9 / ip if ip else 0
        hr9 = hra * 9 / ip if ip else 0
        fip = ((13 * hra + 3 * (bb + hp) - 2 * k) / ip + fip_const) if ip else 0
        era_plus = round(lg_era / era * 100) if era else 0
        babip_denom = bf - k - hra - bb - hp
        p_babip = (ha - hra) / babip_denom if babip_denom > 0 else 0
        k_pct = k / bf * 100 if bf else 0
        bb_pct_p = bb / bf * 100 if bf else 0
        k_bb_pct = k_pct - bb_pct_p
        gb_pct = gb / (gb + fb) * 100 if (gb + fb) else 0
        siera_k = k / bf if bf else 0
        siera_bb = bb / bf if bf else 0
        siera = (6.145 - 16.986 * siera_k + 11.434 * siera_bb
                 + 7.653 * siera_k**2 + 6.664 * siera_bb**2
                 + 0.9) if bf else 0
        return {
            "year": yr, "ip": ip, "era": era, "w": w, "l": l, "sv": sv,
            "k": k, "bb": bb, "war": round(war, 1) if war else 0,
            "gs": gs, "g": g, "hld": hld, "bs": bs, "qs": qs,
            "fip": fip, "siera": siera, "babip": p_babip,
            "hr9": hr9, "bb9": bb9, "k9": k9, "era_plus": era_plus,
            "k_pct": k_pct, "bb_pct": bb_pct_p, "k_bb_pct": k_bb_pct,
            "gb_pct": gb_pct,
        }

    _pit_sql = "SELECT year, ip, era, k, bb, w, l, sv, war, gs, g, hra, bf, hp, ha, hld, bs, qs, gb, fb, r, er FROM pitching_stats WHERE player_id=? AND split_id=? ORDER BY year"

    pit_stats = [_pit_row(r) for r in conn.execute(_pit_sql, (pid, 1)).fetchall()]
    pit_splits = {
        "vl": [_pit_row(r) for r in conn.execute(_pit_sql, (pid, 2)).fetchall()],
        "vr": [_pit_row(r) for r in conn.execute(_pit_sql, (pid, 3)).fetchall()],
    }

    # PAP inputs (gather before conn.close)
    _pap_sal = 0
    _pap_tg = 0
    _pap_year = get_cfg().year
    if surplus_row:
        c_row = conn.execute("SELECT salary_0 FROM contracts WHERE player_id=?", (pid,)).fetchone()
        _pap_sal = c_row[0] if c_row else 0
        _pap_tg = conn.execute(
            "SELECT COUNT(*) FROM games WHERE (home_team=? OR away_team=?) AND date>=? AND played=1",
            (org_id, org_id, f"{_pap_year}-01-01")).fetchone()[0]

    conn.close()

    # Surplus breakdown
    surplus_detail = None
    outcome_probs = None
    try:
        if valuation.get("type") == "MLB":
            import contract_value as _cv
            cv = _cv.contract_value(pid)
            if cv and cv.get("breakdown"):
                surplus_detail = {
                    "rows": [{"year": b["year"], "age": b["age"], "war": round(b["war_base"], 1),
                              "value": round(b["market_value"] / 1e6, 1),
                              "salary": round(b["salary_net"] / 1e6, 1),
                              "surplus": round(b["surplus"] / 1e6, 1)}
                             for b in cv["breakdown"]],
                    "total": {k: round(v / 1e6, 1) for k, v in cv["total_surplus"].items()},
                    "flags": cv.get("flags", []),
                }
        elif valuation.get("type") == "prospect":
            import prospect_value as _pv
            fv = valuation.get("fv", 0)
            bucket_val = valuation.get("bucket", "")
            level_val = valuation.get("level", level_str)
            _dr = valuation.get("def_rating")
            pv = _pv.prospect_surplus(fv, age, level_val, bucket_val,
                                      ovr=valuation.get("ovr"), pot=valuation.get("pot"),
                                      def_rating=_dr)
            opt_total = _pv.prospect_surplus_with_option(
                fv, age, level_val, bucket_val,
                ovr=valuation.get("ovr"), pot=valuation.get("pot"),
                def_rating=_dr)
            if pv and pv.get("breakdown"):
                cert = pv.get("certainty_mult", 1.0)
                scar = pv.get("scarcity_mult", 1.0)
                combined = pv["dev_discount"] * cert * scar
                raw_total = sum(b["market_value"] - b["salary"] for b in pv["breakdown"])
                eta_yr = int(get_cfg().year + pv["years_to_mlb"])
                surplus_detail = {
                    "rows": [{"year": eta_yr + b['control_year'] - 1, "age": b["player_age"],
                              "war": round(b["war"], 1),
                              "value": round(b["market_value"] / 1e6, 1),
                              "salary": round(b["salary"] / 1e6, 1),
                              "surplus": round((b["market_value"] - b["salary"]) / 1e6, 1)}
                             for b in pv["breakdown"]],
                    "total": {"base": round(opt_total / 1e6, 1)},
                    "flags": [f"ETA: {pv['years_to_mlb']:.1f} yrs"],
                    "discount_note": f"× {pv['dev_discount']:.0%} dev"
                                     + (f" × {scar:.2f} scarcity" if scar < 1.0 else "")
                                     + (f" × {cert:.2f} certainty" if cert != 1.0 else "")
                                     + f" = ${opt_total/1e6:.1f}M",
                    "raw_total": round(raw_total / 1e6, 1),
                }
            # Career outcome probabilities
            outcome_probs = _pv.career_outcome_probs(
                fv, age, level_val, bucket_val,
                ovr=valuation.get("ovr"), pot=valuation.get("pot"),
                def_rating=_dr)
        # MLB player who is also rookie-eligible (in prospect_fv)
        if valuation.get("type") == "MLB" and prospect_row and outcome_probs is None:
            import prospect_value as _pv
            _fv = prospect_row[1]
            _bucket = _display_pos(prospect_row[0])
            _level = prospect_row[4]
            outcome_probs = _pv.career_outcome_probs(
                _fv, age, _level, _bucket,
                ovr=ratings["ovr"] if ratings else None,
                pot=ratings["pot"] if ratings else None,
                def_rating=valuation.get("def_rating"))
        # Amateur/draft prospect — not in prospect_fv or player_surplus
        if not valuation and outcome_probs is None and level_str not in ('MLB','AAA','AA','A','A-Short','Rookie','International'):
            try:
                import prospect_value as _pv
                from player_utils import assign_bucket, calc_fv, LEVEL_NORM_AGE
                from fv_calc import RATINGS_SQL
                _conn2 = get_db()
                _rat = _conn2.execute(RATINGS_SQL + " AND r.player_id = ?", (pid,)).fetchone()
                if _rat:
                    _p = dict(_rat)
                    _role_map = {str(k): v for k, v in get_cfg().role_map.items()}
                    _p["_role"] = _role_map.get(str(_p.get("role") or 0), "position_player")
                    _p["Pos"] = str(_p.get("pos") or "")
                    _p["_is_pitcher"] = (_p["Pos"] == "P" or _p["_role"] in ("starter","reliever","closer"))
                    _bucket = assign_bucket(_p)
                    _p["_bucket"] = _bucket
                    _lvl_key = {'11':'intl','10':'a','0':'dsl'}.get(str(_p.get("level","")), 'dsl')
                    _p["_norm_age"] = _p["Age"] + 4
                    _p["_level"] = "a-short"
                    _fv, _fv_plus = calc_fv(_p)
                    _fv_str = f"{_fv}+" if _fv_plus else str(_fv)
                    valuation = {
                        "type": "prospect", "bucket": _display_pos(_bucket),
                        "fv": _fv, "fv_str": _fv_str,
                        "ovr": _p["Ovr"], "pot": _p["Pot"],
                        "surplus": 0, "level": _lvl_key,
                    }
                    outcome_probs = _pv.career_outcome_probs(
                        _fv, age,
                        'aaa' if _p["Ovr"] >= 45 else 'aa' if _p["Ovr"] >= 35 else 'a' if _p["Ovr"] >= 28 else 'a-short',
                        _bucket, ovr=_p["Ovr"], pot=_p["Pot"])
            except Exception:
                pass
    except Exception:
        pass

    # Scouting summary
    summary = None
    league_dir = str(get_cfg().league_dir)
    for fname in ("prospects.json", "roster_notes.json"):
        path = os.path.join(league_dir, "history", fname)
        if os.path.exists(path):
            with open(path) as f:
                notes = json.load(f)
            entry = notes.get(str(pid))
            if entry and entry.get("summary"):
                summary = entry["summary"]
                break

    pos_str = ROLE_MAP.get(role, pos_map().get(pos, "?")) if is_pitcher else pos_map().get(pos, "?")

    # Two-way detection: has both meaningful batting and pitching stats
    is_two_way = bool(bat_stats and pit_stats and
                      any(s["pa"] >= 30 for s in bat_stats) and
                      any(s["ip"] >= 15 for s in pit_stats))

    percentiles = None
    pctile_splits = {}
    bat_percentiles = None
    bat_pctile_splits = {}
    fielding_pctiles = None
    if not is_pitcher and bat_stats:
        percentiles = get_hitter_percentiles(pid)
        for sid, key in ((2, "vl"), (3, "vr")):
            sp = get_hitter_percentiles(pid, split_id=sid)
            if sp:
                pctile_splits[key] = sp
    elif is_pitcher and pit_stats:
        percentiles = get_pitcher_percentiles(pid)
        for sid, key in ((2, "vl"), (3, "vr")):
            sp = get_pitcher_percentiles(pid, split_id=sid)
            if sp:
                pctile_splits[key] = sp
        # Two-way: also get hitter percentiles
        if is_two_way:
            bat_percentiles = get_hitter_percentiles(pid)
            for sid, key in ((2, "vl"), (3, "vr")):
                sp = get_hitter_percentiles(pid, split_id=sid)
                if sp:
                    bat_pctile_splits[key] = sp
    if fielding_stats:
        fielding_pctiles = get_fielding_percentiles(pid)

    # Prospect comps
    prospect_comps = None
    if valuation and valuation.get("type") == "prospect":
        from queries import get_prospect_comps
        prospect_comps = get_prospect_comps(pid)
    elif valuation and valuation.get("type") == "MLB" and prospect_row:
        from queries import get_prospect_comps
        prospect_comps = get_prospect_comps(pid)

    # PAP score (MLB players only — from actual production)
    pap = None
    if surplus_row and (bat_stats or pit_stats):
        _war = 0
        if bat_stats and bat_stats[-1]["year"] == _pap_year:
            _war += bat_stats[-1]["war"]
        if pit_stats and pit_stats[-1]["year"] == _pap_year:
            _war += pit_stats[-1]["war"]
        _dpw = _dollars_per_war()
        pap = calc_pap(_war, _pap_sal, _pap_tg, _dpw)

    return {
        "pid": pid, "name": name, "age": age, "pos": pos_str,
        "team": team_names_map().get(org_id, "?"), "team_abbr": team_abbr_map().get(org_id, "?"), "tid": org_id,
        "level": level_str, "is_pitcher": is_pitcher, "is_two_way": is_two_way,
        "ratings": ratings, "hit_ratings": hit_ratings, "valuation": valuation, "contract": contract,
        "bat_stats": bat_stats, "pit_stats": pit_stats, "summary": summary,
        "bat_splits": bat_splits, "pit_splits": pit_splits,
        "surplus_detail": surplus_detail, "outcome_probs": outcome_probs, "percentiles": percentiles,
        "pctile_splits": pctile_splits, "fielding_stats": fielding_stats,
        "fielding_pctiles": fielding_pctiles,
        "bat_percentiles": bat_percentiles, "bat_pctile_splits": bat_pctile_splits,
        "prospect_comps": prospect_comps, "pap": pap,
    }


def get_player_popup(pid):
    """Lightweight player data for hover popup."""
    conn = get_db()
    year = get_cfg().year

    p = conn.execute(
        "SELECT name, age, team_id, parent_team_id, level, pos, role FROM players WHERE player_id=?",
        (pid,)
    ).fetchone()
    if not p:
        conn.close()
        return None

    is_pitcher = p["role"] in (11, 12, 13)
    org_id = p["team_id"] if p["parent_team_id"] == 0 else p["parent_team_id"]

    r = conn.execute(
        "SELECT ovr, pot, height, bats, throws, "
        "cntct, gap, pow, eye, ks, speed, "
        "stf, mov, ctrl, ctrl_r, ctrl_l, stm, vel, "
        "fst, snk, crv, sld, chg, splt, cutt, cir_chg, scr, frk, kncrv, knbl, "
        "pot_fst, pot_snk, pot_crv, pot_sld, pot_chg, pot_splt, pot_cutt, pot_cir_chg, pot_scr, pot_frk, pot_kncrv, pot_knbl, "
        "pot_cntct, pot_gap, pot_pow, pot_eye, pot_ks, "
        "pot_stf, pot_mov, pot_ctrl, "
        "c, ss, second_b, third_b, first_b, lf, cf, rf "
        "FROM ratings WHERE player_id=? ORDER BY snapshot_date DESC LIMIT 1",
        (pid,)
    ).fetchone()

    # Current year stats
    stats = None
    bat_stats = None
    if is_pitcher:
        s = conn.execute(
            "SELECT ip, era, k, bb, war, sv, hld, g, gs FROM pitching_stats WHERE player_id=? AND year=? AND split_id=1",
            (pid, year)
        ).fetchone()
        if s:
            stats = {"ip": s["ip"], "era": round(s["era"], 2) if s["era"] else None,
                     "k": s["k"], "bb": s["bb"], "war": round(s["war"], 1) if s["war"] else 0,
                     "sv": s["sv"], "hld": s["hld"], "g": s["g"], "gs": s["gs"]}
        # Two-way: also fetch batting stats
        bs = conn.execute(
            "SELECT pa, avg, obp, slg, hr, war, sb FROM batting_stats WHERE player_id=? AND year=? AND split_id=1",
            (pid, year)
        ).fetchone()
        if bs and (bs["pa"] or 0) >= 30:
            bat_stats = {"pa": bs["pa"], "avg": round(bs["avg"], 3) if bs["avg"] else None,
                         "obp": round(bs["obp"], 3) if bs["obp"] else None,
                         "slg": round(bs["slg"], 3) if bs["slg"] else None,
                         "hr": bs["hr"], "war": round(bs["war"], 1) if bs["war"] else 0, "sb": bs["sb"]}
    else:
        s = conn.execute(
            "SELECT pa, avg, obp, slg, hr, war, sb FROM batting_stats WHERE player_id=? AND year=? AND split_id=1",
            (pid, year)
        ).fetchone()
        if s:
            stats = {"pa": s["pa"], "avg": round(s["avg"], 3) if s["avg"] else None,
                     "obp": round(s["obp"], 3) if s["obp"] else None,
                     "slg": round(s["slg"], 3) if s["slg"] else None,
                     "hr": s["hr"], "war": round(s["war"], 1) if s["war"] else 0, "sb": s["sb"]}

    # Surplus
    ed = conn.execute("SELECT MAX(eval_date) FROM player_surplus").fetchone()[0]
    sur = conn.execute(
        "SELECT surplus, surplus_yr1, bucket FROM player_surplus WHERE player_id=? AND eval_date=?", (pid, ed)
    ).fetchone()
    # Prospect FV
    fv_row = conn.execute(
        "SELECT fv, fv_str, level, bucket FROM prospect_fv WHERE player_id=? AND eval_date=?", (pid, ed)
    ).fetchone()

    # PAP from actual production
    _pap = None
    if sur:
        _war = 0
        if stats and "war" in stats:
            _war += stats["war"] or 0
        if bat_stats and "war" in bat_stats:
            _war += bat_stats["war"] or 0
        _tg = conn.execute(
            "SELECT COUNT(*) FROM games WHERE (home_team=? OR away_team=?) AND date>=? AND played=1",
            (org_id, org_id, f"{year}-01-01")).fetchone()[0]
        _dpw = _dollars_per_war()
        _sal = conn.execute("SELECT salary_0 FROM contracts WHERE player_id=?", (pid,)).fetchone()
        _pap = calc_pap(_war, _sal[0] if _sal else 0, _tg, _dpw)

    conn.close()

    pos_str = ROLE_MAP.get(p["role"], pos_map().get(p["pos"], "?")) if is_pitcher else pos_map().get(p["pos"], "?")
    level_str = level_map().get(str(p["level"]), str(p["level"]))
    team_name = team_abbr_map().get(org_id, team_names_map().get(org_id, "?"))

    ratings = None
    if r:
        n = _norm
        if is_pitcher:
            ctrl = r["ctrl"] or (round((r["ctrl_r"] + r["ctrl_l"]) / 2) if r["ctrl_r"] is not None else None)
            pot_ctrl_val = r["pot_ctrl"]
            pitches = []
            for fld, name in [("fst","FB"),("snk","SI"),("crv","CB"),("sld","SL"),
                               ("chg","CH"),("splt","SPL"),("cutt","CUT"),("cir_chg","CC"),
                               ("scr","SCR"),("frk","FRK"),("kncrv","KC"),("knbl","KN")]:
                v = r[fld]
                pot_v = r["pot_" + fld] if ("pot_" + fld) in r.keys() else None
                if (v and v >= 25) or (pot_v and pot_v >= 25):
                    pitches.append({"name": name, "cur": n(v or 0), "pot": n(pot_v or v or 0)})
            pitches.sort(key=lambda x: x["pot"], reverse=True)
            ratings = {
                "stf": [n(r["stf"]), n(r["pot_stf"])] if r["stf"] else None,
                "mov": [n(r["mov"]), n(r["pot_mov"])] if r["mov"] else None,
                "ctl": [n(ctrl), n(pot_ctrl_val)] if ctrl else None,
                "stm": n(r["stm"]) if r["stm"] else None,
                "vel": r["vel"],
                "pitches": pitches[:4],
            }
            # Two-way: also include batting tools
            if bat_stats and r["cntct"] and r["cntct"] >= 20:
                ratings["bat"] = {
                    "con": [n(r["cntct"]), n(r["pot_cntct"])],
                    "pow": [n(r["pow"]), n(r["pot_pow"])],
                    "eye": [n(r["eye"]), n(r["pot_eye"])],
                    "spd": n(r["speed"]) if r["speed"] else None,
                }
        else:
            ratings = {
                "con": [n(r["cntct"]), n(r["pot_cntct"])] if r["cntct"] else None,
                "pow": [n(r["pow"]), n(r["pot_pow"])] if r["pow"] else None,
                "eye": [n(r["eye"]), n(r["pot_eye"])] if r["eye"] else None,
                "spd": n(r["speed"]) if r["speed"] else None,
            }
            # Primary position defense
            _def_map = {"c":"C","ss":"SS","second_b":"2B","third_b":"3B","first_b":"1B","lf":"LF","cf":"CF","rf":"RF"}
            best_def_pos = None
            best_def_grade = 0
            for col, label in _def_map.items():
                pot_col = "pot_" + col
                v = (r[pot_col] if pot_col in r.keys() else None) or (r[col] if col in r.keys() else None) or 0
                g = n(v)
                if g and g > best_def_grade:
                    best_def_grade = g
                    best_def_pos = label
            if best_def_pos and best_def_grade > 20:
                ratings["def"] = {"pos": best_def_pos, "grade": best_def_grade}

    result = {
        "name": p["name"], "age": p["age"], "pos": pos_str,
        "level": level_str, "team": team_name, "tid": org_id, "is_pitcher": is_pitcher,
        "ovr": r["ovr"] if r else None, "pot": r["pot"] if r else None,
        "height": _height_str(r["height"]) if r and r["height"] else None,
        "bats": r["bats"] if r else None, "throws": r["throws"] if r else None,
        "stats": stats, "bat_stats": bat_stats, "ratings": ratings,
        "is_two_way": bat_stats is not None,
        "surplus": round(sur["surplus"] / 1e6, 1) if sur and sur["surplus"] else None,
        "pap": _pap,
        "bucket": (sur["bucket"] if sur else fv_row["bucket"] if fv_row else None),
        "fv": fv_row["fv_str"] if fv_row else None,
    }
    return result
