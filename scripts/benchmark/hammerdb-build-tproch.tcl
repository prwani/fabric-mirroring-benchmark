# HammerDB CLI script for PostgreSQL TPROC-H schema build.
# Override values with env vars before invoking hammerdbcli auto.

set pg_host $::env(POSTGRES_HOST)
set pg_port [expr {[info exists ::env(POSTGRES_PORT)] ? $::env(POSTGRES_PORT) : "5432"}]
set pg_user $::env(POSTGRES_ADMIN_USER)
set pg_pass $::env(PGPASSWORD)
set pg_db $::env(POSTGRES_DATABASE)
set sf [expr {[info exists ::env(TPROC_H_SCALE_FACTOR)] ? $::env(TPROC_H_SCALE_FACTOR) : "1"}]
set vus [expr {[info exists ::env(TPROC_H_VUSERS)] ? $::env(TPROC_H_VUSERS) : "4"}]

dbset db pg
dbset bm TPROC-H
diset connection pg_host $pg_host
diset connection pg_port $pg_port
diset connection pg_user $pg_user
diset connection pg_pass $pg_pass
diset connection pg_dbase $pg_db
diset tpch pg_scale_fact $sf
diset tpch pg_num_tpch_threads $vus

print dict
buildschema
waittocomplete
quit

