// Procedural Web Audio effects. This module is imported by the big screen only.
export class ShowAudio {
  constructor() { this.context = null; this.master = null; this.nodes = new Set(); }
  async unlock() {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return false;
    if (!this.context) {
      this.context = new AudioContext();
      this.master = this.context.createGain();
      this.master.gain.value = 0.35;
      const limiter = this.context.createDynamicsCompressor();
      this.master.connect(limiter); limiter.connect(this.context.destination);
    }
    if (this.context.state === "suspended") await this.context.resume();
    return this.context.state === "running";
  }
  track(node) { this.nodes.add(node); node.onended = () => { this.nodes.delete(node); node.disconnect(); }; }
  stop() { for (const node of this.nodes) { try { node.stop(); } catch (_) {} } this.nodes.clear(); }
  close() { this.stop(); this.context?.close().catch(() => {}); }
  tone(freq, seconds, delay = 0, type = "sine", volume = 0.3, endFreq = null) {
    const c = this.context, at = c.currentTime + delay;
    const osc = c.createOscillator(), gain = c.createGain();
    osc.type = type; osc.frequency.setValueAtTime(freq, at);
    if (endFreq) osc.frequency.exponentialRampToValueAtTime(Math.max(20, endFreq), at + seconds);
    gain.gain.setValueAtTime(0.001, at); gain.gain.exponentialRampToValueAtTime(volume, at + 0.008);
    gain.gain.exponentialRampToValueAtTime(0.001, at + seconds);
    osc.connect(gain); gain.connect(this.master); this.track(osc); osc.start(at); osc.stop(at + seconds + 0.01);
    osc.addEventListener("ended", () => gain.disconnect());
  }
  noise(seconds, delay = 0, volume = 0.3, cutoff = 2500) {
    const c = this.context, at = c.currentTime + delay;
    const buffer = c.createBuffer(1, Math.ceil(c.sampleRate * seconds), c.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
    const source = c.createBufferSource(), filter = c.createBiquadFilter(), gain = c.createGain();
    source.buffer = buffer; filter.type = "bandpass"; filter.frequency.value = cutoff; filter.Q.value = 0.7;
    gain.gain.setValueAtTime(volume, at); gain.gain.exponentialRampToValueAtTime(0.001, at + seconds);
    source.connect(filter); filter.connect(gain); gain.connect(this.master); this.track(source); source.start(at); source.stop(at + seconds);
    source.addEventListener("ended", () => { filter.disconnect(); gain.disconnect(); });
  }
  play(name) {
    if (!this.context || this.context.state !== "running") return false;
    switch (name) {
      case "rimshot": this.tone(180, 0.12, 0, "triangle", 0.65, 70); this.noise(0.12, 0, 0.5); this.noise(0.45, 0.14, 0.45, 6500); break;
      case "sad_trombone": [293, 277, 261, 196].forEach((f, i) => this.tone(f, i === 3 ? 0.85 : 0.3, i * 0.32, "sawtooth", 0.2, i === 3 ? 100 : f * 0.95)); break;
      case "motorbike_horn": [0, 0.2].forEach(d => { this.tone(440, 0.13, d, "square", 0.16); this.tone(554, 0.13, d, "square", 0.13); }); break;
      case "air_horn": [220, 277, 330].forEach(f => this.tone(f, 0.85, 0, "sawtooth", 0.18)); break;
      case "drumroll": for (let i = 0; i < 24; i++) { this.noise(0.08, i * 0.065, 0.08 + i * 0.012, 2200); this.tone(100, 0.05, i * 0.065, "triangle", 0.12); } break;
      case "tick_tock": this.tone(1000, 0.045, 0, "square", 0.08); this.tone(750, 0.035, 0.08, "triangle", 0.1); break;
      case "siren": for (let i = 0; i < 4; i++) { this.tone(500, 0.35, i * 0.7, "sawtooth", 0.17, 1100); this.tone(1100, 0.35, i * 0.7 + 0.35, "sawtooth", 0.17, 500); } break;
      case "ding": this.tone(880, 0.6, 0, "sine", 0.45); this.tone(1320, 0.5, 0.08, "sine", 0.2); break;
      case "buzz": this.tone(120, 0.5, 0, "sawtooth", 0.3, 65); break;
      case "applause": for (let i = 0; i < 32; i++) this.noise(0.15 + Math.random() * 0.3, i * 0.045, 0.1 + Math.random() * 0.12, 1200 + Math.random() * 2000); break;
      case "pop": this.tone(700, 0.1, 0, "sine", 0.5, 130); break;
      case "cash_register": [1500, 2100, 2700].forEach((f, i) => this.tone(f, 0.14, i * 0.09, "triangle", 0.25)); this.noise(0.13, 0.3, 0.2, 4500); this.tone(1700, 0.65, 0.32, "sine", 0.25); break;
      default: return false;
    }
    return true;
  }
}
