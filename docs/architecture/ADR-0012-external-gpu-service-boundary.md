# ADR 0012: External GPU service boundary

Status: accepted.

API replicas never construct local Qwen/CUDA TTS. When configured they use the existing HTTP TTS provider; otherwise speech stays worker-routed. A worker can use local TTS or the same remote endpoint. STT/image services retain their existing external interfaces.

Runtime configuration validates endpoints and required-service policy once. Provider refresh and delivery queues remain bounded and observable. Only explicitly required services block readiness. This prevents each API replica loading another GPU model while preserving the existing provider system. CPU transport certification complements deployment-specific GPU soak measurements.
