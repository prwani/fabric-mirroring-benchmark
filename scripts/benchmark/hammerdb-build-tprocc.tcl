# HammerDB CLI script for PostgreSQL TPROC-C schema build.

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
set warehouses [env_or_default TPROC_C_WAREHOUSES "10"]
set build_vusers [env_or_default TPROC_C_BUILD_VUSERS "4"]
set tablespace [env_or_default TPROC_C_TABLESPACE "pg_default"]
set partition [env_or_default TPROC_C_PARTITION "false"]

puts "SETTING POSTGRESQL TPROC-C BUILD CONFIGURATION"
dbset db pg
dbset bm TPC-C

diset connection pg_host $pg_host
diset connection pg_port $pg_port
diset connection pg_sslmode require

diset tpcc pg_count_ware $warehouses
diset tpcc pg_num_vu $build_vusers
diset tpcc pg_superuser $pg_user
diset tpcc pg_superuserpass $pg_pass
diset tpcc pg_defaultdbase $pg_defaultdbase
diset tpcc pg_user $pg_user
diset tpcc pg_pass $pg_pass
diset tpcc pg_dbase $pg_db
diset tpcc pg_tspace $tablespace
diset tpcc pg_storedprocs true
diset tpcc pg_partition $partition

puts "TPROC-C SCHEMA BUILD STARTED"
buildschema
puts "TPROC-C SCHEMA BUILD COMPLETED"
