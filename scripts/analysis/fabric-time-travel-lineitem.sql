/*
Use this template in the Fabric SQL endpoint after running
scripts/benchmark/run-lineitem-bulk-update.py.

Replace:
  <before_timestamp_utc> with source_pre_update_ts from the CSV
  <after_timestamp_utc>  with fabric_seen_ts or a later UTC timestamp
  <l_orderkey> and <l_linenumber> with sample keys from the CSV
*/

SELECT
    l_orderkey,
    l_linenumber,
    mirror_benchmark_update_batch,
    mirror_benchmark_update_ts
FROM [_public].[lineitem]
WHERE l_orderkey = <l_orderkey>
  AND l_linenumber = <l_linenumber>
OPTION (FOR TIMESTAMP AS OF '<before_timestamp_utc>');

SELECT
    l_orderkey,
    l_linenumber,
    mirror_benchmark_update_batch,
    mirror_benchmark_update_ts
FROM [_public].[lineitem]
WHERE l_orderkey = <l_orderkey>
  AND l_linenumber = <l_linenumber>
OPTION (FOR TIMESTAMP AS OF '<after_timestamp_utc>');
