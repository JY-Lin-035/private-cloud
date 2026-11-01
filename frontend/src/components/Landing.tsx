const FEATURES = [
  { h: "檔案協作與即時共編", p: "邀請夥伴一起編輯文件，編輯者／檢視者權限涇渭分明，變更即時同步。" },
  { h: "加密分享連結", p: "一條連結一套權限：可設密碼、到期日，並能隨時撤銷。" },
  { h: "隱私自主", p: "你的資料存在自己管理的伺服器上，不依賴第三方平台。" },
];

const FAQ = [
  { q: "需要安裝 App 嗎？", a: "不用，開瀏覽器即用，支援手機與桌面裝置。" },
  { q: "支援哪些檔案預覽？", a: "影片、音樂、圖片、PDF、Office 文件格式與文字／程式碼皆可線上預覽，純文字類可直接編輯。" },
  { q: "分享出去的連結安全嗎？", a: "分享連結可加密碼、設效期，撤銷後即時失效。" },
];

export function LandingIntro() {
  return (
    <section className="px-6 pt-8 pb-2 text-center" aria-label="MeowCloud 简介">
      <h1 className="text-2xl sm:text-3xl font-bold text-white drop-shadow">MeowCloud｜個人雲端儲存</h1>
      <p className="mt-2 text-sm sm:text-base text-gray-200 max-w-xl mx-auto leading-relaxed">
        把檔案放上自己的雲端：上傳、瀏覽、協作、共編，在瀏覽器裡完成，手機電腦免安裝。
      </p>
    </section>
  );
}

export function LandingDetail() {
  return (
    <section className="px-6 py-10 max-w-2xl mx-auto" aria-label="功能與常見問題">
      {FEATURES.map((f) => (
        <div key={f.h} className="mb-6">
          <h2 className="text-lg font-semibold text-white">{f.h}</h2>
          <p className="text-sm text-gray-200 leading-relaxed">{f.p}</p>
        </div>
      ))}
      <h2 className="text-lg font-semibold text-white mt-8 mb-3">常見問題</h2>
      {FAQ.map((x) => (
        <div key={x.q} className="mb-4">
          <h3 className="text-base font-medium text-white">{x.q}</h3>
          <p className="text-sm text-gray-200 leading-relaxed">{x.a}</p>
        </div>
      ))}
    </section>
  );
}
