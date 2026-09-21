# -*- coding: utf-8 -*-
"""
配置示例：
{
    "key": "hongguo_dj",
    "name": "红果短剧",
    "type": 3,
    "api": "所在路径/红果短剧.py",
    "searchable": 1,
    "quickSearch": 1,
    "filterable": 1,
    "changeable": 0
}
"""
import base64
import binascii
import hashlib
import json
import os
import random
import re
import socket
import ssl
import struct
import sys
import threading
import time
import traceback
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import quote, urlparse

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from base.spider import Spider

HG_API = "https://api5-normal-sinfonlineb.fqnovel.com/novel/player/multi_video_model/v1/"
HG_UA = "com.phoenix.read/71332 (Linux; U; Android 16; zh_CN; 25053RT47C; Build/BP2A.250605.031.A3; Cronet/TTNetVersion:04657795 2026-01-23 QuicVersion:c67e9834 2025-09-08"

CENC_PROBE_BYTES = 524288
CENC_CHUNK = 1048576

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE


def _hg_md5(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def _hg_url_encode(params):
    parts = []
    for k, v in params.items():
        parts.append(f"{k}={quote(str(v), safe='')}")
    return "&".join(parts).replace("%20", "+").replace("%2A", "*")


def _hg_json_body_md5(payload):
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return _hg_md5(raw).upper()


def _hg_xg_rc4(data, key):
    table = list(range(256))
    j = 0
    for i in range(256):
        j = (j + table[i] + key[i % len(key)]) % 256
        table[i] = table[j]
    ii = 0
    jj = 0
    result = bytearray(len(data))
    for index in range(len(data)):
        ii = (ii + 1) & 0xFF
        x = table[ii]
        jj = (jj + x) & 0xFF
        y = table[jj]
        table[ii] = y
        result[index] = data[index] ^ table[(y + y) & 0xFF]
    return bytes(result)


def _hg_reverse_bits(v):
    return int(f"{v:08b}"[::-1], 2)


def _hg_encrypt_gorgon(payload, query, khronos, xg_rand):
    body_md5 = _hg_json_body_md5(payload).lower() if payload else ""
    data = bytearray(hashlib.md5(query.encode()).digest()[:4])
    if body_md5:
        data += bytes.fromhex(body_md5)[:4]
    else:
        data += b"\0\0\0\0"
    data += b"\0\0\0\0"
    data += struct.pack("<I", 67503104)
    data += struct.pack(">I", khronos)
    key = bytes((0x4A, 320 & 0xFF, 0x16, (xg_rand >> 8) & 0xFF, 0x47, 0x6C, 1, xg_rand & 0xFF))
    result = bytearray(_hg_xg_rc4(bytes(data), key))
    for index in range(len(result)):
        value = result[index]
        value = ((value >> 4) | (value << 4)) & 0xFF
        following = result[index + 1] if index + 1 < len(result) else result[0]
        result[index] = (~(_hg_reverse_bits(following ^ value) ^ 20)) & 0xFF
    header = b"\x84\x04" + struct.pack("<H", xg_rand) + struct.pack("<H", 320)
    return (header + bytes(result)).hex()


def _hg_signed_params(payload, device_id, install_id):
    now = int(time.time())
    params = {
        "iid": install_id, "device_id": device_id, "ac": "wifi",
        "channel": "update_64", "aid": "8662", "app_name": "novelread",
        "version_code": "71332", "version_name": "7.1.3.32",
        "device_platform": "android", "os": "android", "ssmix": "a",
        "device_type": "25053RT47C", "device_brand": "Redmi", "language": "zh",
        "os_api": "36", "os_version": "16", "manifest_version_code": "71332",
        "resolution": "1280*2772", "dpi": "520", "update_version_code": "71332",
        "host_abi": "arm64-v8a", "dragon_device_type": "phone",
        "pv_player": "71332", "compliance_status": "0",
        "need_personal_recommend": "1", "player_so_load": "1",
        "is_android_pad_screen": "0",
    }
    params["ts"] = now
    params["_rticket"] = int(time.time() * 1000)
    khronos = now
    xg_rand = random.randint(0, 0xFFFF)
    query = _hg_url_encode(params)
    headers = {
        "User-Agent": HG_UA,
        "Accept": "application/json; charset=utf-8,application/x-protobuf",
        "Content-Type": "application/json; charset=UTF-8",
        "x-ss-req-ticket": str(int(time.time() * 1000)),
        "x-tt-request-tag": "t=0;n=0",
        "sdk-version": "2",
        "passport-sdk-version": "50561",
        "x-vc-bdturing-sdk-version": "3.7.2.cn",
        "x-khronos": str(khronos),
        "x-gorgon": _hg_encrypt_gorgon(payload, query, khronos, xg_rand),
        "x-ss-stub": _hg_json_body_md5(payload),
    }
    return HG_API + "?" + query, headers


def _hg_https_request(url_str, method, headers, body=None):
    data = body.encode("utf-8") if body and isinstance(body, str) else body
    req = urllib.request.Request(url_str, data=data, headers=headers, method=method)
    resp = urllib.request.urlopen(req, context=_ssl_ctx, timeout=30)
    raw = resp.read()
    return resp.status, dict(resp.headers), raw


def _hg_walk_entries(node, out):
    if not isinstance(node, (dict, list)):
        return
    if isinstance(node, list):
        for v in node:
            _hg_walk_entries(v, out)
        return
    main_url = str(node.get("main_url") or "").strip()
    if main_url:
        encrypt_info = node.get("encrypt_info")
        spade_a = ""
        if encrypt_info:
            spade_a = str(encrypt_info.get("spade_a") or "").strip()
        media_url = main_url
        if not main_url.startswith("http"):
            try:
                decoded = base64.b64decode(main_url).decode("utf-8")
                if decoded.startswith("http"):
                    media_url = decoded
            except Exception:
                pass
        if media_url:
            definition = str(node.get("definition") or "").lower()
            meta = node.get("video_meta")
            if not definition and meta:
                definition = str(meta.get("definition") or "").lower()
            out.append({"definition": definition, "url": media_url, "spade_a": spade_a})
    for v in node.values():
        _hg_walk_entries(v, out)


def _hg_multi_video_model(vid, device_id, install_id):
    payload = {
        "biz_param": {
            "detail_page_version": 0,
            "device_level": 3,
            "disable_digg_stat": False,
            "need_all_video_definition": True,
            "need_mp4_align": False,
            "use_os_player": False,
            "use_server_dns": False,
            "video_platform": 1024,
        },
        "mixed_video_id_map": {"1004": [str(vid)]},
    }
    url, headers = _hg_signed_params(payload, device_id, install_id)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    status, _, raw = _hg_https_request(url, "POST", headers, body)
    if status != 200:
        raise RuntimeError(f"multi_video_model HTTP {status}")
    data = json.loads(raw.decode("utf-8"))
    if data.get("code") != 0:
        raise RuntimeError(f"API error: {data.get('code')} {data.get('message', '')}")
    d = data.get("data") or {}
    entry = d.get(str(vid)) or d
    model = entry.get("video_model")
    if isinstance(model, str):
        try:
            model = json.loads(model)
        except Exception:
            model = {}
    if not isinstance(model, dict):
        model = d
    entries = []
    _hg_walk_entries(model, entries)
    if not entries:
        _hg_walk_entries(d, entries)
    order = ["1080p", "720p", "540p", "480p", "360p"]
    entries.sort(key=lambda e: order.index(e["definition"]) if e["definition"] in order else 99)
    return entries


def _b64url_decode(s):
    out = bytearray()
    acc = 0
    bits = 0
    for ch in str(s):
        if ch == "=":
            break
        v = -1
        if "A" <= ch <= "Z":
            v = ord(ch) - 65
        elif "a" <= ch <= "z":
            v = ord(ch) - 71
        elif "0" <= ch <= "9":
            v = ord(ch) + 4
        elif ch in "-+":
            v = 62
        elif ch in "_/":
            v = 63
        if v < 0:
            continue
        acc = (acc << 6) | v
        bits += 6
        if bits >= 8:
            bits -= 8
            out.append((acc >> bits) & 0xFF)
    return bytes(out)


def _hex_value(b):
    i = b & 0xFF
    if 48 <= i <= 57:
        return i - 48
    if 97 <= i <= 102:
        return i - 87
    if 65 <= i <= 70:
        return i - 55
    return -1


def _popcount(n):
    return bin(n).count("1")


def _read_u32(buf, i):
    return struct.unpack_from(">I", buf, i)[0]


def _read_u64(buf, i):
    return struct.unpack_from(">Q", buf, i)[0]


def _read_u24(buf, i):
    return (buf[i] << 16) | (buf[i + 1] << 8) | buf[i + 2]


def _find_fourcc(data, fourcc, start=0):
    target = fourcc.encode("ascii")
    i = max(0, start)
    while i <= len(data) - 4:
        if data[i:i + 4] == target:
            return i
        i += 1
    return -1


def _find_box(data, fourcc, start=0):
    i = _find_fourcc(data, fourcc, max(4, start))
    if i < 0:
        return None
    size = _read_u32(data, i - 4)
    if size == 1 and i + 12 <= len(data):
        size = _read_u64(data, i + 4)
    if size < 8 or size > 0x7FFFFFFF or (i - 4) + size > len(data):
        return None
    return {"offset": i - 4, "size": size}


def _box_body(data, fourcc, start=0):
    found = _find_box(data, fourcc, start)
    if not found or found["size"] < 8:
        return None
    return {"offset": found["offset"] + 8, "size": found["size"] - 8}


def _replace_fourcc(data, old_fcc, new_fcc):
    old_b = old_fcc.encode("ascii")
    new_b = new_fcc.encode("ascii")
    i = 0
    while True:
        i = _find_fourcc(data, old_fcc, i)
        if i < 0:
            return
        data[i:i + 4] = new_b
        i += 4


def _derive_cenc_content_key(spade_a):
    data = _b64url_decode(spade_a.strip())
    if len(data) < 33:
        raise ValueError("invalid spade_a")
    trim = len(data) - ((data[0] ^ data[1]) ^ data[2])
    length2 = trim + 47
    if length2 <= 0 or trim + 48 > len(data):
        length2 = len(data) - 1
    if length2 < 33:
        raise ValueError("invalid spade_a length")
    region = bytearray(data[1:length2 + 1])
    s1 = 85
    s2 = 246
    for idx in range(length2):
        b = region[idx]
        sel = s1 if (idx & 1) == 1 else s2
        if (idx & 1) == 1:
            s1 = b
        else:
            s2 = b
        region[idx] = ((-21 - _popcount(idx)) + (b ^ sel)) & 0xFF
    key = bytearray(16)
    for j in range(16):
        hi = _hex_value(region[j * 2 + 1])
        lo = _hex_value(region[j * 2 + 2])
        if hi < 0 or lo < 0:
            raise ValueError("invalid spade_a hex")
        key[j] = (hi << 4) | lo
    return bytes(key)


def _add_counter(block, inc):
    block = bytearray(block)
    for i in range(len(block) - 1, -1, -1):
        t = block[i] + (inc & 0xFF)
        block[i] = t & 0xFF
        inc = (inc >> 8) + (t >> 8)
        if inc == 0:
            break
    return bytes(block)


def _parse_cenc_track_tables(data, trak_offset):
    stbl = _find_box(data, "stbl", trak_offset + 8)
    if not stbl:
        return None
    stsz = _box_body(data, "stsz", stbl["offset"])
    stco = _box_body(data, "stco", stbl["offset"])
    co64 = _box_body(data, "co64", stbl["offset"])
    stsc = _box_body(data, "stsc", stbl["offset"])
    saiz = _box_body(data, "saiz", stbl["offset"])
    saio = _box_body(data, "saio", stbl["offset"])
    if not stsz or not stsc or not saiz or not saio or (not stco and not co64):
        return None

    off = stsz["offset"]
    sz = stsz["size"]
    if sz < 12:
        return None
    sample_size = _read_u32(data, off + 4)
    count = _read_u32(data, off + 8)
    if sample_size != 0:
        sizes = [sample_size] * count
    else:
        cap = (sz - 12) // 4
        count = min(count, cap)
        sizes = [_read_u32(data, off + 12 + i * 4) for i in range(count)]

    if stco:
        chunk_off = stco["offset"]
        sz = stco["size"]
        chunk_entry = 4
    else:
        chunk_off = co64["offset"]
        sz = co64["size"]
        chunk_entry = 8
    if sz < 8:
        return None
    n_chunks = min(_read_u32(data, chunk_off + 4), (sz - 8) // chunk_entry)
    offsets = []
    for i in range(n_chunks):
        if chunk_entry == 4:
            offsets.append(_read_u32(data, chunk_off + 8 + i * 4))
        else:
            offsets.append(_read_u64(data, chunk_off + 8 + i * 8))

    off = stsc["offset"]
    sz = stsc["size"]
    if sz < 8:
        return None
    n_stsc = min(_read_u32(data, off + 4), (sz - 8) // 12)
    firsts = []
    per_chunk = []
    for i in range(n_stsc):
        firsts.append(_read_u32(data, off + 8 + i * 12))
        per_chunk.append(_read_u32(data, off + 12 + i * 12))
    chunk_samples = [0] * n_chunks
    for i in range(n_stsc):
        lo = firsts[i] - 1
        hi = firsts[i + 1] - 1 if i + 1 < n_stsc else n_chunks
        for k in range(lo, hi):
            if 0 <= k < n_chunks:
                chunk_samples[k] = per_chunk[i]

    off = saiz["offset"]
    sz = saiz["size"]
    saiz_flags = _read_u24(data, off + 1)
    saiz_hdr = 12 if (saiz_flags & 1) else 4
    if sz < saiz_hdr + 5:
        return None
    default_size = data[off + saiz_hdr]
    n_aux = _read_u32(data, off + saiz_hdr + 1)
    if default_size != 0:
        aux_sizes = [default_size] * n_aux
    else:
        cap = sz - saiz_hdr - 5
        n_aux = min(n_aux, cap)
        aux_sizes = [data[off + saiz_hdr + 5 + i] for i in range(n_aux)]

    off = saio["offset"]
    sz = saio["size"]
    saio_flags = _read_u24(data, off + 1)
    saio_wide = 8 if data[off] == 1 else 4
    saio_hdr = 12 if (saio_flags & 1) else 4
    if sz < saio_hdr + 4 + saio_wide:
        return None
    if _read_u32(data, off + saio_hdr) < 1:
        return None
    if saio_wide == 8:
        aux_offset = _read_u64(data, off + saio_hdr + 4)
    else:
        aux_offset = _read_u32(data, off + saio_hdr + 4)

    return {
        "sizes": sizes, "offsets": offsets,
        "chunk_samples": chunk_samples, "aux_sizes": aux_sizes,
        "aux_offset": aux_offset,
    }


def _patch_cenc_moov(data):
    data = bytearray(data)
    patches = []
    i = 0
    while True:
        i = _find_fourcc(data, "sinf", i)
        if i < 0:
            break
        if i >= 12:
            end = (i - 4) + _read_u32(data, i - 4)
            frma = _find_fourcc(data, "frma", i)
            if end <= len(data) and frma >= 0 and frma + 8 <= end:
                pos = i - 12
                if (data[pos] == 0x65 and data[pos + 1] == 0x6e
                        and data[pos + 2] == 0x63
                        and (data[pos + 3] == 0x76 or data[pos + 3] == 0x61)):
                    patches.append((pos, bytes(data[frma + 4:frma + 8])))
        i += 4
    for pos, fourcc in patches:
        data[pos:pos + 4] = fourcc
    _replace_fourcc(data, "encv", "hvc1")
    _replace_fourcc(data, "enca", "mp4a")
    i = 0
    while True:
        i = _find_fourcc(data, "sinf", i)
        if i < 0:
            return bytes(data)
        if i >= 4:
            size = _read_u32(data, i - 4)
            end = (i - 4) + size
            if 8 <= size < 100000 and end <= len(data):
                data[i:i + 4] = b"free"
                for k in range(i + 4, end):
                    data[k] = 0
                i = end
        i += 4


class CencRangeReader:
    def __init__(self, url, spade_a, headers=None):
        self.url = url
        self.spade_a = spade_a
        self.headers = headers or {}
        self.key = _derive_cenc_content_key(spade_a)
        self.index = None

    def _fetch_range(self, start, end):
        if start < 0 or end < start:
            return b""
        req_headers = dict(self.headers)
        req_headers["Range"] = f"bytes={start}-{end}"
        req_headers["User-Agent"] = HG_UA
        req = urllib.request.Request(self.url, headers=req_headers, method="GET")
        resp = urllib.request.urlopen(req, context=_ssl_ctx, timeout=30)
        if resp.status not in (200, 206):
            raise RuntimeError(f"CENC source returned {resp.status}")
        return resp.read()

    def _probe_total_size(self):
        req_headers = dict(self.headers)
        req_headers["Range"] = "bytes=0-0"
        req_headers["User-Agent"] = HG_UA
        req = urllib.request.Request(self.url, headers=req_headers, method="GET")
        resp = urllib.request.urlopen(req, context=_ssl_ctx, timeout=30)
        cr = resp.headers.get("Content-Range", "")
        if "/" in cr:
            size_str = cr.rsplit("/", 1)[-1].strip()
            try:
                size = int(size_str)
                if size > 0:
                    return size
            except ValueError:
                pass
        return len(resp.read())

    def ensure_index(self):
        if self.index is not None:
            return self.index
        total_size = self._probe_total_size()
        if total_size <= 0:
            raise RuntimeError("invalid CENC media size")
        probe_end = min(CENC_PROBE_BYTES, total_size) - 1
        probe_data = self._fetch_range(0, probe_end)

        moov = _find_box(probe_data, "moov", 0)
        if not moov:
            tail_start = max(0, total_size - CENC_PROBE_BYTES)
            tail_data = self._fetch_range(tail_start, total_size - 1)
            moov2 = _find_box(tail_data, "moov", 0)
            if not moov2:
                raise RuntimeError("CENC media has no parseable moov")
            moov_abs_start = tail_start + moov2["offset"]
            moov_data = self._fetch_range(moov_abs_start, moov_abs_start + moov2["size"] - 1)
            prefix_data = self._fetch_range(0, moov_abs_start - 1) if moov_abs_start > 0 else b""
        else:
            if moov["offset"] + moov["size"] > len(probe_data):
                full_data = self._fetch_range(0, moov["offset"] + moov["size"] - 1)
                moov_data = full_data[moov["offset"]:moov["offset"] + moov["size"]]
            else:
                moov_data = probe_data[moov["offset"]:moov["offset"] + moov["size"]]
            prefix_data = probe_data[:moov["offset"]]

        self.index = self._build_index(moov_data, prefix_data, total_size)
        return self.index

    def _build_index(self, moov_data, prefix_data, total_size):
        prefix_len = len(prefix_data)
        samples = []
        pos = 0
        while pos < len(moov_data):
            trak = _find_box(moov_data, "trak", pos)
            if not trak:
                break
            tables = _parse_cenc_track_tables(moov_data, trak["offset"])
            if tables:
                samples.extend(self._build_track_samples(tables))
            pos = max(trak["size"], 8) + trak["offset"]
        samples.sort(key=lambda s: s["offset"])

        combined = bytearray(prefix_data) + bytearray(moov_data)
        prefix_len = len(prefix_data)
        patched = _patch_cenc_moov(combined)
        patched_moov = patched[prefix_len:]

        return {
            "total_size": total_size,
            "patched_moov": patched_moov,
            "patched_moov_start": prefix_len,
            "samples": samples,
        }

    def _build_track_samples(self, tables):
        aux_total = sum(max(s, 8) for s in tables["aux_sizes"])
        if aux_total <= 0 or aux_total > 0x7FFFFFFF:
            return []
        aux_start = tables["aux_offset"]
        aux_end = aux_start + aux_total - 1
        aux_data = self._fetch_range(aux_start, aux_end)
        if len(aux_data) < aux_total:
            return []

        samples = []
        sample_idx = 0
        aux_pos = 0
        for chunk_idx in range(len(tables["offsets"])):
            if chunk_idx >= len(tables["chunk_samples"]):
                break
            pos = tables["offsets"][chunk_idx]
            for _ in range(tables["chunk_samples"][chunk_idx]):
                if sample_idx >= len(tables["sizes"]) or sample_idx >= len(tables["aux_sizes"]):
                    return samples
                aux_size = max(tables["aux_sizes"][sample_idx], 8)
                iv = bytearray(16)
                take = min(16, aux_size)
                iv[:take] = aux_data[aux_pos:aux_pos + take]
                samples.append({
                    "offset": pos,
                    "size": tables["sizes"][sample_idx],
                    "iv": bytes(iv),
                })
                pos += tables["sizes"][sample_idx]
                aux_pos += aux_size
                sample_idx += 1
        return samples

    def _cenc_keystream(self, iv, size):
        block = bytearray(iv[:16])
        out = bytearray(size)
        cipher = AES.new(self.key, AES.MODE_ECB)
        remaining = size
        offset = 0
        while remaining > 0:
            ks = cipher.encrypt(bytes(block))
            n = min(16, remaining)
            out[offset:offset + n] = ks[:n]
            block = bytearray(_add_counter(bytes(block), 1))
            offset += n
            remaining -= n
        return bytes(out)

    def _decrypt_samples(self, buf, base_offset, samples):
        end = base_offset + len(buf) - 1
        for s in samples:
            if s["offset"] > end:
                return
            s_end = s["offset"] + s["size"] - 1
            if s_end >= base_offset:
                overlap_start = max(base_offset, s["offset"])
                buf_offset = overlap_start - base_offset
                overlap_len = min(end, s_end) - overlap_start + 1
                ks = self._cenc_keystream(s["iv"], s["size"])
                ks_offset = overlap_start - s["offset"]
                for i in range(overlap_len):
                    buf[buf_offset + i] ^= ks[ks_offset + i]

    def read_range(self, start, end):
        idx = self.ensure_index()
        end_clamped = min(end, idx["total_size"] - 1)
        if start < 0 or end_clamped < start:
            return b""

        chunks = []
        while start <= end_clamped:
            moov_end = idx["patched_moov_start"] + len(idx["patched_moov"]) - 1
            if start >= idx["patched_moov_start"] and start <= moov_end:
                slice_end = min(end_clamped, moov_end)
                offset = start - idx["patched_moov_start"]
                chunks.append(idx["patched_moov"][offset:offset + (slice_end - start + 1)])
                start = slice_end + 1
            else:
                chunk_end = min(end_clamped, start + CENC_CHUNK - 1, idx["total_size"] - 1)
                if start < idx["patched_moov_start"]:
                    chunk_end = min(chunk_end, idx["patched_moov_start"] - 1)
                data = bytearray(self._fetch_range(start, chunk_end))
                if not data:
                    break
                self._decrypt_samples(data, start, idx["samples"])
                take = min(len(data), chunk_end - start + 1)
                chunks.append(bytes(data[:take]))
                start += take
        return b"".join(chunks)


_cenc_sessions = {}
_cenc_server = None
_cenc_port = None
_cenc_lock = threading.Lock()


class _CencRequestHandler(BaseHTTPRequestHandler):
    def _handle(self, is_head=False):
        path = urlparse(self.path)
        parts = path.path.strip("/").split("/")
        if len(parts) < 3 or parts[0] != "cenc":
            self.send_error(404)
            return
        token = parts[1]
        session = _cenc_sessions.get(token)
        if not session:
            self.send_error(404)
            return
        session["last_access"] = time.time()
        reader = session["reader"]
        try:
            idx = reader.ensure_index()
            total_size = idx["total_size"]
            range_header = self.headers.get("Range", "")
            start = 0
            end = total_size - 1
            if range_header:
                m = re.match(r"bytes=(\d+)-(\d*)", range_header)
                if m:
                    start = int(m.group(1))
                    end = int(m.group(2)) if m.group(2) else total_size - 1
            end = min(end, total_size - 1)
            length = end - start + 1

            self.send_response(206 if range_header else 200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if range_header:
                self.send_header("Content-Range", f"bytes {start}-{end}/{total_size}")
            self.end_headers()
            if is_head:
                return

            cursor = start
            CHUNK = 262144
            while cursor <= end:
                chunk_end = min(cursor + CHUNK - 1, end)
                data = reader.read_range(cursor, chunk_end)
                if not data:
                    break
                self.wfile.write(data)
                cursor += len(data)
        except Exception as e:
            print("[CENC-ERROR] path=" + self.path + " err=" + str(e))
            print(traceback.format_exc())
            sys.stdout.flush()
            try:
                self.send_error(500, str(e))
            except Exception:
                pass

    def do_GET(self):
        self._handle(False)

    def do_HEAD(self):
        self._handle(True)

    def log_message(self, *args):
        print("[CENC-LOG] " + args[0] % args[1:])
        sys.stdout.flush()


def _ensure_cenc_server():
    global _cenc_server, _cenc_port
    if _cenc_server is not None:
        return _cenc_port
    with _cenc_lock:
        if _cenc_server is not None:
            return _cenc_port
        for port in range(5110, 5210):
            try:
                server = HTTPServer(("127.0.0.1", port), _CencRequestHandler)
                server.daemon_threads = True
                _cenc_server = server
                _cenc_port = port
                t = threading.Thread(target=server.serve_forever, daemon=True)
                t.start()
                return port
            except OSError:
                continue
    raise RuntimeError("No available port for CENC server")


class Spider(Spider):

    KEY = "hongguo_dj"
    NAME = "红果短剧"
    HOST = "https://djapi.999888456.xyz"
    API = "/api/hongguo"
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    FX0 = [104, 64, 70, 166, 190, 168, 143, 130, 225, 254, 251, 217, 196, 34, 45, 60, 29, 20, 103, 105]

    def init(self, extend=""):
        self.hongguo_device_id = str(random.randint(10**14, 10**15 - 1))
        self.hongguo_install_id = str(random.randint(10**14, 10**15 - 1))

    def getName(self):
        pass

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    # 顶置分类：3 个内容类型 + 7 个排行榜，简约名称
    CLASSES = [
        {"type_id": "short_play", "type_name": "短剧"},
        {"type_id": "comic_series", "type_name": "漫剧"},
        {"type_id": "ai_short_play", "type_name": "AI剧"},
        {"type_id": "rank_recommend", "type_name": "推荐榜"},
        {"type_id": "rank_hot", "type_name": "热播榜"},
        {"type_id": "rank_new", "type_name": "新剧榜"},
        {"type_id": "rank_search", "type_name": "热搜榜"},
        {"type_id": "rank_must_watch", "type_name": "必看榜"},
        {"type_id": "rank_zhenguo", "type_name": "臻果榜"},
        {"type_id": "rank_collect", "type_name": "收藏榜"},
    ]

    # 排行榜筛选拆分维度：API 返回扁平 filter 列表，按前缀拆成 4 组
    _RANK_DIMS = ("scope", "background", "theme", "role")
    _RANK_DIM_NAMES = {"scope": "受众", "background": "背景",
                       "theme": "题材", "role": "角色"}

    def homeContent(self, filter):
        res = self._djapiGet("/home")
        raw_filters = res.get("filters") or {}
        filters = self._buildFilters(raw_filters)
        return {"class": self.CLASSES, "filters": filters}

    def _buildFilters(self, raw):
        """处理 API 筛选项：内容类重命名 推荐→排序；排行榜拆分扁平列表"""
        out = {}
        for c in self.CLASSES:
            tid = c["type_id"]
            flist = raw.get(tid, [])
            if tid.startswith("rank_"):
                out[tid] = self._splitRankFilters(flist)
            else:
                out[tid] = self._renameSortFilter(flist)
        return out

    def _renameSortFilter(self, flist):
        """把 推荐 重命名为 排序，避免与排行榜顶置分类混淆"""
        out = []
        for f in flist:
            if f.get("name") == "推荐":
                out.append({**f, "name": "排序"})
            else:
                out.append(f)
        return out

    def _splitRankFilters(self, flist):
        """将排行榜的扁平 filter 列表按维度拆分为多组筛选"""
        if not flist:
            return []
        groups = {}
        for dim in self._RANK_DIMS:
            groups[dim] = {
                "key": dim, "name": self._RANK_DIM_NAMES[dim],
                "value": [{"n": "全部", "v": ""}],
            }
        for f in flist:
            for v in f.get("value", []):
                val = v.get("v", "")
                n = v.get("n", "")
                if not val:
                    continue
                for dim in self._RANK_DIMS:
                    if val.startswith(f"rank_{dim}|"):
                        groups[dim]["value"].append({"n": n, "v": val})
                        break
        return [groups[d] for d in self._RANK_DIMS
                if len(groups[d]["value"]) > 1]

    def categoryContent(self, tid, pg, filter, extend):
        page = self._pageOf(pg)
        tid = str(tid or "").strip() or "short_play"
        extend = extend or {}
        query = f"tid={quote(tid)}&pg={page}"
        if tid.startswith("rank_"):
            # 排行榜：将维度筛选(scope/bg/theme/role)合并为单一 filter 参数
            for dim in self._RANK_DIMS:
                v = extend.get(dim, "")
                if v:
                    query += f"&filter={quote(str(v))}"
                    break
        else:
            for k, v in extend.items():
                if v:
                    query += f"&{quote(str(k))}={quote(str(v))}"
        res = self._djapiGet(f"/category?{query}")
        items = []
        for it in (res.get("list") or []):
            vid = str(it.get("vod_id") or "").strip()
            name = str(it.get("vod_name") or "").strip()
            if not vid or not name:
                continue
            items.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": str(it.get("vod_pic") or "").strip(),
                "vod_remarks": str(it.get("vod_remarks") or "").strip(),
            })
        has_more = len(items) > 0
        pagecount = page + 1 if has_more else page
        return {
            "page": page,
            "pagecount": pagecount,
            "limit": len(items) or 20,
            "total": (pagecount * 30 + len(items)) if has_more else 0,
            "list": items,
        }

    def searchContent(self, key, quick, pg="1"):
        page = self._pageOf(pg)
        wd = str(key or "").strip()
        if not wd:
            return {"list": [], "page": page}
        res = self._djapiGet(f"/search?wd={quote(wd)}&pg={page}")
        items = []
        for it in (res.get("list") or []):
            vid = str(it.get("vod_id") or "").strip()
            name = str(it.get("vod_name") or "").strip()
            if not vid or not name:
                continue
            remark = str(it.get("vod_remarks") or "").strip()
            items.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": str(it.get("vod_pic") or "").strip(),
                "vod_remarks": f"{self.NAME} | {remark}" if remark else self.NAME,
            })
        return {"list": items, "page": page}

    def detailContent(self, ids):
        vid = str(ids[0])
        res = self._djapiGet(f"/detail?id={quote(vid)}")
        v = (res.get("list") or [{}])[0] or {}
        vod = {
            "vod_id": vid,
            "vod_name": str(v.get("vod_name") or ""),
            "vod_pic": str(v.get("vod_pic") or ""),
            "vod_remarks": str(v.get("vod_remarks") or ""),
            "type_name": str(v.get("type_name") or ""),
            "vod_content": str(v.get("vod_content") or ""),
            "vod_play_from": self.NAME,
            "vod_play_url": str(v.get("vod_play_url") or "") or "暂无播放地址$0",
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        play_id = str(id or "").strip()
        if not play_id:
            return {"parse": 0, "url": "", "header": {}}

        vid = play_id
        try:
            decoded = json.loads(base64.b64decode(play_id).decode("utf-8"))
            vid = str(decoded.get("vid") or decoded.get("video_id") or "")
        except Exception:
            pass

        if vid:
            try:
                entries = _hg_multi_video_model(vid, self.hongguo_device_id, self.hongguo_install_id)
                if entries:
                    target = next((e for e in entries if e["spade_a"]), entries[0])
                    token = binascii.hexlify(os.urandom(16)).decode("ascii")
                    port = _ensure_cenc_server()
                    _cenc_sessions[token] = {
                        "reader": CencRangeReader(
                            target["url"], target["spade_a"],
                            {"Referer": "https://novel.snssdk.com/"},
                        ),
                        "last_access": time.time(),
                    }
                    return {
                        "parse": 0,
                        "url": f"http://127.0.0.1:{port}/cenc/{token}/video.mp4",
                        "header": {"User-Agent": HG_UA},
                    }
            except Exception as e:
                print(f"[红果] multi_video_model error: {e}")

        res = self._djapiGet(f"/play?id={quote(play_id)}")
        url = self._pickUrl(res.get("url"))
        return {"parse": 0, "url": url or play_id, "header": {}}

    def localProxy(self, param):
        pass

    def _dj(self, keyid):
        e = str(keyid or "")
        if len(e) <= 4:
            return b""
        raw = bytes.fromhex(e[4:])
        out = bytearray(len(raw))
        for i in range(len(raw)):
            r0 = raw[i] & 0xFF
            r1 = 109 if i == 0 else (raw[i - 1] & 0xFF)
            x = i % 20
            r2 = ((self.FX0[x] ^ ((90 + x * 13) & 0xFF)) ^ 85) & 0xFF
            r3 = (r0 + 215 - 11 * i) & 0xFF
            r4 = (((r3 << 3) | (r3 >> 5)) & 0xFF)
            r5 = (~(r2 ^ r1)) & 0xFF
            r6 = (r5 & 54) | ((~r5 & 0xFF) & 201)
            r7 = ((~r4 & 0xFF) & 54) | (r4 & 201)
            out[i] = (r6 ^ r7) & 0xFF
        return bytes(out)

    def _decryptBody(self, text):
        t = str(text or "")
        if not t.startswith("v2."):
            return t
        parts = t.split(".")
        if len(parts) < 3:
            return t
        raw = self._dj(parts[1])
        if len(raw) < 32:
            return ""
        try:
            key = raw[:16]
            iv = raw[16:32]
            cipher = AES.new(key, AES.MODE_CBC, iv)
            ct = base64.b64decode(parts[2])
            pt = unpad(cipher.decrypt(ct), AES.block_size)
            return pt.decode("utf-8")
        except Exception:
            return ""

    def _djapiGet(self, path):
        url = self.HOST + self.API + path
        try:
            resp = self.fetch(url, headers={"User-Agent": self.UA})
            text = resp.text
        except Exception:
            return {}
        body = self._decryptBody(text)
        if not body:
            return {}
        try:
            return json.loads(body)
        except Exception:
            return {}

    def _pickUrl(self, value):
        if isinstance(value, list):
            for item in value:
                url = str(item or "").strip()
                if url.startswith("http"):
                    return url
            for i in range(1, len(value), 2):
                url = str(value[i] or "").strip()
                if url:
                    return url
            return ""
        return str(value or "").strip()

    def _pageOf(self, value):
        try:
            page = int(value)
            return page if page > 0 else 1
        except (TypeError, ValueError):
            return 1
