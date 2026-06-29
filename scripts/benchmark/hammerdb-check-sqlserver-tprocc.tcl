# HammerDB CLI script for SQL Server/Azure SQL Database TPROC-C schema validation.

if {![info exists ::env(TMPDIR)] || $::env(TMPDIR) eq ""} {
    set ::env(TMPDIR) "/tmp"
}
if {![info exists ::env(TMP)] || $::env(TMP) eq ""} {
    set ::env(TMP) $::env(TMPDIR)
}
if {![info exists ::env(TEMP)] || $::env(TEMP) eq ""} {
    set ::env(TEMP) $::env(TMPDIR)
}
if {![info exists ::env(PATH)] || $::env(PATH) eq ""} {
    set ::env(PATH) "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
}
foreach dir {/opt/mssql-tools18/bin /opt/mssql-tools/bin} {
    if {[file isdirectory $dir] && [string first ":$dir:" ":$::env(PATH):"] < 0} {
        set ::env(PATH) "$dir:$::env(PATH)"
    }
}

set sql_host $::env(AZURE_SQL_HOST)
set sql_port [expr {[info exists ::env(AZURE_SQL_PORT)] ? $::env(AZURE_SQL_PORT) : "1433"}]
set sql_user [expr {[info exists ::env(AZURE_SQL_HAMMERDB_LOGIN)] ? $::env(AZURE_SQL_HAMMERDB_LOGIN) : $::env(AZURE_SQL_ADMIN_USER)}]
set sql_pass [expr {[info exists ::env(AZURE_SQL_HAMMERDB_PASSWORD)] && $::env(AZURE_SQL_HAMMERDB_PASSWORD) ne "" ? $::env(AZURE_SQL_HAMMERDB_PASSWORD) : $::env(AZURE_SQL_ADMIN_PASSWORD)}]
set sql_auth [expr {[info exists ::env(AZURE_SQL_AUTH_MODE)] ? [string tolower $::env(AZURE_SQL_AUTH_MODE)] : "sql"}]
set msi_object_id [expr {[info exists ::env(AZURE_SQL_MSI_OBJECT_ID)] ? $::env(AZURE_SQL_MSI_OBJECT_ID) : "null"}]
set sql_db [expr {[info exists ::env(AZURE_SQL_TPROC_C_DATABASE)] ? $::env(AZURE_SQL_TPROC_C_DATABASE) : "tprocc"}]

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
diset tpcc mssqls_dbase $sql_db

print dict
checkschema
