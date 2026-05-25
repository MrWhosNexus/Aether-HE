let i18n = "en";
let lang = {};
async function initLanguage() {
  const _0xca51cd = await fetch("../config/language.json");
  const _0xe9c603 = await _0xca51cd.text();
  lang = JSON.parse(_0xe9c603);
  getI18nDom(document.body);
}
function getI18n(_0x150002) {
  let _0x469bc7 = lang[i18n][_0x150002] || "";
  if (curDevice && curDevice.company === "mile_varo_ultra") {
    if (i18n === "jp") {
      if (_0x150002 === "triggerMenu1") {
        _0x469bc7 = "UP トリガー";
      }
      if (_0x150002 === "triggerTip1") {
        _0x469bc7 = "UP トリガーを有効にします。";
      }
    }
    if (i18n === "en") {
      if (_0x150002 === "triggerMenu1") {
        _0x469bc7 = "UP Trigger";
      }
      if (_0x150002 === "triggerTip1") {
        _0x469bc7 = "UP Trigger dynamically actuates and resets your key based on your intention to press and release the key";
      }
    }
  }
  if (curCompany === "fengrun_machenike") {
    _0x469bc7 = _0x469bc7.replace("粉轴", "磁灰轴");
    _0x469bc7 = _0x469bc7.replace("万磁Gaming轴", "磁玉Gaming");
  }
  if (curCompany === "mile_qwerty" && _0x150002 === "calibrationStep3") {
    _0x469bc7 = _0x469bc7.replace("blue", "orange");
  }
  if (curCompany === "sanpin_glick" && i18n === "kr") {
    _0x469bc7 = _0x469bc7.replace("SOCD", "펄스탭");
  }
  return _0x469bc7;
}
function getI18nDom(_0xc3dd25) {
  if (_0xc3dd25.childElementCount === 0 || _0xc3dd25.childElementCount === 1 && _0xc3dd25.children[0].tagName === "BR") {
    if (_0xc3dd25.getAttribute("i18n")) {
      _0xc3dd25.innerText = getI18n(_0xc3dd25.getAttribute("i18n"));
    }
  } else {
    [].forEach.call(_0xc3dd25.children, _0x3551c5 => {
      getI18nDom(_0x3551c5);
    });
  }
}