// SPDX-License-Identifier: GPL-3.0-only
// TV-native catalogue + optional per-site JAR extension. No HTML required.
const HG_VERSION = '1.4.2-auto-device-20261027';
let hgOptions = {};
// Snapshot of the verified App category dictionary; shared with the standalone PY.
// Local metadata keeps categories visible even when the network is unavailable.
const hgMeta = {"tabs":[{"type_id":"discover","type_name":"发现"},{"type_id":"latest","type_name":"上新"},{"type_id":"drama","type_name":"真人剧"},{"type_id":"manju","type_name":"漫剧"},{"type_id":"ai","type_name":"AI剧"},{"type_id":"diagnostic","type_name":"运行检查"}],"filters":{"discover":[{"key":"kind","name":"类型","value":[{"v":"all","n":"全部"},{"v":"drama","n":"真人剧"},{"v":"manju","n":"漫剧"},{"v":"ai","n":"AI剧"}]},{"key":"board","name":"榜单","value":[{"v":"ranklist_hot_play_sc","n":"热播榜"},{"v":"ranklist_new_rank_sc","n":"新剧榜"},{"v":"ranklist_hot_search_sc","n":"热搜榜"},{"v":"ranklist_hot_sc","n":"推荐榜"},{"v":"ranklist_prestige","n":"臻果榜"},{"v":"ranklist_subscribe","n":"预约榜"},{"v":"ranklist_must_watch","n":"必看榜"},{"v":"ranklist_followed","n":"收藏榜"}]}],"latest":[{"key":"kind","name":"类型","value":[{"v":"drama","n":"真人剧"},{"v":"manju","n":"漫剧"},{"v":"ai","n":"AI剧"}]}],"drama":[{"key":"category_dim_theme","name":"主题","value":[{"v":"","n":"全部"},{"v":"cate_3","n":"现代言情"},{"v":"cate_19","n":"系统"},{"v":"cate_36","n":"重生"},{"v":"cate_37","n":"穿越"},{"v":"cate_43","n":"娱乐圈"},{"v":"cate_165","n":"悬疑推理"},{"v":"cate_261","n":"都市日常"},{"v":"cate_266","n":"马甲"},{"v":"cate_303","n":"喜剧"},{"v":"cate_316","n":"剧情"},{"v":"cate_382","n":"穿书"},{"v":"cate_395","n":"现言甜宠"},{"v":"cate_439","n":"古风言情"},{"v":"cate_466","n":"闪婚"},{"v":"cate_475","n":"破镜重圆"},{"v":"cate_598","n":"异能"},{"v":"cate_739","n":"逆袭"},{"v":"cate_842","n":"追妻"},{"v":"cate_1007","n":"传承觉醒"},{"v":"cate_1008","n":"虐恋"},{"v":"cate_1013","n":"玄幻仙侠"},{"v":"cate_1020","n":"奇幻爱情"},{"v":"cate_1022","n":"年代爱情"},{"v":"cate_1024","n":"家庭伦理"},{"v":"cate_1038","n":"战神归来"},{"v":"cate_1040","n":"亲情"},{"v":"cate_1041","n":"奇幻脑洞"},{"v":"cate_1043","n":"无敌神医"},{"v":"cate_1044","n":"赘婿逆袭"},{"v":"cate_1047","n":"古风权谋"},{"v":"cate_1048","n":"女性成长"},{"v":"cate_1050","n":"暗恋成真"},{"v":"cate_1051","n":"打脸虐渣"},{"v":"cate_1053","n":"豪门恩怨"}]},{"key":"category_dim_role","name":"设定","value":[{"v":"","n":"全部"},{"v":"cate_20","n":"神豪"},{"v":"cate_28","n":"萌宝"},{"v":"cate_84","n":"皇后"},{"v":"cate_85","n":"王妃"},{"v":"cate_94","n":"团宠"},{"v":"cate_378","n":"女帝"},{"v":"cate_387","n":"青梅竹马"},{"v":"cate_470","n":"替身"},{"v":"cate_737","n":"大叔"},{"v":"cate_760","n":"大女主"},{"v":"cate_844","n":"真假千金"},{"v":"cate_901","n":"龙王"},{"v":"cate_1010","n":"小人物"},{"v":"cate_1045","n":"强者回归"},{"v":"cate_1046","n":"天下无敌"},{"v":"cate_1049","n":"强强联合"},{"v":"cate_1052","n":"欢喜冤家"}]},{"key":"category_dim_epoch","name":"背景","value":[{"v":"","n":"全部"},{"v":"cate_4","n":"校园"},{"v":"cate_11","n":"乡村"},{"v":"cate_127","n":"职场"},{"v":"cate_273","n":"历史古代"},{"v":"cate_308","n":"古装"},{"v":"cate_390","n":"民国"}]},{"key":"sort","name":"推荐","value":[{"v":"","n":"默认"},{"v":"online_time","n":"最新上架"},{"v":"hot_score","n":"最高热度"},{"v":"hot_collect","n":"最高收藏"}]},{"key":"gender","name":"受众","value":[{"v":"","n":"全部"},{"v":"1","n":"男频"},{"v":"0","n":"女频"}]},{"key":"online_time","name":"时间","value":[{"v":"","n":"全部"},{"v":"days_7","n":"7天内上新"},{"v":"days_14","n":"14天内上新"},{"v":"days_30","n":"30天内上新"},{"v":"days_90","n":"90天内上新"}]}],"manju":[{"key":"category_dim_theme","name":"主题","value":[{"v":"","n":"全部"},{"v":"cate_3","n":"现代言情"},{"v":"cate_19","n":"系统"},{"v":"cate_36","n":"重生"},{"v":"cate_37","n":"穿越"},{"v":"cate_43","n":"娱乐圈"},{"v":"cate_165","n":"悬疑推理"},{"v":"cate_261","n":"都市日常"},{"v":"cate_266","n":"马甲"},{"v":"cate_303","n":"喜剧"},{"v":"cate_316","n":"剧情"},{"v":"cate_382","n":"穿书"},{"v":"cate_395","n":"现言甜宠"},{"v":"cate_439","n":"古风言情"},{"v":"cate_466","n":"闪婚"},{"v":"cate_475","n":"破镜重圆"},{"v":"cate_598","n":"异能"},{"v":"cate_739","n":"逆袭"},{"v":"cate_842","n":"追妻"},{"v":"cate_1007","n":"传承觉醒"},{"v":"cate_1008","n":"虐恋"},{"v":"cate_1013","n":"玄幻仙侠"},{"v":"cate_1020","n":"奇幻爱情"},{"v":"cate_1022","n":"年代爱情"},{"v":"cate_1024","n":"家庭伦理"},{"v":"cate_1038","n":"战神归来"},{"v":"cate_1040","n":"亲情"},{"v":"cate_1041","n":"奇幻脑洞"},{"v":"cate_1043","n":"无敌神医"},{"v":"cate_1044","n":"赘婿逆袭"},{"v":"cate_1047","n":"古风权谋"},{"v":"cate_1048","n":"女性成长"},{"v":"cate_1050","n":"暗恋成真"},{"v":"cate_1051","n":"打脸虐渣"},{"v":"cate_1053","n":"豪门恩怨"}]},{"key":"category_dim_role","name":"设定","value":[{"v":"","n":"全部"},{"v":"cate_20","n":"神豪"},{"v":"cate_28","n":"萌宝"},{"v":"cate_84","n":"皇后"},{"v":"cate_85","n":"王妃"},{"v":"cate_94","n":"团宠"},{"v":"cate_378","n":"女帝"},{"v":"cate_387","n":"青梅竹马"},{"v":"cate_470","n":"替身"},{"v":"cate_737","n":"大叔"},{"v":"cate_760","n":"大女主"},{"v":"cate_844","n":"真假千金"},{"v":"cate_901","n":"龙王"},{"v":"cate_1010","n":"小人物"},{"v":"cate_1045","n":"强者回归"},{"v":"cate_1046","n":"天下无敌"},{"v":"cate_1049","n":"强强联合"},{"v":"cate_1052","n":"欢喜冤家"}]},{"key":"category_dim_epoch","name":"背景","value":[{"v":"","n":"全部"},{"v":"cate_4","n":"校园"},{"v":"cate_11","n":"乡村"},{"v":"cate_127","n":"职场"},{"v":"cate_273","n":"历史古代"},{"v":"cate_308","n":"古装"},{"v":"cate_390","n":"民国"}]},{"key":"sort","name":"推荐","value":[{"v":"","n":"默认"},{"v":"online_time","n":"最新上架"},{"v":"hot_score","n":"最高热度"},{"v":"hot_collect","n":"最高收藏"}]},{"key":"gender","name":"受众","value":[{"v":"","n":"全部"},{"v":"1","n":"男频"},{"v":"0","n":"女频"}]},{"key":"online_time","name":"时间","value":[{"v":"","n":"全部"},{"v":"days_7","n":"7天内上新"},{"v":"days_14","n":"14天内上新"},{"v":"days_30","n":"30天内上新"},{"v":"days_90","n":"90天内上新"}]}],"ai":[{"key":"category_dim_theme","name":"主题","value":[{"v":"","n":"全部"},{"v":"cate_3","n":"现代言情"},{"v":"cate_19","n":"系统"},{"v":"cate_36","n":"重生"},{"v":"cate_37","n":"穿越"},{"v":"cate_43","n":"娱乐圈"},{"v":"cate_165","n":"悬疑推理"},{"v":"cate_261","n":"都市日常"},{"v":"cate_266","n":"马甲"},{"v":"cate_303","n":"喜剧"},{"v":"cate_316","n":"剧情"},{"v":"cate_382","n":"穿书"},{"v":"cate_395","n":"现言甜宠"},{"v":"cate_439","n":"古风言情"},{"v":"cate_466","n":"闪婚"},{"v":"cate_475","n":"破镜重圆"},{"v":"cate_598","n":"异能"},{"v":"cate_739","n":"逆袭"},{"v":"cate_842","n":"追妻"},{"v":"cate_1007","n":"传承觉醒"},{"v":"cate_1008","n":"虐恋"},{"v":"cate_1013","n":"玄幻仙侠"},{"v":"cate_1020","n":"奇幻爱情"},{"v":"cate_1022","n":"年代爱情"},{"v":"cate_1024","n":"家庭伦理"},{"v":"cate_1038","n":"战神归来"},{"v":"cate_1040","n":"亲情"},{"v":"cate_1041","n":"奇幻脑洞"},{"v":"cate_1043","n":"无敌神医"},{"v":"cate_1044","n":"赘婿逆袭"},{"v":"cate_1047","n":"古风权谋"},{"v":"cate_1048","n":"女性成长"},{"v":"cate_1050","n":"暗恋成真"},{"v":"cate_1051","n":"打脸虐渣"},{"v":"cate_1053","n":"豪门恩怨"}]},{"key":"category_dim_role","name":"设定","value":[{"v":"","n":"全部"},{"v":"cate_20","n":"神豪"},{"v":"cate_28","n":"萌宝"},{"v":"cate_84","n":"皇后"},{"v":"cate_85","n":"王妃"},{"v":"cate_94","n":"团宠"},{"v":"cate_378","n":"女帝"},{"v":"cate_387","n":"青梅竹马"},{"v":"cate_470","n":"替身"},{"v":"cate_737","n":"大叔"},{"v":"cate_760","n":"大女主"},{"v":"cate_844","n":"真假千金"},{"v":"cate_901","n":"龙王"},{"v":"cate_1010","n":"小人物"},{"v":"cate_1045","n":"强者回归"},{"v":"cate_1046","n":"天下无敌"},{"v":"cate_1049","n":"强强联合"},{"v":"cate_1052","n":"欢喜冤家"}]},{"key":"category_dim_epoch","name":"背景","value":[{"v":"","n":"全部"},{"v":"cate_4","n":"校园"},{"v":"cate_11","n":"乡村"},{"v":"cate_127","n":"职场"},{"v":"cate_273","n":"历史古代"},{"v":"cate_308","n":"古装"},{"v":"cate_390","n":"民国"}]},{"key":"sort","name":"推荐","value":[{"v":"","n":"默认"},{"v":"online_time","n":"最新上架"},{"v":"hot_score","n":"最高热度"},{"v":"hot_collect","n":"最高收藏"}]},{"key":"gender","name":"受众","value":[{"v":"","n":"全部"},{"v":"1","n":"男频"},{"v":"0","n":"女频"}]},{"key":"online_time","name":"时间","value":[{"v":"","n":"全部"},{"v":"days_7","n":"7天内上新"},{"v":"days_14","n":"14天内上新"},{"v":"days_30","n":"30天内上新"},{"v":"days_90","n":"90天内上新"}]}]}};
function hgObject(value) {
  if (typeof value === 'string') { try { value = JSON.parse(value); } catch (_) { return {}; } }
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
}
function hgRequest(method, args) {
  if (typeof globalThis.hongguoNative !== 'function') {
    throw { stage: 'js-jar', code: 'JAR_NOT_LOADED', error: '红果 JAR 未加载，请检查此站点的 jar 完整网址，然后强制停止影音TV再打开' };
  }
  const response = hgObject(globalThis.hongguoNative(JSON.stringify({method: method, args: args || [], options: hgOptions})));
  if (response.ok !== true) throw response;
  if(response.contract!=='hg-tv-app-142')throw {stage:'js-jar',code:'JAR_VERSION_MISMATCH'};
  if (!response.data || typeof response.data !== 'object') throw {stage: method, code: 'BAD_RESULT'};
  return response.data;
}
function hgError(error) {
  const e = error && typeof error === 'object' ? error : {};
  const stage = String(e.stage || 'js').replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 48);
  const code = String(e.code || 'FAILED').replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 48);
  // Never display arbitrary exception messages or signed addresses.
  const message = code === 'ENGINE_RESTART_REQUIRED' ? '请强行停止影音TV后重开，以退出旧的播放内核' : code === 'APP_CONTEXT_INVALID' ? '设备初始化未完成，请退出站点后重新打开' : code === 'JAR_VERSION_MISMATCH' ? '请同时替换红果 JS 和 v142 JAR，并强行停止影音TV后重开' : code === 'JAR_NOT_LOADED' ? '红果 JAR 未加载：请检查站点 jar 的完整网址，并重启影音TV' : '红果暂未返回内容，请检查网络、可用存储空间或重启影音TV';
  return '[' + stage + '/' + code + '] ' + message;
}
function hgFailure(error, page) {
  return {list: [{vod_id: 'hg-diagnostic', vod_name: hgError(error), vod_pic: '', vod_remarks: '选择查看配置说明'}], page: Number(page) || 1, pagecount: Number(page) || 1, limit: 1, total: 1};
}
function hgDiagnostic() {
  let text = 'JS 版本：' + HG_VERSION + '\n';
  try {
    const status = hgRequest('diagnostic', []);
    text += 'JAR 与 App 内置 Python 已连接，仅使用官方 App 播放取源。\n内核：' + String(status.repairVersion || '') + '\n';
    if (!status.catalogueVersion) text += '发现与剧库需要配套 v1.4.2 JAR，请同时更新 JS 和 JAR。\n';
    const cached = status.cachedPython || {};
    if (cached.exists && cached.html) text += '原 Python 缓存是 HTML 页面：请检查脚本下载地址及服务器防护规则。\n';
  } catch (error) { text += hgError(error) + '\n'; }
  text += '本配置应包含 api（JS网址）和 jar（本包JAR网址）。建议均填写完整 HTTP/HTTPS 地址。\n不要替换配置顶层的 spider；不要添加 homePage。修改后强制停止影音TV并重新打开。\n本版使用 App 自带的 Python 3.10 和 AES；无需外部服务或账号信息。';
  return {list: [{vod_id: 'hg-diagnostic', vod_name: '红果运行检查', vod_pic: '', vod_content: text, vod_remarks: HG_VERSION, vod_play_from: '', vod_play_url: ''}]};
}
async function init(cfg) {
  const root = hgObject(cfg);
  hgOptions = hgObject(Object.prototype.hasOwnProperty.call(root, 'ext') ? root.ext : root);
}
async function home(filter) {
  const result = {class: hgMeta.tabs};
  if (filter) result.filters = hgMeta.filters;
  return JSON.stringify(result);
}
async function homeVod() {
  try { return JSON.stringify(hgRequest('homeVod', [])); } catch (error) { return JSON.stringify(hgFailure(error, 1)); }
}
async function category(tid, pg, filter, extend) {
  if (tid === 'diagnostic') return JSON.stringify({list: [{vod_id: 'hg-diagnostic', vod_name: '检查红果运行环境', vod_pic: '', vod_remarks: HG_VERSION}], page: 1, pagecount: 1, limit: 1, total: 1});
  try { return JSON.stringify(hgRequest('category', [String(tid), String(pg || '1'), !!filter, hgObject(extend)])); }
  catch (error) { return JSON.stringify(hgFailure(error, pg)); }
}
async function detail(id) {
  if (id === 'hg-diagnostic') return JSON.stringify(hgDiagnostic());
  try { return JSON.stringify(hgRequest('detail', [String(id)])); }
  catch (error) { const result = hgDiagnostic(); result.list[0].vod_content = hgError(error) + '\n' + result.list[0].vod_content; return JSON.stringify(result); }
}
async function search(key, quick, pg) {
  try { return JSON.stringify(hgRequest('search', [String(key), !!quick, String(pg || '1')])); }
  catch (error) { return JSON.stringify(hgFailure(error, pg)); }
}
async function play(flag, id, vipFlags) {
  try { return JSON.stringify(hgRequest('play', [String(flag || ''), String(id)])); }
  catch (error) { throw new Error(hgError(error)); }
}
async function action() { return JSON.stringify(hgDiagnostic()); }
async function destroy() { /* The shared local media server belongs to the host process. */ }
async function live() { return ''; }
async function proxy() { return [404, 'text/plain', 'Not found']; }
function isVideo(url) { return /^https?:\/\/127\.0\.0\.1:\d+\/play\//.test(String(url)); }
function sniffer() { return false; }
export function __jsEvalReturn() { return {init, home, homeVod, category, detail, search, play, action, destroy, live, proxy, isVideo, sniffer}; }
