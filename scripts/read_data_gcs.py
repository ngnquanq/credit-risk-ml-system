from pyspark.sql import SparkSession
import os

# --- Configurations ---
service_account_key = os.path.abspath("secrets/global-phalanx-449403-d2-aae80316b9df.json")
gcs_connector_path = os.path.abspath("data-platform/jars/gcs-connector-hadoop3-2.2.9-shaded.jar")

# Set environment variable (if not already set)
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = service_account_key

# Create Spark session with GCS configs
spark = SparkSession.builder \
    .appName("ReadGCSCSV") \
    .master("local[*]") \
    .config("spark.jars", gcs_connector_path) \
    .config("spark.hadoop.fs.gs.impl", "com.google.cloud.hadoop.fs.gcs.GoogleHadoopFileSystem") \
    .config("spark.hadoop.fs.AbstractFileSystem.gs.impl", "com.google.cloud.hadoop.fs.gcs.GoogleHadoopFS") \
    .config("spark.hadoop.google.cloud.auth.service.account.enable", "true") \
    .config("spark.hadoop.google.cloud.auth.service.account.json.keyfile", service_account_key) \
    .getOrCreate()

# GCS path
gcs_path = "gs://credit-risk-modeling-bucket/raw_data/application_train.csv"

# Try reading
try:
    df = spark.read \
        .option("header", "true") \
        .option("inferSchema", "true") \
        .csv(gcs_path)

    print("✅ DataFrame loaded successfully!")
    df.show(5)

except Exception as e:
    print(f"❌ Error loading data: {e}")
