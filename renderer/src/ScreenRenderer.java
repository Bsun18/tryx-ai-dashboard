package local.aimonitor.dashboard;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Rect;
import android.os.Looper;
import android.os.SystemClock;
import android.view.Surface;
import android.view.View;
import java.lang.reflect.*;

/** A temporary USB-launched display surface. Does not replace the vendor activity. */
public class ScreenRenderer {
    public static void main(String[] args) throws Exception {
        Looper.prepareMainLooper();
        Class<?> at=Class.forName("android.app.ActivityThread");
        Object thread=at.getMethod("systemMain").invoke(null);
        Context context=(Context)at.getMethod("getSystemContext").invoke(thread);
        Class<?> sc=Class.forName("android.view.SurfaceControl");
        Class<?> builderClass=Class.forName("android.view.SurfaceControl$Builder");
        Object builder=builderClass.getConstructor().newInstance();
        builderClass.getMethod("setName",String.class).invoke(builder,"AI-Telemetry");
        builderClass.getMethod("setBufferSize",int.class,int.class).invoke(builder,2240,1080);
        builderClass.getMethod("setFormat",int.class).invoke(builder,1);
        Object control=builderClass.getMethod("build").invoke(builder);
        Surface surface=Surface.class.getConstructor(sc).newInstance(control);
        Class<?> tc=Class.forName("android.view.SurfaceControl$Transaction");
        Object transaction=tc.getConstructor().newInstance();
        tc.getMethod("setLayer",sc,int.class).invoke(transaction,control,2000000000);
        tc.getMethod("setLayerStack",sc,int.class).invoke(transaction,control,0);
        tc.getMethod("show",sc).invoke(transaction,control);
        tc.getMethod("apply").invoke(transaction);
        MainActivity host=new MainActivity();
        MainActivity.Dash view=host.new Dash(context);
        view.measure(View.MeasureSpec.makeMeasureSpec(2240,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(1080,View.MeasureSpec.EXACTLY));
        view.layout(0,0,2240,1080);host.startTelemetry();
        System.out.println("AI_TELEMETRY_PORTABLE_SURFACE_READY pid="+android.os.Process.myPid());
        long started=SystemClock.elapsedRealtime();
        long duration=args.length>0?Long.parseLong(args[0]):0;
        BrightnessWindow brightness = new BrightnessWindow();
        brightness.start(context, args.length > 1 ? Integer.parseInt(args[1]) : 80);
        long end=duration>0?SystemClock.elapsedRealtime()+duration:Long.MAX_VALUE;
        try {
            while(SystemClock.elapsedRealtime()<end) {
                // A broken USB/data link releases the surface back to the vendor UI.
                long lastData=host.received>0?host.received:started;
                if(SystemClock.elapsedRealtime()-lastData>15000)break;
                Canvas canvas=surface.lockHardwareCanvas();
                try { view.draw(canvas); } finally { surface.unlockCanvasAndPost(canvas); }
                SystemClock.sleep(50);
            }
        } finally {
            host.running=false;
            brightness.close();
            Object removal=tc.getConstructor().newInstance();
            tc.getMethod("remove",sc).invoke(removal,control);tc.getMethod("apply").invoke(removal);
            surface.release();
        }
        System.exit(0);
    }
}
