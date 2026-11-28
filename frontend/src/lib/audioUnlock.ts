/**
 * iPhone Safari plays sound only after a tap. The first "Call the team" (or mic) tap calls this inside the tap, so the
 * Advisor's voice can play later. Harmless everywhere else; does nothing without Web Audio.
 */
let unlocked = false;

export function unlockAudio(): void {
  if (unlocked || typeof window === "undefined") return;
  const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) return;
  try {
    const ctx = new Ctor();
    const buffer = ctx.createBuffer(1, 1, 22050);
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    source.start(0);
    void ctx.resume().finally(() => void ctx.close().catch(() => undefined));
    unlocked = true;
  } catch {
    // no audio device: voice will say so when it starts
  }
}
