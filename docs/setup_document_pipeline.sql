-- =============================================================================
-- Document Intelligence Pipeline - Object Setup
-- =============================================================================
-- Provisions the objects the Enterprise AI document upload flow depends on:
--
--   1. @DOC_STAGE            - internal stage receiving uploaded files (PUT)
--   2. DOCUMENT_CHUNKS       - chunked text + embeddings written by the app
--   3. INSURANCE_SEARCH_SVC  - Cortex Search service the agent queries
--
-- Objects 1 and 2 are also created idempotently at runtime by
-- backend_service.ensure_document_pipeline(), so a fresh account works without
-- running this script. Object 3 is NOT created at runtime: a Cortex Search
-- service is a billable background job and is provisioned explicitly here
-- rather than implicitly on a user's first upload.
--
-- Safe to re-run: every statement is IF NOT EXISTS.
-- =============================================================================

USE DATABASE UNIFIEDAI_DB;
USE SCHEMA UNIFIEDAI_SH;
USE WAREHOUSE COMPUTE_WH;


-- -----------------------------------------------------------------------------
-- 1. Upload stage
-- -----------------------------------------------------------------------------
-- SNOWFLAKE_SSE encryption is required for SNOWFLAKE.CORTEX.PARSE_DOCUMENT to
-- read files back off the stage. DIRECTORY enables listing uploaded files.
CREATE STAGE IF NOT EXISTS UNIFIEDAI_DB.UNIFIEDAI_SH.DOC_STAGE
    DIRECTORY = (ENABLE = TRUE)
    ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
    COMMENT = 'Uploaded insurance documents awaiting parse and chunk ingestion';

-- CREATE ... IF NOT EXISTS does not modify an existing stage, and an internal stage's
-- encryption mode CANNOT be changed afterwards -- "ALTER STAGE ... SET ENCRYPTION"
-- fails with "Cannot set URL, credentials, or encryption key of an internal or
-- temporary stage". A stage created without SNOWFLAKE_SSE defaults to client-side
-- encryption, and PARSE_DOCUMENT then fails with "Input files from stages with Client
-- Side Encryption is not supported", so OCR of scanned/image PDFs never works.
--
-- If OCR is needed and DOC_STAGE predates this script, the stage must be RECREATED.
-- This DESTROYS staged files, so it is commented out deliberately -- uncomment and run
-- it only when you accept that, then re-upload any documents you still need.
-- Text-extractable PDFs are unaffected: the app extracts those client-side.
--
--   CREATE OR REPLACE STAGE UNIFIEDAI_DB.UNIFIEDAI_SH.DOC_STAGE
--       DIRECTORY = (ENABLE = TRUE)
--       ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
--       COMMENT = 'Uploaded insurance documents awaiting parse and chunk ingestion';
--
-- Check the current mode with:  DESC STAGE UNIFIEDAI_DB.UNIFIEDAI_SH.DOC_STAGE;


-- -----------------------------------------------------------------------------
-- 2. Chunk table
-- -----------------------------------------------------------------------------
-- Column list and order must match the INSERT in
-- backend_service.chunk_and_ingest_document().
--
-- Note on EMBEDDING: the app populates this via CORTEX.EMBED_TEXT_768, but the
-- search service below is declared with auto-embedding on CHUNK_TEXT, so
-- Snowflake generates its own index vectors and does not read this column.
-- It is retained for direct vector similarity queries (VECTOR_COSINE_SIMILARITY)
-- outside the search service.
CREATE TABLE IF NOT EXISTS UNIFIEDAI_DB.UNIFIEDAI_SH.DOCUMENT_CHUNKS (
    FILE_NAME    VARCHAR(512),
    CHUNK_TEXT   VARCHAR(16777216),
    CHUNK_INDEX  NUMBER(38,0),
    UPLOADED_AT  TIMESTAMP_NTZ,
    DOC_TYPE     VARCHAR(64),
    EMBEDDING    VECTOR(FLOAT, 768),
    FILE_SIZE    NUMBER(38,0)
);


-- -----------------------------------------------------------------------------
-- 3. Cortex Search service
-- -----------------------------------------------------------------------------
-- Name must match the SEARCH_SERVICE entry in .env (default INSURANCE_SEARCH_SVC),
-- which backend_service.refresh_document_search_service() issues REFRESH against.
--
-- ATTRIBUTES exposes FILE_NAME and DOC_TYPE as filterable columns, which is what
-- allows retrieval to be scoped to a single uploaded document.
CREATE CORTEX SEARCH SERVICE IF NOT EXISTS UNIFIEDAI_DB.UNIFIEDAI_SH.INSURANCE_SEARCH_SVC
    ON CHUNK_TEXT
    ATTRIBUTES FILE_NAME, DOC_TYPE
    WAREHOUSE = COMPUTE_WH
    TARGET_LAG = '1 hour'
    EMBEDDING_MODEL = 'snowflake-arctic-embed-m-v1.5'
    AS (
        SELECT
            CHUNK_TEXT,
            FILE_NAME,
            CHUNK_INDEX,
            DOC_TYPE
        FROM UNIFIEDAI_DB.UNIFIEDAI_SH.DOCUMENT_CHUNKS
        WHERE CHUNK_TEXT IS NOT NULL
    );


-- -----------------------------------------------------------------------------
-- Verification
-- -----------------------------------------------------------------------------
SHOW STAGES LIKE 'DOC_STAGE' IN SCHEMA UNIFIEDAI_DB.UNIFIEDAI_SH;
SHOW CORTEX SEARCH SERVICES LIKE 'INSURANCE_SEARCH_SVC' IN SCHEMA UNIFIEDAI_DB.UNIFIEDAI_SH;

SELECT
    COUNT(*)                     AS TOTAL_CHUNKS,
    COUNT(DISTINCT FILE_NAME)    AS DISTINCT_DOCUMENTS,
    MAX(UPLOADED_AT)             AS LAST_UPLOAD
FROM UNIFIEDAI_DB.UNIFIEDAI_SH.DOCUMENT_CHUNKS;
