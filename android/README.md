# Tor Life OS — Android (WebView) project

โปรเจกต์ Android ที่ห่อแอป `TorLifeOS_v6_0.html` ไว้ใน WebView แล้ว build เป็น `.apk` ได้
แอปเก็บข้อมูลทั้งหมดใน `localStorage` ของ WebView (persist ในพื้นที่ส่วนตัวของแอป) จึง **ใช้งานออฟไลน์ได้เต็มรูปแบบ**

## โครงสร้าง
```
android/
├─ app/
│  ├─ src/main/
│  │  ├─ assets/index.html          ← ตัวแอป (สำเนาของ TorLifeOS_v6_0.html)
│  │  ├─ java/com/torlife/os/MainActivity.kt
│  │  ├─ res/                        ← ไอคอน (adaptive), ธีม, สี, ชื่อแอป
│  │  └─ AndroidManifest.xml
│  ├─ build.gradle
│  └─ proguard-rules.pro
├─ build.gradle · settings.gradle · gradle.properties
└─ gradlew · gradle/wrapper/…        ← Gradle wrapper (8.7) มีให้พร้อม
```

## วิธี build

### ด้วย Android Studio (แนะนำ)
1. **Open** โฟลเดอร์ `android/` (ไม่ใช่ root ของ repo)
2. รอ Gradle sync — Android Studio จะดาวน์โหลด Android SDK, Android Gradle Plugin (8.5.2)
   และ Gradle 8.7 ให้อัตโนมัติ (ต้องมีอินเทอร์เน็ตครั้งแรก)
3. **Build → Build APK(s)** → ไฟล์อยู่ที่ `app/build/outputs/apk/debug/app-debug.apk`

### ด้วยบรรทัดคำสั่ง
ต้องมี Android SDK + ตั้ง `ANDROID_HOME` (หรือมีไฟล์ `local.properties` ที่ชี้ `sdk.dir`)
```bash
cd android
./gradlew assembleDebug          # ได้ APK สำหรับทดสอบ
./gradlew assembleRelease        # ได้ APK release (ต้อง config signing เพิ่มถ้าจะลง Play Store)
```

## สเปก
| รายการ | ค่า |
|--------|-----|
| applicationId | `com.torlife.os` |
| minSdk / targetSdk / compileSdk | 24 / 34 / 34 |
| versionName / versionCode | 6.0 / 60 |
| ภาษา | Kotlin |
| สิทธิ์ | `INTERNET` (ใช้เฉพาะโหมด AI/โหลดฟอนต์ — แอปหลักทำงานได้โดยไม่ต้องต่อเน็ต) |

## อัปเดตแอปเมื่อแก้ไฟล์ HTML
คัดลอกไฟล์ล่าสุดทับ asset แล้ว build ใหม่:
```bash
cp ../TorLifeOS_v6_0.html app/src/main/assets/index.html
./gradlew assembleDebug
```

## หมายเหตุ
- `domStorageEnabled = true` เปิดไว้ — จำเป็นต่อการเซฟข้อมูล ห้ามปิด
- ปุ่ม Back จะย้อน history ของ WebView ก่อน แล้วจึงออกจากแอป
- ข้อมูลของแอปนี้แยกจากข้อมูลบนเบราว์เซอร์/PWA — ย้ายข้ามกันด้วยปุ่ม **สำรอง/กู้คืน JSON** ในแอป
