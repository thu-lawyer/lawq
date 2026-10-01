// 律问 · 法条库页
const api = require("../../utils/api");

const shortLaw = (n) => (n || "").replace(/^中华人民共和国/, "");

Page({
  data: {
    depts: [],
    curDept: "",
    q: "",
    searchMode: false,
    laws: [],
    results: [],
    headNote: "",
    openLawId: "",
    openLawName: "",
    articles: [],
  },

  onLoad() {
    this.initDepts();
    this.loadLaws();
  },

  async initDepts() {
    try {
      const s = await api.request("/api/stats");
      this.setData({ depts: s.departments || [] });
    } catch (e) { this.onError(e); }
  },

  onError(e) {
    wx.showToast({ title: (e && e.message) || "请求失败", icon: "none" });
  },

  onDept(e) {
    this.setData({ curDept: e.currentTarget.dataset.d, searchMode: false, q: "" });
    this.loadLaws();
  },

  onSearch(e) {
    const q = e.detail.value.trim();
    this.setData({ q, searchMode: !!q });
    clearTimeout(this._t);
    this._t = setTimeout(() => (q ? this.doSearch(q) : this.loadLaws()), 400);
  },

  async loadLaws() {
    try {
      const d = await api.request(
        `/api/laws?department=${encodeURIComponent(this.data.curDept)}`
      );
      this.setData({ laws: d.laws || [], headNote: `共 ${d.laws.length} 部` });
    } catch (e) { this.onError(e); }
  },

  async doSearch(q) {
    try {
      const d = await api.request(`/api/search?q=${encodeURIComponent(q)}`);
      const results = (d.articles || []).map((a) => ({
        id: a.id,
        shortName: shortLaw(a.law_name),
        articleNo: a.article_no,
        status: a.status,
        text: a.article_text,
      }));
      this.setData({ results, headNote: `「${q}」前 ${results.length} 条` });
    } catch (e) { this.onError(e); }
  },

  async openLaw(e) {
    const { id, name } = e.currentTarget.dataset;
    wx.showLoading({ title: "加载中" });
    try {
      const d = await api.request(`/api/laws/${id}`);
      this.setData({ openLawId: id, openLawName: name, articles: d.articles || [] });
    } catch (err) { this.onError(err); }
    wx.hideLoading();
  },

  closeLaw() { this.setData({ openLawId: "", articles: [] }); },
});
