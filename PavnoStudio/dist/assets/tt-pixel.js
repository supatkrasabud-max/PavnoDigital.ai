/* TikTok Pixel for www.pavnodigital.com (Events Manager pixel "PAVNO Web").
   The pixel ID is public, not a secret. Events: PageView on every page,
   ViewContent on /product/, InitiateCheckout on Stripe buy-link clicks,
   CompletePayment on /thanks/ once the payment is confirmed. */
(function () {
  var PIXEL_ID = 'DC1FGOBC77U6QF2MTLVG';
  var LAST_KEY = 'pavno-tt-last-checkout';

  !function (w, d, t) {
    w.TiktokAnalyticsObject=t;var ttq=w[t]=w[t]||[];ttq.methods=["page","track","identify","instances","debug","on","off","once","ready","alias","group","enableCookie","disableCookie","holdConsent","revokeConsent","grantConsent"],ttq.setAndDefer=function(t,e){t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}};for(var i=0;i<ttq.methods.length;i++)ttq.setAndDefer(ttq,ttq.methods[i]);ttq.instance=function(t){for(
    var e=ttq._i[t]||[],n=0;n<ttq.methods.length;n++)ttq.setAndDefer(e,ttq.methods[n]);return e},ttq.load=function(e,n){var r="https://analytics.tiktok.com/i18n/pixel/events.js",o=n&&n.partner;ttq._i=ttq._i||{},ttq._i[e]=[],ttq._i[e]._u=r,ttq._t=ttq._t||{},ttq._t[e]=+new Date,ttq._o=ttq._o||{},ttq._o[e]=n||{};n=document.createElement("script")
    ;n.type="text/javascript",n.async=!0,n.src=r+"?sdkid="+e+"&lib="+t;e=document.getElementsByTagName("script")[0];e.parentNode.insertBefore(n,e)};
    ttq.load(PIXEL_ID);
    ttq.page();
  }(window, document, 'ttq');

  function track(name, data, opts) {
    try { window.ttq.track(name, data || {}, opts || {}); } catch (e) { /* never break the page */ }
  }

  function products() {
    try { return typeof LAUNCH_PRODUCTS !== 'undefined' ? LAUNCH_PRODUCTS : []; } catch (e) { return []; }
  }

  function byId(id) {
    var list = products();
    for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i];
    return null;
  }

  function idForLink(href) {
    try {
      if (typeof PAY_LINKS === 'undefined') return '';
      for (var id in PAY_LINKS) if (Object.prototype.hasOwnProperty.call(PAY_LINKS, id) && PAY_LINKS[id] === href) return id;
    } catch (e) {}
    return '';
  }

  function payload(id) {
    var p = byId(id);
    var price = p && typeof p.price === 'number' ? p.price : 0;
    return {
      contents: [{ content_id: id, content_type: 'product', content_name: p ? p.name : id, quantity: 1, price: price }],
      value: price,
      currency: 'THB'
    };
  }

  // Buy-button clicks (links are rendered later by page scripts, so listen on the document).
  document.addEventListener('click', function (ev) {
    var a = ev.target && ev.target.closest ? ev.target.closest('a[href^="https://buy.stripe.com/"]') : null;
    if (!a) return;
    var id = a.dataset.buy || idForLink(a.href);
    if (!id) { track('InitiateCheckout', { currency: 'THB' }); return; }
    track('InitiateCheckout', payload(id));
    try { localStorage.setItem(LAST_KEY, JSON.stringify({ id: id, at: Date.now() })); } catch (e) {}
  }, true);

  window.addEventListener('DOMContentLoaded', function () {
    if (/^\/product\/?$/.test(location.pathname)) {
      var id = new URLSearchParams(location.search).get('id') || '';
      if (id && byId(id)) track('ViewContent', payload(id));
    }
  });

  // Called by /thanks/ only after /api/download confirms the payment.
  window.pavnoTrackPurchase = function (sessionId) {
    var last = null;
    try { last = JSON.parse(localStorage.getItem(LAST_KEY) || 'null'); } catch (e) {}
    var fresh = last && last.id && Date.now() - last.at < 6 * 60 * 60 * 1000;
    var data = fresh ? payload(last.id) : { currency: 'THB' };
    track('CompletePayment', data, sessionId ? { event_id: 'cs_' + String(sessionId).slice(-40) } : {});
    try { localStorage.removeItem(LAST_KEY); } catch (e) {}
  };
})();
