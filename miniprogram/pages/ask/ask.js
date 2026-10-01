// 律问 · 问答页
const api = require("../../utils/api");
const md = require("../../utils/md");

const FALLBACK_SUGGESTS = [
  "小区里被高空抛物砸伤，找谁赔偿？",
  "试用期被辞退有经济补偿吗？",
  "什么情况属于正当防卫？",
  "借钱不还的诉讼时效是几年？",
];

function cn2num(str) {
  if (/^\d+$/.test(str)) return parseInt(str, 10);
  const D = { 零: 0, 〇: 0, 一: 1, 二: 2, 两: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9 };
  const U = { 十: 10, 百: 100, 千: 1000, 万: 10000 };
  let total = 0, num = 0;
  for (const ch of str) {
    if (ch in D) num = D[ch];
    else if (ch in U) {
      if (!num) num = 1;
      if (U[ch] === 10000) total = (total + num) * 10000;
      else total += num * U[ch];
      num = 0;
    } else return null;
  }
  return total + num;
}

const shortLaw = (n) => (n || "").replace(/^中华人民共和国/, "");
const stripNo = (s) => (s || "").replace(/[^\u4e00-\u9fff0-9]/g, "");

Page({
  data: {
    messages: [],
    input: "",
    suggests: FALLBACK_SUGGESTS,
    asking: false,
    showHits: null,
    hitList: [],
    showLogin: false,
    pwd: "",
    loginErr: false,
    scrollTo: "",
  },

  onLoad(options) {
    api.request("/api/suggest")
      .then((d) => this.setData({ suggests: d.questions || FALLBACK_SUGGESTS }))
      .catch(() => {});
    if (options.q) this.ask(decodeURIComponent(options.q));
  },

  onInput(e) { this.setData({ input: e.detail.value }); },
  onSugTap(e) { this.ask(e.currentTarget.dataset.q); },

  onSend() {
    const q = this.data.input.trim();
    if (!q || this.data.asking) return;
    this.setData({ input: "" });
    this.ask(q);
  },

  ask(question) {
    if (this.data.asking) return;
    this._task && this._task.abort && this._task.abort();
    this._lastQuestion = question;
    const messages = this.data.messages.concat(
      { role: "user", text: question },
      { role: "assistant", text: "", hits: [], cites: [], done: false }
    );
    const ai = messages.length - 1;
    this.setData({ messages, asking: true, scrollTo: `m${ai}` });
    this._acc = "";
    this._lastFlush = 0;

    const patch = (fields) => {
      const upd = {};
      for (const [k, v] of Object.entries(fields)) upd[`messages[${ai}].${k}`] = v;
      this.setData(upd);
      this.setData({ scrollTo: `m${ai}` });
    };

    this._task = api.askStream(question, {
      onHits: (hits) => {
        const max = Math.max(...hits.map((h) => h.score || 0), 0.001);
        patch({
          hits: hits.map((h) => ({
            shortName: shortLaw(h.law_name),
            articleNo: h.article_no,
            dept: h.law_department,
            level: h.level,
            status: h.status,
            via: h.via,
            pct: Math.round(((h.score || 0) / max) * 100),
            text: h.article_text,
            law_name: h.law_name,
            article_no: h.article_no,
            flash: false,
          })),
          text: "已检索到法条，正在组织回答…",
        });
      },
      onDelta: (t) => {
        this._acc += t;
        const now = Date.now();
        if (now - this._lastFlush > 250) { this._lastFlush = now; patch({ text: this._acc }); }
      },
      onDone: () => {
        patch({
          text: this._acc,
          done: true,
          nodes: md.mdToNodes(this._acc || "（本次未返回内容）"),
          cites: md.extractCites(this._acc || ""),
        });
        this.setData({ asking: false });
      },
      onError: (err) => {
        if (err && err.code === 401) {
          this.setData({ asking: false, showLogin: true });
          patch({ text: "🔒 需要访问口令，请在弹窗中输入后自动重试", done: true,
                  nodes: md.mdToNodes("🔒 需要访问口令，请在弹窗中输入后自动重试"), cites: [] });
          return;
        }
        const msg = (err && err.message) || "出错了";
        const finalText = (this._acc || "") + `\n\n（${msg}）`;
        patch({ text: finalText, done: true, nodes: md.mdToNodes(finalText), cites: [] });
        this.setData({ asking: false });
      },
    });
  },

  openHits(e) {
    const mi = e.currentTarget.dataset.mi;
    this.setData({ showHits: mi, hitList: this.data.messages[mi].hits });
  },
  closeHits() { this.setData({ showHits: null }); },

  onCiteTap(e) {
    const { mi, ci } = e.currentTarget.dataset;
    const msg = this.data.messages[mi];
    const cite = msg.cites[ci];
    const hits = msg.hits || [];
    const target = cn2num(cite.no);
    const idx = hits.findIndex(
      (h) => shortLaw(h.law_name).includes(shortLaw(cite.law)) && cn2num(stripNo(h.article_no)) === target
    );
    if (idx < 0) { wx.showToast({ title: "该引用不在检索结果中", icon: "none" }); return; }
    const hitList = hits.map((h, i) => ({ ...h, flash: i === idx }));
    this.setData({ showHits: mi, hitList });
  },

  onPwd(e) { this.setData({ pwd: e.detail.value, loginErr: false }); },
  closeLogin() { this.setData({ showLogin: false }); },
  doLogin() {
    wx.request({
      url: api.baseUrl() + "/api/login",
      method: "POST",
      data: { password: this.data.pwd },
      success: (res) => {
        if (res.statusCode !== 200) { this.setData({ loginErr: true }); return; }
        getApp().globalData.token = res.data.token;
        wx.setStorageSync("lawq_token", res.data.token);
        this.setData({ showLogin: false, pwd: "" });
        wx.showToast({ title: "已登录", icon: "success" });
        // 登录成功后自动重试刚才的提问：移除失败的一问一答，重新发起
        const msgs = this.data.messages;
        const last = msgs[msgs.length - 1];
        if (last && last.role === "assistant" && this._lastQuestion &&
            (!last.done || (last.text || "").indexOf("口令") >= 0)) {
          this.setData({ messages: msgs.slice(0, -2) });
          setTimeout(() => this.ask(this._lastQuestion), 400);
        }
      },
      fail: () => this.setData({ loginErr: true }),
    });
  },

  onUnload() { this._task && this._task.abort && this._task.abort(); },
});
