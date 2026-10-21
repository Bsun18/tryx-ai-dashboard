package local.aimonitor.dashboard;

import android.app.Activity;
import android.os.Bundle;
import android.os.SystemClock;
import android.graphics.*;
import android.view.*;
import org.json.JSONObject;
import java.io.*;
import java.net.*;
import java.util.Locale;

/** Native 2240 x 1080 layout approved on 2026-10-21. */
public class MainActivity extends Activity {
    volatile boolean running = true;
    volatile JSONObject data = new JSONObject();
    volatile long received = 0;
    Dash view;
    @Override public void onCreate(Bundle bundle) {
        super.onCreate(bundle);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON | WindowManager.LayoutParams.FLAG_FULLSCREEN);
        getWindow().getDecorView().setSystemUiVisibility(5894);
        view = new Dash(this); setContentView(view); startTelemetry();
    }
    void startTelemetry() {
        new Thread(new Runnable() { public void run() {
            while (running) {
                HttpURLConnection connection = null;
                try {
                    connection = (HttpURLConnection)new URL("http://127.0.0.1:18765/metrics").openConnection();
                    connection.setConnectTimeout(1800); connection.setReadTimeout(1800);
                    BufferedReader reader = new BufferedReader(new InputStreamReader(connection.getInputStream(), "UTF-8"));
                    String line = reader.readLine(); reader.close();
                    if (line != null) {
                        JSONObject incoming = new JSONObject(line);
                        // A responding HTTP server with a stalled sampler is not fresh telemetry.
                        if ("AI-Telemetry".equals(incoming.optString("app")) && incoming.optLong("seq", -1) >= 0
                                && incoming.optDouble("sample_age_s", 999) < 4) {
                            data = incoming; received = SystemClock.elapsedRealtime();
                        }
                    }
                } catch (Exception ignored) { }
                finally { if (connection != null) connection.disconnect(); }
                SystemClock.sleep(500);
            }
        }}, "USB telemetry").start();
    }
    @Override public void onDestroy() { running = false; super.onDestroy(); }

    class Dash extends View {
        final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG | Paint.SUBPIXEL_TEXT_FLAG);
        final int bg=Color.rgb(5,10,13), track=Color.rgb(26,42,51), grid=Color.rgb(19,33,42);
        final int dim=Color.rgb(145,165,178), white=Color.rgb(236,244,247);
        final int cyan=Color.rgb(72,217,237), lime=Color.rgb(197,235,114), amber=Color.rgb(243,186,121);
        final Typeface normal=Typeface.create("sans-serif",Typeface.NORMAL);
        final Typeface medium=Typeface.create("sans-serif-medium",Typeface.NORMAL);
        final Typeface bold=Typeface.create("sans-serif",Typeface.BOLD);
        final DashPathEffect dashed=new DashPathEffect(new float[]{13,7},0);
        static final int HISTORY_CAPACITY = 192; // 90 seconds at the supported 0.5-second interval.
        final float[][] histories = new float[4][HISTORY_CAPACITY];
        final double[] times = new double[HISTORY_CAPACITY];
        int count=0;
        long lastSeq=-1;
        String stream="";
        double timeNow=0;
        float animatedGpu=Float.NaN, animatedCpu=Float.NaN;
        JSONObject d=new JSONObject();
        boolean live=false;
        String previewLabel=null;

        Dash(android.content.Context context) { super(context); }
        boolean finite(float v) { return !Float.isNaN(v) && !Float.isInfinite(v); }
        boolean positive(float v) { return finite(v) && v > 0; }
        float val(String key) { return (float)d.optDouble(key,Double.NaN); }
        float clamp(float v) { return Math.max(0,Math.min(1,v)); }
        String fmt(float v,int digits) { return finite(v) ? String.format(Locale.US,"%."+digits+"f",v) : "—"; }
        String percent(float v,float max) {
            if (!finite(v) || !positive(max)) return "—";
            float ratio=v/max*100;
            return ratio>0 && ratio<0.1f ? "<0.1%" : fmt(ratio,ratio>0&&ratio<10?1:0)+"%";
        }
        String rate(float v) {
            if (!finite(v)) return "— MB/s";
            if (v>=1000) return fmt(v/1000,1)+" GB/s";
            if (v>=1) return fmt(v,v>=100?0:1)+" MB/s";
            return fmt(v*1000,v>=0.1f?0:1)+" KB/s";
        }
        void paint(int color,Paint.Style style) {
            p.setColor(color); p.setStyle(style); p.setPathEffect(null); p.setShader(null);
            p.setStrokeCap(Paint.Cap.BUTT); p.setStrokeJoin(Paint.Join.ROUND);
        }
        void fill(Canvas c,float x,float y,float w,float h,int color) {
            paint(color,Paint.Style.FILL); c.drawRect(x,y,x+Math.max(0,w),y+Math.max(0,h),p);
        }
        void text(Canvas c,String s,float x,float y,float size,int color,Paint.Align align,int weight) {
            paint(color,Paint.Style.FILL); p.setTypeface(weight>=700?bold:weight>=500?medium:normal);
            p.setTextSize(size); p.setTextAlign(align);
            float available=(y==120 && align==Paint.Align.LEFT)?570:(y==120 && align==Paint.Align.RIGHT)?340:0;
            if(available>0 && p.measureText(s)>available) {
                while(s.length()>1 && p.measureText(s+"…")>available)s=s.substring(0,s.length()-1);
                s+="…";
            }
            c.drawText(s,x,y,p);
        }
        void text(Canvas c,String s,float x,float y,float size,int color) {
            text(c,s,x,y,size,color,Paint.Align.LEFT,400);
        }
        void right(Canvas c,String s,float x,float y,float size,int color,int weight) {
            text(c,s,x,y,size,color,Paint.Align.RIGHT,weight);
        }
        void center(Canvas c,String s,float x,float y,float size,int color,int weight) {
            text(c,s,x,y,size,color,Paint.Align.CENTER,weight);
        }
        void line(Canvas c,float x,float y,float x2,float y2,int color,float width) {
            paint(color,Paint.Style.STROKE); p.setStrokeWidth(width); c.drawLine(x,y,x2,y2,p);
        }
        void arc(Canvas c,float x,float y,float r,float sweep,int color,float width) {
            if(sweep<=0)return;
            paint(color,Paint.Style.STROKE); p.setStrokeWidth(width);
            c.drawArc(new RectF(x-r,y-r,x+r,y+r),135,sweep,false,p);
        }
        void hbar(Canvas c,float x,float y,float w,float h,float value,float max,int color) {
            fill(c,x,y,w,h,track);
            if(finite(value)&&positive(max))fill(c,x,y,w*clamp(value/max),h,color);
        }
        void dial(Canvas c,String label,float value,float animated,int color) {
            float x=286,y=342,r=178;
            arc(c,x,y,r,270,track,20);
            if(finite(value))arc(c,x,y,r,270*clamp(animated/100),color,20);
            for(int i=0;i<=40;i++) {
                double a=Math.toRadians(135+i*270f/40);
                float co=(float)Math.cos(a),si=(float)Math.sin(a),inner=i%4==0?188:193;
                line(c,x+199*co,y+199*si,x+inner*co,y+inner*si,i%4==0?dim:track,i%4==0?3:2);
            }
            if(finite(value)) {
                double a=Math.toRadians(135+270*clamp(animated/100));
                float co=(float)Math.cos(a),si=(float)Math.sin(a);
                line(c,x+162*co,y+162*si,x+203*co,y+203*si,white,5);
            }
            center(c,label,x,278,38,dim,400);
            center(c,fmt(value,0),x,398,110,white,700);
            center(c,"%",x,468,38,color,400);
            center(c,"0",110,488,38,dim,400); center(c,"100",470,488,38,dim,400);
        }
        void temperature(Canvas c,float value,int color) {
            text(c,"TEMP °C",72,557,38,dim); right(c,fmt(value,0)+"°",500,557,54,white,700);
            hbar(c,72,578,428,24,value,100,color);
        }
        void memory(Canvas c,String label,float used,float total,int color) {
            text(c,label,555,191,38,dim); right(c,percent(used,total),1030,194,50,white,700);
            text(c,fmt(used,1)+" / "+fmt(total,1),555,248,47,white,Paint.Align.LEFT,500);
            right(c,"GiB",1030,248,38,dim,400); hbar(c,555,270,475,20,used,total,color);
        }
        void gpuMetrics(Canvas c) {
            memory(c,"VRAM",val("vram_used_gib"),val("vram_total_gib"),cyan);
            text(c,"MEM BUSY",555,347,38,dim); right(c,percent(val("gpu_mem_util"),100),1030,350,50,white,700);
            hbar(c,555,370,475,20,val("gpu_mem_util"),100,cyan);
            text(c,"GPU POWER",555,450,38,dim);
            text(c,fmt(val("gpu_power_w"),0)+" / "+fmt(val("gpu_power_limit_w"),0),555,510,47,white,Paint.Align.LEFT,500);
            right(c,"W",1030,510,38,dim,400);
            hbar(c,555,531,475,20,val("gpu_power_w"),val("gpu_power_limit_w"),cyan);
        }
        void cpuMetrics(Canvas c) {
            memory(c,"RAM",val("ram_used_gib"),val("ram_total_gib"),lime);
            text(c,"CPU POWER",555,347,38,dim);
            text(c,fmt(val("cpu_power_w"),0)+" W",555,410,61,white,Paint.Align.LEFT,500);
            text(c,"FAN",555,480,38,dim);
            text(c,fmt(val("fan_rpm"),0)+" RPM",555,543,61,white,Paint.Align.LEFT,500);
        }
        float niceScale(float value) {
            if(!positive(value))return 1;
            float power=(float)Math.pow(10,Math.floor(Math.log10(value))),n=value/power;
            return (n<=1?1:n<=2?2:n<=5?5:10)*power;
        }
        void plot(Canvas c,int firstSeries) {
            float x=48,y=811,w=738,h=110,max=1;
            for(int i=0;i<count;i++)if(timeNow-times[i]<=90) {
                for(int k=firstSeries;k<firstSeries+2;k++)if(finite(histories[k][i]))max=Math.max(max,histories[k][i]);
            }
            max=niceScale(max);
            for(int i=0;i<3;i++)line(c,x,y+i*h/2,x+w,y+i*h/2,grid,2);
            c.save(); c.clipRect(x,y,x+w,y+h);
            for(int series=0;series<2;series++) {
                Path path=new Path(); boolean first=true; float start=0,end=0; boolean any=false;
                for(int i=0;i<count;i++) {
                    float v=histories[firstSeries+series][i];
                    if(timeNow-times[i]>90 || !finite(v)) {first=true; continue;}
                    float px=x+w-(float)(Math.max(0,timeNow-times[i])/90)*w;
                    float py=y+h-clamp(v/max)*h;
                    if(first) {path.moveTo(px,py);first=false;} else path.lineTo(px,py);
                    if(!any)start=px;
                    end=px;any=true;
                }
                if(any) {
                    // Missing intervals remain broken; only the line carries history.
                    paint(series==0?cyan:amber,Paint.Style.STROKE); p.setStrokeWidth(4);
                    if(series==1)p.setPathEffect(dashed);
                    c.drawPath(path,p); p.setPathEffect(null);
                }
            }
            c.restore();
            text(c,"90s",x,960,38,dim); right(c,"AUTO "+rate(max),x+w,960,38,dim,400);
        }
        void vertical(Canvas c,float value,float max,float x,String label,int color) {
            float top=766,bottom=922,h=bottom-top,w=40;
            center(c,percent(value,max),x+w/2,746,38,white,500);
            fill(c,x,top,w,h,track);
            if(finite(value)&&positive(max))fill(c,x,bottom-h*clamp(value/max),w,h*clamp(value/max),color);
            center(c,label,x+w/2,960,38,dim,400);
        }
        void transfer(Canvas c,boolean gpu) {
            float a=val(gpu?"pcie_rx_mb_s":"nvme_read_mb_s"),b=val(gpu?"pcie_tx_mb_s":"nvme_write_mb_s");
            float maxA=val(gpu?"pcie_peak_mb_s":"nvme_read_peak_mb_s"),maxB=val(gpu?"pcie_peak_mb_s":"nvme_write_peak_mb_s");
            line(c,48,630,1030,630,track,2);
            text(c,gpu?"PCIe / GPU":d.optString("storage_title","DISK / I/O"),48,687,42,white,Paint.Align.LEFT,500);
            String basis=d.optString("storage_peak_basis","UNKNOWN");
            String caption=gpu?"MAX "+rate(maxA):basis.equals("LINK")?"LINK "+rate(maxA):basis.equals("REF")?"REF "+fmt(maxA/1000,2)+" / "+fmt(maxB/1000,2)+" GB/s":"MAX —";
            right(c,caption,1030,686,38,dim,400);
            text(c,gpu?"RX → GPU":"READ",48,736,38,cyan); text(c,gpu?"TX → HOST":"WRITE",435,736,38,amber);
            text(c,rate(a),48,790,49,white,Paint.Align.LEFT,500); text(c,rate(b),435,790,49,white,Paint.Align.LEFT,500);
            plot(c,gpu?0:2);
            vertical(c,a,maxA,854,gpu?"RX":"R",cyan); vertical(c,b,maxB,974,gpu?"TX":"W",amber);
        }
        void network(Canvas c,boolean gpu) {
            float value=val(gpu?"net_rx_mb_s":"net_tx_mb_s"),link=val("net_link_mbps"),max=positive(link)?link/8:Float.NaN;
            String speed=positive(link)?(link>=1000?fmt(link/1000,link%1000==0?0:1)+"G":fmt(link,0)+"M"):"—";
            line(c,48,982,1030,982,track,2);
            text(c,(gpu?"NET RX · ":"NET TX · ")+speed,48,1030,38,dim);
            center(c,rate(value),535,1030,44,white,500); right(c,percent(value,max),1030,1030,44,white,500);
            hbar(c,48,1045,982,14,value,max,gpu?cyan:amber);
        }
        void face(Canvas c,boolean gpu) {
            int color=gpu?cyan:lime;
            fill(c,0,0,1078,1080,bg); fill(c,48,43,7,59,color);
            text(c,gpu?"GPU / COMPUTE":"CPU / HOST",78,77,46,white,Paint.Align.LEFT,500);
            text(c,d.optString(gpu?"gpu_label":"cpu_label",gpu?"GPU":"CPU"),78,120,38,dim);
            right(c,gpu?d.optString("pcie_link","—").replace("GEN","G").replace("x","×"):d.optString("nvme_label","—"),1030,120,38,dim,400);
            right(c,previewLabel!=null?previewLabel:live?"USB LIVE":"NO DATA",1030,76,38,dim,400);
            dial(c,gpu?"GPU LOAD":"CPU LOAD",val(gpu?"gpu_util":"cpu_util"),gpu?animatedGpu:animatedCpu,color);
            temperature(c,val(gpu?"gpu_temp_c":"cpu_temp_c"),color);
            if(gpu)gpuMetrics(c); else cpuMetrics(c);
            transfer(c,gpu); network(c,gpu);
        }
        void history(long seq,long age) {
            String incoming=d.optString("stream_id","");
            if(!stream.equals(incoming)||seq<lastSeq) {count=0;lastSeq=-1;stream=incoming;}
            double sample=d.optDouble("sample_monotonic_s",SystemClock.elapsedRealtime()/1000.0);
            timeNow=sample+d.optDouble("sample_age_s",0)+age/1000.0;
            if(seq==lastSeq)return;
            if(count==HISTORY_CAPACITY) {
                System.arraycopy(times,1,times,0,HISTORY_CAPACITY-1);
                for(float[] values:histories)System.arraycopy(values,1,values,0,HISTORY_CAPACITY-1);
            } else count++;
            times[count-1]=sample;
            histories[0][count-1]=val("pcie_rx_mb_s"); histories[1][count-1]=val("pcie_tx_mb_s");
            histories[2][count-1]=val("nvme_read_mb_s"); histories[3][count-1]=val("nvme_write_mb_s");
            lastSeq=seq;
        }
        float smooth(float previous,float next) {
            return !finite(next)?Float.NaN:!finite(previous)?next:previous+(next-previous)*0.18f;
        }
        @Override protected void onDraw(Canvas c) {
            super.onDraw(c);
            d=data;
            long age=received==0?Long.MAX_VALUE:SystemClock.elapsedRealtime()-received;
            live=age<4000 && d.optDouble("sample_age_s",999)+age/1000.0<4;
            if(live)history(d.optLong("seq",-1),age);
            else {d=new JSONObject();count=0;lastSeq=-1;}
            animatedGpu=smooth(animatedGpu,val("gpu_util")); animatedCpu=smooth(animatedCpu,val("cpu_util"));
            c.drawColor(Color.BLACK);
            float scale=Math.min(getWidth()/2240f,getHeight()/1080f);
            c.save(); c.translate((getWidth()-2240*scale)/2,(getHeight()-1080*scale)/2); c.scale(scale,scale);
            face(c,true); c.save(); c.translate(1162,0); face(c,false); c.restore();
            line(c,1078,44,1078,1034,track,2); line(c,1162,44,1162,1034,track,2);
            c.restore();
            if(isAttachedToWindow())postInvalidateDelayed(50);
        }
    }
}
