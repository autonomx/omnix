export const SPEECH_PERFORMANCE_SCHEMA_VERSION = 1 as const;

export type SpeechAct =
  | 'acknowledgement'
  | 'answer'
  | 'question'
  | 'reassurance'
  | 'reflection'
  | 'instruction';
export type DeliveryLevel = 'low' | 'moderate' | 'high';
export type DeliveryPace = 'slightly_slow' | 'natural' | 'slightly_fast';
export type ClausePause = 'short' | 'medium' | 'long';

export type SpeechPerformancePlan = {
  schema_version: typeof SPEECH_PERFORMANCE_SCHEMA_VERSION;
  speech_act: SpeechAct;
  energy: DeliveryLevel;
  warmth: DeliveryLevel;
  certainty: DeliveryLevel;
  pace: DeliveryPace;
  clause_pause: ClausePause;
  emphasis: string[];
  onset_policy: {
    desired_perceived_onset_ms: number;
    maximum_additional_delay_ms: number;
  };
  nonverbal_eligibility: {
    breath: boolean;
    acknowledgement: boolean;
    amused_exhale: boolean;
    sigh: boolean;
  };
};

export type TtsProviderCapabilities = {
  provider: string;
  supports_streaming: boolean;
  supports_concurrent_generation: boolean;
  supports_emotion: boolean;
  supports_speaking_rate: boolean;
  supports_word_emphasis: boolean;
  supports_ssml: boolean;
  supports_word_timestamps: boolean;
};

export const FASTER_QWEN3_TTS_CAPABILITIES: TtsProviderCapabilities = {
  provider: 'faster_qwen3_tts',
  supports_streaming: true,
  supports_concurrent_generation: false,
  supports_emotion: false,
  supports_speaking_rate: false,
  supports_word_emphasis: false,
  supports_ssml: false,
  supports_word_timestamps: false,
};

export type TtsPronunciationHint = {
  phrase: string;
  pronunciation: string;
  locale?: string;
};

export type SpeechSynthesisOptions = {
  performancePlan?: SpeechPerformancePlan;
  pronunciationLexicon?: TtsPronunciationHint[];
};
