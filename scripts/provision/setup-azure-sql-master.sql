:setvar FABRIC_SQL_LOGIN "fabric_login"
:setvar FABRIC_SQL_PASSWORD ""
:setvar HAMMERDB_SQL_LOGIN "hammerdb"
:setvar HAMMERDB_SQL_PASSWORD ""

IF NOT EXISTS (SELECT 1 FROM sys.sql_logins WHERE name = N'$(FABRIC_SQL_LOGIN)')
BEGIN
  DECLARE @create_fabric_login nvarchar(max) =
    N'CREATE LOGIN ' + QUOTENAME(N'$(FABRIC_SQL_LOGIN)') +
    N' WITH PASSWORD = ' + QUOTENAME(N'$(FABRIC_SQL_PASSWORD)', '''');
  EXEC sys.sp_executesql @create_fabric_login;
END;

IF NOT EXISTS (SELECT 1 FROM sys.sql_logins WHERE name = N'$(HAMMERDB_SQL_LOGIN)')
BEGIN
  DECLARE @create_hammerdb_login nvarchar(max) =
    N'CREATE LOGIN ' + QUOTENAME(N'$(HAMMERDB_SQL_LOGIN)') +
    N' WITH PASSWORD = ' + QUOTENAME(N'$(HAMMERDB_SQL_PASSWORD)', '''');
  EXEC sys.sp_executesql @create_hammerdb_login;
END;
GO
