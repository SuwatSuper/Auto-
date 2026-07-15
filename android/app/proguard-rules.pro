# Keep WebView JS interface hooks if any are added later.
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
