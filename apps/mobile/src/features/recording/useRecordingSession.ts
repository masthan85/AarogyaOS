import { useCallback, useEffect, useRef, useState } from 'react';

import {
  assignSpeaker,
  createInteraction,
  freshAccessToken,
  getInteraction,
  getTranscript,
  pauseInteraction,
  resumeInteraction,
  startInteraction,
  stopInteraction,
} from '@/api/endpoints';
import { ApiError } from '@/api/client';
import type { Interaction, Segment, Transcript } from '@/api/schemas';
import { describeClose, mergeSegments, type Phase, recordingIndicator } from '@/domain/recording';
import { type AudioCapture, CaptureUnavailableError, createCapture, simulatedAudioAllowed } from '@/services/audio/capture';
import { GatewayClient, GatewayRefused, toWebSocketUrl } from '@/services/audio/gateway';

type Options = {
  patientId: string;
  encounterId: string;
  languageHint?: string;
  ai: boolean;
};

const POLL_MS = 1000;

/**
 * One consented recording session on this device.
 *
 * The indicator is derived from real state (session live AND microphone running AND socket open),
 * never from what the screen last asked for. If the connection drops, the session shows as paused
 * at once; the server independently pauses it as well, so a stale "recording" cannot persist.
 */
export function useRecordingSession(opts: Options) {
  const [phase, setPhase] = useState<Phase>('idle');
  const [interaction, setInteraction] = useState<Interaction | null>(null);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [speakers, setSpeakers] = useState<Transcript['speakers']>([]);
  const [partial, setPartial] = useState<Transcript['partial']>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [seconds, setSeconds] = useState(0);

  const phaseRef = useRef<Phase>('idle');
  const capture = useRef<AudioCapture | null>(null);
  const gateway = useRef<GatewayClient | null>(null);
  const idRef = useRef<string | null>(null);
  const pathRef = useRef<string | null>(null);
  const lastSeq = useRef(0);

  const move = useCallback((next: Phase) => {
    phaseRef.current = next;
    setPhase(next);
  }, []);

  const teardownStream = useCallback(async () => {
    setCapturing(false);
    setConnected(false);
    await capture.current?.stop();
    gateway.current?.close();
    gateway.current = null;
  }, []);

  const openStream = useCallback(
    async (path: string) => {
      const cap = createCapture();
      capture.current = cap;
      const client = new GatewayClient({
        url: toWebSocketUrl(path),
        getToken: freshAccessToken,
        onEvent: (e) => {
          if (e.type === 'closed') {
            setConnected(false);
            setCapturing(false);
            void capture.current?.stop();
            if (e.code === 4001 && e.reason === 'CONSENT_WITHDRAWN') {
              move('ended');
            } else if (phaseRef.current === 'live') {
              move('paused');
            }
            if (phaseRef.current !== 'idle') setMessage(describeClose(e.code, e.reason));
          }
        },
      });
      gateway.current = client;
      await client.connect();
      setConnected(true);
      await cap.start((frame) => {
        if (!client.sendAudio(frame)) {
          setCapturing(false);
          setConnected(false);
        }
      });
      setCapturing(true);
    },
    [move],
  );

  const fail = useCallback(
    async (e: unknown) => {
      await teardownStream();
      if (e instanceof CaptureUnavailableError) setMessage(e.message);
      else if (e instanceof GatewayRefused) setMessage(describeClose(e.code, e.message));
      else if (e instanceof ApiError) setMessage(e.message);
      else setMessage('Could not start. Check your connection; nothing was recorded.');
      move(idRef.current ? 'paused' : 'error');
    },
    [move, teardownStream],
  );

  const begin = useCallback(async () => {
    setMessage(null);
    move('starting');
    try {
      const created = await createInteraction({
        patient_id: opts.patientId,
        purpose: 'CONSULTATION',
        encounter_id: opts.encounterId,
        language_hint: opts.languageHint,
        ai_processing: opts.ai,
      });
      idRef.current = created.id;
      setInteraction(created);
      const started = await startInteraction(created.id);
      pathRef.current = started.gateway_path;
      setInteraction(started.interaction);
      await openStream(started.gateway_path);
      move('live');
    } catch (e) {
      if (idRef.current && !(e instanceof ApiError)) {
        // We created a session but could not stream: do not leave it claiming to record.
        await stopInteraction(idRef.current).catch(() => undefined);
        idRef.current = null;
      }
      await fail(e);
    }
  }, [fail, move, opts.ai, opts.encounterId, opts.languageHint, opts.patientId, openStream]);

  const pause = useCallback(async () => {
    const id = idRef.current;
    if (!id) return;
    await teardownStream();
    move('paused');
    try {
      setInteraction(await pauseInteraction(id));
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : 'Could not pause on the server; it will pause itself shortly.');
    }
  }, [move, teardownStream]);

  const resume = useCallback(async () => {
    const id = idRef.current;
    if (!id) return;
    setMessage(null);
    move('starting');
    try {
      const current = await getInteraction(id);
      if (current.status === 'PAUSED') setInteraction(await resumeInteraction(id));
      const path = pathRef.current ?? `/api/v1/interactions/${id}/audio`;
      await openStream(path);
      move('live');
    } catch (e) {
      await fail(e);
    }
  }, [fail, move, openStream]);

  const stop = useCallback(async () => {
    const id = idRef.current;
    if (!id) return;
    await capture.current?.stop();
    setCapturing(false);
    gateway.current?.stop();
    try {
      setInteraction(await stopInteraction(id));
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : 'Could not confirm the stop. Check the connection.');
    }
    gateway.current?.close();
    gateway.current = null;
    setConnected(false);
    move('ended');
  }, [move]);

  const assignRole = useCallback(async (speakerId: string, role: string) => {
    const id = idRef.current;
    if (!id) return;
    setSpeakers((prev) => prev.map((s) => (s.speaker_id === speakerId ? { ...s, role } : s)));
    try {
      await assignSpeaker(id, speakerId, role);
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : 'Could not save who is speaking.');
    }
  }, []);

  // Adopt a session that is still open on the server (the app was reopened mid-consultation).
  const adopt = useCallback(
    async (existing: Interaction) => {
      idRef.current = existing.id;
      setInteraction(existing);
      lastSeq.current = 0;
      setSegments([]);
      move(existing.status === 'ENDED' ? 'ended' : 'paused'); // we are not streaming, so never 'live'
    },
    [move],
  );

  // Poll the transcript while a session exists.
  useEffect(() => {
    if (!interaction || phase === 'idle' || phase === 'error') return;
    let cancelled = false;
    const tick = async () => {
      const id = idRef.current;
      if (!id) return;
      try {
        const t = await getTranscript(id, lastSeq.current);
        if (cancelled) return;
        if (t.segments.length) {
          lastSeq.current = t.last_seq;
          setSegments((cur) => mergeSegments(cur, t.segments));
        }
        setSpeakers(t.speakers);
        setPartial(t.partial);
        if (t.status === 'ENDED' && phaseRef.current !== 'ended') {
          const final = await getInteraction(id);
          if (cancelled) return;
          setInteraction(final);
          await teardownStream();
          move('ended');
          if (final.end_reason === 'CONSENT_WITHDRAWN') setMessage(describeClose(4001, 'CONSENT_WITHDRAWN'));
        }
      } catch {
        /* transient: the next tick retries */
      }
    };
    void tick();
    const timer = setInterval(() => void tick(), POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [interaction, phase, move, teardownStream]);

  const indicator = recordingIndicator({ phase, capturing, connected });

  useEffect(() => {
    if (!indicator.isRecording) return;
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, [indicator.isRecording]);

  // Leaving the screen must not leave a recording running: pause it on the server too.
  useEffect(
    () => () => {
      const id = idRef.current;
      const wasLive = phaseRef.current === 'live';
      void capture.current?.stop();
      gateway.current?.close();
      if (id && wasLive) void pauseInteraction(id).catch(() => undefined);
    },
    [],
  );

  return {
    phase, interaction, segments, speakers, partial, message, seconds, indicator,
    begin, pause, resume, stop, assignRole, adopt,
    captureKind: simulatedAudioAllowed() ? ('simulated' as const) : ('microphone' as const),
  };
}
export type RecordingSession = ReturnType<typeof useRecordingSession>;
