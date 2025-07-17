import os
import csv
import psycopg2
from psycopg2 import sql
import pandas as pd

# DB connection config (ensure these match your setup)
DB_NAME = 'homecredit'
DB_USER = 'quang_user'
DB_PASSWORD = 'quang2011'
DB_HOST = 'localhost'
DB_PORT = 5432
NEW_SCHEMA = 'data' # Schema name where your tables are located

# CSV folder (assuming this is where your data files are)
CSV_FOLDER = 'data/'

# Batch size for inserts (if you're also using this script for loading)
BATCH_SIZE = 10000

# Mapping from pandas dtypes to PostgreSQL types (from our previous discussion)
PANDAS_TO_POSTGRES_TYPE_MAP = {
    'int64': 'BIGINT',
    'int32': 'INTEGER',
    'int16': 'SMALLINT',
    'int8': 'SMALLINT',
    'float64': 'DOUBLE PRECISION',
    'float32': 'REAL',
    'bool': 'BOOLEAN',
    'datetime64[ns]': 'TIMESTAMP',
    'object': 'TEXT'
}

def get_postgres_type(pandas_dtype):
    """Maps a pandas dtype to a suitable PostgreSQL data type."""
    if str(pandas_dtype).startswith('Int'):
        return 'BIGINT'
    if str(pandas_dtype).startswith('Float'):
        return 'DOUBLE PRECISION'
    return PANDAS_TO_POSTGRES_TYPE_MAP.get(str(pandas_dtype), 'TEXT')

# --- (The create_table_from_csv and import_csv_to_postgres functions go here) ---
# I'm omitting them for brevity, but assume they are present and functional
# from our previous iterations of the script. If you need them, please let me know.

# --- The core function to set relationships based on your schema diagram ---
def set_relationships(connection, schema_name):
    """
    Sets up primary and foreign key relationships between tables in the specified schema.
    Assumes tables are already created and data loaded.
    """
    conn = connection
    print("\n--- Setting up Table Relationships (Primary and Foreign Keys) ---")

    # Define primary key statements
    # (table_name, pk_column_name)
    pks = [
        ("application_train", "sk_id_curr"),
        ("application_test", "sk_id_curr"),
        ("bureau", "sk_id_bureau"),
        ("previous_application", "sk_id_prev")
    ]

    # Define foreign key statements
    # (child_table, fk_column, parent_table, parent_pk_column, fk_constraint_name)
    # The names for foreign keys are descriptive for clarity.
    fks = [
        # bureau links to application_train/test on SK_ID_CURR
        ("bureau", "sk_id_curr", "application_train", "sk_id_curr", "fk_bureau_to_app_train"),
        ("bureau", "sk_id_curr", "application_test", "sk_id_curr", "fk_bureau_to_app_test"), # Link to test set too if relevant

        # bureau_balance links to bureau on SK_ID_BUREAU
        ("bureau_balance", "sk_id_bureau", "bureau", "sk_id_bureau", "fk_bureau_balance_to_bureau"),

        # previous_application links to application_train/test on SK_ID_CURR
        ("previous_application", "sk_id_curr", "application_train", "sk_id_curr", "fk_prev_app_to_app_train"),
        ("previous_application", "sk_id_curr", "application_test", "sk_id_curr", "fk_prev_app_to_app_test"), # Link to test set too

        # POS_CASH_balance links to previous_application on SK_ID_PREV
        ("pos_cash_balance", "sk_id_prev", "previous_application", "sk_id_prev", "fk_pos_cash_to_prev_app"),

        # installments_payments links to previous_application on SK_ID_PREV
        ("installments_payments", "sk_id_prev", "previous_application", "sk_id_prev", "fk_installments_to_prev_app"),

        # credit_card_balance links to previous_application on SK_ID_PREV
        ("credit_card_balance", "sk_id_prev", "previous_application", "sk_id_prev", "fk_credit_card_to_prev_app")
    ]

    # Helper function to check if a constraint already exists (for idempotency)
    def constraint_exists(cursor, schema, table, name):
        cursor.execute(sql.SQL("""
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.table_constraints
                WHERE constraint_schema = {schema_literal}
                  AND table_name = {table_literal}
                  AND constraint_name = {name_literal}
            );
        """).format(
            schema_literal=sql.Literal(schema),
            table_literal=sql.Literal(table),
            name_literal=sql.Literal(name)
        ))
        return cursor.fetchone()[0]

    with conn.cursor() as cursor:
        cursor.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema_name)))

        # 1. Add Primary Keys
        for table, pk_column in pks:
            pk_constraint_name = f"pk_{table}"
            try:
                if not constraint_exists(cursor, schema_name, table, pk_constraint_name):
                    print(f"Adding PRIMARY KEY '{pk_constraint_name}' to {schema_name}.{table} on ({pk_column})...")
                    alter_pk_query = sql.SQL("ALTER TABLE {}.{} ADD CONSTRAINT {} PRIMARY KEY ({})").format(
                        sql.Identifier(schema_name), sql.Identifier(table),
                        sql.Identifier(pk_constraint_name), sql.Identifier(pk_column)
                    )
                    cursor.execute(alter_pk_query)
                    conn.commit()
                    print(f"✅ PRIMARY KEY '{pk_constraint_name}' added to {table}.")
                else:
                    print(f"PRIMARY KEY '{pk_constraint_name}' already exists on {table}. Skipping.")
            except psycopg2.Error as e:
                conn.rollback() # Rollback on error for this specific PK
                print(f"❌ Error adding PRIMARY KEY to {table} on ({pk_column}): {e}")

        # 2. Add Foreign Keys
        for child_table, fk_column, parent_table, parent_pk_column, fk_constraint_name in fks:
            try:
                if not constraint_exists(cursor, schema_name, child_table, fk_constraint_name):
                    print(f"Adding FOREIGN KEY '{fk_constraint_name}' to {schema_name}.{child_table} ({fk_column}) REFERENCES {schema_name}.{parent_table} ({parent_pk_column})...")
                    alter_fk_query = sql.SQL(
                        "ALTER TABLE {}.{} ADD CONSTRAINT {} FOREIGN KEY ({}) REFERENCES {}.{} ({})"
                    ).format(
                        sql.Identifier(schema_name), sql.Identifier(child_table),
                        sql.Identifier(fk_constraint_name), sql.Identifier(fk_column),
                        sql.Identifier(schema_name), sql.Identifier(parent_table), sql.Identifier(parent_pk_column)
                    )
                    cursor.execute(alter_fk_query)
                    conn.commit() # Commit each FK separately for better error isolation
                    print(f"✅ FOREIGN KEY '{fk_constraint_name}' added to {child_table}.")
                else:
                    print(f"FOREIGN KEY '{fk_constraint_name}' already exists on {child_table}. Skipping.")
            except psycopg2.errors.UndefinedTable:
                conn.rollback()
                print(f"⚠️ Skipping FK '{fk_constraint_name}': Table {schema_name}.{child_table} or {schema_name}.{parent_table} does not exist. (Make sure all CSVs are imported).")
            except psycopg2.errors.InvalidForeignKey:
                conn.rollback()
                print(f"❌ Error adding FOREIGN KEY '{fk_constraint_name}': Data integrity violation. Some values in {child_table}.{fk_column} do not exist in {parent_table}.{parent_pk_column}. You might need to clean your data.")
            except psycopg2.Error as e:
                conn.rollback()
                print(f"❌ Generic error adding FOREIGN KEY '{fk_constraint_name}' to {child_table}: {e}")

    print("--- Finished setting up relationships. ---")

# --- Your main execution block (simplified for demonstration) ---
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
        conn.autocommit = False # Manual transaction control

        with conn.cursor() as cursor_init:
            cursor_init.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(NEW_SCHEMA)))
            conn.commit()
        print(f"Global search path set to '{NEW_SCHEMA}, public'.")

        # Assume your CSV import loop (from previous versions of the script)
        # goes here and has successfully loaded all data.
        # Example of how you might call the import function for one file:
        # csv_files = [f for f in os.listdir(CSV_FOLDER) if f.endswith('.csv')]
        # for csv_file in csv_files:
        #     table_name = os.path.splitext(csv_file)[0].lower()
        #     file_path = os.path.join(CSV_FOLDER, csv_file)
        #     print(f"📦 Importing: {file_path} → {NEW_SCHEMA}.{table_name}")
        #     import_csv_to_postgres(file_path, NEW_SCHEMA, table_name, conn) # Assuming this function is defined
        # print("🎉 All CSVs loaded into PostgreSQL (assuming previous steps were successful).")

        # --- CALL THE RELATIONSHIP FUNCTION HERE ---
        set_relationships(conn, NEW_SCHEMA)
        # ------------------------------------------

    except psycopg2.Error as e:
        print(f"Database connection error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")