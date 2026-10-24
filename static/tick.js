// A clock for the status poll that keeps time while the window is hidden or minimized: browsers
// slow a hidden page's own timers down to once a minute, a worker's they leave alone. See
// everyTwoSeconds in app.js.
setInterval(() => postMessage(null), 2000);
