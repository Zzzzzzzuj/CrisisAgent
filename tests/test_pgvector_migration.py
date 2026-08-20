from pathlib import Path


def test_pgvector_migration_is_after_knowledge_management():
    migration = Path("alembic/versions/0004_add_pgvector_knowledge_vectors.py").read_text(encoding="utf-8")

    assert 'revision = "0004_pgvector"' in migration
    assert 'down_revision = "0003_knowledge_mgmt"' in migration


def test_pgvector_migration_declares_extension_table_index_and_downgrade():
    migration = Path("alembic/versions/0004_add_pgvector_knowledge_vectors.py").read_text(encoding="utf-8")

    assert "CREATE EXTENSION IF NOT EXISTS vector" in migration
    assert "knowledge_chunk_vectors" in migration
    assert "vector_cosine_ops" in migration
    assert "def downgrade" in migration
    assert "drop_table" in migration
