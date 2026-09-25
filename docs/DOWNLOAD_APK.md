# How to Download and Install the WrapItUp Android APK

This guide explains how anyone can download and install the **WrapItUp** mobile app on any Android phone or tablet.

---

## 🚀 Option 1: Direct Download from GitHub Releases (Recommended for Everyone)

1. Open the WrapItUp Releases page:
   👉 **[WrapItUp Releases on GitHub](https://github.com/AfifaKureshi/WrapItUp/releases)**
2. Under the latest release, click on **`WrapItUp-release.apk`** to download it directly to your phone.
3. Once downloaded, tap the APK notification or open your **Files / Downloads** app and tap `WrapItUp-release.apk`.
4. If Android asks: *"For your security, your phone is not allowed to install unknown apps from this source"*:
   - Tap **Settings**
   - Toggle **Allow from this source** ON
   - Tap **Back** and then tap **Install**
5. Launch **WrapItUp**!

---

## 🛠️ Option 2: Download from GitHub Actions (Latest Builds)

If a build just finished on GitHub Actions:

1. Go to the **Actions** tab:
   👉 **[WrapItUp GitHub Actions](https://github.com/AfifaKureshi/WrapItUp/actions)**
2. Click the top workflow run labeled **Build & Release Android APK**.
3. Scroll down to the **Artifacts** section at the bottom of the page.
4. Click **`WrapItUp-Android-APK`** to download the zip file containing the APK.
5. Extract the zip and transfer/install `WrapItUp-release.apk` on your Android device.

---

## 🌐 Connecting the Mobile App to the Backend

When you first launch the WrapItUp app:

1. On the login screen, look for the **Server** button in the header (or tap the message if a connection error appears).
2. Choose your connection mode:
   - **Android Emulator**: Select `http://10.0.2.2:8000`.
   - **Local PC / Physical Device**: Enter your computer's local Wi-Fi IP (e.g., `http://192.168.1.15:8000`). Make sure your PC is running `run_backend_windows.bat` on the same Wi-Fi.
   - **Cloud Hosted**: Enter your deployed backend URL (e.g., `https://wrapitup-api.onrender.com`).
3. Tap **Test Connection** to verify that the app can communicate with the server.
4. Tap **Save & Reconnect**.
5. Sign in using the demo accounts (Farmer, Manufacturer, Researcher) or register a new workspace account!
