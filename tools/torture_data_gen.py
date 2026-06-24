import pandas as pd
import numpy as np
import random
from pathlib import Path

def generate_torture_data(input_csv, output_dir):
    df = pd.read_csv(input_csv)
    # Assume 'timestamp', 'open', 'high', 'low', 'close', 'volume'
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    
    # 1. Missing Event Attack
    missing_df = df.copy()
    if len(missing_df) > 50:
        missing_df = missing_df.drop(index=50).reset_index(drop=True)
    missing_df.to_csv(out_path / "torture_missing_event.csv", index=False)
    
    # 2. Duplicate Event Attack
    dup_df = df.copy()
    if len(dup_df) > 60:
        row_60 = dup_df.iloc[[60]]
        dup_df = pd.concat([dup_df.iloc[:61], row_60, dup_df.iloc[61:]]).reset_index(drop=True)
    dup_df.to_csv(out_path / "torture_duplicate_event.csv", index=False)
    
    # 3. Out-of-order Attack
    ooo_df = df.copy()
    if len(ooo_df) > 71:
        row_70 = ooo_df.iloc[70].copy()
        row_71 = ooo_df.iloc[71].copy()
        ooo_df.iloc[70] = row_71
        ooo_df.iloc[71] = row_70
    ooo_df.to_csv(out_path / "torture_out_of_order.csv", index=False)
    
    # 4. Precision Attack
    prec_df = df.copy()
    if len(prec_df) > 81:
        prec_df.loc[80, 'close'] = prec_df.loc[80, 'close'] + 0.0000000000001
        prec_df.loc[81, 'high'] = 1e-10
        prec_df.loc[82, 'low'] = 1e10
    prec_df.to_csv(out_path / "torture_precision.csv", index=False)
    
    # 5. Timestamp Attack
    ts_df = df.copy()
    if len(ts_df) > 91 and 'timestamp' in ts_df.columns:
        ts_df.loc[90, 'timestamp'] = pd.to_datetime('2100-01-01 00:00:00', utc=True)
        ts_df.loc[91, 'timestamp'] = pd.to_datetime('1970-01-01 00:00:00', utc=True)
    ts_df.to_csv(out_path / "torture_timestamp.csv", index=False)
    
    print(f"Generated Market Truth Torture cases in {output_dir}")

if __name__ == "__main__":
    generate_torture_data("sample_ohlcv.csv", "blackbox_gauntlet/cases/")
