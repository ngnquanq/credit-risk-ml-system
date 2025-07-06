import pandas as pd
import pyarrow.parquet as pq
from pathlib import Path

def get_feature_definitions(parquet_file: str, feature_definitions_csv: str) -> pd.DataFrame:
    """
    Given a parquet file and a feature definitions CSV file, return a filtered DataFrame
    that only includes definitions relevant to the columns in the parquet file.

    Parameters:
    -----------
    parquet_file : str
        Path to the .parquet file to inspect.
    feature_definitions_csv : str
        Path to the CSV file containing feature definitions. Assumes at least a 'feature_name' column.

    Returns:
    --------
    pd.DataFrame
        Filtered DataFrame containing only the feature definitions relevant to the parquet file.
    """
    # Load the feature definitions
    feature_defs = pd.read_csv(feature_definitions_csv)
    if 'Variable' not in feature_defs.columns:
        raise ValueError("The feature definitions CSV must contain a 'Variable' column.")

    # Load the parquet file schema (to avoid loading full data into memory)
    parquet_schema = pq.read_schema(parquet_file)
    parquet_columns = set(parquet_schema.names)

    # Filter the feature definitions to only those used in the parquet file
    relevant_defs = feature_defs[feature_defs['Variable'].isin(parquet_columns)].copy()

    return relevant_defs
