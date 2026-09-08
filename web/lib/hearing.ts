/**
 * What the machine heard, as a still picture.
 *
 * The score strip shows the recording as a score. Before the score can be read there
 * is a hearing: the raw log-frequency picture of the whole piece, computed once,
 * offline, from the decoded samples. It exists to be dissolved — the notes, their
 * height and their dynamics are drawn out of it in the strip's entrance, and a
 * measure's patch of it returns under the pointer to show where that measure's notes
 * came from. It is never a live meter, never driven by playback, and never the first
 * thing on screen for long: the cliché of spectrum in, form out is what this project
 * is not.
 *
 * Decoding runs through an OfflineAudioContext at 16 kHz so a 30 MB upload is a few
 * tens of megabytes of samples, and the picture is 1,024 columns by 32 rows.
 */

export const HEARING_COLUMNS = 1024;
export const HEARING_ROWS = 32;
const RATE = 16000;
const FRAME = 1024;
const F_MIN = 40;
const F_MAX = 7000;
const FLOOR_DB = 60;

export interface Hearing {
  duration: number;
  /** Row-major, bottom row (lowest band) first; 0..255 against the track's own peak. */
  cells: Uint8Array;
}

/** In-place radix-2 FFT. `re` and `im` are the same power-of-two length. */
function fft(re: Float32Array, im: Float32Array): void {
  const n = re.length;
  for (let i = 1, j = 0; i < n; i += 1) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      const tr = re[i]; re[i] = re[j]; re[j] = tr;
      const ti = im[i]; im[i] = im[j]; im[j] = ti;
    }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const angle = (-2 * Math.PI) / len;
    const wr = Math.cos(angle);
    const wi = Math.sin(angle);
    for (let i = 0; i < n; i += len) {
      let cr = 1;
      let ci = 0;
      for (let k = 0; k < len / 2; k += 1) {
        const a = i + k;
        const b = a + len / 2;
        const xr = re[b] * cr - im[b] * ci;
        const xi = re[b] * ci + im[b] * cr;
        re[b] = re[a] - xr; im[b] = im[a] - xi;
        re[a] += xr; im[a] += xi;
        const next = cr * wr - ci * wi;
        ci = cr * wi + ci * wr;
        cr = next;
      }
    }
  }
}

export async function decodeHearing(data: ArrayBuffer): Promise<Hearing> {
  const Offline = window.OfflineAudioContext
    ?? (window as unknown as { webkitOfflineAudioContext?: typeof OfflineAudioContext }).webkitOfflineAudioContext;
  if (!Offline) throw new Error('This browser cannot decode audio.');
  const buffer = await new Offline(1, 1, RATE).decodeAudioData(data.slice(0));
  const channels = Array.from({ length: buffer.numberOfChannels }, (_, i) => buffer.getChannelData(i));
  const length = buffer.length;

  const window_ = new Float32Array(FRAME);
  for (let i = 0; i < FRAME; i += 1) window_[i] = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (FRAME - 1));
  const re = new Float32Array(FRAME);
  const im = new Float32Array(FRAME);
  const binHz = (RATE / 2) / (FRAME / 2);
  const ratio = F_MAX / F_MIN;
  // Bin ranges per row, once.
  const rows = Array.from({ length: HEARING_ROWS }, (_, r) => {
    const f0 = F_MIN * Math.pow(ratio, r / HEARING_ROWS);
    const f1 = F_MIN * Math.pow(ratio, (r + 1) / HEARING_ROWS);
    const b0 = Math.min(FRAME / 2 - 1, Math.floor(f0 / binHz));
    const b1 = Math.min(FRAME / 2, Math.max(b0 + 1, Math.ceil(f1 / binHz)));
    return [b0, b1] as const;
  });

  const db = new Float32Array(HEARING_COLUMNS * HEARING_ROWS);
  let peak = -Infinity;
  for (let c = 0; c < HEARING_COLUMNS; c += 1) {
    const centre = Math.floor(((c + 0.5) / HEARING_COLUMNS) * length);
    const start = centre - FRAME / 2;
    for (let i = 0; i < FRAME; i += 1) {
      const at = start + i;
      let mix = 0;
      if (at >= 0 && at < length) for (const channel of channels) mix += channel[at];
      re[i] = (mix / channels.length) * window_[i];
      im[i] = 0;
    }
    fft(re, im);
    for (let r = 0; r < HEARING_ROWS; r += 1) {
      const [b0, b1] = rows[r];
      let loudest = 0;
      for (let b = b0; b < b1; b += 1) {
        const power = re[b] * re[b] + im[b] * im[b];
        if (power > loudest) loudest = power;
      }
      const value = 10 * Math.log10(loudest + 1e-12);
      db[c * HEARING_ROWS + r] = value;
      if (value > peak) peak = value;
    }
  }

  const cells = new Uint8Array(db.length);
  for (let i = 0; i < db.length; i += 1) {
    const t = Math.min(1, Math.max(0, (db[i] - (peak - FLOOR_DB)) / FLOOR_DB));
    cells[i] = Math.round(255 * t * t);
  }
  return { duration: buffer.duration, cells };
}

/** The hearing as an image for an SVG `<image>`: one ink, alpha carries the level. */
export function hearingImage(hearing: Hearing, rgb: [number, number, number]): string {
  const canvas = document.createElement('canvas');
  canvas.width = HEARING_COLUMNS;
  canvas.height = HEARING_ROWS;
  const context = canvas.getContext('2d');
  if (!context) return '';
  const image = context.createImageData(HEARING_COLUMNS, HEARING_ROWS);
  for (let c = 0; c < HEARING_COLUMNS; c += 1) {
    for (let r = 0; r < HEARING_ROWS; r += 1) {
      const y = HEARING_ROWS - 1 - r;                 // low bands at the bottom
      const i = (y * HEARING_COLUMNS + c) * 4;
      image.data[i] = rgb[0];
      image.data[i + 1] = rgb[1];
      image.data[i + 2] = rgb[2];
      image.data[i + 3] = hearing.cells[c * HEARING_ROWS + r];
    }
  }
  context.putImageData(image, 0, 0);
  return canvas.toDataURL('image/png');
}

/** `#rrggbb`, `#rgb` or `rgb(r, g, b)` to a triple; anything else falls back. */
export function parseRgb(color: string, fallback: [number, number, number]): [number, number, number] {
  const hex = color.trim().match(/^#([0-9a-f]{6})$/i);
  if (hex) {
    const n = parseInt(hex[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  const short = color.trim().match(/^#([0-9a-f]{3})$/i);
  if (short) {
    const [r, g, b] = short[1].split('').map((c) => parseInt(c + c, 16));
    return [r, g, b];
  }
  const rgb = color.match(/rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)/i);
  if (rgb) return [Number(rgb[1]), Number(rgb[2]), Number(rgb[3])];
  return fallback;
}
