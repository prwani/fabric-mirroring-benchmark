# HammerDB CLI script for PostgreSQL TPROC-C schema validation.

proc env_or_default {name default} {
    if {[info exists ::env($name)] && $::env($name) ne ""} {
        return $::env($name)
    }
    return $default
}

set pg_host $::env(POSTGRES_HOST)
set pg_port [env_or_default POSTGRES_PORT "5432"]
set pg_user [env_or_default POSTGRES_ADMIN_USER "pgadmin"]
set pg_pass $::env(PGPASSWORD)
set pg_defaultdbase [env_or_default POSTGRES_DEFAULT_DATABASE "postgres"]
set pg_db [env_or_default TPROC_C_DATABASE "tprocc"]
set bench_user [env_or_default TPROC_C_USER "tprocc"]
set bench_pass [env_or_default TPROC_C_PASSWORD $pg_pass]
set tablespace [env_or_default TPROC_C_TABLESPACE "pg_default"]

dbset db pg
dbset bm TPC-C

diset connection pg_host $pg_host
diset connection pg_port $pg_port
diset connection pg_sslmode require

diset tpcc pg_superuser $pg_user
diset tpcc pg_superuserpass $pg_pass
diset tpcc pg_defaultdbase $pg_defaultdbase
diset tpcc pg_user $bench_user
diset tpcc pg_pass $bench_pass
diset tpcc pg_dbase $pg_db
diset tpcc pg_tspace $tablespace

puts "TPROC-C CHECK SCHEMA STARTED"
checkschema
puts "TPROC-C CHECK SCHEMA COMPLETED"
