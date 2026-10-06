
AND lease_owner IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL
AND (
    (job_type = 'chat.generate'
     AND metadata #> '{compat_contract,compat,inline_execution}' = 'true'::jsonb
     AND EXISTS (
        SELECT 1 FROM omnix_runtime_nodes AS execution_owner
         WHERE execution_owner.id = %s
           AND execution_owner.id = omnix_jobs.metadata #>> '{compat_contract,compat,execution_owner}'
           AND execution_owner.node_type = 'gateway'
           AND execution_owner.status IN ('active', 'draining')
           AND execution_owner.lease_expires_at > clock_timestamp()
           AND execution_owner.metadata ->> 'workspace_id' = omnix_jobs.workspace_id
    ))
    OR (job_type = 'rpg.turn.foreground_record'
        AND module = 'rpg'
        AND metadata #> '{compat_contract,compat,record_only}' = 'true'::jsonb
        AND EXISTS (
            SELECT 1 FROM omnix_rpg_foreground_submissions AS submission
             WHERE submission.workspace_id = omnix_jobs.workspace_id
               AND submission.job_id = omnix_jobs.id
               AND submission.session_id = omnix_jobs.metadata #>> '{compat_contract,input_ref,session_id}'
               AND submission.submission_id = omnix_jobs.input_payload ->> 'submission_id'
               AND submission.claim_token = %s
               AND submission.status = 'claimed'
               AND submission.execution_started_at IS NOT NULL
        ))
)
