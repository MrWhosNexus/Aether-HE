class CacheCleaner {
  static async clearAllCache() {
    try {
      localStorage.clear();
      sessionStorage.clear();
      this.clearCookies();
      await this.clearIndexedDB();
      await this.clearServiceWorkerCache();
      window.location.reload(true);
      console.log("所有缓存已清除");
      return true;
    } catch (_0x470541) {
      console.error("清除缓存失败:", _0x470541);
      return false;
    }
  }
  static clearCookies() {
    document.cookie.split(";").forEach(_0x267a1f => {
      const _0x37da42 = _0x267a1f.indexOf("=");
      const _0x216103 = _0x37da42 > -1 ? _0x267a1f.substr(0, _0x37da42).trim() : _0x267a1f.trim();
      document.cookie = _0x216103 + "=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
      document.cookie = _0x216103 + "=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/; domain=" + window.location.hostname + ";";
      document.cookie = _0x216103 + "=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
    });
  }
  static async clearIndexedDB() {
    if ("indexedDB" in window) {
      const _0x3d93cc = await window.indexedDB.databases();
      for (const _0x1affb5 of _0x3d93cc) {
        if (_0x1affb5.name) {
          const _0x412d36 = window.indexedDB.deleteDatabase(_0x1affb5.name);
          await new Promise((_0x5d5465, _0x2ea3d5) => {
            _0x412d36.onsuccess = _0x5d5465;
            _0x412d36.onerror = _0x2ea3d5;
            _0x412d36.onblocked = () => {
              console.warn("数据库 " + _0x1affb5.name + " 被阻塞，请关闭所有标签页");
              _0x5d5465();
            };
          });
        }
      }
    }
  }
  static async clearServiceWorkerCache() {
    if ("serviceWorker" in navigator) {
      const _0x555054 = await navigator.serviceWorker.getRegistrations();
      for (const _0x5e8a1d of _0x555054) {
        await _0x5e8a1d.unregister();
      }
    }
    if ("caches" in window) {
      const _0xd081ee = await caches.keys();
      await Promise.all(_0xd081ee.map(_0x4c6448 => caches.delete(_0x4c6448)));
    }
  }
  static clearSpecificCache(_0x2ea051) {
    const _0x14ed59 = {
      local: () => localStorage.clear(),
      session: () => sessionStorage.clear(),
      cookies: () => this.clearCookies(),
      http: () => this.clearHTTPCache(),
      images: () => this.clearImageCache(),
      api: () => this.clearAPICache()
    };
    if (_0x14ed59[_0x2ea051]) {
      _0x14ed59[_0x2ea051]();
    } else {
      console.warn("未知的缓存类型: " + _0x2ea051);
    }
  }
  static clearImageCache() {
    document.querySelectorAll("img").forEach(_0x5e272f => {
      const _0xf67c73 = _0x5e272f.src;
      _0x5e272f.src = "";
      setTimeout(() => {
        _0x5e272f.src = _0xf67c73 + "?t=" + Date.now();
      }, 100);
    });
  }
  static clearAPICache() {
    if (window.fetch) {
      const _0x341764 = window.fetch;
      window.fetch = function (..._0x294e64) {
        let [_0x4efae1, _0x7c4e83 = {}] = _0x294e64;
        if (typeof _0x4efae1 == "string") {
          const _0x4e5af9 = new URL(_0x4efae1, window.location.origin);
          _0x4e5af9.searchParams.set("_nocache", Date.now());
          _0x4efae1 = _0x4e5af9.toString();
        }
        _0x7c4e83.headers = {
          ..._0x7c4e83.headers,
          "Cache-Control": "no-cache, no-store, must-revalidate",
          Pragma: "no-cache",
          Expires: "0"
        };
        return _0x341764.call(this, _0x4efae1, _0x7c4e83);
      };
    }
  }
}
window.addEventListener("DOMContentLoaded", () => {
  document.getElementById("clearCache").onclick = async function () {
    const _0xeb035b = await CacheCleaner.clearAllCache();
    showAlert(_0xeb035b ? "sucess" : "failed");
  };
});