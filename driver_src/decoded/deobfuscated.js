let isChangeCalibration = false;
const needSplite = ["labTip1", "labTip2", "labTip3", "labTip4"];
const notAllow = ["sanpin_glick"];
class WmSlider extends HTMLElement {
  static get observedAttributes() {
    return ["max", "min", "step", "value", "disabled"];
  }
  attributeChangedCallback(_0x508fc7, _0x1536c8, _0x1fc3ca) {
    const _0x224e88 = this.getAttribute("step");
    let _0x4ae4ab = countDecimals(parseFloat(_0x224e88));
    const _0x2b88c4 = this.shadowRoot.getElementById("slider");
    const _0x560417 = this.shadowRoot.getElementById("sliderEdit");
    const _0x26bd45 = this.shadowRoot.getElementById("btnSub");
    const _0x10fa22 = this.shadowRoot.getElementById("btnAdd");
    if (_0x508fc7 === "max") {
      const _0x13cce5 = this.getAttribute("max");
      const _0x490aac = this.max * parseFloat(_0x224e88);
      _0x2b88c4.max = this.max;
      _0x2b88c4.setAttribute("max", _0x13cce5);
      _0x560417.setAttribute("max", _0x490aac);
    }
    if (_0x508fc7 === "min") {
      const _0x40829d = this.getAttribute("min");
      const _0x43b90b = _0x40829d * parseFloat(_0x224e88);
      _0x2b88c4.setAttribute("min", _0x40829d);
      _0x560417.setAttribute("min", _0x43b90b);
    }
    if (_0x508fc7 === "value") {
      const _0x50038b = this.getAttribute("value");
      const _0x53fe9f = (_0x50038b * parseFloat(_0x224e88)).toFixed(_0x4ae4ab);
      _0x2b88c4.setAttribute("value", _0x50038b);
      _0x560417.setAttribute("value", _0x53fe9f);
      _0x2b88c4.value = _0x50038b;
      _0x2b88c4.dispatchEvent(new Event("input"));
      _0x560417.value = _0x53fe9f;
      this.value = _0x50038b;
    }
    if (_0x508fc7 === "step") {
      _0x2b88c4.setAttribute("step", 1);
      const _0x141d6c = this.getAttribute("step");
      _0x560417.setAttribute("step", _0x141d6c);
    }
    if (_0x508fc7 === "disabled") {
      let _0xb76fe5 = this.getAttribute("disabled");
      _0xb76fe5 = _0xb76fe5 !== "false";
      _0x2b88c4.disabled = _0xb76fe5;
      _0x560417.disabled = _0xb76fe5;
      _0x26bd45.disabled = _0xb76fe5;
      _0x10fa22.disabled = _0xb76fe5;
    }
  }
  connectedCallback() {
    console.log("connectedCallback", this.getAttribute("max"));
    const _0x5b3222 = this;
    const _0x3b3c61 = this.shadowRoot.getElementById("slider");
    const _0x30c964 = this.shadowRoot.getElementById("sliderEdit");
    const _0x40b329 = this.shadowRoot.getElementById("btnSub");
    const _0x5266c1 = this.shadowRoot.getElementById("btnAdd");
    _0x3b3c61.addEventListener("input", _0x26450d => {
      const _0x5d4083 = (_0x3b3c61.value - _0x3b3c61.min) / (_0x3b3c61.max - _0x3b3c61.min) * 100 + "%";
      _0x3b3c61.style.setProperty("--fill-percent", _0x5d4083);
      const _0x47c35b = _0x5b3222.getAttribute("step");
      const _0x5f1548 = countDecimals(parseFloat(_0x47c35b));
      this.value = _0x26450d.target.value;
      _0x30c964.value = (_0x26450d.target.value * _0x47c35b).toFixed(_0x5f1548);
      this.dispatchEvent(new CustomEvent("input", {
        detail: _0x26450d.target.value
      }));
    });
    _0x3b3c61.addEventListener("change", _0xa44255 => {
      this.dispatchEvent(new CustomEvent("toggle", {
        detail: _0xa44255.target.value
      }));
    });
    _0x40b329.onclick = function (_0x424798) {
      let _0x3b94ba = parseInt(_0x3b3c61.value);
      _0x3b94ba -= 1;
      if (_0x3b94ba < _0x3b3c61.min) {
        _0x3b94ba = _0x3b3c61.min;
      }
      _0x3b3c61.value = _0x3b94ba;
      _0x3b3c61.dispatchEvent(new Event("input"));
      _0x3b3c61.dispatchEvent(new Event("change"));
    };
    _0x5266c1.onclick = function (_0x57e44c) {
      let _0x2f3981 = parseInt(_0x3b3c61.value);
      _0x2f3981 += 1;
      if (_0x2f3981 > _0x3b3c61.max) {
        _0x2f3981 = _0x3b3c61.max;
      }
      _0x3b3c61.value = _0x2f3981;
      _0x3b3c61.dispatchEvent(new Event("input"));
      _0x3b3c61.dispatchEvent(new Event("change"));
    };
    let _0x3b5dff = 0;
    function _0xa54ba3() {
      if (_0x30c964.value === "") {
        _0x30c964.value = _0x3b5dff;
      }
      const _0x2a19d7 = _0x5b3222.getAttribute("step");
      const _0x20e5cc = countDecimals(parseFloat(_0x2a19d7));
      let _0x43ade5 = parseFloat(_0x30c964.value).toFixed(_0x20e5cc);
      let _0x55684c = parseFloat(_0x43ade5);
      let _0x3a42fc = parseFloat(_0x30c964.step);
      let _0x433a96 = Math.floor(accDiv(_0x55684c, _0x3a42fc));
      if (_0x55684c > _0x30c964.max) {
        _0x55684c = _0x30c964.max;
        _0x433a96 = Math.floor(accDiv(_0x55684c, _0x3a42fc));
        _0x3b3c61.value = _0x433a96;
      } else if (_0x55684c < _0x30c964.min) {
        _0x55684c = _0x30c964.min;
        _0x433a96 = Math.floor(accDiv(_0x55684c, _0x3a42fc));
        _0x3b3c61.value = _0x433a96;
      } else if (_0x3a42fc === 0.1 || _0x3a42fc === 0.01) {
        _0x3b3c61.value = _0x433a96;
      } else if (getRemainder(_0x55684c, _0x3a42fc) <= _0x3a42fc / 2) {
        _0x55684c = _0x433a96 * _0x3a42fc;
        _0x3b3c61.value = _0x433a96;
      } else {
        _0x55684c = (_0x433a96 + 1) * _0x3a42fc;
        _0x3b3c61.value = _0x433a96 + 1;
      }
      _0x30c964.value = parseFloat(_0x55684c + "").toFixed(unitNum);
      _0x3b3c61.dispatchEvent(new Event("input"));
      _0x3b3c61.dispatchEvent(new Event("change"));
    }
    _0x30c964.onfocus = function () {
      _0x3b5dff = _0x30c964.value;
    };
    _0x30c964.onblur = function () {
      _0xa54ba3();
    };
    _0x30c964.oninput = function () {
      if (_0x30c964.value !== "") {
        _0x3b5dff = _0x30c964.value;
      }
    };
    _0x30c964.onkeydown = function (_0x329b8f) {
      if (_0x329b8f.code === "Enter") {
        _0xa54ba3();
      }
    };
  }
  constructor() {
    super();
    const _0x30c017 = document.getElementById("mSlider").content;
    this.attachShadow({
      mode: "open"
    }).appendChild(_0x30c017.cloneNode(true));
  }
}
customElements.define("wm-slider", WmSlider);
let isDeviceOut = false;
function mapsAreEqual(_0x41c03d, _0x1ca731) {
  if (_0x41c03d.size !== _0x1ca731.size) {
    return false;
  }
  for (let [_0x5c99f4, _0x48f4b5] of _0x41c03d) {
    if (!_0x1ca731.has(_0x5c99f4) || _0x1ca731.get(_0x5c99f4) !== _0x48f4b5) {
      return false;
    }
  }
  return true;
}
function clearTriggerButtonState() {
  btnSelectAll.checked = false;
  keyBtn.forEach(_0x348355 => {
    if (!isCalibrationing) {
      document.getElementById("calibrationTip")?.remove();
      if (findDeviceKey(document.getElementById(_0x348355.htmlFor).id).code === "Enter" && (curDevice.type === "uk" || curDevice.type === "jp")) {
        document.documentElement.style.setProperty("--ukKey-color", "var(--btn-bgColor)");
        _0x348355.style.display = "flex";
      }
      const _0x7d56b1 = _0x348355.querySelector("[class=devKeyPanelView]");
      if (_0x7d56b1 != null) {
        _0x7d56b1.style.backgroundColor = "";
        _0x7d56b1.childNodes[0].style.color = "";
        _0x7d56b1.style.setProperty("--btn-color", "");
      }
    }
    let _0x2e0cfe = document.getElementById(_0x348355.htmlFor);
    _0x2e0cfe.checked = false;
    _0x2e0cfe.dispatchEvent(new Event("change"));
  });
  checkedKeys = [];
  triggerPower.disabled = checkedKeys.length === 0;
  if (checkedKeys.length === 0) {
    triggerPower.checked = false;
    refreshTriggerView(false);
  }
  refreshTriggerAllView();
  curKey = undefined;
}
async function checkFirmwareVersion(_0x327fa5 = false) {
  if (curDevice !== undefined && curDevice !== null) {
    const _0x3019d6 = await fetch("../config/firmware.json");
    let _0x1d2483 = (await _0x3019d6.json()).device;
    if (_0x1d2483 != null) {
      for (let _0x316505 in _0x1d2483) {
        let _0x304281 = _0x1d2483[_0x316505];
        if (curDevice.product === _0x304281.product) {
          if (isNewVersion(curDevice.version, _0x304281.version)) {
            console.log("发现新版本：V", _0x304281.version);
            if (!_0x327fa5 && (settingsDiv.style.display === "none" || settingsDiv.style.display === "")) {
              settingsDiv.style.display = "flex";
            }
            firmwareInfo.innerText = getI18n("firmwareNew") + " V" + _0x304281.version;
            btnUpdate.setAttribute("version", _0x304281.version);
            btnUpdate.value = _0x304281.file;
            btnUpdate.innerText = getI18n("download");
          } else {
            firmwareInfo.innerText = getI18n("firmwareCurrent") + "V" + curDevice.version + "，" + getI18n("firmwareLast");
            btnUpdate.setAttribute("version", "");
            btnUpdate.value = "";
            btnUpdate.innerText = getI18n("checkUpdate");
          }
          break;
        }
      }
    }
  }
}
async function downloadFirmware(_0xb39a51) {
  let _0x33fbc8 = "../config/firmware/" + _0xb39a51;
  const _0x3c4dc7 = document.getElementById("progressBar");
  const _0x2231c3 = document.getElementById("downloadBtn");
  try {
    const _0x8388b5 = await fetch(_0x33fbc8);
    if (!_0x8388b5.ok) {
      throw new Error("HTTP错误，状态码: " + _0x8388b5.status);
    }
    const _0x5a3aff = _0x8388b5.headers.get("Content-Length");
    const _0x54c2ba = _0x5a3aff ? parseInt(_0x5a3aff, 10) : 0;
    if (!_0x8388b5.body) {
      throw new Error("ReadableStream 不可用");
    }
    const _0x5c7ebf = {
      suggestedName: _0xb39a51,
      types: [{
        description: "Firmware Update Tool",
        accept: {
          "application/rar": [".rar"]
        }
      }],
      excludeAcceptAllOption: true
    };
    const _0x58f68d = await window.showSaveFilePicker(_0x5c7ebf);
    btnUpdate.disabled = true;
    _0x3c4dc7.style.display = "block";
    _0x3c4dc7.style.width = "0%";
    const _0x2a6a5b = document.createElement("div");
    _0x2a6a5b.classList.add("spinner");
    _0x2231c3.appendChild(_0x2a6a5b);
    const _0x258a3f = await _0x58f68d.createWritable();
    const _0x38eb26 = _0x8388b5.body.getReader();
    let _0x47440a = 0;
    while (true) {
      const {
        done: _0x35cc60,
        value: _0x763381
      } = await _0x38eb26.read();
      if (_0x35cc60) {
        break;
      }
      await _0x258a3f.write(_0x763381);
      _0x47440a += _0x763381.length;
      if (_0x54c2ba) {
        const _0x27c26e = _0x47440a / _0x54c2ba * 100;
        _0x3c4dc7.style.width = _0x27c26e + "%";
        btnUpdate.innerText = getI18n("downloading") + _0x27c26e + "%";
      } else {
        showAlert(getI18n("downloading") + " " + _0x47440a + " bytes");
      }
    }
    await _0x258a3f.close();
    showAlert(getI18n("downloadSuccess"));
    _0x3c4dc7.style.display = "none";
    _0x3c4dc7.style.width = "0%";
    _0x2a6a5b.remove();
    btnUpdate.innerText = getI18n("download");
    console.log("下载成功");
    btnUpdate.disabled = false;
  } catch (_0x7f0cf2) {
    if (_0x7f0cf2.name === "UserCancelledError" || _0x7f0cf2.name === "AbortError") {
      console.log("用户取消了文件保存操作");
    } else {
      showAlert(getI18n("downloadFail"));
      console.error("下载失败:", _0x7f0cf2);
    }
    btnUpdate.disabled = false;
  }
}
function isNewVersion(_0x503184, _0x458d02) {
  let _0x5b48da = _0x503184.split(".");
  let _0x5f4e8f = _0x458d02.split(".");
  let _0x32f783 = _0x5b48da.length < _0x5f4e8f.length ? _0x5b48da.length : _0x5f4e8f.length;
  for (let _0x591b6d = 0; _0x591b6d < _0x32f783; _0x591b6d++) {
    let _0x1dd6c3 = parseInt(_0x5b48da[_0x591b6d]);
    let _0x286dc5 = parseInt(_0x5f4e8f[_0x591b6d]);
    if (_0x1dd6c3 < _0x286dc5) {
      return true;
    }
    if (_0x1dd6c3 != _0x286dc5) {
      return false;
    }
  }
  return false;
}
function refreshPrcsValue(_0x47cb6b, _0x41c9c3, _0x417c9c) {
  document.getElementById("prcsPower").checked = _0x47cb6b;
  let _0xea7c66 = document.getElementById("prcsHotKey");
  let _0x13afb8 = findFixedKeyByHid(0, _0x41c9c3);
  let _0x1ae568 = findFixedKeyByHid(0, _0x417c9c);
  _0xea7c66.innerText = _0x13afb8.name + " + " + _0x1ae568.name;
}
function getPrcsIndex() {
  let _0x10a980 = [];
  prcses.forEach(_0x3adabe => {
    _0x10a980.push(_0x3adabe.index);
  });
  let _0x54ff4e = _0x10a980.length;
  for (let _0xa984c1 = 0; _0xa984c1 < _0x10a980.length; _0xa984c1++) {
    if (!_0x10a980.includes(_0xa984c1)) {
      _0x54ff4e = _0xa984c1;
      break;
    }
  }
  return _0x54ff4e;
}
function refreshPrcsList(_0x43ea94) {
  document.getElementById("prcsCount").innerText = _0x43ea94.length + "/20";
  document.getElementById("prcsTip").style.display = _0x43ea94.length > 0 ? "none" : "flex";
  let _0x625887 = document.getElementById("piEdit1");
  let _0x582d1a = document.getElementById("piEdit2");
  let _0x1bb2c4 = document.getElementById("prcsModel1");
  let _0x5c83a2 = document.getElementById("prcsModel2");
  let _0x1df241 = document.getElementById("prcsModel3");
  let _0x2a9b4e = document.getElementById("prcsModel4");
  let _0x1c3531 = document.getElementById("prcsList");
  _0x1c3531.innerHTML = "";
  let _0x3f6df4 = "SOCD";
  if (curCompany === "sanpin_glick" && i18n === "kr") {
    _0x3f6df4 = "펄스탭";
  }
  _0x43ea94.forEach(_0x15b18a => {
    let _0x269235 = _0x3f6df4 + (_0x15b18a.index + 1);
    let _0xa54539 = document.createElement("input");
    _0xa54539.id = _0x269235;
    _0xa54539.type = "radio";
    _0xa54539.name = "prcsBtn";
    _0xa54539.onchange = function () {
      curPrcs = _0x15b18a;
      _0x625887.value = _0x15b18a.key1.name;
      _0x582d1a.value = _0x15b18a.key2.name;
      if (_0x15b18a.model === 0) {
        _0x1bb2c4.checked = true;
      }
      if (_0x15b18a.model === 1) {
        _0x5c83a2.checked = true;
      }
      if (_0x15b18a.model === 2) {
        _0x1df241.checked = true;
      }
      if (_0x15b18a.model === 3) {
        _0x2a9b4e.checked = true;
      }
    };
    let _0x28c100 = document.createElement("label");
    _0x28c100.setAttribute("for", _0x269235);
    _0x28c100.innerText = _0x269235;
    _0x1c3531.appendChild(_0xa54539);
    _0x1c3531.appendChild(_0x28c100);
  });
}
function getMacroIndex() {
  let _0x56dd08 = [];
  macros.forEach(_0xa7eebb => {
    _0x56dd08.push(_0xa7eebb.index);
  });
  let _0x390d1b = _0x56dd08.length;
  for (let _0x127c8d = 0; _0x127c8d < _0x56dd08.length; _0x127c8d++) {
    if (!_0x56dd08.includes(_0x127c8d)) {
      _0x390d1b = _0x127c8d;
      break;
    }
  }
  return _0x390d1b;
}
function refreshMacroList(_0x3537c0) {
  document.getElementById("macInfo").style.display = _0x3537c0.length > 0 ? "block" : "none";
  let _0x36acfb = document.getElementById("macroDiv");
  let _0xb5fd52 = document.getElementById("macKeySet");
  _0xb5fd52.innerHTML = "";
  for (let _0x50eab4 = 0; _0x50eab4 < _0x3537c0.length; _0x50eab4++) {
    let _0x1b5a1d = _0x3537c0[_0x50eab4];
    let _0x25cef2 = document.createElement("div");
    _0x25cef2.className = "macItemDiv";
    let _0x11a6b9 = document.createElement("label");
    _0x11a6b9.innerText = _0x1b5a1d.name;
    let _0x1f13cb = document.createElement("div");
    let _0x29ec4e = document.createElement("button");
    _0x29ec4e.className = "btnEdit";
    _0x29ec4e.onclick = function (_0xf35d50) {
      _0x36acfb.style.display = "block";
      document.getElementById("macroInfoDelay").value = "0";
      document.getElementById("macroKeyEdit").value = "";
      curMacro = _0x1b5a1d;
      refreshMacroItems(curMacro.steps);
      _0xf35d50.stopPropagation();
    };
    let _0x30f073 = document.createElement("button");
    _0x30f073.className = "btnDelete";
    _0x30f073.onclick = function (_0x308162) {
      let _0x598334 = _0x3537c0.indexOf(_0x1b5a1d);
      if (_0x598334 >= 0 && _0x598334 < _0x3537c0.length) {
        _0x3537c0.splice(_0x598334, 1);
        recKeys.forEach((_0x4c3461, _0x4ec1ec) => {
          if (_0x4c3461.code1 === 16 && _0x4c3461.code3 === _0x1b5a1d.index) {
            recKeys.delete(_0x4ec1ec);
            if (curKey !== undefined && curKey.index === _0x4ec1ec) {
              recordInput.value = curKey.name;
            }
          }
        });
        fnKeys.forEach((_0x18f6c7, _0x46de38) => {
          if (_0x18f6c7.code1 === 16 && _0x18f6c7.code3 === _0x1b5a1d.index) {
            fnKeys.delete(_0x46de38);
            if (curKey !== undefined && curKey.index === _0x46de38) {
              recordInput.value = curKey.name;
            }
          }
        });
        refreshRecordDot();
        curProfile.macros = deepCopy(_0x3537c0);
        let _0x1939fd = JSON.stringify(profileSet, replacer);
        localStorage.setItem(curDevice.product, _0x1939fd);
        btnApplyKey.dispatchEvent(new Event("click"));
      }
      refreshMacroList(_0x3537c0);
      _0x308162.stopPropagation();
    };
    _0x1f13cb.appendChild(_0x29ec4e);
    _0x1f13cb.appendChild(_0x30f073);
    _0x1f13cb.style.display = "none";
    _0x25cef2.appendChild(_0x11a6b9);
    _0x25cef2.appendChild(_0x1f13cb);
    _0x25cef2.onmouseenter = function () {
      _0x1f13cb.style.display = "flex";
    };
    _0x25cef2.onmouseleave = function () {
      _0x1f13cb.style.display = "none";
    };
    _0x25cef2.onclick = function () {
      if (curKey !== undefined) {
        if (recMacros.size < 10) {
          let _0xd85507 = new Key();
          _0xd85507.code1 = 16;
          _0xd85507.hidCode = curKey.hidCode;
          _0xd85507.code3 = _0x1b5a1d.index;
          _0xd85507.name = _0x1b5a1d.name;
          let _0x55b59f = new MacroKey();
          _0x55b59f.index = _0x1b5a1d.index;
          _0x55b59f.type = getMacroType();
          _0x55b59f.count = getMacroExecCount();
          recMacros.set(curKey.index, _0x55b59f);
          recordInput.value = _0xd85507.name;
          if (keymapDef.checked) {
            recKeys.set(curKey.index, _0xd85507);
          }
          if (keymapFn.checked) {
            fnKeys.set(curKey.index, _0xd85507);
          }
          refreshRecordDot();
          if (confirm(getI18n("applyTip2"))) {
            btnApplyKey.dispatchEvent(new Event("click"));
          }
        } else {
          showAlert(getI18n("alertMacroWarning"));
        }
      }
    };
    _0xb5fd52.appendChild(_0x25cef2);
  }
  let _0x2bc6ca = document.createElement("button");
  _0x2bc6ca.className = "addButton";
  _0x2bc6ca.onclick = function () {
    if (_0x3537c0.length < 10) {
      _0x36acfb.style.display = "block";
      document.getElementById("macroInfoDelay").value = "0";
      document.getElementById("macroKeyEdit").value = "";
      curMacro = new Macro();
      curMacro.index = getMacroIndex();
      curMacro.name = "Macro" + (curMacro.index + 1);
      refreshMacroItems(curMacro.steps);
    } else {
      showAlert(getI18n("alertMacroWarning"));
    }
  };
  _0xb5fd52.appendChild(_0x2bc6ca);
}
function getMacroType() {
  let _0x5ea4cd = 0;
  let _0x2abde7 = document.getElementById("macroType1");
  let _0x23d124 = document.getElementById("macroType2");
  let _0x23df3c = document.getElementById("macroType3");
  let _0x3aba87 = document.getElementById("macroType4");
  if (_0x2abde7.checked) {
    _0x5ea4cd = 0;
  }
  if (_0x23d124.checked) {
    _0x5ea4cd = 1;
  }
  if (_0x23df3c.checked) {
    _0x5ea4cd = 2;
  }
  if (_0x3aba87.checked) {
    _0x5ea4cd = 3;
  }
  return _0x5ea4cd;
}
function getMacroExecCount() {
  let _0x419f54 = document.getElementById("macroExecCount");
  return parseInt(_0x419f54.value);
}
function refreshMacroItems(_0x221e03) {
  const _0x27e519 = new Set(_0x221e03.map(_0xdccfd3 => _0xdccfd3.tag).filter(_0x53ba4c => _0x53ba4c !== undefined && _0x53ba4c >= 0));
  const _0x2a2098 = Array.from(_0x27e519);
  if (_0x2a2098.length > 20) {
    const _0x4ceb96 = _0x2a2098.slice(0, 20);
    _0x221e03.filter(_0x32404b => _0x32404b.tag === undefined || _0x32404b.tag < 0 || _0x4ceb96.includes(_0x32404b.tag));
    _0x221e03 = _0x4ceb96;
    return showAlert(getI18n("macroStepLimitWarning"));
  }
  let _0x54b010 = document.getElementById("macroItemList");
  _0x54b010.innerHTML = "";
  for (let _0x35ff17 = 0; _0x35ff17 < _0x221e03.length; _0x35ff17++) {
    let _0x1030e2 = _0x221e03[_0x35ff17];
    let _0x36b928 = "step_" + _0x35ff17;
    let _0x2694f4 = document.createElement("div");
    _0x2694f4.className = "macroStep";
    let _0x1997a3 = document.createElement("input");
    _0x1997a3.type = "radio";
    _0x1997a3.name = "macroStep";
    _0x1997a3.id = _0x36b928;
    let _0x3ce96f = document.createElement("label");
    _0x3ce96f.className = "labMacroStep";
    _0x3ce96f.setAttribute("for", _0x36b928);
    _0x3ce96f.setAttribute("tag", _0x1030e2.tag);
    _0x3ce96f.setAttribute("state", _0x1030e2.state);
    let _0xf17119 = document.createElement("span");
    _0xf17119.className = "msDelay";
    _0xf17119.innerText = _0x1030e2.delay + "ms";
    let _0x3e70c6 = document.createElement("img");
    _0x3e70c6.className = "msType";
    _0x3e70c6.setAttribute("type", _0x1030e2.type);
    let _0xeb4939 = theme === "light" ? "image/icon_keyboard.png" : "image/dark/icon_keyboard.png";
    let _0x440a63 = theme === "light" ? "image/icon_mouse.png" : "image/dark/icon_mouse.png";
    _0x3e70c6.src = _0x1030e2.type === 0 ? _0xeb4939 : _0x440a63;
    _0x3e70c6.alt = "";
    let _0x2a887c = document.createElement("img");
    _0x2a887c.className = "msArrow";
    _0x2a887c.setAttribute("state", _0x1030e2.state);
    let _0x2450ee = theme === "light" ? "image/icon_arrow_up.png" : "image/dark/icon_arrow_up.png";
    let _0x4d2f5b = theme === "light" ? "image/icon_arrow_down.png" : "image/dark/icon_arrow_down.png";
    _0x2a887c.src = _0x1030e2.state === 1 ? _0x4d2f5b : _0x2450ee;
    _0x2a887c.alt = "";
    let _0xbb8ad = document.createElement("span");
    _0xbb8ad.innerText = _0x1030e2.key.code1 > 0 ? getI18n(_0x1030e2.key.code) : _0x1030e2.key.name;
    _0x1997a3.onchange = function () {
      if (_0x1997a3.checked) {
        curStep = _0x1030e2;
        console.log(_0x1030e2.key.name);
        setMacroItemOtherOneBackground(_0x1030e2);
        refreshMacroItemInfo(_0x1030e2);
      }
    };
    _0x3ce96f.appendChild(_0xf17119);
    _0x3ce96f.appendChild(_0x3e70c6);
    _0x3ce96f.appendChild(_0x2a887c);
    _0x3ce96f.appendChild(_0xbb8ad);
    _0x2694f4.appendChild(_0x1997a3);
    _0x2694f4.appendChild(_0x3ce96f);
    _0x54b010.appendChild(_0x2694f4);
  }
}
function insertMacroStep() {
  let _0x41eac3 = 0;
  if (curStep !== undefined && curStep !== null) {
    _0x41eac3 = curMacro.steps.indexOf(curStep);
    let _0x54a3ee = new Step();
    _0x54a3ee.tag = getStepTag(curMacro);
    _0x54a3ee.type = 0;
    _0x54a3ee.state = 1;
    _0x54a3ee.delay = 0;
    let _0x28027f = new Step();
    _0x28027f.tag = getStepTag(curMacro);
    _0x28027f.type = 0;
    _0x28027f.state = 0;
    _0x28027f.delay = 0;
    curMacro.steps.splice(_0x41eac3 + 1, 0, _0x28027f);
    curMacro.steps.splice(_0x41eac3 + 1, 0, _0x54a3ee);
  }
  refreshMacroItems(curMacro.steps);
  if (_0x41eac3 + 1 < curMacro.steps.length) {
    curStep = curMacro.steps[_0x41eac3 + 1];
    setCurrentStep(_0x41eac3 + 1);
    setMacroItemOtherOneBackground(curStep);
  }
}
function clearMacroItems() {
  curMacro.steps = [];
  refreshMacroItems(curMacro.steps);
}
function deleteMacroStep() {
  if (curStep !== undefined && curStep !== null) {
    let _0x1fdc07 = curMacro.steps.indexOf(curStep);
    let _0x4bb180 = curStep.tag;
    if (_0x1fdc07 >= 0 && _0x1fdc07 < curMacro.steps.length) {
      curMacro.steps.splice(_0x1fdc07, 1);
    }
    let _0x4f130a = curMacro.steps.find(_0x4f57d3 => _0x4f57d3.tag === _0x4bb180);
    if (_0x4f130a != null) {
      _0x1fdc07 = curMacro.steps.indexOf(_0x4f130a);
      if (_0x1fdc07 >= 0 && _0x1fdc07 < curMacro.steps.length) {
        curMacro.steps.splice(_0x1fdc07, 1);
      }
    }
    refreshMacroItems(curMacro.steps);
    if (curMacro.steps.length > 0) {
      curStep = curMacro.steps[0];
      setCurrentStep(0);
      setMacroItemOtherOneBackground(curStep);
    }
  }
}
function moveUpMacroStep() {
  let _0x5ae7c1 = curMacro.steps.indexOf(curStep);
  let _0x1c97e4 = findStepTag(curMacro, curStep.key.code);
  if (_0x5ae7c1 > 0) {
    let _0xf089b4 = _0x5ae7c1 - 1;
    let _0x544427 = curMacro.steps[_0xf089b4];
    if (_0x544427.tag === _0x1c97e4 && _0x544427.state === 1) {
      return;
    }
    curMacro.steps.splice(_0x5ae7c1, 1);
    curMacro.steps.splice(_0xf089b4, 0, curStep);
    refreshMacroItems(curMacro.steps);
    setCurrentStep(_0xf089b4);
    setMacroItemOtherOneBackground(curStep);
  }
}
function moveDownMacroStep() {
  let _0x3790ca = curMacro.steps.indexOf(curStep);
  let _0x18c285 = findStepTag(curMacro, curStep.key.code);
  if (_0x3790ca < curMacro.steps.length) {
    let _0x416d82 = _0x3790ca + 1;
    let _0x7e28f = curMacro.steps[_0x416d82];
    if (_0x7e28f.tag === _0x18c285 && _0x7e28f.state === 0) {
      return;
    }
    curMacro.steps.splice(_0x3790ca, 1);
    curMacro.steps.splice(_0x416d82, 0, curStep);
    refreshMacroItems(curMacro.steps);
    setCurrentStep(_0x416d82);
    setMacroItemOtherOneBackground(curStep);
  }
}
function setCurrentStep(_0x53e3da) {
  let _0x57d3a5 = document.getElementById("macroItemList").querySelectorAll("input");
  for (let _0x32ba8a = 0; _0x32ba8a < _0x57d3a5.length; _0x32ba8a++) {
    let _0x5d2b84 = _0x57d3a5[_0x32ba8a];
    if (_0x32ba8a === _0x53e3da) {
      _0x5d2b84.checked = true;
      break;
    }
  }
}
function updateStepDelay(_0x16135d) {
  curStep.delay = _0x16135d;
  refreshMacroItems(curMacro.steps);
  setCurrentStep(curMacro.steps.indexOf(curStep));
  setMacroItemOtherOneBackground(curStep);
}
function updateStepKey(_0x1bf879) {
  curMacro.steps.forEach(function (_0x3e57c3) {
    if (_0x3e57c3.tag === curStep?.tag) {
      _0x3e57c3.key = _0x1bf879;
      _0x3e57c3.type = _0x1bf879.code1 === 0 ? 0 : 1;
    }
  });
  refreshMacroItems(curMacro.steps);
  setCurrentStep(curMacro.steps.indexOf(curStep));
  setMacroItemOtherOneBackground(curStep);
}
function getStepTag(_0x4bad8e) {
  let _0x4727dc = [];
  _0x4bad8e.steps.forEach(_0x452e62 => {
    _0x4727dc.push(_0x452e62.tag);
  });
  let _0x9b7dff = _0x4727dc.length;
  for (let _0x35291f = 0; _0x35291f < _0x4727dc.length; _0x35291f++) {
    if (!_0x4727dc.includes(_0x35291f)) {
      _0x9b7dff = _0x35291f;
      break;
    }
  }
  return _0x9b7dff;
}
function findStepTag(_0x10c3bf, _0x303e43) {
  let _0x118599 = 0;
  for (let _0x37cddd = _0x10c3bf.steps.length - 1; _0x37cddd >= 0; _0x37cddd--) {
    let _0x59459f = _0x10c3bf.steps[_0x37cddd];
    if (_0x59459f.key.code === _0x303e43) {
      _0x118599 = _0x59459f.tag;
      break;
    }
  }
  return _0x118599;
}
function setMacroItemOtherOneBackground(_0xa893e2) {
  let _0x1fe175 = document.getElementById("macroItemList").querySelectorAll("label");
  for (let _0x1ff872 of _0x1fe175) {
    if (_0x1ff872.getAttribute("tag") === _0xa893e2.tag.toString()) {
      if (parseInt(_0x1ff872.getAttribute("state")) !== _0xa893e2.state) {
        _0x1ff872.className = "labMacroStep2";
      }
    } else {
      _0x1ff872.className = "labMacroStep";
    }
  }
}
function refreshMacroItemInfo(_0x15c0a7) {
  let _0x19dca8 = document.getElementById("mInfoDelayView");
  let _0x3600e3 = document.getElementById("mInfoEventView");
  let _0x40fec9 = document.getElementById("mInfoKeyView");
  _0x19dca8.style.display = "flex";
  _0x3600e3.style.display = "flex";
  _0x40fec9.style.display = "flex";
  let _0x29737d = document.getElementById("macroInfoDelay");
  let _0x589e0e = document.getElementById("macroKeyboardEvent");
  let _0x2eaf23 = document.getElementById("macroMouseEvent");
  let _0x5ab839 = document.getElementById("mInfoKey");
  let _0x418338 = document.getElementById("mInfoMouse");
  let _0x382d38 = document.getElementById("macroKeyEdit");
  let _0x558e67 = document.getElementById("macroMouseLeft");
  let _0x5c0760 = document.getElementById("macroMouseMiddle");
  let _0x2a327a = document.getElementById("macroMouseRight");
  _0x29737d.value = _0x15c0a7.delay;
  _0x29737d.validity.lastValidValue = _0x29737d.value;
  if (_0x15c0a7.type === 0) {
    _0x589e0e.checked = true;
    _0x5ab839.style.display = "flex";
    _0x418338.style.display = "none";
    _0x382d38.value = _0x15c0a7.key.name;
  }
  if (_0x15c0a7.type === 1) {
    _0x2eaf23.checked = true;
    _0x5ab839.style.display = "none";
    _0x418338.style.display = "flex";
    if (_0x15c0a7.key.code === "MouseLeft") {
      _0x558e67.checked = true;
    }
    if (_0x15c0a7.key.code === "MouseMiddle") {
      _0x5c0760.checked = true;
    }
    if (_0x15c0a7.key.code === "MouseRight") {
      _0x2a327a.checked = true;
    }
  }
}
function refreshRecordDot(_0x59a3a3 = keyBtn) {
  if (menu1.checked) {
    _0x59a3a3.forEach(function (_0x265e94) {
      let _0x1daee2 = _0x265e94.htmlFor;
      let _0x3a46be = findDeviceKey(_0x1daee2);
      const _0x3fce59 = devSet.querySelector(".devKeyName[for=\"" + _0x1daee2 + "\"]")?.closest(".devKeyPanelView")?.querySelector(".devKeyRedDot");
      if (keymapDef.checked) {
        if (recKeys.has(_0x3a46be.index)) {
          const _0x3915c3 = recKeys.get(_0x3a46be.index);
          if (_0x3915c3.code1 === 24 || _0x3915c3.code1 === 25) {
            if (_0x3915c3.code1 === 24 && curDevice.pid === 50023 || _0x3915c3.code1 === 25 && curDevice.pid === 50022) {
              _0x265e94.querySelector("img").style.display = "block";
              _0x3fce59.style.filter = cacheRecKeys.get(_0x3a46be.index)?.name === recKeys.get(_0x3a46be.index)?.name ? "none" : "brightness(0.5)";
            } else {
              _0x265e94.querySelector("img").style.display = "none";
            }
          } else {
            _0x265e94.querySelector("img").style.display = "block";
            _0x3fce59.style.filter = cacheRecKeys.get(_0x3a46be.index)?.name === recKeys.get(_0x3a46be.index)?.name ? "none" : "brightness(0.5)";
          }
        } else {
          _0x265e94.querySelector("img").style.display = "none";
        }
      }
      if (keymapFn.checked) {
        if (fnKeys.has(_0x3a46be.index) && !fnKeyState.includes(_0x3a46be.index)) {
          const _0xc97efc = fnKeys.get(_0x3a46be.index);
          if (_0xc97efc.code1 === 24 || _0xc97efc.code1 === 25) {
            if (_0xc97efc.code1 === 24 && curDevice.pid === 50023 || _0xc97efc.code1 === 25 && curDevice.pid === 50022) {
              _0x265e94.querySelector("img").style.display = "block";
              _0x3fce59.style.filter = cacheFnKeys.get(_0x3a46be.index)?.name === fnKeys.get(_0x3a46be.index)?.name ? "none" : "brightness(0.5)";
            } else {
              _0x265e94.querySelector("img").style.display = "none";
            }
          } else {
            _0x265e94.querySelector("img").style.display = "block";
            _0x3fce59.style.filter = cacheFnKeys.get(_0x3a46be.index)?.name === fnKeys.get(_0x3a46be.index)?.name ? "none" : "brightness(0.5)";
          }
        } else {
          _0x265e94.querySelector("img").style.display = "none";
        }
      }
    });
    let _0x75840a = document.getElementById("deviceBg");
    if (curKey) {
      if (document.getElementById("applyTip1")) {
        document.getElementById("applyTip1").innerText = getI18n("applyTip1");
        return;
      }
      calibrationTipView = document.createElement("div");
      calibrationTipView.setAttribute("id", "applyTip1");
      calibrationTipView.setAttribute("i18n", "applyTip1");
      calibrationTipView.classList.add("applyTip1");
      calibrationTipView.innerText = getI18n("applyTip1");
      _0x75840a.appendChild(calibrationTipView);
    }
  }
}
function refreshDeviceView() {
  if (curKey !== undefined && curKey !== null) {
    if (keymapDef.checked) {
      if (recKeys.has(curKey.index)) {
        recordInput.value = recKeys.get(curKey.index).name;
      } else {
        recordInput.value = curKey.name;
      }
    }
    if (keymapFn.checked) {
      if (fnKeys.has(curKey.index)) {
        recordInput.value = fnKeys.get(curKey.index).name;
      } else {
        recordInput.value = curKey.name;
      }
    }
  }
}
function setRecordKey(_0x9353f8, _0x411292, _0x2ee2f2) {
  if (_0x9353f8 === document.activeElement) {
    let _0x24c72a = findFixedKey(_0x411292.code);
    if (_0x24c72a !== undefined) {
      initRecordKeys(_0x2ee2f2, _0x24c72a);
      let _0x47a730 = _0x24c72a.name;
      if (_0x2ee2f2 === 1) {
        if (keyManu1.checked) {
          _0x9353f8.value = _0x47a730;
        }
        if (keyManu2.checked) {
          _0x47a730 = "";
          for (let _0x11c3e1 = 0; _0x11c3e1 < comKeys.length; _0x11c3e1++) {
            let _0x23deca = comKeys[_0x11c3e1];
            _0x47a730 += _0x11c3e1 === 0 ? _0x23deca.name : " + " + _0x23deca.name;
          }
          if (hasCtrKey() && hasDefKey()) {
            let _0x351f39 = new Key();
            _0x351f39.name = _0x47a730;
            _0x351f39.code1 = 19;
            _0x351f39.hidCode = comKeys.length > 0 ? comKeys[0].hidCode : 0;
            _0x351f39.code3 = comKeys.length > 1 ? comKeys[1].hidCode : 0;
            _0x351f39.code4 = comKeys.length > 2 ? comKeys[2].hidCode : 0;
            if (keymapDef.checked) {
              recKeys.set(curKey.index, _0x351f39);
            }
            if (keymapFn.checked) {
              fnKeys.set(curKey.index, _0x351f39);
            }
            refreshRecordDot();
          }
          _0x9353f8.value = _0x47a730;
        }
      } else {
        _0x9353f8.value = _0x47a730;
        if (_0x2ee2f2 === 9) {
          updateStepKey(_0x24c72a);
        }
      }
    }
    _0x411292.preventDefault();
  }
}
function initRecordKeys(_0x65c3c0, _0x3c86b5) {
  if (_0x65c3c0 === 1 && (keyManu1.checked && (keymapDef.checked && recKeys.set(curKey.index, _0x3c86b5), keymapFn.checked && fnKeys.set(curKey.index, _0x3c86b5), refreshRecordDot()), keyManu2.checked)) {
    if (hasDefKey()) {
      if (isCtrKey(_0x3c86b5.hidCode)) {
        comKeys = [];
        initRecordKeys(_0x65c3c0, _0x3c86b5);
      }
    } else if (!comKeys.some(_0x18bdcc => _0x18bdcc.code === _0x3c86b5.code)) {
      if (comKeys.length < 2 && isCtrKey(_0x3c86b5.hidCode)) {
        comKeys.push(_0x3c86b5);
      }
      if (comKeys.length > 0 && !isCtrKey(_0x3c86b5.hidCode)) {
        comKeys.push(_0x3c86b5);
      }
    }
  }
  if (_0x65c3c0 === 2) {
    curTglKey.keys[0] = _0x3c86b5;
  }
  if (_0x65c3c0 === 3) {
    curMtKey.keys[0] = _0x3c86b5;
  }
  if (_0x65c3c0 === 4) {
    curMtKey.keys[1] = _0x3c86b5;
  }
  if (_0x65c3c0 === 5) {
    curDksKey.keys[0] = _0x3c86b5;
  }
  if (_0x65c3c0 === 6) {
    curDksKey.keys[1] = _0x3c86b5;
  }
  if (_0x65c3c0 === 7) {
    curDksKey.keys[2] = _0x3c86b5;
  }
  if (_0x65c3c0 === 8) {
    curDksKey.keys[3] = _0x3c86b5;
  }
  if (_0x65c3c0 === 10) {
    curPrcs.key1 = _0x3c86b5;
  }
  if (_0x65c3c0 === 11) {
    curPrcs.key2 = _0x3c86b5;
  }
  if (_0x65c3c0 === 12 || _0x65c3c0 === 13) {
    const _0x245fd2 = advKeys?.some(_0x1e4a97 => _0x1e4a97.type === "RS" && _0x1e4a97.keys.some(_0x4c2ff7 => _0x4c2ff7.code === _0x3c86b5.code));
    let _0xc30511 = findDeviceKey(_0x3c86b5.code, "code");
    if (_0x245fd2 || !_0xc30511) {
      setTimeout(() => {
        if (_0x65c3c0 === 12) {
          rsEdit1.value = "";
        } else {
          rsEdit2.value = "";
        }
      }, 20);
      return showAlert(_0x245fd2 ? getI18n("rsTip2") : getI18n("rsTip3"));
    }
    if (_0x65c3c0 === 12) {
      curRSKey.keys[0] = _0x3c86b5;
    }
    if (_0x65c3c0 === 13) {
      curRSKey.keys[1] = _0x3c86b5;
    }
    if (curRSKey.keys[0] === curRSKey.keys[1]) {
      showAlert(getI18n("rsTip2"));
      setTimeout(() => {
        rsEdit2.value = "";
      }, 20);
    }
  }
  if (_0x65c3c0 === 14) {
    curRKRTKey.keys[1] = _0x3c86b5;
  }
}
function isCtrKey(_0x5d87b5) {
  return _0x5d87b5 >= 224 && _0x5d87b5 <= 231;
}
function hasCtrKey() {
  for (let _0x2da30b of comKeys) {
    if (isCtrKey(_0x2da30b.hidCode)) {
      return true;
    }
  }
  return false;
}
function hasDefKey() {
  for (let _0x13e380 of comKeys) {
    if (!isCtrKey(_0x13e380.hidCode)) {
      return true;
    }
  }
  return false;
}
function getEndDksBtn(_0x2d183b, _0xd2f5e9, _0x272c64) {
  let _0x137a26 = "dksLabel" + (_0xd2f5e9 * 4 + 4);
  let _0x237d0e = document.getElementById(_0x137a26);
  for (let _0xb36e9f = _0x272c64 + 1; _0xb36e9f < 4; _0xb36e9f++) {
    let _0x57d962 = "dksBtn" + (_0xd2f5e9 * 4 + _0xb36e9f + 1);
    _0x137a26 = "dksLabel" + (_0xd2f5e9 * 4 + _0xb36e9f + 1);
    let _0x106320 = document.getElementById(_0x57d962);
    _0x237d0e = document.getElementById(_0x137a26);
    if (_0x106320.checked && _0x237d0e !== _0x2d183b) {
      break;
    }
  }
  return _0x237d0e;
}
function setDksBtnWidth(_0x4c8a23, _0xc0e350, _0x59ce01) {
  let _0x1c9d05 = _0x4c8a23.offsetLeft + _0x4c8a23.offsetWidth;
  for (let _0x3da90e = _0x59ce01; _0x3da90e < 3; _0x3da90e++) {
    let _0x7efb83 = "dksLabel" + (_0xc0e350 * 4 + _0x3da90e + 1);
    let _0x3da19c = "dksLabel" + (_0xc0e350 * 4 + _0x3da90e + 2);
    const _0x2337bb = document.getElementById(_0x7efb83);
    const _0x40c99b = document.getElementById(_0x3da19c);
    const _0x4a5e4b = _0x2337bb.offsetLeft + 20;
    const _0x9227c5 = _0x40c99b.offsetLeft + 20;
    if (_0x1c9d05 >= _0x4a5e4b && _0x1c9d05 < _0x9227c5) {
      let _0x42ca13 = _0x9227c5 - _0x4a5e4b;
      _0x4c8a23.style.width = _0x1c9d05 < _0x4a5e4b + _0x42ca13 / 2 ? _0x3da90e === _0x59ce01 ? _0x2337bb.offsetLeft - _0x4c8a23.offsetLeft + 20 + "px" : _0x2337bb.offsetLeft - _0x4c8a23.offsetLeft + "px" : _0x40c99b.offsetLeft - _0x4c8a23.offsetLeft + "px";
      break;
    }
  }
}
function setDksValue() {
  for (let _0x5de43c = 0; _0x5de43c < 4; _0x5de43c++) {
    let _0x534297 = _0x5de43c * 4;
    let _0x235b6f = _0x5de43c * 4 + 1;
    let _0x1605e9 = _0x5de43c * 4 + 2;
    let _0x3889cd = _0x5de43c * 4 + 3;
    let _0x392c08 = getDksBtn(_0x534297);
    let _0x301dba = getDksBtn(_0x235b6f);
    let _0x144609 = getDksBtn(_0x1605e9);
    let _0x3e1b70 = getDksBtn(_0x3889cd);
    let _0x1e202f = document.getElementById(_0x392c08.htmlFor);
    let _0x5e6038 = document.getElementById(_0x301dba.htmlFor);
    let _0x556a7e = document.getElementById(_0x144609.htmlFor);
    let _0xad0346 = document.getElementById(_0x3e1b70.htmlFor);
    if (_0x1e202f.checked) {
      if (_0x392c08.offsetWidth === 20) {
        curDksKey.steps[_0x534297] = 1;
      } else {
        curDksKey.steps[_0x534297] = 2;
      }
    } else {
      curDksKey.steps[_0x534297] = 0;
    }
    if (_0x5e6038.checked) {
      if (_0x301dba.offsetWidth === 20) {
        curDksKey.steps[_0x235b6f] = 1;
      } else if (curDksKey.steps[_0x534297] === 2) {
        curDksKey.steps[_0x235b6f] = 3;
      } else {
        curDksKey.steps[_0x235b6f] = 2;
      }
    } else if (_0x392c08.offsetLeft + _0x392c08.offsetWidth < _0x301dba.offsetLeft + _0x301dba.offsetWidth) {
      curDksKey.steps[_0x235b6f] = 0;
    } else {
      curDksKey.steps[_0x235b6f] = 2;
    }
    if (_0x556a7e.checked) {
      if (_0x144609.offsetWidth === 20) {
        curDksKey.steps[_0x1605e9] = 1;
      } else if (curDksKey.steps[_0x235b6f] >= 2) {
        curDksKey.steps[_0x1605e9] = 3;
      } else {
        curDksKey.steps[_0x1605e9] = 2;
      }
    } else if (_0x392c08.offsetLeft + _0x392c08.offsetWidth < _0x144609.offsetLeft + _0x144609.offsetWidth && _0x301dba.offsetLeft + _0x301dba.offsetWidth < _0x144609.offsetLeft + _0x144609.offsetWidth) {
      curDksKey.steps[_0x1605e9] = 0;
    } else {
      curDksKey.steps[_0x1605e9] = 2;
    }
    if (_0xad0346.checked) {
      curDksKey.steps[_0x3889cd] = 1;
    } else {
      curDksKey.steps[_0x3889cd] = 0;
    }
  }
  console.log(curDksKey.steps);
}
function getDksBtn(_0x1bb75c) {
  let _0x2e8cc1 = document.getElementById("dksInfoDetail").querySelectorAll("label");
  for (let _0x595441 of _0x2e8cc1) {
    if (parseInt(_0x595441.innerText) === _0x1bb75c) {
      return _0x595441;
    }
  }
}
function getAdvIndex() {
  let _0x153239 = [];
  advKeys.forEach(_0xc48c38 => {
    _0x153239.push(_0xc48c38.index);
  });
  let _0x193644 = _0x153239.length;
  for (let _0x230b14 = 0; _0x230b14 < _0x153239.length; _0x230b14++) {
    if (!_0x153239.includes(_0x230b14)) {
      _0x193644 = _0x230b14;
      break;
    }
  }
  return _0x193644;
}
function deepCopy(_0x1f64f6) {
  if (_0x1f64f6 === null || typeof _0x1f64f6 != "object") {
    return _0x1f64f6;
  } else if (_0x1f64f6 instanceof Date) {
    return new Date(_0x1f64f6.getTime());
  } else if (_0x1f64f6 instanceof Array) {
    return _0x1f64f6.reduce((_0x3bee6b, _0x16af22, _0x43dd4c) => {
      _0x3bee6b[_0x43dd4c] = deepCopy(_0x16af22);
      return _0x3bee6b;
    }, []);
  } else if (_0x1f64f6 instanceof Object) {
    return Object.keys(_0x1f64f6).reduce((_0x5130bd, _0x47f5fe) => {
      _0x5130bd[_0x47f5fe] = deepCopy(_0x1f64f6[_0x47f5fe]);
      return _0x5130bd;
    }, {});
  } else {
    return undefined;
  }
}
function refreshAdvList() {
  let _0x334b40 = document.getElementById("advDiv");
  let _0x30b585 = document.getElementById("advTypeInfo");
  let _0x3b91b5 = document.getElementById("advTypeRadio1");
  let _0x57a436 = document.getElementById("advTypeRadio2");
  let _0x17afc5 = document.getElementById("advTypeRadio3");
  let _0x1e5fab = document.getElementById("col1");
  let _0x201177 = document.getElementById("col2");
  let _0x195aa5 = document.getElementById("col3");
  let _0x5a1b57 = document.getElementById("col4");
  let _0x167d73 = document.getElementById("tglEdit");
  let _0x52d11e = document.getElementById("mtEdit1");
  let _0x574304 = document.getElementById("mtEdit2");
  let _0x387b7d = document.getElementById("dksEdit1");
  let _0x294f3f = document.getElementById("dksEdit2");
  let _0x2457f8 = document.getElementById("dksEdit3");
  let _0x400701 = document.getElementById("dksEdit4");
  let _0x5b2967 = document.getElementById("mtRange");
  let _0x15bed2 = document.getElementById("tglDiv");
  let _0x3cbf0e = document.getElementById("mtDiv");
  let _0x3fc6a0 = document.getElementById("dksDiv");
  let _0x4c3398 = document.getElementById("rsDiv");
  let _0x31d956 = document.getElementById("rsEdit1");
  let _0x1fde2b = document.getElementById("rsEdit2");
  let _0x5b29fb = document.getElementById("rkrtDiv");
  let _0x5d7921 = document.getElementById("rkrtEdit");
  let _0xd425b0 = document.getElementById("advKeySet");
  _0xd425b0.innerHTML = "";
  advKeys.forEach(_0x45eb02 => {
    let _0x3f2955 = _0x45eb02.index + 1 + "#" + _0x45eb02.type;
    if (_0x45eb02.type === "RS") {
      _0x3f2955 += "->" + (_0x45eb02.keys[0].name || "") + "  " + (_0x45eb02.keys[1].name || "");
      _0x45eb02.keys.forEach(_0x1a6679 => {
        if (_0x1a6679.index && !recKeys.has(_0x1a6679.index)) {
          recKeys.set(_0x1a6679.index);
          setRecordKeyByKeyId(_0x1a6679.index, _0x3f2955);
          refreshRecordDot([document.querySelector("label[for=\"" + _0x1a6679.code + "\"")]);
        }
      });
    }
    let _0x5a5ec6 = document.createElement("div");
    _0x5a5ec6.className = "macItemDiv";
    let _0x1679c4 = document.createElement("label");
    _0x1679c4.innerText = _0x3f2955;
    let _0x2bde72 = document.createElement("div");
    let _0x468fbd = document.createElement("button");
    _0x468fbd.className = "btnEdit";
    _0x468fbd.onclick = function (_0x313ecf) {
      if (!isRS) {
        document.querySelector("label[for=\"advTypeRadio4\"]")?.remove();
      }
      if (!isRKRT) {
        document.querySelector("label[for=\"advTypeRadio5\"]")?.remove();
      }
      _0x334b40.style.display = "block";
      curAdvIndex = _0x45eb02.index;
      curTglKey = undefined;
      curMtKey = undefined;
      curDksKey = undefined;
      curRSKey = undefined;
      curRKRTKey = undefined;
      if (_0x45eb02.type === "TGL") {
        curTglKey = deepCopy(_0x45eb02);
        _0x17afc5.checked = true;
        _0x30b585.innerText = getI18n("advTip3");
        _0x15bed2.style.display = "flex";
        _0x3cbf0e.style.display = "none";
        _0x3fc6a0.style.display = "none";
        _0x4c3398.style.display = "none";
        _0x5b29fb.style.display = "none";
        _0x167d73.value = _0x45eb02.keys[0].name;
        _0x167d73.classList.remove("tglTmInputFocus");
        curEdit = undefined;
      }
      if (_0x45eb02.type === "RKRT") {
        curRKRTKey = deepCopy(_0x45eb02);
        advTypeRadio5.checked = true;
        _0x30b585.innerText = getI18n("advTip5");
        _0x15bed2.style.display = "none";
        _0x3cbf0e.style.display = "none";
        _0x3fc6a0.style.display = "none";
        _0x4c3398.style.display = "none";
        _0x5b29fb.style.display = "flex";
        _0x5d7921.value = _0x45eb02.keys[1].name;
        _0x5d7921.classList.remove("tglTmInputFocus");
        curEdit = undefined;
      }
      if (_0x45eb02.type === "RS") {
        curRSKey = deepCopy(_0x45eb02);
        advTypeRadio4.checked = true;
        _0x30b585.innerText = getI18n("advTip4");
        _0x15bed2.style.display = "none";
        _0x3cbf0e.style.display = "none";
        _0x3fc6a0.style.display = "none";
        _0x4c3398.style.display = "flex";
        _0x5b29fb.style.display = "none";
        _0x31d956.value = _0x45eb02.keys[0].name;
        _0x1fde2b.value = _0x45eb02.keys[1].name;
        _0x31d956.classList.remove("tglTmInputFocus");
        _0x1fde2b.classList.remove("tglTmInputFocus");
        curEdit = undefined;
      }
      if (_0x45eb02.type === "MT") {
        curMtKey = deepCopy(_0x45eb02);
        _0x57a436.checked = true;
        _0x30b585.innerText = getI18n("advTip2");
        _0x15bed2.style.display = "none";
        _0x3cbf0e.style.display = "flex";
        _0x3fc6a0.style.display = "none";
        _0x4c3398.style.display = "none";
        _0x5b29fb.style.display = "none";
        _0x52d11e.value = _0x45eb02.keys[0].name;
        _0x574304.value = _0x45eb02.keys[1].name;
        _0x5b2967.value = _0x45eb02.duration;
        _0x5b2967.dispatchEvent(new Event("input"));
        _0x52d11e.classList.remove("tglTmInputFocus");
        _0x574304.classList.remove("tglTmInputFocus");
        curEdit = undefined;
      }
      if (_0x45eb02.type === "DKS") {
        curDksKey = deepCopy(_0x45eb02);
        _0x3b91b5.checked = true;
        _0x30b585.innerText = getI18n("advTip1");
        _0x15bed2.style.display = "none";
        _0x3cbf0e.style.display = "none";
        _0x3fc6a0.style.display = "flex";
        _0x4c3398.style.display = "none";
        _0x5b29fb.style.display = "none";
        refreshDksButton();
        _0x1e5fab.innerText = (_0x45eb02.route1 / 10).toFixed(1) + "mm";
        if (curDevice.product === "MKGA75HEARGB") {
          _0x201177.innerText = "3.2mm";
          _0x195aa5.innerText = "3.2mm";
        } else {
          _0x201177.innerText = (_0x45eb02.route2 / 10).toFixed(1) + "mm";
          _0x195aa5.innerText = (_0x45eb02.route3 / 10).toFixed(1) + "mm";
        }
        _0x5a1b57.innerText = (_0x45eb02.route4 / 10).toFixed(1) + "mm";
        _0x387b7d.value = _0x45eb02.keys[0].name;
        _0x294f3f.value = _0x45eb02.keys[1].name;
        _0x2457f8.value = _0x45eb02.keys[2].name;
        _0x400701.value = _0x45eb02.keys[3].name;
        _0x387b7d.classList.remove("tglTmInputFocus");
        _0x294f3f.classList.remove("tglTmInputFocus");
        _0x2457f8.classList.remove("tglTmInputFocus");
        _0x400701.classList.remove("tglTmInputFocus");
        curEdit = undefined;
      }
      _0x313ecf.stopPropagation();
    };
    let _0x48c11b = document.createElement("button");
    _0x48c11b.className = "btnDelete";
    _0x48c11b.onclick = function (_0x11014f) {
      let _0x34a591 = advKeys.indexOf(_0x45eb02);
      if (_0x34a591 >= 0 && _0x34a591 < advKeys.length) {
        advKeys.splice(_0x34a591, 1);
        if (_0x45eb02.type === "RS" || _0x45eb02.type === "RKRT") {
          _0x45eb02.keys.forEach(_0x5568d0 => {
            let _0x1e8b91 = findDeviceKey(_0x5568d0.name, "name");
            if (_0x1e8b91) {
              recKeys.delete(_0x1e8b91.index);
            }
          });
        }
        recKeys.forEach((_0x351b78, _0x430c84) => {
          if (_0x351b78.code1 === 23 && _0x351b78.code3 === _0x45eb02.index) {
            recKeys.delete(_0x430c84);
            if (curKey !== undefined && curKey.index === _0x430c84) {
              recordInput.value = curKey.name;
            }
          }
        });
        fnKeys.forEach((_0x2686a6, _0x5d8c14) => {
          if (_0x2686a6.code1 === 23 && _0x2686a6.code3 === _0x45eb02.index) {
            fnKeys.delete(_0x5d8c14);
            if (curKey !== undefined && curKey.index === _0x5d8c14) {
              recordInput.value = curKey.name;
            }
          }
        });
        refreshRecordDot();
        curProfile.advKeys = deepCopy(advKeys);
        let _0x24e148 = JSON.stringify(profileSet, replacer);
        localStorage.setItem(curDevice.product, _0x24e148);
        btnApplyKey.dispatchEvent(new Event("click"));
      }
      refreshAdvList();
      _0x11014f.stopPropagation();
    };
    _0x2bde72.appendChild(_0x468fbd);
    _0x2bde72.appendChild(_0x48c11b);
    _0x2bde72.style.display = "none";
    _0x5a5ec6.appendChild(_0x1679c4);
    _0x5a5ec6.appendChild(_0x2bde72);
    _0x5a5ec6.onmouseenter = function () {
      _0x2bde72.style.display = "flex";
    };
    _0x5a5ec6.onmouseleave = function () {
      _0x2bde72.style.display = "none";
    };
    _0x5a5ec6.onclick = function () {
      if (curKey !== undefined) {
        if (_0x45eb02.type === "RS" || _0x45eb02.type === "RKRT") {
          const _0x54263c = curProfile.advKeys?.some(_0xa6965a => _0xa6965a.type === "RS" && _0xa6965a.keys.some(_0x591645 => _0x591645.code === curKey.code));
          if (_0x54263c) {
            return showAlert(getI18n("rsTip2"));
          }
          if (_0x45eb02.type === "RS" && _0x45eb02.keys[0].name && _0x45eb02.keys[1].name) {
            return showAlert(getI18n("rsTip2"));
          }
          if (curProfile.advKeys[_0x45eb02.index]) {
            if (curKey.hidCode === _0x45eb02.keys[1].hidCode && _0x45eb02.type === "RS") {
              showAlert(getI18n("rsTip1"));
              return;
            }
            if (_0x45eb02.keys[0].name && _0x45eb02.keys[0].name !== curKey.name && _0x45eb02.type === "RKRT") {
              recKeys.delete(_0x45eb02.keys[0].index);
            }
          }
          if (_0x45eb02.type === "RKRT") {
            _0x45eb02.keys[0] = curKey;
          }
          if (_0x45eb02.type === "RS") {
            if (_0x45eb02.keys[0].name) {
              if (!_0x45eb02.keys[1].name) {
                _0x45eb02.keys[1] = curKey;
              }
            } else {
              _0x45eb02.keys[0] = curKey;
            }
          }
        }
        let _0x5362ca = new Key();
        _0x5362ca.code1 = 23;
        _0x5362ca.hidCode = _0x45eb02.index;
        _0x5362ca.code3 = _0x45eb02.index;
        _0x5362ca.name = _0x3f2955;
        recordInput.value = _0x5362ca.name;
        if (keymapDef.checked) {
          recKeys.set(curKey.index, _0x5362ca);
        }
        if (keymapFn.checked) {
          fnKeys.set(curKey.index, _0x5362ca);
        }
        refreshRecordDot();
        if (confirm(getI18n("applyTip2"))) {
          btnApplyKey.dispatchEvent(new Event("click"));
        }
      }
    };
    _0xd425b0.appendChild(_0x5a5ec6);
  });
  let _0x310bb7 = document.createElement("button");
  _0x310bb7.className = "addButton";
  _0x310bb7.onclick = function () {
    if (!isRS) {
      document.querySelector("label[for=\"advTypeRadio4\"]")?.remove();
    }
    if (!isRKRT) {
      document.querySelector("label[for=\"advTypeRadio5\"]")?.remove();
    }
    if (advKeys.length < 40) {
      _0x334b40.style.display = "block";
      curDksKey = new AdvancedKey();
      curDksKey.route1 = 15;
      if (curDevice.product === "MKGA75HEARGB") {
        curDksKey.route2 = 32;
        curDksKey.route3 = 32;
      } else {
        curDksKey.route2 = curDevice.maxTriggerTravel * curDevice.triggerUnit * 10 - 4;
        curDksKey.route3 = curDevice.maxTriggerTravel * curDevice.triggerUnit * 10 - 4;
      }
      curDksKey.route4 = 15;
      curDksKey.duration = 15;
      curMtKey = new AdvancedKey();
      curMtKey.duration = 15;
      curTglKey = new AdvancedKey();
      curRSKey = new AdvancedKey();
      curRKRTKey = new AdvancedKey();
      _0x3b91b5.checked = true;
      _0x3b91b5.dispatchEvent(new Event("change"));
    } else {
      showAlert(getI18n("alertAdvWarning"));
    }
  };
  _0xd425b0.appendChild(_0x310bb7);
}
function refreshPerformanceView(_0x35cd90, _0x21c33d) {
  if (_0x21c33d) {
    curProfile.other = _0x35cd90;
  }
  let _0x18d946 = _0x35cd90 & 1;
  let _0x5e5299 = _0x35cd90 >> 1 & 1;
  let _0x27e29b = _0x35cd90 >> 2 & 1;
  let _0x423824 = _0x35cd90 >> 3 & 1;
  document.getElementById("perCheckbox1").checked = _0x18d946 === 1;
  document.getElementById("perCheckbox2").checked = _0x5e5299 === 1;
  document.getElementById("perCheckbox4").checked = _0x27e29b === 1;
  document.getElementById("perCheckbox3").checked = _0x423824 === 1;
}
async function refreshDeviceList() {
  if ("navigator" in window && "hid" in navigator) {
    let _0x26aee0 = await navigator.hid.getDevices();
    if (_0x26aee0 != null && _0x26aee0.length > 0) {
      deviceInitialization(_0x26aee0);
    }
  }
}
async function initFixedKeys(_0x162146) {
  await fetch(_0x162146 || "../config/keys.json").then(_0x5b0df7 => _0x5b0df7.json()).then(_0x50fefb => {
    fixedKeys = [];
    for (let _0x488350 in _0x50fefb) {
      let _0x592d94 = _0x50fefb[_0x488350];
      if (_0x592d94 !== undefined) {
        for (let _0x4e5411 in _0x592d94) {
          let _0x56db07 = _0x592d94[_0x4e5411];
          if (_0x56db07 === undefined) {
            continue;
          }
          if (_0x56db07.name === "Expand" && curCompany === "sanpin_glick") {
            _0x56db07.keys.splice(-5, 5);
          }
          let _0x51aafb = new KeySet();
          _0x51aafb.name = _0x56db07.name;
          let _0x446958 = _0x56db07.keys;
          if (_0x446958 !== undefined) {
            _0x446958.forEach(function (_0x35e08c) {
              let _0x59e113 = new Key();
              _0x59e113.name = _0x35e08c.name;
              _0x59e113.code = _0x35e08c.code;
              _0x59e113.code1 = parseInt(_0x35e08c.code1, 16);
              _0x59e113.hidCode = parseInt(_0x35e08c.hidCode, 16);
              _0x59e113.code3 = parseInt(_0x35e08c.code3, 16);
              _0x59e113.code4 = parseInt(_0x35e08c.code4, 16);
              _0x59e113.width = _0x35e08c.width;
              _0x59e113.height = _0x35e08c.height;
              _0x51aafb.keys.push(_0x59e113);
            });
          }
          fixedKeys.push(_0x51aafb);
        }
      }
    }
    console.log(fixedKeys);
  }).catch(_0x15fc0a => console.error("Error reading JSON file:", _0x15fc0a));
}
async function readConfig() {
  try {
    const _0x36e63b = await fetch("../config/device.json?t=" + Math.floor(new Date().getTime() / 1000));
    const _0xe4ae6a = await _0x36e63b.json();
    devList = [];
    for (let _0x558c55 in _0xe4ae6a) {
      let _0x9a1ba6 = _0xe4ae6a[_0x558c55];
      if (_0x9a1ba6 !== undefined) {
        for (let _0x55492f in _0x9a1ba6) {
          let _0x1d87d5 = _0x9a1ba6[_0x55492f];
          if (_0x1d87d5 === undefined) {
            continue;
          }
          let _0x5a1ca1 = new Device();
          _0x5a1ca1.name = _0x1d87d5.name;
          _0x5a1ca1.product = _0x1d87d5.product;
          _0x5a1ca1.company = _0x1d87d5.company;
          _0x5a1ca1.title = _0x1d87d5.title;
          _0x5a1ca1.logoType = parseInt(_0x1d87d5.logoType);
          _0x5a1ca1.vid = parseInt(_0x1d87d5.vid);
          _0x5a1ca1.pid = parseInt(_0x1d87d5.pid);
          _0x5a1ca1.width = parseInt(_0x1d87d5.width);
          _0x5a1ca1.height = parseInt(_0x1d87d5.height);
          _0x5a1ca1.hasLight = _0x1d87d5.hasLight;
          devList.push(_0x5a1ca1);
        }
      }
    }
    await sleep(600);
    await refreshDeviceList();
  } catch (_0x44e204) {
    console.error(_0x44e204);
  }
}
async function readKeys(_0x3dc9d3) {
  try {
    const _0x61ecc7 = await fetch("../config/keys/" + _0x3dc9d3 + ".json?t=v1");
    const _0x34a8b2 = await _0x61ecc7.json();
    curDevice.keys = [];
    let _0x4c6e11 = _0x34a8b2.type;
    if (_0x4c6e11 == null) {
      _0x4c6e11 = "us";
    }
    curDevice.type = _0x4c6e11;
    _0x34a8b2.keys.forEach(function (_0x3fed5f) {
      let _0x4a0758 = new Key();
      _0x4a0758.index = parseInt(_0x3fed5f.index);
      _0x4a0758.name = _0x3fed5f.name;
      _0x4a0758.code = _0x3fed5f.code;
      _0x4a0758.code1 = _0x3fed5f.code1;
      _0x4a0758.hidCode = parseInt(_0x3fed5f.hidCode, 16);
      _0x4a0758.width = parseInt(_0x3fed5f.width);
      _0x4a0758.height = parseInt(_0x3fed5f.height);
      _0x4a0758.x = _0x3fed5f.x;
      _0x4a0758.y = _0x3fed5f.y;
      curDevice.keys.push(_0x4a0758);
    });
  } catch (_0x28d5b8) {
    console.error(_0x28d5b8);
  }
}
function initGameKeyView(_0x98ba58) {
  if (_0x98ba58 === "gamePad1") {
    document.querySelectorAll(".keySet .btn").forEach(_0x478881 => {
      _0x478881.style.cursor = "not-allowed";
      _0x478881.addEventListener("click", function (_0x56b8dc) {
        _0x56b8dc.stopPropagation();
        _0x56b8dc.preventDefault();
        console.log("点击被禁止");
      });
    });
    return;
  }
  let _0x589268 = _0x98ba58 === "gamePad2" ? gamePadXbox360 : gamePadClasical;
  const _0x355825 = document.getElementById("gameSetLeft");
  _0x355825.innerHTML = "";
  let _0x38fa03 = document.createElement("div");
  _0x38fa03.className = "titleDiv";
  let _0x43df9a = document.createElement("label");
  _0x43df9a.innerHTML = getI18n(_0x98ba58 === "gamePad2" ? "Xbox" : "Classical");
  _0x43df9a.setAttribute("i18n", _0x98ba58 === "gamePad2" ? "Xbox" : "Classical");
  _0x38fa03.appendChild(_0x43df9a);
  _0x355825.appendChild(_0x38fa03);
  let _0x1c387c = document.createElement("div");
  _0x1c387c.className = "keySet";
  let _0x1e0aab = document.createElement("div");
  _0x1e0aab.className = "keySet";
  _0x589268.forEach(_0x349be0 => {
    let _0x36951d = document.createElement("div");
    _0x36951d.classList.add("btn");
    let _0x1bc5e1 = document.createElement("img");
    if (_0x349be0.icon) {
      _0x1bc5e1.src = "image/" + _0x349be0.icon + ".png";
    }
    _0x1bc5e1.alt = getI18n(_0x349be0.code);
    _0x1bc5e1.title = _0x1bc5e1.alt;
    let _0x2f04ec = document.createElement("button");
    _0x2f04ec.className = "tooltip";
    _0x2f04ec.setAttribute("i18n", _0x349be0.code);
    _0x2f04ec.textContent = _0x1bc5e1.alt;
    _0x36951d.appendChild(_0x1bc5e1);
    _0x36951d.appendChild(_0x2f04ec);
    let _0x4b32ac = _0x349be0.name;
    _0x36951d.onclick = function () {
      if (curKey !== undefined) {
        console.log(_0x4b32ac, _0x349be0);
        recordInput.value = getI18n(_0x349be0.code);
        _0x355825.querySelectorAll(".btn").forEach(_0x32b890 => {
          _0x32b890.style.borderColor = "var(--border-color)";
        });
        _0x36951d.style.borderColor = "var(--btn-ckBgColor)";
        let _0x227fcf = new Key();
        _0x227fcf.name = _0x4b32ac;
        _0x227fcf.code = _0x349be0.code;
        _0x227fcf.code1 = _0x349be0.code1;
        _0x227fcf.hidCode = _0x349be0.hidCode;
        _0x227fcf.code3 = _0x349be0.code3;
        _0x227fcf.code4 = _0x349be0.code4;
        if (keymapDef.checked) {
          recKeys.set(curKey.index, _0x227fcf);
        }
        if (keymapFn.checked) {
          fnKeys.set(curKey.index, _0x227fcf);
        }
        refreshRecordDot();
        if (confirm(getI18n("applyTip2"))) {
          btnApplyKey.dispatchEvent(new Event("click"));
        }
      }
    };
    if (_0x349be0.group === 1) {
      _0x1c387c.appendChild(_0x36951d);
    } else if (_0x349be0.group === 2) {
      _0x1e0aab.appendChild(_0x36951d);
    } else {
      _0x1c387c.appendChild(_0x36951d);
    }
  });
  _0x355825.appendChild(_0x1c387c);
  _0x355825.appendChild(_0x1e0aab);
}
function initFixedKeyView(_0xfbca75, _0x5d925f) {
  _0xfbca75.innerHTML = "";
  for (let _0x4eddab = 0; _0x4eddab < fixedKeys.length; _0x4eddab++) {
    const _0x1ff951 = fixedKeys[_0x4eddab];
    if (!curDevice.hasLight && _0x1ff951.name === "KeyboardLight") {
      continue;
    }
    let _0x1f74cc = document.createElement("div");
    _0x1f74cc.className = _0x1ff951.name;
    if (_0x4eddab === 0 && _0x5d925f !== 1) {
      _0x1f74cc.style.marginTop = "0";
    }
    let _0x5ef829 = document.createElement("div");
    _0x5ef829.className = "titleDiv";
    let _0x12bb19 = document.createElement("div");
    _0x12bb19.className = "fixedTitleDiv";
    let _0x5690b0 = document.createElement("img");
    _0x5690b0.src = theme === "light" ? "image/icon_arrow2.png" : "image/dark/icon_arrow2.png";
    _0x5690b0.setAttribute("isOpen", "true");
    let _0x2ef0f1 = document.createElement("label");
    _0x2ef0f1.setAttribute("i18n", _0x1ff951.name);
    _0x2ef0f1.innerText = getI18n(_0x1ff951.name);
    _0x12bb19.appendChild(_0x5690b0);
    _0x12bb19.appendChild(_0x2ef0f1);
    _0x5ef829.appendChild(_0x12bb19);
    _0x1f74cc.appendChild(_0x5ef829);
    let _0x1a352f = document.createElement("div");
    _0x1a352f.className = "keySetDiv";
    _0x1a352f.style.display = "flex";
    _0x1ff951.keys.forEach(function (_0x30476e) {
      let _0x4d824d = document.createElement("button");
      if (_0x30476e.code1 !== 0) {
        _0x4d824d.setAttribute("i18n", _0x30476e.code);
      }
      if (["en", "kr", "jp", "tr", "pt-br", "de", "es", "fr"].includes(i18n) && _0x30476e.code1 !== 0) {
        _0x4d824d.className = "fixedKeyButton2";
      } else {
        _0x4d824d.className = "fixedKeyButton1";
      }
      _0x4d824d.innerText = _0x30476e.name;
      _0x4d824d.onclick = function () {
        if (_0x5d925f === 0 && curKey !== undefined) {
          initRecordKeys(1, _0x30476e);
          let _0x3652ee = _0x30476e.code1 > 0 ? getI18n(_0x30476e.code) : _0x30476e.name;
          if (document.getElementById("keyManu2").checked) {
            _0x3652ee = "";
            for (let _0x16eda1 = 0; _0x16eda1 < comKeys.length; _0x16eda1++) {
              let _0xebc32e = comKeys[_0x16eda1];
              _0x3652ee += _0x16eda1 === 0 ? _0xebc32e.name : " + " + _0xebc32e.name;
            }
            if (hasCtrKey() && hasDefKey()) {
              let _0x4d5e74 = new Key();
              _0x4d5e74.name = _0x3652ee;
              _0x4d5e74.code1 = 19;
              _0x4d5e74.hidCode = comKeys.length > 0 ? comKeys[0].hidCode : 0;
              _0x4d5e74.code3 = comKeys.length > 1 ? comKeys[1].hidCode : 0;
              _0x4d5e74.code4 = comKeys.length > 2 ? comKeys[2].hidCode : 0;
              if (keymapDef.checked) {
                recKeys.set(curKey.index, _0x4d5e74);
              }
              if (keymapFn.checked) {
                fnKeys.set(curKey.index, _0x4d5e74);
              }
              refreshRecordDot();
            }
          }
          recordInput.value = _0x3652ee;
        }
        if (_0x5d925f === 1 && curEdit !== undefined) {
          curEdit.value = _0x30476e.name;
          let _0x43014b = findDeviceKey(_0x30476e.name, "name");
          if (curEdit.id === "tglEdit") {
            curTglKey.keys[0] = _0x30476e;
          }
          if (curEdit.id === "mtEdit1") {
            curMtKey.keys[0] = _0x30476e;
          }
          if (curEdit.id === "mtEdit2") {
            curMtKey.keys[1] = _0x30476e;
          }
          if (curEdit.id === "dksEdit1") {
            curDksKey.keys[0] = _0x30476e;
          }
          if (curEdit.id === "dksEdit2") {
            curDksKey.keys[1] = _0x30476e;
          }
          if (curEdit.id === "dksEdit3") {
            curDksKey.keys[2] = _0x30476e;
          }
          if (curEdit.id === "dksEdit4") {
            curDksKey.keys[3] = _0x30476e;
          }
          if (curEdit.id === "rsEdit1") {
            if (curRSKey.keys[1] && curRSKey.keys[1].name === _0x30476e.name || !_0x43014b) {
              curEdit.value = "";
              curRSKey.keys[0] = new _0x30476e();
              return showAlert(getI18n(_0x43014b ? "rsTip2" : "rsTip3"));
            }
            curRSKey.keys[0] = _0x30476e;
          }
          if (curEdit.id === "rsEdit2") {
            if (curRSKey.keys[0] && curRSKey.keys[0].name === _0x30476e.name || !_0x43014b) {
              curEdit.value = "";
              curRSKey.keys[1] = new _0x30476e();
              return showAlert(getI18n(_0x43014b ? "rsTip2" : "rsTip3"));
            }
            curRSKey.keys[1] = _0x30476e;
          }
          if (curEdit.id === "rkrtEdit") {
            if (!_0x43014b) {
              curEdit.value = "";
              curRSKey.keys[1] = new _0x30476e();
              return showAlert(getI18n("rsTip3"));
            }
            curRKRTKey.keys[1] = _0x30476e;
          }
        }
        if (_0x5d925f === 2 && curEdit !== undefined) {
          curEdit.value = _0x30476e.name;
          if (curEdit.id === "piEdit1") {
            curPrcs.key1 = _0x30476e;
          }
          if (curEdit.id === "piEdit2") {
            curPrcs.key2 = _0x30476e;
          }
        }
        if (!document.getElementById("keyManu2").checked && _0x5d925f === 0 && curKey !== undefined) {
          if (confirm(getI18n("applyTip2"))) {
            btnApplyKey.dispatchEvent(new Event("click"));
          }
        }
      };
      _0x1a352f.appendChild(_0x4d824d);
    });
    _0x1f74cc.appendChild(_0x1a352f);
    _0x12bb19.onclick = function () {
      if (_0x5690b0.getAttribute("isOpen") === "true") {
        _0x1a352f.style.display = "none";
        _0x5690b0.src = theme === "light" ? "image/icon_arrow1.png" : "image/dark/icon_arrow1.png";
        _0x5690b0.setAttribute("isOpen", "false");
      } else {
        _0x1a352f.style.display = "flex";
        _0x5690b0.src = theme === "light" ? "image/icon_arrow2.png" : "image/dark/icon_arrow2.png";
        _0x5690b0.setAttribute("isOpen", "true");
      }
    };
    if (_0x5d925f === 1 || _0x5d925f === 2) {
      if (_0x1ff951.name === "Default" || _0x1ff951.name === "Expand") {
        if (_0x1ff951.name === "Expand") {
          let _0x20f99c = document.createElement("div");
          _0x20f99c.className = "spacer";
          _0x20f99c.style.height = "40px";
          _0x1f74cc.appendChild(_0x20f99c);
        }
        _0xfbca75.appendChild(_0x1f74cc);
      }
    } else {
      if (curDevice.hasLight) {
        if (_0x1ff951.name === "Expand") {
          let _0x2abf29 = document.createElement("div");
          _0x2abf29.className = "spacer";
          _0x2abf29.style.height = "0px";
          _0x1f74cc.appendChild(_0x2abf29);
        }
        if (_0x1ff951.name === "KeyboardLight") {
          let _0x5bb7c7 = document.createElement("div");
          _0x5bb7c7.className = "spacer";
          _0x5bb7c7.style.height = "40px";
          _0x1f74cc.appendChild(_0x5bb7c7);
        }
      } else if (_0x1ff951.name === "Special") {
        let _0x264f87 = document.createElement("div");
        _0x264f87.className = "spacer";
        _0x264f87.style.height = "40px";
        _0x1f74cc.appendChild(_0x264f87);
      }
      _0xfbca75.appendChild(_0x1f74cc);
    }
  }
}
function findFixedKey(_0x4572c4) {
  let _0x152855;
  let _0x3c8c4b = false;
  for (const _0x30bd94 of fixedKeys) {
    for (const _0x7d3e31 of _0x30bd94.keys) {
      if (_0x7d3e31.code === _0x4572c4) {
        _0x3c8c4b = true;
        _0x152855 = _0x7d3e31;
        break;
      }
    }
    if (_0x3c8c4b) {
      break;
    }
  }
  return _0x152855;
}
function findFixedKeyByHidCode(_0x411799) {
  let _0x138644;
  let _0x4b169c = false;
  for (const _0x59a4b9 of fixedKeys) {
    for (const _0x231386 of _0x59a4b9.keys) {
      if (_0x231386.code1 === 0 && _0x231386.hidCode === _0x411799) {
        _0x4b169c = true;
        _0x138644 = _0x231386;
        break;
      }
    }
    if (_0x4b169c) {
      break;
    }
  }
  return _0x138644;
}
function findFixedKeyByHid(_0x23f0d5, _0x4276ac, _0x369753) {
  let _0x39c624;
  if (_0x23f0d5 === 0 && _0x4276ac === 250) {
    _0x39c624 = new Key();
    _0x39c624.name = "Fn";
    _0x39c624.code1 = _0x23f0d5;
    _0x39c624.hidCode = _0x4276ac;
  } else {
    let _0x1d1c70 = false;
    for (const _0x1dc215 of fixedKeys) {
      for (const _0x5984e8 of _0x1dc215.keys) {
        if (_0x5984e8.code1 === _0x23f0d5 && _0x5984e8.hidCode === _0x4276ac) {
          if (_0x369753 && _0x5984e8[_0x369753.key] !== _0x369753.value) {
            continue;
          }
          _0x1d1c70 = true;
          _0x39c624 = _0x5984e8;
          break;
        }
      }
      if (_0x1d1c70) {
        break;
      }
    }
  }
  return _0x39c624;
}
function findDeviceKey(_0x36327b, _0x24c0df = "code") {
  let _0x12bb8a;
  if (curDevice !== undefined) {
    for (const _0x258f87 of curDevice.keys) {
      if (_0x258f87[_0x24c0df] === _0x36327b) {
        _0x12bb8a = _0x258f87;
        break;
      }
    }
  }
  return _0x12bb8a;
}
function findGamPadKey(_0x3dc91f, _0x5611b4) {
  if (_0x3dc91f === 24) {
    return gamePadClasical.find(_0x50fe94 => _0x50fe94.code1 === _0x3dc91f && _0x50fe94.hidCode === _0x5611b4);
  } else if (_0x3dc91f === 25) {
    return gamePadXbox360.find(_0x299f80 => _0x299f80.code1 === _0x3dc91f && _0x299f80.hidCode === _0x5611b4);
  } else {
    return null;
  }
}
function refreshKeyButton(_0x487ebf) {
  let _0x5ae7c8 = document.getElementById("triggerManu1");
  let _0xdf6dd5 = document.getElementById("triggerManu5");
  const _0x9d241a = keyBtn.find(_0x23a596 => _0x23a596.htmlFor === _0x487ebf.code);
  if (_0x9d241a != null && _0x9d241a.htmlFor === _0x487ebf.code) {
    if (_0x5ae7c8.checked) {
      if (_0x487ebf.trigger.mode === 0) {
        _0x9d241a.querySelector("[class=devKeyTI1]").style.display = "none";
        _0x9d241a.querySelector("[class=devKeyTI2]").style.display = "none";
      }
      if (_0x487ebf.trigger.mode === 12) {
        _0x9d241a.querySelector("[class=devKeyTI1]").style.display = "flex";
        _0x9d241a.querySelector("[class=devKeyTI1]").style.color = "var(--text-color2)";
        _0x9d241a.querySelector("[class=devKeyTI2]").style.display = "flex";
        _0x9d241a.querySelector("[class=devKeyTI2]").style.color = "var(--text-color2)";
      }
      if (_0x487ebf.trigger.mode === 13) {
        _0x9d241a.querySelector("[class=devKeyTI1]").style.display = "flex";
        _0x9d241a.querySelector("[class=devKeyTI1]").style.color = "var(--text-color2)";
        _0x9d241a.querySelector("[class=devKeyTI2]").style.display = "flex";
        _0x9d241a.querySelector("[class=devKeyTI2]").style.color = "var(--text-color3)";
      }
      let _0x53264f = (_0x487ebf.trigger.travel * curDevice.triggerUnit).toFixed(unitNum);
      let _0x299aba = (_0x487ebf.trigger.interval1 * curDevice.triggerUnit).toFixed(unitNum);
      let _0x517f24 = (_0x487ebf.trigger.interval2 * curDevice.triggerUnit).toFixed(unitNum);
      _0x9d241a.querySelector("[class=devKeyTV]").innerText = _0x53264f;
      _0x9d241a.querySelector("[class=devKeyTI1]").innerText = _0x299aba;
      _0x9d241a.querySelector("[class=devKeyTI2]").innerText = _0x517f24;
    }
    if (_0xdf6dd5.checked) {
      _0x9d241a.querySelector("[class=devKeyTI1]").style.display = "flex";
      _0x9d241a.querySelector("[class=devKeyTI1]").style.color = "var(--text-color2)";
      _0x9d241a.querySelector("[class=devKeyTI2]").style.display = "flex";
      _0x9d241a.querySelector("[class=devKeyTI2]").style.color = "var(--text-color3)";
      let _0x3223c7 = (_0x487ebf.trigger.deadbandTop * curDevice.triggerUnit).toFixed(unitNum);
      let _0x4726b4 = (_0x487ebf.trigger.deadbandBottom * curDevice.triggerUnit).toFixed(unitNum);
      _0x9d241a.querySelector("[class=devKeyTV]").innerText = "";
      _0x9d241a.querySelector("[class=devKeyTI1]").innerText = _0x3223c7;
      _0x9d241a.querySelector("[class=devKeyTI2]").innerText = _0x4726b4;
    }
  }
}
function refreshCheckedKeys(_0x3ff22c, _0x20baae, _0x5c0c07) {
  if (_0x5c0c07) {
    refreshTriggerValue(_0x3ff22c, _0x20baae);
    checkedKeys.push(_0x20baae);
  } else {
    let _0x20c167 = checkedKeys.findIndex(_0x3c600a => _0x3c600a.code === _0x20baae.code);
    if (_0x20c167 !== -1) {
      checkedKeys.splice(_0x20c167, 1);
    }
  }
  document.getElementById("triggerPower").disabled = checkedKeys.length === 0;
  if (checkedKeys.length === 0) {
    document.getElementById("triggerPower").checked = false;
    refreshTriggerView(false);
  }
  refreshTriggerAllView();
}
function refreshProfileTrigger() {
  if (curDevice !== undefined && curDevice !== null) {
    curProfile.triggers.clear();
    curDevice.keys.forEach(_0x4a5b33 => {
      curProfile.triggers.set(_0x4a5b33.index, _0x4a5b33.trigger);
    });
    let _0x4b79e0 = JSON.stringify(profileSet, replacer);
    localStorage.setItem(curDevice.product, _0x4b79e0);
  }
}
function refreshTriggerAllView() {
  let _0x319cc5 = document.getElementById("triggerManu1");
  let _0x33bd36 = document.getElementById("triggerManu5");
  if (_0x319cc5.checked) {
    if (checkedKeys.length > 0) {
      triggerAll.setAttribute("disabled", false);
      if (checkedTip !== undefined && checkedTip !== null) {
        checkedTip.style.display = "block";
      }
    } else {
      triggerAll.setAttribute("disabled", true);
      if (checkedTip !== undefined && checkedTip !== null) {
        checkedTip.style.display = "none";
      }
    }
  }
  if (_0x33bd36.checked) {
    if (checkedKeys.length > 0) {
      dbTop.setAttribute("disabled", false);
      dbBottom.setAttribute("disabled", false);
      if (checkedTip !== undefined && checkedTip !== null) {
        checkedTip.style.display = "block";
      }
    } else {
      dbTop.setAttribute("disabled", true);
      dbBottom.setAttribute("disabled", true);
      if (checkedTip !== undefined && checkedTip !== null) {
        checkedTip.style.display = "none";
      }
    }
  }
}
function refreshTriggerView(_0x42fdfe) {
  if (_0x42fdfe) {
    document.getElementById("triggerDownAndUp").style.display = "flex";
    document.getElementById("labelTip2").style.display = "flex";
    document.getElementById("labelTitle1").style.display = "flex";
    triggerDown.style.display = "flex";
  } else {
    document.getElementById("triggerTravel").checked = false;
    document.getElementById("triggerDownAndUp").style.display = "none";
    document.getElementById("labelTip2").style.display = "none";
    document.getElementById("labelTitle1").style.display = "none";
    triggerDown.style.display = "none";
    document.getElementById("labelTitle2").style.display = "none";
    triggerUp.style.display = "none";
    refreshTriggerTravel(false);
  }
}
function refreshTriggerTravel(_0x2d2a68) {
  if (_0x2d2a68) {
    document.getElementById("labelTitle1").innerText = getI18n("triggerMenu3_Open");
    document.getElementById("labelTitle2").style.display = "flex";
    triggerUp.style.display = "flex";
  } else {
    document.getElementById("labelTitle1").innerText = getI18n("triggerMenu3");
    document.getElementById("labelTitle2").style.display = "none";
    triggerUp.style.display = "none";
  }
}
function refreshTriggerValue(_0x303bf2, _0x1231e9) {
  let _0x1e69ed = document.getElementById("triggerManu1");
  let _0x157dc5 = document.getElementById("triggerManu5");
  if (_0x1e69ed.checked) {
    let _0xf63119 = document.getElementById("triggerPower");
    let _0x23ca4d = document.getElementById("triggerTravel");
    if (_0x1231e9.trigger.mode === 0) {
      _0xf63119.checked = false;
    } else if (_0x1231e9.trigger.mode > 0) {
      _0xf63119.checked = true;
      _0x23ca4d.checked = _0x1231e9.trigger.mode === 13;
      triggerDown.setAttribute("value", _0x1231e9.trigger.interval1);
      triggerUp.setAttribute("value", _0x1231e9.trigger.interval2);
    }
    refreshTriggerView(_0xf63119.checked);
    refreshTriggerTravel(_0x23ca4d.checked);
    refreshTriggerAllView();
  }
  if (_0x157dc5.checked) {
    dbTop.setAttribute("value", _0x1231e9.trigger.deadbandTop);
    dbBottom.setAttribute("value", _0x1231e9.trigger.deadbandBottom);
  }
}
function refreshAllTrigger(_0x35234c) {
  if (curDevice !== null && curDevice !== undefined) {
    curDevice.keys.forEach(_0x941242 => {
      let _0x4542b1 = _0x35234c.get(_0x941242.index);
      if (_0x4542b1 == null) {
        _0x4542b1 = new Trigger();
        _0x4542b1.mode = 0;
        _0x4542b1.travel = Math.floor(curDevice.maxTriggerTravel / 2);
        _0x4542b1.interval1 = 5;
        _0x4542b1.interval2 = 5;
      }
      _0x941242.trigger = _0x4542b1;
      refreshKeyButton(_0x941242);
    });
  }
}
function refreshSwitchList() {
  const _0x250d51 = document.getElementById("switchListView");
  _0x250d51.innerHTML = "";
  switchList.forEach(_0x3abc50 => {
    let _0x26234d = document.createElement("button");
    let _0x8acd65 = document.createElement("span");
    _0x8acd65.className = "switchTop";
    let _0x3658c2 = document.createElement("label");
    _0x3658c2.innerText = _0x3abc50.title;
    let _0x1b816e = document.createElement("span");
    _0x1b816e.style.backgroundColor = _0x3abc50.color.toRgb();
    _0x8acd65.appendChild(_0x3658c2);
    _0x8acd65.appendChild(_0x1b816e);
    let _0x5855e9 = document.createElement("label");
    _0x5855e9.className = "switchBottom";
    _0x5855e9.setAttribute("i18n", _0x3abc50.name);
    _0x5855e9.innerText = getI18n(_0x3abc50.name);
    _0x26234d.onclick = async function () {
      console.log(_0x3abc50.title, _0x3abc50.name);
      checkedKeys.forEach(_0x5f287a => {
        _0x5f287a.switch = _0x3abc50.index;
        refreshKeySwitch(_0x5f287a);
      });
      await setKeySwitch();
    };
    _0x26234d.appendChild(_0x8acd65);
    _0x26234d.appendChild(_0x5855e9);
    _0x250d51.appendChild(_0x26234d);
  });
}
function refreshKeySwitch(_0x36e17b) {
  const _0x46625f = keyBtn.find(_0x37d019 => _0x37d019.htmlFor === _0x36e17b.code);
  if (_0x46625f != null) {
    let _0x2fd2fd = switchDefault.find(_0x14b240 => _0x14b240.index === _0x36e17b.switch);
    if (_0x2fd2fd != null) {
      _0x46625f.querySelector("[class=devKeySwitch]").style.borderColor = _0x2fd2fd.color.toRgb();
      _0x46625f.querySelector("[class=devKeySwitchTitle]").style.backgroundColor = _0x2fd2fd.color.toRgb();
      _0x46625f.querySelector("[class=devKeySwitchTitle]").innerText = _0x2fd2fd.title;
    }
  }
}
async function setDeviceLight() {
  if (curDevice !== undefined) {
    const _0xf41de0 = document.getElementById("lightPower");
    const _0x28cd8f = document.getElementById("colorForegroundLabel");
    const _0x599ace = document.getElementById("colorBackgroundLabel");
    const _0x57d7cd = document.getElementById("lightBrightness");
    const _0x208e8a = document.getElementById("lightSpeed");
    const _0x1294d7 = document.getElementById("lightDirectionDiv");
    const _0x15edc0 = document.getElementById("lightModels");
    const _0xd734b0 = document.getElementById("sideLightModels");
    const _0x5cb15a = document.getElementById("lightManu1");
    const _0x1ba51c = document.getElementById("lightManu2");
    if (_0x5cb15a.checked) {
      _0x15edc0.querySelectorAll("input").forEach(_0x2b178c => {
        if (_0x2b178c.checked) {
          curDevice.light.mode = parseInt(_0x2b178c.value);
        }
      });
      curDevice.light.brightness = parseInt(_0x57d7cd.value);
      curDevice.light.speed = parseInt(_0x208e8a.value);
      let _0x212252 = _0x28cd8f.style.backgroundColor;
      let _0xb3bd71 = _0x599ace.style.backgroundColor;
      curDevice.light.foregroundColor = strToColor(_0x212252);
      curDevice.light.backgroundColor = strToColor(_0xb3bd71);
      if (curDevice.light.mode < 20) {
        curProfile.colorArray1[curDevice.light.mode] = curDevice.light.foregroundColor;
        curProfile.colorArray2[curDevice.light.mode] = curDevice.light.backgroundColor;
      }
      _0x1294d7.querySelectorAll("input").forEach(_0x3325fe => {
        if (_0x3325fe.checked) {
          console.log("light direction:" + _0x3325fe.value);
          curDevice.light.direction = parseInt(_0x3325fe.value);
        }
      });
      curDevice.light.fullColor = document.getElementById("fullColor").checked ? 1 : 0;
      curDevice.light.power = _0xf41de0.checked ? 0 : 1;
      curProfile.light = curDevice.light;
      await setLightValue(curDevice.light, false);
    }
    if (_0x1ba51c.checked) {
      _0xd734b0.querySelectorAll("input").forEach(_0x1ae962 => {
        if (_0x1ae962.checked) {
          curDevice.sideLight.mode = parseInt(_0x1ae962.value);
        }
      });
      curDevice.sideLight.brightness = parseInt(_0x57d7cd.value);
      curDevice.sideLight.speed = parseInt(_0x208e8a.value);
      let _0x99ba06 = _0x28cd8f.style.backgroundColor;
      let _0x5b778e = _0x599ace.style.backgroundColor;
      curDevice.sideLight.foregroundColor = strToColor(_0x99ba06);
      curDevice.sideLight.backgroundColor = strToColor(_0x5b778e);
      if (curDevice.sideLight.mode < 20) {
        curProfile.colorArray3[curDevice.sideLight.mode] = curDevice.sideLight.foregroundColor;
        curProfile.colorArray4[curDevice.sideLight.mode] = curDevice.sideLight.backgroundColor;
      }
      _0x1294d7.querySelectorAll("input").forEach(_0x419982 => {
        if (_0x419982.checked) {
          console.log("light direction:" + _0x419982.value);
          curDevice.sideLight.direction = parseInt(_0x419982.value);
        }
      });
      curDevice.sideLight.fullColor = document.getElementById("fullColor").checked ? 1 : 0;
      curDevice.sideLight.power = _0xf41de0.checked ? 0 : 1;
      curProfile.sideLight = curDevice.sideLight;
      await setLightValue(curDevice.sideLight, true);
    }
    let _0x581011 = JSON.stringify(profileSet, replacer);
    localStorage.setItem(curDevice.product, _0x581011);
  }
}
function refreshColorView(_0x198a84) {
  const _0x269d09 = document.getElementById("lightManu1");
  const _0x4f3957 = document.getElementById("lightManu2");
  let _0x18e38c = document.getElementById("lightBrightnessDiv");
  let _0x8fb189 = document.getElementById("lightSpeedDiv");
  let _0x2a04c5 = document.getElementById("lightDirectionDiv");
  let _0x3acd20 = document.getElementById("dirRight");
  let _0xfef4e7 = document.getElementById("dirUp");
  let _0x2f0bb2 = document.getElementById("dirSpread");
  let _0x1b9bd9 = document.getElementById("btnLeft");
  let _0xa6dd7c = document.getElementById("btnRight");
  let _0xfaed24 = document.getElementById("btnUp");
  let _0x4aa4f3 = document.getElementById("btnDown");
  let _0x163739 = document.getElementById("btnGather");
  let _0x38b88f = document.getElementById("btnSpread");
  _0x1b9bd9.style.display = "none";
  _0xa6dd7c.style.display = "none";
  _0xfaed24.style.display = "none";
  _0x4aa4f3.style.display = "none";
  _0x163739.style.display = "none";
  _0x38b88f.style.display = "none";
  let _0xf0c814 = document.getElementById("labFullColor");
  let _0x1b1789 = document.getElementById("inputFullColor");
  let _0x52df82 = document.getElementById("colorRibbon");
  let _0x52464b = document.getElementById("labBackgroundColor");
  let _0x4dd643 = document.getElementById("colorForegroundLabel");
  let _0x1bad5e = document.getElementById("colorBackgroundLabel");
  _0xf0c814.style.display = "flex";
  _0x1b1789.style.display = "flex";
  _0x52df82.style.display = "flex";
  _0x52464b.style.display = "flex";
  _0x1bad5e.style.display = "flex";
  if (_0x269d09.checked) {
    switch (_0x198a84) {
      case 0:
      case 10:
        _0x18e38c.style.display = "table";
        _0x8fb189.style.display = "none";
        _0x2a04c5.style.display = "none";
        _0x3acd20.checked = true;
        _0xf0c814.style.display = "none";
        _0x1b1789.style.display = "none";
        _0x52df82.style.display = "none";
        _0x52464b.style.display = "none";
        _0x1bad5e.style.display = "none";
        _0x4dd643.style.backgroundColor = curProfile.colorArray1[_0x198a84].toRgb();
        break;
      case 1:
      case 3:
      case 6:
      case 8:
      case 9:
      case 11:
      case 14:
      case 16:
        _0x18e38c.style.display = "table";
        _0x8fb189.style.display = "table";
        _0x2a04c5.style.display = "none";
        _0x3acd20.checked = true;
        _0x4dd643.style.backgroundColor = curProfile.colorArray1[_0x198a84].toRgb();
        _0x1bad5e.style.backgroundColor = curProfile.colorArray2[_0x198a84].toRgb();
        break;
      case 2:
        _0x18e38c.style.display = "table";
        _0x8fb189.style.display = "table";
        _0x2a04c5.style.display = "flex";
        _0x1b9bd9.classList.add("btnLeft");
        _0x1b9bd9.classList.remove("btnAnticlockwise");
        _0xa6dd7c.classList.add("btnRight");
        _0xa6dd7c.classList.remove("btnClockwise");
        _0x1b9bd9.style.display = "flex";
        _0xa6dd7c.style.display = "flex";
        _0xfaed24.style.display = "flex";
        _0x4aa4f3.style.display = "flex";
        _0x163739.style.display = "flex";
        _0x38b88f.style.display = "flex";
        _0x3acd20.checked = true;
        _0x4dd643.style.backgroundColor = curProfile.colorArray1[_0x198a84].toRgb();
        _0x1bad5e.style.backgroundColor = curProfile.colorArray2[_0x198a84].toRgb();
        break;
      case 4:
        _0x18e38c.style.display = "table";
        _0x8fb189.style.display = "table";
        _0x2a04c5.style.display = "flex";
        _0x1b9bd9.classList.add("btnAnticlockwise");
        _0x1b9bd9.classList.remove("btnLeft");
        _0xa6dd7c.classList.add("btnClockwise");
        _0xa6dd7c.classList.remove("btnRight");
        _0x1b9bd9.style.display = "flex";
        _0xa6dd7c.style.display = "flex";
        _0x3acd20.checked = true;
        _0x4dd643.style.backgroundColor = curProfile.colorArray1[_0x198a84].toRgb();
        _0x1bad5e.style.backgroundColor = curProfile.colorArray2[_0x198a84].toRgb();
        break;
      case 15:
        _0x18e38c.style.display = "table";
        _0x8fb189.style.display = "table";
        _0x2a04c5.style.display = "flex";
        _0x1b9bd9.classList.add("btnLeft");
        _0x1b9bd9.classList.remove("btnAnticlockwise");
        _0xa6dd7c.classList.add("btnRight");
        _0xa6dd7c.classList.remove("btnClockwise");
        _0x1b9bd9.style.display = "flex";
        _0xa6dd7c.style.display = "flex";
        _0x3acd20.checked = true;
        _0x4dd643.style.backgroundColor = curProfile.colorArray1[_0x198a84].toRgb();
        _0x1bad5e.style.backgroundColor = curProfile.colorArray2[_0x198a84].toRgb();
        break;
      case 7:
        _0x18e38c.style.display = "table";
        _0x8fb189.style.display = "table";
        _0x2a04c5.style.display = "flex";
        _0x163739.style.display = "flex";
        _0x38b88f.style.display = "flex";
        _0x2f0bb2.checked = true;
        _0x4dd643.style.backgroundColor = curProfile.colorArray1[_0x198a84].toRgb();
        _0x1bad5e.style.backgroundColor = curProfile.colorArray2[_0x198a84].toRgb();
        break;
      case 12:
        _0x18e38c.style.display = "table";
        _0x8fb189.style.display = "none";
        _0x2a04c5.style.display = "flex";
        _0x1b9bd9.style.display = "none";
        _0xa6dd7c.style.display = "none";
        _0xfaed24.style.display = "flex";
        _0x4aa4f3.style.display = "flex";
        _0x163739.style.display = "none";
        _0x38b88f.style.display = "none";
        _0xfef4e7.checked = true;
        _0x4dd643.style.backgroundColor = curProfile.colorArray1[_0x198a84].toRgb();
        _0x1bad5e.style.backgroundColor = curProfile.colorArray2[_0x198a84].toRgb();
    }
  }
  if (_0x4f3957.checked) {
    switch (_0x198a84) {
      case 0:
        _0x18e38c.style.display = "table";
        _0x8fb189.style.display = "none";
        _0x2a04c5.style.display = "none";
        _0x3acd20.checked = true;
        _0xf0c814.style.display = "none";
        _0x1b1789.style.display = "none";
        _0x52df82.style.display = "none";
        _0x52464b.style.display = "none";
        _0x1bad5e.style.display = "none";
        _0x4dd643.style.backgroundColor = curProfile.colorArray3[_0x198a84].toRgb();
        break;
      case 1:
      case 2:
      case 4:
        _0x18e38c.style.display = "table";
        _0x8fb189.style.display = "table";
        _0x2a04c5.style.display = "none";
        _0x3acd20.checked = true;
        _0x4dd643.style.backgroundColor = curProfile.colorArray3[_0x198a84].toRgb();
        _0x1bad5e.style.backgroundColor = curProfile.colorArray4[_0x198a84].toRgb();
        break;
      case 3:
        break;
      case 5:
        _0x18e38c.style.display = "none";
        _0x8fb189.style.display = "none";
        _0x2a04c5.style.display = "none";
        _0x3acd20.checked = true;
        _0xf0c814.style.display = "none";
        _0x1b1789.style.display = "none";
        _0x52df82.style.display = "none";
        _0x52464b.style.display = "none";
        _0x1bad5e.style.display = "none";
        _0x4dd643.style.backgroundColor = curProfile.colorArray3[_0x198a84].toRgb();
    }
  }
}
function refreshReviseKeys(_0x406e08) {
  window.dispatchEvent(new MouseEvent("contextmenu"));
  keyBtn.forEach(_0x587be8 => {
    let _0x2f2abf = findDeviceKey(document.getElementById(_0x587be8.htmlFor).id);
    if (_0x406e08.includes(_0x2f2abf.index)) {
      if (curDevice.type === "uk" || curDevice.type === "jp") {
        if (_0x2f2abf.code === "Enter") {
          _0x587be8.style.display = "inline-block";
          document.documentElement.style.setProperty("--ukKey-color", "var(--btn-bgColor)");
        }
      }
      const _0x14afe9 = _0x587be8.querySelector("[class=devKeyPanelView]");
      if (_0x14afe9 != null) {
        _0x14afe9.style.backgroundColor = "var(--btn-ckBgColor)";
        _0x14afe9.childNodes[0].style.color = "#fff";
        _0x14afe9.style.setProperty("--btn-color", "var(--btn-ckBgColor)");
      }
    }
  });
}
window.addEventListener("beforeunload", async _0x576c18 => {
  if (hidDevice !== undefined) {
    hidDevice.opened;
  }
  isDeviceOut &&= false;
  isPrcs = false;
  isAnyKeyCalibration = false;
});
document.addEventListener("DOMContentLoaded", async () => {
  setViewport();
  filters = [{
    vendorId: 1046,
    productId: 29810,
    usagePage: 65307,
    usage: 145
  }, {
    vendorId: 1046,
    productId: 29698,
    usagePage: 65307,
    usage: 145
  }, {
    vendorId: 1046,
    productId: 29554,
    usagePage: 65307,
    usage: 145
  }, {
    vendorId: 1046,
    productId: 49989,
    usagePage: 65307,
    usage: 145
  }, {
    vendorId: 1046,
    productId: 50037,
    usagePage: 65307,
    usage: 145
  }, {
    vendorId: 1046,
    productId: 28672,
    usagePage: 65307,
    usage: 145
  }, {
    vendorId: 1046,
    productId: 29812,
    usagePage: 65307,
    usage: 145
  }, {
    vendorId: 1046,
    productId: 29952,
    usagePage: 65307,
    usage: 145
  }, {
    vendorId: 6127,
    productId: 25044,
    usagePage: 65307,
    usage: 145
  }, {
    vendorId: 6127,
    productId: 25046,
    usagePage: 65307,
    usage: 145
  }, {
    vendorId: 11836,
    productId: 50021,
    usagePage: 65307,
    usage: 145
  }, {
    vendorId: 11836,
    productId: 50022,
    usagePage: 65307,
    usage: 145
  }, {
    vendorId: 11836,
    productId: 50023,
    usagePage: 65307,
    usage: 145
  }, {
    vendorId: 11836,
    productId: 50024,
    usagePage: 65307,
    usage: 145
  }, {
    vendorId: 11836,
    productId: 50025,
    usagePage: 65307,
    usage: 145
  }, {
    vendorId: 11836,
    productId: 50032,
    usagePage: 65307,
    usage: 145
  }, {
    vendorId: 11836,
    productId: 50033,
    usagePage: 65307,
    usage: 145
  }, {
    vendorId: 11836,
    productId: 29952,
    usagePage: 65307,
    usage: 145
  }, {
    vendorId: 11836,
    productId: 29953,
    usagePage: 65307,
    usage: 145
  }, {
    vendorId: 11836,
    productId: 29954,
    usagePage: 65307,
    usage: 145
  }, {
    vendorId: 11836,
    productId: 29957,
    usagePage: 65307,
    usage: 145
  }, {
    vendorId: 11836,
    productId: 29955,
    usagePage: 65307,
    usage: 145
  }, {
    vendorId: 4479,
    productId: 16390,
    usagePage: 65307,
    usage: 145
  }, {
    vendorId: 4479,
    productId: 16390,
    usagePage: 65307,
    usage: 145
  }, {
    vendorId: 9390,
    productId: 6267,
    usagePage: 65307,
    usage: 145
  }];
  switchDefault.push(new Switch(1, new Color(0, 128, 255), "HM1", "switch1", 3.4));
  switchDefault.push(new Switch(2, new Color(128, 128, 50), "HH1", "switch2", 3.4));
  switchDefault.push(new Switch(3, new Color(128, 128, 128), "CY1", "switch3", 3.4));
  switchDefault.push(new Switch(4, new Color(57, 98, 112), "TW1", "switch4", 3.4));
  switchDefault.push(new Switch(5, new Color(200, 0, 200), "TC1", "switch5", 3.4));
  switchDefault.push(new Switch(6, new Color(230, 99, 11), "SL1", "switch6", 3.4));
  switchDefault.push(new Switch(7, new Color(220, 144, 144), "FZ1", "switch7", 3.9));
  switchDefault.push(new Switch(8, new Color(100, 160, 140), "GJP", "switch8", 3.4));
  switchDefault.push(new Switch(9, new Color(144, 197, 131), "HMZ", "switch9", 3.4));
  switchDefault.push(new Switch(10, new Color(164, 168, 154), "GW1", "switch10", 3.9));
  switchDefault.push(new Switch(11, new Color(139, 157, 141), "VA1", "switch11", 3.4));
  switchDefault.push(new Switch(12, new Color(57, 157, 181), "OTK", "switch12", 3.4));
  switchDefault.push(new Switch(13, new Color(203, 145, 137), "CN1", "switch13", 3.4));
  switchDefault.push(new Switch(14, new Color(194, 143, 100), "RY1", "switch14", 3.4));
  switchDefault.push(new Switch(15, new Color(178, 178, 178), "WCG", "switch15", 3.4));
  switchDefault.push(new Switch(16, new Color(113, 113, 113), "JY1", "switch16", 3.6));
  switchDefault.push(new Switch(17, new Color(87, 152, 146), "CS1", "switch17", 3.4));
  switchDefault.push(new Switch(18, new Color(117, 126, 192), "VA2", "switch18", 3.4));
  switchDefault.push(new Switch(19, new Color(186, 197, 203), "CD", "switch19", 3.4));
  switchDefault.push(new Switch(21, new Color(255, 204, 0), "YH1", "switch21", 3.4));
  switchDefault.push(new Switch(22, new Color(210, 139, 66), "EM1", "switch22", 3.5));
  startStep = document.getElementById("startStep");
  qrcode = document.getElementById("qrcode");
  firmwareInfo = document.getElementById("firmwareInfo");
  ProfileDef = document.getElementById("ProfileDef");
  Profile1 = document.getElementById("Profile1");
  Profile2 = document.getElementById("Profile2");
  Profile3 = document.getElementById("Profile3");
  Profile4 = document.getElementById("Profile4");
  menu1 = document.getElementById("menu1");
  menu2 = document.getElementById("menu2");
  menu4 = document.getElementById("menu4");
  devSet = document.getElementById("deviceBg");
  let _0x51a482 = localStorage.getItem("language");
  if (_0x51a482 == null) {
    _0x51a482 = navigator.language;
  }
  if (_0x51a482 == null) {
    _0x51a482 = "en";
  }
  _0x51a482 = _0x51a482.toLowerCase();
  console.log("language:", _0x51a482);
  const _0x2b58de = window.location.hostname;
  let _0x58702a = document.getElementById("language");
  if (_0x51a482 === "zh-cn" || _0x51a482.includes("cn")) {
    _0x58702a.value = "zh-cn";
    i18n = "zh-cn";
  } else if (_0x51a482 === "kr" || _0x51a482 === "ko") {
    _0x58702a.value = "kr";
    i18n = "kr";
  } else if (_0x51a482 === "jp" || _0x51a482 === "ja") {
    _0x58702a.value = "jp";
    i18n = "jp";
  } else if (_0x51a482 === "tr") {
    _0x58702a.value = "tr";
    i18n = "tr";
  } else if (_0x51a482 === "pt-br") {
    _0x58702a.value = "pt-br";
    i18n = "pt-br";
  } else if (_0x51a482 === "ar") {
    _0x58702a.value = "ar";
    i18n = "ar";
  } else if (_0x51a482 === "de") {
    _0x58702a.value = "de";
    i18n = "de";
  } else if (_0x51a482 === "es") {
    _0x58702a.value = "es";
    i18n = "es";
  } else if (_0x51a482 === "pl") {
    _0x58702a.value = "pl";
    i18n = "pl";
  } else {
    _0x58702a.value = "en";
    i18n = "en";
  }
  if (_0x2b58de.includes("qwertykey.eu")) {
    _0x58702a.value = "en";
    i18n = "en";
    _0x58702a.querySelectorAll("option").forEach(_0x1a4081 => {
      if (_0x1a4081.value === "en") {
        _0x1a4081.style.display = "block";
      } else {
        _0x1a4081.style.display = "none";
      }
    });
  }
  if (_0x2b58de.includes("tryhard")) {
    _0x58702a.value = "fr";
    i18n = "fr";
    document.documentElement.lang = "fr";
  }
  if (_0x2b58de.includes("keyboard.klassegear.software")) {
    _0x58702a.value = "tr";
    i18n = "tr";
    document.documentElement.lang = "tr";
  }
  if (_0x2b58de.includes("silvermonkey")) {
    _0x58702a.value = "pl";
    i18n = "pl";
    document.documentElement.lang = "pl";
  }
  await initLanguage();
  document.getElementById("tbSwitch").style.display = "none";
  let _0x1b470e = document.querySelector("title");
  let _0x3739dd = document.querySelector("link[rel='icon']");
  let _0x23054a = document.getElementById("welcome");
  _0x23054a.setAttribute("i18n", "welcome");
  curCompany = "";
  document.getElementById("domain").innerText = _0x2b58de;
  if (_0x2b58de.includes("kzzi.com")) {
    _0x1b470e.innerHTML = "kzzi";
    _0x3739dd.href = "image/logo_kzzi_icon.png";
    _0x23054a.setAttribute("i18n", "welcomeKzzi");
    _0x23054a.innerText = getI18n("welcomeKzzi");
    qrcode.src = "image/qrcode_kzzi.jpg";
    qrcode.style.display = "block";
    curCompany = "kzzi";
    filters = [{
      vendorId: 1046,
      productId: 29698,
      usagePage: 65307,
      usage: 145
    }, {
      vendorId: 11836,
      productId: 50021,
      usagePage: 65307,
      usage: 145
    }];
  } else if (_0x2b58de.includes("wraith.software")) {
    _0x1b470e.innerHTML = "Wraith";
    _0x3739dd.href = "image/logo_mile_wraith.png";
    _0x23054a.setAttribute("i18n", "welcomeWraith");
    _0x23054a.innerText = getI18n("welcomeWraith");
    curCompany = "mile_wraith";
    filters = [{
      vendorId: 11836,
      productId: 50021,
      usagePage: 65307,
      usage: 145
    }];
  } else if (_0x2b58de.includes("qwertykey.eu")) {
    _0x1b470e.innerHTML = "Qwerty";
    _0x3739dd.href = "image/logo_mile_qwerty_icon.png";
    _0x23054a.setAttribute("i18n", "welcomeQwerty");
    _0x23054a.innerText = getI18n("welcomeQwerty");
    curCompany = "mile_qwerty";
    filters = [{
      vendorId: 11836,
      productId: 50021,
      usagePage: 65307,
      usage: 145
    }, {
      vendorId: 11836,
      productId: 50022,
      usagePage: 65307,
      usage: 145
    }, {
      vendorId: 11836,
      productId: 50023,
      usagePage: 65307,
      usage: 145
    }, {
      vendorId: 11836,
      productId: 50024,
      usagePage: 65307,
      usage: 145
    }];
  } else if (_0x2b58de.includes("varosoftware.com")) {
    _0x1b470e.innerHTML = "VARO SW";
    _0x3739dd.href = "image/logo_mile_varo_icon.png";
    _0x23054a.setAttribute("i18n", "welcomeMileVaro");
    _0x23054a.innerText = getI18n("welcomeMileVaro");
    curCompany = "mile_varo";
    curCompanyList = ["mile_varo", "mile_varo_ultra"];
    filters = [{
      vendorId: 1046,
      productId: 29554,
      usagePage: 65307,
      usage: 145
    }, {
      vendorId: 11836,
      productId: 50021,
      usagePage: 65307,
      usage: 145
    }, {
      vendorId: 4479,
      productId: 16390,
      usagePage: 65307,
      usage: 145
    }];
  } else if (_0x2b58de.includes("aulacn.com")) {
    _0x1b470e.innerHTML = "狼蛛在线驱动系统";
    _0x3739dd.href = "image/logo_suoai_icon.png";
    _0x23054a.setAttribute("i18n", "welcomeSuoai");
    _0x23054a.innerText = getI18n("welcomeSuoai");
    curCompany = "suoai";
    filters = [{
      vendorId: 11836,
      productId: 50021,
      usagePage: 65307,
      usage: 145
    }];
  } else if (_0x2b58de.includes("storia-set-up.com")) {
    _0x1b470e.innerHTML = "Storia-set-up";
    _0x3739dd.href = "image/logo_storia_icon.png";
    _0x23054a.setAttribute("i18n", "welcomeStoria");
    _0x23054a.innerText = getI18n("welcomeStoria");
    curCompany = "storia";
    filters = [{
      vendorId: 1046,
      productId: 29554,
      usagePage: 65307,
      usage: 145
    }];
  } else if (_0x2b58de.includes("qmk.center")) {
    _0x1b470e.innerHTML = "QMK";
    _0x3739dd.href = "image/icon_keyboard.png";
    _0x23054a.setAttribute("i18n", "welcomeGaopan");
    _0x23054a.innerText = getI18n("welcomeGaopan");
    curCompany = "gaopan";
    curCompanyList = ["gaopan", "gaopan_kuanglin", "gaopan_yenkee", "gaopan_magnet"];
    filters = [{
      vendorId: 11836,
      productId: 50021,
      usagePage: 65307,
      usage: 145
    }];
  } else if (_0x2b58de.includes("machenike.com")) {
    _0x1b470e.innerHTML = "MachenikeDriver";
    _0x3739dd.href = "image/logo_fengrun_machenike_icon.png";
    _0x23054a.setAttribute("i18n", "welcomeMachenike");
    _0x23054a.innerText = getI18n("welcomeMachenike");
    curCompany = "fengrun_machenike";
    filters = [{
      vendorId: 11836,
      productId: 50021,
      usagePage: 65307,
      usage: 145
    }];
  } else if (_0x2b58de.includes("ess75.pressplayid.com")) {
    _0x1b470e.innerHTML = "Essential75 HE by Press Play";
    _0x3739dd.href = "image/logo_mile_essential_icon.png";
    _0x23054a.setAttribute("i18n", "welcomeEssential");
    _0x23054a.innerText = getI18n("welcomeEssential");
    curCompany = "mile_essential";
    filters = [{
      vendorId: 11836,
      productId: 50021,
      usagePage: 65307,
      usage: 145
    }, {
      vendorId: 11836,
      productId: 50022,
      usagePage: 65307,
      usage: 145
    }, {
      vendorId: 11836,
      productId: 50023,
      usagePage: 65307,
      usage: 145
    }, {
      vendorId: 11836,
      productId: 50024,
      usagePage: 65307,
      usage: 145
    }];
  } else if (_0x2b58de.includes("fantechworld.com")) {
    _0x1b470e.innerHTML = "FANTECH";
    _0x3739dd.href = "image/logo_fantech_icon.png";
    _0x23054a.setAttribute("i18n", "welcomeFantech");
    _0x23054a.innerText = getI18n("welcomeFantech");
    curCompany = "sanpin_fantech";
    filters = [{
      vendorId: 11836,
      productId: 50021,
      usagePage: 65307,
      usage: 145
    }];
  } else if (_0x2b58de.includes("tryhard-software.com")) {
    _0x1b470e.innerHTML = "Tryhard";
    _0x3739dd.href = "image/logo_tryhard_icon.png";
    _0x23054a.setAttribute("i18n", "welcomeTryhard");
    _0x23054a.innerText = getI18n("welcomeTryhard");
    curCompany = "tryhard_software";
    filters = [{
      vendorId: 11836,
      productId: 50021,
      usagePage: 65307,
      usage: 145
    }];
  } else if (_0x2b58de.includes("silvermonkey.com")) {
    _0x1b470e.innerHTML = "SMX Software";
    _0x3739dd.href = "image/logo_minghuaxin_smx_icon.png";
    _0x23054a.setAttribute("i18n", "welcomeSMX");
    _0x23054a.innerText = getI18n("welcomeSMX");
    curCompany = "minghuaxin_smx";
    filters = [{
      vendorId: 11836,
      productId: 50021,
      usagePage: 65307,
      usage: 145
    }];
    _0x58702a.value = "pl";
    i18n = "pl";
    if (localStorage.getItem("pl")) {
      localStorage.setItem("pl", "1.0.0");
    } else {
      localStorage.removeItem("language");
    }
  } else if (_0x2b58de.includes("glick")) {
    _0x1b470e.innerHTML = "glick";
    _0x3739dd.href = "image/logo_sanpin_glick.png";
    _0x23054a.setAttribute("i18n", "welcomeGlick");
    _0x23054a.innerText = getI18n("welcomeGlick");
    curCompany = "sanpin_glick";
    filters = [{
      vendorId: 11836,
      productId: 50021,
      usagePage: 65307,
      usage: 145
    }];
  } else if (_0x2b58de.includes("cidoo")) {
    _0x1b470e.innerHTML = "Cidoo";
    _0x3739dd.href = "image/logo_mile_cidoo.png";
    _0x23054a.setAttribute("i18n", "welcomeCidoo");
    _0x23054a.innerText = getI18n("welcomeCidoo");
    curCompany = "mile_cidoo";
    filters = [{
      vendorId: 11836,
      productId: 50021,
      usagePage: 65307,
      usage: 145
    }, {
      vendorId: 11836,
      productId: 50022,
      usagePage: 65307,
      usage: 145
    }, {
      vendorId: 11836,
      productId: 50023,
      usagePage: 65307,
      usage: 145
    }, {
      vendorId: 11836,
      productId: 50024,
      usagePage: 65307,
      usage: 145
    }];
  } else if (_0x2b58de.includes("keyboard.klassegear.software")) {
    _0x1b470e.innerHTML = "klassegear";
    _0x3739dd.href = "image/logo_klassegear.png";
    _0x23054a.setAttribute("i18n", "welcomeKlasseGear");
    _0x23054a.innerText = getI18n("welcomeKlasseGear");
    curCompany = "klassegear";
    filters = [{
      vendorId: 11836,
      productId: 50022,
      usagePage: 65307,
      usage: 145
    }, {
      vendorId: 11836,
      productId: 50023,
      usagePage: 65307,
      usage: 145
    }, {
      vendorId: 11836,
      productId: 50024,
      usagePage: 65307,
      usage: 145
    }];
    _0x58702a.value = "tr";
    i18n = "tr";
  } else {
    _0x1b470e.innerHTML = "iLLumiPC";
    _0x3739dd.href = "image/icon_keyboard.png";
    _0x23054a.setAttribute("i18n", "welcome");
    _0x23054a.innerText = getI18n("welcome");
    curCompany = "";
  }
  if (curCompany === "mile_qwerty") {
    let _0x106aa5 = document.querySelector(".magneticSwitch");
    let _0x29b930 = document.createElement("img");
    _0x29b930.src = "image/switch.png";
    _0x106aa5.innerHTML = "";
    _0x106aa5.appendChild(_0x29b930);
  }
  if (curCompany === "tryhard_software") {
    document.getElementById("checkKey").querySelector("label").innerText = "Aucune";
  }
  new ThemeManager();
  menu7 = document.querySelector("label[for=\"menu7\"]");
  menu7.style.display = "none";
  keymapDef = document.getElementById("keymapDef");
  keymapFn = document.getElementById("keymapFn");
  keymapDef.onchange = function () {
    setKeyType("radio", false, false);
    refreshRecordDot();
    menu1.dispatchEvent(new CustomEvent("change"));
  };
  keymapFn.onchange = function () {
    setKeyType("radio", false, false);
    refreshRecordDot();
    menu1.dispatchEvent(new CustomEvent("change"));
  };
  keyManu1 = document.getElementById("keyManu1");
  keyManu2 = document.getElementById("keyManu2");
  keyManu3 = document.getElementById("keyManu3");
  keyManu4 = document.getElementById("keyManu4");
  keyManu10 = document.getElementById("keyManu10");
  fixedKeySet = document.getElementById("fixedKeySet");
  fixedKeySet2 = document.getElementById("fixedKeySet2");
  fixedKeySet3 = document.getElementById("fixedKeySet3");
  keyTip = document.getElementById("keyTip");
  keyTip.style.display = "none";
  dksTriggerDiv = document.getElementById("dksTriggerDiv");
  dksTriggerDiv.style.display = "none";
  autoSplitContent(needSplite);
  _0x58702a.onchange = function () {
    console.log(_0x58702a.value);
    i18n = _0x58702a.value;
    document.documentElement.lang = i18n;
    autoSplitContent(needSplite);
    _0x14f07a.querySelectorAll(".lightMode").forEach(_0x3f0f7b => {
      if (_0x3f0f7b.parentNode.getAttribute("order") < 99998) {
        let _0x513667 = getI18n(_0x3f0f7b.getAttribute("i18n")).length * 10 || 0;
        _0x3f0f7b.parentNode.setAttribute("order", _0x513667);
        _0x3f0f7b.parentNode.style.order = _0x513667 + Number(_0x3f0f7b.parentNode.getAttribute("index"));
      } else {
        _0x3f0f7b.parentNode.style.order = Number(_0x3f0f7b.parentNode.getAttribute("order"));
      }
    });
    if (i18n === "jp" || i18n === "de") {
      document.getElementById("btnReset").style.width = "138px";
      document.querySelector("[for=ProfileDef]").innerText = "" + getI18n("default") + getI18n("profile");
    } else {
      document.getElementById("btnReset").style.width = "88px";
      document.querySelector("[for=ProfileDef]").innerText = getI18n("profile") + " " + getI18n("default");
    }
    if (i18n !== "tr" && i18n !== "pt-br" && i18n !== "de") {
      i18n;
    }
    if (i18n === "de") {
      document.getElementById("macroAlert").style.width = "1000px";
    } else {
      document.getElementById("macroAlert").style.width = "880px";
    }
    if (profileSet !== undefined && profileSet !== null && profileSet.profiles.length >= 5) {
      if (profileSet.profiles[1].name === "") {
        document.querySelector("[for=Profile1]").innerText = getI18n("profile") + " 1";
      } else {
        document.querySelector("[for=Profile1]").innerText = profileSet.profiles[1].name;
      }
      if (profileSet.profiles[2].name === "") {
        document.querySelector("[for=Profile2]").innerText = getI18n("profile") + " 2";
      } else {
        document.querySelector("[for=Profile2]").innerText = profileSet.profiles[2].name;
      }
      if (profileSet.profiles[3].name === "") {
        document.querySelector("[for=Profile3]").innerText = getI18n("profile") + " 3";
      } else {
        document.querySelector("[for=Profile3]").innerText = profileSet.profiles[3].name;
      }
      if (profileSet.profiles[4].name === "") {
        document.querySelector("[for=Profile4]").innerText = getI18n("profile") + " 4";
      } else {
        document.querySelector("[for=Profile4]").innerText = profileSet.profiles[4].name;
      }
    } else {
      document.querySelector("[for=Profile1]").innerText = getI18n("profile") + " 1";
      document.querySelector("[for=Profile2]").innerText = getI18n("profile") + " 2";
      document.querySelector("[for=Profile3]").innerText = getI18n("profile") + " 3";
      document.querySelector("[for=Profile4]").innerText = getI18n("profile") + " 4";
    }
    if (btnUpdate.value === "") {
      firmwareInfo.innerText = getI18n("firmwareCurrent") + "V" + curDevice.version + "，" + getI18n("firmwareLast");
      btnUpdate.innerText = getI18n("checkUpdate");
    } else {
      let _0x123f4a = btnUpdate.getAttribute("version");
      firmwareInfo.innerText = getI18n("firmwareNew") + " V" + _0x123f4a;
      btnUpdate.innerText = getI18n("download");
    }
    initFixedKeyView(fixedKeySet, 0);
    initFixedKeyView(fixedKeySet2, 1);
    initFixedKeyView(fixedKeySet3, 2);
    getI18nDom(document.body);
    localStorage.setItem("language", _0x58702a.value);
  };
  if ("navigator" in window && "hid" in navigator) {
    console.log("WebHID is supported!");
    navigator.hid.addEventListener("connect", ({
      device: _0x392b0a
    }) => {
      console.log("HID connected: " + _0x392b0a.vendorId);
    });
    navigator.hid.addEventListener("disconnect", ({
      device: _0x1e9118
    }) => {
      console.log("HID disconnected: " + _0x1e9118.vendorId);
      if (hidDevice !== undefined && _0x1e9118.vendorId === hidDevice.vendorId && _0x1e9118.productId === hidDevice.productId) {
        curDevice = undefined;
        hidDevice.close();
        hidDevice = undefined;
        isDeviceOut = true;
        location.replace(location.href);
      }
    });
  }
  document.getElementById("btnSearch").onclick = async function () {
    isReadInfo = true;
    await initHidDevice();
    isReadInfo = false;
  };
  const _0x16ccdb = document.getElementById("settingIconDiv");
  settingsDiv = document.getElementById("settingsDiv");
  document.getElementById("settingsInfo");
  const _0x51048c = document.getElementById("settingsClose");
  _0x16ccdb.onclick = function () {
    settingsDiv.style.display = "flex";
  };
  _0x51048c.onclick = function () {
    settingsDiv.style.display = "none";
  };
  btnUpdate = document.getElementById("btnUpdate");
  btnUpdate.onclick = async function () {
    if (btnUpdate.value === "") {
      await checkFirmwareVersion();
    } else {
      await downloadFirmware(btnUpdate.value);
    }
    if (btnUpdate.innerText === getI18n("checkUpdate")) {
      showAlert(getI18n("firmwareCurrent") + "V" + curDevice.version + "，" + getI18n("firmwareLast"));
    }
  };
  const _0x4e3653 = document.querySelectorAll("input[name=\"ctrRadio\"]");
  const _0x5dea9e = document.querySelectorAll("input[name=\"manuRadio\"]");
  async function _0x15cd01(_0x14b110) {
    if (_0x14b110.target.id !== "triggerManu3" && isCalibrationing) {
      isChangeCalibration = true;
      return await _0x5dd167();
    }
  }
  async function _0x51d16a(_0xb24505) {
    if (_0xb24505.target.id !== "menu4" && _0x2ea3e4.checked && isCalibrationing) {
      isChangeCalibration = true;
      return await _0x5dd167();
    }
  }
  _0x4e3653.forEach(_0x3714eb => {
    _0x3714eb.addEventListener("change", _0x15cd01);
  });
  _0x5dea9e.forEach(_0x3cfb8c => {
    _0x3cfb8c.addEventListener("change", _0x51d16a);
  });
  const _0x55e254 = document.getElementById("gamePad1");
  const _0x31eede = document.querySelector("[for=gamePad1]");
  const _0x313ab9 = document.getElementById("gamePad2");
  const _0x522931 = document.querySelector("[for=gamePad2]");
  const _0x13675d = document.getElementById("gamePad3");
  const _0x3c5ae0 = document.querySelector("[for=gamePad3]");
  _0x55e254.onmousedown = _0x31eede.onmousedown = function () {
    if (confirm(getI18n("gamePadTip1"))) {
      _0x55e254.checked = true;
      setGamePadMode(0);
    }
  };
  _0x313ab9.onmousedown = _0x522931.onmousedown = function () {
    if (confirm(getI18n("gamePadTip1"))) {
      _0x313ab9.checked = true;
      setGamePadMode(1);
    }
  };
  _0x13675d.onmousedown = _0x3c5ae0.onmousedown = function () {
    if (confirm(getI18n("gamePadTip1"))) {
      _0x13675d.checked = true;
      setGamePadMode(2);
    }
  };
  const _0xf1e9b0 = document.getElementById("triggerManu1");
  const _0x52734d = document.getElementById("triggerManu2");
  const _0x2ea3e4 = document.getElementById("triggerManu3");
  const _0x3d0f3a = document.getElementById("triggerManu4");
  const _0x2c7037 = document.getElementById("triggerManu5");
  const _0x26e4a2 = document.getElementById("tbView");
  const _0x2c4188 = document.getElementById("tkView");
  const _0xb015fd = document.getElementById("tjView");
  const _0x3ae14c = document.getElementById("trView");
  const _0x5586b2 = document.getElementById("tdView");
  _0xf1e9b0.onchange = function () {
    if (_0xf1e9b0.checked) {
      _0x23e3f1.disabled = false;
      _0x21e3f0.style.display = "flex";
      _0x26e4a2.style.display = "flex";
      _0x2c4188.style.display = "none";
      _0xb015fd.style.display = "none";
      _0x3ae14c.style.display = "none";
      _0x5586b2.style.display = "none";
      setKeyType("checkbox", true, false);
      window.dispatchEvent(new MouseEvent("contextmenu"));
    }
  };
  _0x52734d.onchange = function () {
    if (_0x52734d.checked) {
      _0x23e3f1.disabled = false;
      _0x21e3f0.style.display = "flex";
      _0x26e4a2.style.display = "none";
      _0x2c4188.style.display = "flex";
      _0xb015fd.style.display = "none";
      _0x3ae14c.style.display = "none";
      _0x5586b2.style.display = "none";
      setKeyType("checkbox", false, true);
      window.dispatchEvent(new MouseEvent("contextmenu"));
    }
  };
  _0x2ea3e4.onchange = function () {
    if (_0x2ea3e4.checked) {
      _0x23e3f1.disabled = true;
      _0x23e3f1.checked = false;
      _0x23e3f1.dispatchEvent(new Event("input"));
      _0x21e3f0.style.display = "none";
      _0x26e4a2.style.display = "none";
      _0x2c4188.style.display = "none";
      _0xb015fd.style.display = "flex";
      _0x3ae14c.style.display = "none";
      _0x5586b2.style.display = "none";
      setKeyType("text", false, false);
      window.dispatchEvent(new MouseEvent("contextmenu"));
    }
  };
  _0x3d0f3a.onchange = function () {
    if (_0x3d0f3a.checked) {
      _0x23e3f1.disabled = false;
      _0x21e3f0.style.display = "none";
      _0x26e4a2.style.display = "none";
      _0x2c4188.style.display = "none";
      _0xb015fd.style.display = "none";
      _0x3ae14c.style.display = "flex";
      _0x5586b2.style.display = "none";
      setKeyType("text", false, false);
      window.dispatchEvent(new MouseEvent("contextmenu"));
    }
  };
  _0x2c7037.onchange = function () {
    if (_0x2c7037.checked) {
      _0x23e3f1.disabled = false;
      _0x21e3f0.style.display = "flex";
      _0x26e4a2.style.display = "none";
      _0x2c4188.style.display = "none";
      _0xb015fd.style.display = "none";
      _0x3ae14c.style.display = "none";
      _0x5586b2.style.display = "flex";
      setKeyType("checkbox", true, false);
      window.dispatchEvent(new MouseEvent("contextmenu"));
    }
  };
  const _0x2b19c3 = document.getElementById("pollRate1");
  const _0x1356be = document.getElementById("pollRate2");
  const _0x4635f3 = document.getElementById("pollRate3");
  const _0xbbb260 = document.getElementById("pollRate4");
  document.getElementById("rateList").querySelectorAll("input").forEach(_0x123573 => {
    if (_0x123573.checked) {
      if (_0x123573 === _0x2b19c3) {
        pollRate = 1;
      }
      if (_0x123573 === _0x1356be) {
        pollRate = 2;
      }
      if (_0x123573 === _0x4635f3) {
        pollRate = 4;
      }
      if (_0x123573 === _0xbbb260) {
        pollRate = 8;
      }
    }
    _0x123573.onclick = function (_0x4ab217) {
      console.log(_0x123573.id);
      _0x23be72.style.display = "block";
      _0x179057.value = "rate";
      _0x179057.innerText = getI18n("rateTip2");
    };
  });
  const _0x23e3f1 = document.getElementById("testPower");
  _0x23e3f1.oninput = function () {
    if (_0x23e3f1.checked) {
      openTriggerTest();
    } else {
      closeTriggerTest();
    }
  };
  document.getElementById("testjindu").style.height = "0";
  triggerAll = document.getElementById("triggerAll");
  triggerAll.addEventListener("input", _0x280a3d => {
    if (_0x280a3d.detail && document.activeElement === triggerAll) {
      setMagneticSwitchValue(_0x280a3d.detail);
    }
  });
  triggerAll.addEventListener("toggle", async _0x509313 => {
    let _0x5efe27 = _0x4cdc70.checked ? _0x33e9e1.checked ? 13 : 12 : 0;
    triggerSliderValue = parseInt(triggerAll.value);
    checkedKeys.forEach(function (_0x4505b0) {
      _0x4505b0.trigger.mode = _0x5efe27;
      _0x4505b0.trigger.travel = triggerSliderValue;
      refreshKeyButton(_0x4505b0);
    });
    await setAnyTriggerValue(_0x5efe27);
    refreshProfileTrigger();
  });
  triggerDown = document.getElementById("triggerDown");
  triggerDown.addEventListener("toggle", async _0x4ab6f2 => {
    let _0x3463a3 = _0x4cdc70.checked ? _0x33e9e1.checked ? 13 : 12 : 0;
    checkedKeys.forEach(_0x30c0e3 => {
      _0x30c0e3.trigger.mode = _0x3463a3;
      _0x30c0e3.trigger.interval1 = parseInt(triggerDown.value);
      _0x30c0e3.trigger.interval2 = _0x33e9e1.checked ? parseInt(triggerUp.value) : parseInt(triggerDown.value);
      refreshKeyButton(_0x30c0e3);
    });
    await setAnyTriggerValue(_0x3463a3);
    refreshProfileTrigger();
  });
  triggerUp = document.getElementById("triggerUp");
  triggerUp.addEventListener("toggle", async _0x16e9c0 => {
    let _0x57358e = _0x4cdc70.checked ? _0x33e9e1.checked ? 13 : 12 : 0;
    checkedKeys.forEach(_0x103c02 => {
      _0x103c02.trigger.mode = _0x57358e;
      _0x103c02.trigger.interval1 = parseInt(triggerDown.value);
      _0x103c02.trigger.interval2 = parseInt(triggerUp.value);
      refreshKeyButton(_0x103c02);
    });
    await setAnyTriggerValue(_0x57358e);
    refreshProfileTrigger();
  });
  const _0x4cdc70 = document.getElementById("triggerPower");
  const _0x33e9e1 = document.getElementById("triggerTravel");
  document.getElementById("triggerDownAndUp").style.display = "none";
  document.getElementById("labelTip2").style.display = "none";
  document.getElementById("labelTitle1").style.display = "none";
  triggerDown.style.display = "none";
  document.getElementById("labelTitle2").style.display = "none";
  triggerUp.style.display = "none";
  let _0x385415 = document.getElementById("col1");
  let _0xaec03d = document.getElementById("col2");
  let _0x33b3ad = document.getElementById("col3");
  let _0x2b7489 = document.getElementById("col4");
  let _0x57e9fd = document.getElementById("tglEdit");
  let _0x5c1ad1 = document.getElementById("mtEdit1");
  let _0x1b7114 = document.getElementById("mtEdit2");
  let _0x54c973 = document.getElementById("dksEdit1");
  let _0x213bc8 = document.getElementById("dksEdit2");
  let _0x451f40 = document.getElementById("dksEdit3");
  let _0x39b9a3 = document.getElementById("dksEdit4");
  let _0x36bb8e = document.getElementById("rsEdit1");
  let _0x48d374 = document.getElementById("rsEdit2");
  let _0x1d6f0b = document.getElementById("rkrtEdit");
  let _0x2c90db = document.getElementById("mtRange");
  let _0x4db165 = document.getElementById("tglDiv");
  let _0x120d89 = document.getElementById("mtDiv");
  let _0x2af368 = document.getElementById("dksDiv");
  let _0x93000 = document.getElementById("rkrtDiv");
  let _0x3ff2ca = document.getElementById("rsDiv");
  recordInput = document.getElementById("recordInput");
  btnResetKey = document.getElementById("btnResetKey");
  btnApplyKey = document.getElementById("btnApplyKey");
  let _0x1419db = document.getElementById("macroKeyEdit");
  _0x57e9fd.onfocus = function () {
    curEdit = _0x57e9fd;
    _0x57e9fd.classList.add("tglTmInputFocus");
  };
  _0x5c1ad1.onfocus = function () {
    curEdit = _0x5c1ad1;
    _0x5c1ad1.classList.add("tglTmInputFocus");
    _0x1b7114.classList.remove("tglTmInputFocus");
  };
  _0x1b7114.onfocus = function () {
    curEdit = _0x1b7114;
    _0x5c1ad1.classList.remove("tglTmInputFocus");
    _0x1b7114.classList.add("tglTmInputFocus");
  };
  _0x54c973.onfocus = function () {
    curEdit = _0x54c973;
    _0x54c973.classList.add("tglTmInputFocus");
    _0x213bc8.classList.remove("tglTmInputFocus");
    _0x451f40.classList.remove("tglTmInputFocus");
    _0x39b9a3.classList.remove("tglTmInputFocus");
  };
  _0x213bc8.onfocus = function () {
    curEdit = _0x213bc8;
    _0x54c973.classList.remove("tglTmInputFocus");
    _0x213bc8.classList.add("tglTmInputFocus");
    _0x451f40.classList.remove("tglTmInputFocus");
    _0x39b9a3.classList.remove("tglTmInputFocus");
  };
  _0x451f40.onfocus = function () {
    curEdit = _0x451f40;
    _0x54c973.classList.remove("tglTmInputFocus");
    _0x213bc8.classList.remove("tglTmInputFocus");
    _0x451f40.classList.add("tglTmInputFocus");
    _0x39b9a3.classList.remove("tglTmInputFocus");
  };
  _0x39b9a3.onfocus = function () {
    curEdit = _0x39b9a3;
    _0x54c973.classList.remove("tglTmInputFocus");
    _0x213bc8.classList.remove("tglTmInputFocus");
    _0x451f40.classList.remove("tglTmInputFocus");
    _0x39b9a3.classList.add("tglTmInputFocus");
  };
  _0x36bb8e.onfocus = function () {
    curEdit = _0x36bb8e;
    _0x48d374.classList.remove("tglTmInputFocus");
    _0x36bb8e.classList.add("tglTmInputFocus");
  };
  _0x48d374.onfocus = function () {
    curEdit = _0x48d374;
    _0x36bb8e.classList.remove("tglTmInputFocus");
    _0x48d374.classList.add("tglTmInputFocus");
  };
  _0x1d6f0b.onfocus = function () {
    curEdit = _0x1d6f0b;
    _0x1d6f0b.classList.add("tglTmInputFocus");
  };
  document.addEventListener("keydown", function (_0x1ab36a) {
    setRecordKey(recordInput, _0x1ab36a, 1);
    setRecordKey(_0x57e9fd, _0x1ab36a, 2);
    setRecordKey(_0x5c1ad1, _0x1ab36a, 3);
    setRecordKey(_0x1b7114, _0x1ab36a, 4);
    setRecordKey(_0x54c973, _0x1ab36a, 5);
    setRecordKey(_0x213bc8, _0x1ab36a, 6);
    setRecordKey(_0x451f40, _0x1ab36a, 7);
    setRecordKey(_0x39b9a3, _0x1ab36a, 8);
    setRecordKey(_0x1419db, _0x1ab36a, 9);
    setRecordKey(_0x26f83c, _0x1ab36a, 10);
    setRecordKey(_0x186d3f, _0x1ab36a, 11);
    setRecordKey(_0x36bb8e, _0x1ab36a, 12);
    setRecordKey(_0x48d374, _0x1ab36a, 13);
    setRecordKey(_0x1d6f0b, _0x1ab36a, 14);
  });
  document.addEventListener("keyup", function (_0x20e63a) {
    if (_0x20e63a.code === "PrintScreen" || _0x20e63a.code === "F8") {
      setRecordKey(recordInput, _0x20e63a, 1);
      setRecordKey(_0x57e9fd, _0x20e63a, 2);
      setRecordKey(_0x5c1ad1, _0x20e63a, 3);
      setRecordKey(_0x1b7114, _0x20e63a, 4);
      setRecordKey(_0x54c973, _0x20e63a, 5);
      setRecordKey(_0x213bc8, _0x20e63a, 6);
      setRecordKey(_0x451f40, _0x20e63a, 7);
      setRecordKey(_0x39b9a3, _0x20e63a, 8);
      setRecordKey(_0x1419db, _0x20e63a, 9);
      setRecordKey(_0x36bb8e, _0x20e63a, 12);
      setRecordKey(_0x48d374, _0x20e63a, 13);
      setRecordKey(_0x1d6f0b, _0x20e63a, 14);
    }
  });
  let _0x3ccce2 = document.getElementById("profiles");
  _0x3ccce2.querySelectorAll("input[type=\"radio\"]").forEach(function (_0x4def17, _0x1799e3) {
    _0x4def17.onchange = async function () {
      if (_0x4def17.checked && (console.log("input.checked)", _0x1799e3), document.documentElement.style.setProperty("--translateY", _0x1799e3 * 100 + "%"), profileSet !== undefined && profileSet !== null)) {
        if (_0x4def17.id === "ProfileDef") {
          profileSet.curIndex = 0;
        }
        if (_0x4def17.id === "Profile1") {
          profileSet.curIndex = 1;
        }
        if (_0x4def17.id === "Profile2") {
          profileSet.curIndex = 2;
        }
        if (_0x4def17.id === "Profile3") {
          profileSet.curIndex = 3;
        }
        if (_0x4def17.id === "Profile4") {
          profileSet.curIndex = 4;
        }
        if (profileSet.curIndex < profileSet.profiles.length) {
          curProfile = profileSet.profiles[profileSet.curIndex];
          recKeys = curProfile.defKeys;
          fnKeys = curProfile.fnKeys;
          recMacros = curProfile.recMacros;
          curDevice.light = curProfile.light;
          curDevice.sideLight = curProfile.sideLight;
          prcses = deepCopy(curProfile.prcses);
          macros = deepCopy(curProfile.macros);
          advKeys = deepCopy(curProfile.advKeys);
          if (prcses === undefined || prcses === null) {
            prcses = [];
          }
          document.getElementById("prcsPower").checked = curProfile.prcsPower === 1;
          if (curDevice !== undefined && curDevice !== null && (curProfile.triggers.length === 0 || curProfile.triggers.size === 0)) {
            curDevice.keys.forEach(_0x45a3d0 => {
              let _0x2c78d9 = new Trigger();
              _0x2c78d9.mode = 0;
              _0x2c78d9.travel = Math.floor(curDevice.maxTriggerTravel / 2);
              _0x2c78d9.interval1 = 5;
              _0x2c78d9.interval2 = 5;
              curProfile.triggers.set(_0x45a3d0.index, _0x2c78d9);
            });
          }
          refreshRecordDot();
          refreshDeviceView();
          if (curDevice.hasLight) {
            initLightView();
          }
          refreshMacroList(macros);
          refreshAdvList();
          refreshAllTrigger(curProfile.triggers);
          refreshPrcsList(prcses);
          refreshPerformanceView(curProfile.other, false);
          const _0x53b438 = document.getElementById("prcsList").querySelectorAll("input");
          if (_0x53b438.length > 0) {
            const _0x3c44da = _0x53b438[0];
            _0x3c44da.checked = true;
            _0x3c44da.dispatchEvent(new Event("change"));
          }
        }
        btnApplyKey.dispatchEvent(new Event("click"));
        if (curDevice.hasLight) {
          await setLightValue(curDevice.light, false);
          await setLightValue(curDevice.sideLight, true);
        }
        await setAllTriggerValue(curProfile.triggers);
        await setPrcsPower(_0x51c255.checked);
        await setPrcsData();
        await setPerformanceValue(curProfile.other, curProfile.is6Key);
        if (curProfile.triggers.size > 0) {
          let _0x3de078 = curProfile.triggers.entries().next().value[1];
          initTriggerSlider(curDevice.maxTriggerTravel, curDevice.triggerUnit, _0x3de078.travel);
        } else {
          let _0x18824e = Math.floor(curDevice.maxTriggerTravel / 2);
          initTriggerSlider(curDevice.maxTriggerTravel, curDevice.triggerUnit, _0x18824e);
        }
        if (_0x23e3f1.checked) {
          _0x23e3f1.checked = false;
          _0x23e3f1.dispatchEvent(new Event("input"));
        }
      }
    };
  });
  _0x3ccce2.querySelectorAll("input[type=\"text\"]").forEach(function (_0x479558) {});
  let _0x25ab0f = document.getElementsByClassName("profileItem");
  Array.prototype.forEach.call(_0x25ab0f, function (_0x2caadb) {
    const _0x379e2f = _0x2caadb.querySelector("button");
    if (_0x379e2f != null) {
      const _0x356f36 = _0x379e2f.value;
      const _0xc4a0f = _0x2caadb.querySelector("[for=Profile" + _0x356f36 + "]");
      const _0x36fa14 = document.getElementById("ProfileText" + _0x356f36);
      const _0x1b877f = _0x2caadb.querySelector("[for=ProfileText" + _0x356f36 + "]");
      _0x379e2f.onclick = function () {
        if (function (_0x1f8d1e) {
          var _0x4fed20 = window.getComputedStyle(_0x1f8d1e);
          return _0x4fed20.display;
        }(_0xc4a0f) === "flex") {
          _0xc4a0f.style.display = "none";
          _0x36fa14.style.display = "flex";
          _0x1b877f.style.display = "flex";
          _0x36fa14.value = _0xc4a0f.innerText;
          _0x379e2f.style.backgroundImage = "var(--btn-save)";
        } else {
          _0xc4a0f.style.display = "flex";
          _0x36fa14.style.display = "none";
          _0x1b877f.style.display = "none";
          _0xc4a0f.innerText = _0x36fa14.value === "" ? getI18n("profile") + " " + _0x356f36 : _0x36fa14.value;
          _0x379e2f.style.backgroundImage = "var(--mac-edit)";
          if (profileSet !== undefined && profileSet !== null && profileSet.profiles.length > _0x356f36) {
            profileSet.profiles[_0x356f36].name = _0x36fa14.value;
            let _0x517ecb = JSON.stringify(profileSet, replacer);
            localStorage.setItem(curDevice.product, _0x517ecb);
          }
        }
      };
      _0x36fa14.onkeydown = function (_0x1c9e38) {
        if (_0x1c9e38.key === "Enter" && (_0xc4a0f.style.display = "flex", _0x36fa14.style.display = "none", _0x1b877f.style.display = "none", _0xc4a0f.innerText = _0x36fa14.value === "" ? getI18n("profile") + " " + _0x356f36 : _0x36fa14.value, _0x379e2f.style.backgroundImage = "var(--mac-edit)", profileSet !== undefined && profileSet !== null && profileSet.profiles.length > _0x356f36)) {
          profileSet.profiles[_0x356f36].name = _0x36fa14.value;
          let _0x5a16de = JSON.stringify(profileSet, replacer);
          localStorage.setItem(curDevice.product, _0x5a16de);
        }
      };
    }
  });
  keymapTable = document.getElementById("keymapTable");
  let _0x128641 = document.getElementById("keymapTableView");
  let _0x21e3f0 = document.getElementById("selectAllView");
  let _0x16df64 = document.getElementById("btnSelectAll");
  let _0x31766b = document.getElementById("btnSelectInvert");
  let _0x45f087 = document.getElementById("btnDeselectAll");
  let _0x3e9ad3 = document.getElementById("btnResetTrigger");
  let _0x23b6b7 = document.getElementById("menuDiv");
  _0x23b6b7.querySelectorAll("input").forEach(function (_0x22a4c8) {
    _0x22a4c8.onchange = function () {
      console.log("menuInput", _0x22a4c8.id);
      const _0x5c27f6 = document.querySelector("label[for=\"" + _0x22a4c8.id + "\"]");
      _0x23b6b7.style.setProperty("--menuY", _0x5c27f6.offsetTop + "px");
      document.getElementById("customView").style.display = "none";
      document.getElementById("lightView").style.display = "none";
      document.getElementById("performanceView").style.display = "none";
      document.getElementById("triggerView").style.display = "none";
      document.getElementById("prcsView").style.display = "none";
      document.getElementById("checkKey").querySelector("label").innerText = curCompany === "tryhard_software" ? "Aucune" : "None";
      recordInput.value = "";
      recordInput.disabled = true;
      btnResetKey.disabled = true;
      btnApplyKey.disabled = true;
      keyBtn.forEach(function (_0x491031) {
        _0x491031.querySelector("img").style.display = "none";
      });
      keymapTable.style.display = "none";
      _0x128641.style.display = "none";
      _0x21e3f0.style.display = "none";
      curKey = undefined;
      showKeyColor(false);
      if (_0x22a4c8.id !== "menu4" && _0x23e3f1.checked) {
        _0x23e3f1.checked = false;
        _0x23e3f1.dispatchEvent(new Event("input"));
      }
      if (_0x22a4c8.id !== "menu1") {
        document.getElementById("applyTip1")?.remove("applyTip1");
      }
      if (_0x22a4c8.id === "menu1") {
        clearTriggerButtonState();
        keymapTable.style.display = "flex";
        _0x128641.style.display = "block";
        document.getElementById("customView").style.display = "flex";
        setKeyType("radio", false, false);
        refreshRecordDot();
      }
      if (_0x22a4c8.id === "menu2") {
        clearTriggerButtonState();
        document.getElementById("lightView").style.display = "flex";
        document.getElementById("devViewDiv").classList.add("devViewSetLight");
        if (curDevice.light.mode === 10) {
          setKeyType("checkbox", false, false);
          showKeyColor(true);
        } else {
          setKeyType("text", false, false);
          showKeyColor(false);
        }
        initColorSlider();
      } else {
        document.getElementById("devViewDiv").classList.remove("devViewSetLight");
      }
      if (_0x22a4c8.id === "menu3") {
        clearTriggerButtonState();
        document.getElementById("performanceView").style.display = "flex";
        setKeyType("text", false, false);
      }
      if (_0x22a4c8.id === "menu4") {
        keymapTable.style.display = "flex";
        document.getElementById("triggerView").style.display = "flex";
        const _0x5e9a4b = document.querySelectorAll("#triggerMenuDiv label");
        const _0x362e0d = Array.from(_0x5e9a4b).find(_0x1c9e65 => _0x1c9e65.style.display !== "none");
        if (_0x362e0d) {
          const _0x377668 = document.querySelector("#" + _0x362e0d.htmlFor);
          if (_0x377668) {
            _0x377668.click();
          }
        }
        if (_0xf1e9b0.checked || _0x2c7037.checked) {
          _0x21e3f0.style.display = "flex";
          setKeyType("checkbox", true, false);
        }
        if (_0x52734d.checked) {
          _0x21e3f0.style.display = "flex";
          setKeyType("checkbox", false, true);
        }
        if (_0x2ea3e4.checked || _0x3d0f3a.checked) {
          setKeyType("text", false, false);
        }
      }
      if (_0x22a4c8.id === "menu7") {
        clearTriggerButtonState();
        document.getElementById("prcsView").style.display = "flex";
        setKeyType("text", false, false);
      }
      refreshDevice();
    };
  });
  _0x16df64.onclick = function () {
    checkedKeys = [];
    keyBtn.forEach(_0x1a5320 => {
      let _0x4ffcc7 = document.getElementById(_0x1a5320.htmlFor);
      _0x4ffcc7.checked = true;
      if (_0x1a5320 === keyBtn[0]) {
        _0x4ffcc7.dispatchEvent(new Event("change"));
      }
      let _0x49cacb = findDeviceKey(_0x1a5320.htmlFor);
      if (_0x49cacb != null) {
        if (!checkedKeys.some(_0x399fd2 => _0x399fd2.code === _0x49cacb.code)) {
          checkedKeys.push(_0x49cacb);
        }
      }
    });
    _0x4cdc70.disabled = false;
    refreshTriggerSlider(triggerAll.value);
    refreshTriggerAllView();
    console.log("选中按键数：", checkedKeys.length);
  };
  _0x31766b.onclick = function () {
    checkedKeys = [];
    keyBtn.forEach(_0x9a8c4e => {
      let _0x49aff9 = document.getElementById(_0x9a8c4e.htmlFor);
      _0x49aff9.checked = !_0x49aff9.checked;
      if (_0x9a8c4e === keyBtn[0]) {
        _0x49aff9.dispatchEvent(new Event("change"));
      }
      if (_0x49aff9.checked) {
        let _0x130fcd = findDeviceKey(_0x9a8c4e.htmlFor);
        if (_0x130fcd != null) {
          if (!checkedKeys.some(_0x2c8a9f => _0x2c8a9f.code === _0x130fcd.code)) {
            checkedKeys.push(_0x130fcd);
          }
        }
      }
    });
    if (checkedKeys.length > 0) {
      _0x4cdc70.disabled = checkedKeys.length === 0;
      refreshTriggerSlider(triggerAll.value);
    } else {
      checkedKeys = [];
      _0x4cdc70.disabled = checkedKeys.length === 0;
      _0x4cdc70.checked = false;
      refreshTriggerView(false);
    }
    refreshTriggerAllView();
    console.log("选中按键数：", checkedKeys.length);
  };
  _0x45f087.onclick = function () {
    checkedKeys = [];
    keyBtn.forEach(_0xb00f04 => {
      let _0x952c84 = document.getElementById(_0xb00f04.htmlFor);
      _0x952c84.checked = false;
      if (_0xb00f04 === keyBtn[0]) {
        _0x952c84.dispatchEvent(new Event("change"));
      }
    });
    _0x4cdc70.disabled = checkedKeys.length === 0;
    _0x4cdc70.checked = false;
    refreshTriggerView(false);
    refreshTriggerAllView();
    console.log("选中按键数：", checkedKeys.length);
  };
  _0x3e9ad3.onclick = async function () {
    _0x23be72.style.display = "block";
    _0x179057.value = "trigger";
    _0x179057.innerText = getI18n("resetTriggerAlert");
  };
  document.getElementById("btnReset").onclick = function () {
    _0x23be72.style.display = "block";
    _0x179057.value = "all";
    _0x179057.innerText = getI18n("resetAlert");
  };
  let _0x23be72 = document.getElementById("overlay");
  let _0x179057 = document.getElementById("alertMessage");
  let _0x144388 = document.getElementById("btnAlertOk");
  let _0x2c93cc = document.getElementById("btnAlertCancel");
  _0x144388.onclick = async function () {
    _0x23be72.style.display = "none";
    if (_0x179057.value === "all") {
      await resetKeyboard();
      await resetTrigger();
      if (!isInitDeadBand) {
        await resetDeadBand();
      }
      if (advKeys && advKeys.length) {
        advKeys.forEach(_0x559e23 => {
          if (_0x559e23.type === "RS") {
            _0x559e23.keys[0] = new Key();
            _0x559e23.keys[1] = new Key();
          }
        });
      }
      curProfile.advKeys = deepCopy(advKeys);
      let _0x2e7034 = JSON.stringify(profileSet, replacer);
      localStorage.setItem(curDevice.product, _0x2e7034);
      await sleep(100);
      _0x51c255.checked = false;
      await setPrcsPower(_0x51c255.checked);
      curProfile.prcsPower = 0;
      if (curDevice.hasLight) {
        await initLightValue();
      }
      await readMaxTriggerTravel();
      await readTriggerData();
      await sleep(100);
      recKeys.clear();
      fnKeys.clear();
      recMacros.clear();
      refreshRecordDot();
      if (curKey !== undefined && curKey !== null) {
        recordInput.value = curKey.name;
      }
      triggerSliderValue = Math.floor(curDevice.maxTriggerTravel / 2);
      initTriggerSlider(curDevice.maxTriggerTravel, curDevice.triggerUnit, triggerSliderValue);
      keyBtn.forEach(_0x374429 => {
        refreshKeyButton(findDeviceKey(_0x374429.htmlFor));
      });
      if (curDevice.hasLight) {
        initLightView();
      }
      _0x3ccce2.querySelectorAll("input").forEach(function (_0x25e6aa) {
        if (_0x25e6aa.checked) {
          _0x25e6aa.dispatchEvent(new Event("change"));
        }
      });
    }
    if (_0x179057.value === "trigger") {
      await resetTrigger();
      await sleep(100);
      await readMaxTriggerTravel();
      await readTriggerData();
      await sleep(100);
      triggerSliderValue = Math.floor(curDevice.maxTriggerTravel / 2);
      initTriggerSlider(curDevice.maxTriggerTravel, curDevice.triggerUnit, triggerSliderValue);
      keyBtn.forEach(_0xf7a3dd => {
        refreshKeyButton(findDeviceKey(_0xf7a3dd.htmlFor));
      });
    }
    if (_0x179057.value === "rate") {
      if (_0x2b19c3.checked) {
        pollRate = 1;
      }
      if (_0x1356be.checked) {
        pollRate = 2;
      }
      if (_0x4635f3.checked) {
        pollRate = 4;
      }
      if (_0xbbb260.checked) {
        pollRate = 8;
      }
      await setPollRate();
    }
  };
  _0x2c93cc.onclick = function () {
    _0x23be72.style.display = "none";
    if (_0x179057.value === "rate") {
      if (pollRate === 1) {
        _0x2b19c3.checked = true;
      }
      if (pollRate === 2) {
        _0x1356be.checked = true;
      }
      if (pollRate === 4) {
        _0x4635f3.checked = true;
      }
      if (pollRate === 8) {
        _0xbbb260.checked = true;
      }
    }
  };
  const _0x58b3fa = document.getElementById("labTip");
  const _0x1cce21 = document.getElementById("keyMenuDiv");
  const _0x185deb = document.getElementById("macroKeySet");
  const _0x25521d = document.getElementById("advancedKeySet");
  const _0x5f1c9d = document.getElementById("gameSet");
  const _0x4edbd4 = _0x1cce21.querySelectorAll("label");
  const _0x3a127b = document.getElementById("dbRight");
  _0x4edbd4.forEach(function (_0x2a809e) {
    let _0x56e121 = document.getElementById(_0x2a809e.htmlFor);
    _0x56e121.onchange = function () {
      if (_0x56e121.id === "keyManu1") {
        _0x58b3fa.setAttribute("i18n", "labTip1");
        _0x58b3fa.innerText = getI18n("labTip1");
        fixedKeySet.querySelector("[class=Special]").style.display = "block";
        fixedKeySet.querySelector("[class=KeyboardLight]").style.display = "block";
        let _0x21d94a = fixedKeySet.querySelector("[class=Expand]").querySelector("[class=spacer]");
        if (_0x21d94a != null) {
          _0x21d94a.style.height = "0px";
        }
        fixedKeySet.style.display = "flex";
        _0x185deb.style.display = "none";
        _0x25521d.style.display = "none";
        _0x5f1c9d.style.display = "none";
      }
      if (_0x56e121.id === "keyManu2") {
        _0x58b3fa.setAttribute("i18n", "labTip1");
        _0x58b3fa.innerText = getI18n("labTip1");
        fixedKeySet.querySelector("[class=Special]").style.display = "none";
        fixedKeySet.querySelector("[class=KeyboardLight]").style.display = "none";
        let _0x53a7ef = fixedKeySet.querySelector("[class=Expand]").querySelector("[class=spacer]");
        if (_0x53a7ef != null) {
          _0x53a7ef.style.height = "40px";
        }
        fixedKeySet.style.display = "flex";
        _0x185deb.style.display = "none";
        _0x25521d.style.display = "none";
        _0x5f1c9d.style.display = "none";
      }
      if (_0x56e121.id === "keyManu3") {
        _0x58b3fa.setAttribute("i18n", "labTip2");
        _0x58b3fa.innerText = getI18n("labTip2");
        fixedKeySet.style.display = "none";
        _0x185deb.style.display = "flex";
        _0x25521d.style.display = "none";
        _0x5f1c9d.style.display = "none";
      }
      if (_0x56e121.id === "keyManu4") {
        _0x58b3fa.setAttribute("i18n", "labTip3");
        _0x58b3fa.innerText = getI18n("labTip3");
        fixedKeySet.style.display = "none";
        _0x185deb.style.display = "none";
        _0x25521d.style.display = "flex";
        _0x5f1c9d.style.display = "none";
      }
      if (_0x56e121.id === "keyManu10") {
        _0x58b3fa.setAttribute("i18n", "labTip1");
        _0x58b3fa.innerText = getI18n("labTip1");
        fixedKeySet.style.display = "none";
        _0x185deb.style.display = "none";
        _0x25521d.style.display = "none";
        _0x5f1c9d.style.display = "flex";
        _0x3a127b.style.overflow = "visible";
      } else {
        _0x3a127b.style.overflow = "auto";
      }
      autoSplitContent(needSplite);
    };
  });
  document.querySelectorAll("input[name=\"gamePad\"]").forEach(_0x224e93 => {
    _0x224e93.addEventListener("change", function (_0x297b7f) {
      if (this.checked) {
        console.log("当前选中的是：id=" + this.id + ", value=" + this.value);
        initGameKeyView(this.id);
      }
    });
  });
  btnResetKey.onclick = function () {
    if (curKey !== undefined) {
      btnResetKey.disabled = true;
      if (advKeys) {
        if (advKeys.filter(_0x521a4f => _0x521a4f.type === "RS").some(_0xa15d0c => _0xa15d0c.keys.some(_0x416f62 => _0x416f62.name === curKey.name))) {
          return showAlert(getI18n("rsTip1"));
        }
      }
      recordInput.value = curKey.name;
      comKeys = [];
      if (keymapDef.checked && recKeys.has(curKey.index)) {
        recKeys.delete(curKey.index);
        refreshRecordDot();
      }
      if (keymapFn.checked && fnKeys.has(curKey.index)) {
        fnKeys.delete(curKey.index);
        refreshRecordDot();
      }
      if (recMacros.has(curKey.index)) {
        recMacros.delete(curKey.index);
      }
      btnApplyKey.dispatchEvent(new Event("click"));
    }
  };
  btnApplyKey.onclick = async function () {
    console.log("设置自定义按键功能");
    btnApplyKey.disabled = true;
    document.getElementById("applyTip1")?.remove("applyTip1");
    if (curDevice !== undefined && curDevice !== null) {
      curProfile.defKeys = recKeys;
      curProfile.fnKeys = fnKeys;
      curProfile.recMacros = recMacros;
      let _0x403522 = JSON.stringify(profileSet, replacer);
      localStorage.setItem(curDevice.product, _0x403522);
    }
    await setKeyValue();
    await setFnKeyValue();
    await setMacroValue();
    await setAdvancedKeys();
    setTimeout(() => {
      btnApplyKey.disabled = false;
      refreshRecordDot();
    }, 300);
    btnResetKey.disabled = false;
  };
  let _0x2dcd50 = document.getElementById("macroType1");
  let _0x55511c = document.getElementById("macroType2");
  let _0x4bc066 = document.getElementById("macroType3");
  let _0x36135d = document.getElementById("macroType4");
  let _0x2b22f3 = document.getElementById("macroExecCount");
  _0x2dcd50.onchange = function () {
    if (curKey !== undefined && recMacros.has(curKey.index)) {
      recMacros.get(curKey.index).type = 0;
      recMacros.get(curKey.index).count = 0;
    }
  };
  _0x55511c.onchange = function () {
    if (curKey !== undefined && recMacros.has(curKey.index)) {
      recMacros.get(curKey.index).type = 1;
      recMacros.get(curKey.index).count = getMacroExecCount();
    }
  };
  _0x4bc066.onchange = function () {
    if (curKey !== undefined && recMacros.has(curKey.index)) {
      recMacros.get(curKey.index).type = 2;
      recMacros.get(curKey.index).count = 0;
    }
  };
  _0x36135d.onchange = function () {
    if (curKey !== undefined && recMacros.has(curKey.index)) {
      recMacros.get(curKey.index).type = 3;
      recMacros.get(curKey.index).count = 0;
    }
  };
  _0x2b22f3.oninput = function (_0x39c601) {
    handleInput(_0x39c601);
    if (_0x55511c.checked && curKey !== undefined && recMacros.has(curKey.index)) {
      recMacros.get(curKey.index).count = getMacroExecCount();
    }
  };
  document.getElementById("lightPower").onchange = async function () {
    await setDeviceLight();
  };
  const _0x14f07a = document.getElementById("lightModels");
  const _0x3b3c37 = document.getElementById("sideLightModels");
  const _0x2adc50 = document.getElementById("lightManu1");
  const _0x2ea414 = document.getElementById("lightManu2");
  _0x2adc50.onchange = function () {
    if (_0x2adc50.checked) {
      _0x14f07a.style.display = "grid";
      _0x3b3c37.style.display = "none";
      initLightView();
      const _0x3e080c = _0x14f07a.querySelector("input[type=\"radio\"]:checked");
      if (_0x3e080c) {
        refreshColorView(parseInt(_0x3e080c.value));
      }
    }
  };
  _0x2ea414.onchange = function () {
    if (_0x2ea414.checked) {
      _0x14f07a.style.display = "none";
      _0x3b3c37.style.display = "grid";
      initLightView();
      const _0x1ac740 = _0x3b3c37.querySelector("input[type=\"radio\"]:checked");
      if (_0x1ac740) {
        refreshColorView(parseInt(_0x1ac740.value));
      }
    }
  };
  const _0x19b25c = document.getElementById("lightBrightness");
  _0x19b25c.oninput = function () {
    const _0x226687 = (_0x19b25c.value - _0x19b25c.min) / (_0x19b25c.max - _0x19b25c.min) * 100 + "%";
    _0x19b25c.style.setProperty("--fill-percent", _0x226687);
    document.getElementById("pLightBrightness").innerText = this.value;
  };
  _0x19b25c.onchange = async function () {
    console.log("lightBrightness:", this.value);
    await setDeviceLight();
  };
  const _0x5d0ce9 = document.getElementById("lightSpeed");
  _0x5d0ce9.oninput = function () {
    const _0x12f755 = (_0x5d0ce9.value - _0x5d0ce9.min) / (_0x5d0ce9.max - _0x5d0ce9.min) * 100 + "%";
    _0x5d0ce9.style.setProperty("--fill-percent", _0x12f755);
    document.getElementById("pLightSpeed").innerText = this.value;
  };
  _0x5d0ce9.onchange = async function () {
    console.log("lightSpeed:", this.value);
    await setDeviceLight();
  };
  document.getElementById("lightDirectionDiv").querySelectorAll("input").forEach(_0xc07da => {
    _0xc07da.onchange = async function () {
      if (_0xc07da.checked) {
        console.log("lightDirection:" + _0xc07da.value);
        await setDeviceLight();
      }
    };
  });
  lightCustom1 = document.getElementById("lightCustom1");
  lightCustom2 = document.getElementById("lightCustom2");
  lightCustom1.onchange = async function () {
    if (lightCustom1.checked) {
      setKeysColor();
      await setCustomLight(curDevice.light, 0);
    }
  };
  lightCustom2.onchange = async function () {
    if (lightCustom2.checked) {
      setKeysColor();
      await setCustomLight(curDevice.light, 1);
    }
  };
  const _0x505f7d = document.getElementById("fullColor");
  _0x505f7d.onchange = async function () {
    console.log("is full color:", _0x505f7d.checked);
    await setDeviceLight();
  };
  const _0x310a65 = document.getElementById("btnMusicRhythm");
  _0x310a65.onclick = function () {
    if (confirm(getI18n("downloadTip"))) {
      console.log(_0x310a65.value);
      _0x310a65.disabled = true;
      const _0x4cc0ed = "../plug/" + _0x310a65.value;
      _0xd88efd(_0x4cc0ed, _0x310a65.value);
      setTimeout(function () {
        _0x310a65.disabled = false;
      }, 3000);
    }
  };
  const _0xd88efd = async (_0x26cad9, _0x1291d3) => {
    const _0xc685fc = document.createElement("a");
    _0xc685fc.href = _0x26cad9;
    _0xc685fc.download = _0x1291d3;
    document.body.appendChild(_0xc685fc);
    _0xc685fc.click();
    document.body.removeChild(_0xc685fc);
  };
  let _0x57ac43 = document.getElementsByClassName("performanceItem");
  Array.prototype.forEach.call(_0x57ac43, function (_0x3a700e) {
    _0x3a700e.querySelector("input").onchange = async function () {
      await _0x522e83();
    };
  });
  const _0x31f366 = document.getElementById("perCheckbox5");
  const _0x4102de = document.getElementById("perCheckbox6");
  _0x31f366.oninput = _0x4102de.oninput = function () {
    _0x522e83();
  };
  const _0x522e83 = async () => {
    let _0x28d6c3 = document.getElementById("perCheckbox1").checked ? 1 : 0;
    let _0x5cb07 = document.getElementById("perCheckbox2").checked ? 1 : 0;
    let _0x2412bf = (document.getElementById("perCheckbox3").checked ? 1 : 0) << 3;
    _0x2412bf += (document.getElementById("perCheckbox4").checked ? 1 : 0) << 2;
    _0x2412bf += _0x5cb07 << 1;
    _0x2412bf += _0x28d6c3 | 0;
    await setPerformanceValue(_0x2412bf, _0x4102de.checked);
    curProfile.other = _0x2412bf;
    curProfile.is6Key = _0x4102de.checked;
    let _0x540339 = JSON.stringify(profileSet, replacer);
    localStorage.setItem(curDevice.product, _0x540339);
  };
  iniColorPicker();
  initColorDeep();
  initColorSlider();
  let _0x583d9d = document.getElementById("colorR");
  let _0xf5f326 = document.getElementById("colorG");
  let _0x30cc87 = document.getElementById("colorB");
  _0x583d9d.oninput = async function (_0x552339) {
    handleInput(_0x552339);
    let _0x3a0276 = parseInt(_0x583d9d.value);
    let _0x4fecb6 = parseInt(_0xf5f326.value);
    let _0x12ae81 = parseInt(_0x30cc87.value);
    await setRgb(_0x3a0276, _0x4fecb6, _0x12ae81);
    await setCustomRgb(_0x3a0276, _0x4fecb6, _0x12ae81);
    await setDeviceLight();
  };
  _0xf5f326.oninput = async function (_0x313f43) {
    handleInput(_0x313f43);
    let _0xb00ac6 = parseInt(_0x583d9d.value);
    let _0x1df952 = parseInt(_0xf5f326.value);
    let _0x588c33 = parseInt(_0x30cc87.value);
    await setRgb(_0xb00ac6, _0x1df952, _0x588c33);
    await setCustomRgb(_0xb00ac6, _0x1df952, _0x588c33);
    await setDeviceLight();
  };
  _0x30cc87.oninput = async function (_0x269a53) {
    handleInput(_0x269a53);
    let _0xd9a176 = parseInt(_0x583d9d.value);
    let _0x164112 = parseInt(_0xf5f326.value);
    let _0x1feddd = parseInt(_0x30cc87.value);
    await setRgb(_0xd9a176, _0x164112, _0x1feddd);
    await setCustomRgb(_0xd9a176, _0x164112, _0x1feddd);
    await setDeviceLight();
  };
  document.getElementById("colorSet").querySelectorAll("button").forEach(_0x19bcb0 => {
    _0x19bcb0.onclick = async function () {
      let _0x2a8dda;
      let _0x197f76;
      let _0x3518d9;
      let _0x26f8c2 = _0x19bcb0.style.backgroundColor;
      if (_0x26f8c2.startsWith("rgb(")) {
        let _0x481f53 = _0x26f8c2.split("(")[1].split(")")[0].split(",");
        _0x2a8dda = parseInt(_0x481f53[0], 10);
        _0x197f76 = parseInt(_0x481f53[1], 10);
        _0x3518d9 = parseInt(_0x481f53[2], 10);
        await setRgb(_0x2a8dda, _0x197f76, _0x3518d9);
        await setCustomRgb(_0x2a8dda, _0x197f76, _0x3518d9);
        await setDeviceLight();
        curR = _0x2a8dda;
        curG = _0x197f76;
        curB = _0x3518d9;
      }
    };
  });
  let _0x1d4544 = false;
  let _0x318dce = 0;
  let _0x522165 = 0;
  let _0x209b34 = 0;
  let _0xb89265 = 0;
  const _0x4de4d3 = document.getElementById("draggableBox");
  let _0x2b9502 = document.getElementById("devViewDiv");
  _0x2b9502.addEventListener("mousedown", function (_0x1a1f24) {
    if (menu4.checked && (_0xf1e9b0.checked || _0x52734d.checked || _0x2c7037.checked) && _0x1a1f24.target !== _0x16df64 && _0x1a1f24.target !== _0x31766b && _0x1a1f24.target !== _0x45f087 && _0x1a1f24.target !== _0x3e9ad3 || menu2.checked && curDevice.light.mode === 10) {
      let _0x813a68 = _0x2b9502.getBoundingClientRect();
      let _0x4ec69b = _0x1a1f24.clientX;
      let _0x53db51 = _0x1a1f24.clientY;
      _0x318dce = (_0x4ec69b - _0x813a68.left) / scale;
      _0x209b34 = (_0x53db51 - _0x813a68.top) / scale;
      _0x522165 = _0x318dce;
      _0xb89265 = _0x209b34;
      _0x4de4d3.style.left = _0x318dce + "px";
      _0x4de4d3.style.top = _0x209b34 + "px";
      _0x4de4d3.style.width = "0px";
      _0x4de4d3.style.height = "0px";
      _0x4de4d3.style.display = "flex";
      _0x1d4544 = true;
    }
  });
  window.addEventListener("mousemove", function (_0x436889) {
    if (_0x1d4544) {
      let _0x429a44 = _0x2b9502.getBoundingClientRect();
      let _0x434b29 = _0x436889.clientX;
      let _0x185763 = _0x436889.clientY;
      _0x522165 = (_0x434b29 - _0x429a44.left) / scale;
      _0xb89265 = (_0x185763 - _0x429a44.top) / scale;
      let _0x3df5c9 = Math.min(_0x318dce, _0x522165);
      let _0x25c174 = Math.min(_0x209b34, _0xb89265);
      let _0x1f8995 = Math.abs(_0x522165 - _0x318dce);
      let _0x3ca6cd = Math.abs(_0xb89265 - _0x209b34);
      _0x4de4d3.style.left = _0x3df5c9 + "px";
      _0x4de4d3.style.top = _0x25c174 + "px";
      _0x4de4d3.style.width = _0x1f8995 + "px";
      _0x4de4d3.style.height = _0x3ca6cd + "px";
    }
  });
  window.addEventListener("mouseup", function (_0x465d1d) {
    if (_0x1d4544) {
      let _0x1fc205 = _0x4de4d3.getBoundingClientRect();
      _0x1d4544 = false;
      _0x4de4d3.style.display = "none";
      let _0x3963c6 = false;
      if (_0x1fc205.width < 5 && _0x1fc205.height < 5) {
        return;
      }
      keyBtn.forEach(_0x33c04d => {
        let _0x4d8506 = _0x33c04d.getBoundingClientRect();
        if (_0x4d8506.left + _0x33c04d.offsetWidth / 2 > _0x1fc205.left && _0x4d8506.right - _0x33c04d.offsetWidth / 2 < _0x1fc205.right && _0x4d8506.top + _0x33c04d.offsetHeight / 2 > _0x1fc205.top && _0x4d8506.bottom - _0x33c04d.offsetHeight / 2 < _0x1fc205.bottom) {
          let _0x409960 = document.getElementById(_0x33c04d.htmlFor);
          _0x409960.checked = true;
          if (!_0x3963c6 && menu4.checked) {
            _0x3963c6 = true;
            _0x409960.dispatchEvent(new Event("change"));
          }
          let _0x2a8cb5 = findDeviceKey(_0x33c04d.htmlFor);
          if (_0x2a8cb5 != null) {
            if (!checkedKeys.some(_0x3aabeb => _0x3aabeb.code === _0x2a8cb5.code)) {
              console.log("key", _0x2a8cb5);
              checkedKeys.push(_0x2a8cb5);
            }
          }
        }
      });
      console.log("选中按键数：", checkedKeys.length, checkedKeys);
      if (checkedKeys.length === keyBtn.length && menu4.checked) {
        _0x16df64.checked = true;
      }
      if (checkedKeys.length > 0 && menu4.checked) {
        refreshTriggerSlider(triggerAll.value);
      }
    }
    if (isRecordMacro) {
      if (_0x465d1d.target === _0x1dadea || _0x465d1d.target === _0x3360db || _0x465d1d.target === _0x4dfa2a || _0x465d1d.target === _0x3d8c22 || _0x465d1d.target === _0x42be69) {
        return;
      }
      console.log(_0x465d1d.button);
      let _0x30e347 = new Date();
      let _0x2554b9 = _0x30e347.getTime() - curTime.getTime();
      curTime = _0x30e347;
      console.log(_0x2554b9);
      let _0x8162ee = isFirstStep ? 0 : _0x2554b9;
      if (_0x259e2a.checked) {
        _0x8162ee = 0;
      }
      if (_0x4c19ef.checked) {
        _0x8162ee = parseInt(_0x1e0362.value);
      }
      let _0x10f352 = new Step();
      _0x10f352.type = 1;
      _0x10f352.state = 0;
      if (_0x465d1d.button === 0) {
        _0x10f352.key = findFixedKey("MouseLeft");
      } else if (_0x465d1d.button === 1) {
        _0x10f352.key = findFixedKey("MouseMiddle");
      } else if (_0x465d1d.button === 2) {
        _0x10f352.key = findFixedKey("MouseRight");
      }
      _0x10f352.tag = findStepTag(curMacro, _0x10f352.key.code);
      _0x10f352.delay = _0x8162ee;
      curMacro.steps.push(_0x10f352);
      refreshMacroItems(curMacro.steps);
      _0x4d5d4c.scrollTop = _0x4d5d4c.scrollHeight - _0x4d5d4c.clientHeight;
      isFirstStep = false;
    }
  });
  window.oncontextmenu = function (_0x9e8ab) {
    _0x9e8ab.preventDefault();
    if (menu2.checked || menu4.checked) {
      clearTriggerButtonState();
    }
  };
  _0x4cdc70.onchange = async function () {
    let _0x69c414 = _0x4cdc70.checked ? _0x33e9e1.checked ? 13 : 12 : 0;
    checkedKeys.forEach(_0x4711a8 => {
      _0x4711a8.trigger.mode = _0x69c414;
      _0x4711a8.trigger.interval1 = parseInt(triggerDown.value);
      _0x4711a8.trigger.interval2 = _0x33e9e1.checked ? parseInt(triggerUp.value) : parseInt(triggerDown.value);
      refreshKeyButton(_0x4711a8);
    });
    refreshTriggerView(this.checked);
    await setAnyTriggerValue(_0x69c414);
    refreshProfileTrigger();
  };
  _0x33e9e1.onchange = async function () {
    let _0x5d7881 = _0x4cdc70.checked ? _0x33e9e1.checked ? 13 : 12 : 0;
    checkedKeys.forEach(_0x28834b => {
      _0x28834b.trigger.mode = _0x5d7881;
      _0x28834b.trigger.interval1 = parseInt(triggerDown.value);
      _0x28834b.trigger.interval2 = _0x33e9e1.checked ? parseInt(triggerUp.value) : parseInt(triggerDown.value);
      refreshKeyButton(_0x28834b);
    });
    refreshTriggerTravel(_0x33e9e1.checked);
    await setAnyTriggerValue(_0x5d7881);
    refreshProfileTrigger();
  };
  dbTop = document.getElementById("dbTop");
  dbTop.addEventListener("toggle", async _0x1b33a3 => {
    checkedKeys.forEach(_0x2c80e5 => {
      _0x2c80e5.trigger.deadbandTop = parseInt(dbTop.value);
      _0x2c80e5.trigger.deadbandBottom = parseInt(dbBottom.value);
      refreshKeyButton(_0x2c80e5);
    });
    await setDeadBand();
    refreshProfileTrigger();
  });
  dbBottom = document.getElementById("dbBottom");
  dbBottom.addEventListener("toggle", async _0x53b4a0 => {
    checkedKeys.forEach(_0x2b1f93 => {
      _0x2b1f93.trigger.deadbandTop = parseInt(dbTop.value);
      _0x2b1f93.trigger.deadbandBottom = parseInt(dbBottom.value);
      refreshKeyButton(_0x2b1f93);
    });
    await setDeadBand();
    refreshProfileTrigger();
  });
  let _0x2f5f15 = document.getElementById("reviseKeys");
  async function _0x5dd167() {
    let _0x4dc824;
    _0x2f5f15.disabled = true;
    setTimeout(() => {
      _0x2f5f15.disabled = false;
    }, 2000);
    if (isCalibrationing) {
      isCalibrationing = false;
      _0x2f5f15.setAttribute("i18n", "calibrationStart");
      _0x2f5f15.innerText = getI18n("calibrationStart");
      if (_0x4dc824) {
        _0x4dc824.remove();
      }
      if (isAnyKeyCalibration) {
        await reviseKeys(16, 0);
      } else {
        await reviseKeys(8, 1);
      }
    } else {
      isCalibrationing = true;
      keyBtn.forEach(_0x1cb46e => {
        const _0x4243e2 = _0x1cb46e.querySelector("[class=devKeyPanelView]");
        if (_0x4243e2 != null) {
          _0x4243e2.style.backgroundColor = "";
          _0x4243e2.childNodes[0].style.color = "";
          _0x4243e2.style.setProperty("--btn-color", "");
        }
        let _0x3f21a7 = document.getElementById(_0x1cb46e.htmlFor);
        _0x3f21a7.checked = false;
        _0x3f21a7.dispatchEvent(new Event("change"));
      });
      let _0x47dbe0 = document.getElementById("deviceBg");
      _0x4dc824 = document.createElement("div");
      _0x4dc824.setAttribute("id", "calibrationTip");
      _0x4dc824.classList.add("calibrationTip");
      _0x4dc824.innerText = getI18n("alertCalibrationProgress");
      _0x47dbe0.appendChild(_0x4dc824);
      _0x2f5f15.setAttribute("i18n", "calibrationStop");
      _0x2f5f15.innerText = getI18n("calibrationStop");
      if (isAnyKeyCalibration) {
        showAlert(getI18n("alertCalibrationAnyKey"));
        await reviseKeys(15, 0);
      } else {
        showAlert(getI18n("alertCalibrationAllKey"));
        await reviseKeys(8, 0);
      }
    }
  }
  _0x2f5f15.onmousedown = async function () {
    isChangeCalibration = false;
    await _0x5dd167();
  };
  let _0x51a36d = document.getElementById("advDiv");
  let _0xf83843 = document.getElementById("advTypeInfo");
  let _0x39335b = document.getElementById("advTypeRadio1");
  let _0x47f432 = document.getElementById("advTypeRadio2");
  let _0x122d3d = document.getElementById("advTypeRadio3");
  let _0x3e1985 = document.getElementById("advTypeRadio4");
  let _0x14129e = document.getElementById("advTypeRadio5");
  _0x39335b.onchange = function () {
    _0xf83843.innerText = getI18n("advTip1");
    _0x4db165.style.display = "none";
    _0x120d89.style.display = "none";
    _0x2af368.style.display = "flex";
    _0x3ff2ca.style.display = "none";
    _0x93000.style.display = "none";
    if (curDksKey === undefined || curDksKey === null) {
      curDksKey = new AdvancedKey();
      curDksKey.index = curAdvIndex;
      curDksKey.route1 = 15;
      curDksKey.route2 = 36;
      curDksKey.route3 = 36;
      curDksKey.route4 = 15;
      curDksKey.duration = 15;
    }
    curDksKey.type = "DKS";
    if (curDksKey.index < 0) {
      curDksKey.index = getAdvIndex();
    }
    refreshDksButton();
    _0x385415.innerText = (curDksKey.route1 / 10).toFixed(1) + "mm";
    if (curDevice.product === "MKGA75HEARGB") {
      _0xaec03d.innerText = "3.2mm";
      _0x33b3ad.innerText = "3.2mm";
    } else {
      _0xaec03d.innerText = (curDksKey.route2 / 10).toFixed(1) + "mm";
      _0x33b3ad.innerText = (curDksKey.route3 / 10).toFixed(1) + "mm";
    }
    _0x2b7489.innerText = (curDksKey.route4 / 10).toFixed(1) + "mm";
    _0x54c973.value = curDksKey.keys[0].name;
    _0x213bc8.value = curDksKey.keys[1].name;
    _0x451f40.value = curDksKey.keys[2].name;
    _0x39b9a3.value = curDksKey.keys[3].name;
    _0x54c973.classList.remove("tglTmInputFocus");
    _0x213bc8.classList.remove("tglTmInputFocus");
    _0x451f40.classList.remove("tglTmInputFocus");
    _0x39b9a3.classList.remove("tglTmInputFocus");
    curEdit = undefined;
  };
  _0x47f432.onchange = function () {
    _0xf83843.innerText = getI18n("advTip2");
    _0x4db165.style.display = "none";
    _0x120d89.style.display = "flex";
    _0x2af368.style.display = "none";
    _0x3ff2ca.style.display = "none";
    _0x93000.style.display = "none";
    if (curMtKey === undefined || curMtKey === null) {
      curMtKey = new AdvancedKey();
      curMtKey.index = curAdvIndex;
      curMtKey.duration = 15;
    }
    _0x5c1ad1.value = curMtKey.keys[0].name;
    _0x1b7114.value = curMtKey.keys[1].name;
    _0x2c90db.value = curMtKey.duration;
    _0x2c90db.dispatchEvent(new Event("input"));
    curMtKey.type = "MT";
    if (curMtKey.index < 0) {
      curMtKey.index = getAdvIndex();
    }
    _0x5c1ad1.classList.remove("tglTmInputFocus");
    _0x1b7114.classList.remove("tglTmInputFocus");
    curEdit = undefined;
  };
  _0x122d3d.onchange = function () {
    _0xf83843.innerText = getI18n("advTip3");
    _0x4db165.style.display = "flex";
    _0x120d89.style.display = "none";
    _0x2af368.style.display = "none";
    _0x3ff2ca.style.display = "none";
    _0x93000.style.display = "none";
    if (curTglKey === undefined || curTglKey === null) {
      curTglKey = new AdvancedKey();
      curTglKey.index = curAdvIndex;
    }
    curTglKey.type = "TGL";
    if (curTglKey.index < 0) {
      curTglKey.index = getAdvIndex();
    }
    _0x57e9fd.value = curTglKey.keys[0].name;
    _0x57e9fd.classList.remove("tglTmInputFocus");
    curEdit = undefined;
  };
  _0x3e1985.onchange = function () {
    _0xf83843.innerText = getI18n("advTip4");
    _0x4db165.style.display = "none";
    _0x120d89.style.display = "none";
    _0x2af368.style.display = "none";
    _0x3ff2ca.style.display = "flex";
    _0x93000.style.display = "none";
    if (curRSKey === undefined || curRSKey === null) {
      curRSKey = new AdvancedKey();
      curRSKey.index = curAdvIndex;
    }
    curRSKey.type = "RS";
    if (curRSKey.index < 0) {
      curRSKey.index = getAdvIndex();
    }
    _0x36bb8e.value = curRSKey.keys[0].name;
    _0x48d374.value = curRSKey.keys[1].name;
    _0x36bb8e.classList.remove("tglTmInputFocus");
    _0x48d374.classList.remove("tglTmInputFocus");
    curEdit = undefined;
  };
  _0x14129e.onchange = function () {
    _0xf83843.innerText = getI18n("advTip5");
    _0x4db165.style.display = "none";
    _0x120d89.style.display = "none";
    _0x2af368.style.display = "none";
    _0x3ff2ca.style.display = "none";
    _0x93000.style.display = "flex";
    if (curRKRTKey === undefined || curRKRTKey === null) {
      curRKRTKey = new AdvancedKey();
      curRKRTKey.index = curAdvIndex;
    }
    curRKRTKey.type = "RKRT";
    if (curRKRTKey.index < 0) {
      curRKRTKey.index = getAdvIndex();
    }
    _0x1d6f0b.value = curRKRTKey.keys[1].name;
    _0x1d6f0b.classList.remove("tglTmInputFocus");
    curEdit = undefined;
  };
  _0x2c90db.oninput = function () {
    const _0x2fda84 = (_0x2c90db.value - _0x2c90db.min) / (_0x2c90db.max - _0x2c90db.min) * 100 + "%";
    _0x2c90db.style.setProperty("--fill-percent", _0x2fda84);
    let _0x1a6d15 = _0x2c90db.value * 10;
    document.getElementById("labMtTime").innerText = _0x1a6d15 + "ms";
  };
  _0x2c90db.onchange = function () {
    curMtKey.duration = _0x2c90db.value;
  };
  let _0x5a2d9e = false;
  const _0x34c6a6 = document.getElementById("dksInfoDetail");
  _0x34c6a6.querySelectorAll("label").forEach(_0x24a142 => {
    let _0x3ad926 = parseInt(_0x24a142.innerText);
    let _0x5ec47b = Math.floor(_0x3ad926 / 4);
    let _0x387309 = Math.floor(_0x3ad926 % 4);
    let _0x2447fe = document.getElementById(_0x24a142.htmlFor);
    _0x24a142.onclick = function (_0x521d34) {
      _0x521d34.preventDefault();
    };
    _0x24a142.onmousedown = function () {
      if (_0x24a142.offsetWidth > 20 || _0x2447fe.checked) {
        _0x24a142.style.width = "20px";
        _0x2447fe.checked = false;
        setDksValue();
      } else {
        _0x2447fe.checked = true;
        setDksValue();
      }
      if (_0x387309 < 3) {
        _0x5a2d9e = true;
        _0x34c6a6.style.cursor = "e-resize";
        console.log(_0x2447fe.id, _0x2447fe.checked);
        let _0x25705d = getEndDksBtn(_0x24a142, _0x5ec47b, _0x387309);
        window.onmousemove = function (_0x3508ee) {
          if (_0x5a2d9e) {
            _0x2447fe.checked = true;
            const _0x2d1843 = _0x3508ee.clientX - _0x24a142.getBoundingClientRect().left;
            const _0x31558f = 20;
            const _0x3dcaa9 = _0x25705d.offsetLeft - _0x24a142.offsetLeft;
            const _0x1840b1 = Math.max(_0x31558f, Math.min(_0x3dcaa9, _0x2d1843));
            _0x24a142.style.width = _0x1840b1 + "px";
          }
        };
        window.onmouseup = function () {
          if (_0x5a2d9e) {
            _0x5a2d9e = false;
            _0x34c6a6.style.cursor = "default";
            setDksBtnWidth(_0x24a142, _0x5ec47b, _0x387309);
            setDksValue();
          }
        };
      }
    };
  });
  let _0x5dd3be = document.getElementById("dksTrigger");
  let _0x11076f = document.getElementById("dksTriggerLabel");
  let _0x23bd41 = document.getElementById("dksTriApply");
  let _0x8261a = document.getElementById("dksTriCancel");
  _0x385415.onclick = _0x2b7489.onclick = function () {
    let _0x58ecd0 = _0x385415.getBoundingClientRect();
    dksTriggerDiv.style.display = "flex";
    dksTriggerDiv.style.left = _0x58ecd0.left - _0x58ecd0.width + "px";
    dksTriggerDiv.style.top = _0x58ecd0.top - 100 + "px";
    _0x5dd3be.value = curDksKey.route1;
    _0x5dd3be.max = curDksKey.route2;
    _0x11076f.innerText = (_0x5dd3be.value / 10).toFixed(1) + "mm";
    _0x5dd3be.dispatchEvent(new Event("input"));
  };
  _0x5dd3be.oninput = function () {
    const _0xb9ec8e = (_0x5dd3be.value - _0x5dd3be.min) / (_0x5dd3be.max - _0x5dd3be.min) * 100 + "%";
    _0x5dd3be.style.setProperty("--fill-percent", _0xb9ec8e);
    _0x11076f.innerText = (_0x5dd3be.value / 10).toFixed(1) + "mm";
  };
  _0x23bd41.onclick = function () {
    curDksKey.route1 = _0x5dd3be.value;
    curDksKey.route4 = _0x5dd3be.value;
    _0x385415.innerText = (_0x5dd3be.value / 10).toFixed(1) + "mm";
    _0x2b7489.innerText = (_0x5dd3be.value / 10).toFixed(1) + "mm";
    dksTriggerDiv.style.display = "none";
  };
  _0x8261a.onclick = function () {
    dksTriggerDiv.style.display = "none";
  };
  let _0x50f324 = document.getElementById("btnAdvApply");
  let _0x3d503b = document.getElementById("btnAdvCancel");
  _0x50f324.onclick = async function () {
    _0x51a36d.style.display = "none";
    dksTriggerDiv.style.display = "none";
    if (_0x39335b.checked) {
      curAdvKey = curDksKey;
    }
    if (_0x47f432.checked) {
      curAdvKey = curMtKey;
    }
    if (_0x122d3d.checked) {
      curAdvKey = curTglKey;
    }
    if (_0x3e1985.checked) {
      curAdvKey = curRSKey;
    }
    if (_0x14129e.checked) {
      curAdvKey = curRKRTKey;
    }
    let _0xa76969 = advKeys.find(_0x2020b9 => _0x2020b9.index === curAdvKey.index);
    let _0x2ed776 = -1;
    if (_0xa76969 != null) {
      _0x2ed776 = advKeys.indexOf(_0xa76969);
    }
    if (_0x2ed776 >= 0 && _0x2ed776 < advKeys.length) {
      advKeys.splice(_0x2ed776, 1, curAdvKey);
      if (curKey !== undefined) {
        if (keymapDef.checked && recKeys.has(curKey.index)) {
          recKeys.forEach((_0x3b929a, _0x12e14b) => {
            if (_0x3b929a.code1 === 23 && _0x3b929a.code3 === curAdvKey.index) {
              recordInput.value = curAdvKey.index + 1 + "#" + curAdvKey.type;
            }
          });
        }
        if (keymapFn.checked && fnKeys.has(curKey.index)) {
          fnKeys.forEach((_0xb05fc7, _0x2907a8) => {
            if (_0xb05fc7.code1 === 23 && _0xb05fc7.code3 === curAdvKey.index) {
              recordInput.value = curAdvKey.index + 1 + "#" + curAdvKey.type;
            }
          });
        }
      }
    } else {
      advKeys.push(curAdvKey);
    }
    advKeys.sort(function (_0x17ab2a, _0x58381f) {
      return _0x17ab2a.index - _0x58381f.index;
    });
    if (_0x3e1985.checked) {
      const _0x4fe39c = curAdvKey.keys.filter(_0x1f678f => _0x1f678f?.name).map(_0x392c13 => findDeviceKey(_0x392c13.name, "name")).filter(_0x569b2b => _0x569b2b?.name);
      if (_0x4fe39c.length === 0) {
        return;
      }
      const _0x2c2855 = _0x4fe39c.map(_0x2d1ff4 => _0x2d1ff4.name).join(" ");
      const _0x24d5c8 = (_0x2ed776 >= 0 ? _0x2ed776 + 1 : advKeys.length) + "#" + curAdvKey.type + "->" + _0x2c2855;
      _0x4fe39c.forEach(_0x52973a => {
        setRecordKeyByKeyId(_0x52973a.index, _0x24d5c8);
        const _0x113a32 = document.querySelector("label[for=\"" + _0x52973a.code + "\"]");
        if (_0x113a32) {
          refreshRecordDot([_0x113a32]);
        }
      });
      if (confirm(getI18n("applyTip2"))) {
        btnApplyKey.dispatchEvent(new Event("click"));
      }
    }
    refreshAdvList();
    curProfile.advKeys = deepCopy(advKeys);
    let _0x5289e3 = JSON.stringify(profileSet, replacer);
    localStorage.setItem(curDevice.product, _0x5289e3);
  };
  _0x3d503b.onclick = function () {
    _0x51a36d.style.display = "none";
    dksTriggerDiv.style.display = "none";
  };
  let _0x51c255 = document.getElementById("prcsPower");
  let _0x13b2f4 = document.getElementById("btnApplyPrcs");
  _0x51c255.onchange = async function () {
    _0x13b2f4.dispatchEvent(new Event("click"));
  };
  _0x13b2f4.onclick = async function () {
    await setPrcsPower(_0x51c255.checked);
    await setPrcsData();
    curProfile.prcsPower = _0x51c255.checked ? 1 : 0;
    curProfile.prcses = deepCopy(prcses);
    let _0x42235d = JSON.stringify(profileSet, replacer);
    localStorage.setItem(curDevice.product, _0x42235d);
  };
  let _0x238350 = document.getElementById("prcsList");
  let _0x173c8f = document.getElementById("btnCreatePrcs");
  let _0x5a418c = document.getElementById("btnDeletePrcs");
  _0x173c8f.onclick = function () {
    if (prcses.length < 20) {
      let _0x435bd6 = new Prcs();
      _0x435bd6.index = getPrcsIndex();
      _0x435bd6.name = "SOCD" + (_0x435bd6.index + 1);
      prcses.push(_0x435bd6);
      refreshPrcsList(prcses);
      _0x238350.scrollTop = _0x238350.scrollHeight - _0x238350.clientHeight;
      const _0x4b9e4b = _0x238350.querySelectorAll("input");
      if (_0x4b9e4b.length > 0) {
        const _0x3ae23e = _0x4b9e4b[_0x4b9e4b.length - 1];
        _0x3ae23e.checked = true;
        _0x3ae23e.dispatchEvent(new Event("change"));
      }
    } else {
      showAlert(getI18n("alertPrcsWarning"));
    }
  };
  _0x5a418c.onclick = function () {
    let _0x33f4bf = prcses.indexOf(curPrcs);
    if (_0x33f4bf >= 0 && _0x33f4bf < prcses.length) {
      prcses.splice(_0x33f4bf, 1);
    }
    refreshPrcsList(prcses);
    _0x238350.scrollTop = _0x238350.scrollHeight - _0x238350.clientHeight;
    const _0xb00de5 = _0x238350.querySelectorAll("input");
    if (_0xb00de5.length > 0) {
      const _0x46e687 = _0xb00de5[_0xb00de5.length - 1];
      _0x46e687.checked = true;
      _0x46e687.dispatchEvent(new Event("change"));
    }
    _0x13b2f4.dispatchEvent(new Event("click"));
  };
  let _0x26f83c = document.getElementById("piEdit1");
  let _0x186d3f = document.getElementById("piEdit2");
  _0x26f83c.onfocus = function () {
    curEdit = _0x26f83c;
    _0x26f83c.classList.add("tglTmInputFocus");
    _0x186d3f.classList.remove("tglTmInputFocus");
  };
  _0x186d3f.onfocus = function () {
    curEdit = _0x186d3f;
    _0x186d3f.classList.add("tglTmInputFocus");
    _0x26f83c.classList.remove("tglTmInputFocus");
  };
  document.getElementById("prcsModel").querySelectorAll("input").forEach(_0x20f2aa => {
    _0x20f2aa.onchange = function () {
      if (_0x20f2aa.checked) {
        if (_0x20f2aa.id === "prcsModel1") {
          curPrcs.model = 0;
        }
        if (_0x20f2aa.id === "prcsModel2") {
          curPrcs.model = 1;
        }
        if (_0x20f2aa.id === "prcsModel3") {
          curPrcs.model = 2;
        }
        if (_0x20f2aa.id === "prcsModel4") {
          curPrcs.model = 3;
        }
      }
    };
  });
  let _0x582175 = document.getElementById("macroDiv");
  let _0x3d8c22 = document.getElementById("btnMacroApply");
  let _0x42be69 = document.getElementById("btnMacroCancel");
  _0x3d8c22.onclick = function () {
    _0x582175.style.display = "none";
    if (isRecordMacro) {
      _0x1dadea.dispatchEvent(new Event("click"));
    }
    let _0x511c36 = macros.indexOf(curMacro);
    if (_0x511c36 >= 0 && _0x511c36 < macros.length) {
      macros.splice(_0x511c36, 1, curMacro);
    } else {
      macros.push(curMacro);
    }
    macros.sort(function (_0x77767a, _0xd14091) {
      return _0x77767a.index - _0xd14091.index;
    });
    refreshMacroList(macros);
    curProfile.macros = deepCopy(macros);
    let _0x185e81 = JSON.stringify(profileSet, replacer);
    localStorage.setItem(curDevice.product, _0x185e81);
  };
  _0x42be69.onclick = function () {
    _0x582175.style.display = "none";
    if (isRecordMacro) {
      _0x1dadea.dispatchEvent(new Event("click"));
    }
  };
  let _0x4d5d4c = document.getElementById("macroItemList");
  let _0x259e2a = document.getElementById("mdRadio2");
  let _0x4c19ef = document.getElementById("mdRadio3");
  let _0x1e0362 = document.getElementById("mdDefault");
  let _0x1dadea = document.getElementById("btnRecordMacro");
  let _0x3360db = _0x1dadea.querySelector("img");
  let _0x4dfa2a = _0x1dadea.querySelector("label");
  _0x1dadea.onclick = function () {
    if (curMacro !== undefined) {
      let _0x3f4a72 = _0x1dadea.querySelector("img");
      if (isRecordMacro) {
        isRecordMacro = false;
        _0x3f4a72.src = "image/icon_whiteDot.png";
      } else {
        isRecordMacro = true;
        isFirstStep = true;
        _0x3f4a72.src = "image/icon_redDot.png";
        curTime = new Date();
      }
    }
  };
  window.addEventListener("keydown", function (_0x13a6d1) {
    if (isRecordMacro) {
      let _0x28a044 = _0x13a6d1.code;
      if (_0x13a6d1.key === "Shift" && _0x13a6d1.code === "") {
        _0x28a044 = "ShiftRight";
      }
      console.log("按下", _0x28a044);
      _0x13a6d1.preventDefault();
      let _0x3fe892 = new Date();
      let _0x66dd4b = _0x3fe892.getTime() - curTime.getTime();
      curTime = _0x3fe892;
      console.log(_0x66dd4b);
      let _0x339955 = isFirstStep ? 0 : _0x66dd4b;
      if (_0x259e2a.checked) {
        _0x339955 = 0;
      }
      if (_0x4c19ef.checked) {
        _0x339955 = parseInt(_0x1e0362.value);
      }
      let _0x37eec2 = new Step();
      _0x37eec2.tag = getStepTag(curMacro);
      _0x37eec2.type = 0;
      _0x37eec2.state = 1;
      _0x37eec2.key = findFixedKey(_0x28a044);
      _0x37eec2.delay = _0x339955;
      curMacro.steps.push(_0x37eec2);
      if (_0x28a044 === "MetaLeft" || _0x28a044 === "MetaRight") {
        _0x339955 = isFirstStep ? 0 : 55;
        if (_0x259e2a.checked) {
          _0x339955 = 0;
        }
        if (_0x4c19ef.checked) {
          _0x339955 = parseInt(_0x1e0362.value);
        }
        let _0x2872e = new Step();
        _0x2872e.tag = findStepTag(curMacro, _0x28a044);
        _0x2872e.type = 0;
        _0x2872e.state = 0;
        _0x2872e.key = findFixedKey(_0x28a044);
        _0x2872e.delay = _0x339955;
        curMacro.steps.push(_0x2872e);
      }
      refreshMacroItems(curMacro.steps);
      _0x4d5d4c.scrollTop = _0x4d5d4c.scrollHeight - _0x4d5d4c.clientHeight;
      isFirstStep = false;
    }
  });
  window.addEventListener("keyup", function (_0x4b2a5f) {
    if (isRecordMacro) {
      let _0x1c1adc = _0x4b2a5f.code;
      if (_0x4b2a5f.key === "Shift" && _0x4b2a5f.code === "") {
        _0x1c1adc = "ShiftRight";
      }
      console.log("松开", _0x1c1adc);
      _0x4b2a5f.preventDefault();
      let _0x557721 = new Date();
      let _0x312ccb = _0x557721.getTime() - curTime.getTime();
      curTime = _0x557721;
      console.log(_0x312ccb);
      let _0x214fc0 = 0;
      if (_0x1c1adc === "F8" || _0x1c1adc === "PrintScreen") {
        _0x214fc0 = isFirstStep ? 0 : 55;
        if (_0x259e2a.checked) {
          _0x214fc0 = 0;
        }
        if (_0x4c19ef.checked) {
          _0x214fc0 = parseInt(_0x1e0362.value);
        }
        let _0x2cf4ae = new Step();
        _0x2cf4ae.tag = getStepTag(curMacro);
        _0x2cf4ae.type = 0;
        _0x2cf4ae.state = 1;
        _0x2cf4ae.key = findFixedKey(_0x1c1adc);
        _0x2cf4ae.delay = _0x214fc0;
        curMacro.steps.push(_0x2cf4ae);
      }
      _0x214fc0 = isFirstStep ? 0 : _0x312ccb;
      if (_0x259e2a.checked) {
        _0x214fc0 = 0;
      }
      if (_0x4c19ef.checked) {
        _0x214fc0 = parseInt(_0x1e0362.value);
      }
      let _0x281c03 = new Step();
      _0x281c03.tag = findStepTag(curMacro, _0x1c1adc);
      _0x281c03.type = 0;
      _0x281c03.state = 0;
      _0x281c03.key = findFixedKey(_0x1c1adc);
      _0x281c03.delay = _0x214fc0;
      curMacro.steps.push(_0x281c03);
      refreshMacroItems(curMacro.steps);
      _0x4d5d4c.scrollTop = _0x4d5d4c.scrollHeight - _0x4d5d4c.clientHeight;
      isFirstStep = false;
    }
  });
  window.onmousedown = function (_0x2bcdea) {
    if (isRecordMacro) {
      if (_0x2bcdea.target === _0x1dadea || _0x2bcdea.target === _0x3360db || _0x2bcdea.target === _0x4dfa2a || _0x2bcdea.target === _0x3d8c22 || _0x2bcdea.target === _0x42be69) {
        return;
      }
      console.log(_0x2bcdea.button);
      let _0x4d1b64 = new Date();
      let _0x56c040 = _0x4d1b64.getTime() - curTime.getTime();
      curTime = _0x4d1b64;
      console.log(_0x56c040);
      let _0x51965c = isFirstStep ? 0 : _0x56c040;
      if (_0x259e2a.checked) {
        _0x51965c = 0;
      }
      if (_0x4c19ef.checked) {
        _0x51965c = parseInt(_0x1e0362.value);
      }
      let _0x2134af = new Step();
      _0x2134af.tag = getStepTag(curMacro);
      _0x2134af.type = 1;
      _0x2134af.state = 1;
      if (_0x2bcdea.button === 0) {
        _0x2134af.key = findFixedKey("MouseLeft");
      } else if (_0x2bcdea.button === 1) {
        _0x2134af.key = findFixedKey("MouseMiddle");
      } else if (_0x2bcdea.button === 2) {
        _0x2134af.key = findFixedKey("MouseRight");
      }
      _0x2134af.delay = _0x51965c;
      curMacro.steps.push(_0x2134af);
      refreshMacroItems(curMacro.steps);
      _0x4d5d4c.scrollTop = _0x4d5d4c.scrollHeight - _0x4d5d4c.clientHeight;
      isFirstStep = false;
    }
  };
  let _0x29835b = document.getElementById("mInfoKey");
  let _0x5a85ee = document.getElementById("mInfoMouse");
  let _0x3d5250 = document.getElementById("macroKeyboardEvent");
  let _0x3e663c = document.getElementById("macroMouseEvent");
  _0x3d5250.onchange = function () {
    if (_0x3d5250.checked) {
      _0x29835b.style.display = "flex";
      _0x5a85ee.style.display = "none";
      _0x1419db.value = "";
    }
  };
  _0x3e663c.onchange = function () {
    if (_0x3e663c.checked) {
      _0x29835b.style.display = "none";
      _0x5a85ee.style.display = "flex";
      _0x6e27ff.checked = true;
      _0x6e27ff.dispatchEvent(new Event("change"));
    }
  };
  let _0x4801c6 = document.getElementById("miInsert");
  let _0x3b66d7 = document.getElementById("miClear");
  let _0x56ded7 = document.getElementById("miDelete");
  let _0x3df0e2 = document.getElementById("moveUp");
  let _0x1c34f7 = document.getElementById("moveDown");
  _0x4801c6.onclick = function () {
    insertMacroStep();
  };
  _0x3b66d7.onclick = function () {
    clearMacroItems();
  };
  _0x56ded7.onclick = function () {
    deleteMacroStep();
  };
  _0x3df0e2.onclick = function () {
    moveUpMacroStep();
  };
  _0x1c34f7.onclick = function () {
    moveDownMacroStep();
  };
  let _0x4610e2 = document.getElementById("macroInfoDelay");
  let _0x6e27ff = document.getElementById("macroMouseLeft");
  let _0x2d9881 = document.getElementById("macroMouseMiddle");
  let _0x224c44 = document.getElementById("macroMouseRight");
  _0x4610e2.oninput = function (_0x50d1e5) {
    delayInput(_0x50d1e5);
    updateStepDelay(parseInt(_0x4610e2.value));
  };
  _0x6e27ff.onchange = function () {
    if (_0x6e27ff.checked) {
      updateStepKey(findFixedKey("MouseLeft"));
    }
  };
  _0x2d9881.onchange = function () {
    if (_0x2d9881.checked) {
      updateStepKey(findFixedKey("MouseMiddle"));
    }
  };
  _0x224c44.onchange = function () {
    if (_0x224c44.checked) {
      updateStepKey(findFixedKey("MouseRight"));
    }
  };
  await initFixedKeys();
  await readConfig();
});
const sliderRadius = 8;
function iniColorPicker() {
  let _0x344631 = document.getElementById("colorPicker");
  _0x344631.width = 175 - sliderRadius * 4 - 5;
  _0x344631.height = 175 - sliderRadius * 4 - 5;
  let _0x1ab839 = _0x344631.getContext("2d");
  let _0x5cdd6d = _0x1ab839.createConicGradient(4.7, _0x344631.width / 2, _0x344631.height / 2);
  _0x5cdd6d.addColorStop(0, "#f00");
  _0x5cdd6d.addColorStop(0.16666, "#ff0");
  _0x5cdd6d.addColorStop(0.33333, "#0f0");
  _0x5cdd6d.addColorStop(0.5, "#0ff");
  _0x5cdd6d.addColorStop(0.66666, "#00f");
  _0x5cdd6d.addColorStop(0.83333, "#f0f");
  _0x5cdd6d.addColorStop(1, "#f00");
  _0x1ab839.fillStyle = _0x5cdd6d;
  _0x1ab839.fillRect(0, 0, _0x344631.width, _0x344631.height);
  _0x5cdd6d = _0x1ab839.createRadialGradient(_0x344631.width / 2, _0x344631.height / 2, 0, _0x344631.width / 2, _0x344631.height / 2, _0x344631.height * 0.56);
  _0x5cdd6d.addColorStop(0, "#ffffff");
  _0x5cdd6d.addColorStop(0.05, "#ffffff");
  _0x5cdd6d.addColorStop(0.85, "#ffffff00");
  _0x5cdd6d.addColorStop(1, "#ffffff00");
  _0x1ab839.fillStyle = _0x5cdd6d;
  _0x1ab839.fillRect(0, 0, _0x344631.width, _0x344631.height);
  _0x344631.onclick = async function (_0x1f877a) {
    let _0x38938f = _0x344631.getBoundingClientRect();
    let _0x55b9a9 = _0x1f877a.clientX - _0x38938f.left;
    let _0x40fd9b = _0x1f877a.clientY - _0x38938f.top;
    let _0x507d98 = _0x1ab839.getImageData(_0x55b9a9, _0x40fd9b, 1, 1).data;
    let _0x3c11fb = _0x507d98[0];
    let _0x210dbd = _0x507d98[1];
    let _0x3b212c = _0x507d98[2];
    setRgb(_0x3c11fb, _0x210dbd, _0x3b212c);
    await setCustomRgb(_0x3c11fb, _0x210dbd, _0x3b212c);
    await setDeviceLight();
    curR = _0x3c11fb;
    curG = _0x210dbd;
    curB = _0x3b212c;
    initColorSlider();
  };
}
function initColorDeep() {
  let _0x41ea24 = document.getElementById("colorDeep");
  _0x41ea24.width = 175 - sliderRadius;
  _0x41ea24.height = 175 - sliderRadius;
  let _0xc71fc8 = _0x41ea24.getContext("2d");
  const _0x44faf3 = _0x41ea24.width / 2 - sliderRadius;
  const _0x5934bc = _0x41ea24.width / 2;
  const _0x2ee0b3 = _0x41ea24.height / 2;
  let _0x6303fd = _0xc71fc8.createConicGradient(-Math.PI / 2, _0x5934bc, _0x2ee0b3);
  _0x6303fd.addColorStop(0, "#000");
  _0x6303fd.addColorStop(1, "#fff");
  _0xc71fc8.fillStyle = _0x6303fd;
  _0xc71fc8.fillRect(0, 0, _0x41ea24.width, _0x41ea24.height);
  _0xc71fc8.beginPath();
  _0xc71fc8.arc(_0x5934bc, _0x2ee0b3, _0x44faf3, 0, Math.PI * 2);
  _0xc71fc8.closePath();
  _0xc71fc8.fillStyle = theme === "light" ? "#fff" : "#333";
  _0xc71fc8.fill();
}
function initColorSlider() {
  let _0x223bcd = document.getElementById("colorSlider");
  _0x223bcd.width = 175;
  _0x223bcd.height = 175;
  let _0x367ce0 = _0x223bcd.getContext("2d");
  const _0x5d9957 = _0x223bcd.width / 2 - sliderRadius;
  const _0x335177 = _0x223bcd.width / 2;
  const _0x4f0d75 = _0x223bcd.height / 2;
  let _0x2fdedf = false;
  function _0x4d016b(_0x16a7e4, _0x2ac10e) {
    console.log("angle:" + _0x16a7e4);
    let _0x2e46d1 = 360 / Math.PI * (_0x16a7e4 / 2 + Math.PI / 2);
    _0x2e46d1 -= 90;
    if (_0x2e46d1 < 0) {
      _0x2e46d1 += 360;
    }
    console.log(_0x2e46d1);
    if (_0x2ac10e) {
      setEditValue(_0x2e46d1);
    }
    _0x367ce0.clearRect(0, 0, _0x223bcd.width, _0x223bcd.height);
    _0x367ce0.beginPath();
    _0x367ce0.arc(_0x335177 + Math.cos(_0x16a7e4) * _0x5d9957, _0x4f0d75 + Math.sin(_0x16a7e4) * _0x5d9957, sliderRadius, 0, Math.PI * 2);
    _0x367ce0.fillStyle = "#f00";
    _0x367ce0.fill();
  }
  _0x4d016b(-Math.PI / 2 - 0.01, false);
  _0x223bcd.onmousedown = function (_0x113eb1) {
    let _0x5af6c9 = _0x223bcd.getBoundingClientRect();
    let _0x135588 = _0x113eb1.clientX - _0x5af6c9.left - _0x335177;
    let _0x21b674 = _0x113eb1.clientY - _0x5af6c9.top - _0x4f0d75;
    let _0x43af58 = Math.atan2(_0x21b674, _0x135588);
    _0x2fdedf = true;
    _0x4d016b(_0x43af58, true);
  };
  window.onmousemove = function (_0xe9194a) {
    if (_0x2fdedf) {
      let _0x346d3c = _0x223bcd.getBoundingClientRect();
      let _0x2f5b51 = _0xe9194a.clientX - _0x346d3c.left - _0x335177;
      let _0x52ccd4 = _0xe9194a.clientY - _0x346d3c.top - _0x4f0d75;
      _0x4d016b(Math.atan2(_0x52ccd4, _0x2f5b51), true);
    }
  };
  window.onmouseup = async function () {
    if (_0x2fdedf) {
      _0x2fdedf = false;
      await setDeviceLight();
    }
  };
}
function isValidInteger(_0x55ddb9) {
  return /^(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]\d|[1-9]|0)$/.test(_0x55ddb9);
}
function handleInput(_0x2b2d2c) {
  let _0x38f07f = _0x2b2d2c.target;
  let _0x425a68 = parseInt(_0x38f07f.value).toString();
  if (isValidInteger(_0x425a68)) {
    _0x38f07f.validity.lastValidValue = _0x38f07f.value;
    _0x38f07f.value = _0x425a68;
  } else if (_0x38f07f.value === "") {
    _0x38f07f.value = 0;
  } else {
    _0x38f07f.value = _0x38f07f.validity.lastValidValue;
  }
}
function isValidDelay(_0x932e) {
  return /^(?:6553[0-5]|655[0-2]\d|65[0-4]\d\d|6[0-4]\d{3}|[1-5]\d{4}|[1-9]\d{0,3}|0)$/.test(_0x932e);
}
function delayInput(_0x5530ae) {
  let _0x570e4a = _0x5530ae.target;
  let _0x24d767 = parseInt(_0x570e4a.value).toString();
  if (isValidDelay(_0x24d767)) {
    _0x570e4a.validity.lastValidValue = _0x24d767;
    _0x570e4a.value = _0x24d767;
  } else if (_0x570e4a.value === "") {
    _0x570e4a.value = 0;
  } else {
    _0x570e4a.value = _0x570e4a.validity.lastValidValue;
  }
}
function strToColor(_0x44ac93) {
  let _0x5bf894 = 0;
  let _0x49b577 = 0;
  let _0x1dfce2 = 0;
  let _0x531ea7 = 0;
  if (_0x44ac93.startsWith("rgb") && _0x44ac93.indexOf("(") >= 0) {
    let _0x1da3fb = _0x44ac93.split("(")[1].split(")")[0].split(",");
    _0x5bf894 = parseInt(_0x1da3fb[0]);
    _0x49b577 = parseInt(_0x1da3fb[1]);
    _0x1dfce2 = parseInt(_0x1da3fb[2]);
    if (_0x1da3fb.length > 3) {
      _0x531ea7 = parseInt(_0x1da3fb[3]);
    }
  }
  return new Color(_0x5bf894, _0x49b577, _0x1dfce2, _0x531ea7);
}
async function setRgb(_0x323f37, _0x488d40, _0x33fe02) {
  let _0x712ed2 = document.getElementById("colorR");
  let _0x4826b6 = document.getElementById("colorG");
  let _0x13f8d1 = document.getElementById("colorB");
  _0x712ed2.value = _0x323f37.toString();
  _0x4826b6.value = _0x488d40.toString();
  _0x13f8d1.value = _0x33fe02.toString();
  _0x712ed2.validity.lastValidValue = _0x712ed2.value;
  _0x4826b6.validity.lastValidValue = _0x4826b6.value;
  _0x13f8d1.validity.lastValidValue = _0x13f8d1.value;
  let _0x5e7860 = "rgba(" + _0x323f37 + "," + _0x488d40 + "," + _0x33fe02 + ")";
  console.log("颜色值:", _0x5e7860);
  if (document.getElementById("colorForeground").checked) {
    document.getElementById("colorForegroundLabel").style.backgroundColor = _0x5e7860;
  }
  if (document.getElementById("colorBackground").checked) {
    document.getElementById("colorBackgroundLabel").style.backgroundColor = _0x5e7860;
  }
}
async function setCustomRgb(_0x567996, _0x2167e5, _0x34e82e) {
  if (!isReadInfo && curDevice !== undefined && curDevice !== null && isCustomLight && curDevice.light.mode === 10) {
    setKeyColor(_0x567996, _0x2167e5, _0x34e82e);
    await setCustomLight(curDevice.light, lightCustom1.checked ? 0 : 1);
  }
}
function setEditValue(_0x3ca531) {
  let _0x1dbfbb = Math.round(_0x3ca531 / 360 * curR);
  let _0x579ca = Math.round(_0x3ca531 / 360 * curG);
  let _0x22dc24 = Math.round(_0x3ca531 / 360 * curB);
  console.log(_0x1dbfbb, _0x579ca, _0x22dc24);
  setRgb(_0x1dbfbb, _0x579ca, _0x22dc24);
  setCustomRgb(_0x1dbfbb, _0x579ca, _0x22dc24);
}
function setMagneticSwitchValue(_0x400b67) {
  const _0x1b22ad = document.getElementById("switchThumb");
  if (curDevice) {
    const _0x52d354 = (_0x400b67 - curDevice.minTriggerTravel) * (30 / (curDevice.maxTriggerTravel - curDevice.minTriggerTravel));
    if (_0x1b22ad) {
      _0x1b22ad.style.top = _0x52d354 + "px";
    }
  }
}
function initTriggerSlider(_0x2e2777, _0x48486a, _0x29ff96) {
  const _0x489f96 = document.getElementById("triggerAll");
  _0x489f96.max = _0x2e2777;
  _0x489f96.setAttribute("max", _0x2e2777);
  _0x489f96.setAttribute("min", curDevice.minTriggerTravel);
  _0x489f96.setAttribute("step", _0x48486a);
  _0x489f96.setAttribute("value", _0x29ff96 > _0x2e2777 ? _0x2e2777 : _0x29ff96);
  setMagneticSwitchValue(_0x29ff96 > _0x2e2777 ? _0x2e2777 : _0x29ff96);
}
function refreshTriggerSlider(_0x16e7cd) {
  let _0xc4f52d = isMoreSwitch ? 0 : curDevice.maxTriggerTravel;
  if (isMoreSwitch) {
    checkedKeys.forEach(_0x433067 => {
      let _0x1762d1 = switchDefault.find(_0x1dd8cc => _0x1dd8cc.index === _0x433067.switch);
      if (_0x1762d1 != null) {
        let _0x2feceb = Math.floor(_0x1762d1.travel / curDevice.triggerUnit);
        if (_0xc4f52d === 0) {
          _0xc4f52d = _0x2feceb;
        }
        if (_0x2feceb < _0xc4f52d) {
          _0xc4f52d = _0x2feceb;
        }
      }
    });
  }
  initTriggerSlider(checkedKeys.length > 0 ? _0xc4f52d : curDevice.maxTriggerTravel, curDevice.triggerUnit, _0x16e7cd);
}
function getRemainder(_0x40ef6b, _0x122062) {
  let _0x349b31;
  let _0x26c43b;
  let _0x4ea084;
  try {
    _0x349b31 = _0x40ef6b.toString().split(".")[1].length;
  } catch (_0x9d4116) {
    _0x349b31 = 0;
  }
  try {
    _0x26c43b = _0x122062.toString().split(".")[1].length;
  } catch (_0x52ab11) {
    _0x26c43b = 0;
  }
  _0x4ea084 = Math.pow(10, Math.max(_0x349b31, _0x26c43b));
  return accMul(_0x40ef6b, _0x4ea084) % accMul(_0x122062, _0x4ea084) / _0x4ea084;
}
function accMul(_0x423793, _0x33c8a7) {
  let _0x14c0f4 = 0;
  let _0x5745a3 = _0x423793.toString();
  let _0x365ff4 = _0x33c8a7.toString();
  try {
    _0x14c0f4 += _0x5745a3.split(".")[1].length;
  } catch (_0x2a2774) {}
  try {
    _0x14c0f4 += _0x365ff4.split(".")[1].length;
  } catch (_0x450a36) {}
  return Number(_0x5745a3.replace(".", "")) * Number(_0x365ff4.replace(".", "")) / Math.pow(10, _0x14c0f4);
}
function accDiv(_0x2d088e, _0x20c3eb) {
  let _0x4eef13 = 0;
  let _0x47391c = 0;
  let _0x32c3a9;
  let _0x5a332f;
  try {
    _0x4eef13 = _0x2d088e.toString().split(".")[1].length;
  } catch (_0x3eb836) {}
  try {
    _0x47391c = _0x20c3eb.toString().split(".")[1].length;
  } catch (_0x2c2932) {}
  with (Math) {
    _0x32c3a9 = Number(_0x2d088e.toString().replace(".", ""));
    _0x5a332f = Number(_0x20c3eb.toString().replace(".", ""));
    return _0x32c3a9 / _0x5a332f * pow(10, _0x47391c - _0x4eef13);
  }
}
function countDecimals(_0x4c764e) {
  const _0x40e50a = String(_0x4c764e).match(/\.(\d+)/);
  if (_0x40e50a) {
    return _0x40e50a[1].length;
  } else {
    return 0;
  }
}
function sleep(_0x630457) {
  return new Promise(function (_0x5d4d21) {
    setTimeout(_0x5d4d21, _0x630457);
  });
}
function initLogo() {
  if (curDevice !== undefined) {
    const _0x10b219 = document.getElementById("logoDiv");
    const _0x18357b = document.getElementById("logo");
    const _0x341fe7 = document.getElementById("logoTitle");
    if (curDevice.logoType === 1) {
      _0x10b219.classList.remove("*");
      _0x10b219.classList.add("logoDiv1");
      _0x18357b.classList.remove("*");
      _0x18357b.classList.add("logo1");
      _0x18357b.src = curDevice.company === "" ? "image/logo.png" : "image/logo_" + curDevice.company + ".png";
      _0x341fe7.innerText = curDevice.title === "" ? "iLLumiPC" : curDevice.title;
      _0x341fe7.classList.remove("*");
      _0x341fe7.classList.add("logoTitle1");
    } else if (curDevice.logoType === 2) {
      _0x10b219.classList.remove("*");
      _0x10b219.classList.add("logoDiv2");
      _0x18357b.classList.remove("*");
      _0x18357b.classList.add("logo2");
      if (curDevice.company === "fuLing") {
        _0x18357b.style.width = "180px";
        _0x18357b.style.height = "18px";
      }
      _0x18357b.src = curDevice.company === "" ? "image/logo.png" : "image/logo_" + curDevice.company + ".png";
      _0x341fe7.classList.remove("*");
      _0x341fe7.classList.add("logoTitle2");
    } else if (curDevice.logoType === 3) {
      _0x10b219.classList.remove("*");
      _0x10b219.classList.add("logoDiv3");
      _0x18357b.classList.remove("*");
      _0x18357b.classList.add("logo3");
      _0x18357b.src = curDevice.company === "" ? "image/logo.png" : "image/logo_" + curDevice.company + ".png";
      _0x341fe7.innerText = curDevice.title === "" ? "iLLumiPC" : curDevice.title;
      _0x341fe7.classList.remove("*");
      _0x341fe7.classList.add("logoTitle3");
    } else {
      _0x10b219.classList.remove("*");
      _0x10b219.classList.add("logoDiv");
      _0x18357b.classList.remove("*");
      _0x18357b.classList.add("logo");
      _0x18357b.src = "image/logo.png";
      _0x341fe7.innerText = "iLLumiPC";
      _0x341fe7.classList.remove("*");
      _0x341fe7.classList.add("logoTitle");
    }
  }
}
function replacer(_0x4c8641, _0x3f291d) {
  if (_0x3f291d instanceof Map) {
    return Array.from(_0x3f291d.entries());
  } else {
    return _0x3f291d;
  }
}
function jsonToProfileSet(_0x432403) {
  if (_0x432403 == null) {
    return null;
  }
  let _0x105ada = new ProfileSet();
  const _0x53b7d3 = JSON.parse(_0x432403);
  if (_0x53b7d3 !== null) {
    let _0x7450e8 = [];
    _0x53b7d3.profiles.forEach(_0x5e46e3 => {
      let _0xadf6a0 = new Profile();
      _0xadf6a0.index = _0x5e46e3.index;
      _0xadf6a0.name = _0x5e46e3.name;
      _0xadf6a0.colorArray2[2] = new Color(0, 255, 0);
      _0xadf6a0.colorArray4[4] = new Color(0, 255, 0);
      _0xadf6a0.colorArray1 = objToColorArray(_0x5e46e3.colorArray1, 1);
      _0xadf6a0.colorArray2 = objToColorArray(_0x5e46e3.colorArray2, 2);
      _0xadf6a0.colorArray3 = objToColorArray(_0x5e46e3.colorArray3, 3);
      _0xadf6a0.colorArray4 = objToColorArray(_0x5e46e3.colorArray4, 4);
      _0xadf6a0.light = objToLight(_0x5e46e3.light);
      _0xadf6a0.sideLight = objToLight(_0x5e46e3.sideLight);
      _0xadf6a0.defKeys = objToKeys(_0x5e46e3.defKeys);
      _0xadf6a0.fnKeys = objToKeys(_0x5e46e3.fnKeys);
      _0xadf6a0.recMacros = objToRecMacros(_0x5e46e3.recMacros);
      _0xadf6a0.macros = objToMacros(_0x5e46e3.macros);
      _0xadf6a0.advKeys = objToAdvKeys(_0x5e46e3.advKeys);
      _0xadf6a0.triggers = objToTrigger(_0x5e46e3.triggers);
      _0xadf6a0.prcsPower = _0x5e46e3.prcsPower;
      _0xadf6a0.prcses = objToPrcses(_0x5e46e3.prcses);
      _0xadf6a0.other = _0x5e46e3.other === undefined || _0x5e46e3.other === null ? 1 : _0x5e46e3.other;
      _0x7450e8.push(_0xadf6a0);
    });
    _0x105ada.curIndex = _0x53b7d3.curIndex;
    _0x105ada.profiles = _0x7450e8;
  }
  return _0x105ada;
}
function objToAdvKeyKeys(_0x214bd8) {
  let _0x4a0880 = [];
  if (_0x214bd8 != null) {
    _0x214bd8.forEach(_0x5d706e => {
      let _0xc6f3a6 = objToKey(_0x5d706e);
      _0x4a0880.push(_0xc6f3a6);
    });
  }
  return _0x4a0880;
}
function objToAdvKeys(_0x5d2525) {
  let _0x4ffa48 = [];
  if (_0x5d2525 != null) {
    _0x5d2525.forEach(_0x30be93 => {
      let _0x4472b0 = new AdvancedKey();
      _0x4472b0.index = _0x30be93.index;
      _0x4472b0.type = _0x30be93.type;
      _0x4472b0.duration = _0x30be93.duration;
      _0x4472b0.route1 = _0x30be93.route1;
      _0x4472b0.route2 = _0x30be93.route2;
      _0x4472b0.route3 = _0x30be93.route3;
      _0x4472b0.route4 = _0x30be93.route4;
      _0x4472b0.keys = objToAdvKeyKeys(_0x30be93.keys);
      _0x4472b0.steps = _0x30be93.steps;
      _0x4ffa48.push(_0x4472b0);
    });
  }
  return _0x4ffa48;
}
function objToSteps(_0x911801) {
  let _0x5b7b37 = [];
  if (_0x911801 != null) {
    _0x911801.forEach(_0xa7e26d => {
      let _0x6f42cc = new Step();
      _0x6f42cc.tag = _0xa7e26d.tag;
      _0x6f42cc.type = _0xa7e26d.type;
      _0x6f42cc.state = _0xa7e26d.state;
      _0x6f42cc.delay = _0xa7e26d.delay;
      _0x6f42cc.key = objToKey(_0xa7e26d.key);
      _0x5b7b37.push(_0x6f42cc);
    });
  }
  return _0x5b7b37;
}
function objToRecMacros(_0x36b846) {
  let _0x338f3b = new Map();
  if (_0x36b846 != null) {
    _0x36b846.forEach(_0x2cf57e => {
      if (_0x2cf57e.length >= 2) {
        let _0x562645 = _0x2cf57e[0];
        let _0x1ff86c = _0x2cf57e[1];
        if (_0x562645 !== null && _0x1ff86c !== null) {
          let _0x36d414 = new MacroKey();
          _0x36d414.index = _0x1ff86c.index;
          _0x36d414.type = _0x1ff86c.type;
          _0x36d414.count = _0x1ff86c.count;
          _0x338f3b.set(_0x562645, _0x36d414);
        }
      }
    });
  }
  return _0x338f3b;
}
function objToMacros(_0x4b6b00) {
  let _0x5322ca = [];
  if (_0x4b6b00 != null) {
    _0x4b6b00.forEach(_0x44b36f => {
      let _0x5f32df = new Macro();
      _0x5f32df.index = _0x44b36f.index;
      _0x5f32df.name = _0x44b36f.name;
      _0x5f32df.steps = objToSteps(_0x44b36f.steps);
      _0x5322ca.push(_0x5f32df);
    });
  }
  return _0x5322ca;
}
function objToKey(_0x41d312) {
  let _0x4fb828 = new Key();
  if (_0x41d312 != null) {
    _0x4fb828.index = _0x41d312.index;
    _0x4fb828.name = _0x41d312.name;
    _0x4fb828.code = _0x41d312.code;
    _0x4fb828.code1 = _0x41d312.code1;
    _0x4fb828.hidCode = _0x41d312.hidCode;
    _0x4fb828.code3 = _0x41d312.code3;
    _0x4fb828.code4 = _0x41d312.code4;
    _0x4fb828.x = _0x41d312.x;
    _0x4fb828.y = _0x41d312.y;
  }
  return _0x4fb828;
}
function objToPrcses(_0x3465db) {
  let _0x49a3f8 = [];
  if (_0x3465db != null) {
    _0x3465db.forEach(_0xcb4ddd => {
      let _0x541d4d = new Prcs();
      _0x541d4d.index = _0xcb4ddd.index;
      _0x541d4d.name = _0xcb4ddd.name;
      _0x541d4d.model = _0xcb4ddd.model;
      _0x541d4d.key1 = objToKey(_0xcb4ddd.key1);
      _0x541d4d.key2 = objToKey(_0xcb4ddd.key2);
      _0x49a3f8.push(_0x541d4d);
    });
  }
  return _0x49a3f8;
}
function objToTrigger(_0x248255) {
  let _0x23d4c4 = new Map();
  if (_0x248255 != null) {
    _0x248255.forEach(_0x1e7978 => {
      if (_0x1e7978.length >= 2) {
        let _0x4d81fa = _0x1e7978[0];
        let _0x1bc1b7 = _0x1e7978[1];
        if (_0x4d81fa !== null && _0x1bc1b7 !== null) {
          let _0x50708b = new Trigger();
          _0x50708b.mode = _0x1bc1b7.mode;
          _0x50708b.travel = _0x1bc1b7.travel;
          _0x50708b.interval1 = _0x1bc1b7.interval1;
          _0x50708b.interval2 = _0x1bc1b7.interval2;
          _0x23d4c4.set(_0x4d81fa, _0x50708b);
        }
      }
    });
  }
  return _0x23d4c4;
}
function objToColorArray(_0x2d32bd, _0x363cdf) {
  let _0x49b17b = new Array(20).fill(new Color(255, 0, 0));
  if (_0x363cdf === 2 || _0x363cdf === 4) {
    _0x49b17b = new Array(20).fill(new Color(0, 0, 0));
  }
  if (_0x2d32bd) {
    _0x2d32bd.forEach((_0x30e81d, _0x2ee468) => {
      let _0x39cf77 = new Color(_0x30e81d.r, _0x30e81d.g, _0x30e81d.b);
      if (_0x2ee468 < _0x49b17b.length) {
        _0x49b17b[_0x2ee468] = _0x39cf77;
      }
    });
  }
  return _0x49b17b;
}
function objToLight(_0x36083a) {
  let _0x230494 = new Light();
  if (_0x36083a != null) {
    _0x230494.power = _0x36083a.power;
    _0x230494.mode = _0x36083a.mode;
    _0x230494.brightness = _0x36083a.brightness;
    _0x230494.speed = _0x36083a.speed;
    _0x230494.direction = _0x36083a.direction;
    _0x230494.fullColor = _0x36083a.fullColor;
    _0x230494.foregroundColor = new Color(_0x36083a.foregroundColor.r, _0x36083a.foregroundColor.g, _0x36083a.foregroundColor.b);
    _0x230494.backgroundColor = new Color(_0x36083a.backgroundColor.r, _0x36083a.backgroundColor.g, _0x36083a.backgroundColor.b);
  }
  return _0x230494;
}
function objToKeys(_0x224217) {
  let _0x5a7e53 = new Map();
  if (_0x224217 != null) {
    _0x224217.forEach(_0x47b2d4 => {
      if (_0x47b2d4.length >= 2) {
        let _0x476222 = _0x47b2d4[0];
        let _0x3cfed3 = _0x47b2d4[1];
        if (_0x476222 !== null && _0x3cfed3 !== null) {
          let _0x498dff = objToKey(_0x3cfed3);
          _0x5a7e53.set(_0x476222, _0x498dff);
        }
      }
    });
  }
  return _0x5a7e53;
}
function setViewport() {
  const _0x185b63 = window.innerWidth;
  const _0xf97b43 = window.innerHeight;
  const _0x52d60a = _0x185b63 / Math.max(1920, _0x185b63);
  const _0x572441 = _0xf97b43 / Math.max(1080, _0xf97b43);
  scale = Math.min(_0x52d60a, _0x572441);
  const _0x4d1a94 = document.getElementById("contianer");
  _0x4d1a94.style.transform = "scale(" + scale + ")";
  _0x4d1a94.style.width = _0x185b63 / scale + "px";
  _0x4d1a94.style.height = _0xf97b43 / scale + "px";
  document.body.style.height = _0xf97b43 + "px";
  document.body.style.overflow = "hidden";
}
let oldHeight = 0;
let isWinChanged = false;
let refreshCount = 0;
let timer;
let hbTimer;
async function initHidDevice() {
  if ("navigator" in window && "hid" in navigator) {
    let _0x445f01;
    console.log("WebHID is supported!");
    try {
      _0x445f01 = await navigator.hid.requestDevice({
        filters: filters
      });
    } catch (_0x38ee09) {
      console.log(_0x38ee09.message);
    }
    if (curDevice !== undefined && curDevice !== null) {
      return;
    }
    if (_0x445f01 !== undefined && _0x445f01.length > 0) {
      await deviceInitialization(_0x445f01);
      setTimeout(checkFirmwareVersion, 5000);
    } else {
      document.getElementById("startDiv").style.display = "flex";
      document.getElementById("mainDiv").style.display = "none";
    }
  } else {
    console.log("WebUSB is not supported in this browser.");
    window.alert("WebUSB is not supported in this browser.");
  }
}
async function deviceInitialization(_0x105315) {
  await initDevice(_0x105315);
  if (curDevice !== undefined && hidDevice.opened) {
    startStep.style.width = "calc(50% + 120px)";
    await sleep(600);
    startStep.style.width = "100%";
    await sleep(300);
    firmwareInfo.innerText = getI18n("firmwareCurrent") + "V" + curDevice.version + "，" + getI18n("firmwareLast");
    btnUpdate.setAttribute("version", "");
    btnUpdate.value = "";
    btnUpdate.innerText = getI18n("checkUpdate");
    checkFirmwareVersion(true);
    let _0x316092 = localStorage.getItem(curDevice.product);
    if (_0x316092 != null) {
      profileSet = jsonToProfileSet(_0x316092);
      if (profileSet !== null && profileSet.profiles.length === 5) {
        curProfile = profileSet.profiles[profileSet.curIndex];
        document.documentElement.style.setProperty("--translateY", curProfile.index * 100 + "%");
        if (profileSet.curIndex === 0) {
          ProfileDef.checked = true;
        }
        if (profileSet.curIndex === 1) {
          Profile1.checked = true;
        }
        if (profileSet.curIndex === 2) {
          Profile2.checked = true;
        }
        if (profileSet.curIndex === 3) {
          Profile3.checked = true;
        }
        if (profileSet.curIndex === 4) {
          Profile4.checked = true;
        }
      }
    }
    if (profileSet === undefined || profileSet === null) {
      profileSet = new ProfileSet();
      profileSet.curIndex = 0;
      for (let _0x1a5d3a = 0; _0x1a5d3a < 5; _0x1a5d3a++) {
        let _0x30207d = new Profile();
        _0x30207d.colorArray2[2] = new Color(0, 255, 0);
        _0x30207d.colorArray4[4] = new Color(0, 255, 0);
        _0x30207d.index = _0x1a5d3a;
        _0x30207d.name = "";
        if (_0x1a5d3a === 0) {
          curProfile = _0x30207d;
        }
        _0x30207d.light.power = _0x30207d.sideLight.power = 0;
        _0x30207d.light.mode = _0x30207d.sideLight.mode = 2;
        _0x30207d.light.brightness = _0x30207d.sideLight.brightness = 4;
        _0x30207d.light.speed = _0x30207d.sideLight.speed = 3;
        _0x30207d.light.direction = _0x30207d.sideLight.direction = 0;
        _0x30207d.light.fullColor = _0x30207d.sideLight.fullColor = 1;
        _0x30207d.light.foregroundColor.r = _0x30207d.sideLight.foregroundColor.r = 255;
        _0x30207d.light.foregroundColor.g = _0x30207d.sideLight.foregroundColor.g = 0;
        _0x30207d.light.foregroundColor.b = _0x30207d.sideLight.foregroundColor.b = 0;
        _0x30207d.light.backgroundColor.r = _0x30207d.sideLight.backgroundColor.r = 0;
        _0x30207d.light.backgroundColor.g = _0x30207d.sideLight.backgroundColor.g = 0;
        _0x30207d.light.backgroundColor.b = _0x30207d.sideLight.backgroundColor.b = 0;
        profileSet.profiles[_0x1a5d3a] = _0x30207d;
      }
    }
    oldHeight = 0;
    if (curDevice.pid === 50032 || curDevice.pid === 50033) {
      battery = document.getElementById("batteryContainer");
      battery.style.display = "flex";
      document.getElementById("batteryText").innerHTML = "";
    } else {
      battery = null;
      document.getElementById("batteryContainer")?.remove();
    }
    const _0x49a002 = document.querySelector("[for=keyManu4]");
    const _0x577d69 = document.querySelector("[for=triggerManu1]");
    const _0x217911 = document.querySelector("[for=triggerManu2]");
    const _0x28aadd = document.querySelector("[for=triggerManu3]");
    const _0x54913b = document.querySelector("[for=triggerManu5]");
    if (curDevice.pid === 50025 && curDevice.vid === 11836) {
      if (_0x49a002) {
        _0x49a002.remove();
      }
      if (_0x577d69) {
        _0x577d69.style.display = "none";
      }
      if (_0x217911) {
        _0x217911.style.display = "none";
      }
      if (_0x28aadd) {
        _0x28aadd.style.display = "none";
      }
      if (_0x54913b) {
        _0x54913b.style.display = "none";
      }
    }
    initLogo();
    await readKeys(curDevice.product);
    readHidData();
    isInitOther = true;
    await initInfo();
    await initFnKeyState();
    await initMacroValue();
    if (curDevice.pid !== 49989) {
      await initAdvancedKeys();
      if (isPrcs) {
        await initPrcsPower();
        await initPrcsData();
      }
    }
    await initKeyValue("default");
    await initKeyValue("fn");
    console.log(recKeys, fnKeys);
    if (curDevice.hasLight) {
      await readLightList();
      await readSideLightList();
      await initLightValue();
      await initSideLightValue();
      if (isCustomLight) {
        await initCustomNumber();
        await initCustomLightValue(0);
        await initCustomLightValue(1);
      }
      document.querySelector("[for=menu2]").style.display = "flex";
    } else {
      document.querySelector("[for=menu2]").style.display = "none";
    }
    if (curDevice.pid !== 49989) {
      await readMaxTriggerTravel();
      await readTriggerData();
      if (isPollRate) {
        await readPollRate();
      }
    }
    document.querySelector("[for=triggerManu2]").style.display = isMoreSwitch ? "flex" : "none";
    if (curDevice.pid !== 49989) {
      if (isMoreSwitch) {
        await initSwitchList();
        await initKeySwitch();
        if (switchList.length > 0) {
          refreshSwitchList();
        }
      }
      if (isDeadBand) {
        await readDeadBand();
      }
    }
    if (curDevice.pid === 50032 || curDevice.pid === 50033) {
      if (triMode === 1) {
        document.querySelector("label[for=\"pollRate4\"]").style.display = "none";
      }
      document.getElementById("performance4").style.display = "flex";
      getSleepTimer();
      const _0x303d8d = document.getElementById("sleepApply");
      _0x303d8d.onclick = () => {
        _0x303d8d.disabled = true;
        let _0x208059 = document.getElementById("lightSleep").value;
        let _0x5f2802 = document.getElementById("keyboardSleep").value;
        let _0x52a2b7 = true;
        if (_0x208059 < 5 || _0x208059 > Number(_0x5f2802) * 60) {
          showAlert(_0x208059 < 5 ? getI18n("sleepSetTip1") + 5 : getI18n("sleepSetTip2"));
          _0x52a2b7 = false;
        }
        if (_0x5f2802 < 5 || Number(_0x5f2802) > 60000) {
          showAlert(_0x5f2802 < 5 ? getI18n("sleepSetTip3") + 5 : getI18n("sleepSetTip4") + 60000);
          _0x52a2b7 = false;
        }
        if (_0x52a2b7) {
          setSleepTimer(Number(_0x208059), Number(_0x5f2802) * 60);
        }
        setTimeout(() => {
          _0x303d8d.disabled = false;
          getSleepTimer();
        }, 200);
      };
    }
    if (i18n === "jp" || i18n === "de") {
      document.getElementById("btnReset").style.width = "138px";
      document.querySelector("[for=ProfileDef]").innerText = "" + getI18n("default") + getI18n("profile");
    } else {
      document.getElementById("btnReset").style.width = "88px";
      document.querySelector("[for=ProfileDef]").innerText = getI18n("profile") + " " + getI18n("default");
    }
    const _0x746fad = document.getElementById("lightModels");
    document.getElementById("keymapTableView");
    document.getElementById("selectAllView");
    if (i18n !== "tr" && i18n !== "pt-br" && i18n !== "de" && i18n !== "es") {
      _0x746fad.querySelectorAll("label").forEach(_0x2f30f9 => {
        _0x2f30f9.parentNode.style.order = Number(_0x2f30f9.parentNode.getAttribute("order")) + Number(_0x2f30f9.parentNode.getAttribute("index"));
      });
    }
    if (i18n === "de") {
      document.querySelector("[for=lightManu1]").style.width = "200px";
      document.querySelector("[for=lightManu2]").style.width = "200px";
      document.getElementById("macroAlert").style.width = "1000px";
    } else {
      document.getElementById("macroAlert").style.width = "880px";
    }
    if (profileSet !== undefined && profileSet !== null && profileSet.profiles.length >= 5) {
      if (profileSet.profiles[1].name === "") {
        document.querySelector("[for=Profile1]").innerText = getI18n("profile") + " 1";
      } else {
        document.querySelector("[for=Profile1]").innerText = profileSet.profiles[1].name;
      }
      if (profileSet.profiles[2].name === "") {
        document.querySelector("[for=Profile2]").innerText = getI18n("profile") + " 2";
      } else {
        document.querySelector("[for=Profile2]").innerText = profileSet.profiles[2].name;
      }
      if (profileSet.profiles[3].name === "") {
        document.querySelector("[for=Profile3]").innerText = getI18n("profile") + " 3";
      } else {
        document.querySelector("[for=Profile3]").innerText = profileSet.profiles[3].name;
      }
      if (profileSet.profiles[4].name === "") {
        document.querySelector("[for=Profile4]").innerText = getI18n("profile") + " 4";
      } else {
        document.querySelector("[for=Profile4]").innerText = profileSet.profiles[4].name;
      }
    } else {
      document.querySelector("[for=Profile1]").innerText = getI18n("profile") + " 1";
      document.querySelector("[for=Profile2]").innerText = getI18n("profile") + " 2";
      document.querySelector("[for=Profile3]").innerText = getI18n("profile") + " 3";
      document.querySelector("[for=Profile4]").innerText = getI18n("profile") + " 4";
    }
    if (curDevice.pid === 49989) {
      document.querySelector("[for=menu4]").style.display = "none";
      document.querySelector("[for=menu7]").style.display = "none";
      document.querySelector("[for=keyManu4]").style.display = "none";
    } else {
      document.querySelector("[for=menu4]").style.display = "flex";
      if (document.querySelector("[for=keyManu4]")) {
        document.querySelector("[for=keyManu4]").style.display = "flex";
      }
    }
    document.querySelector("[for=triggerManu4]").style.display = isPollRate ? "flex" : "none";
    if (pollRate === 1) {
      document.getElementById("pollRate1").checked = true;
    }
    if (pollRate === 2) {
      document.getElementById("pollRate2").checked = true;
    }
    if (pollRate === 4) {
      document.getElementById("pollRate3").checked = true;
    }
    if (pollRate === 8) {
      document.getElementById("pollRate4").checked = true;
    }
    document.querySelector("[for=triggerManu5]").style.display = isDeadBand ? "flex" : "none";
    document.getElementById("performance3").style.display = isALlAnd6keySwitch ? "flex" : "none";
    const _0x1a302c = document.getElementById("perCheckbox5");
    const _0x53d057 = document.getElementById("perCheckbox6");
    if (is6KeyMode) {
      _0x53d057.checked = true;
    } else {
      _0x1a302c.checked = true;
    }
    const _0x4a94e0 = document.getElementById("gamePad1");
    const _0xa83ab1 = document.getElementById("gamePad2");
    const _0x3e7399 = document.getElementById("gamePad3");
    const _0x305bf0 = document.querySelector("[for=keyManu10]");
    if (_0x305bf0) {
      _0x305bf0.style.display = isGamePad ? "flex" : "none";
      if (curDevice.pid === 50022) {
        _0xa83ab1.checked = true;
      } else if (curDevice.pid === 50023) {
        _0x3e7399.checked = true;
      } else {
        _0x4a94e0.checked = true;
      }
    }
    curProfile.light = curDevice.light;
    if (curCompany === "mile_varo") {
      curProfile.defKeys = recKeys;
      curProfile.fnKeys = fnKeys;
      curProfile.recMacros = recMacros;
    } else {
      if (recKeys.size > 0) {
        curProfile.defKeys = recKeys;
      } else {
        recKeys = curProfile.defKeys;
      }
      if (fnKeys.size > 0) {
        curProfile.fnKeys = fnKeys;
      } else {
        fnKeys = curProfile.fnKeys;
      }
      if (recMacros.size > 0) {
        curProfile.recMacros = recMacros;
      } else {
        recMacros = curProfile.recMacros;
      }
    }
    curProfile.triggers.clear();
    curDevice.keys.forEach(_0xfd633c => {
      curProfile.triggers.set(_0xfd633c.index, deepCopy(_0xfd633c.trigger));
    });
    document.getElementById("startDiv").style.display = "none";
    document.getElementById("mainDiv").style.display = "block";
    if (isPrcs) {
      menu7.style.display = "flex";
    }
    hbTimer = setInterval(heartbeat, 1000);
    refreshColorView(0);
    let _0x31300e = document.getElementById("devViewDiv").offsetWidth;
    let _0x3155b9 = document.getElementById("devViewDiv").offsetHeight;
    let _0x3472ee = _0x31300e / curDevice.width;
    let _0x1a4818 = _0x3155b9 / (curDevice.height + 30);
    bili = _0x3472ee < _0x1a4818 ? _0x3472ee : _0x1a4818;
    if (bili > 1.55) {
      bili = 1.55;
    }
    let _0x5670b8 = document.getElementById("customView");
    let _0x5a81e7 = document.getElementById("customTop");
    document.getElementById("customBottom").style.height = _0x5670b8.offsetHeight - _0x5a81e7.offsetHeight + "px";
    let _0x3b7329 = document.getElementById("triggerView");
    document.getElementById("triggerBottom").style.height = _0x3b7329.offsetHeight - 40 + "px";
    let _0x22a98 = document.getElementById("prcsView");
    document.getElementById("prcsBottom").style.height = _0x22a98.offsetHeight - 40 + "px";
    let _0x4f9c0d = (_0x3155b9 - curDevice.height * bili) / 2 - 10;
    if (_0x4f9c0d < 5) {
      _0x4f9c0d = 5;
    }
    document.getElementById("devName").innerText = curDevice.name;
    devSet.style.width = curDevice.width * bili + "px";
    devSet.style.minWidth = curDevice.width * bili + "px";
    devSet.style.height = curDevice.height * bili + "px";
    devSet.innerHTML = "";
    let _0x1a7d82 = document.createElement("div");
    _0x1a7d82.className = "devKeySet";
    devSet.appendChild(_0x1a7d82);
    checkedTip = document.createElement("label");
    checkedTip.className = "checkedTip";
    checkedTip.innerText = getI18n("checkedTip");
    checkedTip.setAttribute("i18n", "checkedTip");
    devSet.appendChild(checkedTip);
    i18n;
    unitNum = countDecimals(curDevice.triggerUnit);
    hasRotaryKnob = false;
    curDevice.keys.forEach(_0x209f6e => {
      if (_0x209f6e.code === "RotaryKnob") {
        hasRotaryKnob = true;
        let _0x4cd5ec = document.createElement("label");
        _0x4cd5ec.id = "devKnobPanel";
        _0x4cd5ec.className = "devKnobPanel";
        _0x4cd5ec.style.left = _0x209f6e.x * bili + "px";
        _0x4cd5ec.style.top = _0x209f6e.y * bili + "px";
        _0x4cd5ec.style.width = _0x209f6e.width * bili + "px";
        _0x4cd5ec.style.height = _0x209f6e.height * bili + "px";
        _0x4cd5ec.value = _0x209f6e.x + "," + _0x209f6e.y + "," + _0x209f6e.width + "," + _0x209f6e.height;
        _0x1a7d82.appendChild(_0x4cd5ec);
      } else if (_0x209f6e.code === "SideKnob") {
        let _0xa24a02 = document.createElement("label");
        _0xa24a02.id = "devSidePanel";
        _0xa24a02.className = "devSidePanel";
        _0xa24a02.style.left = _0x209f6e.x * bili + "px";
        _0xa24a02.style.top = _0x209f6e.y * bili + "px";
        _0xa24a02.style.width = _0x209f6e.width * bili + "px";
        _0xa24a02.style.height = _0x209f6e.height * bili + "px";
        _0xa24a02.value = _0x209f6e.x + "," + _0x209f6e.y + "," + _0x209f6e.width + "," + _0x209f6e.height;
        devSet.appendChild(_0xa24a02);
      } else if (_0x209f6e.code === "IdlerWheel") {
        let _0x59a696 = document.createElement("label");
        _0x59a696.id = "devIdlerWheel";
        _0x59a696.className = "devIdlerWheel";
        _0x59a696.style.left = _0x209f6e.x * bili + "px";
        _0x59a696.style.top = _0x209f6e.y * bili + "px";
        _0x59a696.style.width = _0x209f6e.width * bili + "px";
        _0x59a696.style.height = _0x209f6e.height * bili + "px";
        _0x59a696.value = _0x209f6e.x + "," + _0x209f6e.y + "," + _0x209f6e.width + "," + _0x209f6e.height;
        devSet.appendChild(_0x59a696);
      } else if (_0x209f6e.code === "IdlerWheelV") {
        let _0x1615d1 = document.createElement("label");
        _0x1615d1.id = "devIdlerWheelV";
        _0x1615d1.className = "devIdlerWheelV";
        _0x1615d1.style.left = _0x209f6e.x * bili + "px";
        _0x1615d1.style.top = _0x209f6e.y * bili + "px";
        _0x1615d1.style.width = _0x209f6e.width * bili + "px";
        _0x1615d1.style.height = _0x209f6e.height * bili + "px";
        _0x1615d1.value = _0x209f6e.x + "," + _0x209f6e.y + "," + _0x209f6e.width + "," + _0x209f6e.height;
        devSet.appendChild(_0x1615d1);
      } else {
        let _0x5392dc = _0x209f6e.code;
        let _0x27071f = document.createElement("input");
        if (curDevice.product === "7575USHEXYXREJCARGB") {
          if (_0x209f6e.code === "KeyFn" || _0x209f6e.code === "KeyT" || _0x209f6e.code === "Backquote" || _0x209f6e.code === "CustomG1" || _0x209f6e.code === "CustomG2" || _0x209f6e.code === "CustomG3" || _0x209f6e.code === "CustomG4" || _0x209f6e.code === "CustomG5") {
            _0x27071f.type = "button";
          } else {
            _0x27071f.type = "radio";
          }
        } else {
          _0x27071f.type = _0x209f6e.code === "KeyFn" ? "button" : "radio";
        }
        _0x27071f.id = _0x5392dc;
        if (curDevice.type !== "uk" && curDevice.type !== "jp" || _0x209f6e.code !== "Enter") {
          _0x27071f.className = "devKey";
        } else {
          _0x27071f.className = "devKeyUK";
        }
        _0x27071f.name = "devKey";
        let _0x44e6ea = document.createElement("label");
        if (curDevice.type !== "uk" && curDevice.type !== "jp" || _0x209f6e.code !== "Enter") {
          _0x44e6ea.className = "devKeyPanel";
        } else {
          _0x44e6ea.className = "devKeyPanelUK";
        }
        _0x44e6ea.style.left = _0x209f6e.x * bili + "px";
        _0x44e6ea.style.top = _0x209f6e.y * bili + "px";
        _0x44e6ea.style.width = _0x209f6e.width * bili + "px";
        _0x44e6ea.style.height = _0x209f6e.height * bili + "px";
        _0x44e6ea.value = _0x209f6e.x + "," + _0x209f6e.y + "," + _0x209f6e.width + "," + _0x209f6e.height;
        _0x44e6ea.setAttribute("for", _0x5392dc);
        let _0xd8382f = document.createElement("span");
        _0xd8382f.className = "devKeyPanelView";
        _0x44e6ea.appendChild(_0xd8382f);
        let _0x12c1d1 = document.createElement("span");
        _0x12c1d1.className = "devKeyName";
        _0x12c1d1.setAttribute("for", _0x5392dc);
        _0x12c1d1.innerText = _0x209f6e.name;
        _0x12c1d1.style.fontSize = bili * 11 + "px";
        _0x12c1d1.style.paddingLeft = bili * 3 + "px";
        _0x12c1d1.style.paddingTop = bili * 3 + "px";
        let _0x6a6bfb = document.createElement("img");
        _0x6a6bfb.className = "devKeyRedDot";
        _0x6a6bfb.src = "image/icon_redDot.png";
        _0x6a6bfb.alt = "";
        if (keymapDef.checked && recKeys.has(_0x209f6e.index) || keymapFn.checked && fnKeys.has(_0x209f6e.index) && !fnKeyState.includes(_0x209f6e.index)) {
          let _0x2e9022 = recKeys.get(_0x209f6e.index);
          if (keymapFn.checked) {
            _0x2e9022 = fnKeys.get(_0x209f6e.index);
          }
          if (_0x2e9022.code1 === 24 || _0x2e9022.code1 === 25) {
            if (_0x2e9022.code1 === 24 && curDevice.pid === 50023 || _0x2e9022.code1 === 25 && curDevice.pid === 50022) {
              _0x6a6bfb.style.display = "block";
            } else {
              _0x6a6bfb.style.display = "none";
            }
          } else {
            _0x6a6bfb.style.display = "block";
          }
        }
        let _0x33a6bf = document.createElement("span");
        _0x33a6bf.className = "devKeyTrigger";
        let _0x3fd3e4 = document.createElement("label");
        _0x3fd3e4.className = "devKeyTV";
        _0x3fd3e4.innerText = (_0x209f6e.trigger.travel * curDevice.triggerUnit).toFixed(unitNum);
        _0x3fd3e4.style.fontSize = Math.floor(bili * 7) + "px";
        _0x3fd3e4.style.paddingRight = bili * 2 + "px";
        _0x3fd3e4.style.marginTop = bili * 12 + "px";
        let _0x514f3f = document.createElement("span");
        _0x514f3f.className = "devKeyTIView";
        let _0x5f2609 = document.createElement("label");
        _0x5f2609.className = "devKeyTI1";
        _0x5f2609.innerText = (_0x209f6e.trigger.interval1 * curDevice.triggerUnit).toFixed(unitNum);
        _0x5f2609.style.fontSize = Math.floor(bili * 6) + "px";
        _0x5f2609.style.display = _0x209f6e.trigger.mode > 0 ? "flex" : "none";
        let _0x224c95 = document.createElement("label");
        _0x224c95.className = "devKeyTI2";
        _0x224c95.innerText = (_0x209f6e.trigger.interval2 * curDevice.triggerUnit).toFixed(unitNum);
        _0x224c95.style.fontSize = Math.floor(bili * 6) + "px";
        _0x224c95.style.paddingRight = bili + "px";
        _0x224c95.style.display = _0x209f6e.trigger.mode > 0 ? "flex" : "none";
        _0x224c95.style.color = _0x209f6e.trigger.mode === 13 ? "var(--text-color3)" : "var(--text-color2)";
        let _0x422e6e = document.createElement("span");
        _0x422e6e.className = "devKeyBackColor";
        _0x422e6e.style.width = _0x209f6e.width * bili - 4 + "px";
        _0x422e6e.style.height = _0x209f6e.height * bili - 4 + "px";
        let _0x4fca96 = switchDefault.find(_0x3d6aed => _0x3d6aed.index === _0x209f6e.switch);
        if (_0x4fca96 == null) {
          _0x4fca96 = switchDefault[0];
        }
        let _0x109537 = document.createElement("span");
        _0x109537.className = "devKeySwitch";
        _0x109537.style.borderColor = _0x4fca96.color.toRgb();
        let _0x2078cd = document.createElement("label");
        _0x2078cd.className = "devKeySwitchTitle";
        _0x2078cd.style.width = bili * 20 + "px";
        _0x2078cd.style.height = bili * 13 + "px";
        _0x2078cd.style.fontSize = Math.floor(bili * 7) + "px";
        _0x2078cd.style.backgroundColor = _0x4fca96.color.toRgb();
        _0x2078cd.innerText = _0x4fca96.title;
        _0x109537.appendChild(_0x2078cd);
        _0x514f3f.appendChild(_0x5f2609);
        _0x514f3f.appendChild(_0x224c95);
        _0x33a6bf.appendChild(_0x3fd3e4);
        _0x33a6bf.appendChild(_0x514f3f);
        _0xd8382f.appendChild(_0x12c1d1);
        _0xd8382f.appendChild(_0x6a6bfb);
        _0xd8382f.appendChild(_0x33a6bf);
        _0xd8382f.appendChild(_0x422e6e);
        _0xd8382f.appendChild(_0x109537);
        _0x27071f.onchange = function () {
          if (menu1.checked) {
            comKeys = [];
            initKey(_0x44e6ea, _0x209f6e, _0x27071f.checked);
          }
          if (menu2.checked) {
            refreshCheckedKeys(_0x44e6ea, _0x209f6e, _0x27071f.checked);
          }
          if (menu4.checked) {
            refreshCheckedKeys(_0x44e6ea, _0x209f6e, _0x27071f.checked);
            refreshTriggerSlider(_0x209f6e.trigger.travel);
          }
        };
        _0x44e6ea.onmouseenter = function () {
          if (menu1.checked) {
            let _0x5bd944 = _0x209f6e.name;
            if (keymapFn.checked) {
              _0x5bd944 = _0x209f6e.code === "KeyFn" ? _0x209f6e.name : "Fn + " + _0x209f6e.name;
            }
            document.getElementById("keyTipName").innerText = _0x5bd944 ? _0x5bd944.replace(/[\s\u3000]/g, "") : _0x5bd944;
            let _0x4348c5 = getI18n("tipDefault");
            let _0x3cd8ee = _0x209f6e.name;
            if (keymapDef.checked) {
              _0x3cd8ee = curDevice.product === "7575USHEXYXREJCARGB" && _0x209f6e.code === "KeyT" ? _0x209f6e.code === "KeyFn" || _0x209f6e.code === "Backquote" || _0x209f6e.code === "CustomG1" || _0x209f6e.code === "CustomG2" || _0x209f6e.code === "CustomG3" || _0x209f6e.code === "CustomG4" || _0x209f6e.code === "CustomG5" ? getI18n("notRemappable") : _0x209f6e.name : _0x209f6e.code === "KeyFn" ? getI18n("notRemappable") : _0x209f6e.name;
            }
            if (keymapFn.checked) {
              _0x3cd8ee = fnKeyState.includes(_0x209f6e.index) ? getI18n("notRemappable") : _0x209f6e.name;
            }
            if (keymapDef.checked && recKeys.has(_0x209f6e.index) || keymapFn.checked && fnKeys.has(_0x209f6e.index) && !fnKeyState.includes(_0x209f6e.index)) {
              let _0x178b42 = recKeys.get(_0x209f6e.index);
              if (keymapFn.checked) {
                _0x178b42 = fnKeys.get(_0x209f6e.index);
              }
              if (_0x178b42.code1 === 24 || _0x178b42.code1 === 25) {
                if (_0x178b42.code1 === 24 && curDevice.pid === 50023 || _0x178b42.code1 === 25 && curDevice.pid === 50022) {
                  _0x3cd8ee = _0x178b42.code1 > 0 ? getI18n(_0x178b42.code) : _0x178b42.name;
                }
              } else {
                _0x3cd8ee = _0x178b42.code1 > 0 ? getI18n(_0x178b42.code) : _0x178b42.name;
              }
              switch (_0x178b42.code1) {
                case 0:
                  _0x4348c5 = getI18n("keyManu1");
                  break;
                case 2:
                case 3:
                case 4:
                case 5:
                case 6:
                  _0x4348c5 = getI18n("lighting");
                  break;
                case 7:
                  _0x4348c5 = getI18n("multimedia");
                  break;
                case 16:
                  _0x4348c5 = getI18n("keyManu3");
                  _0x3cd8ee = _0x178b42.name;
                  break;
                case 17:
                  _0x4348c5 = getI18n("function");
                  break;
                case 18:
                  _0x4348c5 = getI18n("mouse");
                  break;
                case 19:
                  _0x4348c5 = getI18n("keyManu2");
                  if (_0x3cd8ee === "") {
                    _0x3cd8ee = _0x178b42.name;
                  }
                  break;
                case 23:
                  _0x4348c5 = getI18n("keyManu4");
                  _0x3cd8ee = _0x178b42.name;
                  break;
                case 24:
                  if (curDevice.vid === 50023) {
                    _0x4348c5 = getI18n("gamePad");
                    _0x3cd8ee = getI18n(_0x178b42.code);
                  }
                  break;
                case 25:
                  if (curDevice.vid === 50022) {
                    _0x4348c5 = getI18n("gamePad");
                    _0x3cd8ee = getI18n(_0x178b42.code);
                  }
              }
            }
            document.getElementById("keyTipType").innerText = _0x4348c5;
            document.getElementById("keyTipValue").innerText = _0x3cd8ee ? _0x3cd8ee.replace(/[\s\u3000]/g, "") : _0x3cd8ee;
            let _0x5c7f9a = _0x12c1d1.getBoundingClientRect();
            if (_0x5c7f9a.y < 120) {
              keyTip.querySelector("[class=triangleUp]").style.display = "flex";
              keyTip.querySelector("[class=triangleDown]").style.display = "none";
              keyTip.style.top = _0x5c7f9a.top + _0x5c7f9a.height - bili * 2 + "px";
            } else {
              keyTip.querySelector("[class=triangleUp]").style.display = "none";
              keyTip.querySelector("[class=triangleDown]").style.display = "flex";
              keyTip.style.top = _0x5c7f9a.top - 130 + "px";
            }
            keyTip.style.left = _0x5c7f9a.left - (220 - _0x5c7f9a.width) / 2 + "px";
            keyTip.style.display = "flex";
          }
        };
        _0x44e6ea.onmouseleave = function () {
          keyTip.style.display = "none";
        };
        _0x1a7d82.appendChild(_0x27071f);
        _0x1a7d82.appendChild(_0x44e6ea);
      }
    });
    const _0x1aea22 = devSet.querySelectorAll(".devKeyPanel");
    const _0x3b9d1a = devSet.querySelectorAll(".devKeyPanelUK");
    keyBtn = [..._0x1aea22, ..._0x3b9d1a];
    console.log(fixedKeys);
    if (curDevice && curDevice.company.includes("tryhard")) {
      await initFixedKeys("../config/keysFr.json");
    }
    if (curDevice && curDevice.product === "QK75CHEARGB") {
      await initFixedKeys("../config/keysTr.json");
    }
    if (curDevice && curDevice.company.includes("sanpin_glick")) {
      curCompany = "sanpin_glick";
      await initFixedKeys();
    }
    initFixedKeyView(fixedKeySet, 0);
    initFixedKeyView(fixedKeySet2, 1);
    initFixedKeyView(fixedKeySet3, 2);
    if (curDevice.pid === 50022) {
      initGameKeyView("gamePad2");
    } else if (curDevice.pid === 50023) {
      initGameKeyView("gamePad3");
    } else {
      initGameKeyView("gamePad1");
    }
    if (macros.length <= 0) {
      macros = deepCopy(curProfile.macros);
    } else {
      curProfile.macros = deepCopy(macros);
    }
    if (advKeys.length <= 0) {
      advKeys = deepCopy(curProfile.advKeys);
    } else {
      curProfile.advKeys = deepCopy(advKeys);
    }
    refreshMacroList(macros);
    refreshPrcsList(prcses);
    const _0x276ee6 = document.getElementById("prcsList").querySelectorAll("input");
    if (_0x276ee6.length > 0) {
      const _0x2e1c98 = _0x276ee6[0];
      _0x2e1c98.checked = true;
      _0x2e1c98.dispatchEvent(new Event("change"));
    }
    refreshAdvList();
    initLightView();
    curProfile.prcsPower = document.getElementById("prcsPower").checked ? 1 : 0;
    curProfile.prcses = prcses;
    _0x316092 = JSON.stringify(profileSet, replacer);
    localStorage.setItem(curDevice.product, _0x316092);
    triggerDown.setAttribute("max", Math.ceil(curDevice.maxTriggerTravel / 2));
    triggerDown.setAttribute("min", 1);
    triggerDown.setAttribute("step", curDevice.triggerUnit);
    triggerDown.setAttribute("value", Math.floor(0.5 / curDevice.triggerUnit));
    triggerUp.setAttribute("max", Math.ceil(curDevice.maxTriggerTravel / 2));
    triggerUp.setAttribute("min", 1);
    triggerUp.setAttribute("step", curDevice.triggerUnit);
    triggerUp.setAttribute("value", Math.floor(0.5 / curDevice.triggerUnit));
    dbTop.setAttribute("max", Math.ceil(1 / curDevice.triggerUnit));
    dbTop.setAttribute("min", 0);
    dbTop.setAttribute("step", curDevice.triggerUnit);
    dbTop.setAttribute("value", 2);
    dbBottom.setAttribute("max", Math.ceil(1 / curDevice.triggerUnit));
    dbBottom.setAttribute("min", 0);
    dbBottom.setAttribute("step", curDevice.triggerUnit);
    dbBottom.setAttribute("value", 2);
    getI18nDom(document.body);
    if (Math.abs(window.outerHeight - oldHeight) > 50) {
      isWinChanged = true;
      timer = setInterval(refreshDevice, 100);
      console.log("start timer,Refresh device");
    }
    oldHeight = window.outerHeight;
    const _0x13bbf8 = document.querySelectorAll("#triggerMenuDiv label");
    if (!Array.from(_0x13bbf8).find(_0x29ce34 => _0x29ce34.style.display !== "none")) {
      document.querySelector("[for=menu4]").style.display = "none";
    }
  }
}
function initLightView() {
  if (curDevice !== undefined) {
    const _0x3a57c4 = document.getElementById("lightManu1");
    const _0x46cdda = document.getElementById("lightManu2");
    const _0x70a0f4 = document.getElementById("lightPower");
    const _0x12a3d8 = document.getElementById("lightModels");
    const _0x337a95 = document.getElementById("sideLightModels");
    const _0x5b0fa0 = document.getElementById("lightBrightness");
    const _0x501fee = document.getElementById("lightSpeed");
    const _0x5cbcbc = document.getElementById("colorForeground");
    const _0x2a56e4 = document.getElementById("colorBackgroundLabel");
    const _0x3cfd78 = document.getElementById("lightDirectionDiv");
    const _0x197fce = document.getElementById("lightCustomDiv");
    const _0x16bfa3 = document.getElementById("fullColor");
    _0x70a0f4.checked = curDevice.light.power === 0;
    if (_0x3a57c4.checked) {
      _0x12a3d8.querySelectorAll("input").forEach(_0x25ab2f => {
        if (isMusicRhythmOn) {
          if (_0x25ab2f.value === "100") {
            _0x25ab2f.checked = true;
            _0x25ab2f.dispatchEvent(new Event("change"));
          }
        } else if (curDevice.light.mode.toString() === _0x25ab2f.value) {
          _0x25ab2f.checked = true;
          refreshColorView(parseInt(_0x25ab2f.value));
        }
      });
      showKeyColor(menu2.checked && curDevice.light.mode === 10);
      _0x5b0fa0.max = curDevice.maxLightBrightness;
      _0x5b0fa0.value = curDevice.light.brightness;
      _0x5b0fa0.dispatchEvent(new Event("input"));
      _0x501fee.max = curDevice.maxLightSpeed;
      _0x501fee.value = curDevice.light.speed;
      _0x501fee.dispatchEvent(new Event("input"));
      _0x2a56e4.style.backgroundColor = curDevice.light.backgroundColor.toRgb();
      _0x5cbcbc.checked = true;
      curR = curDevice.light.foregroundColor.r;
      curG = curDevice.light.foregroundColor.g;
      curB = curDevice.light.foregroundColor.b;
      setRgb(curR, curG, curB);
      _0x3cfd78.querySelectorAll("input").forEach(_0xbac225 => {
        if (curDevice.light.direction.toString() === _0xbac225.value) {
          _0xbac225.checked = true;
        }
      });
      if (isCustomLight) {
        if (curDevice.light.mode === 10) {
          _0x197fce.style.display = "flex";
        } else {
          _0x197fce.style.display = "none";
        }
        setKeysColor();
      } else {
        _0x197fce.style.display = "none";
      }
      _0x16bfa3.checked = curDevice.light.fullColor === 1;
    }
    if (_0x46cdda.checked) {
      _0x337a95.querySelectorAll("input").forEach(_0x35f25a => {
        if (curDevice.sideLight.mode.toString() === _0x35f25a.value) {
          _0x35f25a.checked = true;
          refreshColorView(parseInt(_0x35f25a.value));
        }
      });
      showKeyColor(false);
      _0x5b0fa0.max = curDevice.maxSideLightBrightness;
      _0x5b0fa0.value = curDevice.sideLight.brightness;
      _0x5b0fa0.dispatchEvent(new Event("input"));
      _0x501fee.max = curDevice.maxSideLightSpeed;
      _0x501fee.value = curDevice.sideLight.speed;
      _0x501fee.dispatchEvent(new Event("input"));
      _0x2a56e4.style.backgroundColor = curDevice.sideLight.backgroundColor.toRgb();
      _0x5cbcbc.checked = true;
      curR = curDevice.sideLight.foregroundColor.r;
      curG = curDevice.sideLight.foregroundColor.g;
      curB = curDevice.sideLight.foregroundColor.b;
      setRgb(curR, curG, curB);
      _0x3cfd78.querySelectorAll("input").forEach(_0x583f79 => {
        if (curDevice.sideLight.direction.toString() === _0x583f79.value) {
          _0x583f79.checked = true;
        }
      });
      _0x197fce.style.display = "none";
      _0x16bfa3.checked = curDevice.sideLight.fullColor === 1;
    }
    const _0x27b15d = document.querySelector("[for=lightMode10]");
    if (_0x27b15d !== null) {
      _0x27b15d.style.display = isCustomLight ? "flex" : "none";
    }
  }
}
window.addEventListener("resize", async () => {
  setViewport();
});
window.addEventListener("resize", async () => {
  refreshDevice();
  if (Math.abs(window.outerHeight - oldHeight) > 50) {
    isWinChanged = true;
    timer = setInterval(refreshDevice, 50);
    console.log("start timer,Refresh device");
  }
  oldHeight = window.outerHeight;
});
let isDeviceInfoRead = false;
let dongleCount = 0;
let timeoutId;
async function initDevice(_0x40bb86) {
  let _0xe095e6 = false;
  for (const _0x4f5e66 of _0x40bb86) {
    if (_0x4f5e66 !== undefined) {
      console.log(_0x4f5e66.collections.length);
      for (const _0x7d69b6 of devList) {
        if (_0x7d69b6.vid === _0x4f5e66.vendorId && _0x7d69b6.pid === _0x4f5e66.productId) {
          if (curCompany !== "" && curCompanyList && curCompanyList.length > 0) {
            if (!curCompanyList.some(_0x325058 => _0x7d69b6.company === _0x325058)) {
              continue;
            }
          } else if (curCompany !== "" && _0x7d69b6.company !== curCompany) {
            continue;
          }
          if (curCompany === "" && notAllow.includes(_0x7d69b6.company)) {
            continue;
          }
          for (let _0x293211 of _0x4f5e66.collections) {
            if (_0x293211.inputReports.length > 0 && _0x293211.outputReports.length > 0) {
              isDeviceInfoRead = false;
              if (!_0x4f5e66.opened) {
                await _0x4f5e66.open();
              }
              let _0x3c60fa = false;
              _0x4f5e66.oninputreport = ({
                reportId: _0x37af63,
                data: _0x4c0ab1
              }) => {
                let _0x5ba9e5 = new Uint8Array(_0x4c0ab1.buffer);
                if (_0x37af63 === 1 && _0x5ba9e5[0] === 13 && _0x5ba9e5[3] === 0) {
                  _0x3c60fa = _0x5ba9e5[1] === 0;
                  let _0x1d6e8b = _0x5ba9e5[4];
                  let _0x30fbe1 = _0x5ba9e5.subarray(5, _0x1d6e8b);
                  let _0x389301 = new TextDecoder().decode(_0x30fbe1);
                  let _0x11b3a0 = _0x389301.split(",");
                  if (_0x11b3a0.length > 4) {
                    devProduct = _0x11b3a0[4];
                  }
                  if (_0x11b3a0.length > 5) {
                    let _0xe7aeff = _0x11b3a0[5];
                    _0xe7aeff = _0xe7aeff.replace(/[\x00-\x08\x0e-\x1f]/g, "");
                    _0xe7aeff = _0xe7aeff.split("V").join("");
                    _0xe7aeff = _0xe7aeff.split("_").join(".");
                    _0x7d69b6.version = _0xe7aeff;
                  }
                  console.log(_0x389301);
                  if (_0x389301.includes("dongle")) {
                    dongleCount++;
                    if (dongleCount > 1) {
                      showAlert(getI18n("sleepSetTip7"));
                    }
                  }
                  isDeviceInfoRead = true;
                }
              };
              let _0x6ac3fa = new ArrayBuffer(63);
              let _0x1414b4 = new Uint8Array(_0x6ac3fa);
              _0x1414b4[0] = 13;
              await _0x4f5e66.sendReport(1, _0x1414b4);
              while (!isDeviceInfoRead) {
                await new Promise(_0x5a1258 => setTimeout(_0x5a1258, 1));
              }
              isDeviceInfoRead = false;
              if (devProduct === _0x7d69b6.product) {
                hidDevice = _0x4f5e66;
                curDevice = _0x7d69b6;
                _0xe095e6 = true;
                break;
              }
            }
          }
        }
        if (_0xe095e6) {
          break;
        }
      }
    }
    if (_0xe095e6) {
      break;
    }
  }
}
function refreshDevice() {
  if (isWinChanged) {
    refreshCount++;
    if (refreshCount > 10) {
      isWinChanged = false;
      refreshCount = 0;
      if (timer !== undefined) {
        clearInterval(timer);
      }
    }
  }
  if (curDevice !== undefined) {
    let _0x215a11 = document.getElementById("devViewDiv").offsetWidth;
    let _0x188eda = document.getElementById("devViewDiv").offsetHeight;
    let _0x2e0b7e = _0x215a11 / curDevice.width;
    let _0x27f882 = _0x188eda / (curDevice.height + 30);
    bili = _0x2e0b7e < _0x27f882 ? _0x2e0b7e : _0x27f882;
    if (bili > 1.55) {
      bili = 1.55;
    }
    let _0x4edb4d = document.getElementById("customView");
    let _0xd7ddb4 = document.getElementById("customTop");
    document.getElementById("customBottom").style.height = _0x4edb4d.offsetHeight - _0xd7ddb4.offsetHeight + "px";
    let _0x228741 = document.getElementById("lightView");
    let _0x8450e3 = document.getElementById("lightTop");
    document.getElementById("lightBottom").style.height = _0x228741.offsetHeight - _0x8450e3.offsetHeight + "px";
    let _0x47fb43 = document.getElementById("triggerView");
    let _0x37c8c7 = document.getElementById("triggerTop");
    document.getElementById("triggerBottom").style.height = _0x47fb43.offsetHeight - _0x37c8c7.offsetHeight + "px";
    let _0x443a05 = document.getElementById("prcsView");
    let _0x52e6fc = document.getElementById("prcsTop");
    document.getElementById("prcsBottom").style.height = _0x443a05.offsetHeight - _0x52e6fc.offsetHeight + "px";
    if (curProfile.triggers.size > 0) {
      let _0x33d419 = curProfile.triggers.entries().next().value[1];
      initTriggerSlider(curDevice.maxTriggerTravel, curDevice.triggerUnit, _0x33d419.travel);
    } else {
      let _0x2271b3 = Math.floor(curDevice.maxTriggerTravel / 2);
      initTriggerSlider(curDevice.maxTriggerTravel, curDevice.triggerUnit, _0x2271b3);
    }
    let _0x551e5c = (_0x188eda - curDevice.height * bili) / 2 - 10;
    if (_0x551e5c < 5) {
      _0x551e5c = 5;
    }
    devSet.style.width = curDevice.width * bili + "px";
    devSet.style.minWidth = curDevice.width * bili + "px";
    devSet.style.height = curDevice.height * bili + "px";
    document.getElementById("keymapTableView");
    document.getElementById("selectAllView");
    setTimeout(() => {
      keymapTable.style.top = devSet.offsetTop + "px";
      keymapTable.style.left = devSet.offsetLeft + "px";
    }, 100);
    i18n;
    let _0x41246f = document.getElementById("devKnobPanel");
    let _0x34f838 = document.getElementById("devSidePanel");
    let _0x42d708 = document.getElementById("devIdlerWheel");
    let _0xbb68fb = document.getElementById("devIdlerWheelV");
    function _0x3529f5(_0x28dab9) {
      if (_0x28dab9 != null) {
        let _0x3f1ac6 = _0x28dab9.value;
        if (_0x3f1ac6 !== undefined) {
          let _0x48daad = _0x3f1ac6.split(",");
          if (_0x48daad.length >= 4) {
            let _0x509a38 = parseFloat(_0x48daad[0]);
            let _0xae1fff = parseFloat(_0x48daad[1]);
            let _0x27fad9 = parseFloat(_0x48daad[2]);
            let _0x5c86da = parseFloat(_0x48daad[3]);
            _0x28dab9.style.left = _0x509a38 * bili + "px";
            _0x28dab9.style.top = _0xae1fff * bili + "px";
            _0x28dab9.style.width = _0x27fad9 * bili + "px";
            _0x28dab9.style.height = _0x5c86da * bili + "px";
          }
        }
      }
    }
    _0x3529f5(_0x41246f);
    _0x3529f5(_0x34f838);
    _0x3529f5(_0x42d708);
    _0x3529f5(_0xbb68fb);
    keyBtn.forEach(_0x57c79a => {
      let _0x33ba60 = _0x57c79a.value;
      if (_0x33ba60 !== undefined) {
        let _0x9be04f = _0x33ba60.split(",");
        if (_0x9be04f.length >= 4) {
          let _0x871702 = parseFloat(_0x9be04f[0]);
          let _0x1d7581 = parseFloat(_0x9be04f[1]);
          let _0x38062a = parseFloat(_0x9be04f[2]);
          let _0x18bf60 = parseFloat(_0x9be04f[3]);
          _0x57c79a.style.left = _0x871702 * bili + "px";
          _0x57c79a.style.top = _0x1d7581 * bili + "px";
          _0x57c79a.style.width = _0x38062a * bili + "px";
          _0x57c79a.style.height = _0x18bf60 * bili + "px";
          _0x57c79a.querySelector("[class=devKeyBackColor]").style.width = _0x38062a * bili - 4 + "px";
          _0x57c79a.querySelector("[class=devKeyBackColor]").style.height = _0x18bf60 * bili - 4 + "px";
        }
        let _0x35507e = _0x57c79a.querySelector("[class=devKeyName]");
        _0x57c79a.querySelector("img").style.width = bili * 8 + "px";
        _0x57c79a.querySelector("img").style.height = bili * 8 + "px";
        _0x35507e.style.fontSize = bili * 10 + "px";
        _0x57c79a.querySelector("[class=devKeyTV]").style.fontSize = Math.floor(bili * 7) + "px";
        _0x57c79a.querySelector("[class=devKeyTV]").style.marginTop = bili * 12 + "px";
        _0x57c79a.querySelector("[class=devKeyTI1]").style.fontSize = Math.floor(bili * 6) + "px";
        _0x57c79a.querySelector("[class=devKeyTI2]").style.fontSize = Math.floor(bili * 6) + "px";
        _0x57c79a.querySelector("[class=devKeySwitchTitle]").style.width = bili * 20 + "px";
        _0x57c79a.querySelector("[class=devKeySwitchTitle]").style.height = bili * 13 + "px";
        _0x57c79a.querySelector("[class=devKeySwitchTitle]").style.fontSize = Math.floor(bili * 7) + "px";
      }
    });
    refreshDksButton();
  }
}
function refreshDksButton() {
  let _0xa3fce8 = [];
  let _0x7ccf06 = [];
  let _0x3c4555 = document.getElementById("row1");
  let _0x4490bb = document.getElementById("row2");
  let _0xd0342b = document.getElementById("row3");
  let _0x405a39 = document.getElementById("row4");
  _0xa3fce8.push(_0x3c4555);
  _0xa3fce8.push(_0x4490bb);
  _0xa3fce8.push(_0xd0342b);
  _0xa3fce8.push(_0x405a39);
  let _0x49935b = document.getElementById("col1");
  let _0x4100f0 = document.getElementById("col2");
  let _0x3dc214 = document.getElementById("col3");
  let _0x322b68 = document.getElementById("col4");
  _0x7ccf06.push(_0x49935b);
  _0x7ccf06.push(_0x4100f0);
  _0x7ccf06.push(_0x3dc214);
  _0x7ccf06.push(_0x322b68);
  let _0xf9efc3 = document.getElementById("tabLeftTop");
  let _0x5c20fd = document.getElementById("tabLeftRow2");
  document.getElementById("dksInfoDetail").querySelectorAll("label").forEach(_0x33e4d2 => {
    let _0xaff1e5 = parseInt(_0x33e4d2.innerText);
    let _0x338eee = Math.floor(_0xaff1e5 / 4);
    let _0x774026 = Math.floor(_0xaff1e5 % 4);
    if (_0x338eee < _0xa3fce8.length && _0x774026 < _0x7ccf06.length) {
      let _0x455865 = _0x7ccf06[_0x774026].offsetWidth;
      let _0x50248c = _0xa3fce8[_0x338eee].offsetHeight;
      let _0x1be975 = _0x7ccf06[_0x774026].offsetLeft - _0xf9efc3.offsetWidth - bili * 3;
      let _0x4242c6 = _0xa3fce8[_0x338eee].offsetTop - (_0x5c20fd.offsetTop + _0x5c20fd.offsetHeight) - bili;
      _0x33e4d2.style.top = _0x4242c6 + (_0x50248c - 20) / 2 + "px";
      _0x33e4d2.style.left = _0x1be975 + (_0x455865 - 20) / 2 + "px";
      _0x33e4d2.style.zIndex = "" + (5 - _0x774026);
    }
  });
  if (curDksKey !== undefined) {
    for (let _0x359f8a = 0; _0x359f8a < 4; _0x359f8a++) {
      let _0x26094b = curDksKey.steps[_0x359f8a * 4];
      let _0x58ddf1 = curDksKey.steps[_0x359f8a * 4 + 1];
      let _0x3a31fe = curDksKey.steps[_0x359f8a * 4 + 2];
      let _0x3c12c7 = curDksKey.steps[_0x359f8a * 4 + 3];
      let _0x1668b9 = _0x359f8a * 4 + 1;
      let _0x4e9f07 = _0x359f8a * 4 + 2;
      let _0x49eaa9 = _0x359f8a * 4 + 3;
      let _0x51f938 = getDksBtn(_0x359f8a * 4);
      let _0x32422c = getDksBtn(_0x1668b9);
      let _0x17bb36 = getDksBtn(_0x4e9f07);
      let _0x261e7b = getDksBtn(_0x49eaa9);
      let _0x1dfa71 = document.getElementById(_0x51f938.htmlFor);
      let _0x38d845 = document.getElementById(_0x32422c.htmlFor);
      let _0x567181 = document.getElementById(_0x17bb36.htmlFor);
      let _0x4b7162 = document.getElementById(_0x261e7b.htmlFor);
      if (_0x26094b > 0) {
        _0x1dfa71.checked = true;
        if (_0x26094b === 1) {
          _0x51f938.style.width = "20px";
        } else if (_0x26094b === 2) {
          _0x51f938.style.width = _0x58ddf1 === 2 ? _0x3a31fe === 2 ? _0x261e7b.offsetLeft - _0x51f938.offsetLeft + "px" : _0x17bb36.offsetLeft - _0x51f938.offsetLeft + "px" : _0x32422c.offsetLeft - _0x51f938.offsetLeft + "px";
        }
      } else {
        _0x1dfa71.checked = false;
        _0x51f938.style.width = "20px";
      }
      if (_0x58ddf1 === 0) {
        _0x38d845.checked = false;
        _0x32422c.style.width = "20px";
      } else if (_0x58ddf1 === 1) {
        _0x38d845.checked = true;
        _0x32422c.style.width = "20px";
      } else if (_0x58ddf1 === 2) {
        if (_0x26094b === 2) {
          _0x38d845.checked = false;
          _0x32422c.style.width = "20px";
        } else {
          _0x38d845.checked = true;
          _0x32422c.style.width = _0x3a31fe === 2 ? _0x261e7b.offsetLeft - _0x32422c.offsetLeft + "px" : _0x17bb36.offsetLeft - _0x32422c.offsetLeft + "px";
        }
      } else if (_0x58ddf1 === 3) {
        _0x38d845.checked = true;
        _0x32422c.style.width = _0x3a31fe === 2 ? _0x261e7b.offsetLeft - _0x32422c.offsetLeft + "px" : _0x17bb36.offsetLeft - _0x32422c.offsetLeft + "px";
      }
      if (_0x3a31fe === 0) {
        _0x567181.checked = false;
        _0x17bb36.style.width = "20px";
      } else if (_0x3a31fe === 1) {
        _0x567181.checked = true;
        _0x17bb36.style.width = "20px";
      } else if (_0x3a31fe === 2) {
        if (_0x58ddf1 === 2 || _0x58ddf1 === 3) {
          _0x567181.checked = false;
          _0x17bb36.style.width = "20px";
        } else {
          _0x567181.checked = true;
          _0x17bb36.style.width = _0x261e7b.offsetLeft - _0x17bb36.offsetLeft + "px";
        }
      } else if (_0x3a31fe === 3) {
        _0x567181.checked = true;
        _0x17bb36.style.width = _0x261e7b.offsetLeft - _0x17bb36.offsetLeft + "px";
      }
      _0x4b7162.checked = _0x3c12c7 > 0;
      _0x261e7b.style.width = "20px";
    }
  }
}
function initKey(_0x166ae6, _0x2f482e, _0x34270c) {
  if (_0x34270c) {
    curKey = _0x2f482e;
    recordInput.disabled = false;
    btnResetKey.disabled = false;
    btnApplyKey.disabled = false;
    document.getElementById("checkKey").querySelector("label").innerText = _0x2f482e.name.replace(/[\s\u3000]/g, "");
    let _0x5729de = findFixedKey(_0x2f482e.code);
    let _0x19ef14 = false;
    if (keymapDef.checked && recKeys.has(_0x2f482e.index)) {
      _0x5729de = recKeys.get(_0x2f482e.index);
      _0x19ef14 = true;
    }
    if (keymapFn.checked && fnKeys.has(_0x2f482e.index)) {
      _0x5729de = fnKeys.get(_0x2f482e.index);
      _0x19ef14 = true;
    }
    if (_0x5729de !== undefined) {
      let _0x1bfd3e = _0x5729de.name;
      if (_0x19ef14) {
        _0x1bfd3e = _0x5729de.code1 > 0 ? getI18n(_0x5729de.code) : _0x5729de.name;
        if (_0x5729de.code1 === 19) {
          keyManu2.checked = true;
          keyManu2.dispatchEvent(new Event("change"));
          if (_0x1bfd3e === "") {
            _0x1bfd3e = _0x5729de.name;
          }
        } else if (_0x5729de.code1 === 16) {
          keyManu3.checked = true;
          keyManu3.dispatchEvent(new Event("change"));
          _0x1bfd3e = _0x5729de.name;
        } else if (_0x5729de.code1 === 23) {
          keyManu4.checked = true;
          keyManu4.dispatchEvent(new Event("change"));
          _0x1bfd3e = _0x5729de.name;
        } else if (_0x5729de.code1 === 24) {
          if (curDevice.pid === 50023) {
            keyManu10.checked = true;
            keyManu10.dispatchEvent(new Event("change"));
            _0x1bfd3e = getI18n(_0x5729de.code);
          } else {
            keyManu1.checked = true;
            keyManu1.dispatchEvent(new Event("change"));
            _0x1bfd3e = curKey.name;
          }
        } else if (_0x5729de.code1 === 25) {
          if (curDevice.pid === 50022) {
            keyManu10.checked = true;
            keyManu10.dispatchEvent(new Event("change"));
            _0x1bfd3e = getI18n(_0x5729de.code);
          } else {
            keyManu1.checked = true;
            keyManu1.dispatchEvent(new Event("change"));
            _0x1bfd3e = curKey.name;
          }
        } else {
          keyManu1.checked = true;
          keyManu1.dispatchEvent(new Event("change"));
        }
      }
      recordInput.value = _0x1bfd3e;
    }
    keyBtn.forEach(_0x3c15f7 => {
      if (_0x3c15f7 !== _0x166ae6) {
        document.getElementById(_0x3c15f7.htmlFor).checked = false;
      }
    });
  }
}
function setKeyType(_0x3c4b53, _0x274997, _0x6d21db) {
  keyBtn.forEach(_0x253a96 => {
    document.documentElement.style.setProperty("--ukKey-color", "var(--btn-bgColor)");
    const _0x2d7d52 = _0x253a96.querySelector("[class=devKeyPanelView]");
    if (_0x2d7d52 != null) {
      _0x2d7d52.style.backgroundColor = "";
      _0x2d7d52.childNodes[0].style.color = "";
      _0x2d7d52.style.setProperty("--btn-color", "");
    }
    let _0x46420c = document.getElementById(_0x253a96.htmlFor);
    _0x46420c.checked = false;
    if (menu1.checked) {
      if (keymapDef.checked) {
        if (_0x3c4b53 === "radio" && _0x253a96.htmlFor === "KeyFn") {
          _0x46420c.type = "button";
        } else {
          _0x46420c.type = _0x3c4b53;
        }
      }
      if (keymapFn.checked) {
        let _0x372d0e = findDeviceKey(_0x253a96.htmlFor);
        if (_0x372d0e != null && fnKeyState.includes(_0x372d0e.index)) {
          _0x46420c.type = "button";
        } else {
          _0x46420c.type = _0x3c4b53;
        }
      }
    } else {
      _0x46420c.type = _0x3c4b53;
    }
    _0x253a96.querySelector("[class=devKeyTrigger]").style.display = _0x274997 ? "flex" : "none";
    _0x253a96.querySelector("[class=devKeySwitch]").style.display = _0x6d21db ? "flex" : "none";
    refreshKeyButton(findDeviceKey(document.getElementById(_0x253a96.htmlFor).id));
  });
}
function showKeyColor(_0xf11975) {
  keyBtn.forEach(_0x477319 => {
    _0x477319.querySelector("[class=devKeyBackColor]").style.display = _0xf11975 ? "flex" : "none";
  });
}
function setKeysColor() {
  if (curDevice !== undefined && curDevice !== null) {
    keyBtn.forEach(_0x33f3c3 => {
      let _0x8a8735;
      let _0x25251c = findDeviceKey(_0x33f3c3.htmlFor);
      let _0x4c77d4 = _0x33f3c3.querySelector("[class=devKeyBackColor]");
      if (lightCustom1.checked) {
        _0x8a8735 = curDevice.light.keysColor1.get(_0x25251c.index);
      }
      if (lightCustom2.checked) {
        _0x8a8735 = curDevice.light.keysColor2.get(_0x25251c.index);
      }
      if (_0x8a8735 == null) {
        _0x8a8735 = new Color();
      }
      _0x4c77d4.style.setProperty("--color", "rgba(" + _0x8a8735.r + "," + _0x8a8735.g + "," + _0x8a8735.b + ",1)");
    });
  }
}
function setKeyColor(_0x5a22da, _0x5d23d6, _0x441c0a) {
  let _0xa11d92 = new Color(_0x5a22da, _0x5d23d6, _0x441c0a);
  checkedKeys.forEach(_0x5b4b61 => {
    devSet.querySelector("[for=" + _0x5b4b61.code + "]").querySelector("[class=devKeyBackColor]").style.setProperty("--color", "rgba(" + _0xa11d92.r + "," + _0xa11d92.g + "," + _0xa11d92.b + ",1)");
    if (lightCustom1.checked) {
      curDevice.light.keysColor1.set(_0x5b4b61.index, _0xa11d92);
    }
    if (lightCustom2.checked) {
      curDevice.light.keysColor2.set(_0x5b4b61.index, _0xa11d92);
    }
  });
}
function showAlert(_0x18b3ea) {
  if (timeoutId !== undefined) {
    clearTimeout(timeoutId);
    timeoutId = undefined;
  }
  document.getElementById("alertLabel").innerText = _0x18b3ea;
  let _0x3acaa5 = document.getElementById("alertDiv");
  _0x3acaa5.style.display = "flex";
  timeoutId = setTimeout(function () {
    _0x3acaa5.style.display = "none";
  }, 2000);
}
function autoSplitContent(_0x3c2702) {
  const _0x282bd8 = Array.isArray(_0x3c2702) ? _0x3c2702 : [_0x3c2702];
  let _0x375229 = 0;
  _0x282bd8.forEach(_0x5d6301 => {
    document.querySelectorAll("[i18n=\"" + _0x5d6301 + "\"]").forEach(_0x1957b6 => {
      const _0x326c12 = getI18n(_0x5d6301);
      if (_0x326c12.includes(",") || _0x326c12.includes("，") || _0x326c12.includes(".")) {
        let _0x152a62 = [];
        if (language.value === "pl" && _0x326c12.includes(".")) {
          _0x152a62 = _0x326c12.split(".").map(_0x1ce3b4 => _0x1ce3b4.trim()).filter(_0x8915bb => _0x8915bb.length > 0);
        } else if (_0x326c12.includes(",")) {
          _0x152a62 = _0x326c12.split(",").map(_0x32415e => _0x32415e.trim()).filter(_0x2875c5 => _0x2875c5.length > 0);
        } else if (_0x326c12.includes("，")) {
          _0x152a62 = _0x326c12.split("，").map(_0x16d2d8 => _0x16d2d8.trim()).filter(_0x550d30 => _0x550d30.length > 0);
        }
        const _0x44f887 = document.createElement("ul");
        _0x44f887.style.listStyle = "auto";
        _0x152a62.forEach((_0xd544cd, _0x518e7e) => {
          const _0x11a792 = document.createElement("li");
          _0x11a792.className = "part";
          _0x11a792.innerHTML = "\n                                <span>" + _0xd544cd + (language.value === "pl" ? "." : "") + "</span>\n                            ";
          _0x44f887.appendChild(_0x11a792);
          _0x375229++;
        });
        _0x1957b6.innerHTML = "";
        _0x1957b6.appendChild(_0x44f887);
      } else {
        _0x1957b6.innerHTML = _0x326c12;
      }
    });
  });
  return _0x375229;
}
function setRecordKeyByKeyId(_0x4441d3, _0x5be6e4) {
  let _0x14f72f = new Key();
  _0x14f72f.code1 = 23;
  _0x14f72f.hidCode = 0;
  _0x14f72f.name = _0x5be6e4;
  recKeys.set(_0x4441d3, _0x14f72f);
}