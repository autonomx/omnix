# MEM-14 settings route precedence correction

The static `/api/assistant/memory/settings` route is registered before the dynamic `/api/assistant/memory/{memory_id}` management route. This guarantees that GET and POST settings operations cannot be interpreted as memory-record lookups and keeps the browser settings client aligned with the server route table.
