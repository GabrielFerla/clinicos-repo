-- Privilégios do usuário da aplicação (CLINICOS).
--
-- A imagem `gvenzl/oracle-free` cria o usuário via `APP_USER` com CONNECT +
-- RESOURCE, o que cobre a maior parte do schema. Os dois grants abaixo não
-- vêm por padrão e só falham **tarde** — no primeiro INSERT ou na criação do
-- índice vetorial, quando o schema já parece pronto:
--
--   ORA-01950: no privileges on tablespace 'USERS'
--       Sem cota, o CREATE TABLE passa e o INSERT falha.
--
--   ORA-01031 / falha no CREATE VECTOR INDEX
--       O índice vetorial (S1-12) é tratado como mining model pelo 23ai.
--
-- Lembrete operacional: scripts de `/container-entrypoint-initdb.d` só rodam
-- na **criação do volume**. Num volume que já existe, aplique na mão:
--
--     docker compose exec oracle sqlplus -S system/oracle@FREEPDB1 @/container-entrypoint-initdb.d/02_grants.sql
--
-- Nota de arquitetura: vetores nunca moram no schema SYSTEM — a tablespace
-- dele é MANUAL e a coluna VECTOR retorna ORA-43853 (ver ADR-0004).

ALTER SESSION SET CONTAINER = FREEPDB1;

ALTER USER clinicos QUOTA UNLIMITED ON USERS;

GRANT CREATE MINING MODEL TO clinicos;

EXIT;
