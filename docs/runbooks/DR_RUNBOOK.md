# Disaster recovery runbook (Design Area 50)

## RPO / RTO targets

| Component | RPO | RTO | Backup method |
| --- | --- | --- | --- |
| PostgreSQL | 15 min | 30 min | WAL archive + daily `pg_dump` |
| Qdrant | 1 hour | 1 hour | snapshot API, triggered post bulk ops |
| Neo4j | 1 hour | 1 hour | `neo4j-admin dump` nightly |
| Redis | N/A (cache) | 5 min | rebuild from source of truth |
| Kafka | 0 | 5 min | replication factor 3 (prod); single broker (dev) |
| MinIO / blob | 0 | 15 min | volume replication; prod uses versioned bucket |

## Backup commands (local demo)

```bash
# Postgres — ~1s for this demo
docker exec documind-postgres pg_dump -U documind documind > backups/pg-$(date +%Y%m%d).sql

# Qdrant
curl -X POST http://localhost:6333/collections/chunks/snapshots
# Then copy snapshots out of ./data/qdrant/snapshots/

# Neo4j
docker exec documind-neo4j neo4j-admin database dump neo4j --to-path=/backups

# MinIO
mc mirror local/documents backups/minio/
```

## Restore procedure

1. **Stop services**: `make data-down`
2. **Restore stores**:
   - Postgres: `docker compose up -d postgres`, then `psql < backups/pg-YYYYMMDD.sql`
   - Qdrant: copy snapshot into `./data/qdrant/snapshots/`, call `POST /collections/chunks/snapshots/recover`
   - Neo4j: `neo4j-admin database load neo4j --from-path=/backups`
   - MinIO: `mc mirror backups/minio/ local/documents`
3. **Verify integrity**: run `scripts/smoke_test.py` — upload fails means index corruption.
4. **Start services**: `make data-up`, then individual `make run-*`.

## Monthly DR drill

1. Create a snapshot of every store.
2. Spin up a parallel stack with different ports.
3. Restore from the snapshot.
4. Run smoke_test.py against the parallel stack.
5. Compare results to a baseline eval run.
6. Document drift / issues.
7. Tear down parallel stack.

If any drill step takes longer than its RTO target, open a SEV2 ticket to
address the gap before the next drill.
