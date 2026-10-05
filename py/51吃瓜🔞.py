# -*- coding: utf-8 -*-
# 51吃瓜网 TVBox 爬虫
# 站点: https://body.ycvvabhqs.cc/ (51cg1.com)
# 结构: Typecho + Mirages 主题, 列表页/详情页直接嵌入 dplayer config (含完整 m3u8)
# 播放: AES-128 标准 HLS, 无需额外解密

import re
import sys
import json
import base64
import threading
import requests
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote

try:
    from Crypto.Cipher import AES
except ImportError:
    AES = None

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def init(self, extend=""): pass
        def destroy(self): pass
        def getName(self): return ""
        def isVideo(self): return True
        def homeContent(self, filter=False): return {"class": []}
        def homeVideoContent(self): return {"list": []}
        def categoryContent(self, tid, pg="1", filter=False, extend=None): return {"list": []}
        def detailContent(self, ids): return {"list": []}
        def searchContent(self, key, quick=False, pg="1"): return {"list": []}
        def playerContent(self, flag, id, vipFlags=None): return {"parse": 0, "url": "", "header": {}, "content": ""}
        def localProxy(self, params): return []


BASE_URL = "https://body.ycvvabhqs.cc"
# 备用域名
FALLBACK_HOSTS = ["https://body.ycvvabhqs.cc"]
# CDN
VIDEO_HOST = "https://hls.qldjxf.cn"

# ---------- 封面图 AES-CBC 解密参数 ----------
# 来源: /usr/themes/Mirages/js/7.10.0/image.20260416.js
#   cryjs.AES.decrypt(word, cc("102_53_100_57_54_53_100_102_55_53_51_51_54_50_55_48"),
#                     {iv: cc("57_55_98_54_48_51_57_52_97_98_99_50_102_98_101_49"),
#                      mode: CBC, padding: Pkcs7})
IMG_AES_KEY = b"f5d965df75336270"
IMG_AES_IV  = b"97b60394abc2fbe1"
IMG_CDN_HOST = "pic.ndhixj.cn"
IMG_CACHE = {}
IMG_CACHE_MAX = 80
# 本地图片解密代理端口
PROXY_PORT = 19881


# ---------- 纯 Python AES-128 实现（TVBox 环境无 pycryptodome 时兜底） ----------
def _build_sbox():
    """构造标准 AES S-box 与其逆表"""
    s = bytes.fromhex(
        "637c777bf26b6fc53001672bfed7ab76"
        "ca82c97dfa5947f0add4a2af9ca472c0"
        "b7fd9326363ff7cc34a5e5f171d83115"
        "04c723c31896059a071280e2eb27b275"
        "09832c1a1b6e5aa0523bd6b329e32f84"
        "53d100ed20fcb15b6acbbe394a4c58cf"
        "d0efaafb434d338545f9027f503c9fa8"
        "51a3408f929d38f5bcb6da2110fff3d2"
        "cd0c13ec5f974417c4a77e3d645d1973"
        "60814fdc222a908846eeb814de5e0bdb"
        "e0323a0a4906245cc2d3ac629195e479"
        "e7c8376d8dd54ea96c56f4ea657aae08"
        "ba78252e1ca6b4c6e8dd741f4bbd8b8a"
        "703eb5664803f60e613557b986c11d9e"
        "e1f8981169d98e949b1e87e9ce5528df"
        "8ca1890dbfe6426841992d0fb054bb16"
    )
    inv = [0] * 256
    for i, v in enumerate(s):
        inv[v] = i
    return s, bytes(inv)


_SBOX, _INV_SBOX = _build_sbox()
_RCON = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36)


def _xtime(a):
    return ((a << 1) ^ 0x1b) & 0xff if a & 0x80 else (a << 1) & 0xff


def _gmul(a, b):
    """GF(2^8) 乘法"""
    r = 0
    for _ in range(8):
        if b & 1:
            r ^= a
        b >>= 1
        a = _xtime(a)
    return r & 0xff


# --- 预计算乘法表：把 MixColumns 的 16 次 gmul（每次 8 轮循环）降为 16 次查表 ---
# 一次性开销 6×256 次 gmul，换取每块 ~1000 倍加速
_MUL2 = [_gmul(i, 2) for i in range(256)]
_MUL3 = [_gmul(i, 3) for i in range(256)]
_MUL9 = [_gmul(i, 9) for i in range(256)]
_MUL11 = [_gmul(i, 11) for i in range(256)]
_MUL13 = [_gmul(i, 13) for i in range(256)]
_MUL14 = [_gmul(i, 14) for i in range(256)]


def _key_expansion(key):
    """AES-128 密钥扩展，返回 44 个 32bit 字"""
    w = [int.from_bytes(key[i * 4:(i + 1) * 4], "big") for i in range(4)]
    for i in range(4, 44):
        t = w[i - 1]
        if i % 4 == 0:
            t = ((t << 8) | (t >> 24)) & 0xffffffff  # RotWord
            t = (_SBOX[(t >> 24) & 0xff] << 24
                 | _SBOX[(t >> 16) & 0xff] << 16
                 | _SBOX[(t >> 8) & 0xff] << 8
                 | _SBOX[t & 0xff])                  # SubWord
            t ^= (_RCON[i // 4 - 1] << 24)
        w.append(w[i - 4] ^ t)
    return w


def _inv_shift_sub(state):
    """InvShiftRows（每行右移 r 位）+ InvSubBytes 合并（列优先存储）

    源遍历：源 (r, c) 的值移动到目标 (r, (c + r) % 4) —— 右移
    """
    ns = [0] * 16
    for r in range(4):
        for c in range(4):
            ns[r + ((c + r) % 4) * 4] = _INV_SBOX[state[r + c * 4]]
    return ns


def _add_round_key(state, w, base):
    """AddRoundKey: state[0][c] 对应 word 的最高字节 (>>24)，依此递减

    整列打包成 32 位一次异或，避免 16 次单独的移位与赋值。
    """
    for c in range(4):
        v = ((state[c * 4] << 24) | (state[c * 4 + 1] << 16) |
             (state[c * 4 + 2] << 8) | state[c * 4 + 3]) ^ w[base + c]
        state[c * 4]     = (v >> 24) & 0xff
        state[c * 4 + 1] = (v >> 16) & 0xff
        state[c * 4 + 2] = (v >> 8) & 0xff
        state[c * 4 + 3] = v & 0xff
    return state


def _inv_mix_columns(state):
    """InvMixColumns：用预计算乘法表代替 16 次 gmul（纯 Python 路径关键优化）"""
    ns = [0] * 16
    for c in range(4):
        s0 = state[c * 4]
        s1 = state[c * 4 + 1]
        s2 = state[c * 4 + 2]
        s3 = state[c * 4 + 3]
        ns[c * 4]     = _MUL14[s0] ^ _MUL11[s1] ^ _MUL13[s2] ^ _MUL9[s3]
        ns[c * 4 + 1] = _MUL9[s0]  ^ _MUL14[s1] ^ _MUL11[s2] ^ _MUL13[s3]
        ns[c * 4 + 2] = _MUL13[s0] ^ _MUL9[s1]  ^ _MUL14[s2] ^ _MUL11[s3]
        ns[c * 4 + 3] = _MUL11[s0] ^ _MUL13[s1] ^ _MUL9[s2]  ^ _MUL14[s3]
    return ns


# --- AES-128 解密 T-table（等价正向密码 Equivalent Inverse Cipher 用）---
# 标准逆密码的顺序是 InvShiftRows → InvSubBytes → AddRoundKey → InvMixColumns，
# AddRoundKey 夹在中间无法合并。等价正向密码重排为
#   ShiftRows(正) → SubBytes(正) → InvMixColumns → AddRoundKey
# 前 3 步连续，可合并为单次 T-table 查表：4 次 256 项查表 + 3 次 32 位异或。
def _decrypt_block(block, w):
    """单个 16 字节块的 AES-128 逆密码（FIPS-197 标准流程）

    标准逆密码顺序为 InvShiftRows → InvSubBytes → AddRoundKey → InvMixColumns，
    AddRoundKey 夹在中间，无法把中间三步合并成单个 T-table（等价正向密码虽能合并，
    但需要另一套"等价密钥"扩展，收益仅约 18%，不值得增加复杂度）。
    实际优化点：MixColumns 用预计算乘法表 _MUL* 替代 16 次 gmul，
    AddRoundKey 用 32 位打包异或替代 16 次字节移位。
    """
    state = list(block)
    _add_round_key(state, w, 40)
    for rnd in range(9, 0, -1):
        state = _inv_shift_sub(state)
        _add_round_key(state, w, rnd * 4)
        state = _inv_mix_columns(state)
    state = _inv_shift_sub(state)
    _add_round_key(state, w, 0)
    return bytes(state)


def _aes_cbc_decrypt(data):
    """AES-128-CBC 解密 + Pkcs7 去填充，返回完整图片字节"""
    if not data or len(data) % 16 != 0 or len(data) < 16:
        return None
    try:
        if AES is not None:
            plain = AES.new(IMG_AES_KEY, AES.MODE_CBC, IMG_AES_IV).decrypt(data)
        else:
            w = _key_expansion(IMG_AES_KEY)
            parts = []
            prev = bytes(IMG_AES_IV)
            for off in range(0, len(data), 16):
                blk = data[off:off + 16]
                dec = _decrypt_block(blk, w)
                parts.append(bytes(a ^ b for a, b in zip(dec, prev)))
                prev = blk
            plain = b"".join(parts)
        pad = plain[-1]
        if 1 <= pad <= 16:
            plain = plain[:-pad]
        end_jpg = plain.rfind(b"\xff\xd9")
        if end_jpg > 0:
            return plain[:end_jpg + 2]
        end_png = plain.rfind(b"IEND\xaeB`\x82")
        if end_png > 0:
            return plain[:end_png + 8]
        return plain
    except Exception:
        return None


def _guess_img_type(url, data):
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:3] == b"GIF":
        return "image/gif"
    ext = url.lower().rsplit("?", 1)[0].rsplit(".", 1)[-1]
    return {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "webp": "image/webp", "gif": "image/gif"}.get(ext, "image/jpeg")


class _ImgHandler(BaseHTTPRequestHandler):
    """本地图片解密代理: GET /d/<base64url 编码的原图 URL>"""
    def do_GET(self):
        try:
            path = self.path
            if not path.startswith("/d/"):
                self.send_response(404)
                self.end_headers()
                return
            b64 = path[3:]
            # base64url 解码（补 padding）
            raw = base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4))
            url = raw.decode("utf-8", "ignore")
            if not url.startswith("http"):
                self.send_response(404)
                self.end_headers()
                return
            body = None
            ctype = None
            # 缓存
            if url in IMG_CACHE:
                body, ctype = IMG_CACHE[url]
            else:
                r = requests.get(url, headers={"User-Agent": UA,
                                               "Referer": BASE_URL + "/"},
                                 timeout=15)
                if r.status_code != 200 or not r.content:
                    raise ValueError("download failed")
                raw_data = r.content
                ctype = _guess_img_type(url, raw_data)
                if IMG_CDN_HOST in url:
                    dec = _aes_cbc_decrypt(raw_data)
                    if dec and len(dec) > 100:
                        body = dec
                        ctype = _guess_img_type(url, dec)
                    else:
                        body = raw_data
                else:
                    body = raw_data
                if len(IMG_CACHE) >= IMG_CACHE_MAX:
                    IMG_CACHE.clear()
                IMG_CACHE[url] = (body, ctype)
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            try:
                self.send_response(500)
                self.end_headers()
            except Exception:
                pass

    def log_message(self, *args):
        pass

# 分类列表 (tid: 显示名)  —— 已按需求移除: 网黄合集/吃瓜榜单/原创博主
CATEGORIES = [
    ("wpcz", "今日吃瓜"),
    ("rdsj", "热门大瓜"),
    ("whhl", "网红黑料"),
    ("whmx", "明星黑料"),
    ("bkdg", "必看大瓜"),
    ("thjx", "探花精选"),
    ("gcjq", "国产剧情"),
    ("cbdj", "AI成人短剧"),
    ("51djc", "51剧场"),
    ("dcbq", "擦边撩骚"),
    ("snsn", "骚男骚女"),
    ("xsxy", "学生校园"),
    ("lldd", "伦理道德"),
    ("ldcg", "领导干部"),
    ("mrds", "每日大赛"),
    ("sjb", "竞技吃瓜"),
    ("jpll", "软萌甜妹"),
    ("ysyl", "看片娱乐"),
    ("hwcg", "海外吃瓜"),
    ("cgxw", "吃瓜新闻"),
    ("qubk", "吃瓜看戏"),
    ("rrcg", "人人吃瓜"),
]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


class Spider(BaseSpider):
    Name = "51吃瓜网"

    def init(self, extend=""):
        self.host = BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        self.session.trust_env = False
        self._img_proxy = None
        self._start_img_proxy()

    def destroy(self):
        self._stop_img_proxy()
        try:
            if self.session:
                self.session.close()
        except Exception:
            pass
        self.session = None

    def getName(self):
        return self.Name

    def isVideo(self):
        return True

    # ---------- 本地图片解密代理 ----------

    def _start_img_proxy(self):
        """启动本地 HTTP 代理，用于实时解密 CDN 上的 AES 加密封面图"""
        if self._img_proxy is not None:
            return
        port = PROXY_PORT
        last = None
        for offset in range(0, 40):
            try:
                srv = ThreadingHTTPServer(("127.0.0.1", port + offset), _ImgHandler)
                srv.daemon_threads = True
                t = threading.Thread(target=srv.serve_forever, daemon=True,
                                     name="cgw51-img-proxy")
                t.start()
                self._img_proxy = srv
                self._img_port = port + offset
                return
            except Exception as e:
                last = e
                continue
        print(f"[cgw51] image proxy failed: {last}", file=sys.stderr)

    def _stop_img_proxy(self):
        try:
            if self._img_proxy is not None:
                self._img_proxy.shutdown()
                self._img_proxy.server_close()
        except Exception:
            pass
        self._img_proxy = None
        IMG_CACHE.clear()

    def _img_url(self, url):
        """把 CDN 加密图 URL 转成经本地代理解密的直链；非加密图原样返回"""
        if not url or not isinstance(url, str) or self._img_proxy is None:
            return url
        if IMG_CDN_HOST not in url:
            return url
        b64 = base64.urlsafe_b64encode(url.encode("utf-8")).decode().rstrip("=")
        return f"http://127.0.0.1:{self._img_port}/d/{b64}"

    def _fetch_img(self, url):
        """下载并解密单张图片，写入代理缓存"""
        if not url or url in IMG_CACHE:
            return
        try:
            r = requests.get(url, headers={"User-Agent": UA,
                                           "Referer": BASE_URL + "/"},
                             timeout=15)
            if r.status_code != 200 or not r.content:
                return
            raw = r.content
            ctype = _guess_img_type(url, raw)
            if IMG_CDN_HOST in url:
                dec = _aes_cbc_decrypt(raw)
                if dec and len(dec) > 100:
                    ctype = _guess_img_type(url, dec)
                    raw = dec
            if len(IMG_CACHE) >= IMG_CACHE_MAX:
                IMG_CACHE.clear()
            IMG_CACHE[url] = (raw, ctype)
        except Exception:
            pass

    def _preload_images(self, urls, workers=6, cap=30):
        """后台并发预下载+解密封面图，让 TVBox 首次请求即命中缓存"""
        todo = [u for u in urls
                if u and isinstance(u, str) and u.startswith("http")
                and IMG_CDN_HOST in u and u not in IMG_CACHE]
        if not todo:
            return

        def run():
            from concurrent.futures import ThreadPoolExecutor
            batch = todo[:cap]
            with ThreadPoolExecutor(max_workers=workers) as ex:
                list(ex.map(self._fetch_img, batch))

        t = threading.Thread(target=run, daemon=True, name="cgw51-img-preload")
        t.start()

    # ---------- 工具方法 ----------

    def _get(self, url, retries=2):
        """带重试的GET请求"""
        hosts = [self.host] + [h for h in FALLBACK_HOSTS if h != self.host]
        last_err = None
        for h in hosts:
            real_url = url.replace(self.host, h) if h != self.host else url
            for _ in range(retries):
                try:
                    r = self.session.get(real_url, timeout=15)
                    if r.status_code == 200 and len(r.text) > 1000:
                        return r.text
                    last_err = f"status {r.status_code}"
                except Exception as e:
                    last_err = str(e)
        return ""

    def _decode_unicode_url(self, raw):
        """解码 unicode 转义和反斜杠的 URL"""
        try:
            u = raw.encode().decode('unicode_escape')
        except Exception:
            u = raw
        return u.replace('\\/', '/').replace('\\u002f', '/').replace('\\u002F', '/')

    def _extract_videos_from_html(self, html):
        """从列表页 HTML 提取视频列表 (id/标题/封面)"""
        videos = []
        if not html:
            return videos
        # 每个列表项是一个 <article> 块, 内含 post-card-N 和 loadBannerDirect('cover')
        # 结构按文档顺序出现: id → loadBannerDirect(封面) → 标题
        # 用 article 块逐个解析
        articles = re.split(r'<article\b', html)
        for art in articles[1:]:
            try:
                id_m = re.search(r'id="post-card-(\d+)"', art)
                if not id_m:
                    continue
                vid = id_m.group(1)
                # 封面: loadBannerDirect('url', ...) 仅取 pic.ndhixj.cn/xiao 封面（跳过广告图）
                pic = ""
                for pic_m in re.finditer(r"loadBannerDirect\('([^']+)'", art):
                    u = pic_m.group(1)
                    if 'pic.ndhixj.cn' in u and '/xiao/' in u:
                        pic = u
                        break
                # 标题
                t_m = re.search(r'itemprop="headline"[^>]*>(.*?)</h2>', art, re.DOTALL)
                if not t_m:
                    t_m = re.search(r'class="post-card-title"[^>]*>(.*?)</h2>', art, re.DOTALL)
                title = re.sub(r'<[^>]+>', '', t_m.group(1)).strip() if t_m else vid
                # 作者/日期
                author = ""
                a_m = re.search(r'itemprop="author"[^>]*>.{0,200}?itemprop="name"[^>]*content="([^"]+)"', art, re.DOTALL)
                if not a_m:
                    a_m = re.search(r'<meta itemprop="name" content="([^"]+)"/>', art)
                if a_m:
                    author = a_m.group(1)
                d_m = re.search(r'itemprop="dateModified" content="([^"]+)"', art)
                date = d_m.group(1)[:10] if d_m else ""
                remarks = " / ".join(x for x in [author, date] if x)
                videos.append({
                    "vod_id": vid,
                    "vod_name": title,
                    "vod_pic": self._img_url(pic),
                    "vod_remarks": remarks,
                    "_raw_pic": pic,
                })
                if len(videos) >= 30:
                    break
            except Exception:
                continue
        # 后台并发预下载+解密封面图，TVBox 首次请求即命中本地缓存
        raw_pics = [v.pop("_raw_pic", "") for v in videos]
        self._preload_images(raw_pics)
        return videos

    def _extract_play_urls(self, html):
        """从详情页 HTML 提取所有 dplayer config 中的 m3u8 播放地址"""
        urls = []
        if not html:
            return urls
        configs = re.findall(r"data-config='({.*?})'", html, re.DOTALL)
        for cfg in configs:
            # video.url (h264 m3u8, 带 auth_key)
            m = re.search(r'"video"\s*:\s*\{[^}]*?"url"\s*:\s*"([^"]+)"', cfg)
            if m and m.group(1).startswith('https'):
                u = self._decode_unicode_url(m.group(1))
                if u not in urls:
                    urls.append(u)
            # video_h265.url (h265, 部分设备不支持)
            m2 = re.search(r'"video_h265"\s*:\s*\{[^}]*?"url"\s*:\s*"([^"]+)"', cfg)
            if m2 and m2.group(1).startswith('https'):
                u2 = self._decode_unicode_url(m2.group(1))
                if u2 not in urls:
                    urls.append(u2)
        return urls

    # ---------- 契约方法 ----------

    def homeContent(self, filter=False):
        classes = [{"type_id": tid, "type_name": name} for tid, name in CATEGORIES]
        result = {"class": classes, "list": []}
        try:
            html = self._get(self.host + "/")
            videos = self._extract_videos_from_html(html)
            result["list"] = videos
        except Exception as e:
            print(f"[51cg] homeContent error: {e}", file=sys.stderr)
        return result

    def homeVideoContent(self):
        try:
            html = self._get(self.host + "/")
            return {"list": self._extract_videos_from_html(html)}
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg="1", filter=False, extend=None):
        videos = []
        try:
            page = int(pg) if str(pg).isdigit() else 1
            # 分页格式: /category/{tid}/ 或 /category/{tid}/{page}/
            # 注意: /page/N/ 格式返回 403, 必须用 /N/ 格式
            if page <= 1:
                url = f"{self.host}/category/{tid}/"
            else:
                url = f"{self.host}/category/{tid}/{page}/"
            html = self._get(url)
            videos = self._extract_videos_from_html(html)
        except Exception as e:
            print(f"[51cg] categoryContent error: {e}", file=sys.stderr)
        return {
            "list": videos,
            "page": int(pg) if str(pg).isdigit() else 1,
            "pagecount": 999,
            "limit": len(videos),
            "total": 99999,
        }

    def _extract_article_body(self, html):
        """从详情页提取完整文章正文（段落 + 章节标题，过滤广告/页脚）"""
        start_idx = html.find('itemprop="articleBody"')
        if start_idx < 0:
            return ""
        end_idx = html.find('class="dplayer"', start_idx)
        if end_idx < 0:
            end_idx = start_idx + 50000
        article_html = html[start_idx:end_idx]
        # 按 <p> 和 <h2> 分段提取
        parts = re.split(r'(<p[^>]*>|</p>|<h2[^>]*>|</h2>)', article_html)
        blocks = []
        current_type = None
        current_text = []
        for i, token in enumerate(parts):
            if token == '<p':
                if current_text:
                    blocks.append(('para', ''.join(current_text)))
                    current_text = []
                current_type = 'para'
            elif token == '</p>':
                if current_text:
                    text = re.sub(r'<img[^>]*>', '', ''.join(current_text))
                    text = re.sub(r'<a[^>]*>(.*?)</a>', r'\1', text)
                    text = re.sub(r'<[^>]+>', '', text).strip()
                    if len(text) > 5 and '51吃瓜最新地址' not in text and '邮箱' not in text:
                        blocks.append(('para', text))
                    current_text = []
                current_type = None
            elif token == '<h2':
                if current_text:
                    text = ''.join(current_text)
                    text = re.sub(r'<img[^>]*>', '', text)
                    text = re.sub(r'<a[^>]*>(.*?)</a>', r'\1', text)
                    text = re.sub(r'<[^>]+>', '', text).strip()
                    if text:
                        blocks.append(('para', text))
                    current_text = []
                current_type = 'h2'
            elif token == '</h2>':
                if current_text:
                    text = re.sub(r'<[^>]+>', '', ''.join(current_text)).strip()
                    if text:
                        blocks.append(('h2', text))
                    current_text = []
                current_type = None
            else:
                current_text.append(token)
        # 收尾
        if current_text:
            text = re.sub(r'<img[^>]*>', '', ''.join(current_text))
            text = re.sub(r'<a[^>]*>(.*?)</a>', r'\1', text)
            text = re.sub(r'<[^>]+>', '', text).strip()
            if text and '51吃瓜最新地址' not in text and '邮箱' not in text:
                blocks.append(('para', text))
        # 过滤末尾残片（dplayer 等无关 HTML）
        clean_blocks = []
        for b in blocks:
            if b[0] == 'para' and b[1].startswith('<'):
                continue
            clean_blocks.append(b)
        return '\n\n'.join(
            f'## {b[1]}' if b[0] == 'h2' else b[1]
            for b in clean_blocks
        )

    def _extract_meta_description(self, html):
        """从 meta 或 JSON-LD 提取简介摘要"""
        # JSON-LD 优先
        m_json = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
        if m_json:
            try:
                data = json.loads(m_json.group(1))
                for item in data.get("@graph", []):
                    if item.get("@type") == "Article":
                        desc = item.get("description", "")
                        if desc:
                            return desc
            except Exception:
                pass
        # meta description 兜底
        d_m = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', html)
        if d_m:
            return d_m.group(1)
        return ""

    def detailContent(self, ids):
        vod = {
            "vod_id": ids[0],
            "vod_name": "",
            "vod_pic": "",
            "vod_remarks": "",
            "type_name": "",
            "vod_content": "",
            "vod_play_from": "",
            "vod_play_url": "",
        }
        try:
            vid = ids[0]
            html = self._get(f"{self.host}/archives/{vid}/")
            if not html:
                return {"list": [vod]}
            # ---------- 标题 ----------
            t_m = re.search(r'<h1[^>]*itemprop="headline"[^>]*>(.*?)</h1>', html, re.DOTALL)
            if not t_m:
                t_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
            if t_m:
                vod["vod_name"] = re.sub(r'<[^>]+>', '', t_m.group(1)).strip()
            # ---------- 封面 ----------
            pic = ""
            pic_m = re.search(r'data-xkrkllgl="([^"]+)"', html)
            if not pic_m:
                pic_m = re.search(r"loadBannerDirect\('([^']+)'", html)
            if pic_m:
                pic = pic_m.group(1)
            vod["vod_pic"] = self._img_url(pic)
            # ---------- 分类 ----------
            cats = re.findall(r'href="/category/([^"/]+)/"[^>]*>([^<]{1,12})<', html)
            if cats:
                vod["type_name"] = cats[0][1]
            # ---------- 结构化元信息 ----------
            author = ""
            date_published = ""
            date_modified = ""
            keywords = ""
            m_json = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
            if m_json:
                try:
                    data = json.loads(m_json.group(1))
                    for item in data.get("@graph", []):
                        if item.get("@type") == "Article":
                            author = item.get("author", {}).get("name", "")
                            date_published = item.get("datePublished", "")
                            date_modified = item.get("dateModified", "")
                            keywords = item.get("keywords", "")
                            break
                except Exception:
                    pass
            if not author:
                a_m = re.search(r'<meta[^>]+itemprop="author"[^>]+content="([^"]+)"', html)
                if not a_m:
                    a_m = re.search(r'<meta[^>]+name="author"[^>]+content="([^"]+)"', html)
                if a_m:
                    author = a_m.group(1)
            if not date_published:
                dp_m = re.search(r'itemprop="datePublished"[^>]+content="([^"]+)"', html)
                if not dp_m:
                    dp_m = re.search(r'<meta[^>]+property="article:published_time"[^>]+content="([^"]+)"', html)
                if dp_m:
                    date_published = dp_m.group(1)
            if not date_modified:
                dm_m = re.search(r'itemprop="dateModified"[^>]+content="([^"]+)"', html)
                if dm_m:
                    date_modified = dm_m.group(1)
            if not keywords:
                kw_m = re.search(r'<meta[^>]+name="keywords"[^>]+content="([^"]*)"', html)
                if kw_m:
                    keywords = kw_m.group(1)
            # ---------- 完整正文 ----------
            full_body = self._extract_article_body(html)
            meta_desc = self._extract_meta_description(html)
            # 组装简介: 元信息 + 完整正文
            parts = []
            meta_parts = []
            if author:
                meta_parts.append(f"作者：{author}")
            if date_published:
                meta_parts.append(f"发布：{date_published[:10]}")
            if date_modified and date_modified[:10] != date_published[:10]:
                meta_parts.append(f"更新：{date_modified[:10]}")
            if cats:
                cat_names = "、".join(c[1] for c in cats[:5])
                meta_parts.append(f"分类：{cat_names}")
            if keywords:
                meta_parts.append(f"标签：{keywords}")
            # 列表页备注
            vod["vod_remarks"] = " | ".join(meta_parts)
            # 详情页完整内容
            if meta_parts:
                parts.append("📋 " + "  |  ".join(meta_parts))
            if full_body:
                parts.append(f"\n{full_body}")
            elif meta_desc:
                parts.append(f"\n{meta_desc}")
            vod["vod_content"] = "\n".join(parts)
            # ---------- 播放地址 ----------
            urls = self._extract_play_urls(html)
            play_parts = []
            flags = []
            h264 = [u for u in urls if '/videos5/' in u]
            h265 = [u for u in urls if '/m3m/' in u]
            if h264:
                flags.append("原画")
                play_parts.append("完整观看$" + h264[0])
            if h265:
                flags.append("H265")
                play_parts.append("完整观看$" + h265[0])
            if not play_parts and urls:
                flags.append("原画")
                play_parts.append("完整观看$" + urls[0])
            if play_parts:
                vod["vod_play_from"] = "$$$".join(flags)
                vod["vod_play_url"] = "$$$".join(play_parts)
            else:
                vod["vod_play_from"] = "原画"
                vod["vod_play_url"] = "完整观看$" + f"{self.host}/archives/{vid}/"
        except Exception as e:
            print(f"[51cg] detailContent error: {e}", file=sys.stderr)
        return {"list": [vod]}

    def searchContent(self, key, quick=False, pg="1"):
        videos = []
        try:
            page = int(pg) if str(pg).isdigit() else 1
            kw = quote(key)
            if page <= 1:
                url = f"{self.host}/search/{kw}/"
            else:
                url = f"{self.host}/search/{kw}/{page}/"
            html = self._get(url)
            videos = self._extract_videos_from_html(html)
        except Exception as e:
            print(f"[51cg] searchContent error: {e}", file=sys.stderr)
        return {"list": videos, "page": page, "pagecount": 999, "limit": len(videos), "total": 99999}

    def playerContent(self, flag, id, vipFlags=None):
        # id 即完整 m3u8 URL (detailContent 已解析)
        return {
            "parse": 0,
            "url": id,
            "header": {"User-Agent": UA},
        }

    def localProxy(self, params):
        return []
