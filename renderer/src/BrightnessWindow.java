package local.aimonitor.dashboard;

import android.content.Context;
import android.graphics.PixelFormat;
import android.os.Handler;
import android.os.HandlerThread;
import android.view.View;
import android.view.WindowManager;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/** Process-owned brightness request; no global settings or app-op changes. */
final class BrightnessWindow {
    private final HandlerThread thread = new HandlerThread("Dashboard brightness");
    private Handler handler;
    private WindowManager manager;
    private View view;

    void start(final Context context, final int percent) {
        thread.start();
        handler = new Handler(thread.getLooper());
        handler.post(new Runnable() { public void run() {
            try {
                Context shell = context.createPackageContext("com.android.shell", 0);
                manager = (WindowManager)shell.getSystemService(Context.WINDOW_SERVICE);
                // TYPE_SECURE_SYSTEM_OVERLAY uses the shell's existing
                // INTERNAL_SYSTEM_WINDOW permission on the supported firmware.
                WindowManager.LayoutParams params = new WindowManager.LayoutParams(
                    1, 1, 2015, WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE |
                    WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE |
                    WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON, PixelFormat.TRANSLUCENT);
                params.screenBrightness = Math.max(1, Math.min(100, percent)) / 100f;
                params.setTitle("AI-Telemetry-Brightness");
                View candidate = new View(shell);
                manager.addView(candidate, params);
                view = candidate;
                System.out.println("AI_TELEMETRY_BRIGHTNESS=" + params.screenBrightness);
            } catch (Exception error) {
                System.err.println("Brightness control unavailable: " + error);
            }
        }});
    }

    void close() {
        if (handler == null) return;
        final CountDownLatch removed = new CountDownLatch(1);
        handler.post(new Runnable() { public void run() {
            try { if (view != null) manager.removeViewImmediate(view); }
            finally { removed.countDown(); thread.quitSafely(); }
        }});
        try { removed.await(2, TimeUnit.SECONDS); }
        catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); }
    }
}
