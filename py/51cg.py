# -*- coding: utf-8 -*-
import colorsys
import json
import random
import re
import sys
import threading
import time
import socket
import urllib3
urllib3.disable_warnings()
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
try:
    from Crypto.Hash import SHA256
except Exception:
    SHA256 = None
import hashlib
from lxml import etree
try:
    import cssselect
except Exception:
    cssselect = None
from base64 import b64decode, b64encode
from pprint import pprint
from urllib.parse import urlparse, quote, unquote
sys.path.append('..')
from base.spider import Spider


class DNSBypassAdapter(HTTPAdapter):
    """自定义适配器，规避移动DNS劫持；host强制使用IP解析，http host头保留域名"""
    def __init__(self, *args, **kwargs):
        self.custom_hosts = {}
        super().__init__(*args, **kwargs)

    def add_host(self, domain, ip):
        self.custom_hosts[domain.lower()] = ip

    def get_connection(self, url, proxies=None):
        parsed = urlparse(url)
        host = parsed.hostname
        if host and host.lower() in self.custom_hosts:
            real_ip = self.custom_hosts[host.lower()]
            new_url = url.replace(f"//{host}/", f"//{real_ip}/")
            conn = super().get_connection(new_url, proxies=proxies)
            conn.conn.host = host
            return conn
        return super().get_connection(url, proxies=proxies)


class Spider(Spider):
    # 【静态备用域名，移动网动态解析失效时兜底】
    STATIC_BACKUP_HOSTS = [
        'https://nutkvpuvh.oozzvqhzt.cc',
        'https://emxhyyqylw.rigxwsgw.com',
        'https://ktotmwbfwp.oozzvqhzt.cc',
    ]
    FALLBACK_HOSTS = [
        'https://nutkvpuvh.oozzvqhzt.cc',
        'https://emxhyyqylw.rigxwsgw.com',
        'https://ktotmwbfwp.oozzvqhzt.cc',
    ]

    def init(self, extend="{}"):
        self.domin = 'https://cg51.com'
        self.proxies = {}
        # =========【PG内置代理支持】=========
        if extend:
            try:
                cfg = json.loads(extend)
                proxy = cfg.get("proxy")
                if proxy:
                    proxies_dict = {}
                    if isinstance(proxy, str):
                        p = proxy if proxy.startswith("http") else f"http://{proxy}"
                        proxies_dict["http"] = p
                        proxies_dict["https"] = p
                    elif isinstance(proxy, dict):
                        for k, v in proxy.items():
                            if k in ("http", "https") and v:
                                pv = v if v.startswith("http") else f"http://{v}"
                                proxies_dict[k] = pv
                    if proxies_dict:
                        self.proxies = proxies_dict
            except Exception:
                pass
        # ====================================
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Mobile Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'sec-ch-ua': '"Not/A)Brand";v="8", "Chromium";v="134", "Google Chrome";v="134"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'X-Requested-With': 'mark.via.gp'
        }
        self.session = Session()
        self.session.verify = False
        self.session.proxies.update(self.proxies)

        # 会话适配器优化：移动网络缩短超时，关闭重试，减少TLS指纹特征
        retry_strategy = Retry(total=0, backoff_factor=0)
        adapter = DNSBypassAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        # 先通过发布站动态刷新 FALLBACK_HOSTS
        self.refresh_fallback_hosts()
        hosts = []
        try:
            ok = self.getCache('host_51ok')
            if ok:
                hosts.append(ok)
        except Exception:
            pass
        # 动态线路 + 静态兜底线路合并
        for u in self.FALLBACK_HOSTS:
            if u not in hosts:
                hosts.append(u)
        # 移动网动态解析全部失效，强制追加静态备用
        for u in self.STATIC_BACKUP_HOSTS:
            if u not in hosts:
                hosts.append(u)

        self.host = self.host_late(hosts) or self.STATIC_BACKUP_HOSTS[0]
        try:
            self.setCache('host_51ok', self.host)
        except Exception:
            pass
        self.headers.update({'Origin': self.host, 'Referer': f"{self.host}/"})
        self.session.headers.update(self.headers)
        thread = threading.Thread(target=self.getcnh)
        thread.daemon = True
        thread.start()

    def _candidates(self, current_host=None):
        cur = current_host if current_host is not None else self.host
        out = []
        for u in list(self.FALLBACK_HOSTS) + [self.domin] + self.STATIC_BACKUP_HOSTS:
            if u and u != cur and u not in out:
                out.append(u)
        return out

    def refresh_fallback_hosts(self):
        try:
            hosts = []
            gl = self.gethosts()
            if isinstance(gl, str):
                gl = [u.strip() for u in gl.split(',') if u.strip()]
            if gl:
                hosts.extend(gl)
            if not hosts:
                try:
                    hosts = self.get_domains()
                    self.log(f"JS线路回退: {hosts}")
                except Exception as e:
                    self.log(f"get_domains回退失败: {e}")
            fresh = [u for u in hosts if u]
            if fresh:
                merged = list(fresh)
                for u in self.STATIC_BACKUP_HOSTS:
                    if u not in merged:
                        merged.append(u)
                self.FALLBACK_HOSTS = merged
                self.log(f"FALLBACK_HOSTS已刷新: {self.FALLBACK_HOSTS}")
        except Exception as e:
            self.log(f"refresh_fallback_hosts异常: {e}, 使用静态备用线路")

    def switch_host(self, host):
        self.host = host
        self.headers.update({'Origin': host, 'Referer': f"{host}/"})
        self.session.headers.update(self.headers)
        try:
            self.setCache('host_51ok', host)
        except Exception:
            pass

    def log(self, *args):
        try:
            print(*args)
        except Exception:
            pass

    def pq(self, html):
        from lxml import html as lhtml
        return _PQ(lhtml.fromstring(html))

    def req(self, url, timeout=10, **kw):
        kw.setdefault('timeout', timeout)
        kw.setdefault('headers', self.headers)
        kw.setdefault('proxies', self.proxies)
        kw.setdefault('verify', False)
        try:
            return self.session.get(url, **kw)
        except (socket.timeout, ConnectionResetError, OSError) as e:
            self.log(f"请求被重置/超时 {url}, err:{e}")
            raise

    def getdoc(self, path_or_url):
        url = path_or_url if path_or_url.startswith('http') else f"{self.host}{path_or_url}"
        try:
            return self.pq(self.req(url).content)
        except Exception as e:
            self.log(f"请求失败换线: {e}")
        candidates = self._candidates()
        for h in candidates:
            try:
                nurl = path_or_url if path_or_url.startswith('http') else f"{h}{path_or_url}"
                doc = self.pq(self.req(nurl, timeout=7).content)
                self.switch_host(h)
                self.log(f"切换线路成功: {h}")
                return doc
            except Exception:
                continue
        raise Exception(f"所有线路均不可达: {path_or_url}")

    def getName(self):
        return '51吸瓜'

    def getDependence(self):
        return []

    def action(self, action):
        return {}

    def proxy(self, param):
        return self.localProxy(param)

    def isVideoFormat(self, url):
        if not url:
            return False
        u = str(url).lower()
        return '.m3u8' in u or '.mp4' in u or '.flv' in u or '.ts' in u

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def _parse_home(self, data):
        classes = []
        for k in list(data('.navbar-nav.mr-auto').children('li').items())[1:-3]:
            if k('ul'):
                for j in k('ul li').items():
                    classes.append({
                        'type_name': j('a').text(),
                        'type_id': j('a').attr('href').strip(),
                    })
            else:
                classes.append({
                    'type_name': k('a').text(),
                    'type_id': k('a').attr('href').strip(),
                })
        return classes

    def homeContent(self, filter):
        data = None
        classes = []
        lst = []
        try:
            data = self.getdoc('/')
            classes = self._parse_home(data)
            lst = self.getlist(data('#index article a'))
        except Exception:
            pass
        if not classes or not lst:
            for rnd in range(2):
                candidates = self._candidates()
                if rnd == 1:
                    self.log("空壳页首轮重试失败, 刷新FALLBACK_HOSTS后再试")
                    self.refresh_fallback_hosts()
                    candidates = [u for u in self._candidates() if u not in candidates]
                for h in candidates:
                    try:
                        nd = self.pq(self.req(f"{h}/", timeout=7).content)
                        nlst = self.getlist(nd('#index article a'))
                        ncls = self._parse_home(nd)
                        if ncls and nlst:
                            self.switch_host(h)
                            self.log(f"空壳页换线成功: {h}")
                            data, classes, lst = nd, ncls, nlst
                            break
                    except Exception:
                        continue
                if classes and lst:
                    break
        result = {}
        result['class'] = classes
        result['list'] = lst
        return result

    def homeVideoContent(self):
        try:
            data = self.getdoc('/')
            return {'list': self.getlist(data('#index article a'))[:30]}
        except Exception:
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        if '@folder' in tid:
            id = tid.replace('@folder', '')
            videos = self.getfod(id)
        else:
            pg = int(pg or '1')
            tid = str(tid).strip('/')
            videos = []
            try:
                videos = self.getlist(self.getdoc(f"/{tid}/" if pg == 1 else f"/{tid}/{pg}/"), f"/{tid}")
            except Exception:
                pass
            if not videos:
                for rnd in range(2):
                    candidates = self._candidates()
                    if rnd == 1:
                        self.log("分类页首轮重试失败, 刷新FALLBACK_HOSTS后再试")
                        self.refresh_fallback_hosts()
                        candidates = [u for u in self._candidates() if u not in candidates]
                    for h in candidates:
                        try:
                            nd = self.pq(self.req(f"{h}/{tid}/" if pg == 1 else f"{h}/{tid}/{pg}/", timeout=7).content)
                            nv = self.getlist(nd('#archive article a'), f"/{tid}")
                            if nv:
                                self.switch_host(h)
                                self.log(f"分类页换线成功: {h}")
                                videos = nv
                                break
                        except Exception:
                            continue
                    if videos:
                        break
        result = {}
        result['list'] = videos
        result['page'] = pg
        result['pagecount'] = 1 if '@folder' in tid else 99999
        result['limit'] = 90
        result['total'] = 999999
        return result

    def detailContent(self, ids):
        url = ids[0] if ids[0].startswith("http") else f"{self.host}{ids[0]}"
        data = self.getdoc(url)
        title = data('.post-title').text() or ''
        vod = {'vod_id': url, 'vod_name': title, 'vod_pic': '', 'vod_play_from': '51吸瓜'}
        did = data('script[data-api]').attr('data-api') or ''
        try:
            clist = []
            if data('.tags .keywords a'):
                for k in data('.tags .keywords a').items():
                    title = k.text()
                    href = k.attr('href')
                    clist.append('[a=cr:' + json.dumps({'id': href, 'name': title}) + '/]' + title + '[/a]')
            vod['vod_content'] = ' '.join(clist)
        except Exception:
            vod['vod_content'] = data('.post-title').text()
        try:
            plist = []
            if data('.dplayer'):
                for c, k in enumerate(data('.dplayer').items(), start=1):
                    config = json.loads(k.attr('data-config'))
                    plist.append(f"视频{c}${did}_dm_{config['video']['url']}")
            vod['vod_play_url'] = '#'.join(plist)
        except Exception:
            vod['vod_play_url'] = f"可能没有视频${url}"
        return {'list': [vod]}

    def searchContent(self, key, quick, pg="1"):
        data = self.getdoc(f"/search/{quote(key)}/")
        return {'list': self.getlist(data('#archive article a')), 'page': pg}

    def playerContent(self, flag, id, vipFlags):
        pid = id
        if '_dm_' in id:
            _, pid = id.split('_dm_', 1)
        return {'parse': 0, 'url': pid, 'header': self.headers}

    def localProxy(self, param):
        try:
            xtype = param.get('type', '')
            if 'm3u8' in xtype:
                path, url = unquote(param['pdid']).split('_dm_', 1)
                data = self.req(url, timeout=8).text
                lines = data.strip().split('\n')
                times = 0.0
                for i in lines:
                    if i.startswith('#EXTINF:'):
                        times += float(i.split(':')[-1].replace(',', ''))
                thread = threading.Thread(target=self.some_background_task, args=(path, int(times)))
                thread.daemon = True
                thread.start()
                print('[INFO] 获取视频时长成功', times)
                return [200, 'text/plain', data]
            elif 'xdm' in xtype:
                url = f"{self.host}{unquote(param['path'])}"
                res = self.req(url, timeout=8).json()
                dms = []
                for k in res:
                    text = k.get('text')
                    children = k.get('children')
                    if text: dms.append(text.strip())
                    if children:
                        for j in children:
                            ctext = j.get('text')
                            if ctext:
                                ctext = ctext.strip()
                                if "@" in ctext:
                                    dms.append(ctext.split(' ', 1)[-1].strip())
                                else:
                                    dms.append(ctext)
                return self.xml(dms, int(param['times']))
            url = self.d64(param['url'])
            match = re.search(r"loadBannerDirect\('([^']*)'", url)
            if match:
                url = match.group(1)
            res = self.req(url, timeout=8)
            return [200, res.headers.get('Content-Type'), self.aesimg(res.content)]
        except Exception as e:
            print(e)
            return [500, 'text/html', '']

    def some_background_task(self, path, times):
        try:
            time.sleep(1)
            purl = f"{self.getProxyUrl()}&path={quote(path)}&times={times}&type=xdm"
            self.fetch(f"http://127.0.0.1:9978/action?do=refresh&type=danmaku&path={quote(purl)}")
        except Exception as e:
            print(e)

    def xml(self, dms, times):
        try:
            tsrt = f'共有{len(dms)}条弹幕来袭！！！'
            danmustr = f'<?xml version="1.0" encoding="UTF-8"?>\n<i>\n\t<chatserver>chat.xtdm.com</chatserver>\n\t<chatid>88888888</chatid>\n\t<mission>0</mission>\n\t<maxlimit>99999</maxlimit>\n\t<state>0</state>\n\t<real_name>0</real_name>\n\t<source>k-v</source>\n'
            danmustr += f'\t<d p="0,5,25,16711680,0">{tsrt}</d>\n'
            for i in range(len(dms)):
                base_time = (i / len(dms)) * times
                dm0 = base_time + random.uniform(-3, 3)
                dm0 = round(max(0, min(dm0, times)), 1)
                dm2 = self.get_color()
                dm4 = re.sub(r'[<>&\u0000\b]', '', dms[i])
                tempdata = f'\t<d p="{dm0},1,25,{dm2},0">{dm4}</d>\n'
                danmustr += tempdata
            danmustr += '</i>'
            return [200, "text/xml", danmustr]
        except Exception as e:
            print(e)
            return [500, 'text/html', '']

    def get_color(self):
        if random.random() < 0.1:
            h = random.random()
            s = random.uniform(0.7, 1.0)
            v = random.uniform(0.8, 1.0)
            r, g, b = colorsys.hsv_to_rgb(h, s, v)
            r = int(r * 255)
            g = int(g * 255)
            b = int(b * 255)
            decimal_color = (r << 16) + (g << 8) + b
            return str(decimal_color)
        else:
            return '16777215'

    def e64(self, text):
        try:
            text_bytes = text.encode('utf-8')
            encoded_bytes = b64encode(text_bytes)
            return encoded_bytes.decode('utf-8')
        except Exception as e:
            print(f"Base64编码错误: {str(e)}")
            return ""

    def d64(self, encoded_text):
        try:
            encoded_bytes = encoded_text.encode('utf-8')
            decoded_bytes = b64decode(encoded_bytes)
            return decoded_bytes.decode('utf-8')
        except Exception as e:
            print(f"Base64解码错误: {str(e)}")
            return ""

    def gethosts(self):
        try:
            curl = self.getCache('host_51cn')
        except Exception:
            curl = ''
        if curl:
            try:
                data = self.pq(self.req(curl, timeout=7).content)('a').attr('href')
                if data:
                    parsed_url = urlparse(data)
                    return parsed_url.scheme + "://" + parsed_url.netloc
            except Exception:
                pass
        try:
            page = self.req(self.domin, timeout=7).text
            m = re.search(r'(?m)^\s*window\.appConfig\s*=\s*\{', page)
            if not m:
                raise Exception("未找到appConfig")
            seg = page[m.start():]
            datas = re.findall(r'(?m)^\s*data:\s*"([^"]+)"', seg)
            keys = re.findall(r'(?m)^\s*key:\s*"([^"]+)"', seg)
            if not datas:
                raise Exception("未找到appConfig.data")
            data_b64 = datas[-1]
            key_str = keys[-1] if keys else '0726001'
            raw = b64decode(data_b64)
            iv = raw[:16]
            ct = raw[16:]
            try:
                if SHA256 is not None:
                    key = SHA256.new(key_str.encode()).digest()
                else:
                    key = hashlib.sha256(key_str.encode()).digest()
            except Exception:
                key = b'\x42\x4b\xe2\x21\x31\x02\x4a\xbd\x0a\x7f\x2a\xff\xf6\xe8\x1c\xe9\x23\x0b\xfa\xa2\x59\xc9\x8f\x26\xdd\xda\xbb\x28\xdc\xa1\xa4\xe0'
            cipher = AES.new(key, AES.MODE_CBC, iv)
            text = unpad(cipher.decrypt(ct), AES.block_size).decode('utf-8')
            cfg = json.loads(text)
            hosts = []
            for d in cfg.get('domain', []):
                v = d.get('value', '')
                if v:
                    hosts.append(v.rstrip('/'))
            for d in cfg.get('backup_domain', []):
                v = d.get('value', '')
                if v:
                    hosts.append(v.rstrip('/'))
            if hosts:
                self.log(f"cg51线路: {hosts}")
                return hosts
            raise Exception("线路为空")
        except Exception as e:
            self.log(f"获取线路异常: {str(e)}")
            return ""

    def getcnh(self):
        try:
            if not self.host:
                return
            url = f"{self.host}/homeway.html"
            data = self.pq(self.req(url, timeout=7).content)
            a = data('.post-content[itemprop="articleBody"] blockquote p').eq(0)('a')
            href = a.attr('href')
            if href:
                parsed_url = urlparse(href)
                host = parsed_url.scheme + "://" + parsed_url.netloc
                if host:
                    try:
                        self.setCache('host_51cn', host)
                    except Exception:
                        pass
        except Exception as e:
            self.log(f"getcnh: {e}")

    def hstr(self, html):
        pattern = r"(backupLine\s*=\s*\[\])\s+(words\s*=)"
        replacement = r"\1, \2"
        html = re.sub(pattern, replacement, html)
        data = f"""
        var Vx = {{
            range: function(start, end) {{
                const result = [];
                for (let i = start; i < end; i++) {{
                    result.push(i);
                }}
                return result;
            }},
            map: function(array, callback) {{
                const result = [];
                for (let i = 0; i < array.length; i++) {{
                    result.push(callback(array[i], i));
                }}
                return result;
            }}
        }};
        Array.prototype.random = function() {{
            return this[Math.floor(Math.random() * this.length)];
        }};
        var location = {{
            protocol: "https:"
        }};
        function executeAndGetResults() {{
            var allLines = lineAry.concat(backupLine);
            var resultStr = JSON.stringify(allLines);
            return resultStr;
        }};
        {html}
        executeAndGetResults();
        """
        return self.p_qjs(data)

    def p_qjs(self, js_code):
        try:
            from com.whl.quickjs.wrapper import QuickJSContext
            ctx = QuickJSContext.create()
            result_json = ctx.evaluate(js_code)
            ctx.destroy()
            return json.loads(result_json)
        except Exception:
            pass
        try:
            return self.host_from_js(js_code)
        except Exception as e:
            self.log(f"线路解析失败: {e}")
            return []

    def host_from_js(self, js_code):
        words = re.search(r"words\s*=\s*'([^']+)'\s*\.split\(\s*',\s*'\s*\)", js_code)
        if not words:
            raise Exception("未找到words")
        words = words.group(1).split(',')
        if not words:
            raise Exception("words为空")
        domains = []
        for m in re.finditer(r"(?:lineAry|backupLine)\s*=\s*Vx\.map\(\s*Vx\.range\(\s*(\d+)\s*,\s*(\d+)\s*\)", js_code):
            seg = js_code[m.start():m.start()+400]
            sfx = re.search(r"words\.random\(\)\s*\+\s*'\.([^']+)'", seg)
            if not sfx:
                continue
            for _ in range(max(int(m.group(2))-int(m.group(1)), 0)):
                domains.append("https://" + random.choice(words) + "." + sfx.group(1))
        if not domains:
            raise Exception("未找到线路")
        return domains

    def get_domains(self):
        html = self.pq(self.req(self.domin, timeout=7).content)
        html_pattern = r"Base64\.decode\('([^']+)'\)"
        html_match = re.search(html_pattern, html('script').eq(-1).text(), re.DOTALL)
        if not html_match:
            raise Exception("未找到html")
        html = b64decode(html_match.group(1)).decode()
        words_pattern = r"words\s*=\s*'([^']+)'"
        words_match = re.search(words_pattern, html, re.DOTALL)
        if not words_match:
            raise Exception("未找到words")
        words = words_match.group(1).split(',')
        main_pattern = r"lineAry\s*=.*?words\.random\(\)\s*\+\s*'\.([^']+)'"
        domain_match = re.search(main_pattern, html, re.DOTALL)
        if not domain_match:
            raise Exception("未找到主域名")
        domain_suffix = domain_match.group(1)
        domains = []
        for _ in range(3):
            random_word = random.choice(words)
            domain = f"https://{random_word}.{domain_suffix}"
            domains.append(domain)
        return domains

    def getfod(self, id):
        url = f"{self.host}{id}"
        data = self.pq(self.req(url, timeout=8).content)
        vdata = data('.post-content[itemprop="articleBody"]')
        r = ['.txt-apps', '.line', 'blockquote', '.tags', '.content-tabs']
        for i in r: vdata.remove(i)
        h2s = [h.text() for h in vdata('h2').items()]
        ps = list(vdata('p').items())
        videos = []
        hi = 0
        for idx, p in enumerate(ps):
            a = p('a').attr('href')
            if not a:
                continue
            img = ''
            if idx+1 < len(ps):
                img = ps[idx+1]('img').attr('data-xkrkllgl') or ''
            name = (p.text() or '').strip()
            remarks = h2s[hi] if hi < len(h2s) else ''
            video = {
                'vod_id': a,
                'vod_name': name if name else remarks,
                'vod_pic': '',
                'vod_remarks': remarks
            }
            if img:
                video['vod_pic'] = f"{self.getProxyUrl()}&url={self.e64(img)}"
            videos.append(video)
            hi += 1
        return videos

    def host_late(self, url_list):
        if isinstance(url_list, str):
            urls = [u.strip() for u in url_list.split(',') if u.strip()]
        else:
            urls = list(url_list)
        if not urls:
            return ''
        if len(urls) <= 1:
            return urls[0]
        results = {}
        threads = []

        def test_host(url):
            try:
                start_time = time.time()
                response = self.req(url, timeout=2.8, allow_redirects=True)
                delay = (time.time() - start_time) * 1000
                if response.status_code == 200 and response.url:
                    results[url] = (delay, response.url)
                else:
                    results[url] = (float('inf'), url)
            except (socket.timeout, ConnectionResetError, OSError, Exception) as e:
                self.log(f"测速失败 {url}, {e}")
                results[url] = (float('inf'), url)

        for url in urls:
            t = threading.Thread(target=test_host, args=(url,))
            t.daemon = True
            threads.append(t)
            t.start()
        for t in threads:
            t.join(timeout=3.2)
        valid = {k: v for k, v in results.items() if v[0] != float('inf')}
        if valid:
            best = min(valid.items(), key=lambda x: x[1][0])
            final = best[1][1]
        else:
            # 全部测速失败，直接返回静态备用第一个
            self.log("测速全部超时，使用静态兜底域名")
            return self.STATIC_BACKUP_HOSTS[0]
        parsed = urlparse(final)
        return parsed.scheme + "://" + parsed.netloc

    def getlist(self, data, tid=''):
        videos = []
        l = '/mrdg' in tid
        for k in data.items():
            a = k.attr('href')
            b = k('h2').text()
            c = k('span[itemprop="datePublished"]').text()
            if a and b and c and a.startswith('/'):
                pic = k('script').text_raw()
                videos.append({
                    'vod_id': f"{a}{'@folder' if l else ''}",
                    'vod_name': b.replace('\n', ' '),
                    'vod_pic': f"{self.getProxyUrl()}&url={self.e64(pic)}&type=img" if pic else '',
                    'vod_remarks': c,
                    'vod_tag': 'folder' if l else '',
                    'style': {"type": "rect", "ratio": 1.33}
                })
        return videos

    def aesimg(self, word):
        key = b'f5d965df75336270'
        iv = b'97b60394abc2fbe1'
        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted = unpad(cipher.decrypt(word), AES.block_size)
        return decrypted


class _PQ:
    def __init__(self, nodes):
        if isinstance(nodes, _PQ):
            nodes = nodes._nodes
        self._nodes = list(nodes) if isinstance(nodes, (list, tuple)) else [nodes]

    def __call__(self, selector=None):
        if not selector:
            return self
        out = []
        for el in self._nodes:
            try:
                out.extend(el.cssselect(selector))
            except Exception:
                pass
        return _PQ(out)

    def __bool__(self):
        return len(self._nodes) > 0

    def __len__(self):
        return len(self._nodes)

    def __getitem__(self, i):
        return _PQ(self._nodes[i])

    def items(self):
        for el in self._nodes:
            yield _PQ(el)

    def eq(self, i):
        return _PQ(self._nodes[i] if -len(self._nodes) <= i < len(self._nodes) else [])

    def attr(self, name):
        if not self._nodes:
            return None
        v = self._nodes[0].get(name)
        return v

    def text(self):
        if not self._nodes:
            return ''
        parts = []
        for el in self._nodes:
            t = el.text_content().strip()
            if isinstance(el.tag, str) and el.tag in ('script', 'style'):
                continue
            parts.append(t)
        return '\n'.join(p for p in parts if p)

    def text_raw(self):
        if not self._nodes:
            return ''
        return '\n'.join(el.text_content() for el in self._nodes).strip()

    def children(self, selector=None):
        out = []
        for el in self._nodes:
            if hasattr(el, 'iterchildren'):
                out.extend(el.iterchildren())
        if selector:
            sel = _css_to_xpath_safe(selector)
            if sel:
                from lxml import etree as _e
                xp = _e.XPath(sel)
                out = [c for c in out if xp(c)]
        return _PQ(out)

    def remove(self, selectors):
        for sel in selectors.split(','):
            try:
                for el in self(sel)._nodes:
                    parent = el.getparent()
                    if parent is not None:
                        parent.remove(el)
            except Exception:
                pass


def _css_to_xpath_safe(selector):
    try:
        from cssselect import GenericTranslator
        return GenericTranslator().css_to_xpath(selector)
    except Exception:
        return None
