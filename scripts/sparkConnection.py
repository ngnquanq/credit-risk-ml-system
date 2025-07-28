from pyspark.sql import SparkSession

# Replace 'sc://localhost:8888' with the address of your Spark Connect server
# The local port 8888 is forwarded to the remote Spark Connect server (port 15002)
spark = SparkSession.builder.remote("sc://localhost:8888").getOrCreate()

# Now you can use the 'spark' object to interact with the Spark cluster
df = spark.range(10)
df.show()

# When you are done, stop the SparkSession
spark.stop()