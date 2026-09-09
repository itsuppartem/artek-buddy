import {
  isIosDevice,
  isStandaloneDisplay,
  pageSurface,
  shouldShowHomeScreenHint,
} from "../../lib/web-notify";

export function HostPhoneBanners({
  alertOffer,
  hintDismissed,
  onDismissHint,
  onAlertPermission,
}: {
  alertOffer: "hide" | "ask" | "ready";
  hintDismissed: boolean;
  onDismissHint: () => void;
  onAlertPermission: (permission: NotificationPermission) => void;
}) {
  const showHint =
    !hintDismissed &&
    shouldShowHomeScreenHint({
      surface: "host",
      ios: isIosDevice(),
      standalone: isStandaloneDisplay(),
    });
  if (pageSurface() !== "host" || (!showHint && alertOffer !== "ask")) return null;
  return (
    <div
      data-testid="phone-host-banners"
      className="flex shrink-0 flex-col gap-2 border-b border-hairline px-3 pb-2 pt-3"
    >
      {showHint ? (
        <div className="flex items-start gap-2 rounded-[10px] border border-hairline bg-plate px-3 py-2">
          <p
            data-testid="home-screen-hint"
            className="min-w-0 flex-1 text-[13px] leading-5 text-paper"
          >
            Share → Add to Home Screen, then open that icon. iPhone alerts need it and only work
            while this app is open.
          </p>
          <button
            type="button"
            className="shrink-0 pt-0.5 text-[13px] font-medium text-tan"
            onClick={onDismissHint}
          >
            Got it
          </button>
        </div>
      ) : null}
      {alertOffer === "ask" ? (
        <button
          type="button"
          data-testid="turn-on-alerts"
          className="rounded-[10px] border border-tan bg-plate px-3 py-2 text-left text-[13px] font-medium text-paper"
          onClick={() => {
            if (typeof Notification === "undefined") return;
            void Notification.requestPermission().then(onAlertPermission);
          }}
        >
          Turn on alerts — only while this app is open
        </button>
      ) : null}
    </div>
  );
}
