"""Explicit subprocess test processor; never imported by the production worker CLI."""

import sys
import time

from sqlalchemy import create_engine

from app.worker import Worker, WorkerPolicy


def main():
    url, schema, mode = sys.argv[1:]
    engine = create_engine(url, connect_args={"options": f"-c search_path={schema}"})

    def processor(worker, claim, pdf):
        print("CLAIMED", flush=True)
        if mode == "hold":
            while True:
                time.sleep(0.1)
        time.sleep(2)

    print("READY", flush=True)
    sys.stdin.readline()
    result = Worker(engine, processor, WorkerPolicy(3, 1, 2, 0)).run_once()
    print("WORKED" if result else "IDLE", flush=True)
    engine.dispose()


if __name__ == "__main__":
    main()
