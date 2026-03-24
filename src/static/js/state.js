window.VoiceState = {
    recording: false,
    assistantSpeaking: false,
    sttStreaming: false,
    sttFinalizing: false,
    llmStreaming: false,
    interruptRequested: false,

    speechStartTime: 0,
    lastAudioFrameTime: 0,

    tokenBuffer: "",
    partialTranscript: "",

    websocketReady: false
};
