#!/usr/bin/env python3
"""
Spark ML Training Pipeline with ClickHouse Integration

Reads training data directly from ClickHouse application_mart database and
trains distributed ML models using Spark MLlib.

Usage (from Spark cluster):
  spark-submit --master spark://spark-master:7077 \
    --executor-memory 2g --driver-memory 2g \
    --jars /opt/spark/jars/clickhouse-jdbc-0.4.6-all.jar \
    application/training/spark_clickhouse_training.py \
    --experiment credit-risk-clickhouse \
    --register-name credit_risk_model_spark \
    --stage Production

Prerequisites:
  - ClickHouse running with application_mart database
  - Spark cluster with ClickHouse JDBC driver
  - MLflow tracking server
"""

import argparse
from typing import List, Dict, Any
import os

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import col, when, isnan, isnull, lit, coalesce
from pyspark.sql.types import DoubleType, IntegerType
from pyspark.ml.feature import (
    VectorAssembler, StandardScaler, StringIndexer, OneHotEncoder, 
    Imputer, Pipeline, Bucketizer
)
from pyspark.ml.classification import GBTClassifier
from pyspark.ml.evaluation import BinaryClassificationEvaluator, MulticlassClassificationEvaluator
from pyspark.ml.tuning import CrossValidator, ParamGridBuilder
from pyspark.ml import Pipeline as MLPipeline
import mlflow
import mlflow.spark
from loguru import logger


def create_spark_session(app_name: str = "CreditRisk-ClickHouse-Training") -> SparkSession:
    """Create Spark session optimized for ClickHouse connectivity."""
    
    builder = SparkSession.builder \
        .appName(app_name) \
        .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer") \
        .config("spark.sql.adaptive.enabled", "true") \
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true") \
        .config("spark.sql.execution.arrow.pyspark.enabled", "true") \
        .config("spark.sql.adaptive.advisoryPartitionSizeInBytes", "64MB") \
        .config("spark.sql.adaptive.skewJoin.enabled", "true")
    
    # ClickHouse JDBC driver configuration
    clickhouse_jar = "/opt/spark/jars/clickhouse-jdbc-0.4.6-all.jar"
    if os.path.exists(clickhouse_jar):
        builder = builder.config("spark.jars", clickhouse_jar)
    
    return builder.getOrCreate()


def load_training_data_from_clickhouse(
    spark: SparkSession, 
    table_name: str = "mart_application_features",
    sample_fraction: float = 1.0
) -> DataFrame:
    """
    Load training data from ClickHouse application_mart database.
    
    Args:
        spark: SparkSession
        table_name: Name of the feature table in application_mart
        sample_fraction: Fraction of data to sample (for testing)
        
    Returns:
        Spark DataFrame with training data
    """
    
    # ClickHouse connection parameters
    clickhouse_url = "jdbc:clickhouse://clickhouse_dwh:8123/application_mart"
    connection_properties = {
        "driver": "com.clickhouse.jdbc.ClickHouseDriver",
        "user": "default",
        "password": "",
        "socket_timeout": "300000",
        "connection_timeout": "10000"
    }
    
    logger.info(f"🔌 Connecting to ClickHouse: {clickhouse_url}")
    
    try:
        # Build query with optional sampling
        if sample_fraction < 1.0:
            # ClickHouse SAMPLE syntax for efficient sampling
            query = f"(SELECT * FROM {table_name} SAMPLE {sample_fraction}) AS sampled_data"
        else:
            query = f"(SELECT * FROM {table_name}) AS full_data"
        
        df = spark.read \
            .format("jdbc") \
            .option("url", clickhouse_url) \
            .option("dbtable", query) \
            .option("driver", connection_properties["driver"]) \
            .option("user", connection_properties["user"]) \
            .option("password", connection_properties["password"]) \
            .option("fetchsize", "10000") \
            .option("numPartitions", "8") \
            .load()
            
        row_count = df.count()
        col_count = len(df.columns)
        
        logger.info(f"✅ Loaded {row_count:,} rows with {col_count} columns from ClickHouse")
        logger.info(f"📊 Columns: {', '.join(df.columns[:10])}{'...' if col_count > 10 else ''}")
        
        return df
        
    except Exception as e:
        logger.error(f"❌ Failed to load data from ClickHouse: {e}")
        raise


def prepare_features(df: DataFrame) -> DataFrame:
    """
    Prepare and clean features for ML training.
    
    Args:
        df: Raw DataFrame from ClickHouse
        
    Returns:
        Cleaned DataFrame ready for feature engineering
    """
    
    logger.info("🧹 Preparing features...")
    
    # Define expected feature columns (based on your current training script)
    FEATURE_COLUMNS = [
        "EXT_SOURCE_3", "EXT_SOURCE_2", "EXT_SOURCE_1", "DAYS_BIRTH",
        "AMT_GOODS_PRICE", "AMT_CREDIT", "AMT_ANNUITY", "DAYS_EMPLOYED",
        "CODE_GENDER", "BUREAU_DEBT_TO_CREDIT_RATIO", "BUREAU_ACTIVE_CREDIT_SUM",
        "NAME_EDUCATION_TYPE", "POS_MEAN_CONTRACT_LENGTH", "PREV_ANNUITY_MEAN",
        "PREV_GOODS_TO_CREDIT_RATIO", "NAME_FAMILY_STATUS", "POS_LATEST_MONTH",
        "ORGANIZATION_TYPE", "BUREAU_AMT_MAX_OVERDUE_EVER", "POS_TOTAL_MONTHS_OBSERVED",
        "AMT_INCOME_TOTAL", "PREV_REFUSAL_RATE", "NAME_INCOME_TYPE", "CNT_CHILDREN"
    ]
    
    TARGET_COLUMN = "TARGET"
    
    # Check which columns are available
    available_features = [col for col in FEATURE_COLUMNS if col in df.columns]
    missing_features = [col for col in FEATURE_COLUMNS if col not in df.columns]
    
    if missing_features:
        logger.warning(f"⚠️  Missing features: {missing_features}")
    
    logger.info(f"📈 Using {len(available_features)} features for training")
    
    # Select available features + target
    if TARGET_COLUMN not in df.columns:
        raise ValueError(f"Target column '{TARGET_COLUMN}' not found in data")
    
    # Select features and target, handle missing values
    feature_df = df.select(available_features + [TARGET_COLUMN])
    
    # Convert target to proper numeric type
    feature_df = feature_df.withColumn(TARGET_COLUMN, col(TARGET_COLUMN).cast(IntegerType()))
    
    # Basic data quality checks
    total_rows = feature_df.count()
    target_nulls = feature_df.filter(col(TARGET_COLUMN).isNull()).count()
    
    if target_nulls > 0:
        logger.warning(f"⚠️  Found {target_nulls} rows with null target, removing...")
        feature_df = feature_df.filter(col(TARGET_COLUMN).isNotNull())
    
    # Show target distribution
    target_dist = feature_df.groupBy(TARGET_COLUMN).count().collect()
    for row in target_dist:
        logger.info(f"📊 Target {row[TARGET_COLUMN]}: {row['count']:,} samples")
    
    return feature_df


def create_ml_pipeline(feature_columns: List[str]) -> MLPipeline:
    """
    Create Spark ML pipeline with preprocessing and model training stages.
    
    Args:
        feature_columns: List of feature column names
        
    Returns:
        ML Pipeline ready for fitting
    """
    
    logger.info("🔧 Building ML pipeline...")
    
    # Separate categorical and numerical features
    categorical_features = [
        "CODE_GENDER", "NAME_EDUCATION_TYPE", "NAME_FAMILY_STATUS", 
        "ORGANIZATION_TYPE", "NAME_INCOME_TYPE"
    ]
    numerical_features = [col for col in feature_columns if col not in categorical_features]
    
    available_categorical = [col for col in categorical_features if col in feature_columns]
    available_numerical = [col for col in numerical_features if col in feature_columns]
    
    logger.info(f"📊 Categorical features: {len(available_categorical)}")
    logger.info(f"🔢 Numerical features: {len(available_numerical)}")
    
    stages = []
    final_feature_cols = []
    
    # Process categorical features
    if available_categorical:
        for cat_col in available_categorical:
            # String indexer
            indexer = StringIndexer(
                inputCol=cat_col,
                outputCol=f"{cat_col}_indexed",
                handleInvalid="keep"
            )
            stages.append(indexer)
            
            # One-hot encoder
            encoder = OneHotEncoder(
                inputCol=f"{cat_col}_indexed",
                outputCol=f"{cat_col}_encoded",
                dropLast=True
            )
            stages.append(encoder)
            final_feature_cols.append(f"{cat_col}_encoded")
    
    # Process numerical features
    if available_numerical:
        # Imputation for numerical features
        imputer = Imputer(
            inputCols=available_numerical,
            outputCols=[f"{col}_imputed" for col in available_numerical],
            strategy="median"
        )
        stages.append(imputer)
        
        imputed_num_cols = [f"{col}_imputed" for col in available_numerical]
        
        # Feature scaling
        assembler_num = VectorAssembler(
            inputCols=imputed_num_cols,
            outputCol="numerical_features_raw"
        )
        stages.append(assembler_num)
        
        scaler = StandardScaler(
            inputCol="numerical_features_raw",
            outputCol="numerical_features_scaled",
            withStd=True,
            withMean=True
        )
        stages.append(scaler)
        final_feature_cols.append("numerical_features_scaled")
    
    # Combine all features
    final_assembler = VectorAssembler(
        inputCols=final_feature_cols,
        outputCol="features"
    )
    stages.append(final_assembler)
    
    # Add ML model
    gbt = GBTClassifier(
        featuresCol="features",
        labelCol="TARGET",
        maxDepth=6,
        maxIter=100,
        stepSize=0.1,
        subsamplingRate=0.8,
        seed=42
    )
    stages.append(gbt)
    
    return MLPipeline(stages=stages)


def train_and_evaluate_model(
    spark: SparkSession,
    df: DataFrame,
    pipeline: MLPipeline
) -> Dict[str, Any]:
    """
    Train model with cross-validation and evaluate performance.
    
    Args:
        spark: SparkSession
        df: Training DataFrame
        pipeline: ML Pipeline to train
        
    Returns:
        Dictionary containing trained model and metrics
    """
    
    logger.info("🚂 Training distributed model...")
    
    # Train/test split
    train_df, test_df = df.randomSplit([0.8, 0.2], seed=42)
    
    # Cache for performance
    train_df.cache()
    test_df.cache()
    
    logger.info(f"📊 Training set: {train_df.count():,} rows")
    logger.info(f"📊 Test set: {test_df.count():,} rows")
    
    # Train the pipeline
    model = pipeline.fit(train_df)
    
    # Make predictions
    train_predictions = model.transform(train_df)
    test_predictions = model.transform(test_df)
    
    # Evaluate model
    evaluator_auc = BinaryClassificationEvaluator(
        labelCol="TARGET",
        rawPredictionCol="rawPrediction",
        metricName="areaUnderROC"
    )
    
    evaluator_accuracy = MulticlassClassificationEvaluator(
        labelCol="TARGET",
        predictionCol="prediction",
        metricName="accuracy"
    )
    
    # Calculate metrics
    train_auc = evaluator_auc.evaluate(train_predictions)
    test_auc = evaluator_auc.evaluate(test_predictions)
    train_accuracy = evaluator_accuracy.evaluate(train_predictions)
    test_accuracy = evaluator_accuracy.evaluate(test_predictions)
    
    metrics = {
        "train_auc": train_auc,
        "test_auc": test_auc,
        "train_accuracy": train_accuracy,
        "test_accuracy": test_accuracy
    }
    
    logger.info(f"📈 Training AUC: {train_auc:.4f}")
    logger.info(f"📈 Test AUC: {test_auc:.4f}")
    logger.info(f"🎯 Training Accuracy: {train_accuracy:.4f}")
    logger.info(f"🎯 Test Accuracy: {test_accuracy:.4f}")
    
    return {
        "model": model,
        "metrics": metrics,
        "test_predictions": test_predictions
    }


def register_to_mlflow(
    model: MLPipeline,
    metrics: Dict[str, float],
    experiment_name: str,
    model_name: str,
    stage: str = None
) -> str:
    """Register trained model to MLflow."""
    
    logger.info("📝 Registering model to MLflow...")
    
    mlflow.set_experiment(experiment_name)
    
    with mlflow.start_run() as run:
        # Log parameters
        gbt_stage = None
        for stage_obj in model.stages:
            if hasattr(stage_obj, 'getMaxDepth'):
                gbt_stage = stage_obj
                break
                
        if gbt_stage:
            mlflow.log_param("max_depth", gbt_stage.getMaxDepth())
            mlflow.log_param("max_iter", gbt_stage.getMaxIter())
            mlflow.log_param("step_size", gbt_stage.getStepSize())
        
        # Log metrics
        for metric_name, value in metrics.items():
            mlflow.log_metric(metric_name, value)
        
        # Log model
        model_info = mlflow.spark.log_model(
            spark_model=model,
            artifact_path="model",
            registered_model_name=model_name
        )
        
        logger.info(f"✅ Model registered: {model_name}")
        logger.info(f"🔗 Run ID: {run.info.run_id}")
        
        # Stage transition if specified
        if stage:
            client = mlflow.tracking.MlflowClient()
            versions = client.search_model_versions(f"name='{model_name}'")
            for version in versions:
                if version.run_id == run.info.run_id:
                    client.transition_model_version_stage(
                        name=model_name,
                        version=version.version,
                        stage=stage,
                        archive_existing_versions=False
                    )
                    logger.info(f"🔄 Transitioned to stage: {stage}")
                    break
        
        return run.info.run_id


def main():
    parser = argparse.ArgumentParser(description="Spark ML Training with ClickHouse")
    parser.add_argument("--table", default="mart_application_features", 
                       help="ClickHouse table name")
    parser.add_argument("--experiment", default="credit-risk-clickhouse",
                       help="MLflow experiment name")
    parser.add_argument("--register-name", default="credit_risk_model_spark",
                       help="MLflow model name")
    parser.add_argument("--stage", help="Model stage (Production, Staging)")
    parser.add_argument("--sample", type=float, default=1.0,
                       help="Data sampling fraction (0.0-1.0)")
    
    args = parser.parse_args()
    
    logger.info("🚀 Starting Spark ML training with ClickHouse")
    
    # Initialize Spark
    spark = create_spark_session()
    logger.info(f"🌟 Spark UI: {spark.sparkContext.uiWebUrl}")
    
    try:
        # Load data from ClickHouse
        df = load_training_data_from_clickhouse(
            spark, args.table, args.sample
        )
        
        # Prepare features
        feature_df = prepare_features(df)
        
        # Get feature columns (exclude target)
        feature_columns = [col for col in feature_df.columns if col != "TARGET"]
        
        # Create ML pipeline
        pipeline = create_ml_pipeline(feature_columns)
        
        # Train and evaluate
        results = train_and_evaluate_model(spark, feature_df, pipeline)
        
        # Register to MLflow
        run_id = register_to_mlflow(
            results["model"],
            results["metrics"],
            args.experiment,
            args.register_name,
            args.stage
        )
        
        logger.info(f"🎉 Training complete! Test AUC: {results['metrics']['test_auc']:.4f}")
        logger.info(f"📋 MLflow Run ID: {run_id}")
        
    except Exception as e:
        logger.error(f"❌ Training failed: {e}")
        raise
    finally:
        spark.stop()
        logger.info("🔌 Spark session stopped")


if __name__ == "__main__":
    main()