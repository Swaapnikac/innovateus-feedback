"use client";

import { useState, useRef, useCallback, useEffect, forwardRef, useImperativeHandle } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Mic, Square, Check, CheckCircle2, Loader2, Volume2, RotateCcw, Sparkles, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import {
  trackAudioCaptureError,
  trackMicPermission,
  trackTranscriptEdited,
  trackVoiceRecordingStarted,
  trackVoiceRecordingStopped,
} from "@/lib/analytics";
import { MAX_ANSWER_CHARS, MAX_VOICE_RECORDING_MS } from "@/lib/limits";
import { detectPii, stripPii, summarisePii } from "@/lib/pii";

interface VoiceRecorderProps {
  onTranscriptComplete: (transcript: string) => void;
  initialTranscript?: string;
  onRecordingStarted?: () => void;
  questionId?: string;
}

export interface VoiceRecorderHandle {
  /** Stop any active recording and return whatever transcript text is
   * currently displayed (confirmed, enhanced, raw, or live). Used when the
   * parent is about to unmount the recorder — e.g. the user is switching
   * from voice to text mid-recording. */
  flushCurrentTranscript: () => string;
}

interface SpeechRecognitionEvent {
  results: SpeechRecognitionResultList;
  resultIndex: number;
}

interface SpeechRecognitionErrorEvent {
  error: string;
}

// Silence-based auto-stop for the Web Speech API path. Only used when the
// browser gives us speech events we can debounce on.
const SPEECH_API_INACTIVITY_MS = 15000;

export const VoiceRecorder = forwardRef<VoiceRecorderHandle, VoiceRecorderProps>(function VoiceRecorder(
  { onTranscriptComplete, initialTranscript = "", onRecordingStarted, questionId },
  ref,
) {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isEnhancing, setIsEnhancing] = useState(false);
  const [transcript, setTranscript] = useState(initialTranscript);
  const [rawTranscript, setRawTranscript] = useState("");
  const [enhancedTranscript, setEnhancedTranscript] = useState("");
  const [wasEnhanced, setWasEnhanced] = useState(false);
  const [showingOriginal, setShowingOriginal] = useState(false);
  const [liveTranscript, setLiveTranscript] = useState("");
  const [hasRecorded, setHasRecorded] = useState(!!initialTranscript);
  // Always start unconfirmed — even when we're seeded with an initialTranscript
  // (mode switch round-trip, review edit, or survey resume). The parent tracks
  // the real "committed" state; the recorder's confirmed flag is only the
  // button's transient visual state, which any textarea edit already resets.
  const [confirmed, setConfirmed] = useState(false);
  const [recorderError, setRecorderError] = useState<string>("");
  // F4: notice surfaced when the backend strips PII from the Whisper transcript
  // so the user understands why something they said isn't showing up.
  const [piiNotice, setPiiNotice] = useState<string>("");
  // Toast shown when we auto-stop at the MAX_VOICE_RECORDING_MS hard cap so
  // the user knows the recorder didn't break — they just hit the time limit.
  const [durationNotice, setDurationNotice] = useState<string>("");

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const recognitionRef = useRef<any>(null);
  const isRecordingRef = useRef(false);
  // B6: Guard against double-entry while getUserMedia is pending.
  const startingRef = useRef(false);
  const inactivityTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Separate from the inactivity timer so it always fires at
  // MAX_VOICE_RECORDING_MS regardless of ongoing speech. This is the hard cap.
  const maxDurationTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const finalTranscriptRef = useRef("");
  const recordingStartedAtRef = useRef<number | null>(null);
  const stopReasonRef = useRef<
    "user_stop" | "silence_timeout" | "max_duration" | "error" | "unmount"
  >("user_stop");
  // Whether the current ``startRecording`` run wired up Web Speech API. When
  // false, we never touch the short inactivity timer (B5 fix — otherwise the
  // recorder auto-stops at 15s on Firefox/Safari without any speech events
  // to refresh the timer).
  const hasSpeechRecognitionRef = useRef(false);
  // C8: no-op state updates once the component has unmounted — otherwise the
  // async ``mediaRecorder.onstop`` can fire after unmount and trigger the
  // "state update on unmounted component" React warning.
  const isMountedRef = useRef(true);
  const qId = questionId || "unknown";

  const safeSet = useCallback(<T,>(setter: (v: T) => void, value: T) => {
    if (isMountedRef.current) setter(value);
  }, []);

  const enhanceTranscript = useCallback(async (raw: string) => {
    if (!raw.trim()) return;
    safeSet(setRawTranscript, raw);
    safeSet(setTranscript, raw);
    safeSet(setHasRecorded, true);
    safeSet(setConfirmed, false);
    safeSet(setLiveTranscript, "");
    safeSet(setWasEnhanced, false);
    safeSet(setShowingOriginal, false);

    safeSet(setIsEnhancing, true);
    try {
      const result = await api.cleanupTranscript(raw);
      if (result.changed && result.cleaned.trim()) {
        safeSet(setEnhancedTranscript, result.cleaned);
        safeSet(setTranscript, result.cleaned);
        safeSet(setWasEnhanced, true);
      }
    } catch {
      // Cleanup failed silently, raw transcript remains.
    } finally {
      safeSet(setIsEnhancing, false);
    }
  }, [safeSet]);

  const toggleOriginal = () => {
    const next = !showingOriginal;
    setShowingOriginal(next);
    setTranscript(next ? rawTranscript : enhancedTranscript);
  };

  const resetInactivityTimer = useCallback(() => {
    if (inactivityTimerRef.current) {
      clearTimeout(inactivityTimerRef.current);
    }
    // Silence-based auto-stop only runs on the Web Speech path — non-Web-Speech
    // browsers have no onresult events to refresh the timer, so the silence
    // timer would fire mid-speech. The 60s max-duration timer (armed in
    // startRecording) still covers that path.
    if (!hasSpeechRecognitionRef.current) return;
    inactivityTimerRef.current = setTimeout(() => {
      stopReasonRef.current = "silence_timeout";
      stopRecording();
    }, SPEECH_API_INACTIVITY_MS);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const stopRecording = useCallback(() => {
    const wasRecording = isRecordingRef.current;
    isRecordingRef.current = false;

    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch {}
      recognitionRef.current = null;
    }

    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop();
    }

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }

    if (inactivityTimerRef.current) {
      clearTimeout(inactivityTimerRef.current);
      inactivityTimerRef.current = null;
    }
    if (maxDurationTimerRef.current) {
      clearTimeout(maxDurationTimerRef.current);
      maxDurationTimerRef.current = null;
    }

    safeSet(setIsRecording, false);

    if (wasRecording && recordingStartedAtRef.current) {
      const durationSec = (Date.now() - recordingStartedAtRef.current) / 1000;
      try {
        trackVoiceRecordingStopped(qId, durationSec, stopReasonRef.current);
      } catch {
        // ignore
      }
      recordingStartedAtRef.current = null;

      // Surface the auto-stop reason so the user understands why we cut
      // them off instead of silently dropping their audio.
      if (stopReasonRef.current === "max_duration") {
        const capLabel =
          MAX_VOICE_RECORDING_MS >= 60_000
            ? `${Math.round(MAX_VOICE_RECORDING_MS / 60_000)} minutes`
            : `${Math.round(MAX_VOICE_RECORDING_MS / 1_000)} seconds`;
        safeSet(
          setDurationNotice,
          `Recording stopped at ${capLabel} — please keep answers short and focused.`,
        );
      }

      stopReasonRef.current = "user_stop";
    }
  }, [qId, safeSet]);

  const startRecording = async () => {
    // B6: Prevent double-entry from a fast second click or stale onclick
    // handler. Otherwise two getUserMedia() calls race and the first stream
    // is orphaned (mic stays hot).
    if (isRecordingRef.current || startingRef.current) return;
    startingRef.current = true;
    setRecorderError("");
    setDurationNotice("");
    // Defensive reset: wipe any stale PII notice from a previous recording
    // so the yellow box reflects the *current* utterance. Without this, if
    // the user records PII once and then re-records clean audio, the
    // stale notice would keep the yellow box visible on the clean run.
    setPiiNotice("");

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      trackMicPermission("granted");
    } catch (err) {
      const e = err as DOMException | Error;
      const name = (e as DOMException).name || "MicError";
      const message = (e as Error).message || String(e);
      if (name === "NotAllowedError" || name === "SecurityError" || name === "PermissionDeniedError") {
        trackMicPermission("denied", { error_name: name });
      } else {
        trackMicPermission("unknown", { error_name: name });
      }
      trackAudioCaptureError(qId, name, message);
      setRecorderError(
        "Couldn't access your microphone. Check your browser's site permissions, or switch to text input below."
      );
      startingRef.current = false;
      return;
    }

    try {
      streamRef.current = stream;

      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
          ? "audio/webm;codecs=opus"
          : "audio/webm",
      });

      chunksRef.current = [];
      mediaRecorderRef.current = mediaRecorder;
      finalTranscriptRef.current = "";
      setLiveTranscript("");

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const currentTranscript = finalTranscriptRef.current.trim();

        // If Web Speech already produced a final transcript, skip the server
        // round-trip — use it directly. Run the client-side PII stripper
        // first so raw Chrome/Edge transcripts don't leak PII via the
        // "Show original" toggle (the Whisper path is already server-redacted).
        if (currentTranscript) {
          const stripped = stripPii(currentTranscript);
          if (stripped.count > 0) {
            const cats = stripped.categories.join(", ");
            safeSet(
              setPiiNotice,
              cats
                ? `We removed some personal info from your recording (${cats}). Please keep your feedback focused on your experience.`
                : "We removed some personal info from your recording. Please keep your feedback focused on your experience.",
            );
          } else {
            safeSet(setPiiNotice, "");
          }
          if (isMountedRef.current) enhanceTranscript(stripped.text);
          return;
        }

        const audioBlob = new Blob(chunksRef.current, { type: "audio/webm" });
        chunksRef.current = [];

        // C7: drop the threshold from 1000 bytes to 200 so tiny utterances
        // ("yes", "no", single word answers) are still sent to Whisper. If
        // Whisper returns empty, we surface a retry instead of silently
        // dropping the recording.
        if (audioBlob.size > 200) {
          safeSet(setIsTranscribing, true);
          try {
            const result = await api.transcribe(audioBlob);
            safeSet(setIsTranscribing, false);
            if (!isMountedRef.current) return;
            if (result.pii_redaction_applied) {
              const cats = (result.pii_redaction_categories || []).join(", ");
              safeSet(
                setPiiNotice,
                cats
                  ? `We removed some personal info from your recording (${cats}). Please keep your feedback focused on your experience.`
                  : "We removed some personal info from your recording. Please keep your feedback focused on your experience.",
              );
            } else {
              safeSet(setPiiNotice, "");
            }
            if (result.transcript && result.transcript.trim()) {
              enhanceTranscript(result.transcript);
            } else {
              // Whisper returned nothing — give the user a clear next step.
              safeSet(
                setRecorderError,
                "We didn't catch any speech. Please try again, or switch to text input below.",
              );
              safeSet(setTranscript, "");
              safeSet(setLiveTranscript, "");
            }
          } catch (err) {
            // C5: surface transcription errors instead of silently continuing
            // with an empty transcript (which caused answers to disappear).
            safeSet(setIsTranscribing, false);
            if (!isMountedRef.current) return;
            const message = err instanceof Error ? err.message : "unknown";
            trackAudioCaptureError(qId, "TranscribeFailed", message);
            safeSet(
              setRecorderError,
              "Sorry — we couldn't transcribe that recording. Please try again, or switch to text input below.",
            );
            safeSet(setTranscript, "");
            safeSet(setLiveTranscript, "");
          }
        } else {
          // Sub-200-byte audio = basically silence. Tell the user.
          safeSet(
            setRecorderError,
            "The recording was too short. Please speak for a little longer, or switch to text input below.",
          );
          safeSet(setTranscript, "");
          safeSet(setLiveTranscript, "");
        }
      };

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const w = window as any;
      const SpeechRecognitionClass = w.SpeechRecognition || w.webkitSpeechRecognition;
      hasSpeechRecognitionRef.current = !!SpeechRecognitionClass;

      if (SpeechRecognitionClass) {
        const recognition = new SpeechRecognitionClass();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = "en-US";

        recognition.onresult = (event: SpeechRecognitionEvent) => {
          let interim = "";
          let final = "";

          for (let i = 0; i < event.results.length; i++) {
            const result = event.results[i];
            if (result.isFinal) {
              final += result[0].transcript + " ";
            } else {
              interim += result[0].transcript;
            }
          }

          if (final) {
            finalTranscriptRef.current = final.trim();
          }

          setLiveTranscript((final + interim).trim());
          resetInactivityTimer();
        };

        recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
          if (event.error !== "aborted") {
            console.warn("Speech recognition error:", event.error);
          }
        };

        recognition.onend = () => {
          if (isRecordingRef.current && recognitionRef.current) {
            try { recognitionRef.current.start(); } catch {}
          }
        };

        recognitionRef.current = recognition;
        recognition.start();
      }

      mediaRecorder.start(1000);
      isRecordingRef.current = true;
      setIsRecording(true);
      recordingStartedAtRef.current = Date.now();
      stopReasonRef.current = "user_stop";
      try { trackVoiceRecordingStarted(qId); } catch {}
      onRecordingStarted?.();
      resetInactivityTimer();
      // Hard cap that fires regardless of browser-speech support.
      if (maxDurationTimerRef.current) clearTimeout(maxDurationTimerRef.current);
      maxDurationTimerRef.current = setTimeout(() => {
        stopReasonRef.current = "max_duration";
        stopRecording();
      }, MAX_VOICE_RECORDING_MS);
    } catch (err) {
      const e = err as Error;
      stopReasonRef.current = "error";
      trackAudioCaptureError(qId, "SetupError", e?.message || String(e));
      setRecorderError(
        "Something went wrong starting the recording. Please try again or switch to text input below.",
      );
      // Clean up any partial stream so the mic light turns off.
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }
    } finally {
      startingRef.current = false;
    }
  };

  const handleDone = () => {
    setConfirmed(true);
    const source = wasEnhanced ? enhancedTranscript : rawTranscript;
    const originalLen = (source || "").length;
    const finalLen = (transcript || "").length;
    if (source && source !== transcript) {
      const edit = Math.abs(finalLen - originalLen);
      try { trackTranscriptEdited(qId, originalLen, finalLen, edit); } catch {}
    }
    onTranscriptComplete(transcript);
  };

  // When the Web Speech path is active, ``mediaRecorder.onstop`` takes a
  // shortcut and skips the server round-trip — so ``pii_redaction_applied``
  // from the backend never fires. Run the client-side regex detector on the
  // live transcript as it grows so the amber banner still fires (and the
  // user still sees the warning when they stop recording). For non-Web-Speech
  // browsers, ``liveTranscript`` stays empty and this effect no-ops.
  useEffect(() => {
    if (!liveTranscript) return;
    const matches = detectPii(liveTranscript);
    if (matches.length === 0) return;
    const summary = summarisePii(matches);
    safeSet(
      setPiiNotice,
      `Heads up — ${summary} looked like personal information and will be removed before saving.`,
    );
  }, [liveTranscript, safeSet]);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (inactivityTimerRef.current) clearTimeout(inactivityTimerRef.current);
      if (maxDurationTimerRef.current) clearTimeout(maxDurationTimerRef.current);
      if (recognitionRef.current) {
        try { recognitionRef.current.stop(); } catch {}
      }
      if (mediaRecorderRef.current?.state === "recording") {
        mediaRecorderRef.current.stop();
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
      }
    };
  }, []);

  // B7: expose a flushCurrentTranscript() that stops any live recording
  // gracefully and returns whatever text we have (confirmed transcript,
  // enhanced/raw transcript, or interim live transcript). Parent components
  // call this right before switching from voice → text so the in-flight
  // work is not lost on unmount.
  useImperativeHandle(ref, () => ({
    flushCurrentTranscript: () => {
      const preferred =
        (transcript && transcript.trim()) ||
        (enhancedTranscript && enhancedTranscript.trim()) ||
        (rawTranscript && rawTranscript.trim()) ||
        finalTranscriptRef.current ||
        (liveTranscript && liveTranscript.trim()) ||
        "";

      if (isRecordingRef.current) {
        stopReasonRef.current = "user_stop";
        stopRecording();
      }
      return preferred;
    },
  }), [transcript, enhancedTranscript, rawTranscript, liveTranscript, stopRecording]);

  const isBusy = isTranscribing || isEnhancing;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        {!isRecording ? (
          <Button
            type="button"
            onClick={startRecording}
            disabled={isBusy}
            size="lg"
            className="gap-2 bg-brand-blue hover:bg-brand-blue/90 text-base"
          >
            <Mic className="h-5 w-5" />
            {hasRecorded ? "Record Again" : "Start Recording"}
          </Button>
        ) : (
          <Button
            type="button"
            onClick={stopRecording}
            size="lg"
            variant="destructive"
            className="gap-2 text-base"
          >
            <Square className="h-5 w-5" />
            Stop Recording
          </Button>
        )}

        {isBusy && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            {/* Two-phase indicator so the ~2s total wait feels like two quick
                steps instead of one opaque spinner. */}
            {isTranscribing ? "Transcribing audio…" : "Polishing transcript…"}
          </div>
        )}
      </div>

      {recorderError && !isRecording && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 flex items-start gap-2">
          <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
          <div className="flex-1">
            <span>{recorderError}</span>
            <button
              type="button"
              onClick={() => setRecorderError("")}
              className="ml-2 underline text-xs"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {durationNotice && !isRecording && (
        <div className="rounded-lg border border-brand-teal/30 bg-brand-teal/5 px-3 py-2 text-sm text-brand-teal flex items-start gap-2">
          <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
          <div className="flex-1">
            <span>{durationNotice}</span>
            <button
              type="button"
              onClick={() => setDurationNotice("")}
              className="ml-2 underline text-xs"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {piiNotice && !isRecording && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 flex items-start gap-2">
          <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
          <div className="flex-1">
            <span>{piiNotice}</span>
            <button
              type="button"
              onClick={() => setPiiNotice("")}
              className="ml-2 underline text-xs"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {isRecording && (
        <div className="rounded-lg border-2 border-brand-teal/30 bg-brand-teal/5 p-4 space-y-2">
          <div className="flex items-center gap-2 text-sm font-medium text-brand-teal">
            <div className="relative flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand-red opacity-75" />
              <span className="relative inline-flex rounded-full h-3 w-3 bg-brand-red" />
            </div>
            Still listening...
            <Volume2 className="h-4 w-4 ml-auto animate-pulse" />
          </div>
          <div className="min-h-[60px] text-sm text-foreground/80 italic">
            {liveTranscript || "Speak now, your words will appear here in real time..."}
          </div>
        </div>
      )}

      {(hasRecorded || transcript) && !isRecording && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-muted-foreground">
              {isEnhancing ? "Polishing your transcript…" : "Edit your transcript below if needed:"}
            </p>
            {wasEnhanced && !isEnhancing && (
              <button
                type="button"
                onClick={toggleOriginal}
                className="flex items-center gap-1 text-xs text-brand-blue/50 hover:text-brand-blue/80"
              >
                {showingOriginal ? (
                  <><Sparkles className="h-3 w-3" /> Show enhanced</>
                ) : (
                  <><RotateCcw className="h-3 w-3" /> Show original</>
                )}
              </button>
            )}
          </div>
          <Textarea
            value={transcript}
            onChange={(e) => {
              setTranscript(e.target.value.slice(0, MAX_ANSWER_CHARS));
              setConfirmed(false);
            }}
            className="min-h-[100px] resize-y text-base"
            disabled={isBusy}
            maxLength={MAX_ANSWER_CHARS}
          />
          <div className="flex items-center justify-between">
            <div>
              {wasEnhanced && !isEnhancing && !showingOriginal && (
                <span className="inline-flex items-center gap-1 text-xs text-brand-teal">
                  <Sparkles className="h-3 w-3" /> Auto-enhanced
                </span>
              )}
            </div>
            <p className={`text-xs ${transcript.length >= MAX_ANSWER_CHARS - 20 ? "text-brand-red" : "text-brand-blue/40"}`}>
              {transcript.length}/{MAX_ANSWER_CHARS}
            </p>
          </div>
          <Button
            type="button"
            onClick={handleDone}
            disabled={!transcript.trim() || isBusy}
            size="lg"
            variant="default"
            className={confirmed
              ? "gap-2 bg-brand-teal hover:bg-brand-teal/90 border-brand-teal text-white"
              : "gap-2 bg-brand-blue hover:bg-brand-blue/90 text-white shadow-md hover:shadow-lg transition-all"
            }
          >
            {confirmed ? (
              <><CheckCircle2 className="h-5 w-5" /> Response Confirmed</>
            ) : (
              <><Check className="h-5 w-5" /> Use This Response</>
            )}
          </Button>
        </div>
      )}
    </div>
  );
});
