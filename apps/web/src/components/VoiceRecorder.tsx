"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Mic, Square, Check, Loader2, Volume2 } from "lucide-react";
import { api } from "@/lib/api";

interface VoiceRecorderProps {
  onTranscriptComplete: (transcript: string) => void;
  initialTranscript?: string;
  language?: string;
}

const LANG_MAP: Record<string, string> = {
  en: "en-US", es: "es-ES", fr: "fr-FR", pt: "pt-BR",
  zh: "zh-CN", hi: "hi-IN", ar: "ar-SA",
};

interface SpeechRecognitionEvent {
  results: SpeechRecognitionResultList;
  resultIndex: number;
}

interface SpeechRecognitionErrorEvent {
  error: string;
}

export function VoiceRecorder({ onTranscriptComplete, initialTranscript = "", language = "en" }: VoiceRecorderProps) {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [transcript, setTranscript] = useState(initialTranscript);
  const [liveTranscript, setLiveTranscript] = useState("");
  const [hasRecorded, setHasRecorded] = useState(!!initialTranscript);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const recognitionRef = useRef<any>(null);
  const inactivityTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const finalTranscriptRef = useRef("");

  const resetInactivityTimer = useCallback(() => {
    if (inactivityTimerRef.current) {
      clearTimeout(inactivityTimerRef.current);
    }
    inactivityTimerRef.current = setTimeout(() => {
      stopRecording();
    }, 15000);
  }, []);

  const stopRecording = useCallback(() => {
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
    }

    setIsRecording(false);
  }, []);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
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

        if (currentTranscript) {
          setTranscript(currentTranscript);
          setHasRecorded(true);
          setLiveTranscript("");
          return;
        }

        const audioBlob = new Blob(chunksRef.current, { type: "audio/webm" });
        chunksRef.current = [];

        if (audioBlob.size > 1000) {
          setIsTranscribing(true);
          try {
            const result = await api.transcribe(audioBlob);
            if (result.transcript && result.transcript.trim()) {
              setTranscript(result.transcript);
              setHasRecorded(true);
            } else {
              setTranscript(currentTranscript || "");
              setHasRecorded(true);
            }
          } catch {
            setTranscript(currentTranscript || "");
            if (currentTranscript) setHasRecorded(true);
          } finally {
            setIsTranscribing(false);
            setLiveTranscript("");
          }
        } else {
          setTranscript(currentTranscript || "");
          if (currentTranscript) setHasRecorded(true);
          setLiveTranscript("");
        }
      };

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const w = window as any;
      const SpeechRecognitionClass = w.SpeechRecognition || w.webkitSpeechRecognition;

      if (SpeechRecognitionClass) {
        const recognition = new SpeechRecognitionClass();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = LANG_MAP[language] || "en-US";

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
          if (isRecording && recognitionRef.current) {
            try { recognitionRef.current.start(); } catch {}
          }
        };

        recognitionRef.current = recognition;
        recognition.start();
      }

      mediaRecorder.start(1000);
      setIsRecording(true);
      resetInactivityTimer();
    } catch {
      alert("Could not access microphone. Please check your browser permissions and ensure you're using HTTPS or localhost.");
    }
  };

  const handleDone = () => {
    onTranscriptComplete(transcript);
  };

  useEffect(() => {
    return () => {
      if (inactivityTimerRef.current) clearTimeout(inactivityTimerRef.current);
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

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        {!isRecording ? (
          <Button
            type="button"
            onClick={startRecording}
            disabled={isTranscribing}
            size="lg"
            className="gap-2 bg-brand-blue hover:bg-brand-blue/90 h-12 px-6 text-base"
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
            className="gap-2 h-12 px-6 text-base"
          >
            <Square className="h-5 w-5" />
            Stop Recording
          </Button>
        )}

        {isTranscribing && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Enhancing transcript...
          </div>
        )}
      </div>

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
            {liveTranscript || "Speak now — your words will appear here in real time..."}
          </div>
        </div>
      )}

      {(hasRecorded || transcript) && !isRecording && (
        <div className="space-y-2">
          <p className="text-sm font-medium text-muted-foreground">
            Edit your transcript below if needed:
          </p>
          <Textarea
            value={transcript}
            onChange={(e) => setTranscript(e.target.value)}
            className="min-h-[100px] resize-y text-base"
            disabled={isTranscribing}
          />
          <Button
            type="button"
            onClick={handleDone}
            disabled={!transcript.trim() || isTranscribing}
            size="lg"
            className="gap-2 bg-brand-teal hover:bg-brand-teal/90 h-11"
          >
            <Check className="h-5 w-5" />
            Use This Response
          </Button>
        </div>
      )}
    </div>
  );
}
