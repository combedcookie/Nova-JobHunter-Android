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

public class MainActivity extends Activity {
 private WebView web;
 private static final String KEY_ALIAS="nova_provider_credentials_v1";
 @Override public void onCreate(Bundle b){super.onCreate(b);getWindow().setStatusBarColor(0xfff1e9db);getWindow().setNavigationBarColor(0xfff1e9db);
 web=new WebView(this); WebSettings s=web.getSettings();s.setJavaScriptEnabled(true);s.setDomStorageEnabled(true);s.setAllowFileAccess(true);s.setAllowFileAccessFromFileURLs(false);s.setAllowUniversalAccessFromFileURLs(false);s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
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
 private String http(String url,JSONObject headers)throws Exception{URL u=new URL(url);if(!"https".equals(u.getProtocol()))throw new Exception("HTTPS required");HttpURLConnection c=(HttpURLConnection)u.openConnection();c.setConnectTimeout(12000);c.setReadTimeout(18000);c.setInstanceFollowRedirects(false);c.setRequestProperty("User-Agent","NOVA-JobHunter/1.1 (Android)");if(headers!=null){java.util.Iterator<String> keys=headers.keys();while(keys.hasNext()){String k=keys.next();c.setRequestProperty(k,headers.optString(k));}}try{int code=c.getResponseCode();if(code!=200)throw new Exception("Provider HTTP "+code);try(InputStream in=c.getInputStream();ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] buf=new byte[8192];int n;while((n=in.read(buf))!=-1){out.write(buf,0,n);if(out.size()>3500000)throw new Exception("Response too large");}return out.toString("UTF-8");}}finally{c.disconnect();}}
 private JSONObject profile(String provider)throws Exception{JSONObject profiles=credentials();String active=getPreferences(0).getString("active_"+provider,"default");return profiles.optJSONObject(provider+":"+active);}
 public class Bridge{
 @JavascriptInterface public void saveProfile(String provider,String name,String json,int id){new Thread(()->{try{if(!provider.matches("adzuna|usajobs|hackerone")||!name.matches("[a-zA-Z0-9_-]{1,32}"))throw new Exception("Invalid provider/profile");JSONObject val=new JSONObject(json);JSONObject all=credentials();all.put(provider+":"+name,val);saveCredentials(all);getPreferences(0).edit().putString("active_"+provider,name).apply();reply("novaConfigResult",id,true,"Saved securely on this device");}catch(Exception e){reply("novaConfigResult",id,false,e.getMessage());}}).start();}
 @JavascriptInterface public void listProfiles(int id){new Thread(()->{try{JSONObject all=credentials(),out=new JSONObject();JSONArray names=new JSONArray();java.util.Iterator<String> it=all.keys();while(it.hasNext()){String key=it.next();String[] parts=key.split(":",2);if(parts.length==2)names.put(new JSONObject().put("provider",parts[0]).put("name",parts[1]));}out.put("profiles",names);for(String p:new String[]{"adzuna","usajobs","hackerone"})out.put("active_"+p,getPreferences(0).getString("active_"+p,"default"));reply("novaConfigResult",id,true,out.toString());}catch(Exception e){reply("novaConfigResult",id,false,e.getMessage());}}).start();}
 @JavascriptInterface public void activateProfile(String provider,String name,int id){new Thread(()->{try{if(credentials().optJSONObject(provider+":"+name)==null)throw new Exception("Profile not found");getPreferences(0).edit().putString("active_"+provider,name).apply();reply("novaConfigResult",id,true,"Activated");}catch(Exception e){reply("novaConfigResult",id,false,e.getMessage());}}).start();}
 @JavascriptInterface public void deleteProfile(String provider,String name,int id){new Thread(()->{try{JSONObject all=credentials();all.remove(provider+":"+name);saveCredentials(all);reply("novaConfigResult",id,true,"Deleted");}catch(Exception e){reply("novaConfigResult",id,false,e.getMessage());}}).start();}
 @JavascriptInterface public void searchProvider(String provider,String query,String location,int id){new Thread(()->{try{String endpoint;JSONObject headers=null;JSONObject p=profile(provider);if(provider.equals("remotive")){endpoint="https://remotive.com/api/remote-jobs?limit=100&search="+enc(query);}else if(provider.equals("adzuna")){if(p==null)throw new Exception("Configure Adzuna in Settings");String appId=p.optString("id"),key=p.optString("key");if(appId.isEmpty()||key.isEmpty())throw new Exception("Adzuna ID and key required");endpoint="https://api.adzuna.com/v1/api/jobs/us/search/1?app_id="+enc(appId)+"&app_key="+enc(key)+"&results_per_page=50&what="+enc(query)+"&where="+enc(location);}else if(provider.equals("usajobs")){if(p==null)throw new Exception("Configure USAJOBS in Settings");headers=new JSONObject().put("Host","data.usajobs.gov").put("User-Agent",p.optString("email")).put("Authorization-Key",p.optString("key"));endpoint="https://data.usajobs.gov/api/search?Keyword="+enc(query)+"&LocationName="+enc(location)+"&ResultsPerPage=50";}else if(provider.equals("hackerone")){if(p==null)throw new Exception("Configure HackerOne in Settings");String username=p.optString("username"),token=p.optString("token");if(username.isEmpty()||token.isEmpty())throw new Exception("HackerOne credentials required");String basic=Base64.encodeToString((username+":"+token).getBytes(StandardCharsets.UTF_8),Base64.NO_WRAP);headers=new JSONObject().put("Authorization","Basic "+basic).put("Accept","application/json");endpoint="https://api.hackerone.com/v1/hackers/programs?page%5Bsize%5D=25";}else throw new Exception("Unknown provider");String data=http(endpoint,headers);reply("novaProviderResult",id,true,data);}catch(Exception e){reply("novaProviderResult",id,false,e.getMessage()==null?"Request failed":e.getMessage());}}).start();}
 @JavascriptInterface public void auditWebsite(String target,boolean authorized,int id){new Thread(()->{try{
 if(!authorized)throw new Exception("Confirm ownership or explicit authorization first");
 URL u=new URL(target);if(!"https".equalsIgnoreCase(u.getProtocol())||u.getUserInfo()!=null||u.getPort()!=-1)throw new Exception("Use an HTTPS hostname without credentials or port");
 String host=u.getHost();if(host==null||host.length()>253||!host.contains(".")||host.equalsIgnoreCase("localhost")||host.endsWith(".local")||host.endsWith(".internal"))throw new Exception("Public HTTPS host required");
 java.net.InetAddress[] ips=java.net.InetAddress.getAllByName(host);for(java.net.InetAddress ip:ips){byte[] a=ip.getAddress();if(ip.isAnyLocalAddress()||ip.isLoopbackAddress()||ip.isSiteLocalAddress()||ip.isLinkLocalAddress()||ip.isMulticastAddress()||a.length==4&&((a[0]&255)==0||(a[0]&255)==100&&(a[1]&192)==64||(a[0]&255)==169&&(a[1]&255)==254))throw new Exception("Private or reserved host blocked");}
 URL clean=new URL("https",host,"/");javax.net.ssl.HttpsURLConnection c=(javax.net.ssl.HttpsURLConnection)clean.openConnection();c.setRequestMethod("HEAD");c.setInstanceFollowRedirects(false);c.setConnectTimeout(8000);c.setReadTimeout(8000);c.setRequestProperty("User-Agent","NOVA-Authorized-Passive-Audit/1.2");
 JSONObject result=new JSONObject();try{int code=c.getResponseCode();result.put("host",host).put("http_status",code).put("checked_at",System.currentTimeMillis());JSONArray findings=new JSONArray();String[][] checks={{"Strict-Transport-Security","HSTS header not observed"},{"Content-Security-Policy","CSP header not observed"},{"X-Content-Type-Options","X-Content-Type-Options header not observed"},{"Referrer-Policy","Referrer-Policy header not observed"}};for(String[] check:checks){if(c.getHeaderField(check[0])==null)findings.put(check[1]);}result.put("observations",findings).put("note","Configuration observations only, not confirmed vulnerabilities. HEAD / only; verify scope and context manually.");}finally{c.disconnect();}reply("novaAuditResult",id,true,result.toString());
 }catch(Exception e){reply("novaAuditResult",id,false,e.getMessage()==null?"Audit failed":e.getMessage());}}).start();}
 @JavascriptInterface public void open(String url){runOnUiThread(()->openExternal(url));}
 }
 @Override public void onBackPressed(){if(web.canGoBack())web.goBack();else super.onBackPressed();}
}
