# HammerDB CLI script for PostgreSQL TPROC-C timed workload.

if {![info exists ::env(TMPDIR)] || $::env(TMPDIR) eq ""} {
    set ::env(TMPDIR) "/tmp"
}
if {![info exists ::env(TMP)] || $::env(TMP) eq ""} {
    set ::env(TMP) $::env(TMPDIR)
}
if {![info exists ::env(TEMP)] || $::env(TEMP) eq ""} {
    set ::env(TEMP) $::env(TMPDIR)
}

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
set vusers [env_or_default TPROC_C_VUSERS "8"]
set rampup [env_or_default TPROC_C_RAMPUP_MINUTES "2"]
set duration [env_or_default TPROC_C_DURATION_MINUTES "10"]
set total_iterations [env_or_default TPROC_C_TOTAL_ITERATIONS "10000000"]
set allwarehouse [env_or_default TPROC_C_ALL_WAREHOUSE "true"]

puts "SETTING POSTGRESQL TPROC-C RUN CONFIGURATION"
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
diset tpcc pg_driver timed
diset tpcc pg_total_iterations $total_iterations
diset tpcc pg_rampup $rampup
diset tpcc pg_duration $duration
diset tpcc pg_vacuum true
diset tpcc pg_timeprofile true
diset tpcc pg_allwarehouse $allwarehouse

loadscript
puts "TPROC-C TEST STARTED"
vuset vu $vusers
vucreate
tcstart
tcstatus
set jobid [ vurun ]
vudestroy
tcstop
puts "TPROC-C TEST COMPLETE jobid=$jobid"
