package com.nova.jobhunter;

import android.app.Activity;
import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebSettings;
import android.content.Intent;
import android.net.Uri;
import java.net.HttpURLConnection;
import java.net.URL;
import java.io.InputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

public class MainActivity extends Activity {
  private WebView web;
  @Override public void onCreate(Bundle state) {
    super.onCreate(state);
    getWindow().setStatusBarColor(0xfff1e9db);
    getWindow().setNavigationBarColor(0xfff1e9db);
    getWindow().getDecorView().setSystemUiVisibility(android.view.View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | android.view.View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
    web=new WebView(this);
    web.getSettings().setJavaScriptEnabled(true);
    web.getSettings().setDomStorageEnabled(true);
    web.getSettings().setAllowFileAccess(true);
    web.getSettings().setAllowFileAccessFromFileURLs(false);
    web.getSettings().setAllowUniversalAccessFromFileURLs(false);
    web.addJavascriptInterface(new Bridge(),"Nova");
    web.setWebViewClient(new WebViewClient());
    setContentView(web);
    web.loadUrl("file:///android_asset/index.html");
  }
  public class Bridge {
    @JavascriptInterface public void search(String query, int requestId) {
      new Thread(() -> {
        try {
          String endpoint="https://remotive.com/api/remote-jobs?limit=100&search="+java.net.URLEncoder.encode(query,"UTF-8");
          HttpURLConnection c=(HttpURLConnection)new URL(endpoint).openConnection();
          c.setConnectTimeout(12000); c.setReadTimeout(18000);
          c.setRequestProperty("User-Agent","NOVA-JobHunter/1.0");
          int status=c.getResponseCode();
          if(status!=200)throw new Exception("Provider HTTP "+status);
          InputStream in=c.getInputStream(); ByteArrayOutputStream out=new ByteArrayOutputStream();
          byte[] buf=new byte[8192];int n;while((n=in.read(buf))!=-1){out.write(buf,0,n);if(out.size()>3000000)throw new Exception("Response too large");}
          in.close();c.disconnect();
          String data=out.toString("UTF-8");
          runOnUiThread(()->web.evaluateJavascript("novaResult("+requestId+",true,"+org.json.JSONObject.quote(data)+")",null));
        }catch(Exception e){
          String msg=e.getMessage()==null?"Network error":e.getMessage();
          runOnUiThread(()->web.evaluateJavascript("novaResult("+requestId+",false,"+org.json.JSONObject.quote(msg)+")",null));
        }
      }).start();
    }
    @JavascriptInterface public void open(String url){
      if(url==null || !url.startsWith("https://"))return;
      runOnUiThread(()->{try{startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(url)));}catch(Exception ignored){}});
    }
  }
  @Override public void onBackPressed(){if(web.canGoBack()) web.goBack(); else super.onBackPressed();}
}
