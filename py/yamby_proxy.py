# coding=utf-8
#!/usr/bin/python
# Emby 直连源（catvod py 源 / OK影视 · 影视仓 · TVBox 通用）
# v2 strm 增强版
#   1) token 一律走请求头：部分服务器的 nginx 会拦 URL 里的 token（回 member identity required），
#      老版本把 token 拼在 query 里，详情/剧集接口直接被 403 打回，详情页全空。
#   2) strm / 远程源（IsRemote / Container=strm / Protocol=http）走专用播放通路：
#      自动跟随 Emby 的 302 拿到真实直链，m3u8 单独识别，多路回退，不再只拼死一个 stream 地址。
#   3) Fields=MediaSources 被服务器拒绝时自动降级，不会因为一个字段把整个详情页搞空。
#   4) 播放不创建会话、不上报播放状态（silentPlay 默认开）
import sys
import json
import time
import hashlib
from uuid import uuid4
import requests
from urllib.parse import quote, urljoin

sys.path.append('..')
from base.spider import Spider as BaseSpider
from requests.packages.urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# 模块级缓存：同一进程内复用 token，避免每次调用都重新登录
_CACHE = {}
_TOKEN_TTL = 6 * 3600

_VIDEO_EXT = ('mp4', 'mkv', 'avi', 'ts', 'm2ts', 'mov', 'flv', 'wmv', 'webm',
              'rmvb', 'rm', 'mpg', 'mpeg', 'm4v', '3gp', 'iso', 'ass', 'srt')


class Spider(BaseSpider):
    header = {"User-Agent": "Yamby/1.0.2(Android)"}

    def getName(self):
        return "EMBY_Pro"

    # ---------------- 初始化 ----------------
    def init(self, extend):
        cfg = {}
        try:
            if extend:
                cfg = json.loads(extend) if isinstance(extend, str) else (extend or {})
        except Exception:
            cfg = {}

        self.baseUrl = str(cfg.get('server', '')).strip().rstrip('/')
        self.username = str(cfg.get('username', '')).strip()
        self.password = str(cfg.get('password', ''))
        # 只拿到 api_key / token、没有明文密码时，直接填这里，跳过登录
        self.apiKey = str(cfg.get('apiKey', '') or cfg.get('token', '')).strip()
        self.userId = str(cfg.get('userId', '') or '').strip()
        self.proxy_str = str(cfg.get('proxy', '')).strip()
        self.thread = int(cfg.get('thread', 0) or 0)
        self.timeout = int(cfg.get('timeout', 15) or 15)
        self.pageSize = int(cfg.get('pageSize', 30) or 30)

        # 设备伪装：默认和 Yamby 一致，服务端设备列表里看到的就是这个名字
        self.clientName = str(cfg.get('deviceName', '') or 'Yamby')
        self.clientVersion = str(cfg.get('clientVersion', '') or '1.0.2')

        # silentPlay: true = 播放时直接拼直链，完全不发 PlaybackInfo（服务端不会出现播放会话）
        self.silentPlay = bool(cfg.get('silentPlay', True))
        # probe: silentPlay 时先试拉一点，直链不通再回退 PlaybackInfo
        self.probe = bool(cfg.get('probe', True))
        # imageKey: 封面地址带上 api_key，服务器禁止匿名取图时也能显示
        self.imageKey = bool(cfg.get('imageKey', True))

        # ---- strm / 远程源 ----
        # strmMode: auto = 自动（能直出就给 Emby 地址，要跳转就取到真实直链）
        #           emby = 只给 Emby 的 stream 地址（让播放器自己跟 302）
        #           direct = 优先给 strm 文件里写的那个远程地址
        self.strmMode = str(cfg.get('strmMode', 'auto') or 'auto').strip().lower()
        if self.strmMode not in ('auto', 'emby', 'direct'):
            self.strmMode = 'auto'
        # strmResolve: auto 模式下，Emby 地址不通时是否继续解析 strm 里的远程地址
        self.strmResolve = bool(cfg.get('strmResolve', True))
        # strmProbe: 对 strm 做可用性探测（关闭可省 1-3 秒，但失败时不会自动回退）
        self.strmProbe = bool(cfg.get('strmProbe', True))

        # includeTypes: 列表里要哪些类型
        self.includeTypes = str(cfg.get('includeTypes', 'Movie,Series') or 'Movie,Series')

        # threadBase: thread>0 时的多线程中转前缀
        self.threadBase = str(cfg.get('threadBase', 'http://127.0.0.1:7777/') or '')
        if self.threadBase and not self.threadBase.endswith('/'):
            self.threadBase += '/'

        self.session = requests.Session()
        self.session.headers.update(self.header)
        self.session.verify = False

        if self.username:
            self.deviceId = hashlib.md5(self.username.encode('utf-8')).hexdigest()
        elif self.apiKey:
            self.deviceId = hashlib.md5(self.apiKey.encode('utf-8')).hexdigest()
        else:
            self.deviceId = str(uuid4())

        # 让服务端把这条连接识别成一个正常设备，而不是默认的 requests
        self.session.headers['X-Emby-Authorization'] = self._auth_header()

        if self.proxy_str:
            try:
                p = self.proxy_str
                if p.startswith('socks5'):
                    proxy_url = p if '://' in p else 'socks5h://' + p
                elif p.startswith('http'):
                    proxy_url = p
                else:
                    proxy_url = 'http://' + p
                self.session.proxies = {"http": proxy_url, "https": proxy_url}
            except Exception:
                pass

        self._cache_ok = None       # 9978 缓存接口是否可用（懒探测）
        self.srcMap = {}            # item_id -> {source_id: 源信息}，播放阶段要用
        self._detailMap = {}        # item_id -> 详情 JSON（避免详情/播放重复请求）

    # ---------------- 统一请求 ----------------
    def _full(self, path):
        if path.startswith('http://') or path.startswith('https://'):
            return path
        if not path.startswith('/'):
            path = '/' + path
        return self.baseUrl + path

    def _rq(self, method, path, token=None, params=None, headers=None, body=None,
            timeout=None, allow_redirects=True, stream=False):
        """统一请求入口：token 只放 X-Emby-Token 头，绝不拼进 URL。

        有些 Emby 前面挂了 nginx 做会员校验，URL 里带 token 会直接回
        403 {"error":"member identity required"}，导致详情页整片空白。
        """
        url = self._full(path)
        h = dict(self.header)
        if token:
            h['X-Emby-Token'] = token
        if headers:
            h.update(headers)

        p = {}
        for k, v in (params or {}).items():
            lk = str(k).lower()
            if lk in ('x-emby-token', 'api_key', 'apikey'):
                continue
            if v is None:
                continue
            p[k] = v

        kw = {'params': p, 'headers': h, 'timeout': timeout or self.timeout,
              'allow_redirects': allow_redirects, 'stream': stream}
        if body is not None:
            kw['json'] = body
        try:
            return self.session.request(method, url, **kw)
        except Exception:
            return None

    # ---------------- token ----------------
    def _tkey(self):
        raw = '%s|%s|%s' % (self.baseUrl, self.username, self.password)
        return 'emby_token_' + hashlib.md5(raw.encode('utf-8')).hexdigest()

    def _auth_header(self):
        return 'MediaBrowser Client="%s", Device="%s", DeviceId="%s", Version="%s"' % (
            self.clientName, self.clientName, self.deviceId, self.clientVersion)

    def getAccessToken(self, force=False):
        if self.apiKey:
            return self._key_info()
        if not self.baseUrl or not self.username:
            return None

        key = self._tkey()

        if not force:
            c = _CACHE.get(key)
            if c and c.get('v') and c.get('t', 0) > time.time() - _TOKEN_TTL:
                return c['v']
            cached = self.getCache(key)
            if isinstance(cached, dict) and cached.get('AccessToken'):
                _CACHE[key] = {'v': cached, 't': time.time()}
                return cached

        info = self._login()
        if info:
            _CACHE[key] = {'v': info, 't': time.time()}
            self.setCache(key, info)
        return info

    def _key_info(self):
        """用现成 api_key 工作，只需补一个用户 Id"""
        if not self.userId:
            for path, pick in (('/emby/Users/Me', None), ('/emby/Sessions', 'sess')):
                r = self._rq('GET', path, token=self.apiKey)
                if not r or r.status_code != 200:
                    continue
                try:
                    d = r.json()
                except Exception:
                    continue
                if pick is None:
                    self.userId = (d or {}).get('Id', '')
                else:
                    arr = d or []
                    one = next((x for x in arr if x.get('UserId') and x.get('DeviceId') == self.deviceId), None)
                    if not one:
                        one = next((x for x in arr if x.get('UserId')), None)
                    if one:
                        self.userId = one['UserId']
                if self.userId:
                    break
        return {'AccessToken': self.apiKey,
                'User': {'Id': self.userId, 'Name': 'apiKey'}}

    def _login(self):
        url = '/emby/Users/AuthenticateByName'
        params = {
            'X-Emby-Client': self.clientName,
            'X-Emby-Device-Name': self.clientName,
            'X-Emby-Device-Id': self.deviceId,
            'X-Emby-Client-Version': self.clientVersion,
        }
        headers = {
            'Content-Type': 'application/json; charset=UTF-8',
            'X-Emby-Authorization': self._auth_header(),
        }
        body = {'Username': self.username, 'Pw': self.password,
                'Password': self.password}

        # 两套写法兜底：body（标准）/ query（老版本服务端）
        attempts = [
            {'params': params, 'json': body},
            {'params': dict(params, Username=self.username, Pw=self.password), 'json': None},
        ]
        for a in attempts:
            kw = dict(params=a['params'], headers=headers, timeout=self.timeout)
            if a['json'] is not None:
                kw['json'] = a['json']
            try:
                r = self.session.post(self._full(url), **kw)
                if r.status_code == 200:
                    d = r.json()
                    if d.get('AccessToken'):
                        return d
            except Exception:
                continue
        return None

    # ---------------- 首页 / 分类 ----------------
    def homeContent(self, filter):
        empty = {'class': [], 'list': [], 'filters': {}}
        try:
            info = self.getAccessToken()
            if not info:
                return empty
            uid = info['User']['Id']
            r = self._rq('GET', '/emby/Users/%s/Views' % uid, token=info['AccessToken'])
            if not r or r.status_code != 200:
                return empty
            cats = []
            for it in r.json().get('Items', []):
                name = it.get('Name', '')
                if not name or any(x in name for x in ['收藏', '专题', '继续']):
                    continue
                cats.append({'type_name': name, 'type_id': it.get('Id', '')})
            return {'class': cats, 'list': [], 'filters': {}}
        except Exception:
            return empty

    def categoryContent(self, cid, page, filter, ext):
        try:
            info = self.getAccessToken()
            if not info:
                return {'page': 1, 'pagecount': 0, 'limit': 0, 'total': 0, 'list': []}
            uid = info['User']['Id']
            token = info['AccessToken']
            page = int(page or 1)
            limit = self.pageSize

            r = self._rq('GET', '/emby/Users/%s/Items' % uid, token=token, params={
                'SortBy': 'DateLastContentAdded,SortName',
                'IncludeItemTypes': self.includeTypes,
                'SortOrder': 'Descending',
                'ParentId': cid,
                'Recursive': 'true',
                'Limit': str(limit),
                'StartIndex': str((page - 1) * limit),
                'Fields': 'PrimaryImageAspectRatio,ProductionYear',
                'EnableUserData': 'false',
            })
            if not r or r.status_code != 200:
                return {'page': page, 'pagecount': page, 'limit': limit, 'total': 0, 'list': []}

            d = r.json()
            videos = []
            for it in d.get('Items', []):
                vid = it.get('Id', '')
                videos.append({
                    'vod_id': vid,
                    'vod_name': it.get('Name', ''),
                    'vod_pic': self._img(vid, it, token, 400),
                    'vod_remarks': str(it.get('ProductionYear', '') or ''),
                })
            total = int(d.get('TotalRecordCount', 0) or 0)
            pagecount = (total // limit) + (1 if total % limit else 0)
            return {'page': page, 'pagecount': max(pagecount, 0) or 1,
                    'limit': limit, 'total': total, 'list': videos}
        except Exception:
            return {'page': 1, 'pagecount': 0, 'list': []}

    # ---------------- 详情 ----------------
    def _item_detail(self, item_id, uid, token):
        """取单个条目，带 Fields 降级 + 接口形态兜底"""
        cached = self._detailMap.get(item_id)
        if cached:
            return cached

        paths = []
        if uid:
            paths.append('/emby/Users/%s/Items/%s' % (uid, item_id))
        paths.append('/emby/Items/%s' % item_id)

        field_sets = [
            {'Fields': 'MediaSources,Overview,Genres,ProductionYear'},
            {'Fields': 'Overview,Genres,ProductionYear'},
            {},
        ]

        for path in paths:
            for fp in field_sets:
                r = self._rq('GET', path, token=token, params=dict(fp, UserId=uid) if uid else fp)
                if r is None or r.status_code != 200:
                    continue
                try:
                    j = r.json()
                except Exception:
                    continue
                if isinstance(j, dict) and j.get('Id'):
                    self._detailMap[item_id] = j
                    return j
        return None

    def _pb_sources(self, item_id, uid, token):
        """兜底：从 PlaybackInfo 拿 MediaSources"""
        r = self._rq('POST', '/emby/Items/%s/PlaybackInfo' % item_id, token=token,
                     params={'UserId': uid} if uid else {}, body={})
        if r is not None and r.status_code == 200:
            try:
                return r.json().get('MediaSources') or []
            except Exception:
                return []
        return []

    @staticmethod
    def _is_remote(src):
        """判断一个 MediaSource 是不是 strm / 远程源"""
        if not isinstance(src, dict):
            return False
        c = str(src.get('Container') or '').strip().lower()
        if c == 'strm':
            return True
        if src.get('IsRemote') is True:
            return True
        if str(src.get('Protocol') or '').strip().lower() in ('http', 'https'):
            return True
        p = str(src.get('Path') or '')
        if p.startswith('http://') or p.startswith('https://'):
            return True
        return False

    @staticmethod
    def _is_m3u8(u):
        if not u:
            return False
        low = str(u).lower()
        return '.m3u8' in low or 'mpegurl' in low

    @staticmethod
    def _looks_video(u):
        if not u:
            return False
        low = str(u).split('?')[0].lower()
        for ext in _VIDEO_EXT:
            if low.endswith('.' + ext):
                return True
        return False

    def _remember(self, item_id, src):
        if not isinstance(src, dict):
            return
        sid = str(src.get('Id') or '')
        m = self.srcMap.setdefault(item_id, {})
        m[sid] = {
            'Id': sid,
            'Path': str(src.get('Path') or ''),
            'Container': str(src.get('Container') or ''),
            'Protocol': str(src.get('Protocol') or ''),
            'IsRemote': src.get('IsRemote'),
            'Name': str(src.get('Name') or ''),
        }

    def _lookup_source(self, item_id, source_id, uid, token):
        m = self.srcMap.get(item_id) or {}
        if source_id and source_id in m:
            return m[source_id]

        # 详情页没缓存到（比如壳换了进程）：现拉一次
        it = self._item_detail(item_id, uid, token)
        if it:
            for s in (it.get('MediaSources') or []):
                self._remember(item_id, s)
            m = self.srcMap.get(item_id) or {}
            if source_id and source_id in m:
                return m[source_id]

        if not m:
            for s in self._pb_sources(item_id, uid, token):
                self._remember(item_id, s)
            m = self.srcMap.get(item_id) or {}

        if source_id and source_id in m:
            return m[source_id]
        if '' in m:
            return m['']
        if m:
            return list(m.values())[0]
        return {}

    def detailContent(self, did_list):
        try:
            if isinstance(did_list, str):
                did = did_list
            else:
                did = did_list[0] if did_list else ''
            info = self.getAccessToken()
            if not did or not info:
                return {'list': []}

            uid = info['User']['Id']
            token = info['AccessToken']

            it = self._item_detail(did, uid, token)
            if not it:
                return {'list': []}

            vod = {
                'vod_id': did,
                'vod_name': it.get('Name', ''),
                'vod_pic': self._img(did, it, token, 400),
                'type_name': ((it.get('Genres') or ['未知']) or ['未知'])[0],
                'vod_year': str(it.get('ProductionYear', '') or ''),
                'vod_content': (it.get('Overview') or '').strip(),
            }

            play_from, play_url = [], []

            if not it.get('IsFolder', False):
                # 电影 / 单集：只看 MediaSources，不额外调 PlaybackInfo
                sources = it.get('MediaSources') or []
                if not sources:
                    sources = self._pb_sources(did, uid, token)
                if not sources:
                    sources = [{}]

                for idx, s in enumerate(sources):
                    label = s.get('Name') or ('源%d' % (idx + 1))
                    if self._is_remote(s):
                        label = label + '[strm]'
                    label = label.replace('#', '-').replace('$', '|')
                    sid = str(s.get('Id') or '')
                    self._remember(did, s)
                    play_from.append('EMBY-%s' % label)
                    play_url.append('播放$%s' % (did + ('_' + sid if sid else '')))
            else:
                # 剧集 / 季
                play_from.append('EMBY-剧集')
                eps = []
                rs = self._rq('GET', '/emby/Shows/%s/Seasons' % did, token=token,
                              params={'UserId': uid})
                seasons = []
                if rs is not None and rs.status_code == 200:
                    try:
                        seasons = rs.json().get('Items', [])
                    except Exception:
                        seasons = []

                for season in seasons:
                    sid_s = season.get('Id')
                    if not sid_s:
                        continue
                    eps_items = []
                    for extra in ({'Fields': 'MediaSources'}, {}):
                        rq = self._rq('GET', '/emby/Shows/%s/Episodes' % did, token=token,
                                      params=dict(extra, SeasonId=sid_s, UserId=uid))
                        if rq is not None and rq.status_code == 200:
                            try:
                                eps_items = rq.json().get('Items', []) or []
                            except Exception:
                                eps_items = []
                            if eps_items:
                                break
                    for ep in eps_items:
                        s_name = (season.get('Name') or '').strip()
                        e_name = (ep.get('Name') or '').strip()
                        label = ('%s %s' % (s_name, e_name)).strip()
                        label = label.replace('#', '-').replace('$', '|')
                        srcs = ep.get('MediaSources') or []
                        source_id = str(srcs[0].get('Id') or '') if srcs else ''
                        if srcs:
                            self._remember(ep.get('Id', ''), srcs[0])
                        eid = ep.get('Id', '')
                        if not eid:
                            continue
                        eps.append('%s$%s' % (label, eid + ('_' + source_id if source_id else '')))
                if eps:
                    play_url.append('#'.join(eps))
                else:
                    play_url.append('')

            vod['vod_play_from'] = '$$$'.join(play_from)
            vod['vod_play_url'] = '$$$'.join(play_url)
            return {'list': [vod]}
        except Exception:
            return {'list': []}

    # ---------------- 播放 ----------------
    def playerContent(self, flag, pid, vipFlags):
        try:
            pid = str(pid)
            item_id = pid.split('_', 1)[0]
            source_id = pid.split('_', 1)[1] if '_' in pid else ''

            info = self.getAccessToken()
            if not info:
                return {'url': '', 'msg': '登录失败，请检查账号密码'}

            token = info['AccessToken']
            uid = info['User']['Id']

            src = self._lookup_source(item_id, source_id, uid, token)
            url = self._build_play_url(item_id, source_id, uid, token, src)

            if not url:
                return {'url': '', 'msg': '无可用播放地址'}

            if self.thread > 0 and self.threadBase:
                url = '%s?url=%s&thread=%d' % (self.threadBase.rstrip('/'),
                                               quote(url, safe=''), self.thread)

            return {'url': url, 'header': dict(self.header), 'parse': 0}
        except Exception as e:
            return {'url': '', 'msg': '播放解析异常: %s' % str(e)}

    def _build_play_url(self, item_id, source_id, uid, token, src):
        """普通文件走老路；strm / 远程源走专用通路"""
        emby_url = self._stream_url(item_id, source_id, token)
        src = src or {}
        remote = str(src.get('Path') or '').strip()
        is_remote = self._is_remote(src)

        # ---------- 普通本地文件 ----------
        if not is_remote:
            if self.silentPlay:
                if not self.probe or self._probe(emby_url, token):
                    return emby_url
                return self._pb_play_url(item_id, source_id, uid, token) or emby_url
            return self._pb_play_url(item_id, source_id, uid, token) or emby_url

        # ---------- strm / 远程源 ----------
        mode = self.strmMode

        if mode == 'direct':
            if remote.startswith('http'):
                return remote
            return self._pb_play_url(item_id, source_id, uid, token) or emby_url

        if mode == 'emby':
            return emby_url

        # auto：先看 Emby 这条地址是直接出流还是要跳转
        if self.strmProbe:
            target, kind = self._resolve_play(emby_url, token)
            if kind == 'stream':
                # 直接 200/206 出流，交给 Emby 自己服务
                return emby_url
            if kind == 'redirect':
                if self._is_m3u8(target):
                    # 切片地址：给到 m3u8，播放器按它自己解析分片
                    return target
                return target
        else:
            # 不探测就直接给 Emby 地址（大多数播放器能跟 302）
            return emby_url

        # Emby 这条不通：退到 strm 文件里写的远程地址
        if remote.startswith('http') and self.strmResolve:
            t2, k2 = self._resolve_play(remote, None)
            if k2 == 'redirect' and t2:
                return t2
            if k2 == 'stream':
                return remote
            return remote

        # 再退 PlaybackInfo
        pb = self._pb_play_url(item_id, source_id, uid, token)
        return pb or emby_url

    def _stream_url(self, item_id, source_id, token):
        q = 'static=true&api_key=%s' % token
        if source_id:
            q = 'static=true&mediaSourceId=%s&api_key=%s' % (source_id, token)
        return '%s/emby/Videos/%s/stream?%s' % (self.baseUrl, item_id, q)

    def _resolve_play(self, url, token=None):
        """探一下这个地址的播放形态。

        返回 (目标地址, 类型)：
          ('xxx', 'redirect')  -> 3xx，xxx 是跳转目标（通常是网盘 CDN 直链）
          (url,   'stream')    -> 能直接出流
          ('',    '')          -> 不通

        两轮：先用 Range 小请求探，失败再用普通请求（有些网盘/CDN 对 Range 处理古怪）。
        """
        base_headers = dict(self.header)
        if token:
            base_headers['X-Emby-Token'] = token

        for attempt in range(2):
            headers = dict(base_headers)
            if attempt == 0:
                headers['Range'] = 'bytes=0-1'
            try:
                r = self.session.get(url, headers=headers, allow_redirects=False,
                                     stream=True, timeout=max(20, self.timeout))
                code = r.status_code
                loc = r.headers.get('Location') or ''
                ctype = str(r.headers.get('Content-Type') or '').lower()
                try:
                    r.close()
                except Exception:
                    pass

                if code in (301, 302, 303, 307, 308) and loc:
                    if not loc.startswith('http'):
                        loc = urljoin(url, loc)
                    # 跳回 Emby 自己（转码/鉴权页），不算真实直链
                    if '/emby/' in loc and url.split('/emby/')[0] in loc:
                        return '', ''
                    return loc, 'redirect'

                if code in (200, 206):
                    if 'text/html' in ctype or 'application/json' in ctype:
                        return '', ''
                    return url, 'stream'

                if code in (400, 416) and attempt == 0:
                    continue          # Range 不被接受，换普通请求再来一次
                if code >= 500 and attempt == 0:
                    continue          # 服务端偶发 5xx，重试一次
            except Exception:
                if attempt == 0:
                    continue
                return '', ''

        # 最后一手：跟着跳转走到底，看最终落到哪
        try:
            headers = dict(base_headers)
            r = self.session.get(url, headers=headers, allow_redirects=True,
                                 stream=True, timeout=max(20, self.timeout))
            final = r.url or url
            code = r.status_code
            try:
                r.close()
            except Exception:
                pass
            if final and final != url:
                return final, 'redirect'
            if code in (200, 206):
                return url, 'stream'
        except Exception:
            pass
        return '', ''

    def _probe(self, url, token=None):
        try:
            headers = dict(self.header, Range='bytes=0-0')
            if token:
                headers['X-Emby-Token'] = token
            r = self.session.get(url, headers=headers, stream=True,
                                 timeout=max(20, self.timeout), allow_redirects=True)
            code = r.status_code
            try:
                r.close()
            except Exception:
                pass
            return code in (200, 206, 302)
        except Exception:
            return False

    def _pb_play_url(self, item_id, source_id, uid, token):
        try:
            sources = self._pb_sources(item_id, uid, token)
            if not sources:
                return ''
            media = None
            if source_id:
                media = next((s for s in sources if str(s.get('Id') or '') == source_id), None)
            media = media or sources[0]

            u = str(media.get('DirectStreamUrl') or '')
            if not u:
                path = str(media.get('Path') or '')
                if self._is_remote(media) and path.startswith('http'):
                    # strm 里写的远程地址本身就带鉴权，别再拼 token
                    return path
                u = self._stream_url(item_id, str(media.get('Id') or ''), token)
            elif u.startswith('/'):
                u = self.baseUrl + u

            if 'api_key=' not in u and 'X-Emby-Token=' not in u:
                u += ('&' if '?' in u else '?') + 'api_key=' + token
            return u
        except Exception:
            return ''

    # ---------------- 搜索 ----------------
    def searchContent(self, keywords, quick, page):
        try:
            info = self.getAccessToken()
            if not info:
                return {'list': []}
            token = info['AccessToken']
            uid = info['User']['Id']
            r = self._rq('GET', '/emby/Users/%s/Items' % uid, token=token, params={
                'SearchTerm': keywords,
                'IncludeItemTypes': self.includeTypes,
                'Recursive': 'true',
                'Limit': '50',
                'Fields': 'ProductionYear',
            })
            if not r or r.status_code != 200:
                return {'list': []}
            vids = []
            for it in r.json().get('Items', []):
                vid = it.get('Id', '')
                vids.append({'vod_id': vid, 'vod_name': it.get('Name', ''),
                             'vod_pic': self._img(vid, it, token, 400),
                             'vod_remarks': str(it.get('ProductionYear', '') or '')})
            return {'list': vids}
        except Exception:
            return {'list': []}

    # ---------------- 工具 ----------------
    def _img(self, item_id, item, token, width):
        tag = (item.get('ImageTags') or {}).get('Primary', '')
        if not tag:
            return ''
        u = '%s/emby/Items/%s/Images/Primary?maxWidth=%d&tag=%s' % (self.baseUrl, item_id, width, tag)
        if self.imageKey and token:
            u += '&api_key=' + token
        return u

    # --- 9978 缓存（壳提供才用，不可用就只走内存） ---
    def _cache_usable(self):
        if self._cache_ok is not None:
            return self._cache_ok
        try:
            r = self.session.get('http://127.0.0.1:9978/cache?do=get&key=__probe__', timeout=3)
            self._cache_ok = r.status_code < 500
        except Exception:
            self._cache_ok = False
        return self._cache_ok

    def getCache(self, key):
        if not self._cache_usable():
            return None
        try:
            res = self.session.get('http://127.0.0.1:9978/cache?do=get&key=' + key, timeout=5).text
            return json.loads(res) if res else None
        except Exception:
            return None

    def setCache(self, key, value):
        if not self._cache_usable():
            return
        try:
            self.session.post('http://127.0.0.1:9978/cache?do=set&key=' + key,
                              data={'value': json.dumps(value)}, timeout=5)
        except Exception:
            pass

    def delCache(self, key):
        _CACHE.pop(key, None)
        if not self._cache_usable():
            return
        try:
            self.session.get('http://127.0.0.1:9978/cache?do=del&key=' + key, timeout=5)
        except Exception:
            pass
