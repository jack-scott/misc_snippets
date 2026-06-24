#!/usr/bin/env python3
"""
Generate fake drone log files in /data/organised/YYYY-MM-DD/.
Creates a few past flight dates with existing files, then continuously
adds new files for today to simulate an active drone.
"""
import os
import random
import time
import datetime

DATA_DIR = "/data/organised"
DRONE_NAME = os.environ.get("DRONE_NAME", "drone")


def write_fake_file(path, size_bytes):
    """Write a file filled with a small random header + zeros."""
    with open(path, "wb") as f:
        header = os.urandom(min(size_bytes, 4096))
        f.write(header)
        remaining = size_bytes - len(header)
        if remaining > 0:
            f.write(b"\x00" * remaining)


def populate_past_dates():
    today = datetime.date.today()
    past_offsets = [2, 5, 9, 18, 35]
    for offset in past_offsets:
        date = today - datetime.timedelta(days=offset)
        date_dir = os.path.join(DATA_DIR, date.isoformat())
        os.makedirs(date_dir, exist_ok=True)

        n_files = random.randint(15, 80)
        for i in range(n_files):
            fname = f"flight_{i:04d}_{random.randint(10000, 99999)}.bin"
            fpath = os.path.join(date_dir, fname)
            if not os.path.exists(fpath):
                size = random.randint(100 * 1024, 8 * 1024 * 1024)
                write_fake_file(fpath, size)

        total = sum(
            os.path.getsize(os.path.join(date_dir, f))
            for f in os.listdir(date_dir)
        )
        print(f"[{DRONE_NAME}] {date}: {n_files} files, {total/1024/1024:.0f} MB")


def run_live():
    today = datetime.date.today()
    date_dir = os.path.join(DATA_DIR, today.isoformat())
    os.makedirs(date_dir, exist_ok=True)
    counter = 0

    while True:
        fname = f"flight_{int(time.time())}_{counter:04d}.bin"
        fpath = os.path.join(date_dir, fname)
        size = random.randint(50 * 1024, 2 * 1024 * 1024)
        write_fake_file(fpath, size)
        counter += 1
        print(f"[{DRONE_NAME}] wrote {fname} ({size/1024:.0f} KB)")
        time.sleep(random.uniform(10, 45))


if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    populate_past_dates()
    run_live()
