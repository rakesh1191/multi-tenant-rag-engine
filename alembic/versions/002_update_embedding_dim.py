"""Update embedding column from vector(1536) to vector(768) for nomic-embed-text

Revision ID: 002
Revises: 001
Create Date: 2026-03-15

"""
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the HNSW index first (can't alter indexed column directly)
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")

    # Change embedding column dimension
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(768)")

    # Recreate HNSW index with new dimension
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding_hnsw "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(1536)")
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding_hnsw "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )
