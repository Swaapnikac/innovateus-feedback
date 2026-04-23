/**
 * Shared limits for participant-facing inputs.
 *
 * Keep these small on purpose: short answers force participants to say
 * the most important thing first. Long free-form text is where privacy
 * leaks and rambling live.
 *
 * Changing either number is a one-liner here and propagates everywhere.
 */

/** Hard character ceiling on any open-text answer (main answer or follow-up). */
export const MAX_ANSWER_CHARS = 500;

/**
 * Hard ceiling on a single voice recording before we auto-stop.
 * 5 min is a generous ceiling for longer-form feedback. The 15 s
 * Web Speech silence auto-stop still cuts recordings short whenever
 * the participant pauses, so in practice most recordings end much
 * sooner than this cap.
 */
export const MAX_VOICE_RECORDING_MS = 5 * 60_000;
