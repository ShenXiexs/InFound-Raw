<template>
  <main class="embed-page">
    <section class="embed-card">
      <p class="eyebrow">Infound Embed</p>
      <h1>RPA 正式宿主不是这里</h1>
      <p class="body">
        当前 seller RPA 的正式宿主是 <code>frontend.desktop</code>，<code>frontend.embed</code>
        不承载任务调度、worker 生命周期或 Playwright 执行链路。
      </p>
      <p class="body">
        如果需要调试执行引擎，请使用 <code>frontend.rpa.simulation</code>；如果需要走正式链路，请从
        <code>frontend.desktop</code> 进入。
      </p>
    </section>
  </main>
</template>

<style scoped>
.embed-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  margin: 0;
  background:
    radial-gradient(circle at top, rgba(22, 163, 74, 0.12), transparent 35%),
    linear-gradient(180deg, #f7f8f2 0%, #eef1e7 100%);
  color: #182019;
  font-family: 'SF Pro Display', 'Helvetica Neue', sans-serif;
}

.embed-card {
  width: min(680px, calc(100vw - 48px));
  padding: 32px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(24, 32, 25, 0.08);
  box-shadow: 0 24px 60px rgba(24, 32, 25, 0.08);
}

.eyebrow {
  margin: 0 0 12px;
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #4d6b52;
}

h1 {
  margin: 0 0 16px;
  font-size: 34px;
  line-height: 1.05;
}

.body {
  margin: 0 0 12px;
  font-size: 16px;
  line-height: 1.7;
  color: #304233;
}

code {
  padding: 2px 6px;
  border-radius: 8px;
  background: #edf5ea;
  color: #17351d;
}
</style>
