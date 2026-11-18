# coding=utf-8
#!/usr/bin/python
# Emby 直连源（catvod py 源 / OK影视 · 影视仓 · TVBox 通用）
# 优化版：token 只登一次、播放不创建会话、不向服务器上报任何播放状态
import sys
import json
import time
import hashlib
from uuid import uuid4
import requests
from urllib.parse import quote

sys.path.append('..')
from base.spider import Spider as BaseSpider
from requests.packages.urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# 模块级缓存：同一进程内复用 token，避免每次调用都重新登录
_CACHE = {}
_TOKEN_TTL = 6 * 3600


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
        # probe: silentPlay 时先试拉 1 字节，直链不通再回退 PlaybackInfo
        self.probe = bool(cfg.get('probe', True))
        # imageKey: 封面地址带上 api_key，服务器禁止匿名取图时也能显示
        self.imageKey = bool(cfg.get('imageKey', True))

        # threadBase: thread>0 时的多线程中转前缀
        self.threadBase = str(cfg.get('threadBase', 'http://127.0.0.1:7777/') or '')
        if self.threadBase and not self.threadBase.endswith('/'):
            self.threadBase += '/'

        self.session = requests.Session()
        self.session.headers.update(self.header)
        self.session.verify = False

        if self.username:
            self.deviceId = hashlib.md5(self.username.encode('utf-8')).hexdigest()
        else:
            self.deviceId = hashlib.md5(self.apiKey.encode('utf-8')).hexdigest() if self.apiKey else str(uuid4())

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

        self._cache_ok = None  # 9978 缓存接口是否可用（懒探测）

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
            # 1) 标准接口
            try:
                r = self.session.get(self.baseUrl + '/emby/Users/Me',
                                     params={'api_key': self.apiKey}, timeout=self.timeout)
                if r.status_code == 200:
                    self.userId = r.json().get('Id', '')
            except Exception:
                pass
        if not self.userId:
            # 2) 部分分支版本不支持 /Users/Me，从会话列表取
            try:
                r = self.session.get(self.baseUrl + '/emby/Sessions',
                                     params={'api_key': self.apiKey}, timeout=self.timeout)
                if r.status_code == 200:
                    arr = r.json() or []
                    pick = next((x for x in arr if x.get('UserId') and x.get('DeviceId') == self.deviceId), None)
                    if not pick:
                        pick = next((x for x in arr if x.get('UserId')), None)
                    if pick:
                        self.userId = pick['UserId']
            except Exception:
                pass
        return {'AccessToken': self.apiKey,
                'User': {'Id': self.userId, 'Name': 'apiKey'}}

    def _login(self):
        url = self.baseUrl + '/emby/Users/AuthenticateByName'
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
            try:
                r = self.session.post(url, params=a['params'], json=a['json'],
                                      headers=headers, timeout=self.timeout)
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
            r = self.session.get('%s/emby/Users/%s/Views' % (self.baseUrl, uid),
                                 params={'X-Emby-Token': info['AccessToken']},
                                 timeout=self.timeout)
            if r.status_code != 200:
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

            r = self.session.get('%s/emby/Users/%s/Items' % (self.baseUrl, uid), params={
                'X-Emby-Token': token,
                'SortBy': 'DateLastContentAdded,SortName',
                'IncludeItemTypes': 'Movie,Series',
                'SortOrder': 'Descending',
                'ParentId': cid,
                'Recursive': 'true',
                'Limit': str(limit),
                'StartIndex': str((page - 1) * limit),
                'Fields': 'PrimaryImageAspectRatio,ProductionYear',
                'EnableUserData': 'false',
            }, timeout=self.timeout)
            if r.status_code != 200:
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

            # 用 GET + Fields=MediaSources 拿源，不调用 PlaybackInfo（不创建播放会话）
            r = self.session.get('%s/emby/Users/%s/Items/%s' % (self.baseUrl, uid, did),
                                 params={'X-Emby-Token': token,
                                         'Fields': 'MediaSources,Overview,Genres,ProductionYear'},
                                 timeout=self.timeout)
            if r.status_code != 200:
                return {'list': []}
            it = r.json()

            vod = {
                'vod_id': did,
                'vod_name': it.get('Name', ''),
                'vod_pic': self._img(did, it, token, 400),
                'type_name': (it.get('Genres') or ['未知'])[0],
                'vod_year': str(it.get('ProductionYear', '') or ''),
                'vod_content': (it.get('Overview') or '').strip(),
            }

            play_from, play_url = [], []

            if not it.get('IsFolder', False):
                # 只用详情接口带回来的源，不额外调 PlaybackInfo
                sources = it.get('MediaSources') or []
                if not sources:
                    sources = [{}]
                for idx, s in enumerate(sources):
                    play_from.append('EMBY-%s' % (s.get('Name') or '源%d' % (idx + 1)))
                    sid = s.get('Id', '')
                    play_url.append('播放$%s' % (did + ('_' + sid if sid else '')))
            else:
                play_from.append('EMBY-剧集')
                eps = []
                rs = self.session.get('%s/emby/Shows/%s/Seasons' % (self.baseUrl, did),
                                      params={'UserId': uid, 'X-Emby-Token': token},
                                      timeout=self.timeout)
                if rs.status_code == 200:
                    for season in rs.json().get('Items', []):
                        sid_s = season.get('Id')
                        re_ = self.session.get('%s/emby/Shows/%s/Episodes' % (self.baseUrl, sid_s), params={
                            'SeasonId': sid_s, 'UserId': uid, 'X-Emby-Token': token,
                            'Fields': 'MediaSources',
                        }, timeout=self.timeout)
                        if re_.status_code != 200:
                            continue
                        for ep in re_.json().get('Items', []):
                            s_name = (season.get('Name') or '').strip()
                            e_name = (ep.get('Name') or '').strip()
                            label = ('%s %s' % (s_name, e_name)).strip()
                            label = label.replace('#', '-').replace('$', '|')
                            srcs = ep.get('MediaSources') or []
                            source_id = srcs[0].get('Id', '') if srcs else ''
                            pid = ep.get('Id', '') + ('_' + source_id if source_id else '')
                            eps.append('%s$%s' % (label, pid))
                if eps:
                    play_url.append('#'.join(eps))

            vod['vod_play_from'] = '$$$'.join(play_from)
            vod['vod_play_url'] = '$$$'.join(play_url)
            return {'list': [vod]}
        except Exception:
            return {'list': []}

    def _pb_sources(self, item_id, uid, token):
        """兜底：老版本 / 特殊媒体拿 MediaSources"""
        try:
            r = self.session.post('%s/emby/Items/%s/PlaybackInfo' % (self.baseUrl, item_id),
                                  params={'UserId': uid, 'X-Emby-Token': token},
                                  json={}, timeout=self.timeout)
            if r.status_code == 200:
                return r.json().get('MediaSources') or []
        except Exception:
            pass
        return []

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
            url = ''

            if self.silentPlay:
                direct = self._stream_url(item_id, source_id, token)
                url = direct
                if self.probe and not self._probe(direct, token):
                    # 探测失败就退到 PlaybackInfo；它也不给地址时，仍然把直链交给播放器自己试
                    url = self._pb_play_url(item_id, source_id, uid, token) or direct
            else:
                url = self._pb_play_url(item_id, source_id, uid, token)
            if not url:
                return {'url': '', 'msg': '无可用播放地址'}

            if self.thread > 0 and self.threadBase:
                url = '%s?url=%s&thread=%d' % (self.threadBase.rstrip('/'), quote(url, safe=''), self.thread)

            return {'url': url, 'header': dict(self.header), 'parse': 0}
        except Exception as e:
            return {'url': '', 'msg': '播放解析异常: %s' % str(e)}

    def _stream_url(self, item_id, source_id, token):
        q = 'static=true&api_key=%s' % token
        if source_id:
            q = 'static=true&mediaSourceId=%s&api_key=%s' % (source_id, token)
        return '%s/emby/Videos/%s/stream?%s' % (self.baseUrl, item_id, q)

    def _probe(self, url, token):
        try:
            r = self.session.get(url, headers=dict(self.header, Range='bytes=0-0'),
                                 stream=True, timeout=max(30, self.timeout),
                                 allow_redirects=True)
            code = r.status_code
            r.close()
            return code in (200, 206, 302)
        except Exception:
            return False

    def _pb_play_url(self, item_id, source_id, uid, token):
        try:
            r = self.session.post('%s/emby/Items/%s/PlaybackInfo' % (self.baseUrl, item_id),
                                  params={'UserId': uid, 'X-Emby-Token': token},
                                  json={}, timeout=self.timeout)
            if r.status_code != 200:
                return ''
            sources = r.json().get('MediaSources') or []
            if not sources:
                return ''
            media = None
            if source_id:
                media = next((s for s in sources if s.get('Id') == source_id), None)
            media = media or sources[0]
            u = media.get('DirectStreamUrl') or ''
            if not u:
                sid = media.get('Id', '')
                u = self._stream_url(item_id, sid, token)
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
            r = self.session.get('%s/emby/Users/%s/Items' % (self.baseUrl, info['User']['Id']), params={
                'X-Emby-Token': token,
                'SearchTerm': keywords,
                'IncludeItemTypes': 'Movie,Series',
                'Recursive': 'true',
                'Limit': '50',
                'Fields': 'ProductionYear',
            }, timeout=self.timeout)
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
