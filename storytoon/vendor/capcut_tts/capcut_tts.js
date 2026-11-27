'use strict';

/**
 * Bộ tạo giọng nói CapCut TTS độc lập (Node.js thuần — 0 npm dependencies).
 * Đã gỡ bỏ hoàn toàn cơ chế xoay nhiều quốc gia: chỉ dùng cố định 1 quốc gia duy nhất (mặc định: 'VN').
 */

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');
const https = require('node:https');
const crypto = require('node:crypto');
const { execFile } = require('node:child_process');

const BASE_URL = 'https://editor-api-sg.capcutapi.com';
const QUOC_GIA_MAC_DINH = String(process.env.CAPCUT_REGION || 'VN').trim().toUpperCase() || 'VN';
const MAC_DINH_GIONG = 'BV075_streaming';
const MAC_DINH_RESOURCE_ID = '7102355709945188865';

const CHO_CO_BAN_MS = Math.max(8000, parseInt(process.env.CAPCUT_TIMEOUT_MS || '100000', 10) || 100000);
const CHO_TOI_DA_HANG_DOI_MS = Math.max(CHO_CO_BAN_MS, parseInt(process.env.CAPCUT_MAX_QUEUE_MS || '240000', 10) || 240000);
const HAN_KET_HANG_DOI_MS = Math.max(8000, parseInt(process.env.CAPCUT_STALL_MS || '45000', 10) || 45000);
const KICH_THUOC_LO_CAPCUT = Math.max(1, Math.min(25, parseInt(process.env.CAPCUT_BATCH_SIZE || '15', 10) || 15));
const CUA_SO_GOM_LO_MS = Math.max(0, Math.min(50, parseInt(process.env.CAPCUT_BATCH_WINDOW_MS || '10', 10) || 10));
const MAX_KY_TU = Math.max(100, parseInt(process.env.CAPCUT_MAX_CHARS || '500', 10) || 500);

const RSA_PUBLIC_KEY_PEM = [
  '-----BEGIN PUBLIC KEY-----',
  'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAmTd34Lw4b7IuldSXh/zY',
  'CMla+ITdGG5TeWz6ad+OySd4r+IrY45AoqrYUxhQ2dl+7z+i7r/5vEa8rr39BYfB',
  '8AGMQLmZA8HmgpWBsqrn/V6daUALkKnkLb70Fn32CJigIuGXAYqxUdGuI340aC+0',
  'v5Es3puJsHyzf01/AelE4Cdc6bZhQrASJLBh8R3BQToYClmDVSDUQk28o8sl/guA',
  'Z4n303Vj+6Siv1HayPCdV6kpVVnMBAG4+umUbwGmn132N3fgpzLarFF3XyWmS1zh',
  'D/J07iM/rP8GDO9IskHNHd2phrO0G6KzrcFAnTBHjVv+hCBEfzN/no3FNA9AuC36',
  'mwIDAQAB',
  '-----END PUBLIC KEY-----',
].join('\n');

const httpsAgent = new https.Agent({
  keepAlive: true,
  keepAliveMsecs: 5000,
  maxSockets: 128,
  timeout: 15000,
});

const VOICES_DIR = path.join(__dirname, 'voices');
let _boNhoVi = null;
let _boNhoTh = null;
let _boNhoKo = null;

function danhSachGiong(lang = 'vi') {
  const code = String(lang || 'vi').trim().toLowerCase();
  if (code === 'th') {
    return (_boNhoTh ??= JSON.parse(fs.readFileSync(path.join(VOICES_DIR, 'th.json'), 'utf8')));
  }
  if (code === 'ko') {
    return (_boNhoKo ??= JSON.parse(fs.readFileSync(path.join(VOICES_DIR, 'ko.json'), 'utf8')));
  }
  if (code !== 'vi') return [];
  return (_boNhoVi ??= JSON.parse(fs.readFileSync(path.join(VOICES_DIR, 'vi.json'), 'utf8')));
}

function timGiong(id, lang) {
  const ma = String(id || '').trim();
  if (!ma) return null;
  const khopMa = g => g.id === ma || g.maCu === ma;
  if (lang) return danhSachGiong(lang).find(khopMa) || null;
  return (
    danhSachGiong('vi').find(khopMa) ||
    danhSachGiong('th').find(khopMa) ||
    danhSachGiong('ko').find(khopMa) ||
    null
  );
}

function hopLeGiong(id, lang) {
  return Boolean(timGiong(id, lang));
}

function chonGiongHopLe(id, lang) {
  if (lang === 'th' || lang === 'ko') {
    return timGiong(id, lang) || danhSachGiong(lang)[0];
  }
  return timGiong(id, lang) || timGiong(MAC_DINH_GIONG, 'vi') || danhSachGiong('vi')[0];
}

function chuanHoaMaQuocGia(region) {
  const clean = String(region || QUOC_GIA_MAC_DINH).trim().toUpperCase();
  if (!/^[A-Z]{2}$/.test(clean)) {
    throw new Error(`Mã quốc gia không hợp lệ: "${region}" (cần mã ISO 2 ký tự như VN).`);
  }
  return clean;
}

function taoDeviceId() {
  const bytes = crypto.randomBytes(20);
  let out = '';
  for (let i = 0; i < 20; i++) out += String(bytes[i] % 10);
  if (out[0] === '0') out = String((bytes[0] % 9) + 1) + out.slice(1);
  return out;
}

function taoThietBiAo(region = QUOC_GIA_MAC_DINH) {
  const qg = chuanHoaMaQuocGia(region);
  const did = taoDeviceId();
  return {
    aid: '359289',
    app_name: 'CapCut',
    appvr: '8.7.0',
    version_name: '8.7.0',
    version_code: '8.7.0',
    channel: 'capcutpc_google',
    device_platform: 'mac',
    device_type: 'MacBookPro17,4',
    device_brand: 'MacBookPro17,4',
    os_version: '15.7.4',
    device_id: did,
    iid: did,
    tdid: did,
    region: qg,
    loc: qg,
    lan: 'vi-VN',
    pf: '3',
  };
}

function escapeXml(text) {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

function md5Hex(str) {
  return crypto.createHash('md5').update(String(str), 'utf8').digest('hex');
}

function kyHeader(url, appvr, deviceTime, tdid) {
  const cleanPath = String(url).split('?', 1)[0];
  return md5Hex(`9e2c|${cleanPath.slice(-7)}|3|${appvr}|${deviceTime}|${tdid}|11ac`);
}

function kyPayload(ssml, extraInfo, deviceId, appId) {
  const ssmlMd5 = md5Hex(ssml);
  let raw = `appid:${appId}&did:${deviceId}&creditDisable:false&ssml:${ssmlMd5}`;
  if (extraInfo != null) raw += `&extraInfo:${extraInfo}`;
  const encrypted = crypto.publicEncrypt(
    { key: RSA_PUBLIC_KEY_PEM, padding: crypto.constants.RSA_PKCS1_PADDING },
    Buffer.from(raw, 'utf8')
  );
  return encrypted.toString('base64');
}

function taoLoiHuyCapcut() {
  const e = new Error('Đã dừng tạo giọng theo yêu cầu');
  e.code = 'ABORTED';
  return e;
}

function guiRequestBuffer(urlStr, {
  method = 'GET',
  headers = {},
  body = null,
  timeoutMs = 15000,
  daHuy = null,
  dangKyHuy = null,
  _soChuyenHuong = 0,
} = {}) {
  return new Promise((resolve, reject) => {
    if (daHuy?.()) {
      reject(taoLoiHuyCapcut());
      return;
    }
    if (_soChuyenHuong > 5) {
      reject(new Error('CapCut chuyển hướng quá nhiều lần'));
      return;
    }
    let parsed;
    try {
      parsed = new URL(urlStr);
    } catch (err) {
      reject(err);
      return;
    }
    const laHttp = parsed.protocol === 'http:';
    const client = laHttp ? http : https;
    const bodyBuf = body != null ? (Buffer.isBuffer(body) ? body : Buffer.from(String(body), 'utf8')) : null;
    const reqHeaders = { ...headers };
    if (bodyBuf) reqHeaders['content-length'] = Buffer.byteLength(bodyBuf);

    let daChot = false;
    let daKetThuc = false;
    let goHuy = null;
    let henCung = null;
    let henQuetHuy = null;
    const batDau = Date.now();
    const gioiHanMs = Math.max(50, Number(timeoutMs) || 15000);

    const donDep = () => {
      if (henCung) { clearTimeout(henCung); henCung = null; }
      if (henQuetHuy) { clearInterval(henQuetHuy); henQuetHuy = null; }
      if (goHuy) {
        const fn = goHuy;
        goHuy = null;
        fn();
      }
    };
    const thatBai = err => {
      if (daChot) return;
      daChot = true;
      donDep();
      reject(err);
    };
    const thanhCong = val => {
      if (daChot) return;
      daChot = true;
      donDep();
      resolve(val);
    };

    const req = client.request({
      protocol: parsed.protocol,
      hostname: parsed.hostname,
      port: parsed.port || (laHttp ? 80 : 443),
      path: parsed.pathname + parsed.search,
      method,
      headers: reqHeaders,
      agent: laHttp ? undefined : httpsAgent,
    }, res => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        res.resume();
        let nextUrl;
        try {
          nextUrl = new URL(res.headers.location, urlStr).href;
        } catch (err) {
          thatBai(err);
          return;
        }
        donDep();
        const conLaiMs = Math.max(500, gioiHanMs - (Date.now() - batDau));
        guiRequestBuffer(nextUrl, {
          method: 'GET',
          headers: { 'User-Agent': 'Mozilla/5.0' },
          timeoutMs: conLaiMs,
          daHuy,
          dangKyHuy,
          _soChuyenHuong: _soChuyenHuong + 1,
        }).then(thanhCong, thatBai);
        return;
      }
      const chunks = [];
      res.on('data', chunk => {
        if (daHuy?.()) {
          const loi = taoLoiHuyCapcut();
          try { req.destroy(loi); } catch (_) {}
          thatBai(loi);
          return;
        }
        chunks.push(chunk);
      });
      res.on('error', thatBai);
      res.on('aborted', () => thatBai(new Error('CapCut ngắt kết nối giữa chừng')));
      res.on('end', () => {
        daKetThuc = true;
        if (daHuy?.()) {
          thatBai(taoLoiHuyCapcut());
          return;
        }
        const buf = Buffer.concat(chunks);
        if (res.statusCode < 200 || res.statusCode >= 300) {
          thatBai(new Error(`HTTP ${res.statusCode}: ${buf.toString('utf8').slice(0, 200)}`));
          return;
        }
        thanhCong(buf);
      });
      res.on('close', () => {
        if (!daKetThuc && !daChot) {
          thatBai(new Error('CapCut đóng luồng trước khi nhận đủ dữ liệu'));
        }
      });
    });

    const huyRequest = () => {
      const loi = taoLoiHuyCapcut();
      try { req.destroy(loi); } catch (_) {}
      thatBai(loi);
    };
    if (typeof dangKyHuy === 'function') {
      goHuy = dangKyHuy(huyRequest);
    }
    if (typeof daHuy === 'function') {
      henQuetHuy = setInterval(() => {
        if (daHuy()) huyRequest();
      }, 200);
      if (henQuetHuy.unref) henQuetHuy.unref();
    }
    henCung = setTimeout(() => {
      const loi = new Error(`Timeout after ${gioiHanMs}ms`);
      try { req.destroy(loi); } catch (_) {}
      thatBai(loi);
    }, gioiHanMs + Math.min(3000, gioiHanMs));
    if (henCung.unref) henCung.unref();

    req.setTimeout(gioiHanMs, () => {
      const loi = new Error(`Timeout after ${gioiHanMs}ms`);
      try { req.destroy(loi); } catch (_) {}
      thatBai(loi);
    });
    req.on('error', thatBai);
    if (bodyBuf) req.write(bodyBuf);
    req.end();
  });
}

async function postJson(urlStr, headers, bodyStr, timeoutMs = 12000, tuyChonHuy = {}) {
  const buf = await guiRequestBuffer(urlStr, {
    method: 'POST',
    headers,
    body: bodyStr,
    timeoutMs,
    daHuy: tuyChonHuy.daHuy || null,
    dangKyHuy: tuyChonHuy.dangKyHuy || null,
  });
  return JSON.parse(buf.toString('utf8'));
}

const DAU_CAU_BO = new Set(['。', '，', '.', ',', '!', '?', ';', ':', '…', '"', '“', '”', '(', ')']);

function gopUtterancesThanhTu(utterances) {
  if (!Array.isArray(utterances) || !utterances.length) return [];
  const layChu = u => String(u?.word ?? u?.text ?? '');
  const coKhoangTrang = utterances.some(u => {
    const w = layChu(u);
    return w.length > 0 && w.trim() === '';
  });
  if (!coKhoangTrang) {
    return utterances
      .filter(u => {
        const w = layChu(u).trim();
        return w && !DAU_CAU_BO.has(w);
      })
      .map(u => ({
        word: layChu(u).trim(),
        start: Math.round((Number(u.start_time || 0) / 1000) * 1000) / 1000,
        end: Math.round((Number(u.end_time || 0) / 1000) * 1000) / 1000,
      }));
  }
  const kq = [];
  let dangGop = null;
  const dayTu = () => {
    if (dangGop && dangGop.word.trim() && !DAU_CAU_BO.has(dangGop.word.trim())) {
      kq.push({
        word: dangGop.word.trim(),
        start: Math.round(dangGop.start * 1000) / 1000,
        end: Math.round(dangGop.end * 1000) / 1000,
      });
    }
    dangGop = null;
  };
  for (const u of utterances) {
    const raw = layChu(u);
    if (!raw) continue;
    if (!raw.trim() || DAU_CAU_BO.has(raw.trim())) {
      dayTu();
      continue;
    }
    const st = Number(u.start_time || 0) / 1000;
    const et = Number(u.end_time || 0) / 1000;
    if (!dangGop) {
      dangGop = { word: raw, start: st, end: Math.max(st, et) };
    } else {
      dangGop.word += raw;
      if (et >= dangGop.end) dangGop.end = et;
    }
  }
  dayTu();
  return kq;
}

function taoHeadersCapcut(url, device, region, stubText) {
  const qg = chuanHoaMaQuocGia(region);
  const now = String(Math.floor(Date.now() / 1000));
  const traceHex = crypto.randomUUID().replace(/-/g, '');
  const headers = {
    'content-type': 'application/json',
    'appvr': device.appvr,
    'ch': device.channel,
    'device-time': now,
    'lan': device.lan,
    'loc': qg,
    'pf': device.pf,
    'sign-ver': '1',
    'tdid': device.tdid,
    'x-ss-stub': md5Hex(stubText),
    'x-ss-dp': device.aid,
    'x-khronos': now,
    'x-tt-trace-id': `00-${traceHex}-${traceHex.slice(0, 16)}-01`,
    'user-agent': 'Cronet/TTNetVersion:1d7cc3b1 2025-07-16',
    'store-country-code': qg.toLowerCase(),
    'app-sdk-version': device.appvr,
    'appid': device.aid,
  };
  headers.sign = kyHeader(url, device.appvr, now, device.tdid);
  return headers;
}

function taoQueryChung(device, extra = {}) {
  const q = new URLSearchParams({
    app_name: device.app_name,
    device_type: device.device_type,
    os_version: device.os_version,
    channel: device.channel,
    version_name: device.version_name,
    device_brand: device.device_brand,
    device_id: device.device_id,
    iid: device.iid,
    version_code: device.version_code,
    device_platform: device.device_platform,
    aid: device.aid,
    ...extra,
  });
  return q.toString();
}

function ngu(ms, daHuy, dangKyHuy = null) {
  return new Promise((resolve, reject) => {
    if (daHuy?.()) {
      reject(taoLoiHuyCapcut());
      return;
    }
    let xong = false;
    let goHuy = null;
    const t = setTimeout(() => {
      if (xong) return;
      xong = true;
      if (goHuy) goHuy();
      resolve();
    }, ms);
    if (typeof dangKyHuy === 'function') {
      goHuy = dangKyHuy(() => {
        if (xong) return;
        xong = true;
        clearTimeout(t);
        reject(taoLoiHuyCapcut());
      });
    }
  });
}

function taoTaskSubmitCapcut({ text, giongObj, needTimestamp, device, babi, context }) {
  const tsAttr = needTimestamp ? 'true' : 'false';
  const ssml = `<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">\n`
    + `    <voice name="${giongObj.id}" mock_tone_info="" platform="sami" resource_id="${giongObj.resourceId || MAC_DINH_RESOURCE_ID}" emotion="" emotion_scale="0" style="" role="" moyin_emotion="" is_clone_tone="false" need_subtitle_timestamp="${tsAttr}">\n`
    + `        <prosody rate="1.0">${escapeXml(text)}</prosody>\n`
    + `    </voice>\n`
    + `</speak>`;
  const extraInfo = JSON.stringify({ benefit_info: {} });
  const payload = {
    audio_format: 'mp3',
    babi_param: babi,
    credit_disable: false,
    extra_info: extraInfo,
    need_merge_voice: false,
    need_subtitle_timestamp: Boolean(needTimestamp),
    scene: 'text_to_speech',
    ssml,
    sign: kyPayload(ssml, extraInfo, device.device_id, device.aid),
  };
  return {
    context: context || crypto.randomUUID(),
    payload: JSON.stringify(payload),
    req_key: 'sami_text_to_speech',
    task_version: 'v3',
  };
}

async function taiMp3Capcut(speechUrl, region, { timeoutMs = 15000, daHuy = null, dangKyHuy = null } = {}) {
  let loiCuoi = null;
  for (let lan = 0; lan < 2; lan++) {
    if (daHuy?.()) throw taoLoiHuyCapcut();
    try {
      const mp3Buffer = await guiRequestBuffer(speechUrl, {
        method: 'GET',
        headers: { 'User-Agent': 'Mozilla/5.0' },
        timeoutMs,
        daHuy,
        dangKyHuy,
      });
      if (!mp3Buffer || mp3Buffer.length < 400) {
        throw new Error(`CapCut (${region}) MP3 rỗng (${mp3Buffer ? mp3Buffer.length : 0}B)`);
      }
      return mp3Buffer;
    } catch (err) {
      if (daHuy?.() || err?.code === 'ABORTED') throw err;
      loiCuoi = err;
      if (lan === 0) await ngu(350, daHuy, dangKyHuy);
    }
  }
  throw loiCuoi;
}

function lamMoiThietBiNeuCan(slot, region, batBuoc = false) {
  if (!slot) return;
  slot.soLuotDung = (slot.soLuotDung || 0) + 1;
  if (batBuoc || slot.soLuotDung >= 20) {
    slot.device = taoThietBiAo(region);
    slot.soLuotDung = 0;
  }
}

function tinhNhipPollHangDoi(nhipHienTai, status, inq) {
  if (status === 'processing' || (Number.isFinite(inq) && inq >= 0 && inq <= 100)) {
    return Math.min(700, Math.max(350, nhipHienTai));
  }
  if (Number.isFinite(inq) && inq > 400) return 1800;
  if (Number.isFinite(inq) && inq > 100) return 1100;
  return Math.min(950, Math.round(nhipHienTai * 1.25));
}

/**
 * Tạo giọng 1 câu trên đúng 1 quốc gia cố định (`region`).
 */
async function goiCapcutMotCau({ slot, region = QUOC_GIA_MAC_DINH, text, giongObj, needTimestamp = false, daHuy = null, dangKyHuy = null }) {
  const qg = chuanHoaMaQuocGia(region);
  const activeSlot = slot || { soLuotDung: 0, device: taoThietBiAo(qg) };
  const device = activeSlot.device;
  const babi = JSON.stringify({
    feature_entrance: 'editor',
    feature_entrance_detail: 'editor-feature-text_to_speech',
    feature_key: 'text_to_speech',
    scenario: 'video_editor',
  });
  const bodySubmit = JSON.stringify({
    bind_id: crypto.randomUUID(),
    can_queue: true,
    enter_from: 'text_to_speech',
    tasks: [taoTaskSubmitCapcut({ text, giongObj, needTimestamp, device, babi })],
  });

  const batDau = Date.now();
  const hanCoBan = batDau + CHO_CO_BAN_MS;
  const hanToiDaHangDoi = batDau + CHO_TOI_DA_HANG_DOI_MS;
  const conLaiMs = (san = 1500, congThem = 0) => Math.max(san, hanToiDaHangDoi + congThem - Date.now());

  const submitUrl = `${BASE_URL}/lv/v1/common_task/new?${taoQueryChung(device, { region: qg, babi_param: babi })}`;
  const submitRes = await postJson(
    submitUrl,
    taoHeadersCapcut(submitUrl, device, qg, bodySubmit),
    bodySubmit,
    Math.min(10000, conLaiMs(2500)),
    { daHuy, dangKyHuy }
  );

  const taskInfo = submitRes?.data?.tasks?.[0];
  if (!taskInfo || !taskInfo.id || !taskInfo.token) {
    lamMoiThietBiNeuCan(activeSlot, qg, true);
    throw new Error(`CapCut (${qg}) không tạo được task: ${JSON.stringify(submitRes).slice(0, 180)}`);
  }

  const uocTinhMs = Number(taskInfo.estimated_time || 0);
  const inqBanDau = Number(taskInfo.inqueue_amount ?? NaN);
  if (uocTinhMs > CHO_TOI_DA_HANG_DOI_MS || (Number.isFinite(inqBanDau) && inqBanDau > 8000)) {
    throw new Error(`CapCut (${qg}) hàng đợi quá tải (~${Math.round(uocTinhMs / 1000)}s, inq=${inqBanDau || 0})`);
  }

  let inqueueThapNhat = Number.isFinite(inqBanDau) && inqBanDau >= 0 ? inqBanDau : Infinity;
  let mocTienTrienCuoi = Date.now();
  let dangTienTrien = true;
  let nhipPoll = inqueueThapNhat > 400 ? 1500 : (inqueueThapNhat > 100 ? 900 : 350);

  const quetMotLuot = async () => {
    const queryBody = JSON.stringify({
      tasks: [{
        bind_id: '',
        id: taskInfo.id,
        req_key: 'sami_text_to_speech',
        task_version: 'v3',
        token: taskInfo.token,
      }],
    });
    const queryUrl = `${BASE_URL}/lv/v1/common_task/query?${taoQueryChung(device)}`;
    const queryRes = await postJson(
      queryUrl,
      taoHeadersCapcut(queryUrl, device, qg, ''),
      queryBody,
      Math.min(8000, conLaiMs(2000)),
      { daHuy, dangKyHuy }
    );
    const t = queryRes?.data?.tasks?.[0] || {};
    const status = String(t.status || '');
    const inq = Number(t.inqueue_amount ?? NaN);

    if (status === 'succeed' || status === 'completed') {
      let parsedPayload = {};
      try { parsedPayload = JSON.parse(t.payload || '{}') || {}; } catch (_) {}
      const sub0 = (parsedPayload.audio_subtitles || [])[0] || {};
      const speechUrl = sub0.speech_url;
      if (!speechUrl) throw new Error(`CapCut (${qg}) thiếu speech_url`);
      const mp3Buffer = await taiMp3Capcut(speechUrl, qg, {
        timeoutMs: Math.min(15000, conLaiMs(4000, 8000)),
        daHuy,
        dangKyHuy,
      });
      lamMoiThietBiNeuCan(activeSlot, qg, false);
      const words = needTimestamp ? gopUtterancesThanhTu(sub0.utterances || []) : [];
      return {
        mp3Buffer,
        durationMs: Number(sub0.duration || 0),
        words,
        region: qg,
        voiceId: giongObj.id,
      };
    }
    if (status === 'failed' || status === 'error') {
      lamMoiThietBiNeuCan(activeSlot, qg, true);
      throw new Error(`CapCut (${qg}) task lỗi: ${status}`);
    }
    if (status === 'processing') {
      inqueueThapNhat = 0;
      mocTienTrienCuoi = Date.now();
    } else if (Number.isFinite(inq) && inq >= 0 && inq < inqueueThapNhat) {
      inqueueThapNhat = inq;
      mocTienTrienCuoi = Date.now();
    }
    nhipPoll = tinhNhipPollHangDoi(nhipPoll, status, inq);
    if (inqueueThapNhat > 0 && inqueueThapNhat < Infinity && (Date.now() - mocTienTrienCuoi) > HAN_KET_HANG_DOI_MS) {
      dangTienTrien = false;
    }
    return null;
  };

  while (Date.now() < hanCoBan) {
    if (daHuy?.()) throw taoLoiHuyCapcut();
    const choNgu = Math.min(nhipPoll, Math.max(50, hanCoBan - Date.now()));
    await ngu(choNgu, daHuy, dangKyHuy);
    if (Date.now() >= hanCoBan) break;
    const kq = await quetMotLuot();
    if (kq) return kq;
    if (!dangTienTrien) break;
  }

  while (dangTienTrien && inqueueThapNhat < Infinity && Date.now() < hanToiDaHangDoi && (Date.now() - mocTienTrienCuoi) <= HAN_KET_HANG_DOI_MS) {
    if (daHuy?.()) throw taoLoiHuyCapcut();
    const choNgu = Math.min(nhipPoll, Math.max(80, hanToiDaHangDoi - Date.now()));
    await ngu(choNgu, daHuy, dangKyHuy);
    if (Date.now() >= hanToiDaHangDoi) break;
    const kq = await quetMotLuot();
    if (kq) return kq;
  }

  lamMoiThietBiNeuCan(activeSlot, qg, true);
  const daChoGiay = Math.max(Math.round(CHO_CO_BAN_MS / 1000), Math.round((Date.now() - batDau) / 1000));
  throw new Error(`CapCut (${qg}) quá hạn ${daChoGiay}s`);
}

/**
 * Tạo giọng gom lô nhiều câu trong 1 lượt gọi trên đúng 1 quốc gia cố định (`region`).
 */
async function goiCapcutTheoLo({ slot, region = QUOC_GIA_MAC_DINH, danhSachMuc, daHuy = null, dangKyHuy = null }) {
  const qg = chuanHoaMaQuocGia(region);
  const mucHoatDong = (danhSachMuc || []).filter(m => !m.daHuyMuc?.());
  if (!mucHoatDong.length) throw taoLoiHuyCapcut();

  const activeSlot = slot || { soLuotDung: 0, device: taoThietBiAo(qg) };
  const device = activeSlot.device;
  const babi = JSON.stringify({
    feature_entrance: 'editor',
    feature_entrance_detail: 'editor-feature-text_to_speech',
    feature_key: 'text_to_speech',
    scenario: 'video_editor',
  });
  const tasksSubmit = mucHoatDong.map((m, i) => taoTaskSubmitCapcut({
    text: m.text,
    giongObj: m.giongObj,
    needTimestamp: m.needTimestamp,
    device,
    babi,
    context: `item_${i}`,
  }));
  const bodySubmit = JSON.stringify({
    bind_id: crypto.randomUUID(),
    can_queue: true,
    enter_from: 'text_to_speech',
    tasks: tasksSubmit,
  });

  const batDau = Date.now();
  const hanCoBan = batDau + CHO_CO_BAN_MS;
  const hanToiDaHangDoi = batDau + CHO_TOI_DA_HANG_DOI_MS;
  const conLaiMs = (san = 1500, congThem = 0) => Math.max(san, hanToiDaHangDoi + congThem - Date.now());
  const submitUrl = `${BASE_URL}/lv/v1/common_task/new?${taoQueryChung(device, { region: qg, babi_param: babi })}`;
  const submitRes = await postJson(
    submitUrl,
    taoHeadersCapcut(submitUrl, device, qg, bodySubmit),
    bodySubmit,
    Math.min(14000, conLaiMs(3500)),
    { daHuy, dangKyHuy }
  );

  const rawTasks = Array.isArray(submitRes?.data?.tasks) ? submitRes.data.tasks : [];
  if (!rawTasks.length) {
    lamMoiThietBiNeuCan(activeSlot, qg, true);
    throw new Error(`CapCut (${qg}) không tạo được lô task: ${JSON.stringify(submitRes).slice(0, 180)}`);
  }

  const thanhCong = new Map();
  const thatBai = new Map();
  const dangChoMap = new Map();
  const theoContext = new Map();
  for (const rt of rawTasks) {
    if (rt && rt.context) theoContext.set(String(rt.context), rt);
  }

  let maxUocTinhMs = 0;
  let minInqBanDau = Infinity;
  for (let i = 0; i < mucHoatDong.length; i++) {
    const m = mucHoatDong[i];
    const rt = theoContext.get(`item_${i}`) || rawTasks[i];
    if (!rt || !rt.id || !rt.token) {
      thatBai.set(m.idxLo, new Error(`CapCut (${qg}) thiếu id/token cho phần tử ${i}`));
      continue;
    }
    const est = Number(rt.estimated_time || 0);
    const inq = Number(rt.inqueue_amount ?? NaN);
    if (est > maxUocTinhMs) maxUocTinhMs = est;
    if (Number.isFinite(inq) && inq >= 0 && inq < minInqBanDau) minInqBanDau = inq;
    dangChoMap.set(String(rt.id), { muc: m, id: String(rt.id), token: String(rt.token) });
  }

  if (!dangChoMap.size) {
    lamMoiThietBiNeuCan(activeSlot, qg, true);
    const loiDau = thatBai.values().next().value;
    throw loiDau || new Error(`CapCut (${qg}) không khởi tạo được task nào trong lô`);
  }

  if (maxUocTinhMs > CHO_TOI_DA_HANG_DOI_MS || (Number.isFinite(minInqBanDau) && minInqBanDau > 8000)) {
    throw new Error(`CapCut (${qg}) hàng đợi quá tải (~${Math.round(maxUocTinhMs / 1000)}s, inq=${minInqBanDau})`);
  }

  let inqueueThapNhat = minInqBanDau;
  let mocTienTrienCuoi = Date.now();
  let nhipPoll = inqueueThapNhat > 400 ? 1600 : (inqueueThapNhat > 100 ? 950 : 400);
  const hangTaiMp3 = [];
  let dangTai = 0;
  const TRAN_TAI_MP3_TREN_VAN = 5;
  const dayTaiMp3 = fn => new Promise(resolve => {
    const chay = () => {
      dangTai++;
      Promise.resolve().then(fn).finally(() => {
        dangTai--;
        if (hangTaiMp3.length > 0) hangTaiMp3.shift()();
        resolve();
      });
    };
    if (dangTai < TRAN_TAI_MP3_TREN_VAN) chay();
    else hangTaiMp3.push(chay);
  });
  const cacTacVuTaiMp3 = [];

  while (dangChoMap.size > 0) {
    if (daHuy?.()) throw taoLoiHuyCapcut();
    for (const [tid, entry] of [...dangChoMap.entries()]) {
      if (entry.muc.daHuyMuc?.()) dangChoMap.delete(tid);
    }
    if (!dangChoMap.size) break;

    const bayGio = Date.now();
    const quaHanCoBan = bayGio >= hanCoBan;
    const hangDoiBiDongBang = inqueueThapNhat > 0
      && inqueueThapNhat < Infinity
      && (bayGio - mocTienTrienCuoi) > HAN_KET_HANG_DOI_MS;
    const conQuyenGiaHan = inqueueThapNhat < Infinity
      && bayGio < hanToiDaHangDoi
      && (bayGio - mocTienTrienCuoi) <= HAN_KET_HANG_DOI_MS;
    if (hangDoiBiDongBang) break;
    if (quaHanCoBan && !conQuyenGiaHan) break;

    const mocGioiHan = quaHanCoBan ? hanToiDaHangDoi : Math.max(hanCoBan, inqueueThapNhat < Infinity ? hanToiDaHangDoi : hanCoBan);
    const choNgu = Math.min(nhipPoll, Math.max(60, mocGioiHan - bayGio));
    await ngu(choNgu, daHuy, dangKyHuy);
    if (daHuy?.()) throw taoLoiHuyCapcut();

    const danhSachTruyVan = [...dangChoMap.values()].map(e => ({
      bind_id: '',
      id: e.id,
      req_key: 'sami_text_to_speech',
      task_version: 'v3',
      token: e.token,
    }));
    if (!danhSachTruyVan.length) break;

    const queryUrl = `${BASE_URL}/lv/v1/common_task/query?${taoQueryChung(device)}`;
    const queryBody = JSON.stringify({ tasks: danhSachTruyVan });
    const queryRes = await postJson(
      queryUrl,
      taoHeadersCapcut(queryUrl, device, qg, ''),
      queryBody,
      Math.min(10000, conLaiMs(2500)),
      { daHuy, dangKyHuy }
    );

    const kqTasks = Array.isArray(queryRes?.data?.tasks) ? queryRes.data.tasks : [];
    let minInqLuot = Infinity;
    let coProcessing = false;
    let coTaskXongLuotNay = false;

    for (const t of kqTasks) {
      const tid = String(t?.id || '');
      const entry = dangChoMap.get(tid);
      if (!entry) continue;
      const status = String(t.status || '');
      const inq = Number(t.inqueue_amount ?? NaN);
      if (status === 'succeed' || status === 'completed') {
        dangChoMap.delete(tid);
        coTaskXongLuotNay = true;
        let parsedPayload = {};
        try { parsedPayload = JSON.parse(t.payload || '{}') || {}; } catch (_) {}
        const sub0 = (parsedPayload.audio_subtitles || [])[0] || {};
        const speechUrl = sub0.speech_url;
        if (!speechUrl) {
          thatBai.set(entry.muc.idxLo, new Error(`CapCut (${qg}) thiếu speech_url`));
          continue;
        }
        cacTacVuTaiMp3.push(dayTaiMp3(async () => {
          if (entry.muc.daHuyMuc?.()) return;
          try {
            const mp3Buffer = await taiMp3Capcut(speechUrl, qg, {
              timeoutMs: Math.min(15000, conLaiMs(4500, 10000)),
              daHuy: () => Boolean(daHuy?.() || entry.muc.daHuyMuc?.()),
              dangKyHuy,
            });
            const words = entry.muc.needTimestamp ? gopUtterancesThanhTu(sub0.utterances || []) : [];
            thanhCong.set(entry.muc.idxLo, {
              mp3Buffer,
              durationMs: Number(sub0.duration || 0),
              words,
              region: qg,
              voiceId: entry.muc.giongObj.id,
            });
          } catch (errTai) {
            thatBai.set(entry.muc.idxLo, errTai);
          }
        }));
      } else if (status === 'failed' || status === 'error') {
        dangChoMap.delete(tid);
        coTaskXongLuotNay = true;
        thatBai.set(entry.muc.idxLo, new Error(`CapCut (${qg}) task lỗi: ${status}`));
      } else {
        if (status === 'processing') coProcessing = true;
        if (Number.isFinite(inq) && inq >= 0 && inq < minInqLuot) minInqLuot = inq;
      }
    }

    if (coTaskXongLuotNay || coProcessing) {
      if (coProcessing) inqueueThapNhat = 0;
      mocTienTrienCuoi = Date.now();
    } else if (minInqLuot < inqueueThapNhat) {
      inqueueThapNhat = minInqLuot;
      mocTienTrienCuoi = Date.now();
    }
    nhipPoll = tinhNhipPollHangDoi(nhipPoll, coProcessing ? 'processing' : 'queueing', minInqLuot);
  }

  if (cacTacVuTaiMp3.length > 0) {
    await Promise.all(cacTacVuTaiMp3);
  }

  const coTreHan = dangChoMap.size > 0;
  if (coTreHan) {
    const daChoGiay = Math.max(Math.round(CHO_CO_BAN_MS / 1000), Math.round((Date.now() - batDau) / 1000));
    const loiQuaHan = new Error(`CapCut (${qg}) quá hạn ${daChoGiay}s`);
    for (const entry of dangChoMap.values()) {
      if (!entry.muc.daHuyMuc?.()) thatBai.set(entry.muc.idxLo, loiQuaHan);
    }
  }
  lamMoiThietBiNeuCan(activeSlot, qg, coTreHan || thanhCong.size === 0);
  return { thanhCong, thatBai };
}

const RE_TIEN_TO_LA_MA_VI = /(?:thế\s+kỷ|thứ|cấp(?:\s+độ)?|phần|tập|chương|hồi|quyển|điều|khoản|mục|loại|bậc|mức(?:\s+độ)?|hạng|lần|đời|lớp|quận|vành\s+đai)(?:\s+thứ)?\s*$/iu;

function chuanHoaAmViCapcut(chu) {
  const raw = String(chu || '');
  if (!raw) return '';
  return raw.replace(/(?<![\p{L}\p{N}])(v)(i)(?![\p{L}\p{N}])/giu, (khop, v, _i, viTri, toanCau) => {
    if (khop === 'VI') {
      const truoc = toanCau.slice(Math.max(0, viTri - 32), viTri);
      if (RE_TIEN_TO_LA_MA_VI.test(truoc)) return 'sáu';
      return 'Vy';
    }
    return v === 'V' ? 'Vy' : 'vy';
  });
}

function lamSachVanBanDauVao(text, giongObj) {
  const laNgoaiNgu = giongObj?.lang === 'th' || giongObj?.lang === 'ko';
  const chu = laNgoaiNgu
    ? String(text || '')
    : chuanHoaAmViCapcut(
        String(text || '')
          .replace(/(^|\s)(?:ngh|ng|nh|ch|gh|kh|ph|th|tr|qu|[bcdđghklmnpqrstvx])(?=\s*(?:\.{2,}|…|—|--)\s*$)/iu, '')
          .replace(/\s+([.,!?;:…])/g, '$1')
      );
  let sach = chu.replace(/\s+/g, ' ').trim();
  if (!sach) throw new Error('CapCut: văn bản rỗng');
  if (laNgoaiNgu && sach.length > MAX_KY_TU) {
    const tenNn = giongObj.lang === 'ko' ? 'tiếng Hàn' : 'tiếng Thái';
    throw new Error(`Câu ${tenNn} quá dài (${sach.length} > ${MAX_KY_TU} ký tự). Hãy chia câu ngắn hơn.`);
  }
  if (sach.length > MAX_KY_TU) sach = sach.slice(0, MAX_KY_TU);
  return sach;
}

/**
 * Bộ điều phối tạo giọng CapCut cố định 1 quốc gia duy nhất (KHÔNG xoay quốc gia).
 */
class BoTaoGiongCapCut {
  constructor({
    region = QUOC_GIA_MAC_DINH,
    soVanToiDa = 6,
    kichThuocLo = KICH_THUOC_LO_CAPCUT,
    gomLoMs = CUA_SO_GOM_LO_MS,
    uuTienCauDau = true,
    soLanThuLaiCungQuocGia = 1,
    goiMotCau = null,
    goiTheoLo = null,
  } = {}) {
    this.region = chuanHoaMaQuocGia(region);
    this.soVanToiDa = Math.max(1, Math.min(16, Number(soVanToiDa) || 6));
    this._kichThuocLo = Math.max(1, Math.min(25, Number(kichThuocLo) || KICH_THUOC_LO_CAPCUT));
    this._gomLoMs = gomLoMs != null ? Math.max(0, Number(gomLoMs) || 0) : CUA_SO_GOM_LO_MS;
    this._uuTienCauDau = uuTienCauDau !== false;
    this._soLanThuLai = Math.max(0, Math.min(2, Number(soLanThuLaiCungQuocGia) ?? 1));
    this._goiMotCau = typeof goiMotCau === 'function' ? goiMotCau : goiCapcutMotCau;
    this._goiTheoLo = typeof goiTheoLo === 'function'
      ? goiTheoLo
      : (this._goiMotCau === goiCapcutMotCau ? goiCapcutTheoLo : null);

    this.cacVan = Array.from({ length: this.soVanToiDa }, (_, idx) => ({
      idx,
      ban: false,
      jobId: null,
      batDauLuc: 0,
      soLuotDung: 0,
      device: taoThietBiAo(this.region),
    }));
    this.cacJob = new Map();
    this._thuTuLuot = 0;
    this._thuTuJob = 0;
    this._henHuy = null;
    this._henBomLo = null;
  }

  datQuocGiaCoDinh(region) {
    const qg = chuanHoaMaQuocGia(region);
    this.region = qg;
    for (const van of this.cacVan) {
      if (!van.ban) {
        van.device = taoThietBiAo(qg);
        van.soLuotDung = 0;
      }
    }
    return this.region;
  }

  datSoVan(soVan) {
    const moi = Math.max(1, Math.min(16, Number(soVan) || 6));
    while (this.cacVan.length < moi) {
      const idx = this.cacVan.length;
      this.cacVan.push({
        idx,
        ban: false,
        jobId: null,
        batDauLuc: 0,
        soLuotDung: 0,
        device: taoThietBiAo(this.region),
      });
    }
    this.soVanToiDa = moi;
    this._kichHoatBom();
    return this.soVanToiDa;
  }

  _coMucDangCho() {
    for (const job of this.cacJob.values()) {
      if (job.hang.length > 0) return true;
    }
    return false;
  }

  _tongMucDangCho() {
    let tong = 0;
    for (const job of this.cacJob.values()) tong += job.hang.length;
    return tong;
  }

  _soVanRanhHienTai() {
    let ranh = 0;
    for (let i = 0; i < this.soVanToiDa && i < this.cacVan.length; i++) {
      if (!this.cacVan[i].ban) ranh++;
    }
    return ranh;
  }

  _huyHenBomLo() {
    if (this._henBomLo) {
      clearTimeout(this._henBomLo);
      this._henBomLo = null;
    }
  }

  _kichHoatBom() {
    if (!this._goiTheoLo) {
      this._huyHenBomLo();
      this._bomViecDon();
      return;
    }
    const ranh = this._soVanRanhHienTai();
    if (ranh <= 0) {
      this._capNhatHenHuy();
      return;
    }
    if (this._gomLoMs <= 0 || this._tongMucDangCho() >= ranh * this._kichThuocLo) {
      this._huyHenBomLo();
      this._bomViecLo();
      return;
    }
    if (!this._henBomLo) {
      this._henBomLo = setTimeout(() => {
        this._henBomLo = null;
        this._bomViecLo();
      }, this._gomLoMs);
    }
    this._capNhatHenHuy();
  }

  _capNhatHenHuy() {
    if (this._coMucDangCho()) {
      if (!this._henHuy) {
        this._henHuy = setInterval(() => {
          this._quetHuy();
          if (!this._coMucDangCho()) this._capNhatHenHuy();
        }, 200);
        if (this._henHuy.unref) this._henHuy.unref();
      }
    } else {
      this._huyHenBomLo();
      if (this._henHuy) {
        clearInterval(this._henHuy);
        this._henHuy = null;
      }
    }
  }

  _quetHuy() {
    for (const [maJob, job] of this.cacJob.entries()) {
      for (let i = job.hang.length - 1; i >= 0; i--) {
        if (job.hang[i].daHuy?.()) {
          const [muc] = job.hang.splice(i, 1);
          muc.reject(taoLoiHuyCapcut());
        }
      }
      if (!job.hang.length && job.dangChay <= 0) {
        this.cacJob.delete(maJob);
      }
    }
  }

  huyJob(jobId) {
    const maJob = String(jobId || 'default');
    const job = this.cacJob.get(maJob);
    if (!job) return 0;
    const biHuy = job.hang.splice(0, job.hang.length);
    for (const muc of biHuy) {
      muc.reject(taoLoiHuyCapcut());
    }
    let dangChayBiHuy = 0;
    if (job.dangChayMuc && job.dangChayMuc.size > 0) {
      for (const fnHuy of [...job.dangChayMuc]) {
        job.dangChayMuc.delete(fnHuy);
        if (fnHuy()) dangChayBiHuy++;
      }
    }
    if (job.dangChay <= 0) this.cacJob.delete(maJob);
    this._capNhatHenHuy();
    return biHuy.length + dangChayBiHuy;
  }

  layVanRanh() {
    for (let i = 0; i < this.soVanToiDa && i < this.cacVan.length; i++) {
      if (!this.cacVan[i].ban) return this.cacVan[i];
    }
    return null;
  }

  _layMucTiepTheo() {
    this._quetHuy();
    const ungVien = [];
    for (const job of this.cacJob.values()) {
      if (job.hang.length > 0) ungVien.push(job);
    }
    if (!ungVien.length) return null;
    ungVien.sort((a, b) => (a.dangChay - b.dangChay) || (a.luotCuoi - b.luotCuoi) || (a.thuTuTao - b.thuTuTao));
    const jobChon = ungVien[0];
    const muc = jobChon.hang.shift();
    jobChon.dangChay++;
    jobChon.luotCuoi = ++this._thuTuLuot;
    jobChon.soDaCap++;
    return { job: jobChon, muc };
  }

  _layLoTiepTheo(soVanRanh) {
    this._quetHuy();
    const ungVien = [];
    for (const job of this.cacJob.values()) {
      if (job.hang.length > 0) ungVien.push(job);
    }
    if (!ungVien.length) return null;
    ungVien.sort((a, b) => (a.dangChay - b.dangChay) || (a.luotCuoi - b.luotCuoi) || (a.thuTuTao - b.thuTuTao));
    const jobChon = ungVien[0];
    let coLo = 1;
    if (this._uuTienCauDau && jobChon.soDaCap === 0 && soVanRanh >= 2 && jobChon.hang.length >= 2) {
      coLo = 1;
    } else {
      const vanChiaChoJob = Math.max(1, Math.floor(Math.max(1, soVanRanh) / Math.max(1, ungVien.length)));
      coLo = Math.max(1, Math.min(this._kichThuocLo, Math.ceil(jobChon.hang.length / vanChiaChoJob)));
    }
    const loMuc = jobChon.hang.splice(0, coLo);
    jobChon.dangChay++;
    jobChon.luotCuoi = ++this._thuTuLuot;
    jobChon.soDaCap += loMuc.length;
    return { job: jobChon, loMuc };
  }

  _bomViecDon() {
    this._quetHuy();
    for (;;) {
      const van = this.layVanRanh();
      if (!van) break;
      const ke = this._layMucTiepTheo();
      if (!ke) break;
      const { job, muc } = ke;
      van.ban = true;
      van.jobId = job.maJob;
      van.batDauLuc = Date.now();

      let daHuyMuc = false;
      const tapHuy = new Set();
      const daHuyKetHop = () => daHuyMuc || Boolean(muc.daHuy?.());
      const dangKyHuy = fn => {
        if (daHuyKetHop()) {
          try { fn(); } catch (_) {}
          return () => {};
        }
        tapHuy.add(fn);
        return () => tapHuy.delete(fn);
      };
      const kichHoatHuy = () => {
        if (daHuyMuc) return false;
        daHuyMuc = true;
        for (const fn of [...tapHuy]) {
          tapHuy.delete(fn);
          try { fn(); } catch (_) {}
        }
        muc.reject(taoLoiHuyCapcut());
        return true;
      };
      job.dangChayMuc.add(kichHoatHuy);

      this._thucThiDonTrenMotQuocGia(van, { ...muc, daHuy: daHuyKetHop, dangKyHuy })
        .then(muc.resolve, muc.reject)
        .finally(() => {
          job.dangChayMuc.delete(kichHoatHuy);
          tapHuy.clear();
          van.ban = false;
          van.jobId = null;
          van.batDauLuc = 0;
          job.dangChay = Math.max(0, job.dangChay - 1);
          if (job.dangChay <= 0 && !job.hang.length) {
            this.cacJob.delete(job.maJob);
          }
          this._capNhatHenHuy();
          this._bomViecDon();
        });
    }
    this._capNhatHenHuy();
  }

  _bomViecLo() {
    this._huyHenBomLo();
    this._quetHuy();
    for (;;) {
      const soVanRanh = this._soVanRanhHienTai();
      if (soVanRanh <= 0) break;
      const van = this.layVanRanh();
      if (!van) break;
      const ke = this._layLoTiepTheo(soVanRanh);
      if (!ke) break;
      const { job, loMuc } = ke;
      van.ban = true;
      van.jobId = job.maJob;
      van.batDauLuc = Date.now();

      let daHuyLo = false;
      const tapHuy = new Set();
      const daChot = new Set();
      const chotThanhCong = (idxLo, kq) => {
        if (daChot.has(idxLo)) return;
        daChot.add(idxLo);
        loMuc[idxLo].resolve(kq);
      };
      const chotThatBai = (idxLo, err) => {
        if (daChot.has(idxLo)) return;
        daChot.add(idxLo);
        loMuc[idxLo].reject(err);
      };
      const tatCaMucDaHuy = () => daHuyLo || loMuc.every((m, idxLo) => daChot.has(idxLo) || Boolean(m.daHuy?.()));
      const dangKyHuy = fn => {
        if (tatCaMucDaHuy()) {
          try { fn(); } catch (_) {}
          return () => {};
        }
        tapHuy.add(fn);
        return () => tapHuy.delete(fn);
      };
      const kichHoatHuy = () => {
        if (daHuyLo) return false;
        daHuyLo = true;
        for (const fn of [...tapHuy]) {
          tapHuy.delete(fn);
          try { fn(); } catch (_) {}
        }
        let soBiHuy = 0;
        const loiHuy = taoLoiHuyCapcut();
        for (let i = 0; i < loMuc.length; i++) {
          if (!daChot.has(i)) {
            soBiHuy++;
            chotThatBai(i, loiHuy);
          }
        }
        return soBiHuy > 0;
      };

      job.dangChayMuc.add(kichHoatHuy);
      this._thucThiLoTrenMotQuocGia(van, loMuc, {
        daChot,
        chotThanhCong,
        chotThatBai,
        daHuy: tatCaMucDaHuy,
        dangKyHuy,
      }).catch(err => {
        for (let i = 0; i < loMuc.length; i++) {
          chotThatBai(i, err);
        }
      }).finally(() => {
        job.dangChayMuc.delete(kichHoatHuy);
        tapHuy.clear();
        van.ban = false;
        van.jobId = null;
        van.batDauLuc = 0;
        job.dangChay = Math.max(0, job.dangChay - 1);
        if (job.dangChay <= 0 && !job.hang.length) {
          this.cacJob.delete(job.maJob);
        }
        this._capNhatHenHuy();
        this._kichHoatBom();
      });
    }
    this._capNhatHenHuy();
  }

  async _thucThiDonTrenMotQuocGia(van, muc) {
    const qg = muc.region ? chuanHoaMaQuocGia(muc.region) : this.region;
    if (van.device?.region !== qg) {
      van.device = taoThietBiAo(qg);
      van.soLuotDung = 0;
    }
    let loiCuoi = null;
    for (let luot = 0; luot <= this._soLanThuLai; luot++) {
      if (muc.daHuy?.()) throw taoLoiHuyCapcut();
      if (luot > 0) {
        van.device = taoThietBiAo(qg);
        van.soLuotDung = 0;
        await ngu(800, muc.daHuy, muc.dangKyHuy);
      }
      try {
        return await this._goiMotCau({
          slot: van,
          region: qg,
          text: muc.text,
          giongObj: muc.giongObj,
          needTimestamp: muc.needTimestamp,
          daHuy: muc.daHuy,
          dangKyHuy: muc.dangKyHuy,
        });
      } catch (err) {
        if (err?.code === 'ABORTED' || muc.daHuy?.()) throw err;
        loiCuoi = err;
      }
    }
    throw loiCuoi || new Error(`CapCut (${qg}) tạo giọng thất bại.`);
  }

  async _thucThiLoTrenMotQuocGia(van, loMuc, { daChot, chotThanhCong, chotThatBai, daHuy, dangKyHuy }) {
    const qg = loMuc[0]?.region ? chuanHoaMaQuocGia(loMuc[0].region) : this.region;
    if (van.device?.region !== qg) {
      van.device = taoThietBiAo(qg);
      van.soLuotDung = 0;
    }

    const layDanhSachConLai = () => {
      const con = [];
      for (let i = 0; i < loMuc.length; i++) {
        if (daChot.has(i)) continue;
        if (loMuc[i].daHuy?.()) {
          chotThatBai(i, taoLoiHuyCapcut());
          continue;
        }
        con.push({
          idxLo: i,
          text: loMuc[i].text,
          giongObj: loMuc[i].giongObj,
          needTimestamp: loMuc[i].needTimestamp,
          daHuyMuc: () => daChot.has(i) || Boolean(loMuc[i].daHuy?.()),
        });
      }
      return con;
    };

    let loiCuoi = null;
    for (let luot = 0; luot <= this._soLanThuLai; luot++) {
      const conLai = layDanhSachConLai();
      if (!conLai.length) return;
      if (daHuy?.()) throw taoLoiHuyCapcut();
      if (luot > 0) {
        van.device = taoThietBiAo(qg);
        van.soLuotDung = 0;
        await ngu(900, daHuy, dangKyHuy);
      }
      try {
        const { thanhCong, thatBai } = await this._goiTheoLo({
          slot: van,
          region: qg,
          danhSachMuc: conLai,
          daHuy,
          dangKyHuy,
        });
        if (thanhCong && thanhCong.size > 0) {
          for (const [idxLo, kq] of thanhCong.entries()) {
            chotThanhCong(idxLo, kq);
          }
        }
        if (thatBai && thatBai.size > 0) {
          for (const errMuc of thatBai.values()) {
            loiCuoi = errMuc;
          }
        }
        if (!layDanhSachConLai().length) return;
      } catch (err) {
        if (err?.code === 'ABORTED' || daHuy?.()) throw err;
        loiCuoi = err;
      }
    }

    const conSot = layDanhSachConLai();
    for (const m of conSot) {
      chotThatBai(m.idxLo, loiCuoi || new Error(`CapCut (${qg}) tạo lô giọng thất bại.`));
    }
  }

  taoGiong({ text, voice, lang, region = '', jobId = 'default', needTimestamp = false, signal = null, daHuy = null } = {}) {
    let giongObj;
    let sach;
    try {
      giongObj = chonGiongHopLe(voice, lang);
      sach = lamSachVanBanDauVao(text, giongObj);
    } catch (err) {
      return Promise.reject(err);
    }
    const checkCancel = () => Boolean(signal?.aborted || daHuy?.());
    const qg = region ? chuanHoaMaQuocGia(region) : this.region;
    const maJob = String(jobId || 'default');

    return new Promise((resolve, reject) => {
      if (checkCancel()) {
        reject(taoLoiHuyCapcut());
        return;
      }
      let job = this.cacJob.get(maJob);
      if (!job) {
        job = {
          maJob,
          dangChay: 0,
          luotCuoi: 0,
          soDaCap: 0,
          thuTuTao: ++this._thuTuJob,
          hang: [],
          dangChayMuc: new Set(),
        };
        this.cacJob.set(maJob, job);
      }
      job.hang.push({ text: sach, giongObj, region: qg, needTimestamp, daHuy: checkCancel, resolve, reject });
      this._kichHoatBom();
    });
  }
}

function docThoiLuongWavPcm(raWav) {
  let fd = null;
  try {
    const st = fs.statSync(raWav);
    if (!st.isFile() || st.size <= 44) return 0;
    const n = Math.min(st.size, 512);
    const buf = Buffer.allocUnsafe(n);
    fd = fs.openSync(raWav, 'r');
    const docDuoc = fs.readSync(fd, buf, 0, n, 0);
    fs.closeSync(fd);
    fd = null;
    if (docDuoc < 44 || buf.toString('ascii', 0, 4) !== 'RIFF' || buf.toString('ascii', 8, 12) !== 'WAVE') return 0;
    let off = 12;
    let byteRate = 0;
    let dataLen = 0;
    while (off + 8 <= docDuoc) {
      const id = buf.toString('ascii', off, off + 4);
      const sz = buf.readUInt32LE(off + 4);
      if (id === 'fmt ' && sz >= 16 && off + 24 <= docDuoc) {
        byteRate = buf.readUInt32LE(off + 16);
      } else if (id === 'data') {
        dataLen = Math.min(sz, Math.max(0, st.size - (off + 8)));
        break;
      }
      off += 8 + sz + (sz % 2);
    }
    if (byteRate <= 0 || dataLen <= 0) return 0;
    const giay = dataLen / byteRate;
    return Number.isFinite(giay) && giay > 0 ? Math.round(giay * 1000) / 1000 : 0;
  } catch (_) {
    if (fd != null) {
      try { fs.closeSync(fd); } catch (__) {}
    }
    return 0;
  }
}

function catLangBienWavPcm(raWav, { demDauMs = 6, demCuoiMs = 32, nguongBienDo = 165 } = {}) {
  try {
    const buf = fs.readFileSync(raWav);
    if (buf.length <= 64 || buf.toString('ascii', 0, 4) !== 'RIFF' || buf.toString('ascii', 8, 12) !== 'WAVE') return false;
    let off = 12;
    let audioFmt = 0;
    let channels = 0;
    let sampleRate = 0;
    let bitsPerSample = 0;
    let dataOff = -1;
    let dataLen = 0;
    while (off + 8 <= buf.length) {
      const id = buf.toString('ascii', off, off + 4);
      const sz = buf.readUInt32LE(off + 4);
      if (id === 'fmt ' && sz >= 16 && off + 8 + sz <= buf.length) {
        audioFmt = buf.readUInt16LE(off + 8);
        channels = buf.readUInt16LE(off + 10);
        sampleRate = buf.readUInt32LE(off + 12);
        bitsPerSample = buf.readUInt16LE(off + 22);
      } else if (id === 'data') {
        dataOff = off + 8;
        dataLen = Math.min(sz, buf.length - dataOff);
        break;
      }
      off += 8 + sz + (sz % 2);
    }
    const laInt16 = audioFmt === 1 && bitsPerSample === 16;
    const laFloat32 = audioFmt === 3 && bitsPerSample === 32;
    if ((!laInt16 && !laFloat32) || channels < 1 || sampleRate < 8000 || dataOff < 0 || dataLen <= 0) return false;
    const bytesPerSample = laInt16 ? 2 : 4;
    const step = channels * bytesPerSample;
    const totalFrames = Math.floor(dataLen / step);
    if (totalFrames < Math.round(sampleRate * 0.15)) return false;
    const nguong = laInt16 ? nguongBienDo : (nguongBienDo / 32768);
    const docMau = viTri => {
      if (laInt16) return Math.abs(buf.readInt16LE(viTri));
      const v = buf.readFloatLE(viTri);
      return Number.isFinite(v) ? Math.abs(v) : 0;
    };
    let first = 0;
    while (first < totalFrames) {
      let mx = 0;
      const base = dataOff + first * step;
      for (let c = 0; c < channels; c++) mx = Math.max(mx, docMau(base + c * bytesPerSample));
      if (mx >= nguong) break;
      first++;
    }
    if (first >= totalFrames) return false;
    let last = totalFrames - 1;
    while (last > first) {
      let mx = 0;
      const base = dataOff + last * step;
      for (let c = 0; c < channels; c++) mx = Math.max(mx, docMau(base + c * bytesPerSample));
      if (mx >= nguong) break;
      last--;
    }
    const startFrame = Math.max(0, first - Math.round((sampleRate * demDauMs) / 1000));
    const endFrame = Math.min(totalFrames - 1, last + Math.round((sampleRate * demCuoiMs) / 1000));
    const newFrames = endFrame - startFrame + 1;
    if ((startFrame === 0 && endFrame === totalFrames - 1) || newFrames < Math.round(sampleRate * 0.12)) return false;

    const pcmSlice = Buffer.from(buf.subarray(dataOff + startFrame * step, dataOff + (endFrame + 1) * step));
    const fadeInFrames = startFrame > 0 ? Math.min(newFrames, Math.round(sampleRate * 0.004)) : 0;
    const fadeOutFrames = endFrame < totalFrames - 1 ? Math.min(newFrames, Math.round(sampleRate * 0.006)) : 0;
    const nhanHeSo = (p, k) => {
      if (laInt16) pcmSlice.writeInt16LE(Math.round(pcmSlice.readInt16LE(p) * k), p);
      else pcmSlice.writeFloatLE((Number.isFinite(pcmSlice.readFloatLE(p)) ? pcmSlice.readFloatLE(p) : 0) * k, p);
    };
    for (let i = 0; i < fadeInFrames; i++) {
      const k = i / fadeInFrames;
      for (let c = 0; c < channels; c++) nhanHeSo(i * step + c * bytesPerSample, k);
    }
    for (let i = 0; i < fadeOutFrames; i++) {
      const k = i / fadeOutFrames;
      const fIdx = newFrames - 1 - i;
      for (let c = 0; c < channels; c++) nhanHeSo(fIdx * step + c * bytesPerSample, k);
    }

    const header = Buffer.alloc(44);
    header.write('RIFF', 0, 4, 'ascii');
    header.writeUInt32LE(36 + pcmSlice.length, 4);
    header.write('WAVE', 8, 4, 'ascii');
    header.write('fmt ', 12, 4, 'ascii');
    header.writeUInt32LE(16, 16);
    header.writeUInt16LE(audioFmt, 20);
    header.writeUInt16LE(channels, 22);
    header.writeUInt32LE(sampleRate, 24);
    header.writeUInt32LE(sampleRate * step, 28);
    header.writeUInt16LE(step, 32);
    header.writeUInt16LE(bitsPerSample, 34);
    header.write('data', 36, 4, 'ascii');
    header.writeUInt32LE(pcmSlice.length, 40);
    const tamWav = `${raWav}.trim_${process.pid}_${Date.now()}`;
    fs.writeFileSync(tamWav, Buffer.concat([header, pcmSlice]));
    fs.renameSync(tamWav, raWav);
    return true;
  } catch (_) {
    return false;
  }
}

function chuyenMp3SangWavPcm({
  ffmpeg = 'ffmpeg',
  mp3Buffer,
  raWav,
  noiLam = '',
  sampleRate = 48000,
  channels = 1,
  trimSilence = true,
  daHuy = null,
} = {}) {
  return new Promise((resolve, reject) => {
    if (daHuy?.()) {
      reject(taoLoiHuyCapcut());
      return;
    }
    const thuMucTam = noiLam || path.dirname(raWav);
    fs.mkdirSync(thuMucTam, { recursive: true });
    fs.mkdirSync(path.dirname(raWav), { recursive: true });
    const tamMp3 = path.join(thuMucTam, `_capcut_raw_${crypto.randomUUID()}.mp3`);
    try {
      fs.writeFileSync(tamMp3, mp3Buffer);
    } catch (err) {
      reject(err);
      return;
    }

    const xoaTam = () => {
      try { fs.unlinkSync(tamMp3); } catch (_) {}
    };

    const p = execFile(
      ffmpeg,
      ['-nostdin', '-threads', '1', '-y', '-i', tamMp3, '-ar', String(sampleRate), '-ac', String(channels), '-c:a', 'pcm_s16le', raWav],
      { windowsHide: true, timeout: 60000, maxBuffer: 1048576 },
      (err, _stdout, stderr) => {
        xoaTam();
        if (daHuy?.()) {
          reject(taoLoiHuyCapcut());
          return;
        }
        if (err) {
          reject(new Error(`Giải mã MP3 CapCut sang WAV lỗi: ${stderr || err.message}`));
          return;
        }
        if (trimSilence) catLangBienWavPcm(raWav);
        resolve(raWav);
      }
    );
    p.on('error', err => {
      xoaTam();
      reject(new Error(`Không tìm thấy hoặc không chạy được FFmpeg (${ffmpeg}): ${err.message}`));
    });
  });
}

const boTaoGiongMacDinh = new BoTaoGiongCapCut({ region: QUOC_GIA_MAC_DINH });

/**
 * Tạo giọng và ghi thẳng ra tệp `.mp3` hoặc `.wav` (nếu đuôi `.wav` sẽ giải mã sang PCM 16-bit qua FFmpeg).
 */
async function taoGiongRaTep({
  text,
  voice = MAC_DINH_GIONG,
  lang = 'vi',
  region = QUOC_GIA_MAC_DINH,
  outPath,
  ffmpegPath = 'ffmpeg',
  sampleRate = 48000,
  channels = 1,
  trimSilence = true,
  needTimestamp = false,
  signal = null,
  daHuy = null,
} = {}) {
  if (!outPath) throw new Error('Thiếu đường dẫn tệp đầu ra (outPath).');
  fs.mkdirSync(path.dirname(path.resolve(outPath)), { recursive: true });
  const kq = await boTaoGiongMacDinh.taoGiong({
    text,
    voice,
    lang,
    region,
    needTimestamp,
    signal,
    daHuy,
  });

  if (/\.wav$/i.test(outPath)) {
    await chuyenMp3SangWavPcm({
      ffmpeg: ffmpegPath,
      mp3Buffer: kq.mp3Buffer,
      raWav: outPath,
      sampleRate,
      channels,
      trimSilence,
      daHuy: () => Boolean(signal?.aborted || daHuy?.()),
    });
    const durationSec = docThoiLuongWavPcm(outPath) || Number(((kq.durationMs || 0) / 1000).toFixed(2));
    return {
      outPath: path.resolve(outPath),
      format: 'wav',
      durationSec,
      words: kq.words,
      region: kq.region,
      voiceId: kq.voiceId,
    };
  }

  fs.writeFileSync(outPath, kq.mp3Buffer);
  return {
    outPath: path.resolve(outPath),
    format: 'mp3',
    durationSec: Number(((kq.durationMs || 0) / 1000).toFixed(2)),
    words: kq.words,
    region: kq.region,
    voiceId: kq.voiceId,
  };
}

/**
 * Tổng hợp hàng loạt phân đoạn kịch bản song song trên đúng 1 quốc gia cố định.
 */
async function taoNhieuDoanSongSong({
  items,
  workDir,
  voiceId = MAC_DINH_GIONG,
  lang = 'vi',
  region = QUOC_GIA_MAC_DINH,
  concurrency = 0,
  ffmpegPath = 'ffmpeg',
  sampleRate = 48000,
  channels = 1,
  onProgress = null,
  signal = null,
  checkCancelled = null,
} = {}) {
  if (!Array.isArray(items) || !items.length) {
    throw new Error('Danh sách phân đoạn (items) trống.');
  }
  const dir = workDir || path.dirname(path.resolve(items[0].clipPath || 'clip_0.mp3'));
  fs.mkdirSync(dir, { recursive: true });

  const giongChon = chonGiongHopLe(voiceId, lang);
  const jobId = `cc_batch_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
  const isCancelled = () => Boolean(signal?.aborted || checkCancelled?.());

  const logicalCores = os.cpus()?.length || 4;
  const autoConcurrency = logicalCores >= 12 ? 8 : logicalCores >= 8 ? 6 : 4;
  const workers = Math.min(
    Math.max(1, Number(concurrency) || autoConcurrency),
    items.length
  );

  const durations = new Array(items.length).fill(0);
  let cursor = 0;
  let doneCount = 0;
  const t0 = Date.now();

  try {
    async function worker() {
      while (cursor < items.length) {
        if (isCancelled()) throw taoLoiHuyCapcut();
        const idx = cursor++;
        const it = items[idx];
        const targetPath = it.clipPath || path.join(dir, `seg_${String(idx).padStart(3, '0')}.mp3`);
        const res = await taoGiongRaTep({
          text: it.text,
          voice: it.voiceId || giongChon.id,
          lang: it.lang || lang,
          region,
          outPath: targetPath,
          ffmpegPath,
          sampleRate,
          channels,
          needTimestamp: Boolean(it.needTimestamp),
          daHuy: isCancelled,
        });
        durations[idx] = res.durationSec;
        doneCount++;
        if (onProgress) {
          onProgress({
            done: doneCount,
            total: items.length,
            index: idx,
            durationSec: res.durationSec,
            outPath: res.outPath,
          });
        }
      }
    }

    await Promise.all(Array.from({ length: workers }, () => worker()));
    return {
      region: chuanHoaMaQuocGia(region),
      durations,
      elapsedSec: Number(((Date.now() - t0) / 1000).toFixed(2)),
    };
  } finally {
    boTaoGiongMacDinh.huyJob(jobId);
  }
}

module.exports = {
  BASE_URL,
  QUOC_GIA_MAC_DINH,
  MAC_DINH_GIONG,
  BoTaoGiongCapCut,
  boTaoGiongMacDinh,
  danhSachGiong,
  timGiong,
  hopLeGiong,
  chonGiongHopLe,
  chuanHoaMaQuocGia,
  chuanHoaAmViCapcut,
  gopUtterancesThanhTu,
  taoThietBiAo,
  goiCapcutMotCau,
  goiCapcutTheoLo,
  docThoiLuongWavPcm,
  catLangBienWavPcm,
  chuyenMp3SangWavPcm,
  taoGiong: opts => boTaoGiongMacDinh.taoGiong(opts),
  taoGiongRaTep,
  taoNhieuDoanSongSong,
  datQuocGiaCoDinh: region => boTaoGiongMacDinh.datQuocGiaCoDinh(region),
  huyJob: jobId => boTaoGiongMacDinh.huyJob(jobId),
};
