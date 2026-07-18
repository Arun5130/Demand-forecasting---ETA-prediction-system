# Order ingestion

`OrderCsvTransformer` accepts a caller-provided mapping from source CSV columns to the
canonical delivery schema. It parses UTC timestamps, rejects missing identities and duplicate
source order IDs, and normalizes delivery values before a database transaction starts.

`OrderIngestionService` upserts zones, restaurants, customers, drivers, and orders using
PostgreSQL conflict handling. A retry of the same source is idempotent. Configure ETL batch
size through `ETL_BATCH_SIZE`.
