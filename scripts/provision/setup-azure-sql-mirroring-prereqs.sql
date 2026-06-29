:setvar FABRIC_SQL_LOGIN "fabric_login"
:setvar FABRIC_SQL_USER "fabric_user"
:setvar HAMMERDB_SQL_LOGIN "hammerdb"
:setvar HAMMERDB_SQL_USER "hammerdb"

IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'$(FABRIC_SQL_USER)')
BEGIN
  DECLARE @create_fabric_user nvarchar(max) =
    N'CREATE USER ' + QUOTENAME(N'$(FABRIC_SQL_USER)') +
    N' FOR LOGIN ' + QUOTENAME(N'$(FABRIC_SQL_LOGIN)');
  EXEC sys.sp_executesql @create_fabric_user;
END;

GRANT SELECT TO [$(FABRIC_SQL_USER)];
GRANT ALTER ANY EXTERNAL MIRROR TO [$(FABRIC_SQL_USER)];
GRANT VIEW DATABASE PERFORMANCE STATE TO [$(FABRIC_SQL_USER)];
GRANT VIEW DATABASE SECURITY STATE TO [$(FABRIC_SQL_USER)];

IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'$(HAMMERDB_SQL_USER)')
BEGIN
  DECLARE @create_hammerdb_user nvarchar(max) =
    N'CREATE USER ' + QUOTENAME(N'$(HAMMERDB_SQL_USER)') +
    N' FOR LOGIN ' + QUOTENAME(N'$(HAMMERDB_SQL_LOGIN)');
  EXEC sys.sp_executesql @create_hammerdb_user;
END;

ALTER ROLE db_owner ADD MEMBER [$(HAMMERDB_SQL_USER)];
GO
