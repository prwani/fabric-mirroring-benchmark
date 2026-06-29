# HammerDB CLI script for SQL Server/Azure SQL Database TPROC-H schema build.
# Override values with env vars before invoking hammerdbcli auto.

set sql_host $::env(AZURE_SQL_HOST)
set sql_port [expr {[info exists ::env(AZURE_SQL_PORT)] ? $::env(AZURE_SQL_PORT) : "1433"}]
set sql_user [expr {[info exists ::env(AZURE_SQL_HAMMERDB_LOGIN)] ? $::env(AZURE_SQL_HAMMERDB_LOGIN) : $::env(AZURE_SQL_ADMIN_USER)}]
set sql_pass [expr {[info exists ::env(AZURE_SQL_HAMMERDB_PASSWORD)] && $::env(AZURE_SQL_HAMMERDB_PASSWORD) ne "" ? $::env(AZURE_SQL_HAMMERDB_PASSWORD) : $::env(AZURE_SQL_ADMIN_PASSWORD)}]
set sql_db $::env(AZURE_SQL_DATABASE)
set sf [expr {[info exists ::env(TPROC_H_SCALE_FACTOR)] ? $::env(TPROC_H_SCALE_FACTOR) : "1"}]
set threads [expr {[info exists ::env(TPROC_H_BUILD_THREADS)] ? $::env(TPROC_H_BUILD_THREADS) : "4"}]
set columnstore [expr {[info exists ::env(TPROC_H_USE_COLUMNSTORE)] ? $::env(TPROC_H_USE_COLUMNSTORE) : "false"}]
set use_bcp [expr {[info exists ::env(TPROC_H_USE_BCP)] ? $::env(TPROC_H_USE_BCP) : "false"}]

dbset db mssqls
dbset bm TPROC-H
diset connection mssqls_server $sql_host
diset connection mssqls_linux_server $sql_host
diset connection mssqls_port $sql_port
diset connection mssqls_tcp true
diset connection mssqls_azure true
diset connection mssqls_authentication sql
diset connection mssqls_linux_authent sql
diset connection mssqls_uid $sql_user
diset connection mssqls_pass $sql_pass
diset connection mssqls_encrypt_connection true
diset connection mssqls_trust_server_cert false
diset tpch mssqls_tpch_dbase $sql_db
diset tpch mssqls_scale_fact $sf
diset tpch mssqls_num_tpch_threads $threads
diset tpch mssqls_colstore $columnstore
diset tpch mssqls_tpch_use_bcp $use_bcp

print dict
buildschema
waittocomplete
