import os
import argparse
import logging
from pathlib import Path

# Since this is a calibration set, we can just call the main build_perception_pilot logic
# with a different seed and smaller count to ensure independence.

def parse_args():
    parser = argparse.ArgumentParser(description="Build SMC Perception Calibration Set")
    parser.add_argument("--venue", type=str, default="binance")
    parser.add_argument("--symbol", type=str, default="BTCUSDT")
    parser.add_argument("--timeframe", type=str, default="15m")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--seed", type=int, default=111111) # Different from pilot seed 260624
    parser.add_argument("--release", type=str, default="calibration-rc1")
    parser.add_argument("--output", type=str, default="evaluation/calibration_set")
    return parser.parse_args()

def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)
    
    logger.info("Delegating to build_perception_pilot...")
    
    cmd = [
        "python", "tools/build_perception_pilot.py",
        "--venue", args.venue,
        "--symbol", args.symbol,
        "--timeframe", args.timeframe,
        "--count", str(args.count),
        "--seed", str(args.seed),
        "--release", args.release,
        "--output", args.output
    ]
    
    import subprocess
    result = subprocess.run(cmd)
    if result.returncode == 0:
        logger.info(f"Calibration set built successfully at {args.output}")
    else:
        logger.error("Failed to build calibration set")

if __name__ == "__main__":
    main()
