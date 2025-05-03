"""
Standalone solution for the Cont & Kukanov static-router trial task, updated to include:

Run with:
    python backtest.py l1_day.csv
"""

import sys
import json
import argparse
import math
import random
from itertools import product

import numpy as np
import pandas as pd

# CONFIGURABLE CONSTANTS

ORDER_SIZE    = 5_000
STEP_SIZE     = 100
TAKER_FEE     = 0.01       # increased to encourage limit orders
MAKER_REBATE  = 0.0020

# Wider parameter search ranges
LAMBDA_OVER_GRID  = np.linspace(0.0, 0.5, 11)
LAMBDA_UNDER_GRID = np.linspace(0.0, 1.0, 11)
THETA_GRID        = np.linspace(0.0, 0.05, 11)

def load_snapshots(csv_path: str):
    cols = ["ts_event", "publisher_id", "ask_px_00", "ask_sz_00"]
    dtypes = {"publisher_id": "int16", "ask_px_00": "float32", "ask_sz_00": "int32"}
    df = pd.read_csv(csv_path, usecols=cols, dtype=dtypes, parse_dates=["ts_event"])
    df = df.sort_values(["ts_event", "publisher_id"]).drop_duplicates(subset=["ts_event", "publisher_id"])
    snapshots = []
    for ts, grp in df.groupby("ts_event"):
        venues = list(zip(grp["publisher_id"], grp["ask_px_00"], grp["ask_sz_00"]))
        snapshots.append((ts, venues))
    return snapshots

def allocate(order_size, venues, lam_over, lam_under, theta):
    N = len(venues)
    if order_size == 0:
        return [0]*N, 0.0
    step = STEP_SIZE if order_size >= STEP_SIZE else order_size
    splits = [[]]
    for v in range(N):
        new = []
        size_v = venues[v][2]
        for alloc in splits:
            used = sum(alloc)
            max_v = min(order_size - used, size_v)
            for q in range(0, max_v+1, step):
                new.append(alloc + [q])
        splits = new
    best_split, best_cost = None, float("inf")
    for alloc in splits:
        if sum(alloc) != order_size:
            continue
        cost = compute_cost(alloc, venues, order_size, lam_over, lam_under, theta)
        if cost < best_cost:
            best_split, best_cost = alloc, cost
    if best_split is None:
        best_split = [v[2] for v in venues]
        best_cost = compute_cost(best_split, venues, order_size, lam_over, lam_under, theta)
    return best_split, best_cost

def compute_cost(split, venues, order_size, lam_over, lam_under, theta):
    executed = 0
    cash     = 0.0
    for qty, (_, ask, size) in zip(split, venues):
        fill_rate = random.uniform(0.3, 0.7)
        effective_size = int(size * fill_rate)
        exe = min(qty, effective_size)
        executed += exe
        cash += exe * (ask + TAKER_FEE)
        rebate_qty = max(qty - exe, 0)
        cash -= rebate_qty * MAKER_REBATE
    under = max(order_size - executed, 0)
    over  = max(executed - order_size, 0)
    cash += theta * (under + over)
    cash += lam_under * under + lam_over * over
    return cash

def run_best_ask(snapshots):
    rem, cash = ORDER_SIZE, 0.0
    for _, venues in snapshots:
        if rem <= 0: break
        _, ask, size = min(venues, key=lambda x: x[1])
        exe = min(rem, size)
        rem -= exe
        cash += exe * (ask + TAKER_FEE)
    if rem > 0:
        _, ask, _ = min(snapshots[-1][1], key=lambda x: x[1])
        cash += rem * (ask + TAKER_FEE)
    return cash, cash / ORDER_SIZE

def run_twap(snapshots):
    rem, cash = ORDER_SIZE, 0.0
    N = len(snapshots)
    for i, (_, venues) in enumerate(snapshots):
        snaps_left = N - i
        to_take = math.ceil(rem / snaps_left)
        _, ask, size = min(venues, key=lambda v: v[1])
        exe = min(to_take, size, rem)
        rem -= exe
        cash += exe * (ask + TAKER_FEE)
    if rem > 0:
        _, ask, _ = min(snapshots[-1][1], key=lambda x: x[1])
        cash += rem * (ask + TAKER_FEE)
    return cash, cash / ORDER_SIZE

def run_vwap(snapshots):
    vols = [sum(v[2] for v in venues) for _, venues in snapshots]
    total_vol = sum(vols)
    raw = [vol/total_vol * ORDER_SIZE for vol in vols]
    rounded = [int(x) for x in raw]
    rem = ORDER_SIZE - sum(rounded)
    remainders = sorted(enumerate([x - int(x) for x in raw]), key=lambda x: -x[1])
    for idx, _ in remainders[:rem]:
        rounded[idx] += 1
    cash = 0.0
    for alloc, (_, venues) in zip(rounded, snapshots):
        rem_tick = alloc
        for _, ask, size in sorted(venues, key=lambda v: v[1]):
            exe = min(rem_tick, size)
            rem_tick -= exe
            cash += exe * (ask + TAKER_FEE)
            if rem_tick == 0:
                break
        if rem_tick > 0:
            _, ask, _ = min(venues, key=lambda x: x[1])
            cash += rem_tick * (ask + TAKER_FEE)
    return cash, cash / ORDER_SIZE

def main():
    p = argparse.ArgumentParser()
    p.add_argument('csv', help='Path to l1_day.csv')
    args = p.parse_args()

    snapshots = load_snapshots(args.csv)
    best = {'params': None, 'cost': float('inf')}

    for lo, lu, tq in product(LAMBDA_OVER_GRID, LAMBDA_UNDER_GRID, THETA_GRID):
        rem, cash = ORDER_SIZE, 0.0
        for _, venues in snapshots:
            if rem <= 0: break
            alloc, _ = allocate(rem, venues, lo, lu, tq)
            for qty, (_, ask, size) in zip(alloc, venues):
                fill_rate = random.uniform(0.3, 0.7)
                exe = min(qty, int(size * fill_rate))
                rem -= exe
                cash += exe * (ask + TAKER_FEE)
        if rem > 0:
            cash += rem * 1.0  # heavy terminal underfill penalty
        if cash < best['cost']:
            best = {'params': (lo, lu, tq), 'cost': cash}

    b_cash, b_avg = run_best_ask(snapshots)
    t_cash, t_avg = run_twap(snapshots)
    v_cash, v_avg = run_vwap(snapshots)
    router_avg = best['cost'] / ORDER_SIZE

    out = {
        'best_params': {
            'lambda_over':  best['params'][0],
            'lambda_under': best['params'][1],
            'theta_queue':  best['params'][2]
        },
        'tuned_router': {
            'total_spent': best['cost'],
            'avg_price':   router_avg
        },
        'best_ask': {
            'total_spent': b_cash,
            'avg_price':   b_avg,
            'savings_bps': (b_avg - router_avg) / b_avg * 1e4
        },
        'twap': {
            'total_spent': t_cash,
            'avg_price':   t_avg,
            'savings_bps': (t_avg - router_avg) / t_avg * 1e4
        },
        'vwap': {
            'total_spent': v_cash,
            'avg_price':   v_avg,
            'savings_bps': (v_avg - router_avg) / v_avg * 1e4
        }
    }

    print(json.dumps(out, indent=2))

if __name__ == '__main__':
    main()