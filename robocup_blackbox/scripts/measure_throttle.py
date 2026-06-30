#!/usr/bin/env python3
"""Throttle accuracy measurement tool (robocup_blackbox validation #2)
"""

import argparse
import glob
import os
import statistics
import sys
from collections import defaultdict

from mcap.reader import make_reader


def resolve_mcap(path: str) -> str:
    # If a folder (.mcap directory) is given, locate the inner .mcap file
    if os.path.isdir(path):
        inner = sorted(glob.glob(os.path.join(path, "*.mcap")))
        if not inner:
            print(f"[ERROR] No .mcap file found in {path}", file=sys.stderr)
            sys.exit(1)
        return inner[0]
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mcap", help="Path to an mcap file or .mcap directory")
    ap.add_argument("--topic", default="", help="Partial-match filter for topic name")
    ap.add_argument("--expect", type=float, default=None, help="Expected target Hz (for pass/fail judgment)")
    args = ap.parse_args()

    path = resolve_mcap(args.mcap)
    times = defaultdict(list)  # topic -> [log_time_ns ...]

    with open(path, "rb") as f:
        reader = make_reader(f)
        for schema, channel, message in reader.iter_messages():
            if args.topic and args.topic not in channel.topic:
                continue
            times[channel.topic].append(message.log_time)

    if not times:
        print("No recorded messages (check filter).")
        return

    print(f"File: {path}\n")
    hdr = f"{'TOPIC':45} {'CNT':>6} {'dur_s':>7} {'Hz':>7} {'gap_ms(mean':>11} {'std':>6} {'min':>6} {'med':>6} {'max)':>6}"
    print(hdr)
    print("-" * len(hdr))

    for topic in sorted(times):
        ts = sorted(times[topic])
        cnt = len(ts)
        dur = (ts[-1] - ts[0]) / 1e9 if cnt > 1 else 0.0
        hz = (cnt - 1) / dur if dur > 0 else 0.0
        gaps = [(ts[i + 1] - ts[i]) / 1e6 for i in range(cnt - 1)]  # ms
        if gaps:
            g_mean = statistics.mean(gaps)
            g_std = statistics.pstdev(gaps) if len(gaps) > 1 else 0.0
            g_min, g_med, g_max = min(gaps), statistics.median(gaps), max(gaps)
        else:
            g_mean = g_std = g_min = g_med = g_max = 0.0
        print(f"{topic:45} {cnt:>6} {dur:>7.2f} {hz:>7.2f} "
              f"{g_mean:>11.2f} {g_std:>6.2f} {g_min:>6.1f} {g_med:>6.1f} {g_max:>6.1f}")

        if args.expect:
            ideal_gap = 1000.0 / args.expect
            err = (hz - args.expect) / args.expect * 100.0
            print(f"   └ Expected {args.expect:.0f}Hz (gap {ideal_gap:.1f}ms): measured {hz:.2f}Hz "
                  f"({err:+.1f}%), gap uniformity std={g_std:.2f}ms")


if __name__ == "__main__":
    main()
