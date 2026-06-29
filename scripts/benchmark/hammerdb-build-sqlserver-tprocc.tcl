# HammerDB CLI script for SQL Server/Azure SQL Database TPROC-C schema build.
# Override values with env vars before invoking hammerdbcli auto.

set sql_host $::env(AZURE_SQL_HOST)
set sql_port [expr {[info exists ::env(AZURE_SQL_PORT)] ? $::env(AZURE_SQL_PORT) : "1433"}]
set sql_user [expr {[info exists ::env(AZURE_SQL_HAMMERDB_LOGIN)] ? $::env(AZURE_SQL_HAMMERDB_LOGIN) : $::env(AZURE_SQL_ADMIN_USER)}]
set sql_pass [expr {[info exists ::env(AZURE_SQL_HAMMERDB_PASSWORD)] && $::env(AZURE_SQL_HAMMERDB_PASSWORD) ne "" ? $::env(AZURE_SQL_HAMMERDB_PASSWORD) : $::env(AZURE_SQL_ADMIN_PASSWORD)}]
set sql_auth [expr {[info exists ::env(AZURE_SQL_AUTH_MODE)] ? [string tolower $::env(AZURE_SQL_AUTH_MODE)] : "sql"}]
set msi_object_id [expr {[info exists ::env(AZURE_SQL_MSI_OBJECT_ID)] ? $::env(AZURE_SQL_MSI_OBJECT_ID) : "null"}]
set sql_db [expr {[info exists ::env(AZURE_SQL_TPROC_C_DATABASE)] ? $::env(AZURE_SQL_TPROC_C_DATABASE) : "tprocc"}]
set warehouses [expr {[info exists ::env(TPROC_C_WAREHOUSES)] ? $::env(TPROC_C_WAREHOUSES) : "10"}]
set build_vus [expr {[info exists ::env(TPROC_C_BUILD_VUSERS)] ? $::env(TPROC_C_BUILD_VUSERS) : "4"}]

dbset db mssqls
dbset bm TPROC-C
diset connection mssqls_server $sql_host
diset connection mssqls_linux_server $sql_host
diset connection mssqls_port $sql_port
diset connection mssqls_tcp true
diset connection mssqls_azure true
diset connection mssqls_authentication $sql_auth
diset connection mssqls_linux_authent $sql_auth
diset connection mssqls_msi_object_id $msi_object_id
diset connection mssqls_uid $sql_user
diset connection mssqls_pass $sql_pass
diset connection mssqls_encrypt_connection true
diset connection mssqls_trust_server_cert false
diset tpcc mssqls_count_ware $warehouses
diset tpcc mssqls_num_vu $build_vus
diset tpcc mssqls_dbase $sql_db

print dict
buildschema
