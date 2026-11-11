# -*- coding: utf-8 -*-
#!/usr/bin/python
import base64
import gzip
import json
import re
import zlib
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from urllib.parse import quote, unquote, urlparse, parse_qs

try:
    import requests
except Exception:
    requests = None

sys.path.append('..')
try:
    from base.spider import Spider
except Exception:
    class Spider(object):
        def init(self, extend=''):
            pass

# 频道配置（保持不变）
CHANNELS = [
    {
        "type_id": "shareAliyun",
        "type_name": "阿里云盘发布频道"
    },
    {
        "type_id": "leoziyuan",
        "type_name": "LEO"
    },
    {
        "type_id": "douerpan",
        "type_name": "豆儿盘"
    },
    {
        "type_id": "bdwpzhpd8364",
        "type_name": "百度综合"
    },
    {
        "type_id": "Baidu_Netdisk",
        "type_name": "百度资源"
    },
    {
        "type_id": "Panzi88com",
        "type_name": "盘子"
    },
    {
        "type_id": "yunpanuc",
        "type_name": "UC资源"
    },
    {
        "type_id": "rbzhwpzy",
        "type_name": "热播综合"
    },
    {
        "type_id": "yun123pan",
        "type_name": "123云盘臻藏阁"
    },
    {
        "type_id": "Quark_Movies",
        "type_name": "夸克云盘综合资源"
    },
    {
        "type_id": "duanjucabian",
        "type_name": "热门短剧/擦边短剧/精选短剧/在线预览"
    },
    {
        "type_id": "yoyokuakeduanju",
        "type_name": "YOYO资源|夸克|短剧"
    },
    {
        "type_id": "QukanMovie",
        "type_name": "115影视资源分享"
    },
    {
        "type_id": "zhenyingsg",
        "type_name": "帧影时光"
    },
    {
        "type_id": "CBduanju",
        "type_name": "全网擦边|电影|资源分享"
    },
    {
        "type_id": "weichengduanju666",
        "type_name": "短剧大全资源"
    },
    {
        "type_id": "yingxiangkj",
        "type_name": "影享空间"
    },
    {
        "type_id": "QuarkFree",
        "type_name": "夸克网盘资源收藏"
    },
    {
        "type_id": "TG654TG",
        "type_name": "综艺网盘资源频道"
    },    
    {
        "type_id": "XiangxiuNBB",
        "type_name": "4K影视综合电影云盘"
    },
    {
        "type_id": "seedhub_pro",
        "type_name": "SeedHub资源库"
    },
    {
        "type_id": "ucwpzy",
        "type_name": "UC · 发布频道"
    },
    {
        "type_id": "clouddriveresources",
        "type_name": "混合 · CloudDrive"
    },
    {
        "type_id": "dianying4k",
        "type_name": "混合 · 4K影视屋"
    },
    {
        "type_id": "yunpanx",
        "type_name": "混合 · 云盘影库"
    },
    {
        "type_id": "quanziyuanshe",
        "type_name": "混合 · 全网云盘资源社"
    },
    {
        "type_id": "kuyupan",
        "type_name": "混合 · 酷鱼4K"
    },
    {
        "type_id": "PanjClub",
        "type_name": "混合 · 盘酱酱"
    },
    {
        "type_id": "tgsearchers7",
        "type_name": "混合 · 资源宇宙7"
    },
    {
        "type_id": "taoxgzy",
        "type_name": "混合 · 我的资源频道"
    },
    {
        "type_id": "yydf_hzl",
        "type_name": "混合 · 网盘资源合集"
    },
    {
        "type_id": "peccxinpd",
        "type_name": "混合 · 盘链"
    }
]



# ================================================================ 115 网盘直连播放
# 参考「盘搜.py」：Cookie 由站源 ext 传入；分享内文件展开成选集；
# 播放时转存「最近接收」→ 取 pickcode → 加密 downurl 拿真实直链。
# 115 全程不走 push:，其余网盘保持原有推送行为。
P115_WEB_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
               '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36')
P115_HEADERS = {
    'User-Agent': P115_WEB_UA,
    'Referer': 'https://115.com/',
    'Origin': 'https://115.com',
    'Accept': 'application/json, text/plain, */*',
}
VIDEO_EXTS_SET = frozenset((
    'mp4', 'mkv', 'ts', 'm2ts', 'avi', 'mov', 'wmv', 'flv',
    'webm', 'rmvb', 'mpg', 'mpeg', 'm4v', 'iso',
))
ROOT_CID = '0'
P115_CACHE_TTL = 1800

# ---- 115 分享库：fake115share.db 导出的静态 gzip 索引 ----
# 索引每行以 TAB 分隔：
#   C\t<share_code>\t<receive_code>       合集码表（13 条）
#   F\t<name>\t<cidx>\t<fid>\t<cid>      视频文件（约 13.7 万）
#   D\t<name>\t<row_id>\t<cid>\t<pid>     目录（约 1.2 万）
# 放在与 py 相同的静态托管下；可用站源 ext 的 115db_url 覆盖。
SHARE115_DEFAULT_URL = ('https://445569.pages.dev/https://raw.githubusercontent.com/'
                        'happybaihao/pan/main/115share_index.txt.gz')
SHARE115_SEARCH_LIMIT = 40
SHARE115_MAX_EPISODES = 60
SHARE115_MAX_LINES = 12
P115_TRANSFER_TIMEOUT = 25

RSA_N = 0x8686980c0f5a24c4b9d43020cd2c22703ff3f450756529058b1cf88f09b8602136477198a6e2683149659bd122c33592fdb5ad47944ad1ea4d36c6b172aad6338c3bb6ac6227502d010993ac967d1aef00f0c8e038de2e4d3bc2ec368af2e9f10a6f1eda4f7262f136420c07c331b871bf139f74f3010e3c4fe57df3afb71683
RSA_E = 0x10001
KEY_TABLE = bytes([
    240, 229, 105, 174, 191, 220, 191, 138, 26, 69, 232, 190, 125, 166, 115, 184,
    222, 143, 231, 196, 69, 218, 134, 196, 155, 100, 139, 20, 106, 180, 241, 170,
    56, 1, 53, 158, 38, 105, 44, 134, 0, 107, 79, 165, 54, 52, 98, 166,
    42, 150, 104, 24, 242, 74, 253, 189, 107, 151, 143, 77, 143, 137, 19, 183,
    108, 142, 147, 237, 14, 13, 72, 62, 215, 47, 136, 216, 254, 254, 126, 134,
    80, 149, 79, 209, 235, 131, 38, 52, 219, 102, 123, 156, 126, 157, 122, 129,
    50, 234, 182, 51, 222, 58, 169, 89, 52, 102, 59, 170, 186, 129, 96, 72,
    185, 213, 129, 156, 248, 108, 132, 119, 255, 84, 120, 38, 95, 190, 232, 30,
    54, 159, 52, 128, 92, 69, 44, 155, 118, 213, 27, 143, 204, 195, 184, 245,
])


def _p115_text(v):
    return '' if v is None else str(v).strip()


def _p115_basename(name):
    return name.rsplit('.', 1)[0] if '.' in name else name


def _b32e(s):
    if isinstance(s, str):
        s = s.encode('utf-8')
    return base64.b32encode(s).decode('ascii').rstrip('=')


def _b32d(s):
    s = _p115_text(s).upper()
    pad = '=' * (-len(s) % 8)
    return base64.b32decode(s + pad).decode('utf-8')


def _b64e(s):
    if isinstance(s, str):
        s = s.encode('utf-8')
    return base64.urlsafe_b64encode(s).decode('ascii').rstrip('=')


def _b64d(s):
    s = _p115_text(s)
    pad = '=' * (-len(s) % 4)
    try:
        return base64.urlsafe_b64decode(s + pad).decode('utf-8')
    except Exception:
        return ''


def _bytes_to_int(b):
    out = 0
    for byte in b:
        out = (out << 8) | byte
    return out


def _int_to_bytes(value, length=None):
    if length is None:
        length = max(1, (value.bit_length() + 7) // 8)
    out = bytearray(length)
    for i in range(length - 1, -1, -1):
        out[i] = value & 0xFF
        value >>= 8
    return bytes(out)


def _xor_bytes(a, b):
    return bytes(x ^ y for x, y in zip(a, b))


def _chunks(start, end, step=1):
    out = []
    nxt = start + step
    while nxt < end:
        out.append((start, nxt))
        start = nxt
        nxt += step
    if start != end:
        out.append((start, end))
    return out


def _xor_by_key(input_bytes, key):
    out = bytearray(len(input_bytes))
    head = len(input_bytes) & 3
    if head:
        out[0:head] = _xor_bytes(input_bytes[0:head], key[0:head])
    for (f, t) in _chunks(head, len(input_bytes), len(key)):
        seg = input_bytes[f:t]
        klen = len(key)
        for i in range(len(seg)):
            out[f + i] = seg[i] ^ key[i % klen]
    return bytes(out)


def _mod_pow(base, exp, mod):
    if mod == 1:
        return 0
    result = 1
    base %= mod
    while exp:
        if exp & 1:
            result = (result * base) % mod
        exp >>= 1
        base = (base * base) % mod
    return result


def _encode_block(input_bytes):
    block = bytearray(128)
    fill_end = 127 - len(input_bytes)
    for i in range(1, max(1, fill_end)):
        block[i] = 2
    block[0] = 0
    block[128 - len(input_bytes):128] = input_bytes
    return _bytes_to_int(bytes(block))


def _table_key(seed, length):
    out = bytearray(length)
    n = length * (length - 1)
    s = 0
    for i in range(length):
        mixed = (seed[i] + KEY_TABLE[s]) & 255
        out[i] = KEY_TABLE[n] ^ mixed
        n -= length
        s += length
    return bytes(out)


def _encrypt_payload(value):
    input_bytes = value.encode('utf-8') if isinstance(value, str) else bytes(value)
    step1 = _xor_by_key(input_bytes, bytes([141, 165, 165, 141]))
    step2 = step1[::-1]
    step3 = _xor_by_key(step2, bytes([120, 6, 173, 76, 51, 134, 93, 24, 76, 1, 63, 70]))
    padded = bytes(16) + step3
    blocks = _chunks(0, len(padded), 117)
    out = bytearray(len(blocks) * 128)
    pos = 0
    for (f, t) in blocks:
        enc = _mod_pow(_encode_block(padded[f:t]), RSA_E, RSA_N)
        out[pos:pos + 128] = _int_to_bytes(enc, 128)
        pos += 128
    return base64.b64encode(bytes(out)).decode('ascii')


def _decrypt_payload(value):
    raw = base64.b64decode(value)
    merged = bytearray()
    for (f, t) in _chunks(0, len(raw), 128):
        dec = _int_to_bytes(_mod_pow(_bytes_to_int(raw[f:t]), RSA_E, RSA_N))
        idx = dec.find(b"\x00")
        merged.extend(dec[idx + 1:] if idx >= 0 else dec)
    if len(merged) < 16:
        return ''
    seed = merged[0:16]
    key = _table_key(seed, 12)
    body = _xor_by_key(merged[16:], key)[::-1]
    plain = _xor_by_key(body, bytes([141, 165, 165, 141]))
    try:
        return plain.decode('utf-8')
    except Exception:
        return ''


def _build_downurl_body(payload_dict):
    enc = _encrypt_payload(json.dumps(payload_dict, separators=(',', ':')))
    return 'data=' + quote(enc, safe='')


def _extract_encrypted(data):
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
        except Exception:
            return data, None
        return _extract_encrypted(parsed)
    if isinstance(data, dict):
        enc = ''
        d = data.get('data')
        if isinstance(d, str):
            enc = d
        elif isinstance(d, dict) and isinstance(d.get('data'), str):
            enc = d['data']
        return enc, data
    return '', data


def _decode_downurl_response(data):
    enc, payload = _extract_encrypted(data)
    if not enc:
        return payload or {}
    try:
        plain = _decrypt_payload(enc)
        if not plain:
            return payload if isinstance(payload, dict) else {}
        return json.loads(plain)
    except Exception:
        return payload if isinstance(payload, dict) else {}


def _find_url_deep(obj):
    if not isinstance(obj, dict):
        return ''
    u = obj.get('url')
    if isinstance(u, str) and u:
        return u
    if isinstance(u, dict) and isinstance(u.get('url'), str) and u['url']:
        return u['url']
    d = obj.get('data')
    if isinstance(d, dict) and isinstance(d.get('url'), str) and d['url']:
        return d['url']
    for v in obj.values():
        hit = _find_url_deep(v)
        if hit:
            return hit
    return ''


def _find_msg_deep(obj):
    if not isinstance(obj, dict):
        return ''
    for key in ('msg', 'message', 'error'):
        v = obj.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    for v in obj.values():
        hit = _find_msg_deep(v)
        if hit:
            return hit
    return ''


def _pick_cid(data):
    if not isinstance(data, dict):
        return ''
    cid = _p115_text(data.get('cid') or data.get('file_id') or data.get('category_id'))
    if cid:
        return cid
    d = data.get('data')
    if isinstance(d, dict):
        cid = _p115_text(d.get('cid') or d.get('file_id') or d.get('category_id'))
        if cid:
            return cid
    if isinstance(d, list) and d and isinstance(d[0], dict):
        return _p115_text(d[0].get('cid') or d[0].get('file_id'))
    return ''


def _pick_url_by_pickcode(obj, pickcode):
    target = _p115_text(pickcode)
    if not target:
        return ''

    def walk(node):
        if isinstance(node, dict):
            pc = _p115_text(node.get('pickcode') or node.get('pc'))
            if pc and pc == target:
                u = node.get('url')
                if isinstance(u, str) and u:
                    return u
                if isinstance(u, dict) and isinstance(u.get('url'), str):
                    return u['url']
            if target in node and isinstance(node[target], dict):
                u = node[target].get('url')
                if isinstance(u, str) and u:
                    return u
                if isinstance(u, dict) and isinstance(u.get('url'), str):
                    return u['url']
            for v in node.values():
                hit = walk(v)
                if hit:
                    return hit
        elif isinstance(node, list):
            for v in node:
                hit = walk(v)
                if hit:
                    return hit
        return ''

    return walk(obj)


def _parse_115_share(url):
    u = _p115_text(url)
    u = re.sub(r'^https?://(?:www\.)?115cdn\.com/', 'https://115.com/', u, flags=re.I)
    u = re.sub(r'^https?://(?:www\.)?anxia\.com/', 'https://115.com/', u, flags=re.I)
    m = re.search(r'https?://(?:(?:www\.)?115\.com|(?:www\.)?115cdn\.com|'
                  r'(?:www\.)?anxia\.com)/s/([\w-]+)(?:\?([^#]*))?', u, re.I)
    if not m:
        return None
    qs = parse_qs(m.group(2) or '')
    pwd = ''
    for k in ('password', 'pwd', 'receive_code'):
        if qs.get(k):
            pwd = qs[k][0]
            break
    return {'url': u, 'share_id': m.group(1), 'pwd': pwd}


def _is_115_share(url):
    return bool(re.search(r'115(?:cdn)?\.com/s/|anxia\.com/s/', _p115_text(url), re.I))


def _is_115_video(item):
    name = _p115_text(item.get('fn') or item.get('n') or item.get('name'))
    ico = _p115_text(item.get('ico')).lower()
    ext = (name.rsplit('.', 1)[-1] if '.' in name else ico).lower()
    if ext in VIDEO_EXTS_SET:
        return True
    try:
        if int(item.get('isv') or 0) == 1:
            return True
    except Exception:
        pass
    return bool(item.get('play_long'))


def _clean_label(v, fallback=''):
    s = _p115_text(v)
    s = re.sub(r'[$#]+', ' ', s)
    s = re.sub(r'[\r\n\t]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s or fallback


def _format_size(size):
    try:
        n = float(size or 0)
    except Exception:
        return ''
    if n <= 0:
        return ''
    if n >= 1024 ** 3:
        return '%.2fG' % (n / 1024 ** 3)
    if n >= 1024 ** 2:
        return '%.2fM' % (n / 1024 ** 2)
    if n >= 1024:
        return '%.1fK' % (n / 1024)
    return '%dB' % n


def _guess_keyword(name):
    if not name:
        return ''
    base = _p115_basename(name).replace('_', ' ').replace('.', ' ').strip()
    return base[:20]


def _build_115_play_id(share_id, pwd, fid, name):
    payload = '%s|%s|%s|%s' % (share_id, pwd or '_', fid, _b64e(name or ''))
    return '115P|' + _b32e(payload)


def _parse_115_play_id(raw):
    if not _p115_text(raw).startswith('115P|'):
        return None
    try:
        parts = _b32d(_p115_text(raw)[len('115P|'):]).split('|')
        if len(parts) < 4:
            return None
        return {'share_id': parts[0], 'pwd': '' if parts[1] == '_' else parts[1],
                'fid': parts[2], 'name': _b64d(parts[3])}
    except Exception:
        return None


class _P115Cache:
    def __init__(self):
        self._d = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            item = self._d.get(key)
            if not item:
                return None
            if item[0] and item[0] < time.time():
                self._d.pop(key, None)
                return None
            return item[1]

    def set(self, key, value, ttl=300):
        with self._lock:
            if len(self._d) > 400:
                now = time.time()
                self._d = {k: v for k, v in self._d.items() if not v[0] or v[0] > now}
            self._d[key] = (time.time() + ttl if ttl else 0, value)

    def clear(self):
        with self._lock:
            self._d.clear()


class P115(object):
    """115 分享 → 直链播放器。独立 session，不走 t.me 代理。"""

    def __init__(self, cookie, save_dir_name='最近接收', save_cid='', timeout=15):
        self.cookie = cookie or ''
        self.save_dir_name = save_dir_name or '最近接收'
        self.save_cid = save_cid or ''
        try:
            self.timeout = max(6, min(int(timeout or 15), 30))
        except Exception:
            self.timeout = 15
        self._s = None
        if requests is not None:
            try:
                self._s = requests.Session()
                self._s.headers.update({'User-Agent': P115_WEB_UA})
                self._s.proxies = {}
                self._s.trust_env = False
            except Exception:
                self._s = None
        self._cache = _P115Cache()

    @property
    def enabled(self):
        return bool(self.cookie) and self._s is not None

    def _headers(self):
        h = dict(P115_HEADERS)
        h['Cookie'] = self.cookie
        return h

    @staticmethod
    def _error(msg):
        return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '', 'header': {}, 'msg': msg}

    def _play_result(self, real):
        out = {'parse': 0, 'jx': 0, 'playUrl': '', 'url': real,
               'header': {'User-Agent': P115_WEB_UA,
                          'Referer': 'https://115.com/',
                          'Cookie': self.cookie}}
        low = real.lower().split('?')[0]
        if low.endswith('.m3u8'):
            out['format'] = 'application/x-mpegURL'
        elif low.endswith('.mp4'):
            out['format'] = 'video/mp4'
        return out

    # ---------------- 分享内文件列表 ----------------
    def list_videos(self, share_url, max_files=60):
        p = _parse_115_share(share_url)
        if not p or not self.enabled:
            return []
        key = 'list|%s|%s' % (p['share_id'], p['pwd'])
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        out, stack, visited = [], [(ROOT_CID, 0)], set()
        while stack and len(out) < max_files:
            cid, depth = stack.pop()
            if depth > 6 or cid in visited:
                continue
            visited.add(cid)
            try:
                data = self._share_list(p['share_id'], p['pwd'], cid)
            except Exception:
                continue
            for it in (data.get('list') or []):
                is_dir = str(it.get('fc')) == '0' or (
                    not it.get('sha1') and not it.get('ico') and
                    it.get('fn') and '.' not in _p115_text(it.get('fn')))
                fid = _p115_text(it.get('fid') or it.get('cid'))
                if is_dir:
                    if fid:
                        stack.append((fid, depth + 1))
                    continue
                if not _is_115_video(it) or not fid:
                    continue
                name = _p115_text(it.get('fn') or it.get('n')) or fid
                size = _format_size(it.get('fs') or it.get('s'))
                label = ('[%s] %s' % (size, name)) if size else name
                out.append({'fid': fid, 'name': name,
                            'label': _clean_label(label, name)[:60]})
        self._cache.set(key, out, 300)
        return out

    def _share_list(self, share_id, pwd, cid):
        url = 'https://proapi.115.com/android/2.0/share/snap'
        params = {'share_code': share_id, 'receive_code': pwd or '',
                  'offset': 0, 'limit': 200, 'cid': cid or ''}
        r = self._s.get(url, params=params, headers=self._headers(), timeout=self.timeout)
        data = r.json() if r.text else {}
        if not data.get('state'):
            err = data.get('error') or data.get('msg') or 'share read fail'
            if '访问码' in err or '密码' in err:
                hint = ((data.get('data') or {}).get('shareinfo') or {}).get('receive_code') or ''
                if hint and hint != pwd:
                    params['receive_code'] = hint
                    r = self._s.get(url, params=params, headers=self._headers(), timeout=self.timeout)
                    data = r.json() if r.text else {}
                    if data.get('state'):
                        return data.get('data') or {}
            raise RuntimeError(err)
        return data.get('data') or {}

    # ---------------- 保存目录 / 转存 ----------------
    def _find_folder(self, name, parent=ROOT_CID):
        url = 'https://webapi.115.com/files'
        offset = 0
        while offset <= 5000:
            params = {'aid': 1, 'cid': parent, 'o': 'user_ptime', 'asc': 0,
                      'offset': offset, 'show_dir': 1, 'limit': 200,
                      'type': 0, 'format': 'json'}
            try:
                r = self._s.get(url, params=params, headers=self._headers(), timeout=self.timeout)
                items = (r.json() or {}).get('data') or []
            except Exception:
                return ''
            if not items:
                return ''
            for it in items:
                if _p115_text(it.get('n') or it.get('name')) == name:
                    return _p115_text(it.get('cid') or it.get('fid'))
            if len(items) < 200:
                return ''
            offset += 200
        return ''

    def _create_folder(self, name):
        url = 'https://webapi.115.com/files/add'
        h = self._headers()
        h['Content-Type'] = 'application/x-www-form-urlencoded'
        try:
            r = self._s.post(url, data={'cname': name, 'pid': ROOT_CID},
                             headers=h, timeout=self.timeout)
            data = r.json() if r.text else {}
        except Exception:
            return ''
        return _pick_cid(data) if data.get('state') else ''

    def _get_save_cid(self, force=False):
        if self.save_cid and not force:
            return self.save_cid
        cid = self._find_folder(self.save_dir_name)
        if not cid:
            cid = self._create_folder(self.save_dir_name)
        if cid:
            self.save_cid = cid
        return cid

    def _do_receive(self, share_id, pwd, fid, cid):
        url = 'https://proapi.115.com/android/2.0/share/receive'
        payload = {'share_code': share_id, 'receive_code': pwd or '',
                   'file_id': fid, 'cid': cid}
        try:
            r = self._s.post(url, data=payload, headers=self._headers(), timeout=self.timeout)
            data = r.json() if r.text else {}
        except Exception as e:
            return False, 'request fail: %s' % e
        if data.get('state'):
            return True, ''
        err = data.get('error') or data.get('msg') or 'transfer fail'
        if '已存在' in err or '重复' in err:
            return True, ''
        return False, err

    def _search_my_files(self, keyword, exact_name=''):
        url = 'https://webapi.115.com/files/search'
        params = {'search_value': keyword, 'type': 4, 'offset': 0, 'limit': 50,
                  'date': '', 'aid': 1, 'cid': 0, 'pick_code': '',
                  'source': '', 'format': 'json'}
        r = self._s.get(url, params=params, headers=self._headers(), timeout=self.timeout)
        items = (r.json() or {}).get('data') or []
        target = _p115_text(exact_name)
        base = _p115_basename(target).lower() if target else ''
        for it in items:
            fname = _p115_text(it.get('n') or it.get('name'))
            if fname == target:
                pc = _p115_text(it.get('pc') or it.get('pick_code') or it.get('pickcode'))
                if pc:
                    return pc
        if base:
            for it in items:
                fname = _p115_text(it.get('n') or it.get('name'))
                b = re.sub(r'\s*\(\d+\)$', '', _p115_basename(fname).lower())
                if b == base or base in b:
                    pc = _p115_text(it.get('pc') or it.get('pick_code') or it.get('pickcode'))
                    if pc:
                        return pc
        for it in items:
            pc = _p115_text(it.get('pc') or it.get('pick_code') or it.get('pickcode'))
            if pc:
                return pc
        return ''

    # ---------------- pickcode → 直链 ----------------
    def _resolve_pickcode(self, pickcode):
        key = 'pc|%s' % pickcode
        cached = self._cache.get(key)
        if cached:
            return self._play_result(cached)
        body = _build_downurl_body({'pickcode': pickcode})
        url = 'https://proapi.115.com/app/chrome/downurl?t=%d' % int(time.time())
        h = {'Content-Type': 'application/x-www-form-urlencoded',
             'Cookie': self.cookie, 'User-Agent': P115_WEB_UA,
             'Referer': 'https://115.com/', 'Origin': 'https://115.com'}
        try:
            r = self._s.post(url, data=body, headers=h, timeout=self.timeout)
            decoded = _decode_downurl_response(r.text)
        except Exception as e:
            return self._error('115 下载链接解码失败：%s' % e)
        real = _pick_url_by_pickcode(decoded, pickcode) or _find_url_deep(decoded)
        if not real:
            return self._error('115 未返回直链：%s' % (_find_msg_deep(decoded) or '可能触发风控或需要会员'))
        self._cache.set(key, real, P115_CACHE_TTL)
        return self._play_result(real)

    def play(self, share_id, pwd, fid, name):
        if not self.enabled:
            return self._error('115 Cookie 未配置或 requests 不可用')
        tkey = 'tr|%s::%s' % (share_id, fid)
        pc = self._cache.get(tkey)
        if not pc:
            cid = self._get_save_cid()
            if not cid:
                return self._error('无法获取/创建 115 保存目录：%s' % self.save_dir_name)
            ok, err = self._do_receive(share_id, pwd, fid, cid)
            if not ok and ('目录' in err or 'cid' in err.lower() or '不存在' in err or '无权' in err):
                cid2 = self._get_save_cid(force=True)
                if cid2 and cid2 != cid:
                    ok, err = self._do_receive(share_id, pwd, fid, cid2)
            if not ok:
                return self._error('115 转存失败：%s' % err)
            deadline = time.time() + P115_TRANSFER_TIMEOUT
            kw = _guess_keyword(name) or fid
            interval = 0.6
            while time.time() < deadline:
                try:
                    pc = self._search_my_files(kw, name)
                except Exception:
                    pc = ''
                if pc:
                    break
                time.sleep(interval)
                interval = min(interval * 1.5, 3.0)
            if not pc:
                return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '',
                        'header': {'User-Agent': P115_WEB_UA,
                                   'Referer': 'https://115.com/',
                                   'Cookie': self.cookie},
                        'msg': '115 转存中，请 5 秒后重试'}
            self._cache.set(tkey, pc, P115_CACHE_TTL)
        return self._resolve_pickcode(pc)

# ---------------------------------------------------------------- 网盘识别
PAN_ORDER = ['在线视频', '夸克', '百度', '阿里', '迅雷', '115', '123', '天翼', '移动', 'UC', '磁力', 'ED2K']

PAN_RULES = [
    ('夸克', r'pan\.quark\.cn|quark\.cn/s/|drive-pc\.quark\.cn'),
    ('百度', r'pan\.baidu\.com|eyun\.baidu\.com|yun\.baidu\.com/s/'),
    ('阿里', r'aliyundrive\.com|alipan\.com'),
    ('迅雷', r'pan\.xunlei\.com|xunlei\.com/s/'),
    ('115', r'(?:^|[./])115\.com|115cdn\.com|anxia\.com'),
    ('123', r'123pan\.(?:com|cn)|www\.123\d{3}\.(?:com|cn)|123(?:684|865|912|592|836)\.(?:com|cn)'),
    ('天翼', r'cloud\.189\.cn'),
    ('移动', r'caiyun\.139\.com|yun\.139\.com'),
    ('UC', r'pan\.uc\.cn|drive\.uc\.cn'),
    ('磁力', r'^magnet:\?xt=urn:btih:'),
    ('ED2K', r'^ed2k://'),
]

VIDEO_EXT_RE = re.compile(r'\.(?:mp4|m3u8|m3u|mpd|mkv|flv|ts|mov|webm|avi|wmv|rmvb)(?:[?#].*)?$', re.I)

# 频道里的广告消息（VPN 机场 / 卖号 等）没有“名称：”标记，命中这些词直接丢弃
AD_WORDS = ('vpn', '机场', '梯子', '加速器', '买号', '纸飞机', '电报下载', '谷歌号', '推特号',
            '注册送', '推广位', '开会员', '代充')


def pan_type(url):
    u = (url or '').strip().lower()
    if not u:
        return ''
    for name, pat in PAN_RULES:
        if re.search(pat, u):
            return name
    return ''


def is_video_url(url):
    u = (url or '').strip()
    if not u.lower().startswith('http'):
        return False
    return bool(VIDEO_EXT_RE.search(urlparse(u).path or u))


def pack_id(data):
    raw = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    try:
        return 'z' + base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode('ascii').rstrip('=')
    except Exception:
        return 'j' + base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')


def unpack_id(s):
    s = (s or '').strip()
    if not s:
        return None
    tag, body = s[0], s[1:]
    body += '=' * (-len(body) % 4)
    try:
        raw = base64.urlsafe_b64decode(body.encode('ascii'))
    except Exception:
        return None
    try:
        if tag == 'z':
            raw = zlib.decompress(raw)
        return json.loads(raw.decode('utf-8'))
    except Exception:
        return None


class Share115DB(object):
    """115 分享库静态索引：懒加载 gzip 文本，按名称子串检索。

    只保留 bytes 行做线性扫描，不建倒排、不需要 sqlite3，
    内存占用约 20MB；搜索与 TG 频道搜索并行执行，失败不影响原结果。
    """

    def __init__(self, fetcher, url='', timeout=20, enabled=True):
        self.fetcher = fetcher
        self.url = (url or '').strip() or SHARE115_DEFAULT_URL
        try:
            self.timeout = max(12, min(int(timeout or 20), 60))
        except Exception:
            self.timeout = 20
        self.enabled = bool(enabled)
        self.lines = []
        self.codes = []
        self.error = ''
        self._lock = threading.Lock()
        self._loaded = False
        self._last_try = 0

    @staticmethod
    def clean(s):
        s = str(s or '')
        for ch in ('\t', '\r', '\n', '$', '#'):
            s = s.replace(ch, ' ')
        return ' '.join(s.split()).strip()

    def load(self):
        if self._loaded:
            return bool(self.lines)
        if not self.enabled or not self.fetcher or requests is None:
            return False
        with self._lock:
            if self._loaded:
                return bool(self.lines)
            if time.time() - self._last_try < 60:
                return bool(self.lines)
            self._last_try = time.time()
            try:
                raw = self.fetcher(self.url, self.timeout)
                if not raw:
                    raise RuntimeError('索引下载为空或地址不可达')
                if raw[:2] == b'\x1f\x8b':
                    raw = gzip.decompress(raw)
                if not raw.startswith(b'C\t'):
                    raise RuntimeError('索引格式不正确')
                lines = raw.split(b'\n')
                codes = []
                for ln in lines:
                    if ln.startswith(b'C\t'):
                        p = ln.decode('utf-8', 'ignore').split('\t')
                        if len(p) >= 3:
                            codes.append((p[1], p[2]))
                if not codes:
                    raise RuntimeError('索引码表为空')
                self.codes = codes
                self.lines = lines
                self.error = ''
                self._loaded = True
            except Exception as e:
                self.error = '115 分享库加载失败：%s' % str(e)[:80]
            return bool(self.lines)

    @staticmethod
    def parse(ln):
        try:
            p = ln.decode('utf-8', 'ignore').split('\t')
        except Exception:
            return None
        if len(p) < 2 or not p[0]:
            return None
        if p[0] == 'F' and len(p) >= 5:
            return {'k': 'F', 'n': p[1], 'ci': p[2], 'f': p[3], 'cid': p[4]}
        if p[0] == 'D' and len(p) >= 5:
            return {'k': 'D', 'n': p[1], 'rid': p[2], 'cid': p[3], 'pid': p[4]}
        return None

    def code(self, ci):
        try:
            return self.codes[int(ci)]
        except Exception:
            return ('', '')

    def search(self, key, page=1, limit=SHARE115_SEARCH_LIMIT):
        if not self.load() or not key:
            return [], self.error
        needle = str(key).strip().lower().encode('utf-8')
        if not needle:
            return [], self.error
        # 纯中文按 UTF-8 字节子串匹配；含 ASCII 字母时忽略大小写
        ascii_kw = any(65 <= b <= 90 or 97 <= b <= 122 for b in needle)
        dirs, files = [], []
        for ln in self.lines:
            if not (ln.startswith(b'F\t') or ln.startswith(b'D\t')):
                continue
            if needle in (ln.lower() if ascii_kw else ln):
                (dirs if ln.startswith(b'D\t') else files).append(ln)
        hits = dirs + files
        start = max(0, (max(1, page) - 1) * limit)
        return hits[start:start + limit], ''

    def files_by_cid(self, cid, limit=SHARE115_MAX_EPISODES):
        target = str(cid).encode('utf-8')
        out = []
        for ln in self.lines:
            if not ln.startswith(b'F\t') or ln.rsplit(b'\t', 1)[-1] != target:
                continue
            d = self.parse(ln)
            if d:
                out.append(d)
            if len(out) >= limit:
                break
        return out

    def dir_children(self, parent_cid):
        target = str(parent_cid).encode('utf-8')
        out = []
        for ln in self.lines:
            if not ln.startswith(b'D\t') or ln.rsplit(b'\t', 1)[-1] != target:
                continue
            d = self.parse(ln)
            if d:
                out.append(d)
        return out

    def collect_dir(self, cid, max_files=SHARE115_MAX_EPISODES, max_depth=5):
        """深度优先展开目录树；返回 [(线路名, [文件 dict ...]), ...]"""
        groups, total, steps = [], 0, 0
        stack = [(str(cid), '', 0)]
        while stack and total < max_files and steps < 300:
            steps += 1
            cur, label, depth = stack.pop()
            fs = self.files_by_cid(cur, max_files - total)
            if fs:
                groups.append((label or '根目录', fs))
                total += len(fs)
            if depth >= max_depth or total >= max_files:
                continue
            kids = self.dir_children(cur)
            for k in reversed(kids):
                stack.append((k['cid'], (label + '/' + k['n']).strip('/'), depth + 1))
        return groups


class Spider(Spider):
    host = 'https://t.me'
    UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36')
    PROXY_LIST = [
        'http://127.0.0.1:2080', 'http://127.0.0.1:7890', 'http://127.0.0.1:10809',
        'http://127.0.0.1:10172', 'http://127.0.0.1:20172', 'http://127.0.0.1:7891',
        'http://127.0.0.1:10808', 'http://127.0.0.1:1087', 'http://127.0.0.1:3128',
        'http://127.0.0.1:1080', 'http://127.0.0.1:8080', 'http://127.0.0.1:9090',
    ]

    def __init__(self):
        self.channels = list(CHANNELS)
        self.timeout = 15
        self.session = None
        self._cursors = {}
        self._cache = {}
        self._detail_cache = {}
        self._lock = threading.Lock()
        self.cookie_115 = ''
        self.save_dir_name = '最近接收'
        self.save_cid = ''
        self.p115 = None
        self.db115 = None
        self.db115_enable = True
        self.db115_url = ''
        self.search_group = 'pan'
        self.group_only = False

    # ------------------------------------------------------------ 初始化
    def init(self, extend=''):
        ext = {}
        if extend:
            try:
                ext = json.loads(extend) if isinstance(extend, str) else dict(extend)
            except Exception:
                ext = {}
        try:
            self.timeout = int(ext.get('timeout') or 15)
        except Exception:
            self.timeout = 15

        # ---- 115 网盘：Cookie 由站源 ext 传入，115 不走推送 ----
        self.cookie_115 = str(ext.get('115_cookie') or ext.get('cookie') or '').strip()
        self.save_dir_name = str(ext.get('save_dir_name') or '最近接收').strip()
        self.save_cid = str(ext.get('save_cid') or '').strip()
        self.p115 = P115(self.cookie_115, self.save_dir_name, self.save_cid,
                         timeout=self.timeout) if self.cookie_115 else None

        # ---- 115 分享库：静态索引，首次搜索时按需下载，不走推送 ----
        self.db115_enable = str(ext.get('115db_enable', 1)).strip().lower() \
            not in ('0', 'false', 'no', 'off', '')
        self.db115_url = str(ext.get('115db_url') or '').strip()
        self.db115 = Share115DB(self._get_bytes, self.db115_url,
                                timeout=max(12, self.timeout + 8),
                                enabled=self.db115_enable)

        # ---- 搜索结果分类：pan=按网盘类型 / channel=按频道 / 0=关闭 ----
        sg = str(ext.get('search_group', 'pan')).strip().lower()
        if sg in ('pan', 'channel'):
            self.search_group = sg
        elif sg in ('0', 'false', 'no', 'off', ''):
            self.search_group = '0'
        else:
            self.search_group = 'pan'
        self.group_only = str(ext.get('group_only', 0)).strip().lower() in ('1', 'true', 'yes', 'on')

        chans = ext.get('channels')
        if isinstance(chans, list) and chans:
            parsed = []
            for c in chans:
                if not isinstance(c, dict):
                    continue
                cid = c.get('type_id') or c.get('id') or c.get('channel')
                cname = c.get('type_name') or c.get('name') or cid
                if cid:
                    parsed.append({'type_id': str(cid).lstrip('@'), 'type_name': cname})
            if parsed:
                self.channels = parsed

        if requests is None:
            return
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        })
        proxy = ext.get('proxy')
        proxies = {}
        if isinstance(proxy, str) and proxy.strip():
            p = proxy.strip()
            if not p.startswith('http'):
                p = 'http://' + p
            proxies = {'http': p, 'https': p}
        elif isinstance(proxy, dict):
            for k, v in proxy.items():
                if k in ('http', 'https') and v:
                    v = str(v)
                    proxies[k] = v if v.startswith('http') else 'http://' + v
        if not proxies and not self._reachable():
            p = self._detect_proxy()
            if p:
                proxies = {'http': p, 'https': p}
        if proxies:
            self.session.proxies.update(proxies)

    def getName(self):
        return 'TG搜·115直连'

    def isVideoFormat(self, url):
        return is_video_url(url)

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    def _reachable(self):
        try:
            r = requests.get(self.host, timeout=3, headers={'User-Agent': self.UA})
            return r.status_code < 400
        except Exception:
            return False

    def _detect_proxy(self):
        def probe(p):
            try:
                r = requests.get(self.host, proxies={'http': p, 'https': p},
                                 timeout=2.5, headers={'User-Agent': self.UA})
                return p if r.status_code < 400 else None
            except Exception:
                return None
        try:
            with ThreadPoolExecutor(max_workers=6) as ex:
                for res in ex.map(probe, self.PROXY_LIST):
                    if res:
                        return res
        except Exception:
            pass
        return None

    # ------------------------------------------------------------ 抓取
    def _ensure_session(self):
        if self.session is None and requests is not None:
            self.session = requests.Session()
            self.session.headers.update({
                'User-Agent': self.UA,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9',
            })
        return self.session

    def _get(self, url, timeout=None, retries=1, ttl=0):
        if self._ensure_session() is None:
            raise RuntimeError('requests 不可用')
        if ttl:
            with self._lock:
                hit = self._cache.get(url)
            if hit and time.time() - hit[0] < ttl:
                return hit[1]
        last = None
        for _ in range(retries + 1):
            try:
                r = self.session.get(url, timeout=timeout or self.timeout)
                if r.status_code == 200 and r.text:
                    if ttl:
                        with self._lock:
                            self._cache[url] = (time.time(), r.text)
                    return r.text
                last = RuntimeError('http %s' % r.status_code)
            except Exception as e:
                last = e
        raise last if last else RuntimeError('fetch failed')

    # ------------------------------------------------------------ 消息解析
    def _text_of(self, block):
        m = re.search(r'js-message_text[^>]*>(.*?)</div>', block, re.S)
        if not m:
            m = re.search(r'tgme_widget_message_text[^>]*>(.*?)</div>', block, re.S)
        if not m:
            return ''
        t = re.sub(r'<br\s*/?>', '\n', m.group(1))
        t = re.sub(r'<[^>]+>', '', t)
        t = unescape(t).replace('\xa0', ' ')
        return t

    def _clean_title(self, t):
        t = unescape(t or '')
        t = re.sub(r'<[^>]+>', '', t)
        t = re.sub(r'\s+', ' ', t).strip(' -|/·、.。')
        t = re.sub(r'^(?:【[^】]{1,12}】|\[[^\]]{1,12}\])\s*', '', t)
        t = re.sub(r'\s*[（(]?\s*(?:全\s*\d+\s*集|共\s*\d+\s*集|完结|已完结|连载中)\s*[)）]?\s*$', '', t)
        t = re.sub(r'\s*(?:更新至|更新到|更至)\s*(?:第)?\s*\d+\s*(?:集|期)?.*$', '', t)
        return t.strip()[:80]

    def _title_of(self, text, block, mid=''):
        title = ''
        labeled = False
        for line in (text or '').split('\n'):
            line = line.strip()
            if not line:
                continue
            if re.match(r'^(?:[#＃]\S*\s*)+$', line):
                continue
            if len(re.sub(r'[\W_]+', '', line)) < 2:
                continue
            m = re.match(r'^(?:名称|资源名称|资源标题|片名|剧名|标题)\s*[：:]\s*(.+)$', line)
            if m:
                title = m.group(1).strip()
                labeled = True
            else:
                title = line
            break
        if not title:
            bolds = re.findall(r'<b[^>]*>(.*?)</b>', block, re.S)
            title = ' '.join(unescape(re.sub(r'<[^>]+>', '', b)).strip() for b in bolds)
        title = self._clean_title(title)
        if not title and mid:
            title = 'TG资源 ' + mid.split('/')[-1]
        return title, labeled

    def _content_of(self, text):
        t = text or ''
        m = re.search(r'(?:简介|剧情简介|内容简介|剧情|介绍)\s*[：:]\s*', t)
        if m:
            t = t[m.end():]
        keep = []
        for line in t.split('\n'):
            s = line.strip()
            if not s:
                if keep:
                    keep.append('')
                continue
            if re.match(r'^(?:标签|链接|网盘|下载|地址|资源链接|获取|提取码|夸克|百度|阿里|迅雷|115|123|天翼|移动|UC|磁力|ED2K)\s*[：:]', s, re.I):
                break
            if re.search(r'https?://|magnet:\?', s):
                break
            keep.append(s)
        return re.sub(r'\s+', ' ', ' '.join(keep)).strip()[:600]

    def _pic_of(self, block):
        m = re.search(r"background-image\s*:\s*url\(\s*['\"]?([^'\")]+)", block)
        pic = unescape(m.group(1)).strip() if m else ''
        if not pic:
            m = re.search(r'<video[^>]*?poster="([^"]+)"', block)
            pic = unescape(m.group(1)) if m else ''
        if pic.startswith('//'):
            pic = 'https:' + pic
        return pic

    def _parse_block(self, block):
        mid = ''
        m = re.search(r'data-post="([^"]+)"', block)
        if m:
            mid = m.group(1)

        text = self._text_of(block)
        title, labeled = self._title_of(text, block, mid)
        pic = self._pic_of(block)

        hrefs = [unescape(h) for h in re.findall(r'href="([^"]+)"', block)]
        bare = re.findall(r'(?:magnet:\?xt=urn:btih:[0-9a-zA-Z]+|https?://[^\s"\'<>]+)', text)
        vids = [unescape(v) for v in re.findall(r'<(?:video|source)[^>]*?src="([^"]+)"', block)]

        groups = {}

        def add(u):
            u = (u or '').strip().strip('.,;:!?)}」』"\'')
            if len(u) < 12:
                return
            low = u.lower()
            if any(x in low for x in ('t.me/', 'telegram.me/', 'telesco.pe/', 'telegram.org/', 'tgbun.com')):
                return
            t = pan_type(u)
            if not t:
                return
            lst = groups.setdefault(t, [])
            if u not in lst and len(lst) < 40:
                lst.append(u)

        for h in hrefs:
            if h.startswith(('http://', 'https://', 'magnet:', 'ed2k:')):
                add(h)
        for u in bare:
            add(u)

        vlist = groups.setdefault('在线视频', [])
        for v in vids:
            if v.startswith('http') and v not in vlist and len(vlist) < 30:
                vlist.append(v)
        if not vlist:
            groups.pop('在线视频', None)

        if not groups:
            return None

        # 广告消息：没有“名称：”标记 + 命中广告词 + 没有可播视频
        low = (text or '').lower()
        if '在线视频' not in groups and not labeled and any(w in low for w in AD_WORDS):
            return None

        content = self._content_of(text)
        codes = []
        for m in re.finditer(r'(?:提取码|提取密码|访问码|提取口令|密码|pwd)\s*[:：=]?\s*([0-9a-zA-Z]{2,10})', text or ''):
            c = m.group(1)
            if c.lower() not in ('http', 'https', 'www') and c not in codes:
                codes.append(c)
        if codes:
            content = (content + ' ｜ 提取码：' + ' / '.join(codes[:6])).strip()

        ordered = [(k, groups[k]) for k in PAN_ORDER if k in groups]
        ordered += [(k, v) for k, v in groups.items() if k not in PAN_ORDER]
        return {
            'mid': mid,
            'title': title,
            'pic': pic,
            'content': content,
            'groups': ordered,
        }

    def _parse_messages(self, html):
        if not html:
            return []
        out, seen = [], set()
        for block in html.split('tgme_widget_message_bubble')[1:]:
            try:
                msg = self._parse_block(block)
            except Exception:
                msg = None
            if not msg:
                continue
            key = msg['mid'] or (msg['title'] + str(msg['groups'])[:60])
            if key in seen:
                continue
            seen.add(key)
            out.append(msg)
        return out

    # ------------------------------------------------------------ 列表项构造
    def _item(self, msg, prefix=''):
        data = {
            'n': msg['title'],
            'p': msg['pic'],
            'c': msg['content'][:140],
            'm': msg['mid'],
            'g': [[k, v] for k, v in msg['groups']],
        }
        remarks = ' | '.join('%s×%d' % (k, len(v)) for k, v in msg['groups'][:4])
        if prefix:
            remarks = prefix + ' · ' + remarks
        return {
            'vod_id': 'detail|' + pack_id(data),
            'vod_name': msg['title'][:60],
            'vod_pic': msg['pic'],
            'vod_remarks': remarks,
            'vod_content': msg['content'][:200],
            'vod_tag': 'folder',
        }

    # ------------------------------------------------------------ 首页 / 分类
    def homeContent(self, _filter=None):
        classes = []
        for ch in self.channels:
            cid = str(ch.get('type_id') or '').strip()
            if not cid:
                continue
            classes.append({
                'type_id': cid,
                'type_name': ch.get('type_name') or cid,
            })
        return {'class': classes, 'filters': {}}

    def homeVideoContent(self):
        try:
            cid = str(self.channels[0]['type_id'])
            res = self._cat_channel(cid, 1)
            return {'list': res.get('list', [])[:24]}
        except Exception:
            return {'list': []}

    def _empty(self, pg):
        return {'list': [], 'page': pg, 'pagecount': pg, 'limit': 0, 'total': 0}

    def categoryContent(self, tid, pg, _filter=None, extend=None):
        tid = unquote(str(tid or '')).strip()
        try:
            page = int(pg or 1)
        except (TypeError, ValueError):
            page = 1
        if tid.startswith('scat|'):
            d = unpack_id(tid[len('scat|'):]) or {}
            v = d.get('v') or []
            return {'list': v, 'page': 1, 'pagecount': 1,
                    'limit': len(v), 'total': len(v)}
        if tid.startswith('detail|'):
            return self._cat_groups(tid.split('|', 1)[1])
        if tid.startswith('group|'):
            parts = tid.split('|')
            if len(parts) < 3:
                return self._empty(1)
            try:
                idx = int(parts[2])
            except ValueError:
                idx = 0
            return self._cat_links(parts[1], idx)
        return self._cat_channel(tid, page)

    def _cat_groups(self, payload):
        data = unpack_id(payload)
        if not data or not data.get('g'):
            return self._empty(1)
        folders = []
        for i, g in enumerate(data['g']):
            try:
                name, urls = g[0], g[1]
            except (IndexError, TypeError):
                continue
            folders.append({
                'vod_id': 'group|%s|%d' % (payload, i),
                'vod_name': '%s网盘' % name if name != '在线视频' else '在线视频',
                'vod_pic': data.get('p') or '',
                'vod_remarks': '%d条资源' % len(urls),
                'vod_content': '%s\n共 %d 条%s链接，点击选择' % (data.get('n') or '', len(urls), name),
                'vod_tag': 'folder',
            })
        return {'list': folders, 'page': 1, 'pagecount': 1, 'limit': len(folders), 'total': len(folders)}

    def _cat_links(self, payload, gidx):
        data = unpack_id(payload)
        if not data or not data.get('g'):
            return self._empty(1)
        if gidx < 0 or gidx >= len(data['g']):
            return self._empty(1)
        name, urls = data['g'][gidx][0], data['g'][gidx][1]
        videos = []
        for j, u in enumerate(urls):
            videos.append({
                'vod_id': 'pan|%s|%d|%d' % (payload, gidx, j),
                'vod_name': '%s线路%d' % (name, j + 1),
                'vod_pic': data.get('p') or '',
                'vod_remarks': name,
                'vod_content': '%s\n%s' % (data.get('n') or '', u),
                'vod_tag': 'file',
            })
        return {'list': videos, 'page': 1, 'pagecount': 1, 'limit': len(videos), 'total': len(videos)}

    def _cat_channel(self, tid, page):
        tid = tid.lstrip('@')
        url = '%s/s/%s' % (self.host, quote(tid, safe=''))
        if page > 1:
            with self._lock:
                before = self._cursors.get((tid, page))
            if not before:
                return self._empty(page)
            url += '?before=%s' % before
        try:
            html = self._get(url, ttl=60)
        except Exception:
            return self._empty(page)

        m = (re.search(r'js-messages_more[^>]*data-before="(\d+)"', html)
             or re.search(r'data-before="(\d+)"', html)
             or re.search(r'\?before=(\d+)', html))
        if m:
            with self._lock:
                self._cursors[(tid, page + 1)] = m.group(1)

        msgs = self._parse_messages(html)
        items = [self._item(msg) for msg in reversed(msgs)]
        pagecount = page + 1 if items else page
        return {'list': items, 'page': page, 'pagecount': pagecount,
                'limit': len(items), 'total': 999999}

    # ------------------------------------------------------------ 详情
    def detailContent(self, ids):
        if not ids:
            return {'list': []}
        raw = unquote(str(ids[0])).strip()
        if raw.startswith('db115err|'):
            d = unpack_id(raw[len('db115err|'):]) or {}
            msg = str(d.get('m') or '索引未加载')
            return {'list': [{
                'vod_id': raw, 'vod_name': '115大包索引未加载', 'vod_pic': '',
                'vod_content': (msg + '\n请把 115share_index.txt.gz 上传到静态托管，'
                                '并确认站源 ext 的 115db_url 能下载到该文件。'
                                '索引下载会并发尝试代理与直连两条线路。'),
                'vod_play_from': '提示',
                'vod_play_url': '索引加载失败$115err|',
            }]}
        if raw.startswith('115db|'):
            return self._detail_115db(raw[len('115db|'):])
        if raw.startswith('pan|'):
            return self._detail_one(raw)
        if raw.startswith('detail|'):
            return self._detail_all(raw.split('|', 1)[1])
        if raw.startswith('group|'):
            parts = raw.split('|')
            if len(parts) > 1:
                return self._detail_all(parts[1])
        data = unpack_id(raw)
        if data and data.get('g'):
            return self._detail_all(raw)
        return {'list': []}

    def _detail_one(self, raw):
        parts = raw.split('|')
        if len(parts) < 4:
            return {'list': []}
        data = unpack_id(parts[1])
        try:
            gidx, j = int(parts[2]), int(parts[3])
        except ValueError:
            return {'list': []}
        if not data or gidx >= len(data.get('g') or []) or j >= len(data['g'][gidx][1]):
            return {'list': []}
        name, urls = data['g'][gidx][0], data['g'][gidx][1]
        url = urls[j]
        play_from, play_url = self._groups_to_play([(name, [url])])
        return {'list': [{
            'vod_id': raw,
            'vod_name': data.get('n') or 'TG资源',
            'vod_pic': data.get('p') or '',
            'vod_content': '%s\n%s\n%s' % (data.get('c') or data.get('n') or '', name, url),
            'vod_play_from': '$$$'.join(play_from) if play_from else name,
            'vod_play_url': '$$$'.join(play_url) if play_url else ('%s线路%d$%s' % (name, j + 1, url)),
        }]}

    # ------------------------------------------------ 115 选集展开
    def _episodes_115(self, urls):
        if not self.p115 or not self.p115.enabled:
            return '', '未配置 115_cookie（请写在站源 ext）'
        out, seen, err = [], set(), ''
        for u in urls[:8]:
            p = _parse_115_share(u)
            if not p:
                continue
            try:
                vids = self.p115.list_videos(u)
            except Exception as e:
                err = str(e)[:60]
                continue
            for v in vids:
                fid = v['fid']
                if fid in seen:
                    continue
                seen.add(fid)
                token = _build_115_play_id(p['share_id'], p['pwd'], fid, v['name'])
                out.append('%s$%s' % (v['label'], token))
            if len(out) >= 80:
                break
        if out:
            return '#'.join(out), ''
        return '', (err or '未读取到 115 视频文件（Cookie 可能失效或分享需提取码）')

    def _groups_to_play(self, groups):
        play_from, play_url = [], []
        for name, urls in groups:
            if name == '115':
                eps, note = self._episodes_115(urls)
                play_from.append('115')
                if eps:
                    play_url.append(eps)
                else:
                    label = _clean_label(note or '115 解析失败', '115 解析失败')[:60]
                    play_url.append('%s$115err|' % label)
                continue
            seen, eps = set(), []
            for u in urls:
                if not u or u in seen:
                    continue
                seen.add(u)
                eps.append('%s线路%d$%s' % (name, len(eps) + 1, u))
            if eps:
                play_from.append(name)
                play_url.append('#'.join(eps))
        return play_from, play_url

    def _detail_all(self, payload):
        data = unpack_id(payload)
        if not data or not data.get('g'):
            return {'list': [{'vod_id': 'detail|' + payload, 'vod_name': '加载失败',
                              'vod_play_from': '错误', 'vod_play_url': '无资源$'}]}
        play_from, play_url = self._groups_to_play(data['g'])
        if not play_from:
            play_from, play_url = ['无资源'], ['未提取到网盘链接$']
        return {'list': [{
            'vod_id': 'detail|' + payload,
            'vod_name': data.get('n') or 'TG资源',
            'vod_pic': data.get('p') or '',
            'vod_content': data.get('c') or data.get('n') or '',
            'vod_remarks': ' | '.join('%s×%d' % (n, len(u)) for n, u in data['g']),
            'vod_play_from': '$$$'.join(play_from),
            'vod_play_url': '$$$'.join(play_url),
        }]}

    # ------------------------------------------------------------ 搜索
    # ---------------------------------- 115 分享库：下载 / 搜索 / 详情 / 播放
    def _get_bytes(self, url, timeout=20):
        """下载二进制索引：代理链路与国内直连并发双试，谁先成功用谁。"""
        if requests is None:
            return None

        def via_proxy():
            s = self._ensure_session()
            if s is None:
                return None
            try:
                r = s.get(url, timeout=timeout)
                return r.content if r.status_code == 200 and r.content else None
            except Exception:
                return None

        def direct():
            try:
                s = requests.Session()
                s.trust_env = False
                r = s.get(url, timeout=timeout)
                return r.content if r.status_code == 200 and r.content else None
            except Exception:
                return None

        ex = ThreadPoolExecutor(max_workers=2)
        try:
            futs = [ex.submit(via_proxy), ex.submit(direct)]
            for f in as_completed(futs, timeout=timeout + 2):
                try:
                    data = f.result()
                except Exception:
                    continue
                if data:
                    return data
        except Exception:
            pass
        finally:
            ex.shutdown(wait=False)
        return None

    def _db115_play_id(self, f):
        c, r = self.db115.code(f.get('ci', '0')) if self.db115 else ('', '')
        return '115db|' + pack_id({
            'k': 'P',
            'c': c or str(f.get('c') or ''),
            'r': r or str(f.get('r') or ''),
            'f': str(f.get('f') or ''),
            'n': Share115DB.clean(f.get('n') or '')[:120],
        })

    def _db115_episodes(self, files):
        eps, seen = [], set()
        for f in files:
            fid = str(f.get('f') or '')
            if not fid or fid in seen:
                continue
            seen.add(fid)
            nm = re.sub(r'\.[A-Za-z0-9]{2,5}$', '', Share115DB.clean(f.get('n') or ''))
            eps.append('%s$%s' % (nm[:60] or '播放', self._db115_play_id(f)))
        return eps

    def _db115_item(self, row):
        name = Share115DB.clean(row.get('n') or '')[:60] or '115分享'
        data = {'k': row['k'], 'n': str(row.get('n') or '')[:160],
                'cid': row.get('cid', '')}
        if row['k'] == 'F':
            data['ci'] = row.get('ci', '0')
            data['f'] = row.get('f', '')
        return {
            'vod_id': '115db|' + pack_id(data),
            'vod_name': name,
            'vod_pic': '',
            'vod_remarks': '115大包 · ' + ('合集目录' if row['k'] == 'D' else '分享文件'),
            'vod_content': Share115DB.clean(row.get('n') or '')[:200],
        }

    def _detail_115db(self, payload):
        data = unpack_id(payload) or {}
        title = Share115DB.clean(data.get('n') or '115分享资源')[:60]
        base = {'vod_id': '115db|' + payload, 'vod_name': title,
                'vod_pic': '', 'vod_content': title}
        if not self.db115 or not self.db115_enable:
            return {'list': [dict(base, vod_play_from='提示',
                                  vod_play_url='115 分享库已关闭$115err|')]}
        self.db115.load()
        if data.get('k') == 'D':
            groups = self.db115.collect_dir(data.get('cid') or '')
            if not groups:
                return {'list': [dict(base, vod_play_from='提示',
                                      vod_play_url='索引未加载或合集为空$115err|')]}
            play_from, play_url = [], []
            for label, fs in groups[:SHARE115_MAX_LINES]:
                eps = self._db115_episodes(fs)
                if eps:
                    play_from.append(Share115DB.clean(label)[:24] or '115')
                    play_url.append('#'.join(eps))
        else:
            files = [data]
            if data.get('cid'):
                sibs = self.db115.files_by_cid(data['cid'], SHARE115_MAX_EPISODES)
                if sibs:
                    files = ([f for f in sibs if f.get('f') == data.get('f')] +
                             [f for f in sibs if f.get('f') != data.get('f')])
            eps = self._db115_episodes(files)
            play_from = ['115大包']
            play_url = ['#'.join(eps) if eps else '无资源$115err|']
        if not play_from:
            play_from, play_url = ['提示'], ['索引未加载$115err|']
        return {'list': [dict(base,
                              vod_play_from='$$$'.join(play_from),
                              vod_play_url='$$$'.join(play_url))]}

    def _play_115db(self, payload):
        d = unpack_id(payload) or {}
        if d.get('k') == 'D':
            return self._p115_error('这是 115 合集目录，请进入详情选择具体集数')
        if not self.p115 or not self.p115.enabled:
            return self._p115_error('115 分享库需在站源 ext 配置 115_cookie 才能直接播放（不走推送）')
        try:
            return self.p115.play(str(d.get('c') or ''), str(d.get('r') or ''),
                                  str(d.get('f') or ''), str(d.get('n') or ''))
        except Exception as e:
            return self._p115_error('115 分享库播放失败：%s' % e)

    def _make_group_cards(self, buckets, mode):
        """把搜索结果按分类聚合成 folder 卡片（vod_tag=folder -> categoryContent）。"""
        cards = []

        def slim(it):
            return {'vod_id': it.get('vod_id', ''),
                    'vod_name': it.get('vod_name', ''),
                    'vod_pic': it.get('vod_pic', ''),
                    'vod_remarks': it.get('vod_remarks', ''),
                    'vod_content': it.get('vod_content', '')}

        for name in sorted(buckets, key=lambda k: (-len(buckets[k]), k)):
            v = [slim(x) for x in buckets[name][:60]]
            if not v:
                continue
            cards.append({
                'vod_id': 'scat|' + pack_id({'n': name, 'v': v}),
                'vod_name': '%s (%d)' % (name, len(v)),
                'vod_pic': '',
                'vod_remarks': '按网盘分类' if mode == 'pan' else '按频道分类',
                'vod_content': '共 %d 条资源，点击进入列表' % len(v),
                'vod_tag': 'folder',
            })
        return cards

    def searchContent(self, key, quick=False, pg='1'):
        return self.searchContentPage(key, quick, pg)

    def searchContentPage(self, key, quick=False, pg='1'):
        key = (key or '').strip()
        try:
            page = int(pg or 1)
        except (TypeError, ValueError):
            page = 1
        if not key:
            return {'list': [], 'page': page, 'pagecount': 1, 'limit': 0, 'total': 0}

        qkey = quote(key, safe='')
        results = {}

        def one(ch):
            cid = str(ch.get('type_id') or '')
            try:
                html = self._get('%s/s/%s?q=%s' % (self.host, quote(cid, safe=''), qkey),
                                 timeout=6, retries=0)
                return cid, self._parse_messages(html)
            except Exception:
                return cid, []

        channels = self.channels
        ex = ThreadPoolExecutor(max_workers=11)
        tasks, db_hits = {}, []
        try:
            for ch in channels:
                tasks[ex.submit(one, ch)] = ('tg', None)
            if self.db115 and self.db115_enable:
                tasks[ex.submit(self.db115.search, key, page,
                                SHARE115_SEARCH_LIMIT)] = ('db', None)
            for fut in as_completed(tasks, timeout=35):
                kind, _ = tasks[fut]
                try:
                    res = fut.result()
                except Exception:
                    continue
                if kind == 'tg':
                    cid, msgs = res
                    if msgs:
                        results[cid] = msgs
                else:
                    db_hits = (res or ([], ''))[0]
        except Exception:
            pass
        finally:
            ex.shutdown(wait=False)

        names = {str(ch.get('type_id')): (ch.get('type_name') or ch.get('type_id')) for ch in channels}
        items, seen, buckets = [], set(), {}
        for ch in channels:
            cid = str(ch.get('type_id') or '')
            chan_name = Share115DB.clean(names.get(cid, cid))[:20] or cid
            for msg in results.get(cid, []):
                it = self._item(msg, prefix=names.get(cid, cid))
                if it['vod_id'] in seen:
                    continue
                seen.add(it['vod_id'])
                items.append(it)
                if self.search_group == 'channel':
                    keys = [chan_name]
                else:
                    keys = [Share115DB.clean(g[0])[:16] or '其它'
                            for g in (msg.get('groups') or [])]
                for k in (keys or ['其它']):
                    buckets.setdefault(k, []).append(it)
                if len(items) >= 60:
                    break
            if len(items) >= 60:
                break
        # 115 分享库结果：平铺的同时归入「115大包」分类
        for ln in db_hits:
            row = Share115DB.parse(ln)
            if not row:
                continue
            it = self._db115_item(row)
            if it['vod_id'] in seen:
                continue
            seen.add(it['vod_id'])
            items.append(it)
            buckets.setdefault('115大包', []).append(it)

        cards = []
        if self.search_group in ('pan', 'channel') and buckets:
            cards = self._make_group_cards(buckets, self.search_group)
        items = cards if self.group_only else (cards + items[:24])

        # 索引失败时给出可见提示，避免「搜不到却不知道为什么」
        if self.db115 and self.db115_enable and self.db115.error:
            items.append({
                'vod_id': 'db115err|' + pack_id({'m': self.db115.error}),
                'vod_name': '115大包索引未加载',
                'vod_pic': '',
                'vod_remarks': '点开查看原因',
                'vod_content': self.db115.error,
            })
        return {'list': items, 'page': page, 'pagecount': page + 1 if items else page,
                'limit': len(items), 'total': 999999}

    # ------------------------------------------------------------ 播放
    def playerContent(self, flag, vid, _vip_flags=None):
        result = {'parse': 0, 'playUrl': '', 'url': '',
                  'header': {'User-Agent': self.UA, 'Referer': 'https://t.me/'}}
        url = (vid or '').strip()
        if not url:
            return result
        if url.startswith(('pan|', 'group|', 'detail|')):
            url = self._first_url(url)
        if '$' in url:
            url = url.rsplit('$', 1)[-1].strip()

        # ---- 115 分享库：直连播放，绝不推送 ----
        if url.startswith('115db|'):
            return self._play_115db(url[len('115db|'):])

        # ---- 115：直连播放，绝不推送 ----
        if url.startswith('115P|'):
            info = _parse_115_play_id(url)
            if not info:
                return self._p115_error('115 播放 token 无效')
            if not self.p115 or not self.p115.enabled:
                return self._p115_error('115 需在站源 ext 配置 115_cookie')
            try:
                return self.p115.play(info['share_id'], info['pwd'], info['fid'], info['name'])
            except Exception as e:
                return self._p115_error('115 播放失败：%s' % e)
        if url.startswith('115err|'):
            return self._p115_error('115 未走推送：请在站源 ext 配置 115_cookie，或检查 Cookie/分享是否有效')
        if pan_type(url) == '115' or _is_115_share(url):
            return self._play_115_share(url)

        if url.startswith(('magnet:', 'ed2k:', 'thunder:')):
            result['url'] = url
            return result
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        if is_video_url(url):
            result['url'] = url
        else:
            # 其余网盘：交给客户端推送（FongMi/OK影视 会唤起网盘客户端或内置浏览器打开）
            result['url'] = 'push:' + url
        return result

    @staticmethod
    def _p115_error(msg):
        return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '', 'header': {}, 'msg': msg}

    def _play_115_share(self, url):
        if not self.p115 or not self.p115.enabled:
            return self._p115_error('115 网盘需在站源 ext 配置 115_cookie 才能直接播放')
        if not _parse_115_share(url):
            return self._p115_error('该 115 链接不是分享链接，无法直接播放（已禁用推送）')
        try:
            vids = self.p115.list_videos(url)
        except Exception as e:
            return self._p115_error('115 分享读取失败：%s' % e)
        if not vids:
            return self._p115_error('115 分享内未找到视频文件（Cookie 可能失效）')
        p = _parse_115_share(url) or {}
        v = vids[0]
        return self.p115.play(p.get('share_id', ''), p.get('pwd', ''), v['fid'], v['name'])

    def _first_url(self, raw):
        try:
            parts = raw.split('|')
            if parts[0] == 'pan|':
                data = unpack_id(parts[1])
                urls = data['g'][int(parts[2])][1]
                return urls[int(parts[3])]
            if parts[0] == 'group|':
                data = unpack_id(parts[1])
                urls = data['g'][int(parts[2])][1]
                return urls[0] if urls else ''
            data = unpack_id(parts[1] if len(parts) > 1 else raw)
            for _n, urls in (data or {}).get('g') or []:
                if urls:
                    return urls[0]
        except Exception:
            pass
        return ''

    def localProxy(self, params):
        return None
