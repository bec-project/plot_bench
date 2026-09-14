var n, l$1, u$2, i$1, r$1, o$1, e$1, f$2, c$1, a$1, s$1, h$1, p$1, v$1, d$1 = {}, w$1 = [], _ = /acit|ex(?:s|g|n|p|$)|rph|grid|ows|mnc|ntw|ine[ch]|zoo|^ord|itera/i, g = Array.isArray;
function m$1(n2, l2) {
  for (var u2 in l2) n2[u2] = l2[u2];
  return n2;
}
function b(n2) {
  n2 && n2.parentNode && n2.parentNode.removeChild(n2);
}
function k$1(l2, u2, t2) {
  var i2, r2, o2, e2 = {};
  for (o2 in u2) "key" == o2 ? i2 = u2[o2] : "ref" == o2 ? r2 = u2[o2] : e2[o2] = u2[o2];
  if (arguments.length > 2 && (e2.children = arguments.length > 3 ? n.call(arguments, 2) : t2), "function" == typeof l2 && null != l2.defaultProps) for (o2 in l2.defaultProps) void 0 === e2[o2] && (e2[o2] = l2.defaultProps[o2]);
  return x(l2, e2, i2, r2, null);
}
function x(n2, t2, i2, r2, o2) {
  var e2 = { type: n2, props: t2, key: i2, ref: r2, __k: null, __: null, __b: 0, __e: null, __c: null, constructor: void 0, __v: null == o2 ? ++u$2 : o2, __i: -1, __u: 0 };
  return null == o2 && null != l$1.vnode && l$1.vnode(e2), e2;
}
function S(n2) {
  return n2.children;
}
function C$1(n2, l2) {
  this.props = n2, this.context = l2;
}
function $(n2, l2) {
  if (null == l2) return n2.__ ? $(n2.__, n2.__i + 1) : null;
  for (var u2; l2 < n2.__k.length; l2++) if (null != (u2 = n2.__k[l2]) && null != u2.__e) return u2.__e;
  return "function" == typeof n2.type ? $(n2) : null;
}
function I(n2) {
  if (n2.__P && n2.__d) {
    var u2 = n2.__v, t2 = u2.__e, i2 = [], r2 = [], o2 = m$1({}, u2);
    o2.__v = u2.__v + 1, l$1.vnode && l$1.vnode(o2), q(n2.__P, o2, u2, n2.__n, n2.__P.namespaceURI, 32 & u2.__u ? [t2] : null, i2, null == t2 ? $(u2) : t2, !!(32 & u2.__u), r2), o2.__v = u2.__v, o2.__.__k[o2.__i] = o2, D$1(i2, o2, r2), u2.__e = u2.__ = null, o2.__e != t2 && P(o2);
  }
}
function P(n2) {
  if (null != (n2 = n2.__) && null != n2.__c) return n2.__e = n2.__c.base = null, n2.__k.some(function(l2) {
    if (null != l2 && null != l2.__e) return n2.__e = n2.__c.base = l2.__e;
  }), P(n2);
}
function A$1(n2) {
  (!n2.__d && (n2.__d = true) && i$1.push(n2) && !H.__r++ || r$1 != l$1.debounceRendering) && ((r$1 = l$1.debounceRendering) || o$1)(H);
}
function H() {
  try {
    for (var n2, l2 = 1; i$1.length; ) i$1.length > l2 && i$1.sort(e$1), n2 = i$1.shift(), l2 = i$1.length, I(n2);
  } finally {
    i$1.length = H.__r = 0;
  }
}
function L(n2, l2, u2, t2, i2, r2, o2, e2, f2, c2, a2) {
  var s2, h2, p2, v2, y2, _2, g2 = t2 && t2.__k || w$1, m2 = l2.length;
  for (f2 = T$1(u2, l2, g2, f2, m2), s2 = 0; s2 < m2; s2++) null != (p2 = u2.__k[s2]) && (h2 = -1 != p2.__i && g2[p2.__i] || d$1, p2.__i = s2, _2 = q(n2, p2, h2, i2, r2, o2, e2, f2, c2, a2), v2 = p2.__e, p2.ref && h2.ref != p2.ref && (h2.ref && J(h2.ref, null, p2), a2.push(p2.ref, p2.__c || v2, p2)), null == y2 && null != v2 && (y2 = v2), 4 & p2.__u ? (f2 = j$1(p2, f2, n2), h2.__e && (h2.__e = null)) : "function" == typeof p2.type && void 0 !== _2 ? f2 = _2 : v2 && (f2 = v2.nextSibling), p2.__u &= -7);
  return u2.__e = y2, f2;
}
function T$1(n2, l2, u2, t2, i2) {
  var r2, o2, e2, f2, c2, a2 = u2.length, s2 = a2, h2 = 0;
  for (n2.__k = new Array(i2), r2 = 0; r2 < i2; r2++) null != (o2 = l2[r2]) && "boolean" != typeof o2 && "function" != typeof o2 ? ("string" == typeof o2 || "number" == typeof o2 || "bigint" == typeof o2 || o2.constructor == String ? o2 = n2.__k[r2] = x(null, o2, null, null, null) : g(o2) ? o2 = n2.__k[r2] = x(S, { children: o2 }, null, null, null) : void 0 === o2.constructor && o2.__b > 0 ? o2 = n2.__k[r2] = x(o2.type, o2.props, o2.key, o2.ref ? o2.ref : null, o2.__v) : n2.__k[r2] = o2, f2 = r2 + h2, o2.__ = n2, o2.__b = n2.__b + 1, e2 = null, -1 != (c2 = o2.__i = O(o2, u2, f2, s2)) && (s2--, (e2 = u2[c2]) && (e2.__u |= 2)), null == e2 || null == e2.__v ? (-1 == c2 && (i2 > a2 ? h2-- : i2 < a2 && h2++), "function" != typeof o2.type && (o2.__u |= 4)) : c2 != f2 && (c2 == f2 - 1 ? h2-- : c2 == f2 + 1 ? h2++ : (c2 > f2 ? h2-- : h2++, o2.__u |= 4))) : n2.__k[r2] = null;
  if (s2) for (r2 = 0; r2 < a2; r2++) null != (e2 = u2[r2]) && 0 == (2 & e2.__u) && (e2.__e == t2 && (t2 = $(e2)), K(e2, e2));
  return t2;
}
function j$1(n2, l2, u2) {
  var t2, i2;
  if ("function" == typeof n2.type) {
    for (t2 = n2.__k, i2 = 0; t2 && i2 < t2.length; i2++) t2[i2] && (t2[i2].__ = n2, l2 = j$1(t2[i2], l2, u2));
    return l2;
  }
  n2.__e != l2 && (l2 && n2.type && !l2.parentNode && (l2 = $(n2)), l2 = u2.insertBefore(n2.__e, l2 || null));
  do {
    l2 = l2 && l2.nextSibling;
  } while (null != l2 && 8 == l2.nodeType);
  return l2;
}
function O(n2, l2, u2, t2) {
  var i2, r2, o2, e2 = n2.key, f2 = n2.type, c2 = l2[u2], a2 = null != c2 && 0 == (2 & c2.__u);
  if (null === c2 && null == e2 || a2 && e2 == c2.key && f2 == c2.type) return u2;
  if (t2 > (a2 ? 1 : 0)) {
    for (i2 = u2 - 1, r2 = u2 + 1; i2 >= 0 || r2 < l2.length; ) if (null != (c2 = l2[o2 = i2 >= 0 ? i2-- : r2++]) && 0 == (2 & c2.__u) && e2 == c2.key && f2 == c2.type) return o2;
  }
  return -1;
}
function z$1(n2, l2, u2) {
  "-" == l2[0] ? n2.setProperty(l2, null == u2 ? "" : u2) : n2[l2] = null == u2 ? "" : "number" != typeof u2 || _.test(l2) ? u2 : u2 + "px";
}
function N(n2, l2, u2, t2, i2) {
  var r2, o2;
  n: if ("style" == l2) if ("string" == typeof u2) n2.style.cssText = u2;
  else {
    if ("string" == typeof t2 && (n2.style.cssText = t2 = ""), t2) for (l2 in t2) u2 && l2 in u2 || z$1(n2.style, l2, "");
    if (u2) for (l2 in u2) t2 && u2[l2] == t2[l2] || z$1(n2.style, l2, u2[l2]);
  }
  else if ("o" == l2[0] && "n" == l2[1]) r2 = l2 != (l2 = l2.replace(s$1, "$1")), o2 = l2.toLowerCase(), l2 = o2 in n2 || "onFocusOut" == l2 || "onFocusIn" == l2 ? o2.slice(2) : l2.slice(2), n2.l || (n2.l = {}), n2.l[l2 + r2] = u2, u2 ? t2 ? u2[a$1] = t2[a$1] : (u2[a$1] = h$1, n2.addEventListener(l2, r2 ? v$1 : p$1, r2)) : n2.removeEventListener(l2, r2 ? v$1 : p$1, r2);
  else {
    if ("http://www.w3.org/2000/svg" == i2) l2 = l2.replace(/xlink(H|:h)/, "h").replace(/sName$/, "s");
    else if ("width" != l2 && "height" != l2 && "href" != l2 && "list" != l2 && "form" != l2 && "tabIndex" != l2 && "download" != l2 && "rowSpan" != l2 && "colSpan" != l2 && "role" != l2 && "popover" != l2 && l2 in n2) try {
      n2[l2] = null == u2 ? "" : u2;
      break n;
    } catch (n3) {
    }
    "function" == typeof u2 || (null == u2 || false === u2 && "-" != l2[4] ? n2.removeAttribute(l2) : n2.setAttribute(l2, "popover" == l2 && 1 == u2 ? "" : u2));
  }
}
function V(n2) {
  return function(u2) {
    if (this.l) {
      var t2 = this.l[u2.type + n2];
      if (null == u2[c$1]) u2[c$1] = h$1++;
      else if (u2[c$1] < t2[a$1]) return;
      return t2(l$1.event ? l$1.event(u2) : u2);
    }
  };
}
function q(n2, u2, t2, i2, r2, o2, e2, f2, c2, a2) {
  var s2, h2, p2, v2, y2, d2, _2, k2, x2, M, I2, P2, A2, H2, T2, j2, F = u2.type;
  if (void 0 !== u2.constructor) return null;
  128 & t2.__u && (c2 = !!(32 & t2.__u), o2 = [f2 = u2.__e = t2.__e]), (s2 = l$1.__b) && s2(u2);
  n: if ("function" == typeof F) {
    h2 = e2.length;
    try {
      if (x2 = u2.props, M = F.prototype && F.prototype.render, I2 = (s2 = F.contextType) && i2[s2.__c], P2 = s2 ? I2 ? I2.props.value : s2.__ : i2, t2.__c ? k2 = (p2 = u2.__c = t2.__c).__ = p2.__E : (M ? u2.__c = p2 = new F(x2, P2) : (u2.__c = p2 = new C$1(x2, P2), p2.constructor = F, p2.render = Q), I2 && I2.sub(p2), p2.state || (p2.state = {}), p2.__n = i2, v2 = p2.__d = true, p2.__h = [], p2._sb = []), M && null == p2.__s && (p2.__s = p2.state), M && null != F.getDerivedStateFromProps && (p2.__s == p2.state && (p2.__s = m$1({}, p2.__s)), m$1(p2.__s, F.getDerivedStateFromProps(x2, p2.__s))), y2 = p2.props, d2 = p2.state, p2.__v = u2, v2) M && null == F.getDerivedStateFromProps && null != p2.componentWillMount && p2.componentWillMount(), M && null != p2.componentDidMount && p2.__h.push(p2.componentDidMount);
      else {
        if (M && null == F.getDerivedStateFromProps && x2 !== y2 && null != p2.componentWillReceiveProps && p2.componentWillReceiveProps(x2, P2), u2.__v == t2.__v || !p2.__e && null != p2.shouldComponentUpdate && false === p2.shouldComponentUpdate(x2, p2.__s, P2)) {
          u2.__v != t2.__v && (p2.props = x2, p2.state = p2.__s, p2.__d = false), u2.__e = t2.__e, u2.__k = t2.__k, u2.__k.some(function(n3) {
            n3 && (n3.__ = u2);
          }), w$1.push.apply(p2.__h, p2._sb), p2._sb = [], p2.__h.length && e2.push(p2), f2 = $(t2);
          break n;
        }
        null != p2.componentWillUpdate && p2.componentWillUpdate(x2, p2.__s, P2), M && null != p2.componentDidUpdate && p2.__h.push(function() {
          p2.componentDidUpdate(y2, d2, _2);
        });
      }
      if (p2.context = P2, p2.props = x2, p2.__P = n2, p2.__e = false, A2 = l$1.__r, H2 = 0, M) p2.state = p2.__s, p2.__d = false, A2 && A2(u2), s2 = p2.render(p2.props, p2.state, p2.context), w$1.push.apply(p2.__h, p2._sb), p2._sb = [];
      else do {
        p2.__d = false, A2 && A2(u2), s2 = p2.render(p2.props, p2.state, p2.context), p2.state = p2.__s;
      } while (p2.__d && ++H2 < 25);
      p2.state = p2.__s, null != p2.getChildContext && (i2 = m$1(m$1({}, i2), p2.getChildContext())), M && !v2 && null != p2.getSnapshotBeforeUpdate && (_2 = p2.getSnapshotBeforeUpdate(y2, d2)), T2 = null != s2 && s2.type === S && null == s2.key ? E(s2.props.children) : s2, f2 = L(n2, g(T2) ? T2 : [T2], u2, t2, i2, r2, o2, e2, f2, c2, a2), p2.base = u2.__e, u2.__u &= -161, p2.__h.length && e2.push(p2), k2 && (p2.__E = p2.__ = null);
    } catch (n3) {
      if (e2.length = h2, u2.__v = null, c2 || null != o2) {
        if (n3.then) {
          for (u2.__u |= c2 ? 160 : 128; f2 && 8 == f2.nodeType && f2.nextSibling; ) f2 = f2.nextSibling;
          null != o2 && (o2[o2.indexOf(f2)] = null), u2.__e = f2;
        } else if (null != o2) for (j2 = o2.length; j2--; ) b(o2[j2]);
      } else u2.__e = t2.__e;
      null == u2.__k && (u2.__k = t2.__k || []), n3.then || B$1(u2), l$1.__e(n3, u2, t2);
    }
  } else null == o2 && u2.__v == t2.__v ? (u2.__k = t2.__k, u2.__e = t2.__e) : f2 = u2.__e = G(t2.__e, u2, t2, i2, r2, o2, e2, c2, a2);
  return (s2 = l$1.diffed) && s2(u2), 128 & u2.__u ? void 0 : f2;
}
function B$1(n2) {
  n2 && (n2.__c && (n2.__c.__e = true), n2.__k && n2.__k.some(B$1));
}
function D$1(n2, u2, t2) {
  for (var i2 = 0; i2 < t2.length; i2++) J(t2[i2], t2[++i2], t2[++i2]);
  l$1.__c && l$1.__c(u2, n2), n2.some(function(u3) {
    try {
      n2 = u3.__h, u3.__h = [], n2.some(function(n3) {
        n3.call(u3);
      });
    } catch (n3) {
      l$1.__e(n3, u3.__v);
    }
  });
}
function E(n2) {
  return "object" != typeof n2 || null == n2 || n2.__b > 0 ? n2 : g(n2) ? n2.map(E) : void 0 !== n2.constructor ? null : m$1({}, n2);
}
function G(u2, t2, i2, r2, o2, e2, f2, c2, a2) {
  var s2, h2, p2, v2, y2, w2, _2, m2 = i2.props || d$1, k2 = t2.props, x2 = t2.type;
  if ("svg" == x2 ? o2 = "http://www.w3.org/2000/svg" : "math" == x2 ? o2 = "http://www.w3.org/1998/Math/MathML" : o2 || (o2 = "http://www.w3.org/1999/xhtml"), null != e2) {
    for (s2 = 0; s2 < e2.length; s2++) if ((y2 = e2[s2]) && "setAttribute" in y2 == !!x2 && (x2 ? y2.localName == x2 : 3 == y2.nodeType)) {
      u2 = y2, e2[s2] = null;
      break;
    }
  }
  if (null == u2) {
    if (null == x2) return document.createTextNode(k2);
    u2 = document.createElementNS(o2, x2, k2.is && k2), c2 && (l$1.__m && l$1.__m(t2, e2), c2 = false), e2 = null;
  }
  if (null == x2) m2 === k2 || c2 && u2.data == k2 || (u2.data = k2);
  else {
    if (e2 = "textarea" == x2 && null != k2.defaultValue ? null : e2 && n.call(u2.childNodes), !c2 && null != e2) for (m2 = {}, s2 = 0; s2 < u2.attributes.length; s2++) m2[(y2 = u2.attributes[s2]).name] = y2.value;
    for (s2 in m2) y2 = m2[s2], "dangerouslySetInnerHTML" == s2 ? p2 = y2 : "children" == s2 || s2 in k2 || "value" == s2 && "defaultValue" in k2 || "checked" == s2 && "defaultChecked" in k2 || N(u2, s2, null, y2, o2);
    for (s2 in k2) y2 = k2[s2], "children" == s2 ? v2 = y2 : "dangerouslySetInnerHTML" == s2 ? h2 = y2 : "value" == s2 ? w2 = y2 : "checked" == s2 ? _2 = y2 : c2 && "function" != typeof y2 || m2[s2] === y2 || N(u2, s2, y2, m2[s2], o2);
    if (h2) c2 || p2 && (h2.__html == p2.__html || h2.__html == u2.innerHTML) || (u2.innerHTML = h2.__html), t2.__k = [];
    else if (p2 && (u2.innerHTML = ""), L("template" == t2.type ? u2.content : u2, g(v2) ? v2 : [v2], t2, i2, r2, "foreignObject" == x2 ? "http://www.w3.org/1999/xhtml" : o2, e2, f2, e2 ? e2[0] : i2.__k && $(i2, 0), c2, a2), null != e2) for (s2 = e2.length; s2--; ) b(e2[s2]);
    c2 && "textarea" != x2 || (s2 = "value", "progress" == x2 && null == w2 ? u2.removeAttribute("value") : null != w2 && (w2 !== u2[s2] || "progress" == x2 && !w2 || "option" == x2 && w2 != m2[s2]) && N(u2, s2, w2, m2[s2], o2), s2 = "checked", null != _2 && _2 != u2[s2] && N(u2, s2, _2, m2[s2], o2));
  }
  return u2;
}
function J(n2, u2, t2) {
  try {
    if ("function" == typeof n2) {
      var i2 = "function" == typeof n2.__u;
      i2 && n2.__u(), i2 && null == u2 || (n2.__u = n2(u2));
    } else n2.current = u2;
  } catch (n3) {
    l$1.__e(n3, t2);
  }
}
function K(n2, u2, t2) {
  var i2, r2;
  if (l$1.unmount && l$1.unmount(n2), (i2 = n2.ref) && (i2.current && i2.current != n2.__e || J(i2, null, u2)), null != (i2 = n2.__c)) {
    if (i2.componentWillUnmount) try {
      i2.componentWillUnmount();
    } catch (n3) {
      l$1.__e(n3, u2);
    }
    i2.base = i2.__P = i2.__n = null;
  }
  if (i2 = n2.__k) for (r2 = 0; r2 < i2.length; r2++) i2[r2] && K(i2[r2], u2, t2 || "function" != typeof n2.type);
  t2 || b(n2.__e), n2.__c = n2.__ = n2.__e = void 0;
}
function Q(n2, l2, u2) {
  return this.constructor(n2, u2);
}
function R(u2, t2, i2) {
  var r2, o2, e2, f2;
  t2 == document && (t2 = document.documentElement), l$1.__ && l$1.__(u2, t2), o2 = (r2 = false) ? null : t2.__k, e2 = [], f2 = [], q(t2, u2 = t2.__k = k$1(S, null, [u2]), o2 || d$1, d$1, t2.namespaceURI, o2 ? null : t2.firstChild ? n.call(t2.childNodes) : null, e2, o2 ? o2.__e : t2.firstChild, r2, f2), D$1(e2, u2, f2), u2.props.children = null;
}
n = w$1.slice, l$1 = { __e: function(n2, l2, u2, t2) {
  for (var i2, r2, o2; l2 = l2.__; ) if ((i2 = l2.__c) && !i2.__) try {
    if ((r2 = i2.constructor) && null != r2.getDerivedStateFromError && (i2.setState(r2.getDerivedStateFromError(n2)), o2 = i2.__d), null != i2.componentDidCatch && (i2.componentDidCatch(n2, t2 || {}), o2 = i2.__d), o2) return i2.__E = i2;
  } catch (l3) {
    n2 = l3;
  }
  throw n2;
} }, u$2 = 0, C$1.prototype.setState = function(n2, l2) {
  var u2;
  u2 = null != this.__s && this.__s != this.state ? this.__s : this.__s = m$1({}, this.state), "function" == typeof n2 && (n2 = n2(m$1({}, u2), this.props)), n2 && m$1(u2, n2), null != n2 && this.__v && (l2 && this._sb.push(l2), A$1(this));
}, C$1.prototype.forceUpdate = function(n2) {
  this.__v && (this.__e = true, n2 && this.__h.push(n2), A$1(this));
}, C$1.prototype.render = S, i$1 = [], o$1 = "function" == typeof Promise ? Promise.prototype.then.bind(Promise.resolve()) : setTimeout, e$1 = function(n2, l2) {
  return n2.__v.__b - l2.__v.__b;
}, H.__r = 0, f$2 = Math.random().toString(8), c$1 = "__d" + f$2, a$1 = "__a" + f$2, s$1 = /(PointerCapture)$|Capture$/i, h$1 = 0, p$1 = V(false), v$1 = V(true);
var f$1 = 0;
function u$1(e2, t2, n2, o2, i2, u2) {
  t2 || (t2 = {});
  var a2, c2, p2 = t2;
  if ("ref" in p2) for (c2 in p2 = {}, t2) "ref" == c2 ? a2 = t2[c2] : p2[c2] = t2[c2];
  var l2 = { type: e2, props: p2, key: n2, ref: a2, __k: null, __: null, __b: 0, __e: null, __c: null, constructor: void 0, __v: --f$1, __i: -1, __u: 0, __source: i2, __self: u2 };
  if ("function" == typeof e2 && (a2 = e2.defaultProps)) for (c2 in a2) void 0 === p2[c2] && (p2[c2] = a2[c2]);
  return l$1.vnode && l$1.vnode(l2), l2;
}
var t, r, u, i, o = 0, f = [], c = l$1, e = c.__b, a = c.__r, v = c.diffed, l = c.__c, m = c.unmount, p = c.__;
function s(n2, t2) {
  c.__h && c.__h(r, n2, o || t2), o = 0;
  var u2 = r.__H || (r.__H = { __: [], __h: [] });
  return n2 >= u2.__.length && u2.__.push({}), u2.__[n2];
}
function d(n2) {
  return o = 1, y(D, n2);
}
function y(n2, u2, i2) {
  var o2 = s(t++, 2);
  if (o2.t = n2, !o2.__c && (o2.__ = [D(void 0, u2), function(n3) {
    var t2 = o2.__N ? o2.__N[0] : o2.__[0], r2 = o2.t(t2, n3);
    t2 !== r2 && (o2.__N = [r2, o2.__[1]], o2.__c.setState({}));
  }], o2.__c = r, !r.__f)) {
    var f2 = function(n3, t2, r2) {
      if (!o2.__c.__H) return true;
      var u3 = false, i3 = o2.__c.props !== n3;
      if (o2.__c.__H.__.some(function(n4) {
        if (n4.__N) {
          u3 = true;
          var t3 = n4.__[0];
          n4.__ = n4.__N, n4.__N = void 0, t3 !== n4.__[0] && (i3 = true);
        }
      }), c2) {
        var f3 = c2.call(this, n3, t2, r2);
        return u3 ? f3 || i3 : f3;
      }
      return !u3 || i3;
    };
    r.__f = true;
    var c2 = r.shouldComponentUpdate, e2 = r.componentWillUpdate;
    r.componentWillUpdate = function(n3, t2, r2) {
      if (this.__e) {
        var u3 = c2;
        c2 = void 0, f2(n3, t2, r2), c2 = u3;
      }
      e2 && e2.call(this, n3, t2, r2);
    }, r.shouldComponentUpdate = f2;
  }
  return o2.__N || o2.__;
}
function h(n2, u2) {
  var i2 = s(t++, 3);
  !c.__s && C(i2.__H, u2) && (i2.__ = n2, i2.u = u2, r.__H.__h.push(i2));
}
function A(n2) {
  return o = 5, T(function() {
    return { current: n2 };
  }, []);
}
function T(n2, r2) {
  var u2 = s(t++, 7);
  return C(u2.__H, r2) && (u2.__ = n2(), u2.__H = r2, u2.__h = n2), u2.__;
}
function j() {
  for (var n2; n2 = f.shift(); ) {
    var t2 = n2.__H;
    if (n2.__P && t2) try {
      t2.__h.some(z), t2.__h.some(B), t2.__h = [];
    } catch (r2) {
      t2.__h = [], c.__e(r2, n2.__v);
    }
  }
}
c.__b = function(n2) {
  r = null, e && e(n2);
}, c.__ = function(n2, t2) {
  n2 && t2.__k && t2.__k.__m && (n2.__m = t2.__k.__m), p && p(n2, t2);
}, c.__r = function(n2) {
  a && a(n2), t = 0;
  var i2 = (r = n2.__c).__H;
  i2 && (u === r ? (i2.__h = [], r.__h = [], i2.__.some(function(n3) {
    n3.__N && (n3.__ = n3.__N), n3.u = n3.__N = void 0;
  })) : (i2.__h.some(z), i2.__h.some(B), i2.__h = [], t = 0)), u = r;
}, c.diffed = function(n2) {
  v && v(n2);
  var t2 = n2.__c;
  t2 && t2.__H && (t2.__H.__h.length && (1 !== f.push(t2) && i === c.requestAnimationFrame || ((i = c.requestAnimationFrame) || w)(j)), t2.__H.__.some(function(n3) {
    n3.u && (n3.__H = n3.u, n3.u = void 0);
  })), u = r = null;
}, c.__c = function(n2, t2) {
  t2.some(function(n3) {
    try {
      n3.__h.some(z), n3.__h = n3.__h.filter(function(n4) {
        return !n4.__ || B(n4);
      });
    } catch (r2) {
      t2.some(function(n4) {
        n4.__h && (n4.__h = []);
      }), t2 = [], c.__e(r2, n3.__v);
    }
  }), l && l(n2, t2);
}, c.unmount = function(n2) {
  m && m(n2);
  var t2, r2 = n2.__c;
  r2 && r2.__H && (r2.__H.__.some(function(n3) {
    try {
      z(n3);
    } catch (n4) {
      t2 = n4;
    }
  }), r2.__H = void 0, t2 && c.__e(t2, r2.__v));
};
var k = "function" == typeof requestAnimationFrame;
function w(n2) {
  var t2, r2 = function() {
    clearTimeout(u2), k && cancelAnimationFrame(t2), setTimeout(n2);
  }, u2 = setTimeout(r2, 35);
  k && (t2 = requestAnimationFrame(r2));
}
function z(n2) {
  var t2 = r, u2 = n2.__c;
  "function" == typeof u2 && (n2.__c = void 0, u2()), r = t2;
}
function B(n2) {
  var t2 = r;
  n2.__c = n2.__(), r = t2;
}
function C(n2, t2) {
  return !n2 || n2.length !== t2.length || t2.some(function(t3, r2) {
    return t3 !== n2[r2];
  });
}
function D(n2, t2) {
  return "function" == typeof t2 ? t2(n2) : t2;
}
async function jsonOrError(response) {
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(result.error || `Request failed (${response.status}).`);
  }
  return result;
}
async function fetchInitial() {
  const response = await fetch("/api/initial");
  if (!response.ok) throw new Error("The matrix editor could not load its initial suite.");
  return response.json();
}
async function fetchEnvironment() {
  const response = await fetch("/api/environment");
  if (!response.ok) return null;
  return response.json();
}
async function fetchPresets() {
  const response = await fetch("/api/presets");
  if (!response.ok) return [];
  const result = await response.json();
  return result.presets ?? [];
}
async function preview(suite, kind) {
  const response = await fetch("/api/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ suite, kind })
  });
  return jsonOrError(response);
}
async function previewRaw(suiteJson, kind) {
  const response = await fetch("/api/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ suite_json: suiteJson, kind })
  });
  return jsonOrError(response);
}
async function saveSuite(suite, filename, kind) {
  const response = await fetch("/api/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ suite, filename, kind })
  });
  return jsonOrError(response);
}
const ENUMS = {
  view: ["waveform", "image", "both"],
  waveform_mode: ["replace", "append"],
  image_mode: ["scalar", "rgb"]
};
const VIEW_TIP = "Which plot(s) this workload drives: a 1-D waveform, a 2-D image, or both together.";
const OPTION_TIPS = {
  // frontends
  pyqtgraph: "PyQtGraph — Qt, CPU raster rendering.",
  "pyqtgraph-gl": "PyQtGraph with its OpenGL backend.",
  matplotlib: "Matplotlib on the Qt Agg canvas.",
  qtgraphs: "Qt Graphs (QML/Quick) renderer.",
  "qtgraphs-cpp": "Qt Graphs via the native C++ SDK.",
  iced: "Iced — native Rust GUI on wgpu.",
  fyne: "Fyne — Go GUI with custom CPU waveform rasterization and RGBA canvas images.",
  plotly: "Plotly.js in a controlled browser.",
  // backends
  python: "The built-in Python source. Always available with a core install.",
  rust: "The faster native Rust source. Needs ./scripts/setup rust.",
  // modes
  stream: "Live frames delivered as the source produces them.",
  replay: "A recording is preloaded, then played back at a fixed rate.",
  // enum config values
  replace: "Each frame redraws the whole curve.",
  append: "Each frame appends new samples to a rolling window.",
  scalar: "Single-channel intensity image.",
  rgb: "Three-channel colour image."
};
const GROUP_TIPS = {
  frontends: "The plotting implementations to benchmark. Each renders the same frames independently.",
  backends: "Where frames are generated — the Python source or the faster Rust source.",
  modes: "How frames reach the renderer: live streaming, or replay of a preloaded recording.",
  kind: "Frontend benchmark drives a renderer; Source receiver probe measures the source and delivery only, with no plotting."
};
const SHARED_FIELDS = [
  {
    key: "hz",
    label: "Target rate",
    kind: "rate",
    hint: "Hz",
    tip: "Frames per second the source generates and submits. Capped at 120 Hz."
  },
  {
    key: "seed",
    label: "Data seed",
    kind: "number",
    tip: "Seed for the deterministic data generator; the same seed reproduces identical frames."
  }
];
const WAVEFORM_FIELDS = [
  {
    key: "points",
    label: "Waveform points",
    kind: "number",
    tip: "Number of samples in each waveform frame."
  },
  {
    key: "waveform_mode",
    label: "Waveform mode",
    kind: "enum",
    tip: "replace redraws the whole curve each frame; append adds to a rolling window."
  },
  {
    key: "append_count",
    label: "Append count",
    kind: "number",
    hint: "append mode",
    tip: "In append mode, how many new samples are added per frame."
  },
  {
    key: "waveform_plots",
    label: "Waveform plots",
    kind: "number",
    tip: "Number of waveform plot widgets in the window, each with its own data. Between 1 and 16."
  },
  {
    key: "curves",
    label: "Curves per plot",
    kind: "number",
    tip: "Curves drawn in every waveform plot, each with distinct data. Between 1 and 64."
  }
];
const IMAGE_FIELDS = [
  { key: "width", label: "Image width", kind: "number", hint: "px", tip: "Image width in pixels." },
  { key: "height", label: "Image height", kind: "number", hint: "px", tip: "Image height in pixels." },
  {
    key: "image_mode",
    label: "Image mode",
    kind: "enum",
    tip: "scalar sends a single intensity channel; rgb sends three colour channels."
  },
  {
    key: "image_plots",
    label: "Image plots",
    kind: "number",
    tip: "Number of image plot widgets in the window, each with its own data. Between 1 and 16."
  }
];
const RESOLUTION_FIELD = {
  key: "resolution",
  label: "Square resolution",
  kind: "number",
  hint: "px",
  tip: "Shorthand that sets both width and height to the same square size."
};
const ALL_AXES = [
  "view",
  "hz",
  "points",
  "append_count",
  "curves",
  "waveform_plots",
  "waveform_mode",
  "width",
  "height",
  "image_plots",
  "image_mode",
  "seed",
  "resolution"
];
function showsWaveform(view) {
  return view === "waveform" || view === "both";
}
function showsImage(view) {
  return view === "image" || view === "both";
}
function visibleGroups(view, includeResolution = false) {
  const groups = [
    { title: "Rate & seed", fields: SHARED_FIELDS }
  ];
  if (showsWaveform(view)) groups.push({ title: "Waveform", fields: WAVEFORM_FIELDS });
  if (showsImage(view)) {
    const image = includeResolution ? [RESOLUTION_FIELD, ...IMAGE_FIELDS] : IMAGE_FIELDS;
    groups.push({ title: "Image", fields: image });
  }
  return groups;
}
const MAX_SAFE = Number.MAX_SAFE_INTEGER;
function CopyButton(props) {
  const [copied, setCopied] = d(false);
  return /* @__PURE__ */ u$1(
    "button",
    {
      type: "button",
      class: "btn-copy",
      onClick: async () => {
        try {
          await navigator.clipboard.writeText(props.text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1400);
        } catch {
          setCopied(false);
        }
      },
      children: copied ? "Copied" : "Copy"
    }
  );
}
function CommandLine(props) {
  return /* @__PURE__ */ u$1("div", { class: "command-row", children: [
    /* @__PURE__ */ u$1("div", { class: "command-meta", children: [
      /* @__PURE__ */ u$1("span", { class: "command-label", children: props.label }),
      props.note ? /* @__PURE__ */ u$1("span", { class: "muted small", children: props.note }) : null
    ] }),
    /* @__PURE__ */ u$1("div", { class: "command-line", children: [
      /* @__PURE__ */ u$1("code", { children: props.command }),
      /* @__PURE__ */ u$1(CopyButton, { text: props.command })
    ] })
  ] });
}
function InfoTip(props) {
  return /* @__PURE__ */ u$1("span", { class: "infotip", tabIndex: 0, role: "note", "aria-label": props.text, children: [
    /* @__PURE__ */ u$1("span", { class: "infotip-icon", "aria-hidden": "true", children: "i" }),
    /* @__PURE__ */ u$1("span", { class: "infotip-bubble", role: "tooltip", children: props.text })
  ] });
}
function parseNumeric(text, allowDecimal) {
  const trimmed = text.trim();
  if (trimmed === "") return { value: void 0 };
  const clean = allowDecimal ? /^-?\d*\.?\d+$/ : /^-?\d+$/;
  if (!clean.test(trimmed)) {
    return { value: text, error: allowDecimal ? "Enter a number." : "Enter a whole number." };
  }
  const n2 = Number(trimmed);
  if (!Number.isFinite(n2)) return { value: text, error: "Enter a finite number." };
  if (Math.abs(n2) > MAX_SAFE) {
    return {
      value: text,
      error: `Too large for the editor (±${MAX_SAFE.toLocaleString()}). Use the CLI for larger integers.`
    };
  }
  return { value: n2 };
}
function Field(props) {
  return /* @__PURE__ */ u$1("div", { class: "field", children: [
    /* @__PURE__ */ u$1("span", { class: "field-label", children: [
      props.label,
      props.hint ? /* @__PURE__ */ u$1("span", { class: "field-hint", children: [
        " · ",
        props.hint
      ] }) : null,
      props.tip ? /* @__PURE__ */ u$1(InfoTip, { text: props.tip }) : null
    ] }),
    props.children,
    props.error ? /* @__PURE__ */ u$1("span", { class: "field-error", children: props.error }) : null
  ] });
}
function NumberField(props) {
  const [text, setText] = d(props.value === void 0 ? "" : String(props.value));
  const emitted = A(props.value);
  h(() => {
    if (props.value !== emitted.current) {
      setText(props.value === void 0 ? "" : String(props.value));
      emitted.current = props.value;
    }
  }, [props.value]);
  const parsed = parseNumeric(text, props.allowDecimal ?? false);
  return /* @__PURE__ */ u$1(Field, { label: props.label, hint: props.hint, tip: props.tip, error: parsed.error, children: /* @__PURE__ */ u$1(
    "input",
    {
      type: "text",
      inputMode: props.allowDecimal ? "decimal" : "numeric",
      value: text,
      placeholder: props.placeholder === void 0 ? "Optional" : String(props.placeholder),
      "aria-label": props.label,
      "aria-invalid": parsed.error ? "true" : void 0,
      onInput: (event) => {
        const next = event.target.value;
        setText(next);
        const result = parseNumeric(next, props.allowDecimal ?? false);
        emitted.current = result.value;
        props.onChange(result.value);
      }
    }
  ) });
}
function SelectField(props) {
  return /* @__PURE__ */ u$1(Field, { label: props.label, hint: props.hint, tip: props.tip, children: /* @__PURE__ */ u$1(
    "select",
    {
      value: props.value === void 0 ? "" : String(props.value),
      "aria-label": props.label,
      onChange: (event) => {
        const next = event.target.value;
        props.onChange(next === "" ? void 0 : next);
      },
      children: [
        /* @__PURE__ */ u$1("option", { value: "", children: props.defaultLabel }),
        props.options.map((option) => /* @__PURE__ */ u$1("option", { value: option, children: option }))
      ]
    }
  ) });
}
function TextField(props) {
  return /* @__PURE__ */ u$1(Field, { label: props.label, hint: props.hint, children: /* @__PURE__ */ u$1(
    "input",
    {
      type: "text",
      value: props.value,
      placeholder: props.placeholder,
      "aria-label": props.label,
      onInput: (event) => props.onInput(event.target.value)
    }
  ) });
}
function ChipGroup(props) {
  return /* @__PURE__ */ u$1("fieldset", { class: "chip-group", disabled: props.disabled, children: [
    /* @__PURE__ */ u$1("legend", { children: [
      props.legend,
      props.legendTip ? /* @__PURE__ */ u$1(InfoTip, { text: props.legendTip }) : null
    ] }),
    /* @__PURE__ */ u$1("div", { class: "chips", children: props.options.map((option) => {
      const checked = props.selected.includes(option);
      const status = props.status?.[option];
      const missing = status ? !status.installed : false;
      const title = [
        props.tips?.[option],
        status ? status.installed ? "Installed." : `Not installed — ./scripts/setup ${status.setup}` : void 0
      ].filter(Boolean).join(" ");
      return /* @__PURE__ */ u$1(
        "label",
        {
          class: `chip${checked ? " chip-on" : ""}${missing ? " chip-missing" : ""}`,
          title: title || void 0,
          children: [
            /* @__PURE__ */ u$1(
              "input",
              {
                type: "checkbox",
                value: option,
                checked,
                onChange: (event) => props.onToggle(option, event.target.checked)
              }
            ),
            status ? /* @__PURE__ */ u$1(
              "span",
              {
                class: `dot ${status.installed ? "dot-ok" : "dot-missing"}`,
                "aria-hidden": "true"
              }
            ) : null,
            option
          ]
        }
      );
    }) })
  ] });
}
function ConfigFields(props) {
  const view = String(props.config.view ?? props.defaults.view);
  const groups = visibleGroups(view, props.includeResolution);
  const set = (key, value) => {
    const next = { ...props.config };
    if (value === void 0) delete next[key];
    else next[key] = value;
    props.onChange(next);
  };
  return /* @__PURE__ */ u$1("div", { class: "config-groups", children: groups.map((group) => /* @__PURE__ */ u$1("fieldset", { class: "config-group", children: [
    /* @__PURE__ */ u$1("legend", { children: group.title }),
    /* @__PURE__ */ u$1("div", { class: "field-grid", children: group.fields.map((spec) => {
      const value = props.config[spec.key];
      const fallback = props.defaults[spec.key];
      if (spec.kind === "enum") {
        return /* @__PURE__ */ u$1(
          SelectField,
          {
            label: spec.label,
            hint: spec.hint,
            tip: spec.tip,
            value,
            options: ENUMS[spec.key],
            defaultLabel: `Default (${fallback})`,
            onChange: (next) => set(spec.key, next)
          }
        );
      }
      return /* @__PURE__ */ u$1(
        NumberField,
        {
          label: spec.label,
          hint: spec.hint,
          tip: spec.tip,
          value,
          allowDecimal: spec.kind === "rate",
          placeholder: fallback,
          onChange: (next) => set(spec.key, next)
        }
      );
    }) })
  ] })) });
}
function Launcher(props) {
  const { result } = props;
  return /* @__PURE__ */ u$1("section", { class: "panel launcher", children: [
    /* @__PURE__ */ u$1("div", { class: "panel-head", children: [
      /* @__PURE__ */ u$1("h2", { children: "Saved · ready to run" }),
      /* @__PURE__ */ u$1("button", { type: "button", class: "btn-soft", onClick: props.onDismiss, children: "Dismiss" })
    ] }),
    /* @__PURE__ */ u$1("p", { class: "summary", children: [
      "Saved to ",
      /* @__PURE__ */ u$1("code", { children: result.path })
    ] }),
    /* @__PURE__ */ u$1("p", { class: "muted small", children: [
      "This folder is git-ignored. The editor never runs benchmarks — stop it with Ctrl+C, then run one of these in your terminal. Progress prints as ",
      /* @__PURE__ */ u$1("code", { children: "[i/N]" }),
      " with elapsed time, a live ETA and a pass/fail tally."
    ] }),
    /* @__PURE__ */ u$1("div", { class: "commands", children: [
      /* @__PURE__ */ u$1(
        CommandLine,
        {
          label: "1 · Preview",
          note: "Validate and print the schedule without launching.",
          command: result.commands.dry_run
        }
      ),
      /* @__PURE__ */ u$1(
        CommandLine,
        {
          label: "2 · Quick check",
          note: "One short repetition of every selected workload, source, frontend and mode.",
          command: result.commands.quick_check
        }
      ),
      /* @__PURE__ */ u$1(
        CommandLine,
        {
          label: "3 · Full run",
          note: `The configured campaign (~${result.minimum_minutes.toFixed(1)} min minimum, ${result.run_count.toLocaleString()} runs).`,
          command: result.commands.full
        }
      )
    ] })
  ] });
}
const PREVIEW_LIMIT = 250;
function mmss(totalSeconds) {
  const seconds = Math.max(0, Math.round(totalSeconds));
  const m2 = Math.floor(seconds / 60);
  const s2 = seconds % 60;
  return `${m2}:${String(s2).padStart(2, "0")}`;
}
function plotsLabel(config) {
  const view = String(config.view);
  const parts = [];
  if (showsWaveform(view)) {
    const plots = Number(config.waveform_plots ?? 1);
    const curves = Number(config.curves ?? 1);
    parts.push(`${curves > 1 ? `${plots}×${curves}` : plots} wf`);
  }
  if (showsImage(view)) parts.push(`${Number(config.image_plots ?? 1)} img`);
  return parts.join(" · ");
}
function PlanPreview(props) {
  const { plan, error, pending, commands, needsSave } = props;
  return /* @__PURE__ */ u$1("section", { class: "panel", children: [
    /* @__PURE__ */ u$1("div", { class: "panel-head", children: [
      /* @__PURE__ */ u$1("h2", { children: "Execution preview" }),
      pending ? /* @__PURE__ */ u$1("span", { class: "pill pill-pending", children: "validating…" }) : null
    ] }),
    error ? /* @__PURE__ */ u$1("p", { id: "plan-error", class: "alert", role: "alert", children: error }) : null,
    plan ? /* @__PURE__ */ u$1(S, { children: [
      /* @__PURE__ */ u$1("p", { id: "plan-summary", class: "summary", children: [
        /* @__PURE__ */ u$1("strong", { children: plan.case_count.toLocaleString() }),
        " workloads ·",
        " ",
        /* @__PURE__ */ u$1("strong", { children: plan.run_count.toLocaleString() }),
        " runs · at least",
        " ",
        /* @__PURE__ */ u$1("strong", { children: (plan.estimate.minimum_seconds / 60).toFixed(1) }),
        " min"
      ] }),
      /* @__PURE__ */ u$1("p", { class: "muted small", children: [
        "Each run: startup → warmup ",
        plan.warmup_seconds,
        "s → measure ",
        plan.measurement_seconds,
        "s → cooldown",
        " ",
        plan.cooldown_seconds,
        "s (≈ ",
        mmss(plan.warmup_seconds + plan.measurement_seconds + plan.cooldown_seconds),
        " ",
        "each). Startup, replay preload, teardown and report generation add more."
      ] }),
      /* @__PURE__ */ u$1("div", { class: "run-here", children: [
        /* @__PURE__ */ u$1("p", { class: "block-label", children: [
          "Run this configuration",
          needsSave ? /* @__PURE__ */ u$1("span", { class: "run-note", children: " · save it first" }) : null
        ] }),
        commands.map((entry) => /* @__PURE__ */ u$1(CommandLine, { label: entry.label, command: entry.command }))
      ] }),
      /* @__PURE__ */ u$1("div", { class: "table-wrap", children: /* @__PURE__ */ u$1("table", { children: [
        /* @__PURE__ */ u$1("thead", { children: /* @__PURE__ */ u$1("tr", { children: [
          /* @__PURE__ */ u$1("th", { children: "Run" }),
          /* @__PURE__ */ u$1("th", { children: "Workload" }),
          /* @__PURE__ */ u$1("th", { children: "Plots" }),
          /* @__PURE__ */ u$1("th", { children: "Frontend" }),
          /* @__PURE__ */ u$1("th", { children: "Source" }),
          /* @__PURE__ */ u$1("th", { children: "Mode" }),
          /* @__PURE__ */ u$1("th", { children: "Rep" }),
          /* @__PURE__ */ u$1("th", { children: "Rate" })
        ] }) }),
        /* @__PURE__ */ u$1("tbody", { children: plan.jobs.slice(0, PREVIEW_LIMIT).map((job) => /* @__PURE__ */ u$1("tr", { children: [
          /* @__PURE__ */ u$1("td", { children: job.run_id }),
          /* @__PURE__ */ u$1("td", { children: job.scenario }),
          /* @__PURE__ */ u$1("td", { children: plotsLabel(job.config) }),
          /* @__PURE__ */ u$1("td", { children: job.frontend ?? "Receiver" }),
          /* @__PURE__ */ u$1("td", { children: job.backend }),
          /* @__PURE__ */ u$1("td", { children: job.mode }),
          /* @__PURE__ */ u$1("td", { children: job.repetition }),
          /* @__PURE__ */ u$1("td", { children: [
            job.config.hz,
            " Hz"
          ] })
        ] })) })
      ] }) }),
      /* @__PURE__ */ u$1("p", { class: "muted small", children: plan.jobs.length > PREVIEW_LIMIT ? `Showing the first ${PREVIEW_LIMIT} runs in the actual shuffled order. Use --dry-run --json for the full ${plan.run_count.toLocaleString()}-run schedule.` : "All planned runs shown in the actual shuffled order." })
    ] }) : !error && /* @__PURE__ */ u$1("p", { class: "muted", children: "Configure workloads above to preview the schedule." })
  ] });
}
function scope(preset) {
  const runs = preset.run_count.toLocaleString();
  const cases = preset.case_count.toLocaleString();
  return `${cases} workload${preset.case_count === 1 ? "" : "s"} · ${runs} run${preset.run_count === 1 ? "" : "s"} · ~${preset.minimum_minutes.toFixed(1)} min`;
}
function PresetCard(props) {
  const { preset } = props;
  const custom = preset.source === "custom";
  const fallback = custom ? "Saved from the editor." : "No description.";
  return /* @__PURE__ */ u$1(
    "button",
    {
      type: "button",
      class: (custom ? "preset preset-custom" : "preset") + (props.active === preset.path ? " preset-on" : ""),
      disabled: Boolean(preset.error),
      onClick: () => props.onPick(preset),
      title: preset.error ? preset.error : preset.path,
      children: [
        /* @__PURE__ */ u$1("span", { class: "preset-name", children: [
          preset.name,
          custom ? /* @__PURE__ */ u$1("span", { class: "badge badge-custom", children: "custom" }) : null,
          preset.kind === "probe" ? /* @__PURE__ */ u$1("span", { class: "badge", children: "probe" }) : null
        ] }),
        /* @__PURE__ */ u$1("span", { class: "preset-desc", children: preset.error ? `Unavailable: ${preset.error}` : preset.description || fallback }),
        /* @__PURE__ */ u$1("span", { class: "preset-scope", children: preset.error ? preset.filename : scope(preset) })
      ]
    }
  );
}
function PresetGallery(props) {
  const custom = props.presets.filter((preset) => preset.source === "custom");
  const bundled = props.presets.filter((preset) => preset.source !== "custom");
  return /* @__PURE__ */ u$1(S, { children: [
    custom.length ? /* @__PURE__ */ u$1("details", { class: "custom-box", open: true, children: [
      /* @__PURE__ */ u$1("summary", { children: [
        /* @__PURE__ */ u$1("span", { class: "custom-summary", children: "Your saved suites" }),
        /* @__PURE__ */ u$1("span", { class: "badge badge-custom", children: "scenarios_custom" }),
        /* @__PURE__ */ u$1("span", { class: "custom-count", children: custom.length })
      ] }),
      /* @__PURE__ */ u$1("div", { class: "preset-grid", children: custom.map((preset) => /* @__PURE__ */ u$1(PresetCard, { preset, active: props.active, onPick: props.onPick })) })
    ] }) : null,
    /* @__PURE__ */ u$1("div", { class: "preset-grid", children: [
      /* @__PURE__ */ u$1(
        "button",
        {
          type: "button",
          class: props.active === "blank" ? "preset preset-on preset-blank" : "preset preset-blank",
          onClick: props.onBlank,
          children: [
            /* @__PURE__ */ u$1("span", { class: "preset-name", children: "Blank" }),
            /* @__PURE__ */ u$1("span", { class: "preset-desc", children: "Start empty: one waveform workload at the source defaults." }),
            /* @__PURE__ */ u$1("span", { class: "preset-scope", children: "Build from scratch" })
          ]
        }
      ),
      bundled.map((preset) => /* @__PURE__ */ u$1(PresetCard, { preset, active: props.active, onPick: props.onPick }))
    ] })
  ] });
}
function RawJson(props) {
  const [open, setOpen] = d(false);
  const [text, setText] = d("");
  const [error, setError] = d(null);
  h(() => {
    if (!open) setText(JSON.stringify(props.suite, null, 2));
  }, [props.suite, open]);
  return /* @__PURE__ */ u$1(
    "details",
    {
      id: "advanced",
      class: "raw",
      open,
      onToggle: (event) => setOpen(event.target.open),
      children: [
        /* @__PURE__ */ u$1("summary", { children: "Advanced · edit complete suite JSON" }),
        /* @__PURE__ */ u$1("p", { class: "muted small", children: "Applying JSON replaces the form. Python validates it first and preserves unknown fields so errors point at the offending path." }),
        /* @__PURE__ */ u$1(
          "textarea",
          {
            id: "raw",
            rows: 16,
            spellcheck: false,
            "aria-label": "Complete suite JSON",
            value: text,
            onInput: (event) => setText(event.target.value)
          }
        ),
        error ? /* @__PURE__ */ u$1("p", { class: "alert", role: "alert", children: error }) : null,
        /* @__PURE__ */ u$1(
          "button",
          {
            type: "button",
            class: "btn-soft",
            onClick: async () => setError(await props.onApply(text)),
            children: "Apply JSON"
          }
        )
      ]
    }
  );
}
function ViewSegmented(props) {
  return /* @__PURE__ */ u$1("span", { class: "view-control", children: [
    /* @__PURE__ */ u$1("div", { class: "segmented", role: "group", "aria-label": "Plots", children: ENUMS.view.map((option) => /* @__PURE__ */ u$1(
      "button",
      {
        type: "button",
        class: props.value === option ? "seg seg-on" : "seg",
        "aria-pressed": props.value === option,
        onClick: () => props.onChange(option),
        children: option
      }
    )) }),
    /* @__PURE__ */ u$1(InfoTip, { text: VIEW_TIP })
  ] });
}
function parseAxisValues(text, isEnum) {
  const parts = text.split(",").map((value) => value.trim()).filter((value) => value !== "");
  if (isEnum) return parts;
  return parts.map((part) => {
    const n2 = Number(part);
    return Number.isFinite(n2) && Math.abs(n2) <= MAX_SAFE ? n2 : part;
  });
}
function AxesEditor(props) {
  const matrix = props.group.matrix;
  const used = Object.keys(matrix);
  const nextAxis = ALL_AXES.find((axis) => !used.includes(axis));
  const update = (matrixNext) => props.onChange({ ...props.group, matrix: matrixNext });
  const renameAxis = (from, to) => {
    const entries = Object.entries(matrix).map(([axis, values]) => [axis === from ? to : axis, values]);
    update(Object.fromEntries(entries));
  };
  return /* @__PURE__ */ u$1("div", { class: "axes", children: [
    /* @__PURE__ */ u$1("div", { class: "axes-head", children: [
      /* @__PURE__ */ u$1("h4", { children: "Matrix axes" }),
      /* @__PURE__ */ u$1(
        "button",
        {
          type: "button",
          class: "btn-soft",
          disabled: !nextAxis,
          onClick: () => nextAxis && update({ ...matrix, [nextAxis]: [] }),
          children: "+ Add axis"
        }
      )
    ] }),
    used.length === 0 ? /* @__PURE__ */ u$1("p", { class: "muted small", children: "Add one or more axes; every combination becomes a workload." }) : null,
    used.map((key) => {
      const isEnum = Boolean(ENUMS[key]);
      return /* @__PURE__ */ u$1("div", { class: "axis-row", children: [
        /* @__PURE__ */ u$1(Field, { label: "Vary field", children: /* @__PURE__ */ u$1(
          "select",
          {
            value: key,
            "aria-label": "Matrix field",
            onChange: (event) => renameAxis(key, event.target.value),
            children: [
              ALL_AXES.map((axis) => /* @__PURE__ */ u$1("option", { value: axis, disabled: axis !== key && used.includes(axis), children: axis })),
              ALL_AXES.includes(key) ? null : /* @__PURE__ */ u$1("option", { value: key, children: key })
            ]
          }
        ) }),
        /* @__PURE__ */ u$1(Field, { label: "Values", hint: "comma separated", children: /* @__PURE__ */ u$1(
          "input",
          {
            type: "text",
            value: (matrix[key] ?? []).join(", "),
            "aria-label": `Matrix ${key} values`,
            placeholder: isEnum ? ENUMS[key].join(", ") : "e.g. 10000, 100000",
            onInput: (event) => update({ ...matrix, [key]: parseAxisValues(event.target.value, isEnum) })
          }
        ) }),
        /* @__PURE__ */ u$1(
          "button",
          {
            type: "button",
            class: "btn-remove",
            "aria-label": `Remove ${key} axis`,
            onClick: () => {
              const rest = { ...matrix };
              delete rest[key];
              update(rest);
            },
            children: "Remove"
          }
        )
      ] });
    })
  ] });
}
function WorkloadCard(props) {
  const view = String(props.item.config.view ?? props.defaults.view);
  return /* @__PURE__ */ u$1("article", { class: "card", children: [
    /* @__PURE__ */ u$1("div", { class: "card-head", children: [
      /* @__PURE__ */ u$1(
        "input",
        {
          type: "text",
          class: "card-name",
          value: props.item.name,
          "aria-label": "Workload name",
          placeholder: "workload-name",
          onInput: (event) => props.onChange({ ...props.item, name: event.target.value })
        }
      ),
      /* @__PURE__ */ u$1(
        ViewSegmented,
        {
          value: view,
          onChange: (next) => props.onChange({ ...props.item, config: { ...props.item.config, view: next } })
        }
      ),
      /* @__PURE__ */ u$1("button", { type: "button", class: "btn-remove", onClick: props.onRemove, children: "Remove" })
    ] }),
    /* @__PURE__ */ u$1(
      ConfigFields,
      {
        config: props.item.config,
        defaults: props.defaults,
        onChange: (config) => props.onChange({ ...props.item, config })
      }
    )
  ] });
}
function GroupCard(props) {
  const base = props.group.base ?? {};
  const view = String(base.view ?? props.defaults.view);
  return /* @__PURE__ */ u$1("article", { class: "card", children: [
    /* @__PURE__ */ u$1("div", { class: "card-head", children: [
      /* @__PURE__ */ u$1(
        "input",
        {
          type: "text",
          class: "card-name",
          value: props.group.name,
          "aria-label": "Group name",
          placeholder: "group-name",
          onInput: (event) => props.onChange({ ...props.group, name: event.target.value })
        }
      ),
      /* @__PURE__ */ u$1(
        ViewSegmented,
        {
          value: view,
          onChange: (next) => props.onChange({ ...props.group, base: { ...base, view: next } })
        }
      ),
      /* @__PURE__ */ u$1("button", { type: "button", class: "btn-remove", onClick: props.onRemove, children: "Remove" })
    ] }),
    /* @__PURE__ */ u$1("div", { class: "base-block", children: [
      /* @__PURE__ */ u$1("p", { class: "block-label", children: "Base workload — axes below override these" }),
      /* @__PURE__ */ u$1(
        ConfigFields,
        {
          config: base,
          defaults: props.defaults,
          includeResolution: true,
          onChange: (next) => props.onChange({ ...props.group, base: next })
        }
      )
    ] }),
    /* @__PURE__ */ u$1(AxesEditor, { group: props.group, onChange: props.onChange })
  ] });
}
const TIMINGS = [
  { key: "warmup_seconds", label: "Warmup", hint: "seconds", decimal: true, tip: "Unmeasured seconds before each run so the renderer reaches steady state." },
  { key: "measurement_seconds", label: "Measured", hint: "seconds", decimal: true, tip: "The measured window per run, in seconds." },
  { key: "cooldown_seconds", label: "Cooldown", hint: "seconds", decimal: true, tip: "Idle seconds after each run before the next starts." },
  { key: "repetitions", label: "Repetitions", hint: "per combination", decimal: false, tip: "How many times each workload combination runs." },
  { key: "order_seed", label: "Run order seed", hint: "shuffle", decimal: false, tip: "Seed for the deterministic shuffle of run order across the campaign." }
];
function timingDefaults(kind) {
  const probe = kind === "probe";
  return {
    warmup_seconds: probe ? 2 : 5,
    measurement_seconds: probe ? 10 : 30,
    cooldown_seconds: probe ? 0.5 : 1,
    repetitions: 3,
    order_seed: 42
  };
}
function slugify(name) {
  return name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}
function uniqueName(suite, prefix) {
  const names = new Set([...suite.cases ?? [], ...suite.case_groups ?? []].map((item) => item.name));
  let n2 = 1;
  while (names.has(`${prefix}-${n2}`)) n2 += 1;
  return `${prefix}-${n2}`;
}
function blankSuite() {
  return {
    name: "custom-suite",
    frontends: ["pyqtgraph"],
    backends: ["rust"],
    modes: ["stream"],
    repetitions: 1,
    cases: [{ name: "workload-1", config: { view: "waveform" } }]
  };
}
function App() {
  const [options, setOptions] = d(null);
  const [presets, setPresets] = d([]);
  const [env, setEnv] = d(null);
  const [suite, setSuite] = d(null);
  const [kind, setKind] = d("run");
  const [active, setActive] = d(null);
  const [loadedSuite, setLoadedSuite] = d(null);
  const [loadedPath, setLoadedPath] = d(null);
  const [plan, setPlan] = d(null);
  const [previewError, setPreviewError] = d(null);
  const [pending, setPending] = d(false);
  const [filename, setFilename] = d("my-suite");
  const [saved, setSaved] = d(null);
  const [saveError, setSaveError] = d(null);
  const [loadError, setLoadError] = d(null);
  const revision = A(0);
  const importInput = A(null);
  h(() => {
    (async () => {
      try {
        const data = await fetchInitial();
        setOptions(data);
        setSuite(data.suite);
        setPresets(await fetchPresets());
        setEnv(await fetchEnvironment());
      } catch (failure) {
        setLoadError(`${failure.message ?? failure} Restart the matrix editor and reload this page.`);
      }
    })();
  }, []);
  h(() => {
    if (!suite) return;
    const rev = ++revision.current;
    setPending(true);
    const timer = setTimeout(async () => {
      try {
        const result = await preview(suite, kind);
        if (rev !== revision.current) return;
        setPlan(result);
        setPreviewError(null);
      } catch (failure) {
        if (rev !== revision.current) return;
        setPlan(null);
        setPreviewError(failure.message ?? String(failure));
      } finally {
        if (rev === revision.current) setPending(false);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [suite, kind]);
  h(() => {
    setSaved(null);
    setSaveError(null);
  }, [suite, kind]);
  const defaults = options?.config ?? {};
  const tDefaults = T(() => timingDefaults(kind), [kind]);
  if (loadError) {
    return /* @__PURE__ */ u$1("main", { children: /* @__PURE__ */ u$1("p", { class: "alert", role: "alert", children: loadError }) });
  }
  if (!options || !suite) {
    return /* @__PURE__ */ u$1("main", { children: /* @__PURE__ */ u$1("p", { class: "muted", children: "Loading the matrix editor…" }) });
  }
  const patch = (next) => setSuite({ ...suite, ...next });
  const setSelection = (key, fallback) => (value, checked) => {
    const current = new Set(suite[key] ?? fallback);
    if (checked) current.add(value);
    else current.delete(value);
    patch({ [key]: [...current] });
  };
  const setField = (key, value) => {
    const next = { ...suite };
    if (value === void 0 || value === "") delete next[key];
    else next[key] = value;
    setSuite(next);
  };
  const applyRaw = async (text) => {
    try {
      const result = await previewRaw(text, kind);
      setSuite(result.suite);
      setActive(null);
      setLoadedSuite(null);
      setLoadedPath(null);
      return null;
    } catch (failure) {
      return failure.message ?? String(failure);
    }
  };
  const pickPreset = (preset) => {
    setSuite(preset.suite);
    setKind(preset.kind);
    setActive(preset.path);
    setLoadedSuite(preset.suite);
    setLoadedPath(preset.path);
    if (preset.filename.endsWith(".json")) setFilename(preset.filename.replace(/\.json$/, ""));
  };
  const startBlank = () => {
    setSuite(blankSuite());
    setKind("run");
    setActive("blank");
    setLoadedSuite(null);
    setLoadedPath(null);
    setFilename("my-suite");
  };
  const exportJson = () => {
    const payload = plan?.suite ?? suite;
    const blob = new Blob([JSON.stringify(payload, null, 2) + "\n"], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${filename || "my-suite"}.json`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1e3);
  };
  const importJson = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 1024 * 1024) {
      setPreviewError("Suite JSON must be at most 1 MiB.");
      return;
    }
    const message = await applyRaw(await file.text());
    if (message) setPreviewError(message);
    if (importInput.current) importInput.current.value = "";
  };
  const save = async () => {
    if (!plan) return;
    try {
      const result = await saveSuite(plan.suite, filename, kind);
      setSaved(result);
      setSaveError(null);
      setActive(result.path);
      setLoadedSuite(suite);
      setLoadedPath(result.path);
      setPresets(await fetchPresets());
    } catch (failure) {
      setSaved(null);
      setSaveError(failure.message ?? String(failure));
    }
  };
  const probe = kind === "probe";
  const unchanged = loadedPath !== null && loadedSuite !== null && JSON.stringify(suite) === JSON.stringify(loadedSuite);
  const slug = slugify(filename) || "my-suite";
  const runPath = unchanged ? loadedPath : `scenarios_custom/${slug}.json`;
  const runStem = runPath.replace(/^.*\//, "").replace(/\.json$/, "") || "my-suite";
  const command = kind === "run" ? "run" : "probe";
  const liveCommands = [
    { label: "Preview", command: `./scripts/plotbench ${command} --suite ${runPath} --dry-run` },
    { label: "Full run", command: `./scripts/plotbench ${command} --suite ${runPath} --output results/${runStem}` }
  ];
  const recheckEnv = async () => setEnv(await fetchEnvironment());
  const selectedFrontends = probe ? [] : suite.frontends ?? options.frontends;
  const selectedBackends = suite.backends ?? [options.default_backend];
  const missing = [];
  if (env) {
    for (const name of selectedFrontends) {
      const status = env.frontends[name];
      if (status && !status.installed) missing.push({ name, setup: status.setup });
    }
    for (const name of selectedBackends) {
      const status = env.backends[name];
      if (status && !status.installed) missing.push({ name, setup: status.setup });
    }
  }
  const setupNames = [...new Set(missing.map((item) => item.setup).filter(Boolean))];
  const installCommand = setupNames.length ? `./scripts/setup ${setupNames.join(" ")}` : "";
  return /* @__PURE__ */ u$1("main", { children: [
    /* @__PURE__ */ u$1("header", { class: "app-header", children: [
      /* @__PURE__ */ u$1("p", { class: "eyebrow", children: "PLOTBENCH" }),
      /* @__PURE__ */ u$1("h1", { children: "Build a benchmark" }),
      /* @__PURE__ */ u$1("p", { class: "lede", children: "Pick a starting point, shape the workloads, preview the exact run order, then save a suite for the CLI." }),
      /* @__PURE__ */ u$1("p", { class: "muted small", children: "This editor runs locally and never launches measurements. Saving only writes JSON." })
    ] }),
    /* @__PURE__ */ u$1("section", { class: "panel", children: [
      /* @__PURE__ */ u$1("div", { class: "step", children: [
        /* @__PURE__ */ u$1("span", { class: "step-no", children: "1" }),
        /* @__PURE__ */ u$1("h2", { children: "Start from" })
      ] }),
      /* @__PURE__ */ u$1("p", { class: "muted small", children: "Presets are read-only starting points. Load one, then adjust — your changes are saved separately." }),
      /* @__PURE__ */ u$1(PresetGallery, { presets, active, onPick: pickPreset, onBlank: startBlank })
    ] }),
    /* @__PURE__ */ u$1("section", { class: "panel", children: [
      /* @__PURE__ */ u$1("div", { class: "step", children: [
        /* @__PURE__ */ u$1("span", { class: "step-no", children: "2" }),
        /* @__PURE__ */ u$1("h2", { children: "Execution" })
      ] }),
      /* @__PURE__ */ u$1("div", { class: "field-grid setup-grid", children: [
        /* @__PURE__ */ u$1(TextField, { label: "Suite name", value: suite.name ?? "", placeholder: "Describe this campaign", onInput: (v2) => setField("name", v2) }),
        /* @__PURE__ */ u$1("div", { class: "field", children: [
          /* @__PURE__ */ u$1("span", { class: "field-label", children: [
            "Preview command",
            /* @__PURE__ */ u$1(InfoTip, { text: GROUP_TIPS.kind })
          ] }),
          /* @__PURE__ */ u$1("select", { id: "kind", value: kind, onChange: (e2) => setKind(e2.target.value), children: [
            /* @__PURE__ */ u$1("option", { value: "run", children: "Frontend benchmark (run)" }),
            /* @__PURE__ */ u$1("option", { value: "probe", children: "Source receiver probe" })
          ] })
        ] }),
        /* @__PURE__ */ u$1(TextField, { label: "Display context", hint: "recorded with results", value: suite.display_context ?? "", placeholder: "Monitor, refresh rate, scaling, placement", onInput: (v2) => setField("display_context", v2) })
      ] }),
      /* @__PURE__ */ u$1("div", { class: "selections", children: [
        /* @__PURE__ */ u$1(ChipGroup, { legend: "Frontends", legendTip: GROUP_TIPS.frontends, tips: OPTION_TIPS, status: env?.frontends, options: options.frontends, selected: suite.frontends ?? options.frontends, disabled: probe, onToggle: setSelection("frontends", options.frontends) }),
        /* @__PURE__ */ u$1(ChipGroup, { legend: "Source backends", legendTip: GROUP_TIPS.backends, tips: OPTION_TIPS, status: env?.backends, options: options.backends, selected: suite.backends ?? [options.default_backend], onToggle: setSelection("backends", [options.default_backend]) }),
        /* @__PURE__ */ u$1(ChipGroup, { legend: "Delivery modes", legendTip: GROUP_TIPS.modes, tips: OPTION_TIPS, options: options.modes, selected: suite.modes ?? options.modes, disabled: probe, onToggle: setSelection("modes", options.modes) })
      ] }),
      probe ? /* @__PURE__ */ u$1("p", { class: "muted small", children: "Probe measures the source and delivery only; frontend and mode selections are ignored." }) : null,
      missing.length ? /* @__PURE__ */ u$1("div", { class: "install-hint", children: [
        /* @__PURE__ */ u$1("div", { class: "install-head", children: [
          /* @__PURE__ */ u$1("span", { class: "install-title", children: [
            "⚠ Not installed: ",
            missing.map((item) => item.name).join(", ")
          ] }),
          /* @__PURE__ */ u$1("button", { type: "button", class: "btn-soft", onClick: recheckEnv, children: "Re-check" })
        ] }),
        /* @__PURE__ */ u$1(CommandLine, { label: "Install", command: installCommand }),
        /* @__PURE__ */ u$1("p", { class: "muted small", children: [
          "Run this in your terminal, then Re-check. Verify with ",
          /* @__PURE__ */ u$1("code", { children: "./scripts/plotbench doctor" }),
          "."
        ] })
      ] }) : null,
      /* @__PURE__ */ u$1("div", { class: "field-grid timings-grid", children: TIMINGS.map((t2) => /* @__PURE__ */ u$1(
        NumberField,
        {
          label: t2.label,
          hint: t2.hint,
          tip: t2.tip,
          allowDecimal: t2.decimal,
          value: suite[t2.key],
          placeholder: tDefaults[t2.key],
          onChange: (v2) => setField(t2.key, v2)
        }
      )) })
    ] }),
    /* @__PURE__ */ u$1("section", { class: "panel", children: [
      /* @__PURE__ */ u$1("div", { class: "step", children: [
        /* @__PURE__ */ u$1("span", { class: "step-no", children: "3" }),
        /* @__PURE__ */ u$1("h2", { children: "Workloads" })
      ] }),
      /* @__PURE__ */ u$1("div", { class: "sub-head", children: [
        /* @__PURE__ */ u$1("p", { class: "muted small", children: "Each workload is one named case. Empty fields use the source defaults shown as placeholders." }),
        /* @__PURE__ */ u$1("button", { type: "button", class: "btn-soft", onClick: () => patch({ cases: [...suite.cases ?? [], { name: uniqueName(suite, "workload"), config: { view: "waveform" } }] }), children: "+ Add workload" })
      ] }),
      /* @__PURE__ */ u$1("div", { id: "cases", children: (suite.cases ?? []).map((item, index) => /* @__PURE__ */ u$1(
        WorkloadCard,
        {
          item,
          defaults,
          onChange: (next) => patch({ cases: (suite.cases ?? []).map((c2, i2) => i2 === index ? next : c2) }),
          onRemove: () => patch({ cases: (suite.cases ?? []).filter((_2, i2) => i2 !== index) })
        }
      )) }),
      /* @__PURE__ */ u$1("div", { class: "sub-head groups-head", children: [
        /* @__PURE__ */ u$1("p", { class: "muted small", children: "Groups expand every combination of their matrix axes. Axes override the base workload." }),
        /* @__PURE__ */ u$1("button", { type: "button", class: "btn-soft", onClick: () => patch({ case_groups: [...suite.case_groups ?? [], { name: uniqueName(suite, "group"), base: { view: "waveform" }, matrix: { points: [1e4, 1e5] } }] }), children: "+ Add group" })
      ] }),
      /* @__PURE__ */ u$1("div", { id: "groups", children: (suite.case_groups ?? []).map((group, index) => /* @__PURE__ */ u$1(
        GroupCard,
        {
          group,
          defaults,
          onChange: (next) => patch({ case_groups: (suite.case_groups ?? []).map((g2, i2) => i2 === index ? next : g2) }),
          onRemove: () => patch({ case_groups: (suite.case_groups ?? []).filter((_2, i2) => i2 !== index) })
        }
      )) })
    ] }),
    /* @__PURE__ */ u$1(
      PlanPreview,
      {
        plan,
        error: previewError,
        pending,
        commands: liveCommands,
        needsSave: !unchanged
      }
    ),
    saved ? /* @__PURE__ */ u$1(Launcher, { result: saved, onDismiss: () => setSaved(null) }) : null,
    /* @__PURE__ */ u$1(RawJson, { suite, onApply: applyRaw }),
    /* @__PURE__ */ u$1("div", { class: "action-bar", children: [
      /* @__PURE__ */ u$1("div", { class: "save-controls", children: [
        /* @__PURE__ */ u$1("label", { class: "field save-name", children: [
          /* @__PURE__ */ u$1("span", { class: "field-label", children: "File name" }),
          /* @__PURE__ */ u$1("div", { class: "save-name-row", children: [
            /* @__PURE__ */ u$1("span", { class: "prefix", children: "scenarios_custom/" }),
            /* @__PURE__ */ u$1("input", { type: "text", value: filename, "aria-label": "File name", onInput: (e2) => setFilename(e2.target.value) }),
            /* @__PURE__ */ u$1("span", { class: "suffix", children: ".json" })
          ] })
        ] }),
        /* @__PURE__ */ u$1("button", { type: "button", class: "btn-primary", disabled: !plan || !filename.trim(), onClick: save, title: !plan ? "Fix the preview errors first" : void 0, children: "Save to scenarios_custom" })
      ] }),
      /* @__PURE__ */ u$1("div", { class: "action-right", children: [
        /* @__PURE__ */ u$1("button", { type: "button", class: "btn-soft", disabled: !plan, onClick: exportJson, children: "Export JSON" }),
        /* @__PURE__ */ u$1("label", { class: "btn-soft file-btn", children: [
          "Import JSON",
          /* @__PURE__ */ u$1("input", { ref: importInput, type: "file", accept: ".json,application/json", onChange: importJson })
        ] })
      ] })
    ] }),
    saveError ? /* @__PURE__ */ u$1("p", { class: "alert action-alert", role: "alert", children: saveError }) : null
  ] });
}
const root = document.getElementById("root");
if (root) {
  root.textContent = "";
  R(/* @__PURE__ */ u$1(App, {}), root);
}
