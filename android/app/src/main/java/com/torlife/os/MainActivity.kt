package com.torlife.os

import android.annotation.SuppressLint
import android.os.Bundle
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback

/**
 * Tor Life OS — a single-file offline HTML app hosted in a WebView.
 * All data lives in the WebView's localStorage (persisted in the app's
 * private storage), so the app is fully usable with no network.
 */
class MainActivity : ComponentActivity() {

    private lateinit var web: WebView

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        web = WebView(this)
        with(web.settings) {
            javaScriptEnabled = true          // app logic
            domStorageEnabled = true          // localStorage — REQUIRED for data persistence
            databaseEnabled = true
            allowFileAccess = true            // load bundled asset
            allowContentAccess = true
            cacheMode = WebSettings.LOAD_DEFAULT
            loadWithOverviewMode = true
            useWideViewPort = true
            textZoom = 100                    // ignore system font-scale zoom jumps
            mediaPlaybackRequiresUserGesture = true
        }

        // Keep normal navigation inside the app; let the app's own fetch() calls
        // (e.g. optional AI mode) go to the network as usual.
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                return false
            }
        }

        setContentView(web)

        if (savedInstanceState == null) {
            web.loadUrl("file:///android_asset/index.html")
        } else {
            web.restoreState(savedInstanceState)
        }

        // Back button navigates WebView history, then exits.
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (web.canGoBack()) web.goBack() else finish()
            }
        })
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        web.saveState(outState)
    }

    override fun onDestroy() {
        web.destroy()
        super.onDestroy()
    }
}
