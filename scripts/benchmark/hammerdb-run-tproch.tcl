# HammerDB CLI script for PostgreSQL TPROC-H query workload.

set pg_host $::env(POSTGRES_HOST)
set pg_port [expr {[info exists ::env(POSTGRES_PORT)] ? $::env(POSTGRES_PORT) : "5432"}]
set pg_user $::env(POSTGRES_ADMIN_USER)
set pg_pass $::env(PGPASSWORD)
set pg_db $::env(POSTGRES_DATABASE)
set vus [expr {[info exists ::env(TPROC_H_VUSERS)] ? $::env(TPROC_H_VUSERS) : "4"}]

dbset db pg
dbset bm TPROC-H
diset connection pg_host $pg_host
diset connection pg_port $pg_port
diset connection pg_sslmode require
diset tpch pg_tpch_user $pg_user
diset tpch pg_tpch_pass $pg_pass
diset tpch pg_tpch_dbase $pg_db

loadscript
vuset vu $vus
vucreate
vurun
vudestroy
