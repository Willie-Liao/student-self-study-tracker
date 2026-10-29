package edu.jcid.mttracker;

import android.app.Activity;
import android.os.Bundle;
import android.security.KeyChain;
import android.security.KeyChainAliasCallback;
import android.webkit.ClientCertRequest;
import android.webkit.CookieManager;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.security.PrivateKey;
import java.security.cert.X509Certificate;

public class MainActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        WebView webView = findViewById(R.id.tracker);
        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setDomStorageEnabled(true);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true);
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onReceivedClientCertRequest(WebView view, ClientCertRequest request) {
                KeyChain.choosePrivateKeyAlias(
                        MainActivity.this,
                        new KeyChainAliasCallback() {
                            @Override
                            public void alias(String alias) {
                                if (alias == null) {
                                    request.cancel();
                                    return;
                                }
                                new Thread(new Runnable() {
                                    @Override
                                    public void run() {
                                        try {
                                            PrivateKey key = KeyChain.getPrivateKey(MainActivity.this, alias);
                                            X509Certificate[] chain = KeyChain.getCertificateChain(MainActivity.this, alias);
                                            if (key == null || chain == null) {
                                                request.cancel();
                                            } else {
                                                request.proceed(key, chain);
                                            }
                                        } catch (Exception error) {
                                            request.cancel();
                                        }
                                    }
                                }).start();
                            }
                        },
                        new String[]{"RSA"},
                        null,
                        request.getHost(),
                        request.getPort(),
                        null
                );
            }
        });
        webView.loadUrl("https://47.245.34.132/");
    }
}
