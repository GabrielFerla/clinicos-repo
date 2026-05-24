-- Habilita a Vector Pool no Oracle 23ai Free.
--
-- O índice HNSW utilizado em FAQ_VECTOR.EMBEDDING (S1-12) exige
-- vector_memory_size >= 512M. A imagem `gvenzl/oracle-free:23-slim`
-- inicializa esse parâmetro em 0 (Vector Pool desabilitado).
--
-- O comando abaixo grava a configuração apenas no SPFILE — ele só
-- entra em vigor no PRÓXIMO startup do CDB. Isto é uma limitação do
-- parâmetro `vector_memory_size`, que não aceita SCOPE=BOTH/MEMORY.
--
-- Operacionalmente, após o primeiro `make up` é necessário reiniciar
-- o container Oracle uma vez para a Vector Pool ficar ativa. Use:
--     docker compose restart oracle
-- ou o helper `infra/scripts/bootstrap.sh`.

ALTER SYSTEM SET vector_memory_size = 512M SCOPE=SPFILE;

EXIT;
