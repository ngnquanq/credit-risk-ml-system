import pandas as pd
import pyarrow.parquet as pq
import polars as pl
import os
from typing import Union
def get_feature_definitions(data_file_path: str, feature_definitions_csv: str) -> pd.DataFrame:
    """
    Given a data file (parquet or csv) and a feature definitions CSV file,
    return a filtered DataFrame that only includes definitions relevant to the columns
    in the data file, along with their inferred data types.

    Parameters:
    -----------
    data_file_path : str
        Path to the data file (.parquet or .csv) to inspect for columns.
    feature_definitions_csv : str
        Path to the CSV file containing feature definitions.
        Assumes at least a 'Variable' column (or 'feature_name', adjust as needed).

    Returns:
    --------
    pd.DataFrame
        Filtered DataFrame containing only the feature definitions relevant to the data file's columns,
        including a 'Data Type' column.

    Raises:
    -------
    ValueError
        If the feature definitions CSV does not contain a 'Variable' column,
        or if the data_file_path is neither a .parquet nor a .csv file.
    """
    # 1. Load the feature definitions from the CSV
    feature_defs = pd.read_csv(feature_definitions_csv)
    if 'Variable' not in feature_defs.columns:
        raise ValueError("The feature definitions CSV must contain a 'Variable' column.")

    # 2. Determine columns and their data types from the data file based on its type
    file_extension = os.path.splitext(data_file_path)[1].lower()
    data_column_types = {} # Dictionary to store column_name: data_type

    if file_extension == '.parquet':
        parquet_schema = pq.read_schema(data_file_path)
        for field in parquet_schema:
            data_column_types[field.name] = str(field.type) # Convert PyArrow type to string
    elif file_extension == '.csv':
        try:
            # Read a small chunk to infer dtypes.
            # Using dtype=False to let pandas infer, then map.
            # Reading 1000 rows should be sufficient for type inference in most cases.
            temp_df = pd.read_csv(data_file_path, nrows=1000)
            for col in temp_df.columns:
                data_column_types[col] = str(temp_df[col].dtype)
        except Exception as e:
            raise IOError(f"Could not read CSV header or infer types from {data_file_path}: {e}")
    else:
        raise ValueError(f"Unsupported data file type: {file_extension}. Please provide a .parquet or .csv file.")

    # 3. Filter the feature definitions to only those used in the data file
    # Ensure that data_column_types keys are used for filtering to match existing columns
    relevant_columns = set(data_column_types.keys())
    relevant_defs = feature_defs[feature_defs['Variable'].isin(relevant_columns)].copy()

    # 4. Add the 'Data Type' column
    # Create a mapping from Variable name to its data type
    dtype_map = {col: dtype for col, dtype in data_column_types.items()}
    relevant_defs['Data Type'] = relevant_defs['Variable'].map(dtype_map)

    # Reorder columns to have 'Variable', 'Description', 'Data Type'
    # Assuming 'Description' is another column in your feature_definitions_csv
    if 'Description' in relevant_defs.columns:
        relevant_defs = relevant_defs[['Variable', 'Description', 'Data Type']]
    else:
        # If 'Description' isn't present, just include Variable and Data Type
        relevant_defs = relevant_defs[['Variable', 'Data Type']]
        print("Warning: 'Description' column not found in feature definitions CSV.")


    return relevant_defs


def count_missing_data(df: Union[pd.DataFrame, pl.DataFrame]) -> pd.DataFrame:
    """
    Counts missing values (NaN, None, or null) in a DataFrame and returns
    a new DataFrame with the column names, missing counts, and percentages.

    Parameters:
    -----------
    df : Union[pd.DataFrame, pl.DataFrame]
        The input DataFrame, either a Pandas DataFrame or a Polars DataFrame.

    Returns:
    --------
    pd.DataFrame
        A DataFrame with 'Column Name', 'Missing Count', and 'Missing Percentage'
        for columns containing missing values, sorted by 'Missing Percentage' descending.
    """
    missing_data = []

    if isinstance(df, pd.DataFrame):
        for col in df.columns:
            missing_count = df[col].isnull().sum()
            if missing_count > 0:
                total_rows = len(df)
                missing_percentage = (missing_count / total_rows) * 100
                missing_data.append({
                    'Column Name': col,
                    'Missing Count': missing_count,
                    'Missing Percentage': missing_percentage
                })
    elif isinstance(df, pl.DataFrame):
        # Polars handles missing values (nulls) efficiently
        # We can use .null_count() for each column
        for col in df.columns:
            missing_count = df[col].null_count()
            if missing_count > 0:
                total_rows = df.height # .height for number of rows in Polars
                missing_percentage = (missing_count / total_rows) * 100
                missing_data.append({
                    'Column Name': col,
                    'Missing Count': missing_count,
                    'Missing Percentage': missing_percentage
                })
    else:
        raise TypeError("Input must be either a pandas.DataFrame or a polars.DataFrame.")

    # Convert the list of dictionaries to a Pandas DataFrame
    missing_df = pd.DataFrame(missing_data)

    if not missing_df.empty:
        # Sort by missing percentage in descending order
        missing_df = missing_df.sort_values(by='Missing Percentage', ascending=False).reset_index(drop=True)

    return missing_df

def missing_data_cutoff_with_threshold(df: Union[pd.DataFrame, pl.DataFrame], threshold: float) -> Union[pd.DataFrame, pl.DataFrame]:
    """
    Eliminates columns from a DataFrame (Pandas or Polars) that have a missingness
    percentage exceeding a specified threshold.

    Parameters:
    -----------
    df : Union[pd.DataFrame, pl.DataFrame]
        The input DataFrame, either a Pandas DataFrame or a Polars DataFrame.
    threshold : float
        The percentage threshold (e.g., 90.0 for 90%) above which columns
        will be dropped.

    Returns:
    --------
    Union[pd.DataFrame, pl.DataFrame]
        A new DataFrame with columns exceeding the threshold removed.
        The returned DataFrame will be of the same type as the input.
    """
    if not (0 <= threshold <= 100):
        raise ValueError("Threshold must be a percentage between 0 and 100.")

    # Get the missing data summary using our previous function
    missing_summary_df = count_missing_data(df)

    # Identify columns to drop based on the threshold
    columns_to_drop = missing_summary_df[
        missing_summary_df['Missing Percentage'] > threshold
    ]['Column Name'].tolist()

    if not columns_to_drop:
        print(f"No columns found with missing percentage above {threshold}%.")
        return df.copy() # Return a copy to avoid modifying the original DataFrame in place

    print(f"Dropping {len(columns_to_drop)} columns with missing percentage above {threshold}%:")
    for col in columns_to_drop:
        print(f"- {col}")

    # Perform the drop operation based on DataFrame type
    if isinstance(df, pd.DataFrame):
        new_df = df.drop(columns=columns_to_drop)
    elif isinstance(df, pl.DataFrame):
        # Polars has a direct .drop() method
        new_df = df.drop(columns_to_drop)
    else:
        # This case should ideally not be reached if count_missing_data also validated input
        raise TypeError("Input must be either a pandas.DataFrame or a polars.DataFrame.")

    return new_df

def get_transformation_type(column_name: str) -> str:
    """
    Infers the transformation type (P, M, A, D, T, L) based on the last character
    of the column name, according to the provided notation.

    Parameters:
    -----------
    column_name : str
        The name of the column (e.g., 'annuity_780A').

    Returns:
    --------
    str
        The inferred transformation type (P, M, A, D, T, L) or 'Unknown' if the
        last character doesn't match a known type.
    """
    if not isinstance(column_name, str) or len(column_name) == 0:
        return 'Unknown'

    last_char = column_name[-1].upper()

    transformation_map = {
        'P': 'DPD (Days past due) Transform',
        'M': 'Masking Categories Transform',
        'A': 'Amount Transform',
        'D': 'Date Transform',
        'T': 'Unspecified Transform',
        'L': 'Unspecified Transform (often Categorical/Count)'
    }

    # Return the key itself if you want the single letter, otherwise the full description
    return last_char if last_char in transformation_map else 'Unknown'


# --- New Function: get_columns_by_transformation_type ---

def get_columns_by_transformation_type(
    df: Union[pd.DataFrame, pl.DataFrame],
    mapping_type: str
) -> Union[pd.DataFrame, pl.DataFrame]:
    """
    Filters a DataFrame to include only columns whose names end with the
    specified transformation type (P, M, A, D, T, L).

    Parameters:
    -----------
    df : Union[pd.DataFrame, pl.DataFrame]
        The input DataFrame (Pandas or Polars).
    mapping_type : str
        The single-letter transformation type to filter by (e.g., 'A', 'P', 'D', 'M', 'L', 'T').
        Case-insensitive.

    Returns:
    --------
    Union[pd.DataFrame, pl.DataFrame]
        A new DataFrame containing only the columns matching the specified
        transformation type. The returned DataFrame will be of the same type as the input.

    Raises:
    -------
    ValueError
        If the mapping_type is not a single character or not a recognized type.
    """
    if not isinstance(mapping_type, str) or len(mapping_type) != 1:
        raise ValueError("mapping_type must be a single character (e.g., 'A', 'P', 'D').")

    target_char = mapping_type.upper() # Ensure it's uppercase for comparison

    # Define the valid transformation types (keys from the get_transformation_type's map)
    valid_types = {'P', 'M', 'A', 'D', 'T', 'L'}
    if target_char not in valid_types:
        print(f"Warning: '{mapping_type}' is not a recognized transformation type. Valid types are {', '.join(sorted(list(valid_types)))}.")
        # We can still proceed, but it's good to warn the user.
        # Alternatively, you could raise ValueError here if strictness is required.


    matching_columns = []
    for col in df.columns:
        if len(col) > 0 and col[-1].upper() == target_char:
            matching_columns.append(col)

    if not matching_columns:
        print(f"No columns found ending with transformation type '{mapping_type}' in the DataFrame.")
        # Return an empty DataFrame of the correct type if no columns match
        if isinstance(df, pd.DataFrame):
            return pd.DataFrame()
        elif isinstance(df, pl.DataFrame):
            return pl.DataFrame()

    if isinstance(df, pd.DataFrame):
        return df[matching_columns]
    elif isinstance(df, pl.DataFrame):
        return df.select(matching_columns)
    else:
        # This case should ideally not be reached given type hints
        raise TypeError("Input DataFrame must be either a pandas.DataFrame or a polars.DataFrame.")

