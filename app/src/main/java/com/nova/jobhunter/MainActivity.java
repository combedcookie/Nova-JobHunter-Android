package com.nova.jobhunter;
import android.app.Activity;
import android.os.Bundle;
import android.content.Intent;
import android.net.Uri;
import android.webkit.*;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import org.json.*;
import java.net.*;
import java.io.*;
import java.security.KeyStore;
import javax.crypto.*;
import javax.crypto.spec.GCMParameterSpec;
import java.nio.charset.StandardCharsets;
import android.app.Activity;
import android.provider.OpenableColumns;
import android.database.Cursor;
import android.content.ContentResolver;
import android.webkit.MimeTypeMap;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipEntry;
import java.util.regex.Pattern;
import java.util.regex.Matcher;
import com.tom_roush.pdfbox.android.PDFBoxResourceLoader;
import com.tom_roush.pdfbox.pdmodel.PDDocument;
import com.tom_roush.pdfbox.text.PDFTextStripper;

public class MainActivity extends Activity {
 private static boolean novaEngineLoaded=false;
 static {try {System.loadLibrary("nova_native");novaEngineLoaded=true;}catch(UnsatisfiedLinkError e){novaEngineLoaded=false;}}
 private static native String nativeGenerate(String path,String prompt);
 private static native void nativeCancelGeneration();
 private final java.util.concurrent.atomic.AtomicBoolean generationBusy = new java.util.concurrent.atomic.AtomicBoolean(false);
 private WebView web;
 private static final int RESUME_PICK=7301;
 private static final int MODEL_PICK=7302;
 private static final int RESUME_LIMIT=8*1024*1024;
 private void modelResult(boolean ok,String message){runOnUiThread(()->web.evaluateJavascript("novaModelImported("+ok+","+JSONObject.quote(message)+")",null));}
 private void resumeResult(boolean ok,String message){runOnUiThread(()->web.evaluateJavascript("novaResumeImported("+ok+","+JSONObject.quote(message)+")",null));}
 @Override protected void onActivityResult(int request,int result,Intent data){
  super.onActivityResult(request,result,data);
  if(request==MODEL_PICK){if(generationBusy.get()){modelResult(false,"Wait for NOVA to finish generating before replacing the model");return;}if(result!=RESULT_OK||data==null||data.getData()==null){modelResult(false,"Cancelled");return;}Uri modelUri=data.getData();new Thread(()->{java.io.File tmp=null;try{String display="model.gguf";try(Cursor c=getContentResolver().query(modelUri,null,null,null,null)){if(c!=null&&c.moveToFirst()){int n=c.getColumnIndex(OpenableColumns.DISPLAY_NAME);if(n>=0)display=c.getString(n);}}if(display==null||!display.toLowerCase(java.util.Locale.ROOT).endsWith(".gguf"))throw new Exception("Select a .gguf model file");java.io.File dir=new java.io.File(getFilesDir(),"models");if(!dir.exists()&&!dir.mkdirs())throw new Exception("Cannot create model directory");tmp=new java.io.File(dir,"incoming.part");long total=0;try(InputStream in=getContentResolver().openInputStream(modelUri);FileOutputStream out=new FileOutputStream(tmp)){if(in==null)throw new Exception("Cannot open model");byte[] buf=new byte[65536];int n;while((n=in.read(buf))!=-1){total+=n;if(total>6000000000L)throw new Exception("Model exceeds 6 GB");out.write(buf,0,n);}out.getFD().sync();}if(total<1024)throw new Exception("Model file too small");try(FileInputStream check=new FileInputStream(tmp)){byte[] magic=new byte[4];if(check.read(magic)!=4||magic[0]!=71||magic[1]!=71||magic[2]!=85||magic[3]!=70)throw new Exception("Invalid GGUF header");}java.io.File dest=new java.io.File(dir,"nova-model.gguf");java.io.File previous=new java.io.File(dir,"nova-model.previous.gguf");
    if(previous.exists()&&!previous.delete())throw new Exception("Cannot clear previous model backup");
    boolean hadModel=dest.exists();
    if(hadModel&&!dest.renameTo(previous))throw new Exception("Cannot preserve existing model");
    if(!tmp.renameTo(dest)){if(hadModel&&!previous.renameTo(dest))throw new Exception("Model install failed; old model preserved at nova-model.previous.gguf");throw new Exception("Cannot finalize model import");}
    if(previous.exists())previous.delete();modelResult(true,"Stored privately ("+(total/1048576)+" MiB).");}catch(Exception e){if(tmp!=null)tmp.delete();modelResult(false,e.getMessage()==null?"Import failed":e.getMessage());}}).start();return;}
  if(request!=RESUME_PICK)return;
  if(result!=RESULT_OK||data==null||data.getData()==null){resumeResult(false,"Import cancelled");return;}
  Uri uri=data.getData();
  new Thread(()->{try{
   String mime=getContentResolver().getType(uri);
   String name="resume";
   try(Cursor c=getContentResolver().query(uri,null,null,null,null)){
    if(c!=null&&c.moveToFirst()){int col=c.getColumnIndex(OpenableColumns.DISPLAY_NAME);if(col>=0)name=c.getString(col);}
   }
   if(name==null)name="resume";
   String lower=name.toLowerCase(java.util.Locale.ROOT);
   if(!(lower.endsWith(".txt")||lower.endsWith(".docx")||lower.endsWith(".pdf")))throw new Exception("Choose a TXT, DOCX or PDF resume");
   ByteArrayOutputStream out=new ByteArrayOutputStream();
   try(InputStream in=getContentResolver().openInputStream(uri)){
    if(in==null)throw new Exception("Cannot open document");
    byte[] buf=new byte[8192];int n;while((n=in.read(buf))!=-1){out.write(buf,0,n);if(out.size()>RESUME_LIMIT)throw new Exception("Resume exceeds 8 MB");}
   }
   byte[] bytes=out.toByteArray();String extracted;
   if(lower.endsWith(".txt"))extracted=new String(bytes,StandardCharsets.UTF_8);
   else if(lower.endsWith(".docx"))extracted=extractDocx(bytes);
   else {PDFBoxResourceLoader.init(getApplicationContext());try(PDDocument pdf=PDDocument.load(bytes)){if(pdf.getNumberOfPages()>60)throw new Exception("PDF exceeds 60 pages");extracted=new PDFTextStripper().getText(pdf);}}
   extracted=extracted.replace('\u0000',' ').trim();
   if(extracted.isEmpty())throw new Exception("No selectable text found; scanned PDFs need OCR");
   if(extracted.length()>35000)extracted=extracted.substring(0,35000);
   resumeResult(true,extracted);
  }catch(Exception e){resumeResult(false,e.getMessage()==null?"Resume import failed":e.getMessage());}}).start();
 }
 private String extractDocx(byte[] bytes)throws Exception{
  String xml=null;
  try(ZipInputStream zip=new ZipInputStream(new ByteArrayInputStream(bytes))){ZipEntry entry;while((entry=zip.getNextEntry())!=null){if("word/document.xml".equals(entry.getName())){
   ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] buf=new byte[4096];int n;while((n=zip.read(buf))!=-1){out.write(buf,0,n);if(out.size()>2000000)throw new Exception("DOCX XML too large");}xml=out.toString("UTF-8");break;
  }}}
  if(xml==null)throw new Exception("Invalid DOCX document");
  xml=xml.replaceAll("</w:p>","\n").replaceAll("</w:tr>","\n").replaceAll("<w:tab[^>]*/>"," ");
  xml=xml.replaceAll("<[^>]+>","");
  return xml.replace("&amp;","&").replace("&lt;","<").replace("&gt;",">").replace("&quot;","\"").replace("&apos;","'");
 }

 private volatile boolean novaForeground=true;
 @Override protected void onResume(){super.onResume();novaForeground=true;}
 @Override protected void onPause(){novaForeground=false;super.onPause();}
 private static final String COPILOT_CHANNEL="nova_copilot_tasks";
 private void copilotNotify(String title,String message){
  if(android.os.Build.VERSION.SDK_INT>=33 && checkSelfPermission("android.permission.POST_NOTIFICATIONS")!=android.content.pm.PackageManager.PERMISSION_GRANTED)return;
  android.app.NotificationManager nm=(android.app.NotificationManager)getSystemService(NOTIFICATION_SERVICE);
  if(android.os.Build.VERSION.SDK_INT>=26)nm.createNotificationChannel(new android.app.NotificationChannel(COPILOT_CHANNEL,"NOVA task updates",android.app.NotificationManager.IMPORTANCE_DEFAULT));
  Intent intent=new Intent(this,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP|Intent.FLAG_ACTIVITY_SINGLE_TOP);
  android.app.PendingIntent pi=android.app.PendingIntent.getActivity(this,0,intent,android.app.PendingIntent.FLAG_UPDATE_CURRENT|android.app.PendingIntent.FLAG_IMMUTABLE);
  android.app.Notification.Builder b=android.os.Build.VERSION.SDK_INT>=26?new android.app.Notification.Builder(this,COPILOT_CHANNEL):new android.app.Notification.Builder(this);
  b.setSmallIcon(android.R.drawable.ic_dialog_info).setContentTitle(title).setContentText(message).setAutoCancel(true).setContentIntent(pi);
  nm.notify((int)(System.currentTimeMillis()%100000),b.build());
 }
 private static final String KEY_ALIAS="nova_provider_credentials_v1";
 @Override public void onCreate(Bundle b){super.onCreate(b);getWindow().setStatusBarColor(0xff0b1422);getWindow().setNavigationBarColor(0xff0b1422);
 web=new WebView(this);
 if(android.os.Build.VERSION.SDK_INT>=30){
  getWindow().setDecorFitsSystemWindows(false);
  web.setOnApplyWindowInsetsListener((v,insets)->{
   android.graphics.Insets bars=insets.getInsets(android.view.WindowInsets.Type.statusBars()|android.view.WindowInsets.Type.navigationBars());
   v.setPadding(0,bars.top,0,bars.bottom);
   return insets;
  });
 }
 // Dark status/navigation bars use light system icons.
 if(android.os.Build.VERSION.SDK_INT>=30){
  android.view.WindowInsetsController controller=getWindow().getInsetsController();
  if(controller!=null)controller.setSystemBarsAppearance(0,android.view.WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS|android.view.WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS);
 }else{
  getWindow().getDecorView().setSystemUiVisibility(getWindow().getDecorView().getSystemUiVisibility() & ~android.view.View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR);
 }
 WebSettings s=web.getSettings();s.setJavaScriptEnabled(true);s.setDomStorageEnabled(true);s.setAllowFileAccess(true);s.setAllowFileAccessFromFileURLs(false);s.setAllowUniversalAccessFromFileURLs(false);s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
 web.setWebChromeClient(new WebChromeClient(){
 @Override public boolean onConsoleMessage(ConsoleMessage m){
  android.util.Log.d("NOVA_WEBVIEW",
   "JavaScript "+m.messageLevel()+" at line "+m.lineNumber()+
   " in "+m.sourceId());
  return true;
 }
});
web.addJavascriptInterface(new Bridge(),"Nova");web.setWebViewClient(new WebViewClient(){@Override public boolean shouldOverrideUrlLoading(WebView v,WebResourceRequest r){Uri u=r.getUrl();if(!"file".equals(u.getScheme())||!"android_asset".equals(u.getHost())){openExternal(u.toString());return true;}return false;}});setContentView(web);web.loadUrl("file:///android_asset/index.html");}
 private void openExternal(String url){try{Uri u=Uri.parse(url);if(!"https".equalsIgnoreCase(u.getScheme()))return;startActivity(new Intent(Intent.ACTION_VIEW,u));}catch(Exception ignored){}}
 private synchronized SecretKey secret()throws Exception{KeyStore ks=KeyStore.getInstance("AndroidKeyStore");ks.load(null);if(!ks.containsAlias(KEY_ALIAS)){KeyGenerator g=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");g.init(new KeyGenParameterSpec.Builder(KEY_ALIAS,KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT).setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());g.generateKey();}return ((KeyStore.SecretKeyEntry)ks.getEntry(KEY_ALIAS,null)).getSecretKey();}
 private synchronized JSONObject credentials()throws Exception{String stored=getPreferences(0).getString("encrypted_profiles","");if(stored.isEmpty())return new JSONObject();byte[] raw=Base64.decode(stored,Base64.NO_WRAP);byte[] iv=new byte[12];System.arraycopy(raw,0,iv,0,12);Cipher c=Cipher.getInstance("AES/GCM/NoPadding");c.init(Cipher.DECRYPT_MODE,secret(),new GCMParameterSpec(128,iv));return new JSONObject(new String(c.doFinal(raw,12,raw.length-12),StandardCharsets.UTF_8));}
 private synchronized void saveCredentials(JSONObject obj)throws Exception{Cipher c=Cipher.getInstance("AES/GCM/NoPadding");c.init(Cipher.ENCRYPT_MODE,secret());byte[] iv=c.getIV(),data=c.doFinal(obj.toString().getBytes(StandardCharsets.UTF_8));byte[] all=new byte[iv.length+data.length];System.arraycopy(iv,0,all,0,iv.length);System.arraycopy(data,0,all,iv.length,data.length);getPreferences(0).edit().putString("encrypted_profiles",Base64.encodeToString(all,Base64.NO_WRAP)).apply();}
 private void reply(String callback,int id,boolean ok,String payload){runOnUiThread(()->web.evaluateJavascript(callback+"("+id+","+ok+","+JSONObject.quote(payload)+")",null));}
 private String enc(String s)throws Exception{return URLEncoder.encode(s,"UTF-8");}
 private String http(String url,JSONObject headers)throws Exception{URL u=new URL(url);if(!"https".equals(u.getProtocol()))throw new Exception("HTTPS required");HttpURLConnection c=(HttpURLConnection)u.openConnection();c.setConnectTimeout(12000);c.setReadTimeout(18000);c.setInstanceFollowRedirects(false);c.setRequestProperty("User-Agent","NOVA-JobHunter/1.1 (Android)");if(headers!=null){java.util.Iterator<String> keys=headers.keys();while(keys.hasNext()){String k=keys.next();c.setRequestProperty(k,headers.optString(k));}}try{int code=c.getResponseCode();if(code!=200){String reason=code==401?"authentication rejected":code==403?"access denied for this account":code==404?"endpoint or program not found":code==429?"rate limit reached":code>=500?"provider temporarily unavailable":"request rejected";throw new Exception("Provider HTTP "+code+" ("+reason+")");}try(InputStream in=c.getInputStream();ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] buf=new byte[8192];int n;while((n=in.read(buf))!=-1){out.write(buf,0,n);if(out.size()>3500000)throw new Exception("Response too large");}return out.toString("UTF-8");}}finally{c.disconnect();}}
 private JSONObject profile(String provider)throws Exception{JSONObject profiles=credentials();String active=getPreferences(0).getString("active_"+provider,"default");return profiles.optJSONObject(provider+":"+active);}

 private volatile boolean downloadCancelled = false;
 private volatile boolean downloadBusy = false;

 private void downloadEvent(String state, String message) {
  runOnUiThread(() -> web.evaluateJavascript(
   "novaDownloadEvent(" + JSONObject.quote(state) + "," +
   JSONObject.quote(message) + ")", null));
 }

 private void downloadModel() {
  synchronized(this) {
   if(downloadBusy) return;
   downloadBusy = true;
   downloadCancelled = false;
  }
  new Thread(() -> {
   File part = null;
   HttpURLConnection connection = null;
   try {
    File dir = new File(getFilesDir(), "models");
    if(!dir.exists() && !dir.mkdirs())
     throw new IOException("Cannot create model directory");

    File dest = new File(dir, "nova-model.gguf");
    part = new File(dir, "nova-model.part");

    URL url = new URL(
     "https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf?download=true"
    );

    for(int redirects = 0; redirects <= 5; redirects++) {
     if(!"https".equalsIgnoreCase(url.getProtocol()))
      throw new IOException("HTTPS required");

     connection = (HttpURLConnection) url.openConnection();
     connection.setInstanceFollowRedirects(false);
     connection.setConnectTimeout(20000);
     connection.setReadTimeout(30000);

     int code = connection.getResponseCode();
     if(code == 200) break;

     if(code != 301 && code != 302 && code != 303 &&
        code != 307 && code != 308)
      throw new IOException("Model server HTTP " + code);

     String location = connection.getHeaderField("Location");
     if(location == null) throw new IOException("Invalid redirect");
     URL next = new URL(url, location);
     connection.disconnect();
     connection = null;
     url = next;
     if(redirects == 5) throw new IOException("Too many redirects");
    }

    long size = connection.getContentLengthLong();
    if(size < 1024 || size > 6000000000L)
     throw new IOException("Unsupported model size");
    if(dir.getUsableSpace() < size + 300000000L)
     throw new IOException("Insufficient storage");

    long total = 0;
    int lastPercent = -1;
    try(InputStream in = connection.getInputStream();
        FileOutputStream out = new FileOutputStream(part, false)) {
     byte[] buffer = new byte[131072];
     int n;
     while((n = in.read(buffer)) != -1) {
      if(downloadCancelled)
       throw new InterruptedIOException("Download cancelled");
      total += n;
      if(total > size) throw new IOException("Size mismatch");
      out.write(buffer, 0, n);

      int percent = (int)(total * 100 / size);
      if(percent != lastPercent) {
       lastPercent = percent;
       downloadEvent("progress", percent + "% downloaded");
      }
     }
     out.getFD().sync();
    }

    if(total != size) throw new IOException("Incomplete download");
    try(FileInputStream in = new FileInputStream(part)) {
     byte[] magic = new byte[4];
     if(in.read(magic) != 4 ||
        magic[0] != 'G' || magic[1] != 'G' ||
        magic[2] != 'U' || magic[3] != 'F')
      throw new IOException("Invalid GGUF file");
    }

    if(downloadCancelled)
     throw new InterruptedIOException("Download cancelled");
    if(dest.exists()) {
     throw new IOException("A model is already installed. Remove it explicitly before downloading a replacement.");
    }
    if(!part.renameTo(dest))
     throw new IOException("Cannot finish installation");

    downloadEvent("done", "Model installed successfully");
   } catch(Exception e) {
    if(part != null) part.delete();
    downloadEvent("error", String.valueOf(e.getMessage()));
   } finally {
    if(connection != null) connection.disconnect();
    downloadBusy = false;
   }
  }, "nova-model-downloader").start();
 }


 // ECLIPSE_V44_NATIVE_HTTP — dedicated request broker; all per-request permissions enforced here.
 private static final class EclipseV44Job {
  final int id; final String url,host,path,method;
  final java.util.concurrent.atomic.AtomicBoolean finished=new java.util.concurrent.atomic.AtomicBoolean(false);
  volatile boolean cancelled=false;
  volatile java.net.HttpURLConnection connection;
  volatile android.app.AlertDialog dialog;
  EclipseV44Job(int id,String url,String host,String path,String method){this.id=id;this.url=url;this.host=host;this.path=path;this.method=method;}
 }
 private final java.util.concurrent.atomic.AtomicReference<EclipseV44Job> eclipseV44Current=new java.util.concurrent.atomic.AtomicReference<>();
 private volatile long eclipseV44LastNetwork=0;
 private static final class EclipseV44Database extends android.database.sqlite.SQLiteOpenHelper {
  EclipseV44Database(android.content.Context c){super(c,"eclipse_v44_evidence.db",null,1);}
  @Override public void onCreate(android.database.sqlite.SQLiteDatabase db){db.execSQL("CREATE TABLE evidence (id INTEGER PRIMARY KEY AUTOINCREMENT, at_ms INTEGER NOT NULL, host TEXT NOT NULL, path TEXT NOT NULL, method TEXT NOT NULL, status INTEGER NOT NULL, sample_bytes INTEGER NOT NULL, sample_sha256 TEXT, sample_truncated INTEGER NOT NULL, headers_json TEXT NOT NULL)");}
  @Override public void onUpgrade(android.database.sqlite.SQLiteDatabase db,int oldVersion,int newVersion){throw new IllegalStateException("Unsupported evidence migration: preserve database");}
 }
 private void eclipseV44Finish(EclipseV44Job job,boolean ok,String message){
  if(!job.finished.compareAndSet(false,true))return;
  eclipseV44Current.compareAndSet(job,null);
  reply("eclipseV44Result",job.id,ok,message);
 }
 private static String eclipseV44Host(String host)throws Exception {
  if(host==null||host.length()>253||host.length()<4||!host.contains(".")||host.endsWith(".")||host.contains(".."))throw new Exception("A public DNS hostname is required");
  String h=host.toLowerCase(java.util.Locale.ROOT);
  if(h.matches("[0-9.]+")||h.contains(":"))throw new Exception("IP addresses are not supported");
  for(String part:h.split("\\.",-1))if(!part.matches("[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"))throw new Exception("Invalid hostname label");
  for(String suffix:new String[]{".localhost",".local",".internal",".test",".invalid",".example"})if(h.endsWith(suffix))throw new Exception("Local or reserved domains are blocked");
  return h;
 }
 private static EclipseV44Job eclipseV44Validate(int id,String url,String scope,String method)throws Exception {
  if(url==null||url.length()>350||!url.startsWith("https://"))throw new Exception("Use an HTTPS URL under 350 characters");
  if(scope==null)throw new Exception("Scope hostname missing");
  String expected=eclipseV44Host(scope.trim());
  java.net.URI parsed=new java.net.URI(url);
  if(!"https".equalsIgnoreCase(parsed.getScheme())||parsed.getRawUserInfo()!=null||parsed.getPort()!=-1||parsed.getRawQuery()!=null||parsed.getRawFragment()!=null)throw new Exception("No custom port, login, query parameters or fragment allowed");
  String actual=eclipseV44Host(parsed.getHost());
  if(!actual.equals(expected))throw new Exception("Target hostname does not match approved scope exactly");
  String path=parsed.getRawPath();if(path==null||path.isEmpty())path="/";
  if(path.length()>256||!path.matches("/[A-Za-z0-9._~/-]*")||path.contains("..")||!path.equals(new java.net.URI(path).normalize().getRawPath()))throw new Exception("Use a short simple path without encoding or traversal");
  if(!("HEAD".equals(method)||"GET".equals(method)))throw new Exception("Only HEAD and GET are allowed");
  return new EclipseV44Job(id,"https://"+actual+path,actual,path,method);
 }
 private static void eclipseV44CheckPublicDns(String hostname)throws Exception {
  java.net.InetAddress[] addresses=java.net.InetAddress.getAllByName(hostname);
  if(addresses.length<1||addresses.length>12)throw new Exception("DNS resolution refused");
  for(java.net.InetAddress address:addresses){
   byte[] b=address.getAddress();
   if(address.isAnyLocalAddress()||address.isLoopbackAddress()||address.isSiteLocalAddress()||address.isLinkLocalAddress()||address.isMulticastAddress())throw new Exception("Non-public address blocked");
   if(b.length==4){int a=b[0]&255,c=b[1]&255,d=b[2]&255;
    if(a==0||a>=224||a==100&&(c>=64&&c<=127)||a==192&&c==0&&d==0||a==198&&(c==18||c==19)||a==192&&c==0&&d==2||a==198&&c==51&&d==100||a==203&&c==0&&d==113)throw new Exception("Reserved IP blocked");
   }else if(b.length==16){int a=b[0]&255,c=b[1]&255;
    if((a&254)==252||(a==0x20&&c==0x01&&b[2]==0x0d&&(b[3]&255)==0xb8))throw new Exception("Non-public IPv6 blocked");
   }else throw new Exception("Unsupported DNS address type");
  }
 }
 private static String eclipseV44Digest(byte[] body){
  try{byte[] hash=java.security.MessageDigest.getInstance("SHA-256").digest(body);StringBuilder hex=new StringBuilder();for(byte b:hash)hex.append(String.format(java.util.Locale.ROOT,"%02x",b&255));return hex.toString();}
  catch(Exception e){throw new IllegalStateException("SHA-256 unavailable",e);}
 }
 private static String eclipseV44Headers(java.net.HttpURLConnection c){
  org.json.JSONArray headers=new org.json.JSONArray();
  for(String name:new String[]{"Strict-Transport-Security","Content-Security-Policy","X-Content-Type-Options","Referrer-Policy","Cache-Control","Content-Type","Permissions-Policy","Cross-Origin-Resource-Policy"}){
   if(c.getHeaderField(name)!=null)headers.put(name);
  }
  return headers.toString();
 }
 private void eclipseV44SaveEvidence(org.json.JSONObject result)throws Exception {
  EclipseV44Database helper=new EclipseV44Database(getApplicationContext());
  android.database.sqlite.SQLiteDatabase db=helper.getWritableDatabase();
  try{
   android.content.ContentValues values=new android.content.ContentValues();
   values.put("at_ms",result.getLong("at_ms"));values.put("host",result.getString("host"));values.put("path",result.getString("path"));values.put("method",result.getString("method"));
   values.put("status",result.getInt("status"));values.put("sample_bytes",result.getInt("sample_bytes"));values.put("sample_sha256",result.optString("sample_sha256",""));
   values.put("sample_truncated",result.optBoolean("sample_truncated",false)?1:0);values.put("headers_json",result.getJSONArray("headers_present").toString());
   db.beginTransaction();try{
    if(db.insertOrThrow("evidence",null,values)<0)throw new Exception("Evidence insert failed");
    db.execSQL("DELETE FROM evidence WHERE id NOT IN (SELECT id FROM evidence ORDER BY id DESC LIMIT 100)");
    db.setTransactionSuccessful();
   }finally{db.endTransaction();}
  }finally{helper.close();}
 }
 private org.json.JSONArray eclipseV44ReadHistory()throws Exception {
  EclipseV44Database helper=new EclipseV44Database(getApplicationContext());
  android.database.sqlite.SQLiteDatabase db=helper.getReadableDatabase();
  org.json.JSONArray out=new org.json.JSONArray();
  try(android.database.Cursor rows=db.rawQuery("SELECT id,at_ms,host,path,method,status,sample_bytes,sample_sha256,sample_truncated,headers_json FROM evidence ORDER BY id DESC LIMIT 100",null)){
   while(rows.moveToNext()){
    org.json.JSONObject x=new org.json.JSONObject().put("id",rows.getLong(0)).put("at_ms",rows.getLong(1)).put("host",rows.getString(2))
     .put("path",rows.getString(3)).put("method",rows.getString(4)).put("status",rows.getInt(5)).put("sample_bytes",rows.getInt(6))
     .put("sample_sha256",rows.getString(7)).put("sample_truncated",rows.getInt(8)!=0)
     .put("headers_present",new org.json.JSONArray(rows.getString(9)));
    out.put(x);
   }
  }finally{helper.close();}
  return out;
 }
 private void eclipseV44Perform(EclipseV44Job job){
  java.net.HttpURLConnection c=null;
  try{
   if(job.cancelled)throw new java.io.InterruptedIOException("Cancelled before network");
   // DNS preflight refuses private and reserved ranges. No redirect or cookies are allowed.
   // For hostile DNS services this does not prevent DNS rebinding between resolution and connect;
   // only test exact hostnames whose ownership and rules were independently verified.
   eclipseV44CheckPublicDns(job.host);
   if(job.cancelled)throw new java.io.InterruptedIOException("Cancelled before network");
   long now=android.os.SystemClock.elapsedRealtime();
   if(now-eclipseV44LastNetwork<5000L)throw new Exception("Wait at least 5 seconds between V4.4 requests");
   eclipseV44LastNetwork=now;
   java.net.URL target=new java.net.URL(job.url);
   c=(java.net.HttpURLConnection)target.openConnection(java.net.Proxy.NO_PROXY);
   job.connection=c;
   c.setInstanceFollowRedirects(false);c.setUseCaches(false);c.setAllowUserInteraction(false);
   c.setRequestMethod(job.method);c.setConnectTimeout(8000);c.setReadTimeout(10000);
   c.setRequestProperty("Accept-Encoding","identity");
   c.setRequestProperty("User-Agent","NOVA-Eclipse/4.4 (single-approved-request)");
   if(job.cancelled)throw new java.io.InterruptedIOException("Cancelled before network");
   int status=c.getResponseCode();
   if(job.cancelled)throw new java.io.InterruptedIOException("Request cancelled");
   String observedHeaders=eclipseV44Headers(c);
   int sampled=0;boolean truncated=false;String hash="";
   if("GET".equals(job.method)){
    java.io.InputStream body=status>=400?c.getErrorStream():status>=300?null:c.getInputStream();
    if(body!=null)try(java.io.InputStream in=body;java.io.ByteArrayOutputStream sample=new java.io.ByteArrayOutputStream()){
     byte[] chunk=new byte[2048];int n;
     while((n=in.read(chunk,0,Math.min(chunk.length,16385-sample.size())))!=-1){
      if(job.cancelled)throw new java.io.InterruptedIOException("Request cancelled");
      if(sample.size()+n>16384){sample.write(chunk,0,Math.max(0,16384-sample.size()));truncated=true;break;}
      sample.write(chunk,0,n);if(sample.size()==16384){truncated=in.read()!=-1;break;}
     }
     byte[] sampleBytes=sample.toByteArray();sampled=sampleBytes.length;hash=eclipseV44Digest(sampleBytes);
    }
   }
   if(job.cancelled)throw new java.io.InterruptedIOException("Request cancelled");
   org.json.JSONObject result=new org.json.JSONObject().put("environment","approved_live_https").put("network_used",true)
    .put("host",job.host).put("path",job.path).put("method",job.method).put("status",status).put("at_ms",System.currentTimeMillis())
    .put("headers_present",new org.json.JSONArray(observedHeaders)).put("sample_bytes",sampled)
    .put("sample_sha256",hash).put("sample_truncated",truncated)
    .put("note","Metadata observation, not a verified security vulnerability. SHA-256 covers only the sampled bytes; HEAD has no body digest.");
   eclipseV44SaveEvidence(result); // Evidence must persist before reporting success.
   eclipseV44Finish(job,true,result.toString());
  }catch(Exception e){eclipseV44Finish(job,false,e.getMessage()==null?"HTTPS request failed":e.getMessage());}
  finally{if(c!=null)c.disconnect();job.connection=null;}
 }

 public class Bridge{
 @JavascriptInterface public void novaGenerate(String prompt,int id){
  if(prompt==null||prompt.isEmpty()||prompt.length()>5000){reply("novaAiResult",id,false,"Invalid prompt");return;}
  if(!novaEngineLoaded){reply("novaAiResult",id,false,"Native engine unavailable");return;}
  if(!generationBusy.compareAndSet(false,true)){reply("novaAiResult",id,false,"NOVA is already generating");return;}
  new Thread(()->{
   try{
    java.io.File model=new java.io.File(new java.io.File(getFilesDir(),"models"),"nova-model.gguf");
    if(!model.isFile())throw new Exception("Install a GGUF model first");
    String answer=nativeGenerate(model.getAbsolutePath(),prompt);
    if(answer.startsWith("NOVA_ENGINE_ERROR:"))throw new Exception(answer);
    reply("novaAiResult",id,true,answer);
    if(!novaForeground)runOnUiThread(()->copilotNotify("NOVA finished thinking","Tap to review your AI response"));
   }catch(Exception e){reply("novaAiResult",id,false,e.getMessage()==null?"Generation failed":e.getMessage());if(!novaForeground)runOnUiThread(()->copilotNotify("NOVA needs attention","AI task failed; tap to review"));}
   finally{generationBusy.set(false);}
  },"nova-ai").start();
 }

 @JavascriptInterface public void novaCancelGeneration(){if(novaEngineLoaded)nativeCancelGeneration();}
 @JavascriptInterface public void novaDownloadModel(){downloadModel();}
 @JavascriptInterface public void novaCancelDownload(){downloadCancelled=true;}
 @JavascriptInterface public void pickModel(){runOnUiThread(()->{try{Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT);i.setType("*/*");i.addCategory(Intent.CATEGORY_OPENABLE);startActivityForResult(i,MODEL_PICK);}catch(Exception e){modelResult(false,"Picker unavailable");}});}
 @JavascriptInterface public void pickResume(){runOnUiThread(()->{try{Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT);i.setType("*/*");i.addCategory(Intent.CATEGORY_OPENABLE);i.putExtra(Intent.EXTRA_MIME_TYPES,new String[]{"application/pdf","application/vnd.openxmlformats-officedocument.wordprocessingml.document","text/plain"});startActivityForResult(i,RESUME_PICK);}catch(Exception e){resumeResult(false,"Document picker unavailable");}});}

 @JavascriptInterface public void saveProfile(String provider,String name,String json,int id){new Thread(()->{try{if(!provider.matches("adzuna|usajobs|hackerone")||!name.matches("[a-zA-Z0-9_-]{1,32}"))throw new Exception("Invalid provider/profile");JSONObject val=new JSONObject(json);JSONObject all=credentials();all.put(provider+":"+name,val);saveCredentials(all);getPreferences(0).edit().putString("active_"+provider,name).apply();reply("novaConfigResult",id,true,"Saved securely on this device");}catch(Exception e){reply("novaConfigResult",id,false,e.getMessage());}}).start();}
 @JavascriptInterface public void listProfiles(int id){new Thread(()->{try{JSONObject all=credentials(),out=new JSONObject();JSONArray names=new JSONArray();java.util.Iterator<String> it=all.keys();while(it.hasNext()){String key=it.next();String[] parts=key.split(":",2);if(parts.length==2)names.put(new JSONObject().put("provider",parts[0]).put("name",parts[1]));}out.put("profiles",names);for(String p:new String[]{"adzuna","usajobs","hackerone"})out.put("active_"+p,getPreferences(0).getString("active_"+p,"default"));reply("novaConfigResult",id,true,out.toString());}catch(Exception e){reply("novaConfigResult",id,false,e.getMessage());}}).start();}
 @JavascriptInterface public void activateProfile(String provider,String name,int id){new Thread(()->{try{if(provider==null||name==null||!provider.matches("adzuna|usajobs|hackerone")||!name.matches("[a-zA-Z0-9_-]{1,32}"))throw new Exception("Invalid provider/profile");if(credentials().optJSONObject(provider+":"+name)==null)throw new Exception("Profile not found");getPreferences(0).edit().putString("active_"+provider,name).apply();reply("novaConfigResult",id,true,"Activated");}catch(Exception e){reply("novaConfigResult",id,false,e.getMessage());}}).start();}
 @JavascriptInterface public void deleteProfile(String provider,String name,int id){new Thread(()->{try{if(provider==null||name==null||!provider.matches("adzuna|usajobs|hackerone")||!name.matches("[a-zA-Z0-9_-]{1,32}"))throw new Exception("Invalid provider/profile");JSONObject all=credentials();if(!all.has(provider+":"+name))throw new Exception("Profile not found");all.remove(provider+":"+name);saveCredentials(all);if(name.equals(getPreferences(0).getString("active_"+provider,"default")))getPreferences(0).edit().remove("active_"+provider).apply();reply("novaConfigResult",id,true,"Deleted");}catch(Exception e){reply("novaConfigResult",id,false,e.getMessage());}}).start();}
 @JavascriptInterface public void searchProvider(String provider,String query,String location,int id){new Thread(()->{try{String endpoint;JSONObject headers=null;JSONObject p=profile(provider);if(provider.equals("remotive")){endpoint="https://remotive.com/api/remote-jobs?limit=100&search="+enc(query);}else if(provider.equals("adzuna")){if(p==null)throw new Exception("Configure Adzuna in Settings");String appId=p.optString("id"),key=p.optString("key");if(appId.isEmpty()||key.isEmpty())throw new Exception("Adzuna ID and key required");endpoint="https://api.adzuna.com/v1/api/jobs/us/search/1?app_id="+enc(appId)+"&app_key="+enc(key)+"&results_per_page=50&what="+enc(query)+"&where="+enc(location);}else if(provider.equals("usajobs")){if(p==null)throw new Exception("Configure USAJOBS in Settings");headers=new JSONObject().put("Host","data.usajobs.gov").put("User-Agent",p.optString("email")).put("Authorization-Key",p.optString("key"));endpoint="https://data.usajobs.gov/api/search?Keyword="+enc(query)+"&LocationName="+enc(location)+"&ResultsPerPage=50";}else if(provider.equals("hackerone")){if(p==null)throw new Exception("Configure HackerOne in Settings");String username=p.optString("username"),token=p.optString("token");if(username.isEmpty()||token.isEmpty())throw new Exception("HackerOne credentials required");String basic=Base64.encodeToString((username+":"+token).getBytes(StandardCharsets.UTF_8),Base64.NO_WRAP);headers=new JSONObject().put("Authorization","Basic "+basic).put("Accept","application/json");endpoint="https://api.hackerone.com/v1/hackers/programs?page%5Bsize%5D=25";}else throw new Exception("Unknown provider");String data=http(endpoint,headers);reply("novaProviderResult",id,true,data);}catch(Exception e){reply("novaProviderResult",id,false,e.getMessage()==null?"Request failed":e.getMessage());}}).start();}
 // NOVA_H1_DETAILS_V1: authenticated, read-only, bounded API retrieval.
 @JavascriptInterface public void novaH1Details(String handle,int id){new Thread(()->{
  try{
   if(handle==null||!handle.matches("[a-zA-Z0-9_-]{1,80}"))throw new Exception("Invalid program handle");
   JSONObject p=profile("hackerone");if(p==null)throw new Exception("Configure HackerOne credentials in Settings");
   String user=p.optString("username"),token=p.optString("token");
   if(user.isEmpty()||token.isEmpty())throw new Exception("HackerOne credentials required");
   String basic=Base64.encodeToString((user+":"+token).getBytes(StandardCharsets.UTF_8),Base64.NO_WRAP);
   JSONObject headers=new JSONObject().put("Authorization","Basic "+basic).put("Accept","application/json");
   String base="https://api.hackerone.com/v1/hackers/programs/"+handle;
   JSONObject out=new JSONObject().put("handle",handle);
   // NOVA_H1_INDEPENDENT_FETCH_V4: program metadata and scope are separate API resources.
   // Never manufacture a program record or treat partial scope as authorization.
   try {
    String raw=http(base,headers);
    JSONObject programResponse=new JSONObject(raw);
    // NOVA_H1_DIRECT_PROGRAM_V6: live HackerOne detail endpoint may return
    // {id,type,attributes,relationships} directly rather than {data:{...}}.
    JSONObject program=programResponse.optJSONObject("data");
    if(program==null && !programResponse.has("data")
       && "program".equals(programResponse.optString("type"))
       && programResponse.optJSONObject("attributes")!=null){
     program=programResponse;
    }
    if(program==null){
     java.util.ArrayList<String> keys=new java.util.ArrayList<>();
     java.util.Iterator<String> iter=programResponse.keys();
     while(iter.hasNext()&&keys.size()<12){String key=iter.next();if(key.matches("[a-zA-Z_]{1,35}"))keys.add(key);}
     out.put("program_error","Program metadata unavailable (HTTP 200; response keys "+keys.toString()+"); scope not verified");
    } else {
     JSONObject attributes=program.optJSONObject("attributes");
     String returnedHandle=attributes==null?"":attributes.optString("handle","");
     if(!"program".equals(program.optString("type")) || !handle.equalsIgnoreCase(returnedHandle))
      out.put("program_error","Program type or handle mismatch; metadata not trusted");
     else out.put("program",program);
    }
   }catch(Exception metadataError){
    String msg=metadataError.getMessage()==null?"unknown error":metadataError.getMessage();
    out.put("program_error","Program metadata unavailable: "+msg.substring(0,Math.min(180,msg.length())));
   }
   // Fetch structured scopes and exclusions separately; do not infer scope from the program name.
   for(String type:new String[]{"structured_scopes","scope_exclusions"}){
    try{JSONObject data=new JSONObject(http(base+"/"+type+"?page%5Bsize%5D=100",headers));
     JSONArray collected=new JSONArray();int pages=0;String next=base+"/"+type+"?page%5Bsize%5D=100";
     while(next!=null&&pages<10){
      JSONObject page=pages==0?data:new JSONObject(http(next,headers));
      JSONArray items=page.optJSONArray("data");if(items==null)throw new Exception("Scope response missing data array");
      for(int i=0;i<items.length();i++)collected.put(items.get(i));
      JSONObject links=page.optJSONObject("links");String link=links==null?"":links.optString("next","");
      if(link.isEmpty()||"null".equals(link))next=null;
      else {URL candidate=new URL(new URL(base+"/"+type),link);
       if(!"https".equals(candidate.getProtocol())||!"api.hackerone.com".equalsIgnoreCase(candidate.getHost())||candidate.getPort()!=-1||!candidate.getPath().equals("/v1/hackers/programs/"+handle+"/"+type))throw new Exception("Unsafe pagination URL");
       next=candidate.toString();}
      pages++;
     }
     out.put(type,collected);out.put(type+"_has_more",next!=null);out.put(type+"_pages_fetched",pages);
    }catch(Exception e){out.put(type+"_error",type+" retrieval failed: "+e.getMessage());}
   }
   reply("novaH1DetailsResult",id,true,out.toString());
  }catch(Exception e){reply("novaH1DetailsResult",id,false,e.getMessage()==null?"Request failed":e.getMessage());}
 }).start();}
 // NOVA_NATIVE_AUDIT_APPROVAL_V2: native, target-specific, human approval.
 // JavaScript authorization flags cannot bypass this Android confirmation.
 @JavascriptInterface public void auditWebsite(String target,boolean authorized,int id){
  runOnUiThread(()->{
   String shown=target==null?"(missing target)":target;
   if(shown.length()>300){reply("novaAuditResult",id,false,"Target too long");return;}
   new android.app.AlertDialog.Builder(MainActivity.this)
    .setTitle("Authorize passive website check")
    .setMessage("Target: "+shown+"\n\nThis sends one HTTPS HEAD request to the target's root path and inspects response headers. Only continue if you have authorization and the target is in scope. NOVA AI cannot approve this action.")
    .setNegativeButton("Cancel",(dialog,which)->reply("novaAuditResult",id,false,"Cancelled by user"))
    .setOnCancelListener(dialog->reply("novaAuditResult",id,false,"Cancelled by user"))
    .setPositiveButton("Authorize once",(dialog,which)->auditWebsiteApproved(target,authorized,id))
    .show();
  });
 }
 private void auditWebsiteApproved(String target,boolean authorized,int id){new Thread(()->{try{
 // Android confirmation is the authoritative one-time approval; JS flags are not trusted.
 if(target==null||target.length()>300)throw new Exception("Invalid target");
 URL u=new URL(target);if(!"https".equalsIgnoreCase(u.getProtocol())||u.getUserInfo()!=null||u.getPort()!=-1)throw new Exception("Use an HTTPS hostname without credentials or port");
 String host=u.getHost();if(host==null||host.length()>253||!host.contains(".")||host.equalsIgnoreCase("localhost")||host.endsWith(".local")||host.endsWith(".internal")||host.endsWith(".test")||host.endsWith(".invalid")||host.endsWith(".example"))throw new Exception("Public HTTPS host required");
 java.net.InetAddress[] ips=java.net.InetAddress.getAllByName(host);for(java.net.InetAddress ip:ips){byte[] a=ip.getAddress();if(ip.isAnyLocalAddress()||ip.isLoopbackAddress()||ip.isSiteLocalAddress()||ip.isLinkLocalAddress()||ip.isMulticastAddress()||a.length==16&&(a[0]&254)==252||a.length==4&&((a[0]&255)==0||(a[0]&255)>=224||(a[0]&255)==100&&(a[1]&192)==64||(a[0]&255)==169&&(a[1]&255)==254||(a[0]&255)==192&&(a[1]&255)==0&&(a[2]&255)==0))throw new Exception("Private or reserved host blocked");}
 URL clean=new URL("https",host,"/");javax.net.ssl.HttpsURLConnection c=(javax.net.ssl.HttpsURLConnection)clean.openConnection();c.setRequestMethod("HEAD");c.setInstanceFollowRedirects(false);c.setConnectTimeout(8000);c.setReadTimeout(8000);c.setRequestProperty("User-Agent","NOVA-Authorized-Passive-Audit/1.2");
 JSONObject result=new JSONObject();try{int code=c.getResponseCode();result.put("host",host).put("http_status",code).put("checked_at",System.currentTimeMillis());JSONArray findings=new JSONArray();String[][] checks={{"Strict-Transport-Security","HSTS header not observed"},{"Content-Security-Policy","CSP header not observed"},{"X-Content-Type-Options","X-Content-Type-Options header not observed"},{"Referrer-Policy","Referrer-Policy header not observed"}};for(String[] check:checks){if(c.getHeaderField(check[0])==null)findings.put(check[1]);}result.put("observations",findings).put("note","Configuration observations only, not confirmed vulnerabilities. HEAD / only; verify scope and context manually.");}finally{c.disconnect();}reply("novaAuditResult",id,true,result.toString());
 }catch(Exception e){reply("novaAuditResult",id,false,e.getMessage()==null?"Audit failed":e.getMessage());}}).start();}

 // NOVA_NATIVE_AGENT_STAGE2: bounded offline-only native tools
 @JavascriptInterface public void novaAgentCapabilities(int id){
  try{JSONObject x=new JSONObject().put("tools",new JSONArray().put("evidence_sha256")).put("network_tools",false).put("active_testing",false);
   reply("novaAgentToolResult",id,true,x.toString());
  }catch(Exception e){reply("novaAgentToolResult",id,false,"Capabilities unavailable");}
 }
 @JavascriptInterface public void novaAgentEvidenceHash(String content,int id){
  try{
   if(content==null||content.isEmpty()||content.length()>16000)throw new Exception("Evidence must be 1–16000 characters");
   byte[] bytes=content.getBytes(StandardCharsets.UTF_8);
   if(bytes.length>32768)throw new Exception("Evidence too large");
   byte[] digest=java.security.MessageDigest.getInstance("SHA-256").digest(bytes);
   StringBuilder hex=new StringBuilder();
   for(byte b:digest)hex.append(String.format(java.util.Locale.ROOT,"%02x",b&255));
   JSONObject x=new JSONObject().put("tool","evidence_sha256").put("sha256",hex.toString()).put("bytes",bytes.length).put("local_only",true);
   reply("novaAgentToolResult",id,true,x.toString());
  }catch(Exception e){reply("novaAgentToolResult",id,false,e.getMessage()==null?"Hash failed":e.getMessage());}
 }


 // NOVA_SECURITY_LAB_V2: fixed allowlist, native per-request approval, offline only.

 // ECLIPSE_WEB_LAB_V1: one approval authorizes the complete bounded OFFLINE lab suite.
 @JavascriptInterface public void eclipseRunOfflineLab(int id){
  runOnUiThread(()->new android.app.AlertDialog.Builder(MainActivity.this)
   .setTitle("Approve Eclipse offline lab")
   .setMessage("Run 8 local mock authorization checks against sample users A and B and demo orders? No external network, credentials, or live targets are used. Results are returned to Eclipse for review.")
   .setNegativeButton("Cancel",(d,w)->reply("eclipseOfflineLabResult",id,false,"Cancelled by owner"))
   .setOnCancelListener(d->reply("eclipseOfflineLabResult",id,false,"Cancelled by owner"))
   .setPositiveButton("Approve lab",(d,w)->{
    try{
     JSONArray tests=new JSONArray();
     String[] paths={"/api/users/A","/api/users/B","/api/users/A","/api/users/B","/api/orders/demo-101","/api/orders/demo-102","/api/orders/demo-101","/api/orders/demo-102"};
     String[] actors={"A","B","B","A","A","B","B","A"};
     int passes=0;
     for(int i=0;i<paths.length;i++){
      String owner=paths[i].endsWith("/A")||paths[i].endsWith("demo-101")?"A":"B";
      boolean permitted=owner.equals(actors[i]);
      int status=permitted?200:403;
      boolean expected=(i<2||i==4||i==5)?status==200:status==403;
      if(expected)passes++;
      tests.put(new JSONObject().put("actor",actors[i]).put("method","GET")
       .put("path",paths[i]).put("expected_status",permitted?200:403)
       .put("observed_status",status).put("passed",expected)
       .put("environment","offline_mock"));
     }
     JSONObject result=new JSONObject().put("environment","offline_mock")
      .put("network_used",false).put("owner_approved",true)
      .put("tests",tests).put("passed",passes).put("total",tests.length())
      .put("finding_count",0).put("timestamp",System.currentTimeMillis())
      .put("notice","Mock results verify the harness only; no real vulnerability or server was tested.");
     reply("eclipseOfflineLabResult",id,true,result.toString());
    }catch(Exception e){reply("eclipseOfflineLabResult",id,false,"Offline lab failed");}
   }).show());
 }

 @JavascriptInterface public void novaLabRequest(String path,String account,int id){
  runOnUiThread(()->{
   if(path==null||!(path.equals("/api/orders/demo-101")||path.equals("/api/orders/demo-102")||path.equals("/api/users")||path.equals("/api/users/A")||path.equals("/api/users/B"))||!("A".equals(account)||"B".equals(account))){reply("novaLabResult",id,false,"Unsupported offline endpoint or account");return;}
   final String approvedPath=path,approvedAccount=account;
   new android.app.AlertDialog.Builder(MainActivity.this)
    .setTitle("Approve one offline lab request")
    .setMessage("GET "+approvedPath+"\nAccount: "+approvedAccount+"\n\nOffline mock only. No external network activity. Approve exactly this request once?")
    .setNegativeButton("Reject",(d,w)->reply("novaLabResult",id,false,"Rejected by user"))
    .setOnCancelListener(d->reply("novaLabResult",id,false,"Cancelled by user"))
    .setPositiveButton("Approve once",(d,w)->{
     try{
      String owner=approvedPath.endsWith("demo-101")?"A":approvedPath.endsWith("demo-102")?"B":approvedPath.endsWith("/A")?"A":approvedPath.endsWith("/B")?"B":approvedAccount;
      boolean permitted=approvedPath.equals("/api/users")||owner.equals(approvedAccount);
      JSONObject body;
      if(!permitted)body=new JSONObject().put("error","Access denied");
      else if(approvedPath.equals("/api/users"))body=new JSONObject().put("users",new JSONArray().put(new JSONObject().put("id",approvedAccount).put("role","lab_user")));
      else if(approvedPath.startsWith("/api/users/"))body=new JSONObject().put("id",owner).put("role","lab_user");
      else body=new JSONObject().put("order",approvedPath.substring("/api/orders/".length())).put("owner",owner).put("item","Lab sample");
      JSONObject r=new JSONObject().put("environment","offline_mock").put("request","GET "+approvedPath).put("account",approvedAccount).put("status",permitted?200:403).put("body",body).put("approved_once",true).put("network_used",false).put("timestamp",System.currentTimeMillis());
      reply("novaLabResult",id,true,r.toString());
     }catch(Exception e){reply("novaLabResult",id,false,"Lab simulation failed");}
    }).show();
  });
 }

 // NOVA_HTTPBIN_V1: fixed benign endpoint, no user-supplied URL, one approved GET.
 @JavascriptInterface public void novaHttpbinTest(int id){
  runOnUiThread(()->new android.app.AlertDialog.Builder(MainActivity.this)
   .setTitle("Approve one HTTPS test")
   .setMessage("GET https://httpbin.org/get?source=nova\n\nOnly this fixed endpoint. No credentials, cookies or custom headers. One request, no redirects. Approve?")
   .setNegativeButton("Reject",(d,w)->reply("novaHttpbinResult",id,false,"Rejected by user"))
   .setOnCancelListener(d->reply("novaHttpbinResult",id,false,"Cancelled by user"))
   .setPositiveButton("Approve once",(d,w)->new Thread(()->{
    java.net.HttpURLConnection c=null;
    try{
     java.net.URL u=new java.net.URL("https://httpbin.org/get?source=nova");
     c=(java.net.HttpURLConnection)u.openConnection();
     c.setInstanceFollowRedirects(false);
     c.setRequestMethod("GET");c.setConnectTimeout(8000);c.setReadTimeout(8000);
     c.setRequestProperty("Accept","application/json");
     int status=c.getResponseCode();
     java.io.InputStream stream=(status>=400)?c.getErrorStream():c.getInputStream();
     java.io.ByteArrayOutputStream bytes=new java.io.ByteArrayOutputStream();
     if(stream!=null)try(java.io.InputStream in=stream){byte[] buf=new byte[2048];int n;while((n=in.read(buf))!=-1){if(bytes.size()+n>16384)throw new Exception("Response exceeds 16 KiB limit");bytes.write(buf,0,n);}}
     JSONObject result=new JSONObject().put("environment","live_httpbin").put("request","GET https://httpbin.org/get?source=nova")
      .put("status",status).put("body",new String(bytes.toByteArray(),StandardCharsets.UTF_8))
      .put("approved_once",true).put("network_used",true).put("timestamp",System.currentTimeMillis());
     reply("novaHttpbinResult",id,true,result.toString());
    }catch(Exception e){reply("novaHttpbinResult",id,false,"HTTPS test failed: "+(e.getMessage()==null?e.getClass().getSimpleName():e.getMessage()));}
    finally{if(c!=null)c.disconnect();}
   }).start()).show());
 }


 // Eclipse V4.4: all calls come from untrusted WebView and must be validated natively.
 @JavascriptInterface public void eclipseV44Request(String raw,String scope,String method,int id){
  final EclipseV44Job job;
  try{job=eclipseV44Validate(id,raw,scope,method);}catch(Exception e){reply("eclipseV44Result",id,false,e.getMessage());return;}
  if(!eclipseV44Current.compareAndSet(null,job)){reply("eclipseV44Result",id,false,"Another V4.4 request is active");return;}
  runOnUiThread(()->{
   if(job.cancelled){eclipseV44Finish(job,false,"Cancelled");return;}
   android.app.AlertDialog dialog=new android.app.AlertDialog.Builder(MainActivity.this)
    .setTitle("Approve one Eclipse HTTPS request")
    .setMessage("Method: "+job.method+"\nExact target: "+job.url+"\nUser-declared permitted host: "+job.host+"\n\nNo redirects, cookies, credentials, query parameters or automatic follow-up. Confirm that official rules permit this exact request. HTTPS network access is real.")
    .setNegativeButton("Reject",(d,which)->eclipseV44Finish(job,false,"Rejected by owner"))
    .setOnCancelListener(d->eclipseV44Finish(job,false,"Cancelled by owner"))
    .setPositiveButton("Approve once",(d,which)->new Thread(()->eclipseV44Perform(job),"eclipse-v44-approved-request").start())
    .create();
   job.dialog=dialog;
   if(!job.cancelled)dialog.show();else eclipseV44Finish(job,false,"Cancelled");
  });
 }
 @JavascriptInterface public void eclipseV44Cancel(int id){
  EclipseV44Job job=eclipseV44Current.get();if(job==null||job.id!=id)return;
  job.cancelled=true;
  java.net.HttpURLConnection c=job.connection;if(c!=null)c.disconnect();
  android.app.AlertDialog d=job.dialog;if(d!=null)runOnUiThread(()->d.dismiss());
  eclipseV44Finish(job,false,"Cancelled by owner (already-delivered requests cannot be undone)");
 }
 @JavascriptInterface public void eclipseV44History(int id){
  new Thread(()->{try{reply("eclipseV44HistoryResult",id,true,eclipseV44ReadHistory().toString());}
   catch(Exception e){reply("eclipseV44HistoryResult",id,false,"Local evidence database unavailable");}},"eclipse-v44-history").start();
 }
 @JavascriptInterface public void eclipseV44Clear(int id){
  if(eclipseV44Current.get()!=null){reply("eclipseV44ClearResult",id,false,"Finish active request before deleting evidence");return;}
  runOnUiThread(()->new android.app.AlertDialog.Builder(MainActivity.this)
   .setTitle("Delete Eclipse evidence history?")
   .setMessage("Delete all locally saved V4.4 observations? This cannot be undone.")
   .setNegativeButton("Cancel",(d,w)->reply("eclipseV44ClearResult",id,false,"Not deleted"))
   .setOnCancelListener(d->reply("eclipseV44ClearResult",id,false,"Not deleted"))
   .setPositiveButton("Delete history",(d,w)->new Thread(()->{
     try{if(eclipseV44Current.get()!=null)throw new Exception("Request in progress");EclipseV44Database helper=new EclipseV44Database(getApplicationContext());
      try{helper.getWritableDatabase().delete("evidence",null,null);}finally{helper.close();}
      reply("eclipseV44ClearResult",id,true,"Deleted");}
     catch(Exception e){reply("eclipseV44ClearResult",id,false,"Could not delete evidence");}
    },"eclipse-v44-delete-history").start()).show());
 }

 @JavascriptInterface public void novaCopilotNotify(String title,String detail){
  if(title==null||detail==null||title.length()>100||detail.length()>300)return;
  runOnUiThread(()->copilotNotify(title,detail));
 }
 @JavascriptInterface public void novaCopilotPermission(){runOnUiThread(()->{
  if(android.os.Build.VERSION.SDK_INT>=33 && checkSelfPermission("android.permission.POST_NOTIFICATIONS")!=android.content.pm.PackageManager.PERMISSION_GRANTED)
   requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"},8743);
 });}
 @JavascriptInterface public void open(String url){runOnUiThread(()->openExternal(url));}
 }
 @Override protected void onDestroy(){EclipseV44Job job=eclipseV44Current.get();if(job!=null){job.cancelled=true;java.net.HttpURLConnection c=job.connection;if(c!=null)c.disconnect();}super.onDestroy();}
 @Override public void onBackPressed(){if(web.canGoBack())web.goBack();else super.onBackPressed();}
}
