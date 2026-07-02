import pandas as pd
from typing import Iterator, Tuple

class WalkForwardValidator:
    """
    Coordinates the strict chronological walk-forward cross-validation pipeline 
    (Train -> Calibrate -> Test folds). Never randomly shuffles sequential data.
    """
    
    def __init__(self, 
                 train_months: int = 6, 
                 calibrate_months: int = 1, 
                 test_months: int = 1,
                 step_months: int = 1):
        self.train_months = train_months
        self.calibrate_months = calibrate_months
        self.test_months = test_months
        self.step_months = step_months
        
    def generate_folds(self, df: pd.DataFrame) -> Iterator[Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]]:
        """
        Yields (Train, Calibrate, Test) dataframes for each walk-forward fold.
        Expects df to be sorted chronologically and indexed by datetime.
        """
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("DataFrame must have a DatetimeIndex for chronological folding.")
            
        start_date = df.index.min()
        end_date = df.index.max()
        
        current_train_start = start_date
        
        while True:
            current_train_end = current_train_start + pd.DateOffset(months=self.train_months)
            current_calib_end = current_train_end + pd.DateOffset(months=self.calibrate_months)
            current_test_end = current_calib_end + pd.DateOffset(months=self.test_months)
            
            if current_test_end > end_date:
                break
                
            train_df = df[(df.index >= current_train_start) & (df.index < current_train_end)]
            calib_df = df[(df.index >= current_train_end) & (df.index < current_calib_end)]
            test_df = df[(df.index >= current_calib_end) & (df.index < current_test_end)]
            
            yield train_df, calib_df, test_df
            
            current_train_start += pd.DateOffset(months=self.step_months)
