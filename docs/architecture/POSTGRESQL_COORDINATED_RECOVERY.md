# PostgreSQL and BlobStore Coordinated Recovery

A PostgreSQL dump alone is not a complete Omnix backup. PostgreSQL owns structured authority while BlobStore owns referenced binary artifacts. Recovery therefore uses one durable backup generation covering both authorities.

## Generation workflow

1. Create a backup generation with exact software revision, schema range, BlobStore root, retention, RPO, RTO, and encryption policy.
2. Capture the active PostgreSQL asset manifest containing asset identity, workspace, storage provider/key, checksum, byte size, and lifecycle state.
3. Extend deletion protection for manifested assets beyond the supported backup window.
4. Copy or snapshot BlobStore content for the generation.
5. Create the PostgreSQL custom-format backup and record its durable reference.
6. Restore PostgreSQL into an empty database and blobs into an empty BlobStore root.
7. Verify every manifested file by existence, byte size, and SHA-256 checksum.
8. Run migration verification and deterministic application smoke tests.
9. Mark the generation verified only after all authority checks pass.

## Safety rules

- Permanent blob deletion is blocked until `deletion_not_before` has passed.
- Missing and checksum-mismatched blobs fail the generation; they are never silently ignored.
- Unreferenced restored files are reported separately and may be cleaned only after authority verification.
- Backup destinations containing real user data must be encrypted at rest.
- Default targets are RPO 24 hours, RTO 1 hour, and 30-day retention unless an operator records stricter policy.
- The cutover authority gate requires a verified post-import generation.

## Evidence

`omnix_backup_generations` records generation status and policy. `omnix_backup_blob_manifest` records the exact blob authority set and per-item verification. Provider-free PostgreSQL integration tests verify successful generations, missing-blob failure, manifest hashing, and deletion protection.