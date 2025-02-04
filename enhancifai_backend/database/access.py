from enhancifai_backend.database.core import DbSession

read_db = DbSession('read')
write_db = DbSession('write')
