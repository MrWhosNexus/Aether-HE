let isInitOther = false;
function readHidData() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    hidDevice.oninputreport = ({
      reportId: _0x11e6ad,
      data: _0x4364ff
    }) => {
      let _0x732a24 = new Uint8Array(_0x4364ff.buffer);
      if (_0x11e6ad === 1 && _0x732a24[0] === 1) {
        const _0x4b17d2 = _0x732a24.slice(5, 23);
        isPrcs = _0x4b17d2[9] === 1;
        isAnyKeyCalibration = !(~_0x4b17d2[12] & 1);
        isCustomLight = !(~_0x4b17d2[12] & 2);
        isMoreSwitch = !(~_0x4b17d2[12] & 4);
        isPollRate = !(~_0x4b17d2[12] & 8);
        isDeadBand = !(~_0x4b17d2[12] & 16);
        isMusicRhythm = !(~_0x4b17d2[12] & 32);
        isALlAnd6keySwitch = !(~_0x4b17d2[12] & 128);
        isHighPrecision = !(~_0x4b17d2[13] & 1);
        isGamePad = !(~_0x4b17d2[13] & 4);
        isRS = !(~_0x4b17d2[13] & 8);
        isRKRT = !(~_0x4b17d2[13] & 16);
        isMusicRhythmOn = _0x4b17d2[16] === 1;
        const _0x5d6f9b = _0x4b17d2[17];
        is6KeyMode = !(~_0x5d6f9b & 1);
        triMode = _0x732a24[10];
        if (isInitOther) {
          refreshPerformanceView(_0x4b17d2[15], true);
          isInitOther = false;
        }
        isInitInfo = true;
      }
      if (_0x11e6ad === 1 && _0x732a24[0] === 1) {
        const _0x5e43b8 = _0x732a24[1];
        const _0x4654e8 = _0x732a24[8];
        const _0x45bab3 = _0x732a24[9];
        if (isModeChange !== _0x5e43b8 && isModeChange !== -1) {
          showAlert(getI18n("sleepSetTip7"));
          isDeviceOut = true;
          setTimeout(() => {
            location.href = location.href;
          }, 1000);
        }
        isModeChange = _0x5e43b8;
        if (battery) {
          const _0x25618d = document.getElementById("batteryText");
          document.getElementById("triMode").innerText = triMode === 0 ? "USB" : triMode === 1 ? "2.4G" : "";
          if (_0x4654e8 === 1) {
            battery.classList.add("charge");
            battery.style.setProperty("--batery-from", 0);
            _0x25618d.innerHTML = _0x4654e8 === 1 ? getI18n("charging") : getI18n("fullyCharged");
          } else {
            const _0x1b3434 = _0x45bab3 + "%";
            battery.style.setProperty("--batery-from", _0x1b3434);
            _0x25618d.innerHTML = _0x1b3434;
            battery.classList.remove("charge");
          }
        }
      }
      if (_0x11e6ad === 1 && _0x732a24[0] === 10) {
        let _0x4ce262 = _0x732a24[4];
        let _0x657f36 = _0x732a24.slice(5, 5 + _0x4ce262);
        if (_0x657f36.length >= 4) {
          curDevice.maxLightBrightness = _0x657f36[_0x4ce262 - 1];
          curDevice.maxLightSpeed = _0x657f36[_0x4ce262 - 2];
          let _0x14acdb = Array.from(_0x657f36.slice(0, _0x4ce262 - 4));
          if (_0x14acdb.length > 0) {
            if (isMusicRhythm) {
              _0x14acdb = _0x14acdb.concat(100);
            }
            _0x14acdb = _0x14acdb.concat(10);
            const _0x5c54fd = document.getElementById("lightCustomDiv");
            const _0xd8fc0b = document.getElementById("lightModels");
            _0xd8fc0b.innerHTML = "";
            const _0x42a5f6 = document.getElementById("lightRight");
            const _0xe9af29 = document.getElementById("lightMusicView");
            for (let _0x5e639b = 0; _0x5e639b < _0x14acdb.length; _0x5e639b++) {
              let _0x166c27 = document.createElement("input");
              _0x166c27.type = "radio";
              _0x166c27.id = "lightMode" + _0x14acdb[_0x5e639b];
              _0x166c27.name = "lightRadio";
              _0x166c27.value = "" + _0x14acdb[_0x5e639b];
              _0x166c27.onchange = async function () {
                if (_0x166c27.checked) {
                  console.log("light mode:" + _0x166c27.value);
                  if (_0x166c27.value === "100") {
                    _0x42a5f6.style.display = "none";
                    _0xe9af29.style.display = "flex";
                    await setMusicRhythmState("in");
                  } else {
                    _0x42a5f6.style.display = "flex";
                    _0xe9af29.style.display = "none";
                    await setMusicRhythmState("out");
                    if (_0x166c27.value === "10") {
                      setKeyType("checkbox", false, false);
                      showKeyColor(true);
                      _0x5c54fd.style.display = "flex";
                    } else {
                      setKeyType("text", false, false);
                      showKeyColor(false);
                      _0x5c54fd.style.display = "none";
                      window.dispatchEvent(new MouseEvent("contextmenu"));
                    }
                  }
                  refreshColorView(parseInt(_0x166c27.value));
                  await setDeviceLight();
                }
              };
              let _0x5ce961 = document.createElement("label");
              _0x5ce961.classList.add("lightBox");
              let _0x54db53 = document.createElement("img");
              _0x54db53.classList.add("lightIcon");
              _0x54db53.setAttribute("src", "image/dark/icon_" + _0x166c27.id + ".png");
              let _0xfc4894 = document.createElement("span");
              _0xfc4894.setAttribute("i18n", _0x166c27.id);
              _0xfc4894.setAttribute("class", "lightMode");
              _0xfc4894.innerText = getI18n(_0x166c27.id);
              if (i18n === "tr") {
                _0xfc4894.style.height = "40px";
              }
              _0x5ce961.htmlFor = _0x166c27.id;
              let _0x34e869 = _0x14acdb[_0x5e639b] != 10 ? _0xfc4894.innerText.length * 10 || 0 : 99999;
              _0x5ce961.setAttribute("order", _0x34e869);
              _0x5ce961.setAttribute("index", _0x5e639b);
              _0x5ce961.style.order = _0x34e869;
              _0x5ce961.appendChild(_0x54db53);
              _0x5ce961.appendChild(_0xfc4894);
              _0xd8fc0b.appendChild(_0x166c27);
              _0xd8fc0b.appendChild(_0x5ce961);
            }
          }
        }
        isReadLightList = true;
      }
      if (_0x11e6ad === 1 && _0x732a24[0] === 2) {
        let _0x5d4e9e = _0x732a24[4];
        let _0x4ce0a9 = _0x732a24.slice(5, 5 + _0x5d4e9e);
        if (_0x4ce0a9.length >= 4) {
          curDevice.maxSideLightBrightness = _0x4ce0a9[_0x5d4e9e - 1];
          curDevice.maxSideLightSpeed = _0x4ce0a9[_0x5d4e9e - 2];
          let _0x140581 = Array.from(_0x4ce0a9.slice(0, _0x5d4e9e - 4));
          document.querySelector("[for=lightManu2]").style.display = _0x140581.length > 0 ? "flex" : "none";
          if (_0x140581.length > 0) {
            const _0x209e3b = document.getElementById("sideLightModels");
            _0x209e3b.innerHTML = "";
            for (let _0x4e42b7 = 0; _0x4e42b7 < _0x140581.length; _0x4e42b7++) {
              if (_0x140581[_0x4e42b7] === 5) {
                continue;
              }
              let _0x5128d7 = document.createElement("input");
              _0x5128d7.type = "radio";
              _0x5128d7.id = "sideLightMode" + _0x140581[_0x4e42b7];
              _0x5128d7.name = "sideLightRadio";
              _0x5128d7.value = "" + _0x140581[_0x4e42b7];
              _0x5128d7.onchange = async function () {
                if (_0x5128d7.checked) {
                  console.log("light mode:" + _0x5128d7.value);
                  setKeyType("text", false, false);
                  showKeyColor(false);
                  window.dispatchEvent(new MouseEvent("contextmenu"));
                  refreshColorView(parseInt(_0x5128d7.value));
                  await setDeviceLight();
                }
              };
              let _0x11db0a = document.createElement("label");
              _0x11db0a.classList.add("lightBox");
              let _0x18cd73 = document.createElement("img");
              _0x18cd73.classList.add("lightIcon");
              _0x18cd73.setAttribute("src", "image/dark/icon_" + (_0x5128d7.id ? _0x5128d7.id.replace("sideLightMode", "lightMode") : "close") + ".png");
              let _0x26d4d1 = document.createElement("span");
              _0x26d4d1.setAttribute("i18n", _0x5128d7.id);
              _0x26d4d1.setAttribute("class", "lightMode");
              _0x26d4d1.innerText = getI18n(_0x5128d7.id);
              if (i18n === "tr") {
                _0x26d4d1.style.height = "40px";
              }
              _0x11db0a.htmlFor = _0x5128d7.id;
              let _0x522500 = _0x140581[_0x4e42b7] != 10 ? _0x26d4d1.innerText.length * 10 || 0 : 99999;
              _0x11db0a.setAttribute("order", _0x522500);
              _0x11db0a.setAttribute("index", _0x4e42b7);
              _0x11db0a.style.order = _0x522500;
              _0x11db0a.appendChild(_0x18cd73);
              _0x11db0a.appendChild(_0x26d4d1);
              _0x209e3b.appendChild(_0x5128d7);
              _0x209e3b.appendChild(_0x11db0a);
            }
          }
        }
        isReadLightList = true;
      }
      if (_0x11e6ad === 1 && _0x732a24[0] === 7) {
        let _0x123f99 = _0x732a24[4];
        let _0x252b3b = _0x732a24.slice(5, 5 + _0x123f99);
        let _0x3c2703 = _0x252b3b[9];
        if (_0x3c2703 >= 6) {
          _0x3c2703 = 0;
        }
        if (_0x252b3b.length >= 12) {
          curDevice.light.mode = _0x252b3b[0];
          curDevice.light.brightness = _0x252b3b[1];
          curDevice.light.speed = _0x252b3b[2];
          curDevice.light.foregroundColor.r = _0x252b3b[3];
          curDevice.light.foregroundColor.g = _0x252b3b[4];
          curDevice.light.foregroundColor.b = _0x252b3b[5];
          curDevice.light.backgroundColor.r = _0x252b3b[6];
          curDevice.light.backgroundColor.g = _0x252b3b[7];
          curDevice.light.backgroundColor.b = _0x252b3b[8];
          curDevice.light.direction = _0x3c2703;
          curDevice.light.fullColor = _0x252b3b[10];
          curDevice.light.power = _0x252b3b[11];
        }
        isInitLightValue = true;
      }
      if (_0x11e6ad === 1 && _0x732a24[0] === 8) {
        let _0x1ec587 = _0x732a24[4];
        let _0x2913a3 = _0x732a24.slice(5, 5 + _0x1ec587);
        let _0x222fb2 = _0x2913a3[9];
        if (_0x222fb2 >= 6) {
          _0x222fb2 = 0;
        }
        if (_0x2913a3.length >= 12) {
          curDevice.sideLight.mode = _0x2913a3[0];
          curDevice.sideLight.brightness = _0x2913a3[1];
          curDevice.sideLight.speed = _0x2913a3[2];
          curDevice.sideLight.foregroundColor.r = _0x2913a3[3];
          curDevice.sideLight.foregroundColor.g = _0x2913a3[4];
          curDevice.sideLight.foregroundColor.b = _0x2913a3[5];
          curDevice.sideLight.backgroundColor.r = _0x2913a3[6];
          curDevice.sideLight.backgroundColor.g = _0x2913a3[7];
          curDevice.sideLight.backgroundColor.b = _0x2913a3[8];
          curDevice.sideLight.direction = _0x222fb2;
          curDevice.sideLight.fullColor = _0x2913a3[10];
          curDevice.sideLight.power = _0x2913a3[11];
        }
        isInitLightValue = true;
      }
      if (_0x11e6ad === 1 && _0x732a24[0] === 9) {
        if (_0x732a24[1] === 128 || _0x732a24[1] === 129) {
          let _0x4dfb36 = _0x732a24[2] << 8 | _0x732a24[3];
          let _0x63ab34 = _0x732a24[4];
          let _0x303c1c = _0x732a24.slice(5, 5 + _0x63ab34);
          for (let _0x90822a = 0; _0x90822a < _0x303c1c.length / 3; _0x90822a++) {
            let _0x221bb3 = _0x4dfb36 * 18 + _0x90822a;
            let _0xc9d7bd = new Color();
            _0xc9d7bd.r = _0x303c1c[_0x90822a * 3];
            _0xc9d7bd.g = _0x303c1c[_0x90822a * 3 + 1];
            _0xc9d7bd.b = _0x303c1c[_0x90822a * 3 + 2];
            if (_0x732a24[1] === 128) {
              curDevice.light.keysColor1.set(_0x221bb3, _0xc9d7bd);
            }
            if (_0x732a24[1] === 129) {
              curDevice.light.keysColor2.set(_0x221bb3, _0xc9d7bd);
            }
          }
          if (_0x4dfb36 === 7) {
            isInitCustomLightValue = true;
          }
        } else {
          if (_0x732a24[1] === 0) {
            lightCustom1.checked ||= true;
          }
          if (_0x732a24[1] === 1) {
            lightCustom2.checked ||= true;
          }
        }
      }
      if (_0x11e6ad === 1 && _0x732a24[0] === 14) {
        let _0x4bad12 = _0x732a24[4];
        if (_0x4bad12 > 0 && _0x732a24.length > _0x4bad12 + 5) {
          let _0x3672af = 0;
          let _0x15ca6a = 0;
          for (let _0x43e6d2 = 0; _0x43e6d2 < _0x4bad12; _0x43e6d2++) {
            let _0x38a49b = _0x732a24[_0x43e6d2 + 5];
            _0x15ca6a = _0x43e6d2;
            for (let _0x5f58ca = 0; _0x5f58ca < 6; _0x5f58ca++) {
              _0x3672af = _0x5f58ca;
              let _0x4528e3 = _0x3672af * 22 + _0x15ca6a;
              if ((_0x38a49b >> _0x5f58ca & 1) === 1) {
                fnKeyState.push(_0x4528e3);
              }
            }
          }
        }
        isInitFnKeyState = true;
      }
      if (_0x11e6ad === 1 && _0x732a24[0] === 20 && _0x732a24[5] === 1) {
        let _0x4966a7 = document.getElementById("alertMessage");
        let _0x385546 = document.getElementById("btnAlertOk");
        _0x4966a7.value = "all";
        _0x385546.dispatchEvent(new Event("click"));
      }
      if (_0x11e6ad === 1 && _0x732a24[0] === 20) {
        if (_0x732a24[1] === 2) {
          const _0x474510 = _0x732a24[8] << 8 | _0x732a24[9];
          const _0xbc37a5 = _0x732a24[10] << 8 | _0x732a24[11];
          document.getElementById("lightSleep").value = _0x474510;
          document.getElementById("keyboardSleep").value = Number(_0xbc37a5) / 60;
        } else {
          showAlert(getI18n("success"));
        }
      }
      if (_0x11e6ad === 1 && _0x732a24[0] === 24 && (_0x732a24[1] === 128 || _0x732a24[1] === 130)) {
        let _0x46d2af = _0x732a24[2] << 8 | _0x732a24[3];
        let _0x1ccf60 = _0x732a24[4];
        let _0x578536 = Math.floor(_0x1ccf60 / 4);
        for (let _0x324f66 = 0; _0x324f66 < _0x578536; _0x324f66++) {
          let _0x56c929 = _0x46d2af * 14 + _0x324f66;
          let _0x1646f8 = curDevice.keys.find(_0x3c958e => _0x3c958e.index === _0x56c929);
          if (_0x1646f8 != null) {
            let _0x5d0bc2 = findFixedKey(_0x1646f8.code);
            if (_0x5d0bc2 != null) {
              let _0x3605b5 = _0x732a24[_0x324f66 * 4 + 5];
              let _0x4942dc = _0x732a24[_0x324f66 * 4 + 6];
              let _0x4a6c39 = _0x732a24[_0x324f66 * 4 + 7];
              let _0xb54aea = _0x732a24[_0x324f66 * 4 + 8];
              if (_0x3605b5 !== _0x5d0bc2.code1 || _0x4942dc !== _0x5d0bc2.hidCode || _0x4a6c39 !== _0x5d0bc2.code3 || _0xb54aea !== _0x5d0bc2.code4) {
                if (_0x3605b5 === 16) {
                  let _0x38aa26 = _0x4a6c39;
                  if (_0x38aa26 >= 0 && _0x38aa26 < readMacroList.length) {
                    let _0x5455b0 = readMacroList[_0x38aa26];
                    let _0x21c213 = macros.find(_0x2cc24a => _0x2cc24a.index === _0x5455b0.index);
                    if (_0x21c213 != null) {
                      recMacros.set(_0x56c929, _0x5455b0);
                      let _0x4387f7 = new Key();
                      _0x4387f7.code1 = 16;
                      _0x4387f7.hidCode = _0x4942dc;
                      _0x4387f7.code3 = _0x38aa26;
                      _0x4387f7.name = _0x21c213.name;
                      if (_0x732a24[1] === 128) {
                        recKeys.set(_0x56c929, _0x4387f7);
                        cacheRecKeys.set(_0x56c929, _0x4387f7);
                      }
                      if (_0x732a24[1] === 130) {
                        fnKeys.set(_0x56c929, _0x4387f7);
                        cacheFnKeys.set(_0x56c929, _0x4387f7);
                      }
                    }
                  }
                } else if (_0x3605b5 === 23) {
                  let _0x3a13bf = advKeys.find(_0x62fe95 => _0x62fe95.index === _0x4942dc);
                  if (_0x3a13bf != null) {
                    let _0x224bcf = new Key();
                    _0x224bcf.name = _0x3a13bf.name;
                    _0x224bcf.code1 = _0x3605b5;
                    _0x224bcf.hidCode = _0x4942dc;
                    _0x224bcf.code3 = _0x4a6c39;
                    _0x224bcf.code4 = _0xb54aea;
                    if (_0x732a24[1] === 128) {
                      recKeys.set(_0x56c929, _0x224bcf);
                      cacheRecKeys.set(_0x56c929, _0x224bcf);
                    }
                    if (_0x732a24[1] === 130) {
                      fnKeys.set(_0x56c929, _0x224bcf);
                      cacheFnKeys.set(_0x56c929, _0x224bcf);
                    }
                  }
                } else if (_0x3605b5 === 18) {
                  let _0x3a2201 = findFixedKeyByHid(_0x3605b5, _0x4a6c39, {
                    key: "code3",
                    value: _0x4942dc
                  });
                  if (_0x3a2201 != null) {
                    _0x3a2201.code1 = _0x3605b5;
                    _0x3a2201.hidCode = _0x4a6c39;
                    _0x3a2201.code3 = _0x4942dc;
                    _0x3a2201.code4 = _0xb54aea;
                    if (_0x732a24[1] === 128) {
                      recKeys.set(_0x56c929, _0x3a2201);
                      cacheRecKeys.set(_0x56c929, _0x3a2201);
                    }
                    if (_0x732a24[1] === 130) {
                      fnKeys.set(_0x56c929, _0x3a2201);
                      cacheFnKeys.set(_0x56c929, _0x3a2201);
                    }
                  }
                } else if (_0x3605b5 === 19) {
                  let _0x310b01 = findFixedKeyByHidCode(_0x4942dc);
                  let _0x2ba7f0 = findFixedKeyByHidCode(_0x4a6c39);
                  let _0x303869 = findFixedKeyByHidCode(_0xb54aea);
                  let _0x1bae92 = _0x310b01.name + " + " + _0x2ba7f0.name;
                  if (_0x303869 !== undefined) {
                    _0x1bae92 += " + " + _0x303869.name;
                  }
                  let _0x272bb4 = new Key();
                  _0x272bb4.name = _0x1bae92;
                  _0x272bb4.code1 = _0x3605b5;
                  _0x272bb4.hidCode = _0x4942dc;
                  _0x272bb4.code3 = _0x4a6c39;
                  _0x272bb4.code4 = _0xb54aea;
                  if (_0x732a24[1] === 128) {
                    recKeys.set(_0x56c929, _0x272bb4);
                    cacheRecKeys.set(_0x56c929, _0x272bb4);
                  }
                  if (_0x732a24[1] === 130) {
                    fnKeys.set(_0x56c929, _0x272bb4);
                    cacheFnKeys.set(_0x56c929, _0x272bb4);
                  }
                } else if (_0x3605b5 === 24 || _0x3605b5 === 25) {
                  const _0x33ce74 = findGamPadKey(_0x3605b5, _0x4942dc);
                  let _0x3ff4be = new Key();
                  _0x3ff4be.code = _0x33ce74.code;
                  _0x3ff4be.code1 = _0x33ce74.code1;
                  _0x3ff4be.hidCode = _0x33ce74.hidCode;
                  _0x3ff4be.code3 = _0x33ce74.code3;
                  _0x3ff4be.code4 = _0x33ce74.code4;
                  if (_0x732a24[1] === 128) {
                    recKeys.set(_0x56c929, _0x3ff4be);
                    cacheRecKeys.set(_0x56c929, _0x3ff4be);
                  }
                  if (_0x732a24[1] === 130) {
                    fnKeys.set(_0x56c929, _0x3ff4be);
                    cacheFnKeys.set(_0x56c929, _0x3ff4be);
                  }
                } else if (_0x3605b5 !== 0 || _0x4942dc !== 0) {
                  let _0x25f760 = findFixedKeyByHid(_0x3605b5, _0x4942dc);
                  if (_0x25f760 != null) {
                    _0x25f760.code1 = _0x3605b5;
                    _0x25f760.hidCode = _0x4942dc;
                    _0x25f760.code3 = _0x4a6c39;
                    _0x25f760.code4 = _0xb54aea;
                    console.log(_0x25f760.name, _0x56c929);
                    if (_0x732a24[1] === 128) {
                      recKeys.set(_0x56c929, _0x25f760);
                      cacheRecKeys.set(_0x56c929, _0x25f760);
                    }
                    if (_0x732a24[1] === 130) {
                      fnKeys.set(_0x56c929, _0x25f760);
                      cacheFnKeys.set(_0x56c929, _0x25f760);
                    }
                  }
                }
              }
            }
          }
        }
        if (_0x46d2af === 9) {
          isInitKeyValue = true;
        }
      }
      if (_0x11e6ad === 1 && _0x732a24[0] === 25) {
        if (_0x732a24[1] >= 128) {
          let _0x187d48 = _0x732a24[2] << 8 | _0x732a24[3];
          let _0x295198 = _0x732a24[1] - 128;
          let _0x16b3eb = _0x732a24.slice(5, 13)[3];
          let _0x42703b = Math.floor(_0x16b3eb / 4);
          let _0x2d26ff = macros.find(_0x2162cb => _0x2162cb.index === _0x295198);
          if (_0x16b3eb > 0 && _0x16b3eb <= 58) {
            let _0x3cb194 = _0x732a24.slice(5, 13);
            let _0x28395a = (_0x3cb194[0] & 128) > 0;
            _0x295198 = _0x3cb194[0] & 127;
            let _0x44226d = _0x3cb194[1];
            let _0x58e10d = _0x3cb194[4] << 8 | _0x3cb194[5];
            let _0x26ea05 = new MacroKey();
            _0x26ea05.index = _0x295198;
            _0x26ea05.type = _0x44226d;
            _0x26ea05.count = _0x58e10d;
            readMacroList.push(_0x26ea05);
            if (_0x28395a) {
              isInitMacroValue = true;
              return;
            }
            let _0xd939db = _0x732a24.slice(13, 13 + _0x16b3eb);
            if (_0x187d48 === 0) {
              _0x2d26ff = new Macro();
              _0x2d26ff.index = _0x295198;
              _0x2d26ff.name = "Macro" + (_0x2d26ff.index + 1);
              macros.push(_0x2d26ff);
            }
            if (_0x2d26ff !== undefined) {
              for (let _0x1c4a5d = 0; _0x1c4a5d < _0x42703b; _0x1c4a5d++) {
                let _0x2e43bd = _0xd939db[_0x1c4a5d * 4];
                let _0x4c4acd = _0xd939db[_0x1c4a5d * 4 + 1];
                let _0x149d6e = _0xd939db[_0x1c4a5d * 4 + 2] << 8 | _0xd939db[_0x1c4a5d * 4 + 3];
                let _0x3c636c = new Step();
                _0x3c636c.type = _0x4c4acd & 15;
                _0x3c636c.state = _0x4c4acd >> 4 & 15;
                _0x3c636c.delay = _0x149d6e;
                if (_0x3c636c.type === 0) {
                  _0x3c636c.key = findFixedKeyByHid(0, _0x2e43bd);
                }
                if (_0x3c636c.type === 1) {
                  if (_0x2e43bd === 0) {
                    _0x3c636c.key = findFixedKey("MouseLeft");
                  }
                  if (_0x2e43bd === 1) {
                    _0x3c636c.key = findFixedKey("MouseMiddle");
                  }
                  if (_0x2e43bd === 2) {
                    _0x3c636c.key = findFixedKey("MouseRight");
                  }
                }
                if (_0x3c636c.state === 1) {
                  _0x3c636c.tag = getStepTag(_0x2d26ff);
                } else {
                  _0x3c636c.tag = findStepTag(_0x2d26ff, _0x3c636c.key.code);
                }
                _0x2d26ff.steps.push(_0x3c636c);
              }
              let _0x1352bd = macros.indexOf(_0x2d26ff);
              if (_0x1352bd >= 0 && _0x1352bd < macros.length) {
                macros.splice(_0x1352bd, 1, _0x2d26ff);
              }
            }
          }
          if (_0x187d48 >= 4) {
            if (_0x2d26ff != null) {
              let _0x514f36 = 0;
              for (let _0x5076aa = 0; _0x5076aa < _0x2d26ff.steps.length; _0x5076aa++) {
                let _0x4d8bf6 = _0x2d26ff.steps[_0x5076aa].delay;
                _0x2d26ff.steps[_0x5076aa].delay = _0x514f36;
                _0x514f36 = _0x4d8bf6;
              }
              let _0x55d675 = macros.indexOf(_0x2d26ff);
              if (_0x55d675 >= 0 && _0x55d675 < macros.length) {
                macros.splice(_0x55d675, 1, _0x2d26ff);
              }
            }
            isInitMacroValue = true;
          }
        } else {
          isMacroWriteFinish = true;
        }
      }
      if (_0x11e6ad === 1 && _0x732a24[0] === 33 && _0x732a24[5] === 1 && curDevice) {
        _0x732a24[6];
        _0x732a24[7];
        const _0x39a346 = _0x732a24[9] << 8 | _0x732a24[8];
        const _0x2f2723 = curDevice.maxTriggerTravel * curDevice.triggerUnit * 100 * 0.62;
        const _0x425698 = _0x39a346 / curDevice.maxTriggerTravel * _0x2f2723;
        document.getElementById("testjindu").style.height = _0x425698 + "px";
      }
      if (_0x11e6ad === 1 && _0x732a24[0] === 33 && _0x732a24[5] === 4) {
        let _0x38470b = _0x732a24[7] === 0 ? 10 : _0x732a24[7];
        if (curDevice !== undefined) {
          curDevice.maxTriggerTravel = _0x732a24[9] << 8 | _0x732a24[6];
          let _0x12047b = isHighPrecision ? 1000 : 100;
          curDevice.triggerUnit = _0x38470b / _0x12047b;
          let _0xe849bb = _0x732a24[10];
          if (_0xe849bb === 0 && curDevice.triggerUnit === 0.04) {
            _0xe849bb = curDevice.company === "suoai" ? 2 : 3;
          }
          if (_0xe849bb === 0 && curDevice.triggerUnit === 0.1) {
            _0xe849bb = 1;
          }
          if (_0xe849bb === 0 && curDevice.triggerUnit === 0.08) {
            _0xe849bb = 1;
          }
          curDevice.minTriggerTravel = _0xe849bb;
          isMaxTriggerRead = true;
        }
      }
      if (_0x11e6ad === 1 && _0x732a24[0] === 33 && _0x732a24[5] === 5) {
        triggerData.push(_0x732a24);
        isTriggerRead = true;
      }
      if (_0x11e6ad === 1 && _0x732a24[0] === 33 && _0x732a24[5] === 9) {
        if (_0x732a24[6] === 1 || _0x732a24[6] === 2 || _0x732a24[6] === 4 || _0x732a24[6] === 8) {
          pollRate = _0x732a24[6];
          isReadPollRate = true;
        }
      }
      if (_0x11e6ad === 1 && _0x732a24[0] === 33 && (_0x732a24[5] === 8 || _0x732a24[5] === 15)) {
        if (_0x732a24[6] === 0) {
          if (isChangeCalibration) {
            showAlert(getI18n("calibrationStop"));
          } else {
            showAlert(getI18n("alertCalibrationSuccess"));
          }
          isCalibrationing = false;
          document.getElementById("calibrationTip")?.remove();
          let _0x3b21a7 = document.getElementById("reviseKeys");
          _0x3b21a7.setAttribute("i18n", "calibrationStart");
          _0x3b21a7.innerText = getI18n("calibrationStart");
          if (curCompany === "kzzi") {
            window.dispatchEvent(new MouseEvent("contextmenu"));
          }
        }
        if (_0x732a24[6] === 1) {
          let _0xc32a7a = [];
          let _0x3d4395 = _0x732a24.slice(7, 29);
          for (let _0x5eb31f = 0; _0x5eb31f < _0x3d4395.length; _0x5eb31f++) {
            let _0x4934ff = _0x3d4395[_0x5eb31f];
            for (let _0xcc5b7f = 0; _0xcc5b7f < 6; _0xcc5b7f++) {
              let _0x1d4e7c = _0xcc5b7f * 22 + _0x5eb31f;
              if ((_0x4934ff >> _0xcc5b7f & 1) === 1) {
                _0xc32a7a.push(_0x1d4e7c);
              }
            }
          }
          console.log(_0xc32a7a);
          refreshReviseKeys(_0xc32a7a);
        }
        if (_0x732a24[6] === 2 || _0x732a24[6] === 4) {
          showAlert(getI18n("alertCalibrationFail"));
          isCalibrationing = false;
          document.getElementById("calibrationTip")?.remove();
          let _0x20ca1e = document.getElementById("reviseKeys");
          _0x20ca1e.setAttribute("i18n", "calibrationStart");
          _0x20ca1e.innerText = getI18n("calibrationStart");
          if (curCompany === "kzzi") {
            window.dispatchEvent(new MouseEvent("contextmenu"));
          }
        }
      }
      if (_0x11e6ad === 1 && _0x732a24[0] === 33 && _0x732a24[5] === 17) {
        const _0x34a9fb = document.getElementById("triggerPower");
        _0x34a9fb.checked = false;
        _0x34a9fb.dispatchEvent(new Event("change"));
        window.dispatchEvent(new MouseEvent("contextmenu"));
        readTriggerData().then(_0x263513 => {
          keyBtn.forEach(_0xd02f61 => {
            let _0x540dbf = findDeviceKey(_0xd02f61.htmlFor);
            if (document.getElementById(_0xd02f61.htmlFor).checked) {
              let _0x229ef9 = Math.floor(curDevice.maxTriggerTravel / 2);
              initTriggerSlider(curDevice.maxTriggerTravel, curDevice.triggerUnit, _0x229ef9);
            }
            refreshKeyButton(_0x540dbf);
          });
        });
      }
      if (_0x11e6ad === 1 && _0x732a24[0] === 34 && _0x732a24[1] === 128) {
        let _0xda9c61 = _0x732a24[2] << 8 | _0x732a24[3];
        if (_0x732a24[5] === 0) {
          if (_0xda9c61 === 39) {
            isInitAdvancedKeys = true;
          }
          return;
        }
        if (_0x732a24[5] === 1 || _0x732a24[5] === 2 || _0x732a24[5] === 3 || _0x732a24[5] === 4 || _0x732a24[5] === 5) {
          let _0x50ea9d = new AdvancedKey();
          _0x50ea9d.index = _0xda9c61;
          if (_0x732a24[5] === 1) {
            _0x50ea9d.type = "DKS";
            _0x50ea9d.route1 = _0x732a24[6];
            _0x50ea9d.route2 = _0x732a24[7];
            _0x50ea9d.route3 = _0x732a24[8];
            _0x50ea9d.route4 = _0x732a24[9];
            for (let _0x3c05fa = 0; _0x3c05fa < 4; _0x3c05fa++) {
              let _0xfb9861 = _0x732a24[_0x3c05fa * 8 + 10];
              let _0x5b0de4 = _0x732a24[_0x3c05fa * 8 + 11];
              let _0x544b54 = _0x732a24[_0x3c05fa * 8 + 12];
              let _0xd730cc = _0x732a24[_0x3c05fa * 8 + 13];
              let _0x3d2d25 = new Key();
              if (_0xfb9861 !== 0 || _0x5b0de4 !== 0) {
                _0x3d2d25 = findFixedKeyByHid(_0xfb9861, _0x5b0de4);
              }
              _0x3d2d25.code1 = _0xfb9861;
              _0x3d2d25.hidCode = _0x5b0de4;
              _0x3d2d25.code3 = _0x544b54;
              _0x3d2d25.code4 = _0xd730cc;
              _0x50ea9d.keys.splice(_0x3c05fa, 1, _0x3d2d25);
              _0x50ea9d.steps.splice(_0x3c05fa * 4, 1, _0x732a24[_0x3c05fa * 8 + 14]);
              _0x50ea9d.steps.splice(_0x3c05fa * 4 + 1, 1, _0x732a24[_0x3c05fa * 8 + 15]);
              _0x50ea9d.steps.splice(_0x3c05fa * 4 + 2, 1, _0x732a24[_0x3c05fa * 8 + 16]);
              _0x50ea9d.steps.splice(_0x3c05fa * 4 + 3, 1, _0x732a24[_0x3c05fa * 8 + 17]);
            }
          } else if (_0x732a24[5] === 2) {
            _0x50ea9d.type = "MT";
            let _0x494e0d = new Key();
            let _0x5a9783 = new Key();
            let _0x10e0a3 = _0x732a24[6];
            let _0x4f9ec8 = _0x732a24[7];
            let _0x303627 = _0x732a24[8];
            let _0x5a0cff = _0x732a24[9];
            if (_0x10e0a3 !== 0 || _0x4f9ec8 !== 0) {
              _0x494e0d = findFixedKeyByHid(_0x10e0a3, _0x4f9ec8);
            }
            _0x494e0d.code1 = _0x10e0a3;
            _0x494e0d.hidCode = _0x4f9ec8;
            _0x494e0d.code3 = _0x303627;
            _0x494e0d.code4 = _0x5a0cff;
            _0x10e0a3 = _0x732a24[10];
            _0x4f9ec8 = _0x732a24[11];
            _0x303627 = _0x732a24[12];
            _0x5a0cff = _0x732a24[13];
            if (_0x10e0a3 !== 0 || _0x4f9ec8 !== 0) {
              _0x5a9783 = findFixedKeyByHid(_0x10e0a3, _0x4f9ec8);
            }
            _0x5a9783.code1 = _0x10e0a3;
            _0x5a9783.hidCode = _0x4f9ec8;
            _0x5a9783.code3 = _0x303627;
            _0x5a9783.code4 = _0x5a0cff;
            _0x50ea9d.keys.splice(0, 1, _0x5a9783);
            _0x50ea9d.keys.splice(1, 1, _0x494e0d);
            _0x50ea9d.duration = _0x732a24[14];
          } else if (_0x732a24[5] === 3) {
            _0x50ea9d.type = "TGL";
            let _0x2748d3 = _0x732a24[6];
            let _0x1ec4e1 = _0x732a24[7];
            let _0x1861af = _0x732a24[8];
            let _0x5cbf03 = _0x732a24[9];
            let _0x5b907d = new Key();
            if (_0x2748d3 !== 0 || _0x1ec4e1 !== 0) {
              _0x5b907d = findFixedKeyByHid(_0x2748d3, _0x1ec4e1);
            }
            _0x5b907d.code1 = _0x2748d3;
            _0x5b907d.hidCode = _0x1ec4e1;
            _0x5b907d.code3 = _0x1861af;
            _0x5b907d.code4 = _0x5cbf03;
            _0x50ea9d.keys.splice(0, 1, _0x5b907d);
          } else if (_0x732a24[5] === 4) {
            _0x50ea9d.type = "RS";
            let _0xdab13d = new Key();
            _0xdab13d.code1 = _0x732a24[6];
            _0xdab13d.hidCode = _0x732a24[7];
            _0xdab13d.code3 = _0x732a24[8];
            _0xdab13d.code4 = _0x732a24[9];
            _0xdab13d = Object.assign({}, _0xdab13d, findDeviceKey(_0xdab13d.hidCode, "hidCode"));
            let _0x364973 = new Key();
            _0x364973.code1 = _0x732a24[12];
            _0x364973.hidCode = _0x732a24[13];
            _0x364973.code3 = _0x732a24[14];
            _0x364973.code4 = _0x732a24[15];
            _0x364973 = Object.assign({}, _0x364973, findDeviceKey(_0x364973.hidCode, "hidCode"));
            _0x50ea9d.keys.splice(0, 2, _0xdab13d, _0x364973);
          } else if (_0x732a24[5] === 5) {
            _0x50ea9d.type = "RKRT";
            let _0x2bf381 = new Key();
            _0x2bf381.code1 = _0x732a24[6];
            _0x2bf381.hidCode = _0x732a24[7];
            _0x2bf381.code3 = _0x732a24[8];
            _0x2bf381.code4 = _0x732a24[9];
            _0x2bf381 = Object.assign({}, _0x2bf381, findDeviceKey(_0x2bf381.hidCode, "hidCode"));
            let _0x490656 = new Key();
            _0x490656.code1 = _0x732a24[12];
            _0x490656.hidCode = _0x732a24[13];
            _0x490656.code3 = _0x732a24[14];
            _0x490656.code4 = _0x732a24[15];
            _0x490656 = Object.assign({}, _0x490656, findDeviceKey(_0x490656.hidCode, "hidCode"));
            _0x50ea9d.keys.splice(0, 2, _0x2bf381, _0x490656);
          }
          _0x50ea9d.name = _0x50ea9d.index + 1 + "#" + _0x50ea9d.type;
          if (_0x50ea9d.type === "RS") {
            let _0x1cb3b1 = _0x50ea9d.keys.map(_0x183644 => _0x183644.name).join(" ");
            _0x50ea9d.name += "->" + _0x1cb3b1;
          }
          advKeys.push(_0x50ea9d);
        }
        if (_0xda9c61 === 39) {
          isInitAdvancedKeys = true;
        }
      }
      if (_0x11e6ad === 1 && _0x732a24[0] === 36) {
        if (_0x732a24[1] === 2) {
          let _0x44e6c0 = _0x732a24[4];
          let _0x11f3ca = _0x732a24.slice(5, 5 + _0x44e6c0);
          if (_0x11f3ca.length >= 6) {
            let _0x4c4dde = _0x11f3ca[0] === 1;
            let _0x3f6f0e = _0x11f3ca[4];
            let _0x2b2b32 = _0x11f3ca[5];
            refreshPrcsValue(_0x4c4dde, _0x3f6f0e, _0x2b2b32);
          }
        }
        if (_0x732a24[1] === 1) {
          let _0x1f7b62 = _0x732a24[2] << 8 | _0x732a24[3];
          let _0x57c4a7 = _0x732a24.slice(5, 45);
          for (let _0xef8aa2 = 0; _0xef8aa2 < 10; _0xef8aa2++) {
            let _0x27e5e0 = _0x57c4a7[_0xef8aa2 * 4];
            let _0x17896f = _0x57c4a7[_0xef8aa2 * 4 + 1];
            let _0x470e4c = _0x57c4a7[_0xef8aa2 * 4 + 2];
            let _0x38f480 = _0x57c4a7[_0xef8aa2 * 4 + 3];
            if ((_0x27e5e0 !== 7 || _0x17896f !== 255 || _0x470e4c !== 255 || _0x38f480 !== 255) && _0x27e5e0 !== 0) {
              let _0x2f1110 = findFixedKeyByHid(0, _0x470e4c);
              let _0x961a33 = findFixedKeyByHid(0, _0x38f480);
              if (_0x2f1110 == null) {
                _0x2f1110 = new Key();
              }
              if (_0x961a33 == null) {
                _0x961a33 = new Key();
              }
              let _0x176f94 = new Prcs();
              _0x176f94.index = getPrcsIndex();
              _0x176f94.name = "PRCS" + (_0x176f94.index + 1);
              _0x176f94.model = _0x17896f;
              _0x176f94.key1 = _0x2f1110;
              _0x176f94.key2 = _0x961a33;
              prcses.push(_0x176f94);
            }
          }
          if (_0x1f7b62 === 1) {
            isInitPrcsData = true;
          }
        }
      }
      if (_0x11e6ad === 1 && _0x732a24[0] === 37) {
        if (_0x732a24[1] === 0) {
          let _0x2232ae = _0x732a24[4];
          let _0x3a80a9 = _0x732a24.slice(5, 5 + _0x2232ae);
          switchList = [];
          if (_0x3a80a9.length >= 2) {
            let _0x498295 = _0x3a80a9[0] << 8 | _0x3a80a9[1];
            for (let _0x528793 = 0; _0x528793 < _0x498295; _0x528793++) {
              let _0x52043f = _0x3a80a9[2 + _0x528793];
              const _0x568588 = switchDefault.find(_0x5cce89 => _0x5cce89.index === _0x52043f);
              if (_0x568588 != null) {
                switchList.push(_0x568588);
              }
            }
          }
          isInitSwitchList = true;
        } else if (_0x732a24[1] === 2) {
          let _0x329be0 = _0x732a24[2] << 8 | _0x732a24[3];
          console.log("page: " + _0x329be0);
          let _0x959146 = _0x732a24[4];
          let _0x2b567b = _0x732a24.slice(5, 5 + _0x959146);
          for (let _0x3c6f4b = 0; _0x3c6f4b < _0x959146; _0x3c6f4b++) {
            let _0x2ddcea = _0x329be0 * 58 + _0x3c6f4b;
            let _0x3d0294 = curDevice.keys.find(_0x3c840d => _0x3c840d.index === _0x2ddcea);
            if (_0x3d0294 != null) {
              _0x3d0294.switch = _0x2b567b[_0x3c6f4b];
            }
          }
          if (_0x329be0 === 2) {
            isInitKeySwitch = true;
          }
        }
      }
      if (_0x11e6ad === 1 && _0x732a24[0] === 38 && _0x732a24[1] === 0) {
        let _0x261dea = _0x732a24[2] << 8 | _0x732a24[3];
        console.log("page: " + _0x261dea);
        let _0x147bbb = _0x732a24[4];
        let _0x3ff6e3 = 29;
        let _0xd37efa = _0x732a24.slice(5, 5 + _0x147bbb);
        for (let _0x2ab15e = 0; _0x2ab15e < _0x3ff6e3; _0x2ab15e++) {
          let _0x35c8d2 = _0x261dea * _0x3ff6e3 + _0x2ab15e;
          let _0xaf5fb9 = curDevice.keys.find(_0x25265d => _0x25265d.index === _0x35c8d2);
          if (_0xaf5fb9 != null) {
            _0xaf5fb9.trigger.deadbandTop = _0xd37efa[_0x2ab15e * 2];
            _0xaf5fb9.trigger.deadbandBottom = _0xd37efa[_0x2ab15e * 2 + 1];
          }
        }
        if (_0x261dea === 4) {
          isInitDeadBand = true;
        }
      }
    };
  }
}
let isInitInfo = false;
async function initInfo() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    isInitInfo = false;
    waitCount = 0;
    let _0x289bad = new ArrayBuffer(63);
    let _0x49b33a = new Uint8Array(_0x289bad);
    _0x49b33a[0] = 1;
    await hidDevice.sendReport(1, _0x49b33a);
    while (!isInitInfo && waitCount < 10) {
      await new Promise(_0x1a992e => setTimeout(_0x1a992e, 0));
      waitCount++;
    }
    isInitInfo = false;
    waitCount = 0;
  }
}
async function heartbeat() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    let _0x2f22da = new ArrayBuffer(63);
    let _0xfc6db4 = new Uint8Array(_0x2f22da);
    _0xfc6db4[0] = 1;
    await hidDevice.sendReport(1, _0xfc6db4);
  }
}
async function setMusicRhythmState(_0x1a84b5) {
  let _0x25fc5f = new ArrayBuffer(63);
  let _0x2510ed = new Uint8Array(_0x25fc5f);
  _0x2510ed[0] = 23;
  _0x2510ed[4] = 2;
  if (_0x1a84b5 === "in") {
    _0x2510ed[5] = 1;
    _0x2510ed[6] = 1;
  } else {
    _0x2510ed[5] = 0;
    _0x2510ed[6] = 0;
  }
  await hidDevice.sendReport(1, _0x2510ed);
}
async function resetTrigger() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    let _0x465373 = new ArrayBuffer(63);
    let _0x1ee108 = new Uint8Array(_0x465373);
    _0x1ee108[0] = 33;
    _0x1ee108[4] = 24;
    _0x1ee108[5] = 6;
    await hidDevice.sendReport(1, _0x1ee108);
  }
}
function openTriggerTest() {
  if (curDevice) {
    let _0x2e1b27 = new ArrayBuffer(22);
    let _0x9aca48 = new Uint8Array(_0x2e1b27);
    curDevice.keys.forEach(_0x46779c => {
      let _0x3c3e47 = Math.floor(_0x46779c.index / 22);
      let _0x14076f = _0x46779c.index % 22;
      _0x9aca48[_0x14076f] += 1 << _0x3c3e47;
    });
    let _0x583cde = new ArrayBuffer(63);
    let _0x4a061a = new Uint8Array(_0x583cde);
    _0x4a061a[0] = 33;
    _0x4a061a[4] = 24;
    _0x4a061a[5] = 2;
    _0x4a061a.set(_0x9aca48, 6);
    hidDevice.sendReport(1, _0x4a061a);
  }
}
function closeTriggerTest() {
  if (curDevice) {
    let _0x2bd0f7 = new ArrayBuffer(63);
    let _0x336498 = new Uint8Array(_0x2bd0f7);
    _0x336498[0] = 33;
    _0x336498[4] = 24;
    _0x336498[5] = 3;
    hidDevice.sendReport(1, _0x336498);
  }
}
let waitCount = 0;
let isMaxTriggerRead = false;
async function readMaxTriggerTravel() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    isTriggerRead = false;
    waitCount = 0;
    let _0x1250de = new ArrayBuffer(63);
    let _0x4c34d9 = new Uint8Array(_0x1250de);
    _0x4c34d9[0] = 33;
    _0x4c34d9[4] = 24;
    _0x4c34d9[5] = 4;
    await hidDevice.sendReport(1, _0x4c34d9);
    while (!isMaxTriggerRead && waitCount < 10) {
      await new Promise(_0x3399ad => setTimeout(_0x3399ad, 0));
      waitCount++;
    }
    isMaxTriggerRead = false;
    waitCount = 0;
  }
}
let triggerData = [];
let isTriggerRead = false;
async function readTriggerData() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    triggerData = [];
    isTriggerRead = false;
    waitCount = 0;
    for (const _0x502329 of curDevice.keys) {
      let _0x2d9200 = _0x502329.index;
      let _0x2d4b9e = Math.floor(_0x2d9200 / 22);
      let _0x50fec2 = _0x2d9200 % 22;
      let _0x10620d = new ArrayBuffer(63);
      let _0x55bbd1 = new Uint8Array(_0x10620d);
      _0x55bbd1[0] = 33;
      _0x55bbd1[4] = 24;
      _0x55bbd1[5] = 5;
      _0x55bbd1[6] = _0x2d4b9e;
      _0x55bbd1[7] = _0x50fec2;
      await hidDevice.sendReport(1, _0x55bbd1);
      while (!isTriggerRead && waitCount < 10) {
        await new Promise(_0x3a3977 => setTimeout(_0x3a3977, 0));
        waitCount++;
      }
      isTriggerRead = false;
      waitCount = 0;
    }
    if (triggerData.length > 0) {
      for (let _0x55f325 = 0; _0x55f325 < triggerData.length; _0x55f325++) {
        let _0xd6255e = triggerData[_0x55f325];
        if (_0x55f325 < curDevice.keys.length && _0xd6255e !== undefined && _0xd6255e.length >= 63) {
          curDevice.keys[_0x55f325].trigger.mode = _0xd6255e[6];
          curDevice.keys[_0x55f325].trigger.travel = _0xd6255e[11] << 8 | _0xd6255e[7];
          curDevice.keys[_0x55f325].trigger.interval1 = _0xd6255e[13] << 8 | _0xd6255e[9];
          curDevice.keys[_0x55f325].trigger.interval2 = _0xd6255e[14] << 8 | _0xd6255e[10];
        }
      }
    }
  }
}
let isReadPollRate = false;
async function readPollRate() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    isReadPollRate = false;
    waitCount = 0;
    let _0x206bd9 = new ArrayBuffer(63);
    let _0x561ed7 = new Uint8Array(_0x206bd9);
    _0x561ed7[0] = 33;
    _0x561ed7[4] = 1;
    _0x561ed7[5] = 9;
    await hidDevice.sendReport(1, _0x561ed7);
    while (!isReadPollRate && waitCount < 10) {
      await new Promise(_0x2ad042 => setTimeout(_0x2ad042, 0));
      waitCount++;
    }
    isReadPollRate = false;
    waitCount = 0;
  }
}
let isInitKeyValue = false;
async function initKeyValue(_0x471fae) {
  if (curDevice !== undefined && hidDevice !== undefined) {
    isInitKeyValue = false;
    waitCount = 0;
    let _0x1abcc1 = 128;
    if (_0x471fae === "default") {
      _0x1abcc1 = 128;
    }
    if (_0x471fae === "fn") {
      _0x1abcc1 = 130;
    }
    let _0x1773cd = new ArrayBuffer(63);
    let _0x5768ed = new Uint8Array(_0x1773cd);
    _0x5768ed[0] = 24;
    _0x5768ed[1] = _0x1abcc1;
    await hidDevice.sendReport(1, _0x5768ed);
    while (!isInitKeyValue && waitCount < 10) {
      await new Promise(_0x3ecf1a => setTimeout(_0x3ecf1a, 0));
      waitCount++;
    }
    isInitKeyValue = false;
    waitCount = 0;
  }
}
async function setKeyValue() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    let _0x57828e = new ArrayBuffer(528);
    let _0x269025 = new Uint8Array(_0x57828e);
    curDevice.keys.forEach(function (_0x3f8397) {
      let _0xd34b38 = _0x3f8397.index;
      let _0x514347 = _0x3f8397.code === "KeyFn" ? 1 : 0;
      let _0x1ae230 = _0x3f8397.hidCode;
      let _0x3f7a97 = 0;
      let _0x372a73 = 0;
      if (_0x3f8397.code1 !== undefined && _0x3f8397.code1 !== null) {
        _0x514347 = _0x3f8397.code1;
        _0x3f7a97 = _0x3f8397.code3 === undefined || _0x3f8397.code3 === null ? 0 : _0x3f8397.code3;
        _0x372a73 = _0x3f8397.code4 === undefined || _0x3f8397.code4 === null ? 0 : _0x3f8397.code4;
      }
      if (_0x3f8397.name === "M1" || _0x3f8397.name === "M2" || _0x3f8397.name === "M3" || _0x3f8397.name === "M4") {
        const _0x5cdef4 = findFixedKey(_0x3f8397.code);
        if (_0x5cdef4 != null) {
          _0x514347 = _0x5cdef4.code1;
          _0x1ae230 = _0x5cdef4.hidCode;
          _0x3f7a97 = _0x5cdef4.code3;
        }
      }
      if (recKeys.has(_0xd34b38)) {
        let _0x16aca0 = recKeys.get(_0xd34b38);
        _0x514347 = _0x16aca0.code1;
        _0x1ae230 = _0x16aca0.hidCode;
        _0x3f7a97 = _0x16aca0.code3;
        _0x372a73 = _0x16aca0.code4;
        if (_0x514347 === 16) {
          _0x269025[_0xd34b38 * 4] = _0x514347;
          _0x269025[_0xd34b38 * 4 + 1] = _0x3f8397.hidCode;
          _0x269025[_0xd34b38 * 4 + 2] = usedMacro.has(_0xd34b38) ? usedMacro.get(_0xd34b38) : _0x3f7a97;
          _0x269025[_0xd34b38 * 4 + 3] = 0;
        } else if (_0x514347 === 18) {
          _0x269025[_0xd34b38 * 4] = _0x514347;
          _0x269025[_0xd34b38 * 4 + 1] = _0x3f7a97;
          _0x269025[_0xd34b38 * 4 + 2] = _0x1ae230;
          _0x269025[_0xd34b38 * 4 + 3] = _0x372a73;
        } else {
          _0x269025[_0xd34b38 * 4] = _0x514347;
          _0x269025[_0xd34b38 * 4 + 1] = _0x1ae230;
          _0x269025[_0xd34b38 * 4 + 2] = _0x3f7a97;
          _0x269025[_0xd34b38 * 4 + 3] = _0x372a73;
        }
      } else {
        _0x269025[_0xd34b38 * 4] = _0x514347;
        _0x269025[_0xd34b38 * 4 + 1] = _0x1ae230;
        _0x269025[_0xd34b38 * 4 + 2] = _0x3f7a97;
        _0x269025[_0xd34b38 * 4 + 3] = _0x372a73;
      }
    });
    if (hasRotaryKnob && curDevice.pid !== 50021) {
      _0x269025[64] = 7;
      _0x269025[65] = 18;
      _0x269025[68] = 7;
      _0x269025[69] = 17;
      _0x269025[72] = 7;
      _0x269025[73] = 16;
      _0x269025[76] = 2;
      _0x269025[77] = 2;
      _0x269025[80] = 3;
      _0x269025[81] = 1;
      _0x269025[84] = 3;
      _0x269025[85] = 0;
    }
    let _0x24fadb = 56;
    let _0x24a22a = _0x57828e.byteLength % _0x24fadb;
    let _0x20c75f = Math.floor(_0x57828e.byteLength / _0x24fadb);
    if (_0x24a22a > 0) {
      _0x20c75f += 1;
    }
    console.log("改键包数：", _0x20c75f);
    cacheRecKeys = recKeys;
    for (let _0x4609cc = 0; _0x4609cc < _0x20c75f; _0x4609cc++) {
      _0x57828e = new ArrayBuffer(63);
      let _0x3498c1 = new Uint8Array(_0x57828e);
      _0x3498c1[0] = 24;
      _0x3498c1[1] = 0;
      _0x3498c1[2] = _0x4609cc >> 8 & 255;
      _0x3498c1[3] = _0x4609cc & 255;
      if (_0x24a22a > 0 && _0x4609cc === _0x20c75f - 1) {
        _0x3498c1[4] = _0x24a22a;
        _0x3498c1.set(_0x269025.subarray(_0x4609cc * _0x24fadb, _0x4609cc * _0x24fadb + _0x24a22a), 5);
      } else {
        _0x3498c1[4] = _0x24fadb;
        _0x3498c1.set(_0x269025.subarray(_0x4609cc * _0x24fadb, _0x4609cc * _0x24fadb + _0x24fadb), 5);
      }
      await hidDevice.sendReport(1, _0x3498c1);
    }
  }
}
async function setFnKeyValue() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    let _0x384fb3 = new ArrayBuffer(528);
    let _0x3ece60 = new Uint8Array(_0x384fb3);
    curDevice.keys.forEach(function (_0x1b867f) {
      let _0x47759b = _0x1b867f.index;
      let _0x4681d0 = 0;
      let _0x3ddc3d = 0;
      let _0x476458 = 0;
      let _0x91960 = 0;
      if (fnKeys.has(_0x47759b)) {
        let _0x563c58 = fnKeys.get(_0x47759b);
        _0x4681d0 = _0x563c58.code1;
        _0x3ddc3d = _0x563c58.hidCode;
        _0x476458 = _0x563c58.code3;
        _0x91960 = _0x563c58.code4;
        if (_0x4681d0 === 16) {
          _0x3ece60[_0x47759b * 4] = _0x4681d0;
          _0x3ece60[_0x47759b * 4 + 1] = _0x1b867f.hidCode;
          _0x3ece60[_0x47759b * 4 + 2] = usedMacro.has(_0x47759b) ? usedMacro.get(_0x47759b) : 0;
          _0x3ece60[_0x47759b * 4 + 3] = 0;
        } else if (_0x4681d0 === 18) {
          _0x3ece60[_0x47759b * 4] = _0x4681d0;
          _0x3ece60[_0x47759b * 4 + 1] = _0x476458;
          _0x3ece60[_0x47759b * 4 + 2] = _0x3ddc3d;
          _0x3ece60[_0x47759b * 4 + 3] = _0x91960;
        } else {
          _0x3ece60[_0x47759b * 4] = _0x4681d0;
          _0x3ece60[_0x47759b * 4 + 1] = _0x3ddc3d;
          _0x3ece60[_0x47759b * 4 + 2] = _0x476458;
          _0x3ece60[_0x47759b * 4 + 3] = _0x91960;
        }
      } else {
        _0x3ece60[_0x47759b * 4] = _0x4681d0;
        _0x3ece60[_0x47759b * 4 + 1] = _0x3ddc3d;
        _0x3ece60[_0x47759b * 4 + 2] = _0x476458;
        _0x3ece60[_0x47759b * 4 + 3] = _0x91960;
      }
    });
    let _0x336a9d = 56;
    let _0x4fdb01 = _0x384fb3.byteLength % _0x336a9d;
    let _0xa9c8e8 = Math.floor(_0x384fb3.byteLength / _0x336a9d);
    if (_0x4fdb01 > 0) {
      _0xa9c8e8 += 1;
    }
    console.log("改键包数：", _0xa9c8e8);
    cacheFnKeys = recKeys;
    for (let _0x32c4cd = 0; _0x32c4cd < _0xa9c8e8; _0x32c4cd++) {
      _0x384fb3 = new ArrayBuffer(63);
      let _0x5ef65b = new Uint8Array(_0x384fb3);
      _0x5ef65b[0] = 24;
      _0x5ef65b[1] = 2;
      _0x5ef65b[2] = _0x32c4cd >> 8 & 255;
      _0x5ef65b[3] = _0x32c4cd & 255;
      if (_0x4fdb01 > 0 && _0x32c4cd === _0xa9c8e8 - 1) {
        _0x5ef65b[4] = _0x4fdb01;
        _0x5ef65b.set(_0x3ece60.subarray(_0x32c4cd * _0x336a9d, _0x32c4cd * _0x336a9d + _0x4fdb01), 5);
      } else {
        _0x5ef65b[4] = _0x336a9d;
        _0x5ef65b.set(_0x3ece60.subarray(_0x32c4cd * _0x336a9d, _0x32c4cd * _0x336a9d + _0x336a9d), 5);
      }
      await hidDevice.sendReport(1, _0x5ef65b);
    }
  }
}
let isInitFnKeyState = false;
async function initFnKeyState() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    isInitFnKeyState = false;
    waitCount = 0;
    let _0x2a8730 = new ArrayBuffer(63);
    let _0xcd4e97 = new Uint8Array(_0x2a8730);
    _0xcd4e97[0] = 14;
    await hidDevice.sendReport(1, _0xcd4e97);
    while (!isInitFnKeyState && waitCount < 10) {
      await new Promise(_0x4b3b84 => setTimeout(_0x4b3b84, 0));
      waitCount++;
    }
    isInitFnKeyState = false;
    waitCount = 0;
  }
}
let readMacroList = [];
let isInitMacroValue = false;
async function initMacroValue() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    isInitMacroValue = false;
    waitCount = 0;
    readMacroList = [];
    for (let _0x4824b9 = 128; _0x4824b9 < 138; _0x4824b9++) {
      let _0x2c56fc = new ArrayBuffer(63);
      let _0x26d4f2 = new Uint8Array(_0x2c56fc);
      _0x26d4f2[0] = 25;
      _0x26d4f2[1] = _0x4824b9;
      await hidDevice.sendReport(1, _0x26d4f2);
      while (!isInitMacroValue && waitCount < 10) {
        await new Promise(_0x472a66 => setTimeout(_0x472a66, 0));
        waitCount++;
      }
      isInitMacroValue = false;
      waitCount = 0;
    }
  }
}
let isMacroWriteFinish = false;
async function setMacroValue() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    isMacroWriteFinish = false;
    waitCount = 0;
    usedMacro = new Map();
    usedMacroIndex = [];
    for (let _0x402820 = 0; _0x402820 < 10; _0x402820++) {
      let _0x385150 = new ArrayBuffer(256);
      let _0x348b9c = new Uint8Array(_0x385150);
      let _0x2e45df = _0x387b7b(_0x402820);
      if (_0x2e45df != null) {
        let _0x165e0a = _0x2e45df[0];
        let _0x77ad47 = _0x2e45df[1];
        if (_0x77ad47 != null) {
          let _0x446960 = macros.find(_0x56b126 => _0x56b126.index === _0x77ad47.index);
          if (_0x446960 != null) {
            let _0x577661 = _0x446960.index;
            _0x577661 += (usedMacroIndex.includes(_0x446960.index) ? 1 : 0) << 7;
            _0x348b9c[0] = _0x577661;
            _0x348b9c[1] = _0x77ad47.type;
            _0x348b9c[3] = _0x446960.steps.length * 4;
            _0x348b9c[4] = _0x77ad47.count >> 8 & 255;
            _0x348b9c[5] = _0x77ad47.count & 255;
            for (let _0x36bf31 = 0; _0x36bf31 < _0x446960.steps.length; _0x36bf31++) {
              let _0x38d563;
              let _0x48859c = _0x446960.steps[_0x36bf31];
              let _0x553425 = _0x48859c.state << 4 | _0x48859c.type;
              let _0x3e6c7d = 0;
              if (_0x36bf31 < _0x446960.steps.length - 1) {
                _0x38d563 = _0x446960.steps[_0x36bf31 + 1];
                _0x3e6c7d = _0x38d563.delay;
              }
              _0x348b9c[_0x36bf31 * 4 + 8] = _0x48859c.key.hidCode;
              _0x348b9c[_0x36bf31 * 4 + 9] = _0x553425;
              _0x348b9c[_0x36bf31 * 4 + 10] = _0x3e6c7d >> 8 & 255;
              _0x348b9c[_0x36bf31 * 4 + 11] = _0x3e6c7d & 255;
            }
            usedMacro.set(_0x165e0a, _0x402820);
            if (!usedMacroIndex.includes(_0x446960.index)) {
              usedMacroIndex.push(_0x446960.index);
            }
          }
        }
      }
      let _0x1d5dd9 = 58;
      let _0x2d0838 = _0x385150.byteLength % _0x1d5dd9;
      let _0x5717bc = Math.floor(_0x385150.byteLength / _0x1d5dd9);
      if (_0x2d0838 > 0) {
        _0x5717bc += 1;
      }
      console.log("宏命令包数：", _0x5717bc);
      for (let _0x5baf7 = 0; _0x5baf7 < _0x5717bc; _0x5baf7++) {
        _0x385150 = new ArrayBuffer(63);
        let _0x51d78f = new Uint8Array(_0x385150);
        _0x51d78f[0] = 25;
        _0x51d78f[1] = _0x402820;
        _0x51d78f[2] = _0x5baf7 >> 8 & 255;
        _0x51d78f[3] = _0x5baf7 & 255;
        if (_0x2d0838 > 0 && _0x5baf7 === _0x5717bc - 1) {
          _0x51d78f[4] = _0x2d0838;
          _0x51d78f.set(_0x348b9c.subarray(_0x5baf7 * _0x1d5dd9, _0x5baf7 * _0x1d5dd9 + _0x2d0838), 5);
        } else {
          _0x51d78f[4] = _0x1d5dd9;
          _0x51d78f.set(_0x348b9c.subarray(_0x5baf7 * _0x1d5dd9, (_0x5baf7 + 1) * _0x1d5dd9), 5);
        }
        await hidDevice.sendReport(1, _0x51d78f);
        while (!isMacroWriteFinish && waitCount < 10) {
          await new Promise(_0x144532 => setTimeout(_0x144532, 0));
          waitCount++;
        }
        isMacroWriteFinish = false;
        waitCount = 0;
      }
    }
    function _0x387b7b(_0x5e5f95) {
      let _0x3fc7e9 = Array.from(recMacros);
      if (_0x5e5f95 >= 0 && _0x5e5f95 < _0x3fc7e9.length) {
        return _0x3fc7e9[_0x5e5f95];
      }
    }
  }
}
let isReadLightList = false;
async function readLightList() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    isReadLightList = false;
    waitCount = 0;
    let _0x407da6 = new ArrayBuffer(63);
    let _0x115e42 = new Uint8Array(_0x407da6);
    _0x115e42[0] = 10;
    await hidDevice.sendReport(1, _0x115e42);
    while (!isReadLightList && waitCount < 10) {
      await new Promise(_0x2f0d58 => setTimeout(_0x2f0d58, 1));
      waitCount++;
    }
    isReadLightList = false;
    waitCount = 0;
  }
}
async function readSideLightList() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    isReadLightList = false;
    waitCount = 0;
    let _0x20e7b0 = new ArrayBuffer(63);
    let _0x1bdae8 = new Uint8Array(_0x20e7b0);
    _0x1bdae8[0] = 2;
    await hidDevice.sendReport(1, _0x1bdae8);
    while (!isReadLightList && waitCount < 10) {
      await new Promise(_0x24e8a3 => setTimeout(_0x24e8a3, 1));
      waitCount++;
    }
    isReadLightList = false;
    waitCount = 0;
  }
}
let isInitLightValue = false;
async function initLightValue() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    isInitLightValue = false;
    waitCount = 0;
    let _0x2be1dc = new ArrayBuffer(63);
    let _0x3377e6 = new Uint8Array(_0x2be1dc);
    _0x3377e6[0] = 7;
    _0x3377e6[1] = 1;
    await hidDevice.sendReport(1, _0x3377e6);
    while (!isInitLightValue && waitCount < 10) {
      await new Promise(_0xd73139 => setTimeout(_0xd73139, 1));
      waitCount++;
    }
    isInitLightValue = false;
    waitCount = 0;
  }
}
async function initSideLightValue() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    isInitLightValue = false;
    waitCount = 0;
    let _0x4e6fa9 = new ArrayBuffer(63);
    let _0x15ea0c = new Uint8Array(_0x4e6fa9);
    _0x15ea0c[0] = 8;
    _0x15ea0c[1] = 1;
    await hidDevice.sendReport(1, _0x15ea0c);
    while (!isInitLightValue && waitCount < 10) {
      await new Promise(_0x54ee02 => setTimeout(_0x54ee02, 1));
      waitCount++;
    }
    isInitLightValue = false;
    waitCount = 0;
  }
}
async function setLightValue(_0x5afa19, _0x12c011) {
  if (curDevice !== undefined && hidDevice !== undefined) {
    let _0x1fa85a = new ArrayBuffer(63);
    let _0x4a030b = new Uint8Array(_0x1fa85a);
    _0x4a030b[0] = _0x12c011 ? 8 : 7;
    _0x4a030b[1] = 0;
    _0x4a030b[2] = 0;
    _0x4a030b[3] = 0;
    _0x4a030b[4] = 14;
    _0x4a030b[5] = _0x5afa19.mode;
    _0x4a030b[6] = _0x5afa19.brightness;
    _0x4a030b[7] = _0x5afa19.speed;
    _0x4a030b[8] = _0x5afa19.foregroundColor.r;
    _0x4a030b[9] = _0x5afa19.foregroundColor.g;
    _0x4a030b[10] = _0x5afa19.foregroundColor.b;
    _0x4a030b[11] = _0x5afa19.backgroundColor.r;
    _0x4a030b[12] = _0x5afa19.backgroundColor.g;
    _0x4a030b[13] = _0x5afa19.backgroundColor.b;
    _0x4a030b[14] = _0x5afa19.direction;
    _0x4a030b[15] = _0x5afa19.fullColor;
    _0x4a030b[16] = _0x5afa19.power;
    await hidDevice.sendReport(1, _0x4a030b);
  }
}
async function initCustomNumber() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    let _0x29904a = new ArrayBuffer(63);
    let _0x221e3f = new Uint8Array(_0x29904a);
    _0x221e3f[0] = 9;
    _0x221e3f[1] = 32;
    await hidDevice.sendReport(1, _0x221e3f);
  }
}
let isInitCustomLightValue = false;
async function initCustomLightValue(_0x3d0fbb) {
  if (curDevice !== undefined && hidDevice !== undefined) {
    isInitCustomLightValue = false;
    waitCount = 0;
    let _0x56be67 = new ArrayBuffer(63);
    let _0x32dc24 = new Uint8Array(_0x56be67);
    _0x32dc24[0] = 9;
    _0x32dc24[1] = _0x3d0fbb === 0 ? 128 : 129;
    await hidDevice.sendReport(1, _0x32dc24);
    while (!isInitCustomLightValue && waitCount < 10) {
      await new Promise(_0x1bd4c6 => setTimeout(_0x1bd4c6, 1));
      waitCount++;
    }
    isInitCustomLightValue = false;
    waitCount = 0;
  }
}
async function setCustomLight(_0x5089b5, _0x1b3fe9) {
  let _0x28525d = new ArrayBuffer(396);
  let _0x37122a = new Uint8Array(_0x28525d);
  curDevice.keys.forEach(_0x34e063 => {
    if (_0x1b3fe9 === 0) {
      if (_0x5089b5.keysColor1.has(_0x34e063.index)) {
        let _0x578e9d = _0x5089b5.keysColor1.get(_0x34e063.index);
        _0x37122a[_0x34e063.index * 3] = _0x578e9d.r;
        _0x37122a[_0x34e063.index * 3 + 1] = _0x578e9d.g;
        _0x37122a[_0x34e063.index * 3 + 2] = _0x578e9d.b;
      }
    } else if (_0x5089b5.keysColor2.has(_0x34e063.index)) {
      let _0x13e0b1 = _0x5089b5.keysColor2.get(_0x34e063.index);
      _0x37122a[_0x34e063.index * 3] = _0x13e0b1.r;
      _0x37122a[_0x34e063.index * 3 + 1] = _0x13e0b1.g;
      _0x37122a[_0x34e063.index * 3 + 2] = _0x13e0b1.b;
    }
  });
  let _0x3eeaff = 54;
  let _0x2a62b0 = Math.floor(_0x37122a.length / _0x3eeaff);
  let _0x263ffe = _0x28525d.byteLength % _0x3eeaff;
  if (_0x263ffe > 0) {
    _0x2a62b0 += 1;
  }
  for (let _0x5d7305 = 0; _0x5d7305 < _0x2a62b0; _0x5d7305++) {
    _0x28525d = new ArrayBuffer(63);
    let _0x163fcf = new Uint8Array(_0x28525d);
    _0x163fcf[0] = 9;
    _0x163fcf[1] = _0x1b3fe9;
    _0x163fcf[2] = _0x5d7305 >> 8 & 255;
    _0x163fcf[3] = _0x5d7305 & 255;
    if (_0x263ffe > 0 && _0x5d7305 === _0x2a62b0 - 1) {
      _0x163fcf[4] = _0x263ffe;
      _0x163fcf.set(_0x37122a.subarray(_0x5d7305 * _0x3eeaff, _0x5d7305 * _0x3eeaff + _0x263ffe), 5);
    } else {
      _0x163fcf[4] = _0x3eeaff;
      _0x163fcf.set(_0x37122a.subarray(_0x5d7305 * _0x3eeaff, (_0x5d7305 + 1) * _0x3eeaff), 5);
    }
    await hidDevice.sendReport(1, _0x163fcf);
    await sleep(5);
  }
}
async function setPerformanceValue(_0x1d6ec3, _0x391774) {
  if (curDevice !== undefined && hidDevice !== undefined) {
    let _0x2c88ce = _0x1d6ec3 & 1;
    let _0x7035c5 = _0x1d6ec3 >> 1 & 1;
    let _0x170d2a = _0x1d6ec3 >> 2 & 1;
    let _0x2bfaca = _0x1d6ec3 >> 3 & 1;
    let _0x1421be = new ArrayBuffer(63);
    let _0xd37ee7 = new Uint8Array(_0x1421be);
    _0xd37ee7[0] = 20;
    _0xd37ee7[4] = 1;
    _0xd37ee7[12] = _0x2c88ce;
    _0xd37ee7[13] = _0x7035c5;
    _0xd37ee7[14] = _0x170d2a;
    _0xd37ee7[15] = _0x2bfaca;
    _0xd37ee7[18] = _0x391774 ? 1 : 0;
    await hidDevice.sendReport(1, _0xd37ee7);
  }
}
async function resetKeyboard() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    let _0xa63765 = new ArrayBuffer(63);
    let _0x481800 = new Uint8Array(_0xa63765);
    _0x481800[0] = 20;
    _0x481800[4] = 1;
    _0x481800[5] = 1;
    await hidDevice.sendReport(1, _0x481800);
  }
}
function setGamePadMode(_0x17223f) {
  if (curDevice && hidDevice) {
    let _0x20a9cc = new ArrayBuffer(63);
    let _0x5d0931 = new Uint8Array(_0x20a9cc);
    _0x5d0931[0] = 20;
    _0x5d0931[1] = 3;
    _0x5d0931[4] = 1;
    _0x5d0931[5] = _0x17223f;
    hidDevice.sendReport(1, _0x5d0931);
  }
}
function getSleepTimer() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    let _0x9aed14 = new ArrayBuffer(6);
    let _0x3f0f2 = new Uint8Array(_0x9aed14);
    _0x3f0f2[0] = 20;
    _0x3f0f2[1] = 2;
    hidDevice.sendReport(1, _0x3f0f2);
  }
}
function setSleepTimer(_0x2210a7, _0x41c426) {
  if (curDevice !== undefined && hidDevice !== undefined) {
    let _0x56b5fc = new ArrayBuffer(63);
    let _0x8ed922 = new Uint8Array(_0x56b5fc);
    const _0x50b61e = _0x2210a7 >> 8 & 255;
    const _0x5c5ef7 = _0x2210a7 & 255;
    const _0x105bce = _0x41c426 >> 8 & 255;
    const _0x286fb7 = _0x41c426 & 255;
    _0x8ed922[0] = 20;
    _0x8ed922[1] = 1;
    _0x8ed922[8] = _0x50b61e;
    _0x8ed922[9] = _0x5c5ef7;
    _0x8ed922[10] = _0x105bce;
    _0x8ed922[11] = _0x286fb7;
    hidDevice.sendReport(1, _0x8ed922);
  }
}
async function setAnyTriggerValue(_0x107265, _0x4b9e63 = checkedKeys) {
  if (curDevice !== undefined && hidDevice !== undefined && _0x4b9e63 !== undefined) {
    let _0x42bc2c = 0;
    let _0x44f60f = 0;
    let _0x2efde0 = 0;
    let _0x1ba475 = new ArrayBuffer(31);
    let _0x451314 = new Uint8Array(_0x1ba475);
    _0x451314[0] = _0x107265;
    _0x4b9e63.forEach(_0x86d213 => {
      let _0x8fb0b = _0x86d213.index;
      let _0x3ac003 = Math.floor(_0x8fb0b / 22);
      _0x451314[_0x8fb0b % 22 + 1] += 1 << _0x3ac003;
      _0x42bc2c = _0x86d213.trigger.travel;
      _0x44f60f = _0x86d213.trigger.interval1;
      _0x2efde0 = _0x86d213.trigger.interval2;
    });
    _0x451314[23] = _0x42bc2c & 255;
    _0x451314[24] = _0x42bc2c & 255;
    _0x451314[25] = _0x44f60f & 255;
    _0x451314[26] = _0x2efde0 & 255;
    _0x451314[27] = _0x42bc2c >> 8 & 255;
    _0x451314[28] = _0x42bc2c >> 8 & 255;
    _0x451314[29] = _0x44f60f >> 8 & 255;
    _0x451314[30] = _0x2efde0 >> 8 & 255;
    let _0x40361f = new ArrayBuffer(63);
    let _0xc4e908 = new Uint8Array(_0x40361f);
    _0xc4e908[0] = 33;
    _0xc4e908[4] = 24;
    _0xc4e908.set(_0x451314, 5);
    await hidDevice.sendReport(1, _0xc4e908);
  }
}
async function setAllTriggerValue(_0x29c618) {
  if (curDevice !== undefined && hidDevice !== undefined) {
    let _0x138e11 = [];
    for (let [_0x179456, _0x1d305b] of _0x29c618) {
      let _0x90a8f9 = _0x138e11.find(_0x340377 => _0x340377.value.mode === _0x1d305b.mode && _0x340377.value.travel === _0x1d305b.travel && _0x340377.value.interval1 === _0x1d305b.interval1 && _0x340377.value.interval2 === _0x1d305b.interval2);
      if (_0x90a8f9 != null) {
        _0x90a8f9.indexs.push(_0x179456);
      } else {
        _0x90a8f9 = {};
        _0x90a8f9.indexs = [];
        _0x90a8f9.indexs.push(_0x179456);
        _0x90a8f9.value = _0x1d305b;
        _0x138e11.push(_0x90a8f9);
      }
    }
    for (let _0x2d5271 of _0x138e11) {
      let _0x16b1c6 = _0x2d5271.indexs.map(_0x314053 => ({
        index: _0x314053,
        trigger: _0x29c618.get(_0x314053)
      }));
      await setAnyTriggerValue(_0x2d5271.value.mode, _0x16b1c6);
    }
    console.log(_0x138e11);
  }
}
async function reviseKey() {
  if (curDevice !== undefined && hidDevice !== undefined && curKey !== undefined) {
    let _0x171140 = curKey.index;
    let _0x3fd5e0 = Math.floor(_0x171140 / 22);
    let _0x2d58cb = _0x171140 % 22;
    let _0x518e43 = new ArrayBuffer(63);
    let _0x12f9f1 = new Uint8Array(_0x518e43);
    _0x12f9f1[0] = 33;
    _0x12f9f1[4] = 24;
    _0x12f9f1[5] = 7;
    _0x12f9f1[6] = _0x3fd5e0;
    _0x12f9f1[7] = _0x2d58cb;
    await hidDevice.sendReport(1, _0x12f9f1);
  }
}
async function setPollRate() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    let _0x35923e = new ArrayBuffer(63);
    let _0x4bb5f3 = new Uint8Array(_0x35923e);
    _0x4bb5f3[0] = 33;
    _0x4bb5f3[5] = 9;
    _0x4bb5f3[6] = 1;
    _0x4bb5f3[7] = pollRate;
    await hidDevice.sendReport(1, _0x4bb5f3);
  }
}
async function reviseKeys(_0x4cd35b, _0x4f0668) {
  if (curDevice !== undefined && hidDevice !== undefined) {
    let _0x38fefb = new ArrayBuffer(63);
    let _0x4f770c = new Uint8Array(_0x38fefb);
    _0x4f770c[0] = 33;
    _0x4f770c[4] = 24;
    _0x4f770c[5] = _0x4cd35b;
    _0x4f770c[6] = _0x4f0668;
    await hidDevice.sendReport(1, _0x4f770c);
  }
}
let isInitAdvancedKeys = false;
async function initAdvancedKeys() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    isInitAdvancedKeys = false;
    waitCount = 0;
    let _0x47eea3 = new ArrayBuffer(63);
    let _0x7deea = new Uint8Array(_0x47eea3);
    _0x7deea[0] = 34;
    _0x7deea[1] = 128;
    await hidDevice.sendReport(1, _0x7deea);
    while (!isInitAdvancedKeys && waitCount < 10) {
      await new Promise(_0x2bfe46 => setTimeout(_0x2bfe46, 0));
      waitCount++;
    }
    isInitAdvancedKeys = false;
    waitCount = 0;
  }
}
async function setAdvancedKeys() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    for (let _0x243199 = 0; _0x243199 < 40; _0x243199++) {
      let _0x4328e5 = new ArrayBuffer(63);
      let _0x1c6058 = new Uint8Array(_0x4328e5);
      _0x1c6058[0] = 34;
      _0x1c6058[1] = _0x243199;
      _0x1c6058[4] = 50;
      let _0x40bf38 = advKeys.find(_0x366b51 => _0x366b51.index === _0x243199);
      if (_0x40bf38 != null) {
        let _0x219f86 = 0;
        if (_0x40bf38.type === "DKS") {
          _0x219f86 = 1;
        }
        if (_0x40bf38.type === "MT") {
          _0x219f86 = 2;
        }
        if (_0x40bf38.type === "TGL") {
          _0x219f86 = 3;
        }
        if (_0x40bf38.type === "RS") {
          _0x219f86 = 4;
        }
        if (_0x40bf38.type === "RKRT") {
          _0x219f86 = 5;
        }
        _0x1c6058[5] = _0x219f86;
        if (_0x219f86 === 1) {
          _0x1c6058[6] = _0x40bf38.route1;
          _0x1c6058[7] = _0x40bf38.route2;
          _0x1c6058[8] = _0x40bf38.route3;
          _0x1c6058[9] = _0x40bf38.route4;
          for (let _0x10675f = 0; _0x10675f < 4; _0x10675f++) {
            _0x1c6058[_0x10675f * 8 + 10] = _0x40bf38.keys[_0x10675f].code1;
            _0x1c6058[_0x10675f * 8 + 11] = _0x40bf38.keys[_0x10675f].hidCode;
            _0x1c6058[_0x10675f * 8 + 12] = _0x40bf38.keys[_0x10675f].code3;
            _0x1c6058[_0x10675f * 8 + 13] = _0x40bf38.keys[_0x10675f].code4;
            _0x1c6058[_0x10675f * 8 + 14] = _0x40bf38.steps[_0x10675f * 4];
            _0x1c6058[_0x10675f * 8 + 15] = _0x40bf38.steps[_0x10675f * 4 + 1];
            _0x1c6058[_0x10675f * 8 + 16] = _0x40bf38.steps[_0x10675f * 4 + 2];
            _0x1c6058[_0x10675f * 8 + 17] = _0x40bf38.steps[_0x10675f * 4 + 3];
          }
        }
        if (_0x219f86 === 2) {
          _0x1c6058[6] = _0x40bf38.keys[1].code1;
          _0x1c6058[7] = _0x40bf38.keys[1].hidCode;
          _0x1c6058[8] = _0x40bf38.keys[1].code3;
          _0x1c6058[9] = _0x40bf38.keys[1].code4;
          _0x1c6058[10] = _0x40bf38.keys[0].code1;
          _0x1c6058[11] = _0x40bf38.keys[0].hidCode;
          _0x1c6058[12] = _0x40bf38.keys[0].code3;
          _0x1c6058[13] = _0x40bf38.keys[0].code4;
          _0x1c6058[14] = _0x40bf38.duration;
        }
        if (_0x219f86 === 3) {
          _0x1c6058[6] = _0x40bf38.keys[0].code1;
          _0x1c6058[7] = _0x40bf38.keys[0].hidCode;
          _0x1c6058[8] = _0x40bf38.keys[0].code3;
          _0x1c6058[9] = _0x40bf38.keys[0].code4;
        }
        if (_0x219f86 === 4) {
          let _0xea0ddb = findDeviceKey(_0x40bf38.keys[0].code) || {};
          let _0x267076 = findDeviceKey(_0x40bf38.keys[1].code) || {};
          _0x1c6058[6] = _0xea0ddb.code1;
          _0x1c6058[7] = _0xea0ddb.hidCode;
          _0x1c6058[8] = _0xea0ddb.code3;
          _0x1c6058[9] = _0xea0ddb.code4;
          _0x1c6058[10] = Math.floor(_0xea0ddb.index / 22);
          _0x1c6058[11] = _0xea0ddb.index % 22;
          _0x1c6058[12] = _0x267076.code1;
          _0x1c6058[13] = _0x267076.hidCode;
          _0x1c6058[14] = _0x267076.code3;
          _0x1c6058[15] = _0x267076.code4;
          _0x1c6058[16] = Math.floor(_0x267076.index / 22);
          _0x1c6058[17] = _0x267076.index % 22;
        }
        if (_0x219f86 === 5) {
          _0x1c6058[6] = _0x40bf38.keys[0].code1;
          _0x1c6058[7] = _0x40bf38.keys[0].hidCode;
          _0x1c6058[8] = _0x40bf38.keys[0].code3;
          _0x1c6058[9] = _0x40bf38.keys[0].code4;
          _0x1c6058[12] = _0x40bf38.keys[1].code1;
          _0x1c6058[13] = _0x40bf38.keys[1].hidCode;
          _0x1c6058[14] = _0x40bf38.keys[1].code3;
          _0x1c6058[15] = _0x40bf38.keys[1].code4;
        }
      }
      await hidDevice.sendReport(1, _0x1c6058);
    }
  }
}
async function setPrcsPower(_0x11f805) {
  if (curDevice !== undefined && hidDevice !== undefined) {
    let _0x14c407 = new ArrayBuffer(63);
    let _0xa9f19f = new Uint8Array(_0x14c407);
    _0xa9f19f[0] = 36;
    _0xa9f19f[1] = 3;
    _0xa9f19f[4] = 1;
    _0xa9f19f[5] = _0x11f805 ? 1 : 0;
    await hidDevice.sendReport(1, _0xa9f19f);
  }
}
async function initPrcsPower() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    let _0x3a8237 = new ArrayBuffer(63);
    let _0x31c711 = new Uint8Array(_0x3a8237);
    _0x31c711[0] = 36;
    _0x31c711[1] = 2;
    await hidDevice.sendReport(1, _0x31c711);
  }
}
async function setPrcsData() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    for (let _0x101dc7 = 0; _0x101dc7 < 2; _0x101dc7++) {
      let _0x3f5d53 = new ArrayBuffer(63);
      let _0x104687 = new Uint8Array(_0x3f5d53);
      _0x104687[0] = 36;
      _0x104687[1] = 0;
      _0x104687[2] = _0x101dc7 >> 8 & 255;
      _0x104687[3] = _0x101dc7 & 255;
      _0x104687[4] = 40;
      for (let _0x5a8e54 = 0; _0x5a8e54 < 10; _0x5a8e54++) {
        let _0x4b3040 = _0x101dc7 * 10 + _0x5a8e54;
        if (_0x4b3040 < prcses.length) {
          let _0x392019 = prcses[_0x4b3040];
          _0x104687[_0x5a8e54 * 4 + 5] = 1;
          _0x104687[_0x5a8e54 * 4 + 6] = _0x392019.model;
          _0x104687[_0x5a8e54 * 4 + 7] = _0x392019.key1.hidCode;
          if (curDevice.type !== "us" && _0x392019.key2.hidCode === 49) {
            _0x104687[_0x5a8e54 * 4 + 8] = 50;
          } else {
            _0x104687[_0x5a8e54 * 4 + 8] = _0x392019.key2.hidCode;
          }
        }
      }
      await hidDevice.sendReport(1, _0x104687);
    }
  }
}
let isInitPrcsData = false;
async function initPrcsData() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    isInitPrcsData = false;
    waitCount = 0;
    let _0xd1f2e6 = new ArrayBuffer(63);
    let _0xcb7ca1 = new Uint8Array(_0xd1f2e6);
    _0xcb7ca1[0] = 36;
    _0xcb7ca1[1] = 1;
    await hidDevice.sendReport(1, _0xcb7ca1);
    while (!isInitPrcsData && waitCount < 10) {
      await new Promise(_0x23cb6d => setTimeout(_0x23cb6d, 0));
      waitCount++;
    }
    isInitPrcsData = false;
    waitCount = 0;
  }
}
let isInitSwitchList = false;
async function initSwitchList() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    isInitSwitchList = false;
    waitCount = 0;
    let _0x9295bd = new ArrayBuffer(63);
    let _0x24e581 = new Uint8Array(_0x9295bd);
    _0x24e581[0] = 37;
    _0x24e581[1] = 0;
    await hidDevice.sendReport(1, _0x24e581);
    while (!isInitSwitchList && waitCount < 10) {
      await new Promise(_0x5e1be6 => setTimeout(_0x5e1be6, 0));
      waitCount++;
    }
    isInitSwitchList = false;
    waitCount = 0;
  }
}
let isInitKeySwitch = false;
async function initKeySwitch() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    isInitKeySwitch = false;
    waitCount = 0;
    let _0x5119e7 = new ArrayBuffer(63);
    let _0x13bf11 = new Uint8Array(_0x5119e7);
    _0x13bf11[0] = 37;
    _0x13bf11[1] = 2;
    await hidDevice.sendReport(1, _0x13bf11);
    while (!isInitKeySwitch && waitCount < 10) {
      await new Promise(_0x5abf23 => setTimeout(_0x5abf23, 0));
      waitCount++;
    }
    isInitKeySwitch = false;
    waitCount = 0;
  }
}
async function setKeySwitch() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    let _0x1cb54a = new ArrayBuffer(132);
    let _0x586e70 = new Uint8Array(_0x1cb54a);
    curDevice.keys.forEach(_0x10a122 => {
      if (_0x10a122.index < _0x586e70.length) {
        _0x586e70[_0x10a122.index] = _0x10a122.switch;
      }
    });
    let _0x270868 = 58;
    let _0x4855af = Math.floor(_0x586e70.length / _0x270868);
    let _0x17c7d2 = _0x586e70.length % _0x270868;
    if (_0x17c7d2 > 0) {
      _0x4855af += 1;
    }
    for (let _0x50b821 = 0; _0x50b821 < _0x4855af; _0x50b821++) {
      _0x1cb54a = new ArrayBuffer(63);
      let _0x53fd2a = new Uint8Array(_0x1cb54a);
      _0x53fd2a[0] = 37;
      _0x53fd2a[1] = 1;
      _0x53fd2a[2] = _0x50b821 >> 8 & 255;
      _0x53fd2a[3] = _0x50b821 & 255;
      if (_0x17c7d2 > 0 && _0x50b821 === _0x4855af - 1) {
        _0x53fd2a[4] = _0x17c7d2;
        _0x53fd2a.set(_0x586e70.subarray(_0x50b821 * _0x270868, _0x50b821 * _0x270868 + _0x17c7d2), 5);
      } else {
        _0x53fd2a[4] = _0x270868;
        _0x53fd2a.set(_0x586e70.subarray(_0x50b821 * _0x270868, (_0x50b821 + 1) * _0x270868), 5);
      }
      await hidDevice.sendReport(1, _0x53fd2a);
    }
  }
}
let isInitDeadBand = false;
async function readDeadBand() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    isInitKeySwitch = false;
    waitCount = 0;
    let _0x4dc2a0 = new ArrayBuffer(63);
    let _0x43a209 = new Uint8Array(_0x4dc2a0);
    _0x43a209[0] = 38;
    _0x43a209[1] = 0;
    await hidDevice.sendReport(1, _0x43a209);
    while (!isInitDeadBand && waitCount < 10) {
      await new Promise(_0xf8f1aa => setTimeout(_0xf8f1aa, 0));
      waitCount++;
    }
    isInitDeadBand = false;
    waitCount = 0;
  }
}
async function setDeadBand() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    let _0x456407 = 132;
    let _0x57b542 = new ArrayBuffer(_0x456407 * 2);
    let _0x1f0927 = new Uint8Array(_0x57b542);
    curDevice.keys.forEach(_0x137352 => {
      if (_0x137352.index < _0x456407) {
        _0x1f0927[_0x137352.index * 2] = _0x137352.trigger.deadbandTop;
        _0x1f0927[_0x137352.index * 2 + 1] = _0x137352.trigger.deadbandBottom;
      }
    });
    let _0x224568 = 58;
    let _0x3ed44b = Math.floor(_0x1f0927.length / _0x224568);
    let _0x2a8bf6 = _0x1f0927.length % _0x224568;
    if (_0x2a8bf6 > 0) {
      _0x3ed44b += 1;
    }
    for (let _0xc45430 = 0; _0xc45430 < _0x3ed44b; _0xc45430++) {
      _0x57b542 = new ArrayBuffer(63);
      let _0x2450a3 = new Uint8Array(_0x57b542);
      _0x2450a3[0] = 38;
      _0x2450a3[1] = 1;
      _0x2450a3[2] = _0xc45430 >> 8 & 255;
      _0x2450a3[3] = _0xc45430 & 255;
      if (_0x2a8bf6 > 0 && _0xc45430 === _0x3ed44b - 1) {
        _0x2450a3[4] = _0x2a8bf6;
        _0x2450a3.set(_0x1f0927.subarray(_0xc45430 * _0x224568, _0xc45430 * _0x224568 + _0x2a8bf6), 5);
      } else {
        _0x2450a3[4] = _0x224568;
        _0x1f0927.subarray(_0xc45430 * _0x224568, (_0xc45430 + 1) * _0x224568);
        _0x2450a3.set(_0x1f0927.subarray(_0xc45430 * _0x224568, (_0xc45430 + 1) * _0x224568), 5);
      }
      await hidDevice.sendReport(1, _0x2450a3);
    }
  }
}
async function resetDeadBand() {
  if (curDevice !== undefined && hidDevice !== undefined) {
    let _0x410947 = new ArrayBuffer(63);
    let _0x2a44d4 = new Uint8Array(_0x410947);
    _0x2a44d4[0] = 38;
    _0x2a44d4[1] = 0;
    await hidDevice.sendReport(1, _0x2a44d4);
  }
}
function forceRefreshByFormSubmit() {
  const _0x3c968d = document.createElement("form");
  _0x3c968d.method = "GET";
  _0x3c968d.action = window.location.href;
  _0x3c968d.style.display = "none";
  const _0x59c4e8 = document.createElement("input");
  _0x59c4e8.type = "hidden";
  _0x59c4e8.name = "_force_refresh";
  _0x59c4e8.value = Date.now();
  _0x3c968d.appendChild(_0x59c4e8);
  document.body.appendChild(_0x3c968d);
  _0x3c968d.submit();
}