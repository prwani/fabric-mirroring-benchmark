# Fabric notebook template: inspect mirrored Delta table storage impact.
#
# Run this in a Microsoft Fabric Spark notebook attached to the workspace that
# contains the mirrored database. Fill in the workspace/item/table path from the
# mirrored database REST response. The table path usually lives under:
#   .../<workspaceId>/<mirroredDatabaseId>/Tables/<schema>/<table>
#
# Example:
#   table_path = "abfss://<workspaceId>@onelake.dfs.fabric.microsoft.com/<mirroredDatabaseId>/Tables/_public/lineitem"

from pyspark.sql import functions as F

table_path = "abfss://<workspaceId>@onelake.dfs.fabric.microsoft.com/<mirroredDatabaseId>/Tables/_public/lineitem"


def list_files_recursive(path: str):
    files = []
    for item in mssparkutils.fs.ls(path):
        if item.isDir:
            files.extend(list_files_recursive(item.path))
        else:
            files.append(item)
    return files


def summarize_path(path: str):
    files = list_files_recursive(path)
    rows = [(f.path, f.size) for f in files]
    return spark.createDataFrame(rows, ["path", "size_bytes"])


all_files = summarize_path(table_path)
display(
    all_files
    .withColumn("kind", F.when(F.col("path").contains("/_delta_log/"), F.lit("delta_log")).otherwise(F.lit("data_file")))
    .groupBy("kind")
    .agg(
        F.count("*").alias("file_count"),
        F.sum("size_bytes").alias("total_bytes"),
    )
)

display(
    spark.sql(f"DESCRIBE HISTORY delta.`{table_path}`")
)

# Optional: compare row counts at two timestamps captured by the bulk update CSV.
before_timestamp_utc = "<source_pre_update_ts>"
after_timestamp_utc = "<fabric_seen_ts>"

before_df = spark.read.format("delta").option("timestampAsOf", before_timestamp_utc).load(table_path)
after_df = spark.read.format("delta").option("timestampAsOf", after_timestamp_utc).load(table_path)

print("before rows", before_df.count())
print("after rows", after_df.count())
