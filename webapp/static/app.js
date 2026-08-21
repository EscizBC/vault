/**
 * MONO — Telegram Mini App магазин цифровых товаров.
 * Черно-белая тема, 4 вкладки, bottom-sheets, swipe-to-pay, админ-панель.
 */
(function () {
  'use strict';

  var tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  if (tg) {
    tg.ready();
    tg.expand();
    try {
      tg.setHeaderColor('#050505');
      tg.setBackgroundColor('#050505');
    } catch (e) { /* older clients */ }
  }

  /** Иконка CryptoBot — официальный аватар бота из интернета (по ТЗ). */
  var CRYPTOBOT_ICON = 'https://t.me/i/userpic/320/CryptoBot.jpg';

  // ------------------------------------------------------------------
  // API
  // ------------------------------------------------------------------

  function authHeaders() {
    var headers = { 'Content-Type': 'application/json' };
    if (tg && tg.initData) headers['Authorization'] = 'tma ' + tg.initData;
    return headers;
  }

  function api(path, options) {
    options = options || {};
    options.headers = authHeaders();
    return fetch(path, options).then(function (res) {
      if (!res.ok) {
        return res.json().catch(function () { return {}; }).then(function (body) {
          throw new Error(body.detail || 'Request failed (' + res.status + ')');
        });
      }
      return res.json();
    });
  }

  function get(path) { return api(path); }
  function post(path, body) { return api(path, { method: 'POST', body: JSON.stringify(body || {}) }); }
  function del(path) { return api(path, { method: 'DELETE' }); }

  function postForm(path, formData) {
    var headers = {};
    if (tg && tg.initData) headers['Authorization'] = 'tma ' + tg.initData;
    return fetch(path, { method: 'POST', headers: headers, body: formData }).then(function (res) {
      if (!res.ok) {
        return res.json().catch(function () { return {}; }).then(function (body) {
          throw new Error(body.detail || 'Request failed (' + res.status + ')');
        });
      }
      return res.json();
    });
  }

  function authImageUrl(path) {
    // Screenshot endpoints require auth headers; fetch as blob and objectURL.
    return fetch(path, { headers: authHeaders() })
      .then(function (res) {
        if (!res.ok) throw new Error('Failed to load image');
        return res.blob();
      })
      .then(function (blob) { return URL.createObjectURL(blob); });
  }

  // ------------------------------------------------------------------
  // State
  // ------------------------------------------------------------------

  var state = {
    items: [],
    cart: { items: [], total: 0, count: 0 },
    profile: null,
    purchases: [],
    view: 'home',
  };

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------

  function $(id) { return document.getElementById(id); }

  function money(v) { return '$' + Number(v || 0).toFixed(2); }

  function esc(str) {
    var div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
  }

  // Escape a string, then swap payment emojis for card brand logos.
  function brand(str) {
    return esc(str)
      .replace(/\uD83D\uDE08/g, '<img src="/static/images/mastercard.svg" class="brand-ico brand-mc" alt="Mastercard" />')
      .replace(/\uD83D\uDC79/g, '<img src="/static/images/visa.svg" class="brand-ico brand-visa" alt="Visa" />');
  }

  function fmtDate(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    return d.toLocaleDateString('en-US', { day: '2-digit', month: '2-digit', year: '2-digit' }) +
      ' ' + d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
  }

  function haptic(kind) {
    if (!tg || !tg.HapticFeedback) return;
    try {
      if (kind === 'success' || kind === 'error' || kind === 'warning') {
        tg.HapticFeedback.notificationOccurred(kind);
      } else {
        tg.HapticFeedback.impactOccurred(kind || 'light');
      }
    } catch (e) { /* noop */ }
  }

  function toast(text, isError) {
    var wrap = $('toast-wrap');
    var el = document.createElement('div');
    el.className = 'toast' + (isError ? ' error' : '');
    el.textContent = text;
    wrap.appendChild(el);
    setTimeout(function () {
      el.classList.add('out');
      setTimeout(function () { el.remove(); }, 350);
    }, 2400);
  }

  function copyText(text, label) {
    function done() { haptic('light'); toast(label || 'Copied'); }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { fallbackCopy(text); done(); });
    } else {
      fallbackCopy(text); done();
    }
  }

  function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch (e) { /* noop */ }
    ta.remove();
  }

  function showSuccess(title, sub) {
    var overlay = $('success-overlay');
    $('success-title').textContent = title || 'Done';
    $('success-sub').textContent = sub || '';
    overlay.classList.add('show');
    haptic('success');
    setTimeout(function () { overlay.classList.remove('show'); }, 1800);
  }

  // ------------------------------------------------------------------
  // Навигация по вкладкам
  // ------------------------------------------------------------------

  var navButtons = document.querySelectorAll('.nav-btn');

  function switchView(name) {
    if (state.view === name) return;
    state.view = name;
    haptic('light');
    document.querySelectorAll('.view').forEach(function (v) { v.classList.remove('active'); });
    var view = $('view-' + name);
    view.classList.add('active');
    navButtons.forEach(function (b) {
      var active = b.getAttribute('data-view') === name;
      b.classList.toggle('active', active);
      b.setAttribute('aria-current', active ? 'page' : 'false');
    });
    if (name === 'cart') loadCart();
    if (name === 'purchases') loadPurchases();
    if (name === 'profile') loadProfile();
  }

  navButtons.forEach(function (btn) {
    btn.addEventListener('click', function () { switchView(btn.getAttribute('data-view')); });
  });

  // ------------------------------------------------------------------
  // Каталог
  // ------------------------------------------------------------------

  function renderSkeletons() {
    var grid = $('items-grid');
    grid.innerHTML = '';
    for (var i = 0; i < 4; i++) {
      var sk = document.createElement('div');
      sk.className = 'card skeleton';
      sk.innerHTML = '<div class="card-img sk-shimmer"></div><div class="card-body">' +
        '<div class="sk-shimmer" style="height:14px;width:70%;border-radius:6px"></div>' +
        '<div class="sk-shimmer" style="height:11px;width:90%;border-radius:6px;margin-top:8px"></div>' +
        '<div class="sk-shimmer" style="height:24px;width:50%;border-radius:6px;margin-top:12px"></div></div>';
      grid.appendChild(sk);
    }
  }

  function renderItems() {
    var grid = $('items-grid');
    var empty = $('items-empty');
    grid.innerHTML = '';
    empty.classList.toggle('hidden', state.items.length > 0);
    state.items.forEach(function (item, idx) {
      var card = document.createElement('article');
      card.className = 'card';
      card.setAttribute('role', 'listitem');
      card.style.setProperty('--i', idx);
      var badge = item.in_stock
        ? '<span class="card-badge">' + item.stock + ' pcs</span>'
        : '<span class="card-badge sold-out">Sold out</span>';
      card.innerHTML =
        '<div class="card-img">' +
          (item.image_url ? '<img src="' + esc(item.image_url) + '" alt="' + esc(item.name) + '" loading="lazy" />' : '') +
          badge +
        '</div>' +
        '<div class="card-body">' +
        '<div class="card-name">' + brand(item.name) + '</div>' +
        '<div class="card-desc">' + brand(item.description) + '</div>' +
          '<div class="card-price mono">' + money(item.price) + '</div>' +
          '<button class="btn btn-primary btn-sm" type="button" ' + (item.in_stock ? '' : 'disabled') + '>' +
            (item.in_stock ? 'Add to cart' : 'Out of stock') +
          '</button>' +
        '</div>';
      card.querySelector('.card-img').addEventListener('click', function () { openItemSheet(item); });
      card.querySelector('.card-name').addEventListener('click', function () { openItemSheet(item); });
      var buyBtn = card.querySelector('button');
      buyBtn.addEventListener('click', function (ev) {
        ev.stopPropagation();
        addToCart(item.id, buyBtn);
      });
      grid.appendChild(card);
    });
  }

  var searchTimer = null;
  $('search-input').addEventListener('input', function (ev) {
    clearTimeout(searchTimer);
    var q = ev.target.value.trim();
    searchTimer = setTimeout(function () { loadItems(q); }, 300);
  });

  function loadItems(query) {
    return get('/api/items' + (query ? '?q=' + encodeURIComponent(query) : ''))
      .then(function (items) {
        state.items = items;
        renderItems();
      })
      .catch(function (err) { toast(err.message, true); });
  }

  function openItemSheet(item) {
    openSheet(item.name,
      '<div class="detail-img">' +
        (item.image_url ? '<img src="' + esc(item.image_url) + '" alt="' + esc(item.name) + '" />' : '') +
      '</div>' +
      '<div class="detail-row">' +
        '<span class="detail-price mono">' + money(item.price) + '</span>' +
        '<span class="detail-stock">' + (item.in_stock ? 'In stock: ' + item.stock : 'Out of stock') + '</span>' +
      '</div>' +
      '<p class="detail-desc">' + brand(item.description) + '</p>' +
      '<button id="sheet-add-btn" class="btn btn-primary" type="button" ' + (item.in_stock ? '' : 'disabled') + '>' +
        (item.in_stock ? 'Add to cart — ' + money(item.price) : 'Out of stock') +
      '</button>');
    var btn = $('sheet-add-btn');
    if (btn && item.in_stock) {
      btn.addEventListener('click', function () {
        addToCart(item.id, btn).then(closeSheet);
      });
    }
  }

  function addToCart(itemId, btn) {
    if (btn) btn.disabled = true;
    return post('/api/cart/add', { item_id: itemId, quantity: 1 })
      .then(function (cart) {
        state.cart = cart;
        updateCartBadge();
        haptic('medium');
        toast('Added to cart');
        flyToCart(btn);
      })
      .catch(function (err) { haptic('error'); toast(err.message, true); })
      .finally(function () { if (btn) btn.disabled = false; });
  }

  /** Микро-анимация: точка лет��т от кнопки к иконке корзины. */
  function flyToCart(fromEl) {
    var target = document.querySelector('.nav-btn[data-view="cart"]');
    if (!fromEl || !target) return;
    var a = fromEl.getBoundingClientRect();
    var b = target.getBoundingClientRect();
    var dot = document.createElement('div');
    dot.className = 'fly-dot';
    dot.style.left = (a.left + a.width / 2) + 'px';
    dot.style.top = (a.top + a.height / 2) + 'px';
    document.body.appendChild(dot);
    requestAnimationFrame(function () {
      dot.style.transform = 'translate(' + (b.left + b.width / 2 - a.left - a.width / 2) + 'px,' +
        (b.top + b.height / 2 - a.top - a.height / 2) + 'px) scale(0.2)';
      dot.style.opacity = '0';
    });
    setTimeout(function () { dot.remove(); }, 700);
  }

  function updateCartBadge() {
    var badge = $('cart-badge');
    var count = state.cart.count;
    badge.textContent = count > 0 ? count : '';
    badge.classList.toggle('show', count > 0);
    badge.classList.remove('pulse');
    if (count > 0) {
      void badge.offsetWidth;
      badge.classList.add('pulse');
    }
  }

  // ------------------------------------------------------------------
  // Корзина
  // ------------------------------------------------------------------

  function loadCart() {
    return get('/api/cart')
      .then(function (cart) {
        state.cart = cart;
        renderCart();
        updateCartBadge();
      })
      .catch(function (err) { toast(err.message, true); });
  }

  function renderCart() {
    var list = $('cart-list');
    var empty = $('cart-empty');
    var footer = $('cart-footer');
    list.innerHTML = '';
    var has = state.cart.items.length > 0;
    empty.classList.toggle('hidden', has);
    footer.classList.toggle('hidden', !has);
    resetPayZone();

    state.cart.items.forEach(function (row, idx) {
      var el = document.createElement('div');
      el.className = 'cart-row';
      el.style.setProperty('--i', idx);
      el.innerHTML =
        '<div class="cart-thumb">' +
          (row.image_url ? '<img src="' + esc(row.image_url) + '" alt="" />' : '') +
        '</div>' +
        '<div class="cart-info">' +
          '<div class="cart-name">' + brand(row.name) + '</div>' +
          '<div class="cart-unit mono">' + money(row.price) + ' each</div>' +
          '<div class="cart-sub mono">' + money(row.subtotal) + '</div>' +
        '</div>' +
        '<div class="qty">' +
          '<button type="button" aria-label="Decrease">−</button>' +
          '<span class="qty-n mono">' + row.quantity + '</span>' +
          '<button type="button" aria-label="Increase">+</button>' +
        '</div>';
      var btns = el.querySelectorAll('.qty button');
      btns[0].addEventListener('click', function () { setQty(row.item_id, row.quantity - 1); });
      btns[1].addEventListener('click', function () { setQty(row.item_id, row.quantity + 1); });
      list.appendChild(el);
    });
    $('cart-total').textContent = money(state.cart.total);
  }

  function setQty(itemId, qty) {
    haptic('light');
    var req = qty <= 0 ? del('/api/cart/' + itemId) : post('/api/cart/quantity', { item_id: itemId, quantity: qty });
    req.then(function (cart) {
      state.cart = cart;
      renderCart();
      updateCartBadge();
    }).catch(function (err) {
      haptic('error');
      toast(err.message, true);
      loadCart();
    });
  }

  // --------- Оплата: кнопка Pay -> фиксированная панель со свайпом внизу ---------

  function resetPayZone() {
    var zone = $('pay-zone');
    zone.innerHTML = '<button id="pay-btn" class="btn btn-primary" type="button">Pay</button>';
    $('pay-btn').addEventListener('click', showSwipeConfirm);
  }

  function closeSwipeOverlay() {
    var overlay = $('swipe-overlay');
    if (!overlay) return;
    overlay.classList.remove('show');
    setTimeout(function () { overlay.remove(); }, 280);
  }

  function showSwipeConfirm() {
    haptic('medium');
    var old = $('swipe-overlay');
    if (old) old.remove();

    var count = state.cart.count;
    var overlay = document.createElement('div');
    overlay.id = 'swipe-overlay';
    overlay.className = 'swipe-overlay';
    overlay.innerHTML =
      '<div class="swipe-panel" id="swipe-panel">' +
        '<div class="swipe-grabber" aria-hidden="true"></div>' +
        '<div class="swipe-summary">' +
          '<div class="swipe-summary-left">' +
            '<span class="swipe-summary-label">Total</span>' +
            '<span class="swipe-summary-items">' + count + (count === 1 ? ' item' : ' items') + '</span>' +
          '</div>' +
          '<span class="swipe-summary-total mono">' + money(state.cart.total) + '</span>' +
        '</div>' +
        '<div class="swipe-confirm" id="swipe-confirm">' +
          '<div class="swipe-fill" id="swipe-fill"></div>' +
          '<span class="swipe-label" id="swipe-label">' +
            'Slide to pay' +
            '<span class="swipe-chevrons" aria-hidden="true">' +
              '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="m9 18 6-6-6-6"/></svg>' +
              '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="m9 18 6-6-6-6"/></svg>' +
              '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="m9 18 6-6-6-6"/></svg>' +
            '</span>' +
          '</span>' +
          '<div class="swipe-knob" id="swipe-knob" role="slider" aria-label="Confirm payment" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0" tabindex="0">' +
            '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="m13 6 6 6-6 6"/></svg>' +
          '</div>' +
        '</div>' +
        '<button class="swipe-cancel" id="swipe-cancel" type="button">Cancel</button>' +
      '</div>';
    document.body.appendChild(overlay);

    $('swipe-cancel').addEventListener('click', function () {
      haptic('light');
      closeSwipeOverlay();
    });
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) closeSwipeOverlay();
    });

    // Show with a transition, then wire up the drag logic once the panel is laid out.
    requestAnimationFrame(function () {
      overlay.classList.add('show');
      requestAnimationFrame(initSwipe);
    });
  }

  function initSwipe() {
    var track = $('swipe-confirm');
    var knob = $('swipe-knob');
    var fill = $('swipe-fill');
    var label = $('swipe-label');
    if (!track || !knob) return;
    var dragging = false;
    var startX = 0;
    var pos = 0;
    var done = false;

    function maxPos() { return track.clientWidth - knob.offsetWidth - 10; }

    function setPos(p, animate) {
      pos = Math.max(0, Math.min(p, maxPos()));
      knob.style.transition = animate ? 'transform 0.25s cubic-bezier(0.22,1,0.36,1)' : 'none';
      fill.style.transition = animate ? 'width 0.25s cubic-bezier(0.22,1,0.36,1)' : 'none';
      knob.style.transform = 'translateX(' + pos + 'px)';
      fill.style.width = (pos + knob.offsetWidth + 10) + 'px';
      var pct = maxPos() > 0 ? Math.round((pos / maxPos()) * 100) : 0;
      knob.setAttribute('aria-valuenow', String(pct));
      label.style.opacity = String(Math.max(0, 1 - pos / (maxPos() * 0.6)));
    }

    function finish() {
      done = true;
      setPos(maxPos(), true);
      confirmCheckout();
    }

    knob.addEventListener('pointerdown', function (e) {
      if (done) return;
      e.preventDefault();
      dragging = true;
      startX = e.clientX - pos;
      try { knob.setPointerCapture(e.pointerId); } catch (err) { /* noop */ }
      haptic('light');
    });
    knob.addEventListener('pointermove', function (e) {
      if (!dragging || done) return;
      setPos(e.clientX - startX, false);
    });
    function release() {
      if (!dragging || done) return;
      dragging = false;
      if (pos >= maxPos() * 0.9) {
        finish();
      } else {
        setPos(0, true);
      }
    }
    knob.addEventListener('pointerup', release);
    knob.addEventListener('pointercancel', release);
    knob.addEventListener('keydown', function (e) {
      if (done) return;
      if (e.key === 'ArrowRight') {
        setPos(pos + maxPos() / 5, true);
        if (pos >= maxPos() * 0.9) finish();
      }
      if (e.key === 'ArrowLeft') setPos(pos - maxPos() / 5, true);
    });

    setPos(0, false);
  }

  function confirmCheckout() {
    haptic('heavy');
    var label = $('swipe-label');
    if (label) { label.textContent = 'Processing…'; label.style.opacity = '1'; }
    post('/api/cart/checkout')
      .then(function (result) {
        closeSwipeOverlay();
        showSuccess('Payment successful', 'Charged ' + money(result.total));
        state.cart = { items: [], total: 0, count: 0 };
        renderCart();
        updateCartBadge();
        loadProfile();
        resetPayZone();
        setTimeout(function () { switchView('purchases'); }, 1600);
      })
      .catch(function (err) {
        haptic('error');
        toast(err.message, true);
        closeSwipeOverlay();
        resetPayZone();
      });
  }

  // ------------------------------------------------------------------
  // Покупки
  // ------------------------------------------------------------------

  function loadPurchases() {
    return get('/api/purchases')
      .then(function (purchases) {
        state.purchases = purchases;
        renderPurchases();
      })
      .catch(function (err) { toast(err.message, true); });
  }

  function renderPurchases() {
    var list = $('purchase-list');
    var empty = $('purchases-empty');
    list.innerHTML = '';
    empty.classList.toggle('hidden', state.purchases.length > 0);
    state.purchases.forEach(function (p, idx) {
      var card = document.createElement('div');
      card.className = 'purchase-card';
      card.style.setProperty('--i', idx);
      card.innerHTML =
        '<button class="purchase-head" type="button" aria-expanded="false">' +
          '<span class="purchase-check" aria-hidden="true">' +
            '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>' +
          '</span>' +
          '<span class="purchase-meta">' +
            '<span class="purchase-name">' + brand(p.item_name) + '</span>' +
            '<span class="purchase-date">' + fmtDate(p.created_at) + '</span>' +
          '</span>' +
          '<span class="purchase-price mono">' + money(p.price) + '</span>' +
          '<span class="purchase-chevron" aria-hidden="true">' +
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="m6 9 6 6 6-6"/></svg>' +
          '</span>' +
        '</button>' +
        '<div class="purchase-data">' +
          '<div class="purchase-data-inner">' +
            '<code class="mono">' + esc(p.data || '—') + '</code>' +
            '<button class="copy-btn" type="button">' +
              '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>' +
              'Copy' +
            '</button>' +
          '</div>' +
        '</div>';
      var head = card.querySelector('.purchase-head');
      head.addEventListener('click', function () {
        var open = card.classList.toggle('open');
        head.setAttribute('aria-expanded', String(open));
        haptic('light');
      });
      card.querySelector('.copy-btn').addEventListener('click', function () {
        copyText(p.data || '', 'Data copied');
      });
      list.appendChild(card);
    });
  }

  // ------------------------------------------------------------------
  // Профиль
  // ------------------------------------------------------------------

  function loadProfile() {
    return get('/api/user')
      .then(function (profile) {
        state.profile = profile;
        renderProfile();
      })
      .catch(function (err) { toast(err.message, true); });
  }

  function renderProfile() {
    var p = state.profile;
    if (!p) return;
    var tgUser = tg && tg.initDataUnsafe && tg.initDataUnsafe.user ? tg.initDataUnsafe.user : null;
    var name = (tgUser && (tgUser.first_name + (tgUser.last_name ? ' ' + tgUser.last_name : ''))) || p.first_name || 'User';
    var username = (tgUser && tgUser.username) || p.username;
    var photo = (tgUser && tgUser.photo_url) || p.avatar_url;

    $('profile-name').textContent = name;
    $('profile-username').textContent = username ? '@' + username : '';
    $('profile-tgid').textContent = 'ID ' + p.telegram_id;
    var balEl = $('profile-balance');
    animateBalance(balEl, p.balance);
    balEl.classList.remove('bump');
    void balEl.offsetWidth;
    balEl.classList.add('bump');

    var avatar = $('profile-avatar');
    if (photo) {
      avatar.innerHTML = '<img src="' + esc(photo) + '" alt="" />';
    } else {
      avatar.textContent = (name || '?').charAt(0).toUpperCase();
    }
    $('admin-entry').classList.toggle('hidden', !p.is_admin);
  }

  /** Плавная анимация числа баланса. */
  function animateBalance(el, target) {
    var from = parseFloat((el.textContent || '0').replace(/[^0-9.]/g, '')) || 0;
    var start = null;
    var dur = 600;
    function frame(ts) {
      if (!start) start = ts;
      var t = Math.min(1, (ts - start) / dur);
      var eased = 1 - Math.pow(1 - t, 3);
      el.textContent = money(from + (target - from) * eased);
      if (t < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  // ------------------------------------------------------------------
  // Bottom Sheet
  // ------------------------------------------------------------------

  var sheetEl = $('sheet');
  var backdropEl = $('sheet-backdrop');

  function openSheet(title, html) {
    $('sheet-title').innerHTML = brand(title);
    $('sheet-body').innerHTML = html;
    sheetEl.classList.add('open');
    backdropEl.classList.add('show');
    haptic('light');
  }

  function closeSheet() {
    sheetEl.classList.remove('open');
    backdropEl.classList.remove('show');
  }

  $('sheet-close').addEventListener('click', closeSheet);
  backdropEl.addEventListener('click', closeSheet);

  document.querySelectorAll('[data-open-sheet]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var kind = btn.getAttribute('data-open-sheet');
      if (kind === 'topup') openTopUpSheet();
      if (kind === 'purchase-history') openPurchaseHistorySheet();
      if (kind === 'transactions') openTransactionsSheet();
      if (kind === 'admin') openAdminSheet();
    });
  });

  // ------------------------------------------------------------------
  // Пополнение баланса
  // ------------------------------------------------------------------

  function openTopUpSheet() {
    openSheet('Top up balance',
      '<div class="field"><label for="topup-amount">Amount, USD</label>' +
      '<input id="topup-amount" class="amount-input mono" type="number" inputmode="decimal" min="1" max="10000" placeholder="0.00" /></div>' +
      '<div class="quick-amounts">' +
        [10, 25, 50, 100].map(function (v) {
          return '<button class="btn btn-ghost btn-sm" type="button" data-amount="' + v + '">$' + v + '</button>';
        }).join('') +
      '</div>' +
      '<div class="method-grid">' +
        '<button class="method-btn" type="button" data-method="cryptobot">' +
          '<span class="method-icon"><img src="' + CRYPTOBOT_ICON + '" alt="CryptoBot" loading="lazy" ' +
            'onerror="this.replaceWith(Object.assign(document.createElement(\'span\'),{textContent:\'CB\',className:\'mono\'}))" /></span>' +
          'CryptoBot' +
          '<span class="chev"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="m9 18 6-6-6-6"/></svg></span>' +
        '</button>' +
        '<button class="method-btn" type="button" data-method="wallet">' +
          '<span class="method-icon"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12V7H5a2 2 0 0 1 0-4h14v4"/><path d="M3 5v14a2 2 0 0 0 2 2h16v-5"/><path d="M18 12a2 2 0 0 0 0 4h4v-4Z"/></svg></span>' +
          'Crypto wallets' +
          '<span class="chev"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="m9 18 6-6-6-6"/></svg></span>' +
        '</button>' +
      '</div>');

    var input = $('topup-amount');
    document.querySelectorAll('[data-amount]').forEach(function (b) {
      b.addEventListener('click', function () {
        input.value = b.getAttribute('data-amount');
        haptic('light');
      });
    });
    document.querySelectorAll('[data-method]').forEach(function (b) {
      b.addEventListener('click', function () {
        var amount = parseFloat(input.value);
        if (!amount || amount <= 0) { haptic('warning'); toast('Enter an amount', true); input.focus(); return; }
        if (b.getAttribute('data-method') === 'cryptobot') {
          startCryptoBotTopUp(amount, b);
        } else {
          openWalletsSheet(amount);
        }
      });
    });
  }

  function startCryptoBotTopUp(amount, btn) {
    btn.disabled = true;
    post('/api/user/topup/cryptobot', { amount: amount })
      .then(function (res) {
        closeSheet();
        toast('Invoice created — pay in CryptoBot');
        if (tg && res.pay_url) {
          tg.openTelegramLink(res.pay_url);
        } else if (res.pay_url) {
          window.open(res.pay_url, '_blank');
        }
      })
      .catch(function (err) { haptic('error'); toast(err.message, true); })
      .finally(function () { btn.disabled = false; });
  }

  function openWalletsSheet(amount) {
    openSheet('Top up — ' + money(amount),
      '<p class="view-sub">Send the exact amount to one of the addresses, attach a payment screenshot and tap &quot;I have paid&quot;. An administrator will review your request.</p>' +
      '<div id="wallets-list"><div class="sk-shimmer" style="height:64px;border-radius:14px"></div></div>' +
      '<img id="ws-preview" class="attach-preview" alt="Payment screenshot preview" style="display:none" />' +
      '<div class="attach-row">' +
        '<input id="ws-file" type="file" accept="image/*" class="sr-only" style="position:absolute;width:1px;height:1px;opacity:0" />' +
        '<button id="ws-attach" class="attach-btn" type="button">' +
          '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>' +
          'Attach screenshot' +
        '</button>' +
        '<span id="ws-filename" class="attach-name"></span>' +
      '</div>');

    var file = null;
    var fileInput = $('ws-file');
    $('ws-attach').addEventListener('click', function () { fileInput.click(); });
    fileInput.addEventListener('change', function () {
      file = fileInput.files && fileInput.files[0] ? fileInput.files[0] : null;
      var preview = $('ws-preview');
      var nameEl = $('ws-filename');
      var btn = $('ws-attach');
      if (file) {
        nameEl.textContent = file.name;
        btn.classList.add('has-file');
        preview.src = URL.createObjectURL(file);
        preview.style.display = 'block';
        haptic('light');
      } else {
        nameEl.textContent = '';
        btn.classList.remove('has-file');
        preview.style.display = 'none';
      }
    });

    get('/api/user/wallets')
      .then(function (wallets) {
        var list = $('wallets-list');
        if (!list) return;
        if (!wallets.length) {
          list.innerHTML = '<p class="view-sub">Wallets are temporarily unavailable</p>';
          return;
        }
        list.innerHTML = wallets.map(function (w, i) {
          return '<div class="wallet-row" style="--i:' + i + '">' +
            '<div class="wallet-label mono">' + esc(w.label) + '</div>' +
            '<div class="wallet-addr-row">' +
              '<code class="wallet-addr mono">' + esc(w.address) + '</code>' +
              '<button class="wallet-copy" type="button" data-addr="' + esc(w.address) + '" aria-label="Copy ' + esc(w.label) + ' address">' +
                '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>' +
              '</button>' +
            '</div>' +
            '<button class="btn btn-ghost btn-sm" type="button" data-paid="' + esc(w.key) + '">I have paid</button>' +
          '</div>';
        }).join('');
        list.querySelectorAll('.wallet-copy').forEach(function (b) {
          b.addEventListener('click', function () { copyText(b.getAttribute('data-addr'), 'Address copied'); });
        });
        list.querySelectorAll('[data-paid]').forEach(function (b) {
          b.addEventListener('click', function () {
            if (!file) {
              haptic('warning');
              toast('Please attach a payment screenshot first', true);
              return;
            }
            b.disabled = true;
            var fd = new FormData();
            fd.append('amount', String(amount));
            fd.append('wallet_key', b.getAttribute('data-paid'));
            fd.append('screenshot', file);
            postForm('/api/user/topup/wallet', fd)
              .then(function () {
                closeSheet();
                showSuccess('Request sent', 'Your balance will be credited after confirmation');
              })
              .catch(function (err) { haptic('error'); toast(err.message, true); b.disabled = false; });
          });
        });
      })
      .catch(function (err) { toast(err.message, true); });
  }

  // ------------------------------------------------------------------
  // История покупок / транзакций
  // ------------------------------------------------------------------

  function openPurchaseHistorySheet() {
    openSheet('Purchase history', '<div id="hist-list"><div class="sk-shimmer" style="height:56px;border-radius:14px"></div></div>');
    get('/api/purchases/history')
      .then(function (rows) {
        var list = $('hist-list');
        if (!list) return;
        if (!rows.length) { list.innerHTML = '<p class="view-sub">No purchases yet</p>'; return; }
        list.innerHTML = rows.map(function (r, i) {
          return '<div class="hist-row" style="--i:' + i + '">' +
            '<span class="hist-icon" aria-hidden="true"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg></span>' +
            '<span class="hist-main"><span class="hist-title">' + brand(r.item_name) + '</span>' +
            '<span class="hist-sub">' + fmtDate(r.created_at) + '</span></span>' +
            '<span class="hist-amount mono">−' + money(r.price) + '</span>' +
          '</div>';
        }).join('');
      })
      .catch(function (err) { toast(err.message, true); });
  }

  function openTransactionsSheet() {
    openSheet('Transaction history', '<div id="tx-list"><div class="sk-shimmer" style="height:56px;border-radius:14px"></div></div>');
    get('/api/user/transactions')
      .then(function (rows) {
        var list = $('tx-list');
        if (!list) return;
        if (!rows.length) { list.innerHTML = '<p class="view-sub">No transactions yet</p>'; return; }
        var statusLabel = { pending: 'Pending', completed: 'Completed', failed: 'Declined' };
        list.innerHTML = rows.map(function (r, i) {
          var isPlus = r.type === 'deposit' || r.type === 'admin_credit';
          var sign = isPlus ? '+' : '−';
          return '<div class="hist-row" style="--i:' + i + '">' +
            '<span class="hist-icon ' + (isPlus ? 'plus' : '') + '" aria-hidden="true">' +
              (isPlus
                ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M12 19V5"/><path d="m5 12 7-7 7 7"/></svg>'
                : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M12 5v14"/><path d="m19 12-7 7-7-7"/></svg>') +
            '</span>' +
            '<span class="hist-main"><span class="hist-title">' + esc(r.payment_method) + (r.comment ? ' · ' + esc(r.comment) : '') + '</span>' +
            '<span class="hist-sub">' + fmtDate(r.created_at) + '</span></span>' +
            '<span style="display:flex;flex-direction:column;align-items:flex-end;gap:3px">' +
              '<span class="hist-amount mono ' + (isPlus ? 'plus' : '') + '">' + sign + money(r.amount) + '</span>' +
              '<span class="hist-status ' + esc(r.status) + '">' + (statusLabel[r.status] || r.status) + '</span>' +
            '</span>' +
          '</div>';
        }).join('');
      })
      .catch(function (err) { toast(err.message, true); });
  }

  // ------------------------------------------------------------------
  // Админ-панель
  // ------------------------------------------------------------------

  function openAdminSheet() {
    openSheet('Админ-панель',
      '<div class="admin-tabs" role="tablist">' +
        '<button class="admin-tab active" type="button" data-atab="products" role="tab" aria-selected="true">Товары</button>' +
        '<button class="admin-tab" type="button" data-atab="requests" role="tab" aria-selected="false">Заявки</button>' +
        '<button class="admin-tab" type="button" data-atab="users" role="tab" aria-selected="false">Юзеры</button>' +
        '<button class="admin-tab" type="button" data-atab="broadcast" role="tab" aria-selected="false">Рассылка</button>' +
        '<button class="admin-tab" type="button" data-atab="wallets" role="tab" aria-selected="false">Кошельки</button>' +
      '</div>' +
      '<div id="admin-content"></div>');
    document.querySelectorAll('.admin-tab').forEach(function (t) {
      t.addEventListener('click', function () {
        document.querySelectorAll('.admin-tab').forEach(function (x) {
          x.classList.remove('active');
          x.setAttribute('aria-selected', 'false');
        });
        t.classList.add('active');
        t.setAttribute('aria-selected', 'true');
        renderAdminTab(t.getAttribute('data-atab'));
        haptic('light');
      });
    });
    renderAdminTab('products');
  }

  function renderAdminTab(tab) {
    var c = $('admin-content');
    if (!c) return;
    if (tab === 'products') renderAdminProducts(c);
    if (tab === 'requests') renderAdminRequests(c);
    if (tab === 'users') renderAdminUsers(c);
    if (tab === 'broadcast') renderAdminBroadcast(c);
    if (tab === 'wallets') renderAdminWallets(c);
  }

  // --------- Товары ---------

  function renderAdminProducts(c) {
    c.innerHTML =
      '<div class="field"><label for="ap-name">Название</label><input id="ap-name" type="text" maxlength="255" placeholder="Название товара" /></div>' +
      '<div class="field"><label for="ap-desc">Описание</label><textarea id="ap-desc" rows="2" maxlength="4000" placeholder="Краткое описание"></textarea></div>' +
      '<div class="field"><label for="ap-price">Цена, USD</label><input id="ap-price" class="mono" type="number" inputmode="decimal" min="0.01" placeholder="0.00" /></div>' +
      '<div class="field"><label>Фото товара</label>' +
        '<img id="ap-img-preview" class="attach-preview" alt="Превью фото товара" style="display:none" />' +
        '<div class="attach-row" style="margin:0">' +
          '<input id="ap-img-file" type="file" accept="image/*" style="position:absolute;width:1px;height:1px;opacity:0" aria-hidden="true" tabindex="-1" />' +
          '<button id="ap-img-btn" class="attach-btn" type="button">' +
            '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/></svg>' +
            'Загрузить фото' +
          '</button>' +
          '<span id="ap-img-status" class="attach-name"></span>' +
        '</div>' +
      '</div>' +
      '<div class="field"><label for="ap-img">или URL изображения</label><input id="ap-img" type="text" maxlength="512" placeholder="/static/images/… или https://…" /></div>' +
      '<div class="field"><label for="ap-units">Товарные единицы (по одной на строку)</label>' +
      '<textarea id="ap-units" class="mono" rows="4" placeholder="login:pass&#10;KEY-XXXX-YYYY"></textarea></div>' +
      '<button id="ap-save" class="btn btn-primary" type="button">Создать / пополнить</button>' +
      '<div id="ap-list" style="margin-top:16px"><div class="sk-shimmer" style="height:52px;border-radius:14px"></div></div>';

    var imgFile = $('ap-img-file');
    $('ap-img-btn').addEventListener('click', function () { imgFile.click(); });
    imgFile.addEventListener('change', function () {
      var f = imgFile.files && imgFile.files[0] ? imgFile.files[0] : null;
      if (!f) return;
      var status = $('ap-img-status');
      var btn = $('ap-img-btn');
      status.textContent = 'Загрузка…';
      btn.disabled = true;
      var fd = new FormData();
      fd.append('image', f);
      postForm('/api/admin/upload-image', fd)
        .then(function (res) {
          $('ap-img').value = res.url;
          var preview = $('ap-img-preview');
          preview.src = res.url;
          preview.style.display = 'block';
          status.textContent = f.name;
          btn.classList.add('has-file');
          haptic('light');
        })
        .catch(function (err) {
          haptic('error');
          toast(err.message, true);
          status.textContent = '';
        })
        .finally(function () { btn.disabled = false; });
    });

    $('ap-save').addEventListener('click', function () {
      var units = $('ap-units').value.split('\n').map(function (s) { return s.trim(); }).filter(Boolean);
      var body = {
        item_id: $('ap-save').getAttribute('data-item-id') ? Number($('ap-save').getAttribute('data-item-id')) : null,
        name: $('ap-name').value.trim(),
        description: $('ap-desc').value.trim(),
        price: parseFloat($('ap-price').value) || null,
        image_url: $('ap-img').value.trim(),
        units: units,
      };
      $('ap-save').disabled = true;
      post('/api/admin/restock', body)
        .then(function () {
          showSuccess('Сохранено', units.length ? 'Добавлено единиц: ' + units.length : '');
          $('ap-save').removeAttribute('data-item-id');
          $('ap-save').textContent = 'Создать / пополнить';
          ['ap-name', 'ap-desc', 'ap-price', 'ap-img', 'ap-units'].forEach(function (id) { $(id).value = ''; });
          $('ap-img-preview').style.display = 'none';
          $('ap-img-status').textContent = '';
          $('ap-img-btn').classList.remove('has-file');
          loadAdminProducts();
          loadItems();
        })
        .catch(function (err) { haptic('error'); toast(err.message, true); })
        .finally(function () { $('ap-save').disabled = false; });
    });
    loadAdminProducts();
  }

  function loadAdminProducts() {
    get('/api/admin/products')
      .then(function (rows) {
        var list = $('ap-list');
        if (!list) return;
        if (!rows.length) { list.innerHTML = '<p class="view-sub">Товаров нет</p>'; return; }
        list.innerHTML = rows.map(function (r, i) {
          return '<div class="admin-product-row" style="--i:' + i + '">' +
            '<div class="ap-main">' +
              '<span class="ap-name">' + brand(r.name) + '</span>' +
              '<span class="ap-meta mono">' + money(r.price) + ' · ' + r.stock + ' шт · продано ' + r.sold + '</span>' +
            '</div>' +
            '<button class="btn btn-ghost btn-sm" type="button" data-edit="' + r.id + '">Пополнить</button>' +
            '<button class="toggle ' + (r.is_active ? 'on' : '') + '" type="button" data-vis="' + r.id + '" data-val="' + (r.is_active ? '1' : '0') + '" role="switch" aria-checked="' + r.is_active + '" aria-label="Видимость ' + esc(r.name) + '"><span></span></button>' +
          '</div>';
        }).join('');
        list.querySelectorAll('[data-edit]').forEach(function (b) {
          b.addEventListener('click', function () {
            var row = rows.find(function (x) { return x.id === Number(b.getAttribute('data-edit')); });
            if (!row) return;
            $('ap-name').value = row.name;
            $('ap-desc').value = row.description;
            $('ap-price').value = row.price;
            $('ap-img').value = row.image_url || '';
            var preview = $('ap-img-preview');
            if (row.image_url) {
              preview.src = row.image_url;
              preview.style.display = 'block';
            } else {
              preview.style.display = 'none';
            }
            $('ap-save').setAttribute('data-item-id', String(row.id));
            $('ap-save').textContent = 'Обновить «' + row.name + '»';
            $('ap-name').scrollIntoView({ behavior: 'smooth', block: 'center' });
          });
        });
        list.querySelectorAll('[data-vis]').forEach(function (b) {
          b.addEventListener('click', function () {
            var visible = b.getAttribute('data-val') !== '1';
            post('/api/admin/visibility', { item_id: Number(b.getAttribute('data-vis')), visible: visible })
              .then(function () {
                b.classList.toggle('on', visible);
                b.setAttribute('data-val', visible ? '1' : '0');
                b.setAttribute('aria-checked', String(visible));
                haptic('light');
                loadItems();
              })
              .catch(function (err) { toast(err.message, true); });
          });
        });
      })
      .catch(function (err) { toast(err.message, true); });
  }

  // --------- Заявки на пополнение ---------

  function renderAdminRequests(c) {
    c.innerHTML = '<div class="sk-shimmer" style="height:80px;border-radius:14px"></div>';
    get('/api/admin/requests')
      .then(function (rows) {
        if (!rows.length) {
          c.innerHTML = '<p class="view-sub">Ожидающих заявок нет</p>';
          return;
        }
        c.innerHTML = rows.map(function (r) {
          var uname = r.user.username ? '@' + esc(r.user.username) : esc(r.user.first_name || r.user.telegram_id);
          return '<div class="req-card" data-req="' + r.id + '">' +
            '<div class="req-head">' +
              '<span class="req-user">' + uname + '</span>' +
              '<span class="req-amount mono">' + money(r.amount) + '</span>' +
            '</div>' +
            '<div class="req-meta">ID ' + esc(r.user.telegram_id) + ' · ' + esc(r.payment_method) + ' · ' + fmtDate(r.created_at) + ' · Заявка #' + r.id + '</div>' +
            (r.has_screenshot
              ? '<img class="req-shot" data-shot="' + r.id + '" alt="Скриншот оплаты — заявка #' + r.id + '" />'
              : '<p class="view-sub" style="margin-bottom:10px">Без скриншота</p>') +
            '<div class="req-actions">' +
              '<button class="btn btn-primary btn-sm" type="button" data-approve="' + r.id + '">Принять</button>' +
              '<button class="btn btn-ghost btn-sm" type="button" data-decline="' + r.id + '">Отклонить</button>' +
            '</div>' +
          '</div>';
        }).join('');

        c.querySelectorAll('[data-shot]').forEach(function (img) {
          authImageUrl('/api/admin/requests/' + img.getAttribute('data-shot') + '/screenshot')
            .then(function (url) { img.src = url; })
            .catch(function () { img.style.display = 'none'; });
        });

        function decide(id, approve, btn) {
          btn.disabled = true;
          post('/api/admin/requests/decision', { transaction_id: Number(id), approve: approve })
            .then(function () {
              showSuccess(approve ? 'Заявка принята' : 'Заявка отклонена');
              renderAdminRequests(c);
            })
            .catch(function (err) {
              haptic('error');
              toast(err.message, true);
              btn.disabled = false;
            });
        }
        c.querySelectorAll('[data-approve]').forEach(function (b) {
          b.addEventListener('click', function () { decide(b.getAttribute('data-approve'), true, b); });
        });
        c.querySelectorAll('[data-decline]').forEach(function (b) {
          b.addEventListener('click', function () { decide(b.getAttribute('data-decline'), false, b); });
        });
      })
      .catch(function (err) { toast(err.message, true); });
  }

  // --------- Пользователи ---------

  function renderAdminUsers(c) {
    c.innerHTML =
      '<div class="field"><label for="au-q">Telegram ID или @username</label>' +
      '<input id="au-q" type="text" placeholder="123456789 или @user" /></div>' +
      '<button id="au-find" class="btn btn-primary" type="button">Найти</button>' +
      '<div id="au-result"></div>';
    $('au-find').addEventListener('click', findAdminUser);
    $('au-q').addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.isComposing && e.keyCode !== 229) findAdminUser();
    });
  }

  function findAdminUser() {
    var q = $('au-q').value.trim();
    if (!q) return;
    get('/api/admin/user?q=' + encodeURIComponent(q))
      .then(function (u) {
        $('au-result').innerHTML =
          '<div class="found-user">' +
            '<div class="ap-main">' +
              '<span class="ap-name">' + esc(u.first_name || u.username || u.telegram_id) + (u.username ? ' · @' + esc(u.username) : '') + '</span>' +
              '<span class="ap-meta mono">ID ' + u.telegram_id + ' · Баланс ' + money(u.balance) + '</span>' +
            '</div>' +
          '</div>' +
          '<div class="field"><label for="au-amount">Сумма, USD</label>' +
          '<input id="au-amount" class="mono" type="number" inputmode="decimal" min="0.01" placeholder="0.00" /></div>' +
          '<div class="field"><label for="au-comment">Комментарий (виден в истории)</label>' +
          '<input id="au-comment" type="text" maxlength="512" placeholder="Причина" /></div>' +
          '<div class="seg">' +
            '<button id="au-credit" class="btn btn-primary" type="button">Начислить</button>' +
            '<button id="au-debit" class="btn btn-ghost" type="button">Списать</button>' +
          '</div>';
        function adjust(action) {
          var amount = parseFloat($('au-amount').value);
          if (!amount || amount <= 0) { toast('Введите сумму', true); return; }
          post('/api/admin/balance', {
            telegram_id: u.telegram_id,
            amount: amount,
            action: action,
            comment: $('au-comment').value.trim(),
          })
            .then(function (res) {
              showSuccess(action === 'credit' ? 'Начислено' : 'Списано', 'Новый баланс: ' + money(res.balance));
              findAdminUser();
            })
            .catch(function (err) { haptic('error'); toast(err.message, true); });
        }
        $('au-credit').addEventListener('click', function () { adjust('credit'); });
        $('au-debit').addEventListener('click', function () { adjust('debit'); });
      })
      .catch(function (err) {
        $('au-result').innerHTML = '<p class="view-sub" style="margin-top:12px">' + esc(err.message) + '</p>';
      });
  }

  // --------- Рассылка ---------

  function renderAdminBroadcast(c) {
    c.innerHTML =
      '<div class="field"><label for="ab-text">Текст (поддерживается HTML: &lt;b&gt;, &lt;i&gt;, &lt;a&gt;)</label>' +
      '<textarea id="ab-text" rows="4" maxlength="4000" placeholder="Текст сообщения"></textarea></div>' +
      '<div class="field"><label for="ab-photo">URL фото (необязательно)</label>' +
      '<input id="ab-photo" type="text" maxlength="512" placeholder="https://…" /></div>' +
      '<div class="broadcast-preview" id="ab-preview" aria-live="polite"></div>' +
      '<button id="ab-send" class="btn btn-primary" type="button">Отправить</button>' +
      '<div id="ab-result" class="broadcast-stats"></div>';

    get('/api/admin/broadcast/recipients')
      .then(function (r) {
        var el = $('ab-preview');
        if (el) el.textContent = 'Получателей: ' + r.count;
      })
      .catch(function () { /* noop */ });

    $('ab-send').addEventListener('click', function () {
      var text = $('ab-text').value.trim();
      if (!text) { toast('Введите текст', true); return; }
      $('ab-send').disabled = true;
      $('ab-send').textContent = 'Отправка…';
      post('/api/admin/broadcast', { text: text, photo_url: $('ab-photo').value.trim() })
        .then(function (r) {
          $('ab-result').innerHTML =
            '<span class="bstat">Доставлено: <b class="mono">' + r.sent + '</b></span>' +
            '<span class="bstat">Не доставлено: <b class="mono">' + r.failed + '</b></span>';
          showSuccess('Рассылка завершена', 'Доставлено: ' + r.sent);
        })
        .catch(function (err) { haptic('error'); toast(err.message, true); })
        .finally(function () {
          $('ab-send').disabled = false;
          $('ab-send').textContent = 'Отправить';
        });
    });
  }

  // --------- Кошельки ---------

  function renderAdminWallets(c) {
    c.innerHTML = '<div class="sk-shimmer" style="height:52px;border-radius:14px"></div>';
    get('/api/admin/wallets')
      .then(function (w) {
        c.innerHTML =
          '<div class="field"><label for="aw-btc">BTC</label><input id="aw-btc" class="mono" type="text" maxlength="128" value="' + esc(w.wallet_btc || '') + '" /></div>' +
          '<div class="field"><label for="aw-eth">ETH</label><input id="aw-eth" class="mono" type="text" maxlength="128" value="' + esc(w.wallet_eth || '') + '" /></div>' +
          '<div class="field"><label for="aw-usdt">USDT TRC20</label><input id="aw-usdt" class="mono" type="text" maxlength="128" value="' + esc(w.wallet_usdt_trc20 || '') + '" /></div>' +
          '<button id="aw-save" class="btn btn-primary" type="button">Сохранить</button>';
        $('aw-save').addEventListener('click', function () {
          $('aw-save').disabled = true;
          post('/api/admin/wallets', {
            wallet_btc: $('aw-btc').value.trim(),
            wallet_eth: $('aw-eth').value.trim(),
            wallet_usdt_trc20: $('aw-usdt').value.trim(),
          })
            .then(function () { showSuccess('Кошельки обновлены'); })
            .catch(function (err) { haptic('error'); toast(err.message, true); })
            .finally(function () { $('aw-save').disabled = false; });
        });
      })
      .catch(function (err) { toast(err.message, true); });
  }

  // ------------------------------------------------------------------
  // Falling credit cards backdrop
  // ------------------------------------------------------------------

  function initCardsRain() {
    var wrap = $('cards-rain');
    if (!wrap) return;
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    var COUNT = 14;
    for (var i = 0; i < COUNT; i++) {
      var card = document.createElement('div');
      card.className = 'rain-card';
      card.style.setProperty('--x', (Math.random() * 100).toFixed(1) + '%');
      card.style.setProperty('--w', (38 + Math.random() * 42).toFixed(0) + 'px');
      card.style.setProperty('--dur', (9 + Math.random() * 10).toFixed(1) + 's');
      card.style.setProperty('--delay', (-Math.random() * 18).toFixed(1) + 's');
      card.style.setProperty('--r0', (-40 + Math.random() * 80).toFixed(0) + 'deg');
      card.style.setProperty('--r1', (-60 + Math.random() * 120).toFixed(0) + 'deg');
      card.style.setProperty('--op', (0.08 + Math.random() * 0.14).toFixed(2));
      wrap.appendChild(card);
    }
  }

  // ------------------------------------------------------------------
  // Init
  // ------------------------------------------------------------------

  initCardsRain();
  renderSkeletons();
  loadItems();
  loadCart();
  loadProfile();
})();
