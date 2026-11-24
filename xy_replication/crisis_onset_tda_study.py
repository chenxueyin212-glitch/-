"""READ-ONLY diagnostic: does a HIGH H2 hole count precede crises?

Two user questions are addressed, and one prior misreading is corrected:

  Q0 (correction) "N low is effective"  -- NOT supported by the previous
     diagnostics.  The daily IC of low N was inflated by repeated days inside
     the same event; the event-start IC is 0.0131 with a CI crossing zero and
     permutation p ~ 0.5.  This script does not re-litigate that; it only
     records the correction in the JSON/report.

  Q1 Can a HIGH N predict a crisis?  Crisis label is borrowed from the frozen
     Gate 0 protocol: Y_t = 1 if the minimum cumulative SIMPLE return of the
     benchmark over the next 20 trading days, measured from the t close, is
     <= -10%.  Two benchmark variants: Wind All-A 881001.WI (main, matches
     the Xingye replication line and all previous IC work) and the frozen
     Gate 0 composite of 000001/399001 (sensitivity ONLY, truncated at
     2024-12-31 with the frozen label_end boundary so no 2025 test row is
     ever read).

  Q2 What do the persistence summaries look like BEFORE a crisis?  Event-time
     paths of H1/H2 counts, landscape L1, max H2 persistence, Betti numbers,
     average industry correlation, leading eigenvalue share and node count.

Everything is in-sample and descriptive.  Crisis labels use FUTURE returns by
construction, so they are retrospective annotations, NOT tradable signals.
Signals are evaluated with an event-level lead window [e-L, e-1] to keep the
"early warning" semantics, plus two permutation nulls (global circular shift
and SAME-YEAR circular shift, the latter controlling the strong drift of N).
No existing output file is modified.  Gate 1 stays paused; the 2025 final
test is not read; Gate 2 not started.

Outputs (all under outputs/):
  xy_crisis_onset_tda.json, xy_crisis_events.csv,
  xy_crisis_signal_grid.csv, xy_crisis_onset_tda.png
"""
from __future__ import annotations

import csv
import json
import math
import sqlite3
from datetime import date, datetime
from pathlib import Path

import numpy as np
from scipy.stats import rankdata

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
WORKSPACE = ROOT.parent
FEATURE_CSV = OUT / "xy_corrected_sw193_ifind_peak_features.csv"
WIND_CSV = OUT / "xy_wind_all_a_daily.csv"
DB = WORKSPACE / "a_share_pit" / "tdx_central.db"

JSON_OUT = OUT / "xy_crisis_onset_tda.json"
EVENT_CSV = OUT / "xy_crisis_events.csv"
GRID_CSV = OUT / "xy_crisis_signal_grid.csv"
FIG_OUT = OUT / "xy_crisis_onset_tda.png"

START, END = "2015-07-01", "2025-05-30"
H = 20
DROP = -0.10
GAP_EVENT_CALENDAR_DAYS = 20
GAP_SIGNAL_CALENDAR_DAYS = 10
LEADS = (5, 10, 20)
BLOCK, N_BOOT, SEED = 20, 1000, 20261108
N_EVENT_BOOT, N_PERM = 10000, 2000

FEATURES = [
    "h2_count", "h1_count", "h2_landscape_l1", "h1_landscape_l1",
    "max_h2_persistence", "h2_betti_0p4", "h2_betti_0p6", "h2_betti_0p8",
    "industry_average_correlation", "correlation_leading_eigenvalue_share",
    "n_nodes",
]
PATH_OFFSETS = (-40, -30, -20, -10, -5, 0, 5, 10, 20)


def finite_or_none(v):
    if v is None:
        return None
    f = float(v)
    return f if math.isfinite(f) else None


def pearson(x, y):
    if len(x) < 3:
        return float("nan")
    xc, yc = x - x.mean(), y - y.mean()
    den = math.sqrt(float(xc @ xc) * float(yc @ yc))
    return float(xc @ yc / den) if den > 0 else float("nan")


def spearman(x, y):
    return pearson(rankdata(x), rankdata(y))


def average_precision(score, y):
    """Step-wise PR-AUC (average precision). Higher score = predicts crisis."""
    m = np.isfinite(score) & (y >= 0)
    s, yy = np.asarray(score)[m], np.asarray(y)[m].astype(int)
    if yy.sum() == 0 or yy.sum() == len(yy):
        return float("nan")
    order = np.argsort(-s, kind="stable")
    yy = yy[order]
    tp = np.cumsum(yy)
    prec = tp / np.arange(1, len(yy) + 1)
    return float((prec * yy).sum() / yy.sum())


def ordinals(dates):
    return np.asarray([date.fromisoformat(d).toordinal() for d in dates])


def clusters_from_flags(flags, dates, ords, gap_days, allowed=None):
    """Merge flagged days into clusters separated by > gap CALENDAR days."""
    idx = np.flatnonzero(flags)
    if allowed is not None:
        idx = np.asarray([i for i in idx if allowed[i]])
    out, cur = [], []
    for i in idx:
        if cur and ords[i] - ords[cur[-1]] > gap_days:
            out.append(cur)
            cur = []
        cur.append(int(i))
    if cur:
        out.append(cur)
    return out


def read_inputs():
    frows = [r for r in csv.DictReader(FEATURE_CSV.open(encoding="utf-8-sig"))
             if r["date"] <= END]
    dates = [r["date"] for r in frows]
    n = len(dates)
    F = {k: np.asarray([float(r[k]) for r in frows]) for k in FEATURES}
    N = F["h2_count"].astype(int)

    wind = {r["date"]: (float(r["open"]), float(r["close"]), float(r["low"]))
            for r in csv.DictReader(WIND_CSV.open(encoding="utf-8-sig"))}
    close = np.asarray([wind[d][1] for d in dates])
    op = np.asarray([wind[d][0] for d in dates])
    low = np.asarray([wind[d][2] for d in dates])

    # frozen Gate 0 composite: I_t = I_{t-1} * (1 + .5*(r_000001 + r_399001))
    # only common dates, and only up to 2024-12-31 (no 2025 test rows read)
    con = sqlite3.connect(str(DB))
    sh = dict(con.execute("select date, close from index_daily_raw "
                          "where code='000001' and market=1"))
    sz = dict(con.execute("select date, close from index_daily_raw "
                          "where code='399001' and market=0"))
    common = sorted(set(sh) & set(sz))
    common = [d for d in common if d <= "2024-12-31"]
    level, comp = 1.0, {}
    prev = None
    for d in common:
        if prev is not None:
            r1 = sh[d] / sh[prev] - 1
            r2 = sz[d] / sz[prev] - 1
            level *= 1 + 0.5 * (r1 + r2)
        comp[d] = level
        prev = d
    con.close()
    comp_dates = [d for d in dates if d in comp]
    comp_close = np.asarray([comp[d] for d in comp_dates])

    return dict(dates=dates, n=n, F=F, N=N, close=close, op=op, low=low,
                ords=ordinals(dates), wind_days=len(wind),
                comp_dates=comp_dates, comp_close=comp_close)


def crisis_labels(prices, dates, threshold=DROP, horizon=H,
                  label_end_boundary=None):
    """Y_t=1 iff min_{j=1..h}(P_{t+j}/P_t - 1) <= threshold. None = undecided."""
    n = len(prices)
    y = np.full(n, -1, dtype=int)
    worst = np.full(n, np.nan)
    worst_date = [None] * n
    for i in range(n - horizon):
        fut = prices[i + 1:i + horizon + 1] / prices[i] - 1
        j = int(np.argmin(fut))
        worst[i] = float(fut[j])
        worst_date[i] = dates[i + j + 1]
        if label_end_boundary is not None and dates[i + horizon] >= label_end_boundary:
            continue  # frozen development-label boundary
        y[i] = int(fut[j] <= threshold)
    return y, worst, worst_date


def causal_midrank(N, W, dates_ords=None):
    """rho_t = (#{N_s < N_t} + 0.5*#{N_s = N_t})/W, s in [t-W+1, t]."""
    n = len(N)
    rho = np.full(n, np.nan)
    for t in range(W - 1, n):
        win = N[t - W + 1:t + 1]
        less = int((win < N[t]).sum())
        equal = int((win == N[t]).sum())
        rho[t] = (less + 0.5 * equal) / W
    return rho


def forward_returns(op, h):
    n = len(op)
    ro = np.full(n, np.nan)
    ro[:n - h - 1] = op[h + 1:] / op[1:n - h] - 1
    return ro


def block_boot_precision(s, y, valid, idx_matrix):
    """Paired moving-block bootstrap of P(Y=1 | s=1)."""
    sv, yv = s[valid], y[valid]
    vals = []
    for idx in idx_matrix:
        ss, yy = sv[idx], yv[idx]
        m = ss == 1
        vals.append(float(yy[m].mean()) if m.sum() >= 3 else float("nan"))
    fin = [v for v in vals if math.isfinite(v)]
    if len(fin) < 10:
        return [None, None], len(vals) - len(fin)
    return [float(np.quantile(fin, 0.025)), float(np.quantile(fin, 0.975))], len(vals) - len(fin)


def circular_shift(s, offsets_by_year, year_index, n_years):
    """Independent circular shift inside each calendar-year block."""
    out = np.empty_like(s)
    for yy in range(n_years):
        m = year_index == yy
        k = int(m.sum())
        if k == 0:
            continue
        out[m] = np.roll(s[m], offsets_by_year[yy])
    return out


def main():
    D = read_inputs()
    dates, n, F, N = D["dates"], D["n"], D["F"], D["N"]
    ords, close, op = D["ords"], D["close"], D["op"]
    rep = np.asarray([START <= d <= END for d in dates])

    # ---------------- crisis labels --------------------------------------
    y, worst, worst_date = crisis_labels(close, dates)
    valid = rep & (y >= 0)
    prevalence = float(y[valid].mean())
    y_full = np.where(valid, y, -1)

    # sensitivity: frozen composite, truncated by the frozen label boundary
    cy, cworst, cworst_date = crisis_labels(
        D["comp_close"], D["comp_dates"], label_end_boundary="2025-01-01")
    cset = {d: int(v) for d, v in zip(D["comp_dates"], cy)}
    y_comp = np.asarray([cset.get(d, -1) for d in dates])
    valid_comp = rep & (y_comp >= 0)

    # sensitivity thresholds on the main benchmark
    y05, _, _ = crisis_labels(close, dates, threshold=-0.05)
    y15, _, _ = crisis_labels(close, dates, threshold=-0.15)
    prev05 = float((y05[rep & (y05 >= 0)] == 1).mean())
    prev15 = float((y15[rep & (y15 >= 0)] == 1).mean())

    # ---------------- crisis events --------------------------------------
    flags = (y == 1) & rep          # crisis events ONLY inside the report period
    first_rep_idx = int(np.flatnonzero(rep)[0])
    raw_events = clusters_from_flags(flags, dates, ords,
                                     GAP_EVENT_CALENDAR_DAYS, allowed=rep)
    events = []
    for k, c in enumerate(raw_events, 1):
        e = c[0]
        left_censored = bool(e == first_rep_idx)
        # first date whose forward cumulative return breaches the threshold
        worst_d = worst_date[e]
        events.append({
            "event_id": k,
            "onset": dates[e],
            "onset_index": e,
            "label_end_date": dates[e + H] if e + H < n else None,
            "end": dates[c[-1]],
            "label_run_days": len(c),
            "left_censored_label": left_censored,
            "worst_cumulative_return_from_onset": finite_or_none(worst[e]),
            "worst_date": worst_d,
            "N_at_onset": int(N[e]),
            "avg_corr_at_onset": finite_or_none(F["industry_average_correlation"][e]),
        })
    usable_events = [r for r in events if not r["left_censored_label"]]
    event_onsets = np.asarray([r["onset_index"] for r in usable_events], dtype=int)

    # ---------------- signals: pre-registered grid ------------------------
    rhos = {W: causal_midrank(N, W) for W in (60, 120, 250)}
    signals = []

    def add(name, s, family, note, score=None, continuous=None):
        signals.append(dict(name=name, s=np.asarray(s, dtype=float),
                            family=family, note=note, score=score,
                            continuous=continuous))

    for k in (15, 20, 25, 30):
        add(f"fixed_N_ge_{k}", (N >= k).astype(float), "fixed_high_N",
            "absolute threshold; vulnerable to the N level drift")
    for W in (60, 120, 250):
        for p in (0.80, 0.90, 0.95):
            s = (rhos[W] >= p).astype(float)
            s[np.isnan(rhos[W])] = 0.0
            add(f"roll_N_W{W}_p{int(p*100):02d}", s, "causal_rolling_high_quantile",
                "rho_t uses only [t-W+1,t] history; semantic = N relatively high vs recent past")
    add("low_N_le_1_control", (N <= 1).astype(float), "control_low_N",
        "the Xingye rule; included to check the user's prior reading")
    add("avg_corr_ge_p90", (F["industry_average_correlation"] >=
                            np.quantile(F["industry_average_correlation"][rep], 0.90)
                            ).astype(float), "control_non_tda",
        "simple average correlation, NO topology; in-sample 90th percentile (leaks the future)")
    add("leading_eig_ge_p90", (F["correlation_leading_eigenvalue_share"] >=
                               np.quantile(F["correlation_leading_eigenvalue_share"][rep], 0.90)
                               ).astype(float), "control_non_tda",
        "leading eigenvalue share, NO topology; in-sample 90th percentile (leaks the future)")

    continuous_scores = {
        "score_N": N.astype(float),
        "score_roll_rho_W120": rhos[120],
        "score_avg_corr": F["industry_average_correlation"],
        "score_leading_eig": F["correlation_leading_eigenvalue_share"],
        "score_h2_landscape_l1": F["h2_landscape_l1"],
        "score_h1_landscape_l1": F["h1_landscape_l1"],
        "score_minus_N": -N.astype(float),
    }

    # ---------------- evaluation helpers ----------------------------------
    # lead windows for each event
    lead_mask = {L: np.zeros(n, dtype=bool) for L in LEADS}
    for e in event_onsets:
        for L in LEADS:
            lead_mask[L][max(0, e - L):e] = True
    # loose (contemporaneous) window: onset-L .. end of that Y=1 run
    loose_mask = np.zeros(n, dtype=bool)
    for ev in usable_events:
        e = ev["onset_index"]
        end_i = dates.index(ev["end"])
        loose_mask[max(0, e - 20):end_i + 1] = True

    years = np.asarray([int(d[:4]) for d in dates])
    uniq_years = sorted(set(years.tolist()))
    year_index = np.asarray([uniq_years.index(v) for v in years])
    n_years = len(uniq_years)

    rng = np.random.default_rng(SEED)
    global_offsets = rng.integers(1, n, size=N_PERM)
    year_offsets = np.column_stack([
        rng.integers(1, max(2, int((year_index == yy).sum())), size=N_PERM)
        for yy in range(n_years)
    ])

    # bootstrap index matrix (paired blocks over the valid-day sequence)
    nv = int(valid.sum())
    starts_max = nv - BLOCK + 1
    nb = math.ceil(nv / BLOCK)
    boot_idx = np.concatenate([
        np.arange(s, s + BLOCK)
        for s in rng.integers(0, starts_max, size=(N_BOOT, nb)).ravel()
    ]).reshape(N_BOOT, nb * BLOCK)[:, :nv]

    def lead_recall(s, L=20):
        return float(np.mean([float(s[max(0, e - L):e].max()) > 0
                             if e > 0 else 0.0 for e in event_onsets]))

    def signal_clusters(s):
        return clusters_from_flags(s == 1, dates, ords,
                                   GAP_SIGNAL_CALENDAR_DAYS, allowed=valid)

    report_years = (ords[int(np.flatnonzero(rep)[-1])] -
                    ords[int(np.flatnonzero(rep)[0])]) / 365.25

    grid_rows, boot_degenerate = [], []
    null_recall_matrix = np.zeros((N_PERM, len(signals)))
    for si, sig in enumerate(signals):
        s = sig["s"]
        sv = s[valid]
        on = sv == 1
        n_on = int(on.sum())
        precision = float(y[valid][on].mean()) if n_on else None
        recall = float(on[y[valid] == 1].mean()) if (y[valid] == 1).sum() else None
        lifts = (precision / prevalence) if precision is not None else None
        ci_prec, degen = block_boot_precision(s, y_full, valid, boot_idx)
        if degen:
            boot_degenerate.append({"tag": sig["name"], "degenerate_draws": degen})

        scl = signal_clusters(s)
        hit_clusters = 0
        hit_clusters_loose = 0
        for c in scl:
            m = np.zeros(n, dtype=bool)
            m[c] = True
            if (m & lead_mask[20]).any():
                hit_clusters += 1
            if (m & loose_mask).any():
                hit_clusters_loose += 1
        fp_per_year = (len(scl) - hit_clusters) / report_years

        row = {
            "signal": sig["name"], "family": sig["family"], "note": sig["note"],
            "signal_days_valid": n_on,
            "trigger_share_valid": n_on / int(valid.sum()),
            "signal_clusters": len(scl),
            "precision": finite_or_none(precision),
            "recall_daily": finite_or_none(recall),
            "lift_vs_prevalence": finite_or_none(lifts),
            "ci95_precision": ci_prec,
            "ci95_precision_crosses_prevalence": (
                None if ci_prec[0] is None else bool(ci_prec[0] <= prevalence <= ci_prec[1])),
            "event_lead_recall_L5": lead_recall(s, 5),
            "event_lead_recall_L10": lead_recall(s, 10),
            "event_lead_recall_L20": lead_recall(s, 20),
            "expected_recall_if_iid_at_same_trigger_rate": (
                1 - (1 - n_on / int(valid.sum())) ** 20),
            "recall_minus_iid_expectation": (
                lead_recall(s, 20) - (1 - (1 - n_on / int(valid.sum())) ** 20)),
            "signal_clusters_hit_lead20": hit_clusters,
            "signal_clusters_hit_loose": hit_clusters_loose,
            "false_alarm_clusters_per_year": finite_or_none(fp_per_year),
        }

        # permutation nulls on the two headline statistics
        actual_recall = row["event_lead_recall_L20"]
        actual_prec = precision if precision is not None else float("nan")
        null_g_recall = np.empty(N_PERM)
        null_y_recall = np.empty(N_PERM)
        null_g_prec = np.empty(N_PERM)
        null_y_prec = np.empty(N_PERM)
        event_windows = [np.arange(max(0, e - 20), e) for e in event_onsets]
        for b in range(N_PERM):
            sg = np.roll(s, global_offsets[b])
            sy = circular_shift(s, year_offsets[b], year_index, n_years)
            ng = [float(sg[w].max()) > 0 if len(w) else 0.0 for w in event_windows]
            ny = [float(sy[w].max()) > 0 if len(w) else 0.0 for w in event_windows]
            null_g_recall[b] = np.mean(ng)
            null_y_recall[b] = np.mean(ny)
            null_recall_matrix[b, si] = null_y_recall[b]
            mg, my = sg[valid] == 1, sy[valid] == 1
            null_g_prec[b] = float(y[valid][mg].mean()) if mg.sum() >= 3 else float("nan")
            null_y_prec[b] = float(y[valid][my].mean()) if my.sum() >= 3 else float("nan")

        def pval(null, actual, greater=True):
            fin = null[np.isfinite(null)]
            if len(fin) < 10 or not math.isfinite(actual):
                return None
            if greater:
                return float((fin >= actual).mean())
            ge, le = float((fin >= actual).mean()), float((fin <= actual).mean())
            return float(min(1.0, 2 * min(ge, le)))

        row["perm_global_p_recall_greater"] = pval(null_g_recall, actual_recall)
        row["perm_same_year_p_recall_greater"] = pval(null_y_recall, actual_recall)
        row["perm_global_p_precision_greater"] = pval(null_g_prec, actual_prec)
        row["perm_same_year_p_precision_greater"] = pval(null_y_prec, actual_prec)
        row["null_same_year_recall_mean"] = finite_or_none(float(np.nanmean(null_y_recall)))
        row["null_same_year_precision_mean"] = finite_or_none(float(np.nanmean(null_y_prec)))
        grid_rows.append(row)

    # ---------------- joint max-T correction over the whole grid -----------
    mean_null = null_recall_matrix.mean(axis=0)
    sd_null = null_recall_matrix.std(axis=0, ddof=1)
    sd_safe = np.where(sd_null > 1e-9, sd_null, np.nan)
    actual_recalls = np.asarray([r["event_lead_recall_L20"] for r in grid_rows])
    z_actual = (actual_recalls - mean_null) / sd_safe
    z_null = (null_recall_matrix - mean_null) / sd_safe
    T_obs = float(np.nanmax(z_actual))
    T_null = np.nanmax(z_null, axis=1)
    joint = {
        "method": "same-year circular-shift max-T over all binary signals",
        "n_tests": len(signals),
        "statistic": "max over signals of (recall - permutation mean)/permutation sd",
        "observed_max_T": finite_or_none(T_obs),
        "permutation_null_max_T_mean": finite_or_none(float(np.nanmean(T_null))),
        "p_value": (float(np.nanmean(T_null >= T_obs))
                    if math.isfinite(T_obs) else None),
        "bonferroni_alpha_per_cell": 0.05 / len(signals),
        "smallest_single_cell_same_year_p": float(min(
            r["perm_same_year_p_recall_greater"] for r in grid_rows
            if r["perm_same_year_p_recall_greater"] is not None)),
        "limitation": "circular shift preserves within-year autocorrelation but "
                      "breaks the exact alignment of signal clusters and crisis "
                      "onsets; it is a descriptive null, not a formal causal test",
    }

    # ---------------- incremental value of N beyond plain correlation -----
    corr = F["industry_average_correlation"]
    q90 = float(np.quantile(corr[rep], 0.90))
    hi = (corr >= q90) & valid
    Nfloat = N.astype(float)
    med_hi = float(np.median(Nfloat[hi]))
    g_hiN = hi & (Nfloat >= med_hi)
    g_loN = hi & (Nfloat < med_hi)
    p_hiN, p_loN = float(y[g_hiN].mean()), float(y[g_loN].mean())
    diff_actual = p_hiN - p_loN
    null_diff = np.empty(N_PERM)
    for b in range(N_PERM):
        Ns = circular_shift(Nfloat, year_offsets[b], year_index, n_years)
        mb = float(np.nanmedian(Ns[hi]))
        a, c = hi & (Ns >= mb), hi & (Ns < mb)
        null_diff[b] = (float(y[a].mean()) - float(y[c].mean())
                        if a.sum() >= 3 and c.sum() >= 3 else np.nan)
    nd = null_diff[np.isfinite(null_diff)]

    z_corr = (corr - corr[rep].mean()) / corr[rep].std(ddof=1)
    z_N = (Nfloat - Nfloat[rep].mean()) / Nfloat[rep].std(ddof=1)
    comb_plus, comb_minus = z_corr + z_N, z_corr - z_N
    incremental = {
        "corr_p90_threshold": q90,
        "n_corr_high_days": int(hi.sum()),
        "median_N_within_corr_high": med_hi,
        "P_crisis_given_corr_high_and_N_high": p_hiN,
        "n_corr_high_N_high": int(g_hiN.sum()),
        "P_crisis_given_corr_high_and_N_low": p_loN,
        "n_corr_high_N_low": int(g_loN.sum()),
        "difference_highN_minus_lowN": diff_actual,
        "same_year_permutation_p_two_sided": (
            float(min(1.0, 2 * min((nd >= diff_actual).mean(),
                                   (nd <= diff_actual).mean())))
            if len(nd) >= 10 else None),
        "AP_avg_corr_full": finite_or_none(average_precision(corr, y_full)),
        "AP_minus_N_full": finite_or_none(average_precision(-Nfloat, y_full)),
        "AP_avg_corr_plus_N_z": finite_or_none(average_precision(comb_plus, y_full)),
        "AP_avg_corr_minus_N_z": finite_or_none(average_precision(comb_minus, y_full)),
        "AP_N_within_corr_high": finite_or_none(average_precision(
            np.where(hi, Nfloat, np.nan), y_full)),
        "prevalence_within_corr_high": float(y[hi].mean()),
        "direction_caveat": "both sign conventions of N are disclosed; neither "
                            "was pre-registered as a preferred direction, so "
                            "these are exploratory increment checks only",
    }

    # ---------------- continuous scores: PR-AUC / IC ----------------------
    score_rows = []
    for name, score in continuous_scores.items():
        ap = average_precision(score, y_full)
        ro20 = forward_returns(op, 20)
        m = valid & np.isfinite(score) & np.isfinite(ro20)
        ic = pearson(score[m], ro20[m])
        ic_s = spearman(score[m], ro20[m])
        score_rows.append({
            "score": name,
            "average_precision_prauc": finite_or_none(ap),
            "prauc_lift_vs_prevalence": finite_or_none(ap / prevalence) if math.isfinite(ap) else None,
            "ic_vs_forward20_return": finite_or_none(ic),
            "spearman_vs_forward20_return": finite_or_none(ic_s),
            "n_valid": int(m.sum()),
        })

    # ---------------- segment AP: is the full-sample -N effect drift? -----
    segment_ap = []
    for label, sel in [("2015-2020", rep & (years <= 2020)),
                       ("2021-2025", rep & (years >= 2021)),
                       ("full_report", rep)]:
        yseg = np.where(sel & valid, y, -1)
        row = {"segment": label,
               "n_days": int((sel & valid).sum()),
               "prevalence": float(y[yseg >= 0].mean())}
        for name, score in continuous_scores.items():
            row["AP_" + name] = finite_or_none(average_precision(score, yseg))
        segment_ap.append(row)

    # ---------------- N vs return by horizon (high-N direction) -----------
    horizon_ic = []
    N_valid = N[valid].astype(float)
    for h in (1, 5, 10, 20, 40):
        ro = forward_returns(op, h)
        ro_valid = ro[valid]
        m = valid & np.isfinite(ro)
        x, yy = N[m].astype(float), ro[m]
        vals = []
        for idx in boot_idx:
            ok = np.isfinite(ro_valid[idx])
            if ok.sum() < 10:
                continue
            v = pearson(N_valid[idx][ok], ro_valid[idx][ok])
            if math.isfinite(v):
                vals.append(v)
        ci = ([float(np.quantile(vals, 0.025)), float(np.quantile(vals, 0.975))]
              if len(vals) >= 10 else [None, None])
        horizon_ic.append({
            "horizon_days": h, "n": int(m.sum()),
            "ic_N_vs_forward_return": finite_or_none(pearson(x, yy)),
            "spearman": finite_or_none(spearman(x, yy)),
            "ci95_ic": ci,
            "crosses_zero": (None if ci[0] is None else bool(ci[0] <= 0 <= ci[1])),
        })

    # ---------------- crisis-onset persistence paths ----------------------
    # z-scores and midrank percentiles use the REPORT-PERIOD distribution only
    rep_idx = np.flatnonzero(rep)
    zF, pF = {}, {}
    for k in FEATURES:
        v = F[k][rep_idx]
        mu, sd = float(v.mean()), float(v.std(ddof=1))
        zF[k] = (F[k] - mu) / (sd if sd > 0 else 1.0)
        r = rankdata(v) / (len(v) + 1.0)
        # map every date to a percentile by searchsorted on the sorted report values
        srt = np.sort(v)
        pF[k] = np.asarray([np.searchsorted(srt, x, side="right") / (len(v) + 1.0)
                            for x in F[k]])

    # causal rolling percentile of N (drift-free version)
    rho120 = rhos[120]

    path = {k: {} for k in FEATURES}
    path["roll_rho_N_W120"] = {}
    arrays_for_path = {**zF, "roll_rho_N_W120": np.where(np.isfinite(rho120), rho120, np.nan)}
    for key, arr in arrays_for_path.items():
        for j in PATH_OFFSETS:
            vals = []
            for e in event_onsets:
                q = e + j
                vals.append(float(arr[q]) if 0 <= q < n and math.isfinite(arr[q]) else np.nan)
            v = np.asarray(vals, dtype=float)
            fin = v[np.isfinite(v)]
            if len(fin) < 3:
                path[key][str(j)] = {"n_events": len(fin), "mean": None,
                                     "ci95": [None, None], "median": None}
                continue
            eb = rng.choice(fin, size=(N_EVENT_BOOT, len(fin)), replace=True).mean(axis=1)
            path[key][str(j)] = {
                "n_events": len(fin), "mean": float(fin.mean()),
                "median": float(np.median(fin)),
                "ci95": [float(np.quantile(eb, 0.025)), float(np.quantile(eb, 0.975))],
                "crosses_zero": bool(np.quantile(eb, 0.025) <= 0 <= np.quantile(eb, 0.975)),
            }

    # headline statistic: per-event mean over j in [-20, 0], then mean across events
    window_j = [-20, -10, -5, 0]
    legal_starts = np.asarray([i for i in rep_idx if 0 <= i - 40 and i + 20 < n])
    year_of_legal = np.asarray([int(dates[i][:4]) for i in legal_starts])

    def window_stat(arr, starts, offsets=None):
        offs = window_j if offsets is None else offsets
        cols = np.column_stack([arr[starts + j] for j in offs]).astype(float)
        ok = np.isfinite(cols)
        total = np.where(ok, cols, 0.0).sum(axis=1)
        cnt = ok.sum(axis=1)
        return np.divide(total, cnt, out=np.full(len(total), np.nan),
                         where=cnt > 0)

    # same-year matched permutation null
    per_year_pools = {yy: legal_starts[year_of_legal == yy] for yy in uniq_years}
    real_years = [int(dates[e][:4]) for e in event_onsets]
    n_ev = len(event_onsets)
    null_same_year = {}
    idx_draws = np.column_stack([
        rng.choice(per_year_pools[yy], size=N_PERM, replace=True)
        if len(per_year_pools[yy]) else rng.choice(legal_starts, size=N_PERM, replace=True)
        for yy in real_years
    ])
    for key, arr in arrays_for_path.items():
        null_same_year[key] = (window_stat(arr, idx_draws)
                               if (idx_draws >= 0).all()
                               else np.full(N_PERM, np.nan))

    path_summary = []
    for key, arr in arrays_for_path.items():
        actual = float(np.nanmean(window_stat(arr, event_onsets)))
        nl = null_same_year[key]
        nl = nl[np.isfinite(nl)]
        p_two = (float(min(1.0, 2 * min((nl >= actual).mean(), (nl <= actual).mean())))
                 if len(nl) >= 10 else None)
        # midrank percentile version (only for real features)
        if key in pF:
            pct_actual = float(np.nanmean(window_stat(pF[key], event_onsets)))
            pct_null = (float(np.nanmean(window_stat(pF[key], idx_draws)))
                        if (idx_draws >= 0).all() else None)
        else:
            pct_actual, pct_null = None, None
        tie_zero = (float((F[key][rep_idx] == 0).mean())
                    if key in F else None)
        path_summary.append({
            "feature": key,
            "zero_tie_fraction_in_report_period": finite_or_none(tie_zero),
            "midrank_percentile_reliable": (
                None if tie_zero is None else bool(tie_zero < 0.5)),
            "actual_mean_z_or_fraction_in_window": actual,
            "same_year_null_mean": finite_or_none(float(nl.mean())) if len(nl) else None,
            "same_year_null_sd": finite_or_none(float(nl.std(ddof=1))) if len(nl) else None,
            "same_year_p_two_sided": p_two,
            "actual_mean_midrank_percentile": finite_or_none(pct_actual),
            "same_year_null_midrank_percentile": finite_or_none(pct_null),
            "significant_after_bonferroni_12": (
                None if p_two is None else bool(p_two < 0.05 / 12)),
        })

    # ---------------- pre-crisis vs post-crisis onset contrast ------------
    # If a feature is a genuine EARLY warning it must be elevated BEFORE the
    # onset.  If it only rises AFTER, it is a coincident/lagging state variable.
    pre_post = []
    for key, arr in arrays_for_path.items():
        def pp(starts):
            pre = window_stat(arr, starts, [-20, -10])
            post = window_stat(arr, starts, [10, 20])
            return post - pre
        actual_pp = float(np.nanmean(pp(event_onsets)))
        # each permutation draw already averages its m matched pseudo-events
        # inside window_stat, so pp(idx_draws) is already (N_PERM,)
        null_pp = pp(idx_draws)
        null_pp = null_pp[np.isfinite(null_pp)]
        p_pp = (float(min(1.0, 2 * min((null_pp >= actual_pp).mean(),
                                        (null_pp <= actual_pp).mean())))
                if len(null_pp) >= 10 else None)
        pre_post.append({
            "feature": key,
            "mean_z_at_j_minus20_minus10": finite_or_none(
                float(np.nanmean(window_stat(arr, event_onsets, [-20, -10])))),
            "mean_z_at_j_plus10_plus20": finite_or_none(
                float(np.nanmean(window_stat(arr, event_onsets, [10, 20])))),
            "post_minus_pre": finite_or_none(actual_pp),
            "same_year_null_post_minus_pre": finite_or_none(
                float(np.nanmean(null_pp))) if len(null_pp) else None,
            "same_year_p_two_sided": p_pp,
        })

    # ---------------- drift confounding: year-level audit -----------------
    by_year = []
    for yy in uniq_years:
        m = rep & (years == yy) & (y >= 0)
        if not m.any():
            continue
        by_year.append({
            "year": yy, "n_days": int(m.sum()),
            "crisis_label_share": float(y[m].mean()),
            "mean_N": float(N[m].mean()),
            "median_N": float(np.median(N[m])),
            "mean_roll_rho_N_W120": finite_or_none(float(np.nanmean(rho120[m]))),
            "mean_avg_corr": float(F["industry_average_correlation"][m].mean()),
            "corr_N_vs_crisis_label": finite_or_none(pearson(N[m].astype(float), y[m].astype(float))),
        })

    # ---------------- hand-worked examples --------------------------------
    ex = []
    for target in ["2015-08-18", "2018-05-21", "2020-03-02", "2022-02-14", "2024-01-25"]:
        if target not in dates:
            continue
        i = dates.index(target)
        fut = close[i + 1:i + H + 1] / close[i] - 1
        j = int(np.argmin(fut))
        ex.append({
            "date": target, "close_t": float(close[i]), "N_t": int(N[i]),
            "worst_date": dates[i + j + 1],
            "worst_close": float(close[i + j + 1]),
            "worst_cumulative_return": float(fut[j]),
            "Y_t": int(y[i]),
            "avg_corr": float(F["industry_average_correlation"][i]),
            "open_t_plus_1": float(op[i + 1]),
            "forward20_open_to_open": finite_or_none(float(forward_returns(op, 20)[i])),
        })
    i = dates.index("2021-06-29")
    W = 120
    win = N[i - W + 1:i + 1]
    ex_rho = {
        "date": "2021-06-29", "N": int(N[i]), "W": W,
        "window_min": int(win.min()), "window_max": int(win.max()),
        "window_median": float(np.median(win)),
        "less": int((win < N[i]).sum()), "equal": int((win == N[i]).sum()),
        "rho": float((int((win < N[i]).sum()) + 0.5 * int((win == N[i]).sum())) / W),
        "triggers_p90": bool((int((win < N[i]).sum()) + 0.5 * int((win == N[i]).sum())) / W >= 0.90),
    }

    # ---------------- payload ---------------------------------------------
    payload = {
        "generated_on": datetime.now().isoformat(timespec="seconds"),
        "status": "exploratory in-sample descriptive diagnostic; NOT a strategy, "
                  "NOT a replication, NOT out-of-sample, NOT a Gate 1 result",
        "question": "Q0 correction of 'low N is effective'; Q1 does high N warn of "
                    "crises; Q2 what do persistence summaries look like before crises",
        "correction_of_prior_reading": {
            "user_reading": "N very low -> effective",
            "verdict": "NOT SUPPORTED",
            "evidence": [
                "Daily low-N point-biserial IC 0.0913 falls to 0.0131 after collapsing "
                "389 signal days to 40 independent event starts; its 95% CI crosses zero.",
                "Event-start forward-20 mean +0.9198% has CI [-1.49%, +3.23%] and "
                "permutation p=0.524 (simple) / 0.1096 (gap-matched).",
                "Cluster-last-day IC is -0.0058 with mean -0.0275%; the only "
                "executable confirmation-day IC is -0.0004, i.e. indistinguishable "
                "from unconditional.",
                "The apparently strong daily IC is carried by 319 cluster MIDDLE days "
                "(IC 0.0981), i.e. repeated counting of one event, not timing skill.",
            ],
            "accurate_statement": "The low-hole STATE has a weak positive association "
                                  "with subsequent returns, but the tradeable first "
                                  "trigger is not distinguishable from random days.",
        },
        "crisis_definition": {
            "main": "Y_t = 1 iff min_{j=1..20}(P_{t+j}/P_t - 1) <= -10%, P = "
                    "Wind All-A 881001.WI CLOSE, t is a feature-calendar trading day",
            "benchmark_main": "881001.WI daily close (3012 rows, 2012-12-31..2025-05-30)",
            "benchmark_sensitivity": "frozen Gate 0 composite I_t = I_{t-1}*(1+0.5*"
                                     "(r_000001+r_399001)), common dates only, "
                                     "truncated 2024-12-31, label_end(t) < 2025-01-01",
            "why_not_gate1": "This is the Xingye replication line's exploratory "
                             "label. It is NOT the sealed Gate 1 2025 test label; "
                             "no Gate 1 OOF/test row is read or scored here.",
            "look_ahead_warning": "Y_t is defined with FUTURE 20-day prices. It is a "
                                  "retrospective annotation for description, never a "
                                  "tradable signal. Signals at t are evaluated only "
                                  "against the lead window [e-L, e-1].",
            "thresholds_borrowed_from": "config/study.toml Gate 0 frozen protocol",
            "sensitivity_prevalence": {"-5%": prev05, "-10%": prevalence, "-15%": prev15},
            "frozen_composite_prevalence": float(y_comp[valid_comp].mean()),
            "frozen_composite_n_valid": int(valid_comp.sum()),
        },
        "data": {
            "feature_file": str(FEATURE_CSV.relative_to(WORKSPACE)),
            "feature_rows_total": 3339,
            "feature_rows_used": n,
            "first_date": dates[0], "last_date": dates[-1],
            "report_days": int(rep.sum()),
            "valid_labeled_days": int(valid.sum()),
            "undecided_tail_days": int((rep & (y < 0)).sum()),
            "wind_calendar_days": D["wind_days"],
            "wind_only_calendar_days": D["wind_days"] - n,
            "calendar_note": "18 Wind trading days are absent from the feature "
                             "calendar; using the feature calendar keeps this "
                             "comparable with all previous IC diagnostics. The "
                             "earlier audit showed the 20-day IC moves 0.06629 -> "
                             "0.06678 under the full Wind calendar.",
            "prevalence": prevalence,
        },
        "event_definition": {
            "rule": "consecutive Y=1 days merged; a gap > 20 CALENDAR days starts "
                    "a new crisis event",
            "n_raw_events": len(events),
            "n_usable_events": len(usable_events),
            "left_censored_events": [r["onset"] for r in events if r["left_censored_label"]],
            "left_censor_note": "2015-07-01 is the first report day and already Y=1, "
                                "so its pre-crisis window is outside the labeled "
                                "report period; excluded from event-level statistics.",
            "report_period_years": report_years,
        },
        "crisis_events": events,
        "preregistration": {
            "grid_fixed_before_viewing_results": True,
            "families": ["fixed_N_ge_{15,20,25,30}",
                         "roll_N_W{60,120,250}_p{80,90,95}",
                         "low_N_le_1_control", "avg_corr_ge_p90", "leading_eig_ge_p90"],
            "n_binary_signals": len(signals),
            "n_crisis_events_used_in_statistics": len(usable_events),
            "n_continuous_scores": len(continuous_scores),
            "all_cells_disclosed_no_selection_by_result": True,
            "lead_windows_trading_days": list(LEADS),
            "headline_statistic": "event lead recall at L=20 and precision P(Y=1|s=1)",
            "permutations": N_PERM,
            "nulls": ["global circular shift", "same-year circular shift (controls drift)"],
            "bootstrap": {"block_days": BLOCK, "repetitions": N_BOOT, "seed": SEED},
            "multiple_testing": f"{len(signals)} binary signals x several statistics; "
                                "no selection. Path summary uses Bonferroni "
                                "alpha=0.05/12.",
        },
        "signal_grid": grid_rows,
        "joint_max_t_correction": joint,
        "incremental_value_of_N_beyond_correlation": incremental,
        "pre_vs_post_onset_contrast": pre_post,
        "continuous_scores": score_rows,
        "segment_average_precision": segment_ap,
        "N_vs_forward_return_ic": horizon_ic,
        "bootstrap_degenerate_draws": boot_degenerate,
        "persistence_path": path,
        "persistence_path_summary": path_summary,
        "path_window_offsets": list(window_j),
        "by_year_audit": by_year,
        "hand_worked_examples": ex,
        "rolling_midrank_example": ex_rho,
        "interpretation": {},
        "gate_status": "Gate 1 paused; 2025 final test not read; Gate 2 not started.",
    }

    # interpretation computed AFTER all cells exist, without selecting any cell
    best_same_year = sorted(
        [r for r in grid_rows if r["perm_same_year_p_recall_greater"] is not None],
        key=lambda r: r["perm_same_year_p_recall_greater"])[:3]
    sig_cells = [r for r in grid_rows
                 if r["perm_same_year_p_recall_greater"] is not None
                 and r["perm_same_year_p_recall_greater"] < 0.05]
    path_sig = [r["feature"] for r in path_summary
                if r["significant_after_bonferroni_12"]]
    payload["interpretation"] = {
        "high_N_precision_lift_range": [
            finite_or_none(min(r["lift_vs_prevalence"] for r in grid_rows
                               if r["lift_vs_prevalence"] is not None
                               and r["family"] in ("fixed_high_N", "causal_rolling_high_quantile"))),
            finite_or_none(max(r["lift_vs_prevalence"] for r in grid_rows
                               if r["lift_vs_prevalence"] is not None
                               and r["family"] in ("fixed_high_N", "causal_rolling_high_quantile"))),
        ],
        "n_signals_same_year_p_below_005": len(sig_cells),
        "signals_same_year_p_below_005": [r["signal"] for r in sig_cells],
        "n_high_N_signals_with_precision_lift_above_1": sum(
            1 for r in grid_rows
            if r["family"] in ("fixed_high_N", "causal_rolling_high_quantile")
            and r["lift_vs_prevalence"] is not None
            and r["lift_vs_prevalence"] > 1),
        "joint_max_t_p": joint["p_value"],
        "bonferroni_alpha_per_cell": joint["bonferroni_alpha_per_cell"],
        "top_cell_recall_vs_iid_expectation": next(
            {"signal": r["signal"],
             "actual": r["event_lead_recall_L20"],
             "iid_expectation": r["expected_recall_if_iid_at_same_trigger_rate"]}
            for r in grid_rows if r["signal"] == "roll_N_W120_p80"),
        "three_smallest_same_year_p": [
            {"signal": r["signal"], "p": r["perm_same_year_p_recall_greater"],
             "recall": r["event_lead_recall_L20"],
             "false_alarms_per_year": r["false_alarm_clusters_per_year"]}
            for r in best_same_year],
        "path_features_significant_after_bonferroni": path_sig,
        "expected_false_positives_main_recall_test_at_5pct": 0.05 * len(grid_rows),
        "warning": "All results in-sample; crisis labels use future prices; "
                   "N drifts strongly (median 3 -> 14), so absolute high-N "
                   "thresholds confound regime drift with warning ability. "
                   "Same-year permutation is the stricter null.",
    }

    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                                   allow_nan=False) + "\n", encoding="utf-8")

    with EVENT_CSV.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(events[0].keys()))
        w.writeheader()
        w.writerows(events)
    with GRID_CSV.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(grid_rows[0].keys()))
        w.writeheader()
        w.writerows(grid_rows)

    # ---------------- figure ---------------------------------------------
    red, blue, grey = "#B23A48", "#185FA5", "#7A8794"
    fig, axes = plt.subplots(2, 2, figsize=(15, 9))
    x = np.arange(n)

    ax = axes[0, 0]
    ax.plot(x[rep], N[rep], lw=0.8, color=blue, label="H2 count N")
    for ev in events:
        i0 = dates.index(ev["onset"])
        i1 = dates.index(ev["end"])
        ax.axvspan(i0, i1, color=grey, alpha=0.25)
    hi = (N >= 25) & rep
    ax.scatter(x[hi], N[hi], s=7, color=red, alpha=0.7, label="N >= 25")
    ax.set_title("(a) N, crisis-label runs (grey) and high-N days", fontsize=11)
    ax.set_ylabel("H2 finite intervals")
    ax.legend(fontsize=8, loc="upper left")

    ax = axes[0, 1]
    for r in grid_rows:
        fp = r["false_alarm_clusters_per_year"]
        rc = r["event_lead_recall_L20"]
        if fp is None:
            continue
        fam = r["family"]
        color = red if fam == "fixed_high_N" else blue if fam == "causal_rolling_high_quantile" else grey
        ax.scatter(fp, rc, s=45, color=color, alpha=0.8, edgecolor="none")
        ax.annotate(r["signal"].replace("fixed_N_ge_", "N>=").replace("roll_N_", "r"),
                    (fp, rc), fontsize=6, alpha=0.85)
    ax.set_xlabel("false-alarm signal clusters / year")
    ax.set_ylabel("event lead recall (L=20)")
    ax.set_title("(b) Warning ability vs false alarms (all cells)", fontsize=11)
    ax.set_ylim(-0.05, 1.05)

    ax = axes[1, 0]
    for key, color, lab in [("h2_count", red, "H2 count N"),
                            ("industry_average_correlation", blue, "avg industry corr"),
                            ("h2_landscape_l1", grey, "H2 landscape L1")]:
        ys = [path[key][str(j)]["mean"] for j in PATH_OFFSETS]
        ax.plot(PATH_OFFSETS, ys, marker="o", ms=3.5, color=color, label=lab)
    ax.axhline(0, color="black", lw=0.8, ls="--")
    ax.axvline(0, color=grey, lw=0.8, ls=":")
    ax.set_xlabel("trading days relative to crisis-label onset")
    ax.set_ylabel("mean z-score vs report period")
    ax.set_title("(c) Persistence summary before / after onset", fontsize=11)
    ax.legend(fontsize=8)

    ax = axes[1, 1]
    key = "h2_count"
    nl = null_same_year[key]
    nl = nl[np.isfinite(nl)]
    ax.hist(nl, bins=45, color="#b8c6d1", edgecolor="none",
            label="same-year matched null")
    actual = next(r["actual_mean_z_or_fraction_in_window"]
                  for r in path_summary if r["feature"] == key)
    ax.axvline(actual, color=red, lw=2, label=f"actual (z={actual:.3f})")
    ax.set_title("(d) N in [-20,0] window vs drift-matched null", fontsize=11)
    ax.set_xlabel("mean z-score")
    ax.legend(fontsize=8)

    fig.suptitle("High H2 count and crisis onset: read-only in-sample diagnostic",
                 fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(FIG_OUT, dpi=130)
    plt.close(fig)

    print(json.dumps({
        "prevalence": round(prevalence, 5),
        "n_events": len(events), "n_usable": len(usable_events),
        "n_signals": len(signals),
        "same_year_p_below_005": payload["interpretation"]["signals_same_year_p_below_005"],
        "three_smallest_p": payload["interpretation"]["three_smallest_same_year_p"],
        "path_significant": path_sig,
        "joint_max_t_p": joint["p_value"],
        "bonferroni_alpha": joint["bonferroni_alpha_per_cell"],
        "high_N_cells_with_lift_above_1": payload["interpretation"][
            "n_high_N_signals_with_precision_lift_above_1"],
        "incremental": {
            k: incremental[k] for k in
            ("AP_avg_corr_full", "AP_minus_N_full", "AP_avg_corr_plus_N_z",
             "AP_avg_corr_minus_N_z", "difference_highN_minus_lowN",
             "same_year_permutation_p_two_sided")
        },
        "pre_post_avg_corr": next(r for r in pre_post
                                  if r["feature"] == "industry_average_correlation"),
        "segment_AP_minus_N": {r["segment"]: r["AP_score_minus_N"]
                               for r in segment_ap},
        "h20_ic_N": next(r["ic_N_vs_forward_return"] for r in horizon_ic
                         if r["horizon_days"] == 20),
        "outputs": [JSON_OUT.name, EVENT_CSV.name, GRID_CSV.name, FIG_OUT.name],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
