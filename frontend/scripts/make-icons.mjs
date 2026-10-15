// Writes public/icon-192.png, icon-512.png and icon-maskable-512.png: a cream "V" on forest green.
// Pure Node (zlib), so no image tooling is needed. Run: node scripts/make-icons.mjs
import { writeFileSync } from "node:fs";
import { deflateSync } from "node:zlib";

const BG = [0x2d, 0x6a, 0x4f], FG = [0xf5, 0xf0, 0xe4];
// "V" as a polygon in a 0..1 square
const V = [[0.24, 0.27], [0.36, 0.27], [0.5, 0.62], [0.64, 0.27], [0.76, 0.27], [0.56, 0.75], [0.44, 0.75]];

function inside(x, y, poly) {
  let hit = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) hit = !hit;
  }
  return hit;
}

function inRounded(x, y, r) {   // rounded square, corner radius r (0..0.5)
  const cx = Math.min(Math.max(x, r), 1 - r), cy = Math.min(Math.max(y, r), 1 - r);
  return (x - cx) ** 2 + (y - cy) ** 2 <= r * r;
}

function crc32(buf) {
  let c, crc = 0xffffffff;
  for (const b of buf) { c = (crc ^ b) & 0xff; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; crc = (crc >>> 8) ^ c; }
  return (crc ^ 0xffffffff) >>> 0;
}
function chunk(type, data) {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type), data]);
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(body));
  return Buffer.concat([len, body, crc]);
}

function png(size, { radius, scale }) {
  const SS = 4, raw = Buffer.alloc(size * (size * 4 + 1));
  for (let y = 0; y < size; y++) {
    raw[y * (size * 4 + 1)] = 0;
    for (let x = 0; x < size; x++) {
      let bg = 0, fg = 0;
      for (let sy = 0; sy < SS; sy++) for (let sx = 0; sx < SS; sx++) {
        const u = (x + (sx + 0.5) / SS) / size, v = (y + (sy + 0.5) / SS) / size;
        if (!inRounded(u, v, radius)) continue;
        bg++;
        if (inside(0.5 + (u - 0.5) / scale, 0.5 + (v - 0.5) / scale, V)) fg++;
      }
      const n = SS * SS, o = y * (size * 4 + 1) + 1 + x * 4;
      for (let c = 0; c < 3; c++) raw[o + c] = bg ? Math.round((BG[c] * (bg - fg) + FG[c] * fg) / bg) : 0;
      raw[o + 3] = Math.round((255 * bg) / n);
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0); ihdr.writeUInt32BE(size, 4); ihdr[8] = 8; ihdr[9] = 6;
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", ihdr), chunk("IDAT", deflateSync(raw)), chunk("IEND", Buffer.alloc(0))]);
}

writeFileSync("public/icon-192.png", png(192, { radius: 0.22, scale: 1 }));
writeFileSync("public/icon-512.png", png(512, { radius: 0.22, scale: 1 }));
writeFileSync("public/icon-maskable-512.png", png(512, { radius: 0, scale: 0.8 }));   // full bleed, V inside the safe zone
