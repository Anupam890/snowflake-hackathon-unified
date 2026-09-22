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
