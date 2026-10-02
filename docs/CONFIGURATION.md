# Omnix configuration

This file is generated from `app.config.registry`. Values are intentionally never emitted.

| Variable | Type | Default | Owner | Description |
| --- | --- | --- | --- | --- |
| `APCA_API_KEY_ID` | string | — | trading | Controls apca api key id for trading. |
| `APCA_API_SECRET_KEY` | string | — | trading | Controls apca api secret key for trading. |
| `CI` | boolean | `false` | kernel | Controls ci for kernel. |
| `HERMES_API_KEY` | string | — | hermes, research, trading | Controls hermes api key for hermes, research, trading. |
| `HERMES_BASE_URL` | string | `http://127.0.0.1:8642` | hermes, launcher | Controls hermes base url for hermes, launcher. |
| `HERMES_ENABLED` | string | — | hermes, launcher, research | Controls hermes enabled for hermes, launcher, research. |
| `HERMES_TIMEOUT_SECONDS` | string | `45` | hermes | Controls hermes timeout seconds for hermes. |
| `HF_TOKEN` | string | — | image | Controls hf token for image. |
| `LIVE_SPEECH_INPUT_SAMPLE_RATE` | string | `16000` | live-speech | Controls live speech input sample rate for live-speech. |
| `LIVE_SPEECH_LLM_BASE_URL` | string | `http://127.0.0.1:1234/v1` | live-speech | Controls live speech llm base url for live-speech. |
| `LIVE_SPEECH_LLM_MODEL` | string | `local-model` | live-speech | Controls live speech llm model for live-speech. |
| `LIVE_SPEECH_LLM_PROVIDER` | string | `fake` | live-speech | Controls live speech llm provider for live-speech. |
| `LIVE_SPEECH_OUTPUT_SAMPLE_RATE` | string | `24000` | live-speech | Controls live speech output sample rate for live-speech. |
| `LIVE_SPEECH_REALTIME_ENABLED` | string | `false` | live-speech | Controls live speech realtime enabled for live-speech. |
| `LIVE_SPEECH_STT_PROVIDER` | string | `fake` | live-speech | Controls live speech stt provider for live-speech. |
| `LIVE_SPEECH_STT_URL` | string | `http://127.0.0.1:8000` | live-speech | Controls live speech stt url for live-speech. |
| `LIVE_SPEECH_TTS_PROVIDER` | string | `fake` | live-speech | Controls live speech tts provider for live-speech. |
| `LIVE_SPEECH_TTS_URL` | string | `http://127.0.0.1:5101` | live-speech | Controls live speech tts url for live-speech. |
| `LIVE_SPEECH_VAD_PROVIDER` | string | `energy` | live-speech | Controls live speech vad provider for live-speech. |
| `LM_API_TOKEN` | string | — | live-speech | Controls lm api token for live-speech. |
| `LOCALAPPDATA` | string | — | launcher, security | Controls localappdata for launcher, security. |
| `OMNIX_AGENT_AUTO_INSTALL_DEPENDENCIES` | string | `true` | agent-runtime | Controls agent auto install dependencies for agent-runtime. |
| `OMNIX_AGENT_BROWSER_BACKEND` | string | — | launcher | Controls agent browser backend for launcher. |
| `OMNIX_AGENT_BROWSER_ENABLED` | boolean | `true` | assistant-tools | Controls agent browser enabled for assistant-tools. |
| `OMNIX_AGENT_CONTAINER_BROKER_URL` | string | — | agent-runtime | Controls agent container broker url for agent-runtime. |
| `OMNIX_AGENT_CONTAINER_MODEL_GATEWAY_URL` | string | — | agent-runtime | Controls agent container model gateway url for agent-runtime. |
| `OMNIX_AGENT_DEBUG_LOGS` | string | `0` | launcher, observability | Controls agent debug logs for launcher, observability. |
| `OMNIX_AGENT_DEFAULT_BASE_REF` | string | `HEAD` | agent-runtime | Controls agent default base ref for agent-runtime. |
| `OMNIX_AGENT_DEFAULT_MODEL_ID` | string | — | agent-runtime | Controls agent default model id for agent-runtime. |
| `OMNIX_AGENT_DEFAULT_PROVIDER_ID` | string | — | agent-runtime | Controls agent default provider id for agent-runtime. |
| `OMNIX_AGENT_DEFAULT_REPOSITORY` | string | — | agent-runtime, launcher | Controls agent default repository for agent-runtime, launcher. |
| `OMNIX_AGENT_DEPENDENCY_INSTALL_TIMEOUT_SECONDS` | string | `900` | agent-runtime | Controls agent dependency install timeout seconds for agent-runtime. |
| `OMNIX_AGENT_DOCKER_CPUS` | string | `2` | agent-runtime | Controls agent docker cpus for agent-runtime. |
| `OMNIX_AGENT_DOCKER_IMAGE` | string | — | agent-runtime | Controls agent docker image for agent-runtime. |
| `OMNIX_AGENT_DOCKER_MEMORY` | string | `4g` | agent-runtime | Controls agent docker memory for agent-runtime. |
| `OMNIX_AGENT_DOCKER_NETWORK` | string | — | agent-runtime | Controls agent docker network for agent-runtime. |
| `OMNIX_AGENT_DOCKER_PIDS` | string | `256` | agent-runtime | Controls agent docker pids for agent-runtime. |
| `OMNIX_AGENT_DOCKER_TMPFS` | string | `256m` | agent-runtime | Controls agent docker tmpfs for agent-runtime. |
| `OMNIX_AGENT_LOG_DIR` | string | — | launcher, observability | Controls agent log dir for launcher, observability. |
| `OMNIX_AGENT_LOG_MAX_FIELD_CHARS` | string | — | launcher, observability | Controls agent log max field chars for launcher, observability. |
| `OMNIX_AGENT_LOG_RETENTION_DAYS` | string | — | launcher, observability | Controls agent log retention days for launcher, observability. |
| `OMNIX_AGENT_MCPORTER_COMMAND` | string | — | assistant-tools | Controls agent mcporter command for assistant-tools. |
| `OMNIX_AGENT_MCP_ENABLED` | boolean | `true` | assistant-tools | Controls agent mcp enabled for assistant-tools. |
| `OMNIX_AGENT_MCP_TIMEOUT_SECONDS` | string | `60` | assistant-tools | Controls agent mcp timeout seconds for assistant-tools. |
| `OMNIX_AGENT_PLAN_REVIEW_ENABLED` | string | `false` | agent-runtime | Controls agent plan review enabled for agent-runtime. |
| `OMNIX_AGENT_PLAN_REVIEW_MAX_ROUNDS` | string | `3` | agent-runtime | Controls agent plan review max rounds for agent-runtime. |
| `OMNIX_AGENT_PLAN_REVIEW_MODE` | string | `auto` | agent-runtime | Controls agent plan review mode for agent-runtime. |
| `OMNIX_AGENT_PLAN_REVIEW_MODEL` | string | — | agent-runtime | Controls agent plan review model for agent-runtime. |
| `OMNIX_AGENT_PLAN_REVIEW_PROVIDER` | string | — | agent-runtime | Controls agent plan review provider for agent-runtime. |
| `OMNIX_AGENT_PLAN_REVIEW_REASONING_EFFORT` | string | — | agent-runtime | Controls agent plan review reasoning effort for agent-runtime. |
| `OMNIX_AGENT_PLAN_REVIEW_TIMEOUT_SECONDS` | string | `180` | agent-runtime | Controls agent plan review timeout seconds for agent-runtime. |
| `OMNIX_AGENT_PLAN_REVIEW_TRANSPORT_ATTEMPTS` | string | `2` | agent-runtime | Controls agent plan review transport attempts for agent-runtime. |
| `OMNIX_AGENT_REASONING_EFFORT` | string | — | agent-runtime | Controls agent reasoning effort for agent-runtime. |
| `OMNIX_AGENT_SEMANTIC_CLASSIFIER_MIN_CONFIDENCE` | string | `0.60` | agent-runtime | Controls agent semantic classifier min confidence for agent-runtime. |
| `OMNIX_AGENT_SEMANTIC_CLASSIFIER_MODE` | string | `auto` | agent-runtime | Controls agent semantic classifier mode for agent-runtime. |
| `OMNIX_AGENT_SEMANTIC_CLASSIFIER_MODEL` | string | — | agent-runtime | Controls agent semantic classifier model for agent-runtime. |
| `OMNIX_AGENT_SEMANTIC_CLASSIFIER_PROVIDER` | string | — | agent-runtime | Controls agent semantic classifier provider for agent-runtime. |
| `OMNIX_AGENT_SEMANTIC_CLASSIFIER_TIMEOUT_SECONDS` | string | `6` | agent-runtime | Controls agent semantic classifier timeout seconds for agent-runtime. |
| `OMNIX_AGENT_SEMANTIC_TASK_CACHE` | string | `1` | agent-runtime | Controls agent semantic task cache for agent-runtime. |
| `OMNIX_AGENT_SEMANTIC_TASK_CACHE_SIZE` | string | `256` | agent-runtime | Controls agent semantic task cache size for agent-runtime. |
| `OMNIX_AGENT_SEMANTIC_TASK_CACHE_TTL_SECONDS` | string | `300` | agent-runtime | Controls agent semantic task cache ttl seconds for agent-runtime. |
| `OMNIX_AGENT_SEMANTIC_TASK_PARSER_MODE` | string | `auto` | agent-runtime | Controls agent semantic task parser mode for agent-runtime. |
| `OMNIX_AGENT_SEMANTIC_TASK_PARSER_MODEL` | string | — | agent-runtime | Controls agent semantic task parser model for agent-runtime. |
| `OMNIX_AGENT_SEMANTIC_TASK_PARSER_PROVIDER` | string | — | agent-runtime | Controls agent semantic task parser provider for agent-runtime. |
| `OMNIX_AGENT_SEMANTIC_TASK_PARSER_TIMEOUT_SECONDS` | string | — | agent-runtime | Controls agent semantic task parser timeout seconds for agent-runtime. |
| `OMNIX_ALLOWED_PRIVATE_NETWORKS` | string | — | security | Controls allowed private networks for security. |
| `OMNIX_ALLOW_LEGACY_IMPORT` | boolean | `false` | kernel | Controls allow legacy import for kernel. |
| `OMNIX_ALLOW_LEGACY_TEST_PERSISTENCE` | boolean | `false` | kernel | Controls allow legacy test persistence for kernel. |
| `OMNIX_ALPACA_API_KEY_ID` | string | — | trading | Controls alpaca api key id for trading. |
| `OMNIX_ALPACA_API_SECRET_KEY` | string | — | trading | Controls alpaca api secret key for trading. |
| `OMNIX_ALPACA_DATA_URL` | string | — | trading | Controls alpaca data url for trading. |
| `OMNIX_ALPACA_STATUS_STREAM` | string | `1` | trading | Controls alpaca status stream for trading. |
| `OMNIX_ALPACA_STREAM_URL` | string | `wss://stream.data.alpaca.markets/v2/iex` | trading | Controls alpaca stream url for trading. |
| `OMNIX_ALPACA_WS_PROXY` | string | — | trading | Controls alpaca ws proxy for trading. |
| `OMNIX_APPROVAL_SELF_ALLOWED_MAX_RISK` | string | — | capabilities | Controls approval self allowed max risk for capabilities. |
| `OMNIX_APP_OPEN_URL` | string | — | launcher | Controls app open url for launcher. |
| `OMNIX_APP_PRIVATE_URL` | string | — | launcher | Controls app private url for launcher. |
| `OMNIX_ASSETS_MANIFEST_PATH` | string | — | assets | Controls assets manifest path for assets. |
| `OMNIX_ASSISTANT_TOOLS_CONFIG_PATH` | string | — | assistant-tools | Controls assistant tools config path for assistant-tools. |
| `OMNIX_ASSISTANT_TOOLS_CONNECT_RETURN_URL` | string | `/chatbot` | assistant-tools | Controls assistant tools connect return url for assistant-tools. |
| `OMNIX_ASSISTANT_TOOLS_LEDGER_PATH` | string | — | assistant-tools | Controls assistant tools ledger path for assistant-tools. |
| `OMNIX_ASSISTANT_TOOLS_SKIP_LOCAL_ENV` | string | — | assistant-tools | Controls assistant tools skip local env for assistant-tools. |
| `OMNIX_ASSISTANT_TURN_STORE_PATH` | string | — | chat | Controls assistant turn store path for chat. |
| `OMNIX_AUDIOBOOK_CLASSIFICATION_LOG_PATH` | string | — | audiobook | Controls audiobook classification log path for audiobook. |
| `OMNIX_AUDIOBOOK_LOG_DIR` | string | — | audiobook | Controls audiobook log dir for audiobook. |
| `OMNIX_AUTH_COOKIE_SECURE` | boolean | `false` | security | Controls auth cookie secure for security. |
| `OMNIX_AUTH_MODE` | string | — | production.py, security | Controls auth mode for production.py, security. |
| `OMNIX_AUTH_SESSION_IDLE_HOURS` | integer | `12` | security | Controls auth session idle hours for security. |
| `OMNIX_AUTH_SESSION_MAX_DAYS` | integer | `7` | security | Controls auth session max days for security. |
| `OMNIX_AVATAR_GENERATION_LOG_PATH` | string | — | characters | Controls avatar generation log path for characters. |
| `OMNIX_BINANCE_FUTURES_WS_PROXY` | string | — | trading | Controls binance futures ws proxy for trading. |
| `OMNIX_BINANCE_WS_PROXY` | string | — | trading | Controls binance ws proxy for trading. |
| `OMNIX_BIND_HOST` | string | `127.0.0.1` | kernel | Controls bind host for kernel. |
| `OMNIX_BLOB_BACKEND` | string | `local` | kernel | Controls blob backend for kernel. |
| `OMNIX_BLOB_ROOT` | string | — | kernel | Controls blob root for kernel. |
| `OMNIX_BROWSER_EXE` | string | — | launcher | Controls browser exe for launcher. |
| `OMNIX_CHARACTER_CLOUD_SYNC_ENABLED` | boolean | — | tooling | Controls character cloud sync enabled for tooling. |
| `OMNIX_CHARACTER_HERMES_SYNC_ENABLED` | boolean | — | characters | Controls character hermes sync enabled for characters. |
| `OMNIX_CHARACTER_MEMORY_ENABLED` | boolean | — | characters | Controls character memory enabled for characters. |
| `OMNIX_CHARACTER_MODE_ENABLED` | string | — | characters, launcher | Controls character mode enabled for characters, launcher. |
| `OMNIX_CHARACTER_SHARED_MEMORY_ENABLED` | boolean | — | characters | Controls character shared memory enabled for characters. |
| `OMNIX_CHAT_COMPACTION_THRESHOLD` | string | `40` | chat | Controls chat compaction threshold for chat. |
| `OMNIX_CHAT_PROFILE_ID` | string | — | assistant-memory | Controls chat profile id for assistant-memory. |
| `OMNIX_CHAT_WORKSPACE_ID` | string | — | assistant-memory | Controls chat workspace id for assistant-memory. |
| `OMNIX_COMPANION_ROLLOUT_STAGE` | string | — | assistant-memory | Controls companion rollout stage for assistant-memory. |
| `OMNIX_DATABASE_APPLICATION_NAME` | string | `omnix` | kernel | Controls database application name for kernel. |
| `OMNIX_DATABASE_POOL_MAX` | string | — | kernel | Controls database pool max for kernel. |
| `OMNIX_DATABASE_URL` | string | — | kernel | Controls database url for kernel. |
| `OMNIX_DEEP_RESEARCH_HERMES_ENABLED` | string | `0` | research | Controls deep research hermes enabled for research. |
| `OMNIX_DEEP_RESEARCH_LOG_PATH` | string | — | research | Controls deep research log path for research. |
| `OMNIX_DEPLOYMENT_PROCESS_COUNTS` | string | — | kernel | Controls deployment process counts for kernel. |
| `OMNIX_DESKTOP_COMPANION_EVALUATION_PATH` | string | — | desktop-companion | Controls desktop companion evaluation path for desktop-companion. |
| `OMNIX_DEVICE_PERMIT_LEASE_SECONDS` | integer | `120` | kernel | Controls device permit lease seconds for kernel. |
| `OMNIX_DRAIN_MIN_SECONDS` | integer | `0` | kernel | Controls drain min seconds for kernel. |
| `OMNIX_DRAIN_SECONDS` | integer | `30` | kernel | Controls drain seconds for kernel. |
| `OMNIX_ENV` | string | `development` | gateway, kernel, production.py, security | Controls env for gateway, kernel, production.py, security. |
| `OMNIX_EOU_MODEL` | string | `nvidia/parakeet_realtime_eou_120m-v1` | providers | Controls eou model for providers. |
| `OMNIX_EOU_RIGHT_CONTEXT` | integer | `1` | providers | Controls eou right context for providers. |
| `OMNIX_EVENT_LOOP_LAG_MONITOR` | boolean | `1` | gateway | Controls event loop lag monitor for gateway. |
| `OMNIX_FFMPEG` | string | — | audiobook, tooling | Controls ffmpeg for audiobook, tooling. |
| `OMNIX_GATEWAY_BACKGROUND_ROLE` | string | `worker` | kernel | Controls gateway background role for kernel. |
| `OMNIX_GATEWAY_PORT` | string | — | gateway, kernel | Controls gateway port for gateway, kernel. |
| `OMNIX_GATEWAY_STARTUP_TIMEOUT_SECONDS` | string | — | launcher | Controls gateway startup timeout seconds for launcher. |
| `OMNIX_IBKR_CLIENT_ID` | string | — | trading | Controls ibkr client id for trading. |
| `OMNIX_IBKR_ENABLED` | string | — | trading | Controls ibkr enabled for trading. |
| `OMNIX_IBKR_HOST` | string | — | trading | Controls ibkr host for trading. |
| `OMNIX_IBKR_LIVE_AUTHORITY` | string | — | trading | Controls ibkr live authority for trading. |
| `OMNIX_IBKR_MONITOR` | string | — | trading | Controls ibkr monitor for trading. |
| `OMNIX_IBKR_MONITOR_IN_TESTS` | boolean | `0` | trading | Controls ibkr monitor in tests for trading. |
| `OMNIX_IBKR_PORT` | string | — | trading | Controls ibkr port for trading. |
| `OMNIX_IBKR_RECOVERY_AUTHORITY` | string | — | trading | Controls ibkr recovery authority for trading. |
| `OMNIX_IMAGE_ENABLED` | string | — | image, image-http-client.py, launcher | Controls image enabled for image, image-http-client.py, launcher. |
| `OMNIX_IMAGE_PRELOAD` | string | `0` | image-service-runtime.py, launcher | Controls image preload for image-service-runtime.py, launcher. |
| `OMNIX_IMAGE_PROVIDER` | string | — | image-service-runtime.py | Controls image provider for image-service-runtime.py. |
| `OMNIX_IMAGE_REQUIRE_EXPLICIT_LOAD` | string | `1` | image, image-service-runtime.py, launcher | Controls image require explicit load for image, image-service-runtime.py, launcher. |
| `OMNIX_IMAGE_SERVICE_MODE` | string | — | image, image-service-runtime.py | Controls image service mode for image, image-service-runtime.py. |
| `OMNIX_IMAGE_URL` | string | — | image-http-client.py | Controls image url for image-http-client.py. |
| `OMNIX_IMAGE_WARMUP` | string | `0` | image-service-runtime.py, launcher | Controls image warmup for image-service-runtime.py, launcher. |
| `OMNIX_INLINE_RESEARCH_JOB_EXECUTOR` | string | `1` | research | Controls inline research job executor for research. |
| `OMNIX_JOB_PRIORITY_AGING_SECONDS` | integer | `60` | kernel | Controls job priority aging seconds for kernel. |
| `OMNIX_JOB_WORKER_METRICS_HOST` | string | `127.0.0.1` | worker | Controls job worker metrics host for worker. |
| `OMNIX_JOB_WORKER_METRICS_PORT` | integer | `8090` | worker | Controls job worker metrics port for worker. |
| `OMNIX_JOB_WORKER_POOLS` | string | — | worker | Controls job worker pools for worker. |
| `OMNIX_JOB_WORKER_SHUTDOWN_GRACE_SECONDS` | integer | `30` | worker | Controls job worker shutdown grace seconds for worker. |
| `OMNIX_JOB_WORKER_STARTUP_TIMEOUT_SECONDS` | integer | `120` | worker | Controls job worker startup timeout seconds for worker. |
| `OMNIX_KASA_DEVICE_ALIAS` | string | — | assistant-tools | Controls kasa device alias for assistant-tools. |
| `OMNIX_KASA_DEVICE_HOST` | string | — | assistant-tools | Controls kasa device host for assistant-tools. |
| `OMNIX_KASA_ENABLED` | boolean | — | assistant-tools | Controls kasa enabled for assistant-tools. |
| `OMNIX_LAUNCHER_AUTO_START` | string | `0` | launcher | Controls launcher auto start for launcher. |
| `OMNIX_LAUNCHER_KILL_PORT` | boolean | `false` | tooling | Controls launcher kill port for tooling. |
| `OMNIX_LAUNCHER_PORT_RELEASE_TIMEOUT` | string | `8` | tooling | Controls launcher port release timeout for tooling. |
| `OMNIX_LAUNCHER_URL` | string | — | image-http-client.py | Controls launcher url for image-http-client.py. |
| `OMNIX_LEGACY_AUDIO_DIRS` | string | — | assets | Controls legacy audio dirs for assets. |
| `OMNIX_LEGACY_DOCUMENT_DIRS` | string | — | assets | Controls legacy document dirs for assets. |
| `OMNIX_LIVE_AGENT_AUTO_ROUTE_ENABLED` | boolean | — | hermes | Controls live agent auto route enabled for hermes. |
| `OMNIX_LIVE_AGENT_ENABLED` | boolean | — | hermes | Controls live agent enabled for hermes. |
| `OMNIX_LIVE_AGENT_REQUIRE_HERMES` | boolean | — | hermes | Controls live agent require hermes for hermes. |
| `OMNIX_LIVE_CHAT_EVALUATION_PATH` | string | — | chat | Controls live chat evaluation path for chat. |
| `OMNIX_LIVE_CONVERSATION_PROFILE_PATH` | string | — | characters | Controls live conversation profile path for characters. |
| `OMNIX_LIVE_GLOBAL_PROMPT_CACHE_TTL_SECONDS` | string | `60` | providers | Controls live global prompt cache ttl seconds for providers. |
| `OMNIX_LIVE_LMSTUDIO_STATEFUL_RESPONSES` | string | `true` | launcher | Controls live lmstudio stateful responses for launcher. |
| `OMNIX_LIVE_MAX_CALLS` | integer | — | kernel | Controls live max calls for kernel. |
| `OMNIX_LIVE_PRONUNCIATION_PATH` | string | — | characters | Controls live pronunciation path for characters. |
| `OMNIX_LIVE_TTS_PROVIDER_NAME` | string | — | kernel | Controls live tts provider name for kernel. |
| `OMNIX_LIVE_TTS_SPECULATIVE_CHUNK_STEPS` | string | `2` | launcher | Controls live tts speculative chunk steps for launcher. |
| `OMNIX_LIVE_VOICE_EXECUTION_MODE` | string | — | kernel | Controls live voice execution mode for kernel. |
| `OMNIX_LIVE_VOICE_MODEL_ID` | string | — | kernel | Controls live voice model id for kernel. |
| `OMNIX_LIVE_VOICE_PROVIDER_ID` | string | — | kernel | Controls live voice provider id for kernel. |
| `OMNIX_LOG_FORMAT` | string | `text` | observability | Controls log format for observability. |
| `OMNIX_LOG_LEVEL` | string | — | observability, worker | Controls log level for observability, worker. |
| `OMNIX_LOG_LEVELS` | string | — | observability | Controls log levels for observability. |
| `OMNIX_MEMORY_STRUCTURED_EXTRACTION_MODE` | string | — | assistant-memory | Controls memory structured extraction mode for assistant-memory. |
| `OMNIX_MEMORY_STRUCTURED_EXTRACTION_MODEL` | string | — | assistant-memory | Controls memory structured extraction model for assistant-memory. |
| `OMNIX_MEMORY_STRUCTURED_EXTRACTION_PROVIDER` | string | — | assistant-memory | Controls memory structured extraction provider for assistant-memory. |
| `OMNIX_MEMORY_STRUCTURED_EXTRACTION_TIMEOUT_SECONDS` | string | `8` | assistant-memory | Controls memory structured extraction timeout seconds for assistant-memory. |
| `OMNIX_MIGRATE_ON_START` | boolean | `false` | production.py | Controls migrate on start for production.py. |
| `OMNIX_MIGRATION_DATABASE_URL` | string | — | kernel | Controls migration database url for kernel. |
| `OMNIX_NEMOTRON_FINAL_RIGHT_CONTEXT` | integer | `13` | providers | Controls nemotron final right context for providers. |
| `OMNIX_NEMOTRON_MODEL` | string | `nvidia/nemotron-speech-streaming-en-0.6b` | providers | Controls nemotron model for providers. |
| `OMNIX_NEMOTRON_RIGHT_CONTEXT` | integer | `1` | providers | Controls nemotron right context for providers. |
| `OMNIX_OIDC_ALLOWED_DOMAINS` | list | — | security | Controls oidc allowed domains for security. |
| `OMNIX_OIDC_API_AUDIENCE` | string | — | security | Controls oidc api audience for security. |
| `OMNIX_OIDC_CLIENT_ID` | string | — | security | Controls oidc client id for security. |
| `OMNIX_OIDC_CLIENT_SECRET` | string | — | security | Controls oidc client secret for security. |
| `OMNIX_OIDC_DEFAULT_ROLE` | string | `member` | security | Controls oidc default role for security. |
| `OMNIX_OIDC_GROUPS_CLAIM` | string | `groups` | security | Controls oidc groups claim for security. |
| `OMNIX_OIDC_ISSUER` | string | — | security | Controls oidc issuer for security. |
| `OMNIX_OIDC_REDIRECT_URI` | string | — | security | Controls oidc redirect uri for security. |
| `OMNIX_OIDC_REQUIRED_GROUP` | string | — | security | Controls oidc required group for security. |
| `OMNIX_OIDC_SCOPES` | list | — | security | Controls oidc scopes for security. |
| `OMNIX_OIDC_WORKSPACE_ID` | string | `workspace:local` | security | Controls oidc workspace id for security. |
| `OMNIX_PERSISTENCE_MODE` | string | — | kernel, trading | Controls persistence mode for kernel, trading. |
| `OMNIX_PLAYWRIGHT_SEARCH_HEADLESS` | string | `1` | research | Controls playwright search headless for research. |
| `OMNIX_PRIVATE_BROWSER` | string | — | launcher | Controls private browser for launcher. |
| `OMNIX_PROVIDER_SECRETS_PATH` | string | — | security | Controls provider secrets path for security. |
| `OMNIX_REQUIRE_ROLE_SEPARATION` | boolean | `false` | kernel | Controls require role separation for kernel. |
| `OMNIX_RESEARCH_LEGACY_ALIASES_ENABLED` | string | `1` | research | Controls research legacy aliases enabled for research. |
| `OMNIX_RESEARCH_LEGACY_ALIAS_SUNSET` | string | — | research | Controls research legacy alias sunset for research. |
| `OMNIX_ROLE_PERMISSIONS` | string | — | security | Controls role permissions for security. |
| `OMNIX_RPG_DEBUG_LOGS` | string | `1` | rpg | Controls rpg debug logs for rpg. |
| `OMNIX_RPG_LOG_DIR` | string | — | rpg | Controls rpg log dir for rpg. |
| `OMNIX_RPG_LOG_MAX_FIELD_CHARS` | string | — | rpg | Controls rpg log max field chars for rpg. |
| `OMNIX_RPG_LOG_RETENTION_DAYS` | string | — | rpg | Controls rpg log retention days for rpg. |
| `OMNIX_RPG_SLOW_SPAN_MS` | string | — | rpg | Controls rpg slow span ms for rpg. |
| `OMNIX_RUN_TOKEN_KEY` | string | — | security | Controls run token key for security. |
| `OMNIX_S3_ACCESS_KEY_ID` | string | — | kernel | Controls s3 access key id for kernel. |
| `OMNIX_S3_BUCKET` | string | — | kernel | Controls s3 bucket for kernel. |
| `OMNIX_S3_ENDPOINT` | string | — | kernel | Controls s3 endpoint for kernel. |
| `OMNIX_S3_PREFIX` | string | — | kernel | Controls s3 prefix for kernel. |
| `OMNIX_S3_REGION` | string | `us-east-1` | kernel | Controls s3 region for kernel. |
| `OMNIX_S3_SECRET_ACCESS_KEY` | string | — | kernel | Controls s3 secret access key for kernel. |
| `OMNIX_S3_TIMEOUT_SECONDS` | integer | `60` | kernel | Controls s3 timeout seconds for kernel. |
| `OMNIX_SCHEDULER_PROCESS_WORKERS` | integer | `2` | kernel | Controls scheduler process workers for kernel. |
| `OMNIX_SCHEDULER_THREAD_WORKERS` | integer | `4` | kernel | Controls scheduler thread workers for kernel. |
| `OMNIX_SECRET_STORE` | string | — | security | Controls secret store for security. |
| `OMNIX_SECRET_STORE_PATH` | string | — | security | Controls secret store path for security. |
| `OMNIX_SERVICE_TOKEN` | string | — | security | Controls service token for security. |
| `OMNIX_SOFTWARE_REVISION` | string | — | kernel | Controls software revision for kernel. |
| `OMNIX_SSE_FLUSH_PREAMBLE_BYTES` | string | — | live-voice | Controls sse flush preamble bytes for live-voice. |
| `OMNIX_START_HERMES` | boolean | — | launcher | Controls start hermes for launcher. |
| `OMNIX_START_IMAGE_SERVICE` | string | — | launcher | Controls start image service for launcher. |
| `OMNIX_STT_DEVICE` | string | `auto` | providers | Controls stt device for providers. |
| `OMNIX_STT_PORT` | integer | `5201` | tooling | Controls stt port for tooling. |
| `OMNIX_STT_STREAM_CHUNK_MS` | integer | `160` | providers | Controls stt stream chunk ms for providers. |
| `OMNIX_STT_URL` | string | `http://127.0.0.1:5201` | launcher | Controls stt url for launcher. |
| `OMNIX_TIMEZONE` | string | `UTC` | assistant-tools | Controls timezone for assistant-tools. |
| `OMNIX_TRADE_AUDIT_LOGGING` | string | `1` | trading | Controls trade audit logging for trading. |
| `OMNIX_TRADE_LOG_DIR` | string | — | trading | Controls trade log dir for trading. |
| `OMNIX_TRADING_AI_SHADOW_CIRCUIT_PERSISTENCE` | string | `1` | trading | Controls trading ai shadow circuit persistence for trading. |
| `OMNIX_TRADING_AI_SHADOW_MONITOR` | boolean | `1` | trading | Controls trading ai shadow monitor for trading. |
| `OMNIX_TRADING_AI_SHADOW_MONITOR_IN_TESTS` | boolean | `0` | trading | Controls trading ai shadow monitor in tests for trading. |
| `OMNIX_TRADING_AI_SHADOW_V2_MONITOR` | boolean | `1` | trading | Controls trading ai shadow v2 monitor for trading. |
| `OMNIX_TRADING_AI_SHADOW_V2_MONITOR_IN_TESTS` | boolean | `0` | trading | Controls trading ai shadow v2 monitor in tests for trading. |
| `OMNIX_TRADING_AI_SHADOW_V3_MONITOR` | boolean | `1` | trading | Controls trading ai shadow v3 monitor for trading. |
| `OMNIX_TRADING_AI_SHADOW_V3_MONITOR_IN_TESTS` | boolean | `0` | trading | Controls trading ai shadow v3 monitor in tests for trading. |
| `OMNIX_TRADING_ALERT_INTERVAL_SECONDS` | string | `30` | trading | Controls trading alert interval seconds for trading. |
| `OMNIX_TRADING_ALERT_MONITOR` | boolean | `1` | trading | Controls trading alert monitor for trading. |
| `OMNIX_TRADING_ALERT_MONITOR_IN_TESTS` | boolean | `0` | trading | Controls trading alert monitor in tests for trading. |
| `OMNIX_TRADING_DEEP_RECOVERY_SHADOW_MONITOR` | boolean | `1` | trading | Controls trading deep recovery shadow monitor for trading. |
| `OMNIX_TRADING_DEEP_RECOVERY_SHADOW_MONITOR_IN_TESTS` | boolean | `0` | trading | Controls trading deep recovery shadow monitor in tests for trading. |
| `OMNIX_TRADING_DYNAMIC_DISCOVERY` | boolean | `1` | trading | Controls trading dynamic discovery for trading. |
| `OMNIX_TRADING_DYNAMIC_DISCOVERY_IN_TESTS` | boolean | `0` | trading | Controls trading dynamic discovery in tests for trading. |
| `OMNIX_TRADING_EXECUTION_OBSERVATION_INTERVAL_SECONDS` | string | `3` | trading | Controls trading execution observation interval seconds for trading. |
| `OMNIX_TRADING_EXECUTION_OBSERVATION_MONITOR` | boolean | `1` | trading | Controls trading execution observation monitor for trading. |
| `OMNIX_TRADING_EXECUTION_OBSERVATION_MONITOR_IN_TESTS` | boolean | `0` | trading | Controls trading execution observation monitor in tests for trading. |
| `OMNIX_TRADING_EXECUTION_OBSERVATION_WORKERS` | string | `8` | trading | Controls trading execution observation workers for trading. |
| `OMNIX_TRADING_FINVIZ_SHADOW_ACCOUNT_ID` | string | — | trading | Controls trading finviz shadow account id for trading. |
| `OMNIX_TRADING_FINVIZ_SHADOW_AUTOPROVISION` | boolean | `1` | trading | Controls trading finviz shadow autoprovision for trading. |
| `OMNIX_TRADING_FINVIZ_SHADOW_AUTOPROVISION_IN_TESTS` | boolean | `0` | trading | Controls trading finviz shadow autoprovision in tests for trading. |
| `OMNIX_TRADING_FINVIZ_SHADOW_INITIAL_CASH` | string | `1000` | trading | Controls trading finviz shadow initial cash for trading. |
| `OMNIX_TRADING_HERMES_RESEARCH_ENABLED` | string | — | launcher | Controls trading hermes research enabled for launcher. |
| `OMNIX_TRADING_IBKR_EVIDENCE_DIR` | string | — | trading | Controls trading ibkr evidence dir for trading. |
| `OMNIX_TRADING_INTERDAY_LEARNING` | boolean | `1` | trading | Controls trading interday learning for trading. |
| `OMNIX_TRADING_INTERDAY_LEARNING_IN_TESTS` | boolean | `0` | trading | Controls trading interday learning in tests for trading. |
| `OMNIX_TRADING_LIQUIDATION_COLLECTOR` | boolean | `1` | trading | Controls trading liquidation collector for trading. |
| `OMNIX_TRADING_LIQUIDATION_COLLECTOR_IN_TESTS` | boolean | `0` | trading | Controls trading liquidation collector in tests for trading. |
| `OMNIX_TRADING_PAPER_ACTIVE_INTERVAL_SECONDS` | string | `1` | trading | Controls trading paper active interval seconds for trading. |
| `OMNIX_TRADING_PAPER_INTERVAL_SECONDS` | string | `15` | trading | Controls trading paper interval seconds for trading. |
| `OMNIX_TRADING_PAPER_MONITOR` | boolean | `1` | trading | Controls trading paper monitor for trading. |
| `OMNIX_TRADING_PAPER_MONITOR_IN_TESTS` | boolean | `0` | trading | Controls trading paper monitor in tests for trading. |
| `OMNIX_TRADING_PROSPECTIVE_ECONOMIC_MONITOR` | boolean | `1` | trading | Controls trading prospective economic monitor for trading. |
| `OMNIX_TRADING_PROSPECTIVE_ECONOMIC_MONITOR_IN_TESTS` | boolean | `0` | trading | Controls trading prospective economic monitor in tests for trading. |
| `OMNIX_TRADING_PROSPECTIVE_GAP_GITHUB_REF` | string | `main` | trading | Controls trading prospective gap github ref for trading. |
| `OMNIX_TRADING_PROSPECTIVE_GAP_GITHUB_REPOSITORY` | string | `autonomx/omnix` | trading | Controls trading prospective gap github repository for trading. |
| `OMNIX_TRADING_PROSPECTIVE_GAP_MONITOR` | boolean | `1` | trading | Controls trading prospective gap monitor for trading. |
| `OMNIX_TRADING_PROSPECTIVE_GAP_MONITOR_IN_TESTS` | boolean | `0` | trading | Controls trading prospective gap monitor in tests for trading. |
| `OMNIX_TRADING_PROSPECTIVE_GAP_REMOTE_INBOX` | string | `1` | trading | Controls trading prospective gap remote inbox for trading. |
| `OMNIX_TRADING_RESEARCH_MAX_REPORTS_PER_CANDIDATE_DAY` | integer | `3` | trading | Controls trading research max reports per candidate day for trading. |
| `OMNIX_TRADING_RESEARCH_MONITOR` | boolean | `1` | trading | Controls trading research monitor for trading. |
| `OMNIX_TRADING_RESEARCH_MONITOR_INTERVAL_SECONDS` | string | `60` | trading | Controls trading research monitor interval seconds for trading. |
| `OMNIX_TRADING_RESEARCH_MONITOR_IN_TESTS` | boolean | `0` | trading | Controls trading research monitor in tests for trading. |
| `OMNIX_TRADING_RESEARCH_OUTCOME_MONITOR` | boolean | `1` | trading | Controls trading research outcome monitor for trading. |
| `OMNIX_TRADING_RESEARCH_OUTCOME_MONITOR_IN_TESTS` | boolean | `0` | trading | Controls trading research outcome monitor in tests for trading. |
| `OMNIX_TRADING_RESEARCH_UNRESOLVED_RETRY_SECONDS` | integer | `300` | trading | Controls trading research unresolved retry seconds for trading. |
| `OMNIX_TRADING_SESSION_RECONCILIATION_MONITOR` | boolean | `1` | trading | Controls trading session reconciliation monitor for trading. |
| `OMNIX_TRADING_SESSION_RECONCILIATION_MONITOR_IN_TESTS` | boolean | `0` | trading | Controls trading session reconciliation monitor in tests for trading. |
| `OMNIX_TRADING_SOLANA_AI_MONITOR` | boolean | `0` | trading | Controls trading solana ai monitor for trading. |
| `OMNIX_TRADING_SOLANA_AI_MONITOR_IN_TESTS` | boolean | `0` | trading | Controls trading solana ai monitor in tests for trading. |
| `OMNIX_TRADING_STRATEGY_MONITOR` | boolean | `1` | trading | Controls trading strategy monitor for trading. |
| `OMNIX_TRADING_STRATEGY_MONITOR_IN_TESTS` | boolean | `0` | trading | Controls trading strategy monitor in tests for trading. |
| `OMNIX_TRADING_UNIVERSE_ARCHIVER` | boolean | `1` | trading | Controls trading universe archiver for trading. |
| `OMNIX_TRADING_UNIVERSE_ARCHIVER_INTERVAL_SECONDS` | string | `30` | trading | Controls trading universe archiver interval seconds for trading. |
| `OMNIX_TRADING_UNIVERSE_ARCHIVER_IN_TESTS` | boolean | `0` | trading | Controls trading universe archiver in tests for trading. |
| `OMNIX_TRADING_V2_QUALIFICATION` | boolean | `1` | trading | Controls trading v2 qualification for trading. |
| `OMNIX_TRADING_V2_QUALIFICATION_IN_TESTS` | boolean | `0` | trading | Controls trading v2 qualification in tests for trading. |
| `OMNIX_TRADING_YAHOO_ACQUISITION` | boolean | `1` | trading | Controls trading yahoo acquisition for trading. |
| `OMNIX_TRADING_YAHOO_ACQUISITION_INTERVAL_SECONDS` | string | `30` | trading | Controls trading yahoo acquisition interval seconds for trading. |
| `OMNIX_TRADING_YAHOO_ACQUISITION_IN_TESTS` | boolean | `0` | trading | Controls trading yahoo acquisition in tests for trading. |
| `OMNIX_TRADING_YAHOO_EVIDENCE_DIR` | string | — | trading | Controls trading yahoo evidence dir for trading. |
| `OMNIX_TTS_MODEL_DIR` | string | — | launcher | Controls tts model dir for launcher. |
| `OMNIX_TTS_PORT` | integer | `5101` | tooling | Controls tts port for tooling. |
| `OMNIX_TTS_STARTUP_WARMUP` | string | — | voice | Controls tts startup warmup for voice. |
| `OMNIX_TTS_SYNTHESIS_WORKERS` | integer | `8` | tooling | Controls tts synthesis workers for tooling. |
| `OMNIX_TTS_URL` | string | `http://127.0.0.1:5101` | launcher | Controls tts url for launcher. |
| `OMNIX_TTS_WARMUP_SPEAKER` | string | — | voice | Controls tts warmup speaker for voice. |
| `OMNIX_VISION_API_KEY` | string | — | assistant-context | Controls vision api key for assistant-context. |
| `OMNIX_VISION_BASE_URL` | string | — | assistant-context | Controls vision base url for assistant-context. |
| `OMNIX_VISION_MODEL` | string | — | assistant-context | Controls vision model for assistant-context. |
| `OMNIX_VISION_PROVIDER` | string | — | assistant-context | Controls vision provider for assistant-context. |
| `OMNIX_VISION_TIMEOUT_SECONDS` | string | `25.0` | assistant-context | Controls vision timeout seconds for assistant-context. |
| `OMNIX_VISUAL_PROVIDER` | string | — | rpg | Controls visual provider for rpg. |
| `OMNIX_VOICE_CLONES_DIR` | string | — | assets | Controls voice clones dir for assets. |
| `OMNIX_VOICE_CLONES_FILE` | string | — | assets | Controls voice clones file for assets. |
| `OMNIX_VOICE_DEBUG_LOGGING` | string | `1` | voice-debug.py | Controls voice debug logging for voice-debug.py. |
| `OMNIX_VOICE_DEBUG_LOG_DIR` | string | — | voice-debug.py | Controls voice debug log dir for voice-debug.py. |
| `OMNIX_WEB_SEARCH_API_KEY` | string | — | research, security | Controls web search api key for research, security. |
| `OMNIX_WEB_SEARCH_PROVIDER` | string | — | research, security | Controls web search provider for research, security. |
| `OMNIX_WEB_SEARCH_TIMEOUT_SECONDS` | string | `8.0` | research | Controls web search timeout seconds for research. |
| `PARAKEET_LIVE_EDGE_PADDING_MS` | integer | `100` | providers | Controls parakeet live edge padding ms for providers. |
| `PARAKEET_LIVE_MAX_QUEUED_SEGMENTS` | integer | `32` | providers | Controls parakeet live max queued segments for providers. |
| `PARAKEET_LIVE_MAX_SESSION_SEGMENTS` | integer | `8` | providers | Controls parakeet live max session segments for providers. |
| `PARAKEET_LIVE_TRIM_DBFS` | number | — | providers | Controls parakeet live trim dbfs for providers. |
| `PARAKEET_WARMUP_SECONDS` | number | `0.75` | providers | Controls parakeet warmup seconds for providers. |
| `PATH` | string | — | agent-runtime | Controls path for agent-runtime. |
| `PROGRAMFILES` | string | — | launcher | Controls programfiles for launcher. |
| `PYTEST_CURRENT_TEST` | string | — | kernel | Controls pytest current test for kernel. |
| `PYTHONPATH` | string | — | rpg | Controls pythonpath for rpg. |
| `RPG_TRACE_PROVIDER_CALLS` | string | — | providers | Controls rpg trace provider calls for providers. |
| `RPG_TRACE_SESSION_TURN` | string | — | rpg | Controls rpg trace session turn for rpg. |
| `SYSTEMROOT` | string | — | agent-runtime | Controls systemroot for agent-runtime. |
| `VITE_ASSISTANT_STT_URL` | string | `/api/stt?language=en&authority=auto&endpoint_threshold=0.5` | launcher | Controls vite assistant stt url for launcher. |
| `VITE_LIVE_SPECULATION_ENABLED` | string | `true` | launcher | Controls vite live speculation enabled for launcher. |
| `VITE_LIVE_TTS_ADAPTIVE_BUFFER` | string | `true` | launcher | Controls vite live tts adaptive buffer for launcher. |
