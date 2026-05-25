class Profile {
  constructor() {
    this.index = 0;
    this.name = "";
    this.light = new Light();
    this.colorArray1 = new Array(20).fill(new Color(255, 0, 0));
    this.colorArray2 = new Array(20).fill(new Color(0, 0, 0));
    this.colorArray3 = new Array(20).fill(new Color(255, 0, 0));
    this.colorArray4 = new Array(20).fill(new Color(0, 0, 0));
    this.sideLight = new Light();
    this.defKeys = new Map();
    this.fnKeys = new Map();
    this.macros = [];
    this.advKeys = [];
    this.recMacros = new Map();
    this.triggers = new Map();
    this.prcsPower = 0;
    this.prcses = [];
    this.other = 1;
    this.is6Key = false;
  }
}
class ProfileSet {
  constructor() {
    this.curIndex = 0;
    const _0xed2b55 = new Profile();
    _0xed2b55.colorArray2[2] = new Color(0, 255, 0);
    _0xed2b55.colorArray4[4] = new Color(0, 255, 0);
    this.profiles = new Array(5).fill(_0xed2b55);
  }
}
class Trigger {
  constructor() {
    this.mode = 0;
    this.travel = 0;
    this.interval1 = 0;
    this.interval2 = 0;
    this.deadbandTop = 0;
    this.deadbandBottom = 0;
  }
}
class Key {
  constructor() {
    this.index = 0;
    this.name = "";
    this.code = "";
    this.code1 = 0;
    this.hidCode = 0;
    this.code3 = 0;
    this.code4 = 0;
    this.width = 0;
    this.height = 0;
    this.x = "";
    this.y = "";
    this.trigger = new Trigger();
    this.switch = 0;
  }
}
class Light {
  constructor() {
    this.mode = 0;
    this.brightness = 0;
    this.speed = 0;
    this.foregroundColor = new Color(0, 0, 0, 0);
    this.backgroundColor = new Color(0, 0, 0, 0);
    this.direction = 0;
    this.fullColor = 0;
    this.power = 0;
    this.keysColor1 = new Map();
    this.keysColor2 = new Map();
  }
}
class AdvancedKey {
  constructor() {
    this.index = -1;
    this.type = "";
    this.duration = 0;
    this.keys = new Array(4).fill(new Key());
    this.route1 = 0;
    this.route2 = 0;
    this.route3 = 0;
    this.route4 = 0;
    this.steps = new Array(16).fill(0);
  }
}
class Prcs {
  constructor() {
    this.index = 0;
    this.name = "";
    this.key1 = new Key();
    this.key2 = new Key();
    this.model = 0;
  }
}
class Step {
  constructor() {
    this.tag = 0;
    this.type = 0;
    this.state = 0;
    this.delay = 0;
    this.key = new Key();
  }
}
class Macro {
  constructor() {
    this.index = 0;
    this.name = "";
    this.steps = [];
  }
}
class MacroKey {
  constructor() {
    this.index = 0;
    this.type = 0;
    this.count = 0;
  }
}
class Switch {
  constructor(_0x2d5906, _0x1b1988, _0x53b507, _0x6f198e, _0x5252c6) {
    this.index = _0x2d5906 === undefined ? 0 : _0x2d5906;
    this.color = _0x1b1988 === undefined ? new Color() : _0x1b1988;
    this.title = _0x53b507 === undefined ? "" : _0x53b507;
    this.name = _0x6f198e === undefined ? "" : _0x6f198e;
    this.travel = _0x5252c6 === undefined ? 3.4 : _0x5252c6;
  }
}
class Color {
  constructor(_0x28c186, _0x58dcef, _0x45024a, _0x2db8cd) {
    this.r = _0x28c186 === undefined ? 0 : _0x28c186;
    this.g = _0x58dcef === undefined ? 0 : _0x58dcef;
    this.b = _0x45024a === undefined ? 0 : _0x45024a;
    this.a = _0x2db8cd === undefined ? 0 : _0x2db8cd;
  }
  toRgb() {
    return "rgb(" + this.r + ", " + this.g + ", " + this.b + ")";
  }
  toRgba() {
    return "rgba(" + this.r + ", " + this.g + ", " + this.b + ", " + this.a + ")";
  }
}
class Device {
  constructor() {
    this.name = "";
    this.product = "";
    this.company = "";
    this.title = "";
    this.logoType = 0;
    this.vid = 0;
    this.pid = 0;
    this.width = 0;
    this.height = 0;
    this.hasLight = false;
    this.maxLightBrightness = 0;
    this.maxLightSpeed = 0;
    this.maxSideLightBrightness = 0;
    this.maxSideLightSpeed = 0;
    this.minTriggerTravel = 0;
    this.maxTriggerTravel = 0;
    this.triggerUnit = 0;
    this.type = "us";
    this.keys = [];
    this.light = new Light();
    this.sideLight = new Light();
    this.version = "";
  }
}
class KeySet {
  constructor() {
    this.name = "";
    this.keys = [];
  }
}
let profileSet;
let curProfile;
let curDevice;
let hidDevice;
let curKey;
let menu7;
let curPrcs;
let triMode;
let curMacro;
let curStep;
let curTime;
let curDksKey;
let curMtKey;
let curTglKey;
let curRSKey;
let curRKRTKey;
let curEdit;
let keyTip;
let dksTriggerDiv;
let settingsDiv;
let startStep;
let qrcode;
let checkedTip;
let btnUpdate;
let firmwareInfo;
let ProfileDef;
let Profile1;
let Profile2;
let Profile3;
let Profile4;
let menu1;
let menu2;
let menu4;
let devSet;
let keyBtn;
let keymapTable;
let keymapDef;
let keymapFn;
let keyManu1;
let keyManu2;
let keyManu3;
let keyManu4;
let keyManu10;
let recordInput;
let btnResetKey;
let btnApplyKey;
let fixedKeySet;
let fixedKeySet2;
let fixedKeySet3;
let fixedKeySet4;
let lightCustom1;
let lightCustom2;
let triggerAll;
let triggerDown;
let triggerUp;
let dbTop;
let dbBottom;
let battery;
let scale = 1;
let filters = [];
let curCompany = "";
let curCompanyList = null;
let isReadInfo = false;
let theme = "dark";
let bili = 0;
let fixedKeys = [];
let devList = [];
let devProduct = "";
let recKeys = new Map();
let fnKeys = new Map();
let cacheRecKeys = new Map();
let cacheFnKeys = new Map();
let comKeys = [];
let fnKeyState = [];
let switchList = [];
let switchDefault = [];
let hasRotaryKnob = false;
let isPrcs = false;
let prcses = [];
let isAnyKeyCalibration = false;
let isCustomLight = false;
let isMoreSwitch = false;
let isPollRate = false;
let isDeadBand = false;
let isCalibrationing = false;
let isMusicRhythm = false;
let isMusicRhythmOn = false;
let isALlAnd6keySwitch = false;
let isHighPrecision = false;
let is6KeyMode = false;
let isGamePad = false;
let isRS = false;
let isRKRT = false;
let pollRate = 1;
let isModeChange = -1;
let usedMacro = new Map();
let usedMacroIndex = [];
let recMacros = new Map();
let macros = [];
let isRecordMacro = false;
let isFirstStep = false;
let unitNum = 0;
let curR = 255;
let curG = 0;
let curB = 0;
let checkedKeys = [];
let triggerSliderValue = 0;
let advKeys = [];
let curAdvIndex = -1;