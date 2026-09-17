// 本资源来源于互联网公开渠道，仅可用于个人学习爬虫技术。
// 严禁将其用于任何商业用途，下载后请于 24 小时内删除，搜索结果均来自源站，本人不承担任何责任。

import {
    Crypto,
    _
} from 'assets://js/lib/cat.js';

let host = 'https://ds3xy2yunsa.xyz';
let device_id = '';
const pkg = 'com.tvcloud.io';
const device_id_cache_key = 'com.sunshine.tv_3qys_B7k7Dt56Rn';

async function init(cfg) {
    if (typeof cfg.ext === 'string' && cfg.ext.startsWith('http')) {
        host = cfg.ext.trim().replace(/\/$/, '');
    }
}

async function home(filter) {
    const hd = await getHeaders();
    const resp = await req(`${host}/api.php/app/index/home`, {
        headers: hd
    });
    const json = JSON.parse(resp.content);
    const classes = _.map(json.data.categories, (i) => ({
        type_id: i.type_name,
        type_name: i.type_name
    }));
    const videos = [];
    for (const cat of json.data.categories) {
        videos.push(...arr2vods(cat.videos));
    }
  
  	const filterObj = {
        "电影": [
            {
                key: "class",
                name: "类型",
                value: [
                    { n: "全部", v: "" },
                    { n: "动作", v: "动作" },
                    { n: "喜剧", v: "喜剧" },
                    { n: "爱情", v: "爱情" },
                    { n: "科幻", v: "科幻" },
                    { n: "恐怖", v: "恐怖" },
                    { n: "悬疑", v: "悬疑" },
                    { n: "犯罪", v: "犯罪" },
                    { n: "战争", v: "战争" },
                    { n: "动画", v: "动画" },
                    { n: "冒险", v: "冒险" },
                    { n: "历史", v: "历史" },
                    { n: "灾难", v: "灾难" },
                    { n: "纪录", v: "纪录" },
                    { n: "剧情", v: "剧情" }
                ]
            },
            {
                key: "area",
                name: "地区",
                value: [
                    { n: "全部", v: "" },
                    { n: "大陆", v: "大陆" },
                    { n: "香港", v: "香港" },
                    { n: "台湾", v: "台湾" },
                    { n: "美国", v: "美国" },
                    { n: "日本", v: "日本" },
                    { n: "韩国", v: "韩国" },
                    { n: "泰国", v: "泰国" },
                    { n: "印度", v: "印度" },
                    { n: "英国", v: "英国" },
                    { n: "法国", v: "法国" },
                    { n: "德国", v: "德国" },
                    { n: "加拿大", v: "加拿大" },
                    { n: "西班牙", v: "西班牙" },
                    { n: "意大利", v: "意大利" },
                    { n: "澳大利亚", v: "澳大利亚" }
                ]
            },
            {
                key: "year",
                name: "年份",
                value: [
                    { n: "全部", v: "" },
                    { n: "2026", v: "2026" },
                    { n: "2025", v: "2025" },
                    { n: "2024", v: "2024" },
                    { n: "2023", v: "2023" },
                    { n: "2022", v: "2022" },
                    { n: "2021", v: "2021" },
                    { n: "2020", v: "2020" },
                    { n: "2019", v: "2019" },
                    { n: "2018", v: "2018" },
                    { n: "2017", v: "2017" },
                    { n: "2016", v: "2016" },
                    { n: "2015-2011", v: "2015-2011" },
                    { n: "2010-2000", v: "2010-2000" },
                    { n: "90年代", v: "90年代" },
                    { n: "80年代", v: "80年代" },
                    { n: "更早", v: "更早" }
                ]
            },
            {
                key: "sort",
                name: "排序",
                value: [
                    { n: "人气", v: "hits" },
                    { n: "最新", v: "time" },
                    { n: "评分", v: "score" },
                    { n: "年份", v: "year" }
                ]
            }
        ],

        "剧集": [
            {
                key: "class",
                name: "类型",
                value: [
                    { n: "全部", v: "" },
                    { n: "爱情", v: "爱情" },
                  	{ n: "古装", v: "古装" },
                    { n: "武侠", v: "武侠" },
                    { n: "历史", v: "历史" },
                    { n: "家庭", v: "家庭" },                    
                    { n: "喜剧", v: "喜剧" },               
                    { n: "悬疑", v: "悬疑" },
                    { n: "犯罪", v: "犯罪" },
                    { n: "战争", v: "战争" },
                  	{ n: "奇幻", v: "奇幻" },
                    { n: "科幻", v: "科幻" },
                    { n: "恐怖", v: "恐怖" }
                ]
            },
            {
                key: "area",
                name: "地区",
                value: [
                    { n: "全部", v: "" },
                    { n: "大陆", v: "大陆" },
                    { n: "香港", v: "香港" },
                  	{ n: "台湾", v: "台湾" },
                    { n: "美国", v: "美国" },
                  	{ n: "日本", v: "日本" },
                    { n: "韩国", v: "韩国" },                   
                    { n: "泰国", v: "泰国" },
                    { n: "英国", v: "英国" }
                ]
            },
            {
                key: "year",
                name: "年份",
                value: [
                    { n: "全部", v: "" },
                    { n: "2026", v: "2026" },
                    { n: "2025", v: "2025" },
                    { n: "2024", v: "2024" },
                    { n: "2023", v: "2023" },
                    { n: "2022", v: "2022" },
                    { n: "2021", v: "2021" },
                    { n: "2020-2016", v: "2020-2016" },
                    { n: "2015-2011", v: "2015-2011" },
                    { n: "2010-2000", v: "2010-2000" },
                    { n: "更早", v: "更早" }
                ]
            },
            {
                key: "sort",
                name: "排序",
                value: [
                    { n: "人气", v: "hits" },
                    { n: "最新", v: "time" },
                    { n: "评分", v: "score" },
                    { n: "年份", v: "year" }
                ]
            }
        ],

        "动漫": [
            {
                key: "class",
                name: "类型",
                value: [
                    { n: "全部", v: "" },
                    { n: "冒险", v: "冒险" },
                    { n: "奇幻", v: "奇幻" },                   
                  	{ n: "科幻", v: "科幻" },
          			{ n: "武侠", v: "武侠" },
                  	{ n: "悬疑", v: "悬疑" }
                ]
            },
            {
                key: "area",
                name: "地区",
                value: [
                    { n: "大陆", v: "大陆" },
                    { n: "日本", v: "日本" },
                    { n: "欧美", v: "欧美" }
                ]
            },
            {
                key: "year",
                name: "年份",
                value: [
                    { n: "全部", v: "" },
                    { n: "2026", v: "2026" },
                    { n: "2025", v: "2025" },
                    { n: "2024", v: "2024" },
                    { n: "2023", v: "2023" },
                    { n: "2022", v: "2022" },
                    { n: "2021", v: "2021" },
                    { n: "2020", v: "2020" },
                    { n: "2019", v: "2019" },
                    { n: "2018", v: "2018" },
                    { n: "2017", v: "2017" },
                    { n: "2016", v: "2016" },
                    { n: "2015", v: "2015" },
                    { n: "2014", v: "2014" },
                    { n: "2013", v: "2013" },
                    { n: "2012", v: "2012" },
                    { n: "2011", v: "2011" },
                    { n: "更早", v: "更早" }
                ]
            },
            {
                key: "sort",
                name: "排序",
                value: [
                    { n: "人气", v: "hits" },
                    { n: "最新", v: "time" },
                    { n: "评分", v: "score" },
                    { n: "年份", v: "year" }
                ]
            }
        ],

        "综艺": [
            {
                key: "class",
                name: "类型",
                value: [
                    { n: "全部", v: "" },
                    { n: "真人秀", v: "真人秀" },
                    { n: "音乐", v: "音乐" },
                    { n: "脱口秀", v: "脱口秀" },
                    { n: "歌舞", v: "歌舞" },
                    { n: "爱情", v: "爱情" }
                ]
            },
          	{
                key: "area",
                name: "地区",
                value: [
                    { n: "全部", v: "" },
                    { n: "大陆", v: "大陆" },
                    { n: "香港", v: "香港" },
                  	{ n: "台湾", v: "台湾" },
                    { n: "美国", v: "美国" },
                  	{ n: "日本", v: "日本" },
                    { n: "韩国", v: "韩国" }
                ]
            },
            {
                key: "year",
                name: "年份",
                value: [
                    { n: "全部", v: "" },
                    { n: "2026", v: "2026" },
                    { n: "2025", v: "2025" },
                    { n: "2024", v: "2024" },
                    { n: "2023", v: "2023" },
                    { n: "2022", v: "2022" },
                    { n: "2021", v: "2021" },
                    { n: "2020", v: "2020" },
                    { n: "2019", v: "2019" },
                    { n: "2018", v: "2018" },
                    { n: "2017", v: "2017" },
                    { n: "2016", v: "2016" },
                    { n: "2015", v: "2015" },
                    { n: "2014", v: "2014" },
                    { n: "2013", v: "2013" },
                    { n: "2012", v: "2012" },
                    { n: "2011", v: "2011" },
                    { n: "更早", v: "更早" }
                ]
            },
            {
                key: "sort",
                name: "排序",
                value: [
                    { n: "人气", v: "hits" },
                    { n: "最新", v: "time" },
                    { n: "评分", v: "score" },
                    { n: "年份", v: "year" }
                ]
            }
        ]
    };
  
    return JSON.stringify({
        class: classes,
      	filters: filterObj,
        list: videos
    });
}

async function homeVod() {
    return JSON.stringify({
        list: []
    });
}

async function category(tid, pg, filter, extend) {
    const hd = await getHeaders();
    
    // 基础参数
    let params = `type_name=${encodeURIComponent(tid)}&page=${pg}`;
    
    // 从 extend 中提取筛选参数
    if (extend && typeof extend === 'object') {
        // 排序（默认 hits）
        const sort = extend.sort || 'hits';
        params += `&sort=${encodeURIComponent(sort)}`;
        
        // 类型筛选
        if (extend.class) {
            params += `&class=${encodeURIComponent(extend.class)}`;
        }
        
        // 地区筛选
        if (extend.area) {
            params += `&area=${encodeURIComponent(extend.area)}`;
        }
        
        // 年份筛选
        if (extend.year) {
            params += `&year=${encodeURIComponent(extend.year)}`;
        }
    } else {
        // 无筛选时默认按人气排序
        params += `&sort=hits`;
    }
    
    const resp = await req(`${host}/api.php/app/filter/vod?${params}`, {
        headers: hd
    });
    const json = JSON.parse(resp.content);
    return JSON.stringify({
        list: arr2vods(json.data || []),
        page: parseInt(pg),
        pagecount: json.totalpage || 999,
        limit: 20,
        total: (json.totalpage || 999) * 20
    });
}

async function search(wd, quick, pg = 1) {
    const hd = await getHeaders();
    const resp = await req(`${host}/api.php/app/search/index?wd=${encodeURIComponent(wd)}&page=${pg}&limit=15`, {
        headers: hd
    });
    const json = JSON.parse(resp.content);
    return JSON.stringify({
        list: arr2vods(json.data),
        pagecount: json.pageCount,
        page: parseInt(pg)
    });
}

async function detail(id) {
    const hd = await getHeaders();
    const resp = await req(`${host}/api.php/app/vod/get_detail?vod_id=${id}`, {
        headers: hd
    });
    const json = JSON.parse(resp.content);
    const data = json.data[0];
    const players = json.vodplayer || [];

    const fromList = data.vod_play_from ? data.vod_play_from.split('$$$') : [];
    const urlList = data.vod_play_url ? data.vod_play_url.split('$$$') : [];

    // 1. 先收集所有播放源信息到一个临时数组
    const sourceList = [];

    for (let i = 0; i < fromList.length; i++) {
        const code = fromList[i];
        const urlsStr = urlList[i] || '';
        const info = _.find(players, (p) => p.from === code);
        if (!info || !urlsStr) continue;

        const needParse = info.decode_status || '0';
        const mode = info.decode_mode || 'server';
        const parseUrl = info.parse_url || '';
        const showName = info.show || code;
        const name = showName.toLowerCase() === code.toLowerCase() ? showName : `${showName} (${code})`;
        const vodFrom = (mode === 'client' && parseUrl) ? showName : code;

        const items = urlsStr.split('#');
        const urls = [];
        for (const item of items) {
            if (!item.includes('$')) continue;
            const idx = item.indexOf('$');
            const ep = item.substring(0, idx);
            const url = item.substring(idx + 1);
            if (ep && url) {
                urls.push(`${ep}$${code}@${needParse}@${mode}@${parseUrl}@${vodFrom}@${url}`);
            }
        }
        if (urls.length) {
            // 存入对象，保留 name 和 urls 组装后的字符串
            sourceList.push({
                name: name,
                urls: urls.join('#')
            });
        }
    }

    // 2. 按优先级排序：4K > 2K > 其他
    const getPriority = (str) => {
        if (str.includes('4K')) return 0;
        if (str.includes('IM')) return 1;
        return 2;
    };
    sourceList.sort((a, b) => {
        const pa = getPriority(a.name);
        const pb = getPriority(b.name);
        if (pa !== pb) return pa - pb;
        // 同优先级可保持原顺序（或按名称字典序，视需求）
        return 0;
    });

    // 3. 重新生成 shows 和 play_urls
    const shows = sourceList.map(item => item.name);
    const play_urls = sourceList.map(item => item.urls);

    return JSON.stringify({
        list: [{
            vod_id: data.vod_id.toString(),
            vod_name: data.vod_name,
            vod_pic: data.vod_pic,
            vod_remarks: data.vod_remarks,
            vod_year: data.vod_year,
            vod_area: data.vod_area,
            vod_actor: data.vod_actor,
            vod_director: data.vod_director,
            vod_content: data.vod_content,
            vod_play_from: shows.join('$$$'),
            vod_play_url: play_urls.join('$$$'),
            type_name: data.vod_class
        }]
    });
}

async function play(flag, vid, flags) {
    const parts = vid.split('@');
    const needParse = parts[1] || '0';
    const mode = parts[2] || 'server';
    const parseUrl = parts[3] || '';
    const vodFrom = parts[4] || (parts[0].includes('$') ? parts[0].split('$')[1] : flag);
    const rawUrl = parts.slice(5).join('@');
    let url = '';
    let jx = 0;

    if (needParse === '1') {
        try {
            const hd = await getHeaders();
            if (mode === 'client' && parseUrl) {
                const resp = await req(parseUrl.replace(/\{url\}/g, encodeURIComponent(rawUrl)), {
                    headers: hd,
                    timeout: 30000
                });
                const json = JSON.parse(resp.content);
                url = (json.code === 1 && json.data?.startsWith('http')) ? json.data :
                    (json.url?.startsWith('http') ? json.url : '');
                if (!url && resp.content.trim().startsWith('http')) url = resp.content.trim();
            } else {
                const resp = await req(`${host}/api.php/app/decode/url/?url=${encodeURIComponent(rawUrl)}&vodFrom=${encodeURIComponent(vodFrom)}&_t=${Date.now()}`, {
                    headers: hd,
                    timeout: 30000
                });
                console.log(resp)
                const json = JSON.parse(resp.content);
                if (json.code === 1 && json.data?.startsWith('http')) url = json.data;
            }
        } catch (e) {
            console.error('Play decode error:', e);
        }
    }

    url = url || rawUrl;
    if (/\.(mp4|m3u8)($|\?)/.test(url)) jx = 0;
    if (/(www\.iqiyi|v\.qq|v\.youku|www\.mgtv|www\.bilibili)\.com/.test(url)) jx = 1;

    return JSON.stringify({
        jx: jx,
        parse: 0,
        url: url,
        header: {
            'User-Agent': 'com.sunshine.tv/1.2.0 (Linux;Android 15) AndroidXMedia3/1.4.1'
        }
    });
}
async function getHeaders() {
    const timestamp = Date.now().toString();
 
    if (!device_id) {
        device_id = await local.get('cache', device_id_cache_key);
        if (!device_id || device_id.length !== 16) {
            device_id = randomStr(16);
            await local.set('cache', device_id_cache_key, device_id);
        }
    }

    const hash = Crypto.SHA256(device_id).toString().toUpperCase();
 
    const hashPrefix = hash.substring(0, 8);

    let randomDigits = '';
    for (let i = 0; i < 8; i++) {
        randomDigits += Math.floor(Math.random() * 10);
    }
  
    const nonce = hashPrefix + randomDigits;
 
    const sign = sha256(`finger=SF-F5F11CB15897115AE6BCFE063C288F730CA865588F572C780A3E8477D0DD3776&id=${pkg}&nonce=${nonce}&sk=SK-sk_13oXDZ7u9j2Tk1c0cawWVFfO&time=${timestamp}&v=9`);
    return {        
        'x-aid': pkg,
        'x-ave': '9',
        'x-time': timestamp,
        'x-nonc': nonce,
        'x-sign': sign,
        'Accept': 'application/json',
        'x-device-id': device_id,
        'x-device-brand': 'realme',
        'x-device-model': 'RMX5200',
        'x-update-id': 'aaf44685-971c-413e-9131-1b5076594826',
        'User-Agent': 'okhttp/4.12.0'
    };
}

function arr2vods(arr) {
    return _.map(arr, (i) => {
        const type = i.type_name || '';
        return {
            vod_id: i.vod_id.toString(),
            vod_name: i.vod_name,
            vod_pic: i.vod_pic,
            vod_remarks: i.vod_remarks,
            type_name: type + (i.vod_class ? (type ? ',' : '') + i.vod_class : ''),
            vod_year: i.vod_year
        };
    });
}

function randomStr(len, chars = '0A1AD8F189470636') {
    let str = '';
    for (let i = 0; i < len; i++) {
        str += chars[_.random(0, chars.length - 1)];
    }
    return str;
}

function sha256(text) {
    return Crypto.SHA256(text).toString().toUpperCase();
}

export function __jsEvalReturn() {
    return {
        init,
        home,
        homeVod,
        category,
        search,
        detail,
        play
    };
}