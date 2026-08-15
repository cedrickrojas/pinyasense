(function registerPwa() {
  if (!('serviceWorker' in navigator)) {
    return;
  }

  window.addEventListener('load', async function onLoad() {
    try {
      await navigator.serviceWorker.register('/sw.js');
    } catch (error) {
      console.warn('Service worker registration failed:', error);
    }
  });
})();
