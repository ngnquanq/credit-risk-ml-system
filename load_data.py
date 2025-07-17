import os
import csv
import psycopg2
from psycopg2 import sql
import pandas as pd # Import pandas

# DB connection config
DB_NAME = 'homecredit'
DB_USER = 'quang_user'
DB_PASSWORD = 'quang2011'
DB_HOST = 'localhost'
DB_PORT = 5432
NEW_SCHEMA = 'data' # Schema name

# CSV folder
CSV_FOLDER = 'data/'

# Batch size for inserts
BATCH_SIZE = 100000 # Adjust this based on your system's memory and performance

# Mapping from pandas dtypes to PostgreSQL types
PANDAS_TO_POSTGRES_TYPE_MAP = {
    'int66': 'BIGINT', # General integer
    'int32': 'INTEGER',
    'int16': 'SMALLINT',
    'int8': 'SMALLINT',
    'float64': 'DOUBLE PRECISION', # Use DOUBLE PRECISION for floating point numbers
    'float32': 'REAL',
    'bool': 'BOOLEAN',
    'datetime64[ns]': 'TIMESTAMP', # For datetime objects
    'object': 'TEXT' # Default for strings and mixed types
    # Add more mappings as needed, e.g., 'category': 'TEXT', 'timedelta': 'INTERVAL'
}

def get_postgres_type(pandas_dtype):
    """Maps a pandas dtype to a suitable PostgreSQL data type."""
    # Handle nullable integer types specifically
    if str(pandas_dtype).startswith('Int'): # For pandas nullable integer types like 'Int64'
        return 'BIGINT'
    if str(pandas_dtype).startswith('Float'): # For pandas nullable float types like 'Float64'
        return 'DOUBLE PRECISION'
    
    return PANDAS_TO_POSTGRES_TYPE_MAP.get(str(pandas_dtype), 'TEXT')


def create_table_from_csv(connection, cursor, schema_name, table_name, file_path, encoding='utf-8'):
    """
    Creates a PostgreSQL table based on the CSV header and pandas-inferred types.
    Ensures DROP and CREATE are committed separately.
    Returns the DataFrame headers and the DataFrame itself.
    """
    # 1. Read CSV into Pandas DataFrame for type inference
    try:
        df = pd.read_csv(file_path, encoding=encoding, low_memory=False) # low_memory=False to help with mixed types
    except pd.errors.EmptyDataError:
        raise ValueError(f"CSV file '{file_path}' is empty.")
    except Exception as e:
        raise ValueError(f"Error reading CSV '{file_path}' with pandas: {e}")

    # Clean up column names (as done previously)
    df.columns = [col.strip().lower().replace(' ', '_') for col in df.columns]

    # Handle potentially empty column names after cleaning
    cleaned_columns = []
    for i, col in enumerate(df.columns):
        if not col:
            new_col = f"column_{i}"
            print(f"Warning: Empty column header found in '{file_path}' at position {i}. Renamed to '{new_col}'.")
            cleaned_columns.append(new_col)
        else:
            cleaned_columns.append(col)
    df.columns = cleaned_columns # Update DataFrame columns

    # 2. Map pandas dtypes to PostgreSQL types
    columns_with_types = []
    for col_name, dtype in df.dtypes.items():
        pg_type = get_postgres_type(dtype)
        columns_with_types.append(sql.Identifier(col_name) + sql.SQL(f' {pg_type}'))

    if not columns_with_types:
        raise ValueError(f"No columns found for table '{table_name}' from '{file_path}'.")
    
    # 3. Construct CREATE TABLE query
    full_table_identifier = sql.Identifier(schema_name, table_name)
    create_table_query = sql.SQL("CREATE TABLE {} ({})").format(
        full_table_identifier,
        sql.SQL(', ').join(columns_with_types)
    )

    try:
        # Check if table exists
        cursor.execute(sql.SQL("""
            SELECT EXISTS (
                SELECT 1
                FROM pg_tables
                WHERE schemaname = {schema_literal} AND tablename = {table_literal}
            );
        """).format(
            schema_literal=sql.Literal(schema_name), 
            table_literal=sql.Literal(table_name)
        ))
        table_exists = cursor.fetchone()[0]

        if table_exists:
            print(f"Table '{schema_name}.{table_name}' already exists. Dropping...")
            cursor.execute(sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(full_table_identifier))
            connection.commit() # COMMIT AFTER DROP
            print(f"Committed DROP TABLE for '{schema_name}.{table_name}'.")
        
        # Now, create the table
        cursor.execute(create_table_query)
        print(f"🔄 Table '{schema_name}.{table_name}' created or recreated with inferred types.")

    except psycopg2.Error as e:
        print(f"Error creating table {schema_name}.{table_name}: {e}")
        raise # Re-raise to ensure transaction rollback

    return df # Return the DataFrame for data insertion

def import_csv_to_postgres(file_path, schema_name, table_name, connection):
    """
    Imports a CSV file into the specified PostgreSQL table using batch INSERTs.
    Leverages pandas for type inference and data loading.
    """
    conn = connection

    try:
        # Determine encoding for the specific file for both table creation and data reading
        encoding = 'utf-8'
        if 'HomeCredit_columns_description.csv' in file_path:
            encoding = 'latin-1' 

        # --- Part 1: Create/Recreate Table (with internal DROP and commit) ---
        df = None # Initialize df outside try block
        with conn.cursor() as cursor_ddl:
            cursor_ddl.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema_name)))
            df = create_table_from_csv(
                conn, cursor_ddl, schema_name, table_name, file_path, encoding
            )
        conn.commit() # Commit CREATE TABLE operation for this file
        print(f"Committed CREATE TABLE for '{schema_name}.{table_name}'.")

        if df.empty:
            print(f"Warning: DataFrame for '{file_path}' is empty after processing. Skipping data import.")
            return

        # --- Part 2: Batch Insert Data ---
        rows_inserted_count = 0
        
        # Convert DataFrame to list of lists (excluding header row)
        # Handle NaN values explicitly, as psycopg2 doesn't like numpy.nan
        # Convert pandas.NA (for nullable dtypes) to None as well
        data_to_insert = df.where(pd.notna(df), None).values.tolist()
        
        # Get column names (from DataFrame) for the INSERT statement
        headers = df.columns.tolist()

        # Construct the INSERT statement
        columns_sql = sql.SQL(', ').join(map(sql.Identifier, headers))
        placeholders = sql.SQL(', ').join(sql.Placeholder() * len(headers))
        insert_query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            sql.Identifier(schema_name, table_name), 
            columns_sql,
            placeholders
        )
        
        # If there are no rows to insert, just commit and return
        if not data_to_insert:
            print(f"No data rows to insert into '{schema_name}.{table_name}'.")
            conn.commit()
            return

        with conn.cursor() as cursor_dml: # Use a fresh cursor for DML
            cursor_dml.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema_name)))

            # Perform batch inserts
            for i in range(0, len(data_to_insert), BATCH_SIZE):
                batch = data_to_insert[i:i + BATCH_SIZE]
                cursor_dml.executemany(insert_query, batch)
                rows_inserted_count += len(batch)
                print(f"Inserted {rows_inserted_count} rows into '{schema_name}.{table_name}' so far...")

            conn.commit() # Commit all batch inserts for this file
            print(f"✅ {rows_inserted_count} rows successfully loaded into '{schema_name}.{table_name}'.")

    except ValueError as ve: 
        conn.rollback()
        print(f"Skipping import for {file_path}: {ve}")
    except Exception as e:
        conn.rollback()
        print(f"❌ Error importing {file_path} into {schema_name}.{table_name}: {e}")

# Main execution
if __name__ == "__main__":
    conn = None
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        conn.autocommit = False # Manage transactions manually

        # --- Explicitly set search_path for the current session (once for the whole script) ---
        with conn.cursor() as cursor_init:
            cursor_init.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(NEW_SCHEMA)))
            conn.commit() # Commit the SET command
        print(f"Global search path set to '{NEW_SCHEMA}, public'.")
        # -----------------------------------------------------------

        csv_files = [f for f in os.listdir(CSV_FOLDER) if f.endswith('.csv')]

        if not csv_files:
            print(f"No CSV files found in '{CSV_FOLDER}'. Exiting.")

        for csv_file in csv_files:
            table_name = os.path.splitext(csv_file)[0].lower()
            file_path = os.path.join(CSV_FOLDER, csv_file)

            print(f"📦 Importing: {file_path} → {NEW_SCHEMA}.{table_name}")
            import_csv_to_postgres(file_path, NEW_SCHEMA, table_name, conn)

        print("🎉 All CSVs loaded into PostgreSQL.")

    except psycopg2.Error as e:
        print(f"Database connection error: {e}")
    except FileNotFoundError:
        print(f"Error: CSV_FOLDER '{CSV_FOLDER}' not found. Please ensure the 'data' directory exists.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")