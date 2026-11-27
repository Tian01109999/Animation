'use strict';
// JSON over stdin preserves Unicode and avoids command-line quoting/length limits.
const fs = require('node:fs');
const capcut = require('./capcut_tts');

async function main() {
  const opts = JSON.parse(fs.readFileSync(0, 'utf8'));
  if (!['vi', 'th', 'ko'].includes(opts.lang) || !capcut.hopLeGiong(opts.voice, opts.lang)) {
    throw new Error('Giọng CapCut không thuộc ngôn ngữ đã chọn.');
  }
  if (!String(opts.text || '').trim()) throw new Error('Câu đọc rỗng.');
  await capcut.taoGiongRaTep({
    text: opts.text, voice: opts.voice, lang: opts.lang, region: 'VN',
    outPath: opts.outPath, needTimestamp: false,
  });
}
main().then(() => process.exit(0)).catch(err => {
  console.error(String(err.message || err));
  process.exit(1);
});
