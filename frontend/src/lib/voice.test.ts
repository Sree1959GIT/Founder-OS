import { describe, expect, it } from "vitest";

import { latencyLine, ms, pcm16ToFloat, voiceUrl } from "@/lib/voice";

describe("voice client helpers", () => {
  it("builds the socket URL from the page, with the session", () => {
    const at = { protocol: "http:", host: "127.0.0.1:3000" } as Location;
    expect(voiceUrl("ses_1", "ptt", at)).toBe("ws://127.0.0.1:3000/ws/voice?mode=ptt&session_id=ses_1");
    expect(voiceUrl(null, "duplex", { protocol: "https:", host: "x" } as Location)).toBe("wss://x/ws/voice?mode=duplex");
  });
  it("turns int16 PCM into floats", () => {
    const pcm = new Int16Array([0, 16384, -32768]).buffer;
    expect(Array.from(pcm16ToFloat(pcm))).toEqual([0, 0.5, -1]);
  });
  it("shows the last turn's latency and the barge-in stop time", () => {
    const turn = {
      id: "t",
      text: "What is our runway?",
      stt_ms: 280.4,
      turn_ms: 300,
      first_audio_ms: 812.6,
      first_audio_lane: "conversation",
      first_answer_audio_ms: 2410,
      tts_first_ms: 5,
    };
    const barge = { paused_ms: 70, stopped_ms: 655, client_flush_ms: 0.4, verdict: "barge_in", by: "duration" };
    expect(latencyLine(turn, barge)).toBe("first words 813 ms · answer 2410 ms · STT 280 ms · barge-in stop 655 ms");
    expect(latencyLine(null, { ...barge, verdict: "backchannel" })).toBe("barge-in stop 655 ms (backchannel)");
    expect(ms(null)).toBe("–");
  });
});
