# coding: utf-8
"""
番茄酱 (fanqiejiang) · OK影视 / TVBox / 影视仓 爬虫源
================================================================
数据源: mino 米米4K 直连接口 (番茄酱 App 主数据链)
  分类  GET /api/categories          -> data[] (type_id/type_name/type_extend)
  列表  GET /api/videos?type_id=&page=&limit=&class=&year=&area=&lang=
        -> data{list,total,page,page_size} (标准 MacCMS 字段)
  搜索  GET /api/search?wd=&page=&limit=
  详情  GET /api/videos/{vod_id}     -> 标准 MacCMS 字段 + play_list 结构化线路
  播放  POST /api/parse       body {"url": 每集token, "from": 线路名, "vod_id": id}
        -> data.url (真实 m3u8, 带时效签名)

关键机制:
  1. 请求必须带 UA / Referer(http://43.248.128.122:8080/) / X-Device-ID(32位hex)
  2. 播放换票: vod_id 必须为数字; 且 /api/parse 对 device_id 有防重放限制,
     每次换票必须使用全新随机 device_id 才能稳定成功
  3. 部分线路(rose/co 等)接口侧解析不稳定, 已实现同剧跨线路自动回退
  4. 输出双字段(typeId/type_id 等), 兼容 OK影视 与 TVBox/影视仓 引擎

功能覆盖: 分类栏 / 子分类筛选 / 海报 / 搜索(含翻页) / 多线路播放 / 自动换源
"""

try:
    from base.spider import Spider
except ImportError:
    class Spider:
        pass

import json
import re
import time
import uuid
import urllib.parse

try:
    import urllib.request as _urlreq
except Exception:
    _urlreq = None

try:
    import requests
except ImportError:
    requests = None

try:
    import ssl
    _ssl_ctx = ssl.create_default_context()
    _ssl_ctx.check_hostname = False
    _ssl_ctx.verify_mode = ssl.CERT_NONE
except Exception:
    _ssl_ctx = None


class Spider(Spider):

    # ========== TVBox 引擎必需属性 ==========
    name = 'fanqiejiang'
    searchable = 1
    quickSearch = 1
    filterable = 1
    changeable = 0

    siteUrl = 'http://43.248.128.122:8080'
    api = siteUrl + '/api'

    # collect 网关 nby/gulu 站 (App 短剧数据源: 名称桥接 gulu_id -> 直链)
    NBY = 'https://collect.fanqiecn.com/jx/station/nby'
    GULU = 'https://fanqiecn.com/jx/r.m3u8?v=gulu:%s:%d&mode=m3u8'

    # 线路 token 前缀 -> 显示名 (App 内映射)
    PLAY_ALIAS = {
        'rose': '超清', 'qq': 'TX', 'duanju': '星4K', 'zijianm3u8': '云4K',
        'mgtv': '芒果', 'qiyi': '奇异', 'youku': '优酷', 'bilibili': '哔哩哔哩',
        '1080P': '1080P', 'RR': '外剧专线', 'SZYS': '臻彩4K', 'zydj': '短剧',
        'gulu': '短剧',
        'CO4K': '番茄4K', 'JD4K': '番茄4K-2', 'qsvip': '高清专线',
        'newxfyun': '新旋风', 'nby': 'NBY', 'dyttm3u8': '电影天堂',
        'lzm3u8': '量子', 'bfzym3u8': '暴风', 'ffm3u8': '非凡',
    }

    # 只追加这 4 条 4K 线路, 其余全部丢弃
    KEEP_4K = ('星4K', '云4K', '番茄4K', '番茄4K-2')

    # 线路显示优先级 (越靠前越优先); 不在列表中的排最后
    PLAY_ORDER = [
        '番茄4K', '番茄4K-2', '星4K', '云4K',
        'qq', 'mgtv', 'qiyi', 'youku',
    ]
    # 屏蔽线路黑名单 (填写别名映射后的显示名, 匹配时忽略大小写)
    PLAY_BLOCK = []

    @classmethod
    def _alias(cls, token):
        """线路 token -> 显示名; 未收录的保留原 token"""
        t = str(token or '')
        low = t.lower()
        for k, v in cls.PLAY_ALIAS.items():
            if low == k.lower():
                return v
        # 含关键字模糊匹配
        if '4k' in low and 'zijian' in low:
            return '云4K'
        if 'duanju' in low:
            return '星4K'
        return t

    @classmethod
    def _unalias(cls, name):
        """显示名 -> 原始线路 token; 找不到则原样返回"""
        t = str(name or '')
        for k, v in cls.PLAY_ALIAS.items():
            if t == v:
                return k
        return t

    # 通用筛选维度 (地区/语言/年份), 分类子类由接口动态下发
    FILTER_AREA = ['内地', '香港', '台湾', '美国', '韩国', '日本', '英国', '泰国', '印度', '其他']
    FILTER_LANG = ['国语', '粤语', '英语', '日语', '韩语', '泰语', '其他']
    FILTER_YEAR = [str(y) for y in range(2026, 2015, -1)]

    UA = ('Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36')

    def __init__(self):
        self.device_id = uuid.uuid4().hex          # 32位hex, 每次启动随机
        self._cur_vod_id = ''                      # 播放换票用的 vod_id
        self._last_vod_id = {}                     # 线路名 -> vod_id (播放时回退)
        self._play_map = {}                        # vod_id -> {线路名: {集名: token}}
        self._gulu_bridge = {}                     # vod_id -> (gulu_id, 集数) 短剧桥接
        self._live_cache = None                    # 直播频道缓存 (None=未加载)
        self.headers = {
            "User-Agent": self.UA,
            "Accept": "application/json, */*",
            "X-Device-ID": self.device_id,
            "Referer": self.siteUrl + "/",
        }

    # ========== 引擎生命周期 (壳环境强制要求) ==========

    def getName(self):
        return "番茄酱"

    def init(self, extend=""):
        return

    def isVideoFormat(self, url):
        return self._is_media(url)

    def manualVideoCheck(self):
        return

    def destroy(self):
        return

    # ========== HTTP ==========

    def _get_json(self, url, timeout=15):
        """URL 编码参数后 GET, 返回 dict (失败返回 {})"""
        return self._request('GET', url, timeout=timeout)

    def _post_parse(self, url, body, timeout=15):
        """换票 POST, body 为 dict, 返回 dict (失败返回 {})"""
        return self._request('POST', url, body=body, timeout=timeout)

    # ========== nby/gulu 短剧桥接 (App 短剧数据源) ==========

    def _nby_get(self, path, params=None):
        """请求 collect 网关 nby 站 (短剧库: search/detail/play)
        App 短剧播放链路: nby search(名称) -> detail(gulu_id/集数) ->
        r.m3u8?v=gulu:{id}:{ep}&mode=m3u8 -> 302 直链 m3u8 (无需换票/IP白名单)
        """
        qs = ''
        if params:
            qs = '?' + urllib.parse.urlencode(params)
        return self._get_json(self.NBY + path + qs)

    def _nby_search(self, name):
        """nby 站按名称搜索短剧, 返回 [{vod_id, vod_name, ...}]"""
        if not name:
            return []
        j = self._nby_get('/search', {'q': str(name)})
        return (j.get('list') or [])

    def _nby_detail(self, gid):
        """nby 站短剧详情, 返回 {vod_play_from, vod_play_url, ...}"""
        j = self._nby_get('/detail', {'id': str(gid)})
        lst = j.get('list') or []
        return lst[0] if lst else {}

    def _nby_bridge(self, vod_name):
        """名称桥接: 在 nby/gulu 短剧库按剧名找 gulu_id 与可播线路.
        优先精确同名; 否则取搜索结果第一条.
        线路分类:
          - gulu 型 (source=rose 等 lirose 系): r.m3u8 302 直链可播
          - 直链 m3u8 型 (dyttm3u8/lzm3u8/ffm3u8): 直接透传
          - 网页型 (qiyi 等): 保留原始链接, 播放时走 /api/parse 兜底
        失败返回 None.
        """
        if not vod_name:
            return None
        hits = self._nby_search(vod_name)
        if not hits:
            return None
        hit = None
        for h in hits:
            if (h.get('vod_name') or '') == vod_name:
                hit = h
                break
        if hit is None:
            hit = hits[0]
        gid = str(hit.get('vod_id') or '')
        if not gid or not gid.isdigit():
            return None
        d = self._nby_detail(gid)
        if not d:
            return None
        # 解析 nby 各线路 (from -> [(集名, url)])
        froms = (d.get('vod_play_from') or '').split('$$$')
        urls = (d.get('vod_play_url') or '').split('$$$')
        lines = []          # [{'from': f, 'kind': 'gulu'|'direct'|'web', 'eps': [(name,url)]}]
        max_eps = 0
        for i, f in enumerate(froms):
            u = urls[i] if i < len(urls) else ''
            if not f or not u:
                continue
            eps = []
            for ep in u.split('#'):
                if '$' not in ep:
                    continue
                nm, link = ep.split('$', 1)
                if nm and link.strip():
                    eps.append((nm.strip(), link.strip()))
            if not eps:
                continue
            # 线路类型判定
            f0 = f.lower()
            if self._is_media(u):
                kind = 'direct'      # 直链 m3u8
            elif 'rose' in f0 or 'zijianm3u8' in f0 or 'qq' in f0 or 'zydj' in f0:
                kind = 'gulu'        # lirose 系: 可经 r.m3u8 302 直链播放
            else:
                kind = 'web'         # 网页链接: 走换票
            lines.append({'from': f, 'kind': kind, 'eps': eps})
            max_eps = max(max_eps, len(eps))
        if not lines:
            return None
        return {'gid': gid, 'eps': max_eps, 'lines': lines,
                'name': d.get('vod_name') or ''}

    def _gulu_play_url(self, gid, ep):
        """第 ep 集 (0 基) 的 gulu 播放地址: r.m3u8 302 直链模板"""
        return self.GULU % (str(gid), int(ep))

    def _gulu_resolve(self, url):
        """r.m3u8 302 直链解析: 客户端跟随重定向拿到最终 m3u8 直链;
        失败时原样返回 (旧版播放器可自行重定向).
        """
        try:
            hdr = {'User-Agent': self.UA, 'Referer': 'https://fanqiecn.com/'}
            if requests is not None:
                r = requests.get(url, headers=hdr, timeout=20, allow_redirects=True,
                                 verify=False)
                if r.status_code == 200:
                    return r.url or url
            elif _urlreq is not None:
                req = _urlreq.Request(url, headers=hdr)
                with _urlreq.urlopen(req, timeout=20, context=_ssl_ctx) as resp:
                    return resp.geturl() or url
        except Exception:
            pass
        return url

    def _nby_lines(self, vod_name):
        """用精确片名在 nby 站匹配, 返回补充线路
        [{'from': token, 'eps': [{'name','url'}]}]，含 CO4K/JD4K 等主接口没有的线路"""
        if not vod_name:
            return []
        j = self._nby_get('/search', {'q': vod_name})
        hits = j.get('list') or []
        hit = None
        for h in hits:
            if (h.get('vod_name') or '').strip() == str(vod_name).strip():
                hit = h
                break
        if not hit:
            return []
        gid = str(hit.get('vod_id') or '')
        if not gid.isdigit():
            return []
        d = self._nby_get('/detail', {'id': gid})
        lst = d.get('list') or []
        if not lst:
            return []
        v = lst[0]
        froms = (v.get('vod_play_from') or '').split('$$$')
        urls = (v.get('vod_play_url') or '').split('$$$')
        out = []
        for i, f in enumerate(froms):
            u = urls[i] if i < len(urls) else ''
            if not f or not u:
                continue
            eps = []
            for ep in u.split('#'):
                if '$' not in ep:
                    continue
                nm, link = ep.split('$', 1)
                nm, link = nm.strip(), link.strip()
                if nm and link:
                    eps.append({'name': nm, 'url': link})
            if eps:
                out.append({'from': f, 'eps': eps, 'gid': gid})
        return out

    def _nby_resolve(self, token, gid, from_name):
        """nby 站换票: 直链直接返回; token 调 nby/play"""
        u = (token or '').strip()
        if not u:
            return ''
        if self._is_media(u):
            return u
        if u.startswith('http'):
            # 网页链接: 尝试 nby play
            pass
        j = self._get_json(self.NBY + '/play?url=' + urllib.parse.quote(u, safe='') + '&id=' + str(gid))
        return (j.get('url') or '') if isinstance(j, dict) else ''

    def _request(self, method, url, body=None, timeout=15):
        """requests 优先 (verify=False, 兼容 Chaquopy 壳对证书的不信任),
        无 requests 时回退 urllib, 双请求层均可用。
        """
        h = dict(self.headers)
        # 换票必须使用全新随机 device_id, 覆盖默认头
        if method == 'POST' and body is not None and 'X-Device-ID' not in body:
            h['X-Device-ID'] = uuid.uuid4().hex
        try:
            if requests is not None:
                if method == 'POST':
                    h['Content-Type'] = 'application/json'
                    r = requests.post(url, data=json.dumps(body).encode('utf-8'),
                                      headers=h, timeout=timeout, verify=False)
                else:
                    r = requests.get(url, headers=h, timeout=timeout, verify=False)
                return json.loads(r.text) if r.status_code == 200 else {}
            if _urlreq is not None:
                kw = {'headers': h, 'timeout': timeout}
                if _ssl_ctx is not None and url.startswith('https'):
                    kw['context'] = _ssl_ctx
                if method == 'POST' and body is not None:
                    kw['data'] = json.dumps(body).encode('utf-8')
                    kw['method'] = 'POST'
                    h['Content-Type'] = 'application/json'
                    kw['headers'] = h
                    req = _urlreq.Request(url, **kw)
                else:
                    req = _urlreq.Request(url, **kw)
                with _urlreq.urlopen(req, timeout=timeout) as resp:
                    return json.loads(resp.read().decode('utf-8', 'ignore'))
        except Exception:
            return {}
        return {}

    # ========== 数据裁剪 ==========

    @staticmethod
    def _is_media(url):
        """是否为可直接播放的媒体直链"""
        u = (url or '').strip().lower()
        return bool(re.search(r'\.(m3u8|mp4|flv|mkv|ts|m4s)(\?|#|$)', u))

    @staticmethod
    def _is_webpage(url):
        """是否为外站网页链接 (v.qq.com 等, 无法直换票)"""
        u = (url or '').strip().lower()
        return bool(re.match(r'^https?://', u)) and not Spider._is_media(u)

    @staticmethod
    def _pick_vod(info):
        """截取前端常用字段 (双字段: 驼峰 + 蛇形, 兼容不同引擎)"""
        def both(snake, camel):
            v = info.get(snake, '')
            if snake == 'vod_id':
                v = str(v or '')
            elif snake in ('vod_score',):
                v = str(v or '')
            else:
                v = v or ''
            return {snake: v, camel: v}

        d = {}
        d.update(both('vod_id', 'vodId'))
        d.update(both('vod_name', 'vodName'))
        d.update(both('vod_pic', 'vodPic'))
        d.update(both('vod_remarks', 'vodRemarks'))
        d.update(both('vod_year', 'vodYear'))
        d.update(both('vod_area', 'vodArea'))
        d.update(both('vod_class', 'vodClass'))
        d.update(both('vod_score', 'vodScore'))
        d.update(both('vod_actor', 'vodActor'))
        d.update(both('vod_director', 'vodDirector'))
        return d

    # ========== 首页 / 分类 ==========

    def homeContent(self, filter):
        cats = self._get_json(self.api + '/categories')
        classes, filters = [], {}
        # 直播分类固定置顶 (数据来自 /api/live/channels)
        classes.append({'type_id': 'live', 'typeId': 'live',
                        'type_name': '直播', 'typeName': '直播'})
        filters['live'] = [{'key': 'group', 'name': '分组',
                            'value': [{'n': '全部', 'v': ''},
                                      {'n': '央视频道', 'v': '央视频道'},
                                      {'n': '卫视频道', 'v': '卫视频道'},
                                      {'n': '附加地方频道', 'v': '附加地方频道'}]}]
        for c in (cats.get('data') or []):
            tid = str(c.get('type_id', ''))
            name = c.get('type_name', '')
            if not tid:
                continue
            # 双字段: typeId/type_id 均输出
            classes.append({'type_id': tid, 'typeId': tid,
                            'type_name': name, 'typeName': name})
            sub = []
            try:
                ext = json.loads(c.get('type_extend') or '{}')
                sub = [{'n': s, 'v': s} for s in (ext.get('class') or []) if s]
            except Exception:
                sub = []
            filters[tid] = [
                {'key': '分类', 'name': '分类',
                 'value': [{'n': '全部', 'v': ''}] + sub},
                {'key': '地区', 'name': '地区',
                 'value': [{'n': '全部', 'v': ''}] +
                          [{'n': a, 'v': a} for a in self.FILTER_AREA]},
                {'key': '语言', 'name': '语言',
                 'value': [{'n': '全部', 'v': ''}] +
                          [{'n': l, 'v': l} for l in self.FILTER_LANG]},
                {'key': '年份', 'name': '年份',
                 'value': [{'n': '全部', 'v': ''}] +
                          [{'n': y, 'v': y} for y in self.FILTER_YEAR]},
            ]
        return {'class': classes, 'filters': filters,
                'list': self.homeVideoContent().get('list', [])}

    def homeVideoContent(self):
        return self._fetch_list({})

    # ========== 直播 ==========

    def _live_load(self):
        """拉取直播频道全量并缓存, 返回 [(分组, [频道])] 有序列表.
        接口: GET /api/live/channels -> data[{id,name,category,sources:[{url,..}]}]
        """
        if self._live_cache is not None:
            return self._live_cache
        groups = {}          # 分组名 -> [频道]
        order = []           # 分组出现顺序 (央视频道/卫视频道/附加地方频道)
        j = self._get_json(self.api + '/live/channels')
        for c in (j.get('data') or []):
            if not isinstance(c, dict):
                continue
            # 只保留有可用源的频道
            srcs = [s for s in (c.get('sources') or [])
                    if isinstance(s, dict) and (s.get('url') or '').strip()]
            if not srcs:
                continue
            g = c.get('category') or '其他'
            if g not in groups:
                groups[g] = []
                order.append(g)
            groups[g].append((c, srcs))
        # 按分组固定顺序 + 频道内 sort_order 排序
        res = []
        for g in order:
            lst = groups[g]
            lst.sort(key=lambda x: (x[0].get('sort_order') or 0,
                                    x[0].get('id') or 0))
            res.append((g, [c for c, _ in lst]))
        self._live_cache = res
        return res

    def _live_page(self, pg, extend):
        """直播频道分页列表: 分组筛选由 extend['group'] 决定, 每页 50"""
        try:
            page = max(int(pg), 1)
        except Exception:
            page = 1
        ext = extend if isinstance(extend, dict) else {}
        group = str(ext.get('group') or '').strip()
        LEN = 50
        chans = []
        for g, lst in self._live_load():
            if group and g != group:
                continue
            chans.extend(lst)
        total = len(chans)
        pagecount = max(-(-total // LEN), 1) if total else 1
        page = min(page, pagecount)
        start = (page - 1) * LEN
        vlist = []
        for c in chans[start:start + LEN]:
            vlist.append({
                'vod_id': 'live_' + str(c.get('id', '')),
                'vodId': 'live_' + str(c.get('id', '')),
                'vod_name': c.get('name') or '',
                'vodName': c.get('name') or '',
                'vod_pic': c.get('logo') or '',
                'vodPic': c.get('logo') or '',
                'vod_remarks': '直播',
                'vodRemarks': '直播',
            })
        return {'list': vlist, 'page': page, 'pagecount': pagecount,
                'limit': LEN, 'total': total}

    def _live_detail(self, vid):
        """直播频道详情: sources[] 每个源一条线路 (名称为 线路N)"""
        self._cur_vod_id = vid
        cid = str(vid)[5:]
        ch, srcs = None, []
        for _, lst in self._live_load():
            for c in lst:
                if str(c.get('id')) == cid:
                    ch = c
                    break
            if ch:
                break
        if not ch:
            return {'list': []}
        srcs = [s for s in (ch.get('sources') or [])
                if isinstance(s, dict) and (s.get('url') or '').strip()]
        if not srcs:
            return {'list': []}
        froms, urls = [], []
        for i, s in enumerate(srcs, 1):
            name = '线路%d' % i
            u = s.get('url', '').strip()
            if u.startswith('//'):
                u = 'https:' + u
            froms.append(name)
            urls.append(u)
        d = {
            'vod_id': vid,
            'vodId': vid,
            'vod_name': ch.get('name') or '',
            'vodName': ch.get('name') or '',
            'vod_pic': ch.get('logo') or '',
            'vodPic': ch.get('logo') or '',
            'vod_remarks': '直播',
            'vodRemarks': '直播',
            'vod_area': ch.get('category') or '直播',
            'vodArea': ch.get('category') or '直播',
            'vod_content': (ch.get('name') or '') + ' 电视直播频道',
            'vodContent': (ch.get('name') or '') + ' 电视直播频道',
            'vod_play_from': '$$$'.join(froms),
            'vodPlayFrom': '$$$'.join(froms),
            # 直播地址为 m3u8 直链, playerContent 直接透传
            'vod_play_url': '$$$'.join(urls),
            'vodPlayUrl': '$$$'.join(urls),
        }
        return {'list': [d]}

    # ========== 列表 / 筛选 ==========

    def _fetch_list(self, params):
        """params: t / wd / page / class / year / area / lang
        (列表接口主分类参数为 t, 对应 /api/categories 的 type_id)
        """
        p = dict(params)
        p.setdefault('limit', '20')
        if 'page' not in p:
            p['page'] = '1'
        qs = urllib.parse.urlencode({k: v for k, v in p.items() if v != ''})
        j = self._get_json(self.api + '/videos?' + qs)
        data = j.get('data') or {}
        vlist = [self._pick_vod(v) for v in (data.get('list') or [])]
        total = data.get('total') or 0
        try:
            page = int(data.get('page') or 1)
        except Exception:
            page = 1
        try:
            pagecount = -(-total // int(p.get('limit', 20))) if total else 1
        except Exception:
            pagecount = 1
        try:
            limit = int(p.get('limit', 20))
        except Exception:
            limit = 20
        return {'list': vlist, 'page': page, 'pagecount': pagecount,
                'limit': limit, 'total': total}

    def categoryContent(self, tid, pg, filter, extend):
        # ---- 直播分类 (live) ----
        if str(tid) == 'live':
            return self._live_page(pg, extend)
        if not str(tid).isdigit():
            return {'list': [], 'page': 1, 'pagecount': 1, 'limit': 20, 'total': 0}
        ext = extend if isinstance(extend, dict) else {}
        try:
            page = str(int(pg) if str(pg).isdigit() else 1)
        except Exception:
            page = '1'
        params = {'t': str(tid), 'page': page}
        # 接口筛选参数为 class/area/lang/year, 兼容中英文 filter key
        alias = {'class': '分类', 'area': '地区', 'lang': '语言', 'year': '年份'}
        for en, zh in alias.items():
            v = ext.get(en) or ext.get(zh)
            if v:
                params[en] = str(v)
        return self._fetch_list(params)

    # ========== 详情 ==========

    def detailContent(self, ids):
        if not ids:
            return {'list': []}
        vid = str(ids[0])
        # ---- 直播频道详情 ----
        if vid.startswith('live_'):
            return self._live_detail(vid)
        item = self._get_json(self.api + '/videos/' + vid).get('data') or {}
        if not item:
            return {'list': []}
        self._cur_vod_id = vid

        d = self._pick_vod(item)
        d['vod_content'] = item.get('vod_content', '') or ''
        d['vodContent'] = d['vod_content']

        # 缓存详情播放结构, 供 playerContent 自动换源回退
        pmap = {}
        for pl0 in (item.get('play_list') or []):
            f = pl0.get('from') or ''
            eps = {}
            for e in (pl0.get('episodes') or []):
                nm, u = (e.get('name') or ''), (e.get('url') or '')
                if nm and u:
                    eps.setdefault(nm, u)
            if f:
                pmap[f] = eps
        if pmap:
            self._play_map[vid] = pmap

        # 线路: 保留所有原始线路 (包括token/网页/直链),
        # 壳端需要完整线路列表做展示; 播放时走换票或fallback兜底.
        # 集名统一规范化并强制按数字大小升序, 修复超100集错排/不显示
        froms = (item.get('vod_play_from') or '').split('$$$')
        urls = (item.get('vod_play_url') or '').split('$$$')
        keep_from, keep_url = [], []
        for i, f in enumerate(froms):
            u = urls[i] if i < len(urls) else ''
            if not f or not u:
                continue
            raw = []
            for ep in u.split('#'):
                if '$' not in ep:
                    continue
                name, link = ep.split('$', 1)
                if not link.strip():
                    continue
                raw.append((name.strip(), link.strip()))
            if raw:
                raw = self._sort_eps(raw)
                # 基于别名映射后的显示名去重, 避免同别名多原始名重复展示
                alias_name = self._alias(f)
                # 若已有同名别名, 保留首个并跳过后续重复的别名线路
                existing_aliases = [self._alias(x) for x in keep_from]
                if alias_name in existing_aliases:
                    continue
                keep_from.append(f)
                keep_url.append('#'.join('%s$%s' % (nm, lk) for nm, lk in raw))

        # ---- 短剧/无线路兜底: nby/gulu 库名称桥接 ----
        # mino 站短剧 (t=5) 详情无线路, App 内短剧走 collect nby/gulu 库:
        # 按剧名在 nby 搜索 -> 线路 (rose 系经 r.m3u8 302 直链 / 直链 m3u8 / 网页换票)
        # 仅当原生无线路时才桥接, 避免给已有原生线路的剧混入不可播桥接线路
        if not keep_from:
            vod_name = item.get('vod_name') or ''
            br = self._nby_bridge(vod_name)
            if br:
                for ln in br['lines']:
                    f = ln['from']
                    if f in keep_from:          # 已有同名线路, 避免重复
                        continue
                    eps = self._sort_eps(ln['eps'])
                    pairs = []
                    eps_map = {}
                    for e, (nm, link) in enumerate(eps):
                        if ln['kind'] == 'gulu':
                            link = self._gulu_play_url(br['gid'], e)  # r.m3u8 302 直链, 索引=排序后序号
                        pairs.append('%s$%s' % (nm, link))
                        eps_map[nm] = link
                    if pairs:
                        keep_from.append(f)
                        keep_url.append('#'.join(pairs))
                        pmap[f] = eps_map
                if keep_from and br['lines']:
                    self._gulu_bridge[vid] = (br['gid'], br['eps'])
                    self._play_map[vid] = pmap

        # ---- nby 站补充线路: 追加主接口没有的多源线路 (含 4K) ----
        # 追加所有不在 keep_from 中的非重复线路
        try:
            nbr = self._nby_lines(item.get('vod_name') or '')
            for ln in nbr:
                alias = self._alias(ln['from'])
                # 基于别名去重, 兼容 keep_from 中既有原始名也有别名的情况
                existing_aliases = [self._alias(x) for x in keep_from]
                if alias in existing_aliases:
                    continue
                eps = self._sort_eps([(e['name'], e['url']) for e in ln['eps']])
                if not eps:
                    continue
                pairs = []
                emap = {}
                for nm, link in eps:
                    pairs.append('%s$%s@@nby:%s:%s' % (nm, link, ln.get('gid', ''), ln['from']))
                    emap[nm] = link
                keep_from.append(alias)
                keep_url.append('#'.join(pairs))
                pmap['nby:' + alias] = emap
            self._play_map[vid] = pmap
        except Exception:
            pass

        # ---- 线路屏蔽 + 排序 (基于别名映射后的显示名, 同时支持原始名匹配) ----
        def _sort_key(f_name):
            alias_name = self._alias(f_name)
            # 屏蔽黑名单 (同时匹配别名和原始名, 忽略大小写)
            block_names = [b.lower() for b in self.PLAY_BLOCK]
            if alias_name.lower() in block_names or f_name.lower() in block_names:
                return (1, 9999, f_name)
            # 优先按 PLAY_ORDER 排序 (同时支持别名和原始名)
            idx = 9999
            for target in (alias_name, f_name):
                if target in self.PLAY_ORDER:
                    idx = self.PLAY_ORDER.index(target)
                    break
            return (0, idx, f_name)

        zipped = list(zip(keep_from, keep_url))
        zipped.sort(key=lambda x: _sort_key(x[0]))
        # 过滤掉被屏蔽的线路
        filtered = [(f, u) for f, u in zipped if _sort_key(f)[0] == 0]
        keep_from = [x[0] for x in filtered]
        keep_url  = [x[1] for x in filtered]

        # 最终线路名用别名映射后的显示名, 但保留原始名供 playerContent 换票
        keep_from_alias = [self._alias(f) for f in keep_from]
        pf = '$$$'.join(keep_from_alias)
        pu = '$$$'.join(keep_url)
        d['vod_play_from'] = pf
        d['vodPlayFrom'] = pf
        d['vod_play_url'] = pu
        d['vodPlayUrl'] = pu
        return {'list': [d]}

    # ========== 搜索 ==========

    def searchContent(self, key, quick, pg='1'):
        try:
            page = str(int(pg) if str(pg).isdigit() else 1)
        except Exception:
            page = '1'
        qs = urllib.parse.urlencode({'wd': str(key), 'page': page, 'limit': '20'})
        j = self._get_json(self.api + '/search?' + qs)
        data = j.get('data') or {}
        vlist = [self._pick_vod(v) for v in (data.get('list') or [])]
        total = data.get('total') or 0
        try:
            pagecount = -(-total // 20) if total else 1
        except Exception:
            pagecount = 1
        return {'list': vlist, 'page': int(page), 'pagecount': pagecount,
                'limit': 20, 'total': total}

    def searchContentPage(self, key, quick, pg='1'):
        return self.searchContent(key, quick, pg)

    # ========== 播放 ==========

    def playerContent(self, flag, id, vipFlags):
        """flag 为线路名(如 zijianm3u8/rose), id 为每集链接 (可能带 名称$ 前缀)
        换票失败时自动回退到同剧其他线路的同一集 (接口侧部分线路解析不稳定)
        """
        raw = str(id or '')
        ep_name, link = '', raw
        if '$' in raw:
            ep_name, link = raw.split('$', 1)
        ep_name = (ep_name or '').strip()
        link = link.strip()
        # 播放 id 尾部可能带 @@<原始线路token>；显示名(星4K/云4K)用于展示，换票须用原始 from
        real_from = str(flag or '')
        if '@@' in link:
            link, real_from = link.rsplit('@@', 1)
            link = link.strip()
            real_from = real_from.strip()
        header = {'User-Agent': self.UA, 'Referer': self.siteUrl + '/'}

        # nby 补充线路: marker 形如 nby:<gid>:from
        if real_from.startswith('nby:'):
            parts = real_from.split(':', 2)
            gid = parts[1] if len(parts) > 1 else ''
            nfrom = parts[2] if len(parts) > 2 else ''
            nh = {'User-Agent': self.UA, 'Referer': 'https://collect.fanqiecn.com/'}
            if self._is_media(link):
                return {'parse': 0, 'url': link, 'header': nh}
            real = self._nby_resolve(link, gid, nfrom)
            if real:
                return {'parse': 0, 'url': real, 'header': nh}
            return {'parse': 1, 'url': '', 'header': nh}

        flag = real_from
        # 还原别名映射为原始线路名, 保证 _play_map 与 _api_parse 能正确匹配
        flag = self._unalias(flag)

        if not link:
            return {'parse': 0, 'url': '', 'header': header}
        # 直播频道直链: URL 可能不带扩展名, 直接透传 (任何 http(s) 链接均可)
        if str(self._cur_vod_id).startswith('live_'):
            return {'parse': 0, 'url': link, 'header': header}
        # 短剧 gulu 线路: r.m3u8 模板 -> 跟随 302 到直链 m3u8 (无需换票)
        if flag == 'gulu' or 'r.m3u8?v=gulu:' in link:
            resolved = self._gulu_resolve(link)
            return {'parse': 0, 'url': resolved,
                    'header': {'User-Agent': self.UA, 'Referer': 'https://fanqiecn.com/'}}
        if self._is_media(link):
            return {'parse': 0, 'url': link, 'header': header}
        if self._is_webpage(link):
            # 外站网页无法直接播放, 尝试走换票接口兜底 (失败则尝试其他线路同集)
            res = self._parse_ticket(flag, link)
            if not res['url']:
                res = self._fallback_play(flag, ep_name)
            return res

        # 其余为 token (zijian_/rose_ 等) -> 换票
        res = self._parse_ticket(flag, link)
        if not res['url']:
            res = self._fallback_play(flag, ep_name)
        return res

    @staticmethod
    def _ep_no(ep_name):
        """集名归一化: '第1集'/'01'/'1'/'E01' -> 1; 无数字返回 -1"""
        _m = re.search(r'(\d+)', str(ep_name or ''))
        return int(_m.group(1)) if _m else -1

    @staticmethod
    def _norm_ep_name(ep_name, width=1):
        """集名规范化: 纯数字 -> 第%0{width}d集; 含数字的替换数字部分为等宽,
        不含数字的原样返回(会被过滤). 等宽使壳端字符串排序与数字序一致,
        根治超100集字典序错乱"""
        s = str(ep_name or '').strip()
        if s.isdigit():
            return '第%s集' % str(int(s)).zfill(width)
        _m = re.search(r'(\d+)', s)
        if _m:
            num = int(_m.group(1))
            return s[:_m.start()] + str(num).zfill(width) + s[_m.end():]
        return s

    def _sort_eps(self, eps):
        """[(集名, 链接)] -> 集名规范化(等宽数字) + 过滤非集数杂质 + 强制按数字升序"""
        max_no = 0
        for nm, _ in eps:
            n = self._ep_no(nm)
            if n > max_no:
                max_no = n
        width = len(str(max_no)) if max_no else 1
        out = []
        for i, (nm, link) in enumerate(eps):
            n = self._ep_no(nm)
            if n < 0:
                continue          # 过滤无数字杂质项(海报/视频信息/演员头像)
            out.append((self._norm_ep_name(nm, width), link, n, i))
        out.sort(key=lambda x: (x[2], x[3]))
        return [(a, b) for a, b, _, _ in out]

    def _fallback_play(self, flag, ep_name):
        """主线路换票失败 -> 按集名在同剧其他线路中依次试换票
        集名做数字归一化匹配 (rose 用 '1', zijianm3u8 用 '第1集')"""
        vid = self._play_map.get(self._cur_vod_id) or {}
        if not vid or not ep_name:
            return {'parse': 0, 'url': '', 'header': {}}
        base_no = self._ep_no(ep_name)
        for f, eps in vid.items():
            if f == flag:
                continue
            tok = eps.get(ep_name)
            if not tok and base_no >= 0:
                # 精确集名未命中时按集号归一化匹配
                for k, v in eps.items():
                    if self._ep_no(k) == base_no:
                        tok = v
                        break
            if not tok:
                continue
            if f == 'gulu' or 'r.m3u8?v=gulu:' in tok:
                # gulu 短剧直链: 直接 302 解析
                resolved = self._gulu_resolve(tok)
                if resolved:
                    return {'parse': 0, 'url': resolved,
                            'header': {'User-Agent': self.UA,
                                       'Referer': 'https://fanqiecn.com/'}}
            else:
                res = self._parse_ticket(f, tok)
                if res['url']:
                    return res
        return {'parse': 0, 'url': '', 'header': {}}

    def _parse_ticket(self, flag, token):
        vid = self._cur_vod_id or self._last_vod_id.get(flag, '')
        # 换票接口要求 vod_id 为数字; 且每次换票使用全新随机 device_id (防重放)
        try:
            vid = int(vid)
        except Exception:
            pass
        body = {'url': token, 'from': flag, 'vod_id': vid}
        # 由 _request 自动注入随机 X-Device-ID
        j = self._request('POST', self.api + '/parse', body=body)
        data = j.get('data') or {}
        url = data.get('url', '') or ''
        code = j.get('code', 0)
        # 综艺(网页线路)换票: 首次常被游客次数限制(40311)或解析抖动,
        # 换全新随机 device_id 重试一次即可出票
        if not url and (code == 40311 or str(code) == '40311' or flag in ('mgtv', 'qiyi')):
            j = self._request('POST', self.api + '/parse', body=body)
            data = j.get('data') or {}
            url = data.get('url', '') or ''
        self._last_vod_id[flag] = vid
        # mgtv CDN 校验请求头: 强制 Chrome UA/Referer 会被 403 拒;
        # 返回空 header 让播放器用自己的头 (真机 ExoPlayer/ijk 头可过, 沙箱无头已验 200)
        if url and ('mgtv.com' in url or '.titan.' in url):
            return {'parse': 0, 'url': url, 'header': {}}
        return {'parse': 0, 'url': url,
                'header': {'User-Agent': self.UA, 'Referer': self.siteUrl + '/'}}

    def localProxy(self, param):
        return [200, "video/MP2T", b"", {}]