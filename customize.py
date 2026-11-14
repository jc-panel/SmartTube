#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TubePlus TV — personnalisation de SmartTube (yuliskov/SmartTube, MIT).
Lancé par le workflow GitHub Actions AVANT le build.

Ce script, sans toucher au reste de l'app :
  1. Renomme l'app en « TubePlus » et change l'applicationId (flavor stbeta)
  2. Pose le logo TubePlus (icône + bannière TV) à partir de assets/logo.png
  3. Écrit l'écran d'activation par code (LicenseActivity) branché sur jc-panel.com
  4. Fait de cet écran le point d'entrée (launcher) à la place du Splash
  5. Garde la mention de licence MIT (obligation légale)
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

# ---- Paramètres TubePlus ----------------------------------------------------
APP_NAME        = "TubePlus"
APPLICATION_ID  = "com.jcpanel.tubeplustv"
JC_PACKAGE      = "com.jcpanel.tubeplus"
API_URL         = "https://jc-panel.com/wp-json/jclic/v1/check"
OFFLINE_GRACE_DAYS = 7

APP_MODULE   = os.path.join(ROOT, "smarttubetv")
MAIN_SRC     = os.path.join(APP_MODULE, "src", "main")
MANIFEST     = os.path.join(MAIN_SRC, "AndroidManifest.xml")
BUILD_GRADLE = os.path.join(APP_MODULE, "build.gradle")
SPLASH_CLASS = "com.liskovsoft.smartyoutubetv2.tv.ui.main.SplashActivity"


def log(msg):
    print("  [customize] " + msg, flush=True)


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ============================================================================
# 1. Nom de l'app + applicationId
# ============================================================================
def rename_app():
    # app_name dans tous les flavors
    for flavor in ("main", "stbeta", "ststable", "stfdroid"):
        p = os.path.join(MAIN_SRC if flavor == "main" else os.path.join(APP_MODULE, "src", flavor),
                         "res", "values", "strings.xml")
        if os.path.exists(p):
            s = read(p)
            s2 = re.sub(r'(<string[^>]*name="app_name"[^>]*>).*?(</string>)',
                        r'\1<![CDATA[' + APP_NAME + r']]>\2', s, flags=re.S)
            if s2 != s:
                write(p, s2)
                log("app_name -> %s (%s)" % (APP_NAME, flavor))

    # applicationId du flavor stfdroid (celui qu'on build — sans services Google)
    g = read(BUILD_GRADLE)
    g2 = re.sub(r'(stfdroid\s*\{\s*\n\s*applicationId\s+")[^"]+(")',
                r'\g<1>' + APPLICATION_ID + r'\g<2>', g, count=1)
    if g2 != g:
        write(BUILD_GRADLE, g2)
        log("applicationId stfdroid -> %s" % APPLICATION_ID)
    else:
        log("!! applicationId stfdroid non trouvé (vérifier build.gradle)")


# ============================================================================
# 2. Logo TubePlus -> icône carrée + bannière TV
# ============================================================================
def apply_logo():
    src = os.path.join(ROOT, "assets", "logo.png")
    if not os.path.exists(src):
        log("!! assets/logo.png absent — logo non appliqué")
        return
    try:
        from PIL import Image
    except Exception:
        log("!! Pillow absent — logo non appliqué")
        return

    logo = Image.open(src).convert("RGBA")

    def square_icon(size):
        # fond sombre + logo centré (on garde le logo entier, letterbox)
        canvas = Image.new("RGBA", (size, size), (14, 18, 28, 255))
        w, h = logo.size
        scale = min(size / w, size / h) * 0.92
        nw, nh = int(w * scale), int(h * scale)
        small = logo.resize((nw, nh), Image.LANCZOS)
        canvas.alpha_composite(small, ((size - nw) // 2, (size - nh) // 2))
        return canvas

    def banner(w, h):
        canvas = Image.new("RGBA", (w, h), (14, 18, 28, 255))
        lw, lh = logo.size
        scale = min(w / lw, h / lh) * 0.96
        nw, nh = int(lw * scale), int(lh * scale)
        small = logo.resize((nw, nh), Image.LANCZOS)
        canvas.alpha_composite(small, ((w - nw) // 2, (h - nh) // 2))
        return canvas

    # mipmap carré + bannière (densités Android) — on écrase les noms SmartTube
    dens = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
    for name, size in dens.items():
        folder = os.path.join(MAIN_SRC, "res", "mipmap-" + name)
        os.makedirs(folder, exist_ok=True)
        ico = square_icon(size)
        for fn in ("app_icon.png", "app_icon_alt.png", "ic_launcher.png"):
            ico.save(os.path.join(folder, fn))
        # bannière TV au nom déjà utilisé par le manifest (@mipmap/app_banner)
        bscale = size / 48.0
        bw, bh = int(320 * bscale / 2), int(180 * bscale / 2)
        banner(max(320, bw), max(180, bh)).save(os.path.join(folder, "app_banner.png"))
    # bannière dédiée à l'écran d'activation (drawable/jc_banner)
    for name in ("drawable-xhdpi", "drawable"):
        folder = os.path.join(MAIN_SRC, "res", name)
        os.makedirs(folder, exist_ok=True)
        banner(640, 360).save(os.path.join(folder, "jc_banner.png"))
    log("logo appliqué (icônes + bannière TV app_banner + jc_banner)")


# ============================================================================
# 3. Écran d'activation par code (LicenseManager + LicenseActivity)
# ============================================================================
def write_license_sources():
    pkg_path = os.path.join(MAIN_SRC, "java", *JC_PACKAGE.split("."))
    os.makedirs(pkg_path, exist_ok=True)

    manager = r'''package %(pkg)s;

import android.content.Context;
import android.content.SharedPreferences;
import android.provider.Settings;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;

/** Vérifie le code d'activation auprès du panel jc-panel.com. */
public final class LicenseManager {
    private static final String API = "%(api)s";
    private static final long GRACE_MS = %(grace)dL * 24L * 60L * 60L * 1000L;
    private static final String PREF = "jc_license";

    public static final class Result {
        public boolean valid;
        public String reason = "";
        public long expires = 0L;
    }

    private LicenseManager() {}

    private static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences(PREF, Context.MODE_PRIVATE);
    }

    @SuppressWarnings("HardwareIds")
    public static String deviceId(Context c) {
        String id = Settings.Secure.getString(c.getContentResolver(), Settings.Secure.ANDROID_ID);
        return id == null ? "unknown" : id;
    }

    public static String savedCode(Context c) {
        return prefs(c).getString("code", "");
    }

    public static long expiresAt(Context c) {
        return prefs(c).getLong("expires", 0L);
    }

    /** Date de fin lisible "JJ/MM/AAAA", vide si inconnue. */
    public static String expiresText(Context c) {
        long e = expiresAt(c);
        if (e <= 0L) return "";
        java.text.SimpleDateFormat f =
            new java.text.SimpleDateFormat("dd/MM/yyyy", java.util.Locale.FRANCE);
        return f.format(new java.util.Date(e));
    }

    /** Accès autorisé hors-ligne : code non expiré et vérifié il y a moins de GRACE jours. */
    public static boolean isActivatedLocally(Context c) {
        SharedPreferences p = prefs(c);
        long expires = p.getLong("expires", 0L);
        long last = p.getLong("last_check", 0L);
        long now = System.currentTimeMillis();
        if (expires > 0L && now > expires) return false;
        return last > 0L && (now - last) < GRACE_MS;
    }

    private static void save(Context c, String code, long expires) {
        prefs(c).edit()
            .putString("code", code)
            .putLong("expires", expires)
            .putLong("last_check", System.currentTimeMillis())
            .apply();
    }

    /** Appel réseau bloquant — à lancer dans un thread. */
    public static Result check(Context c, String code) {
        Result r = new Result();
        HttpURLConnection conn = null;
        try {
            String body = "code=" + URLEncoder.encode(code, "UTF-8")
                        + "&device=" + URLEncoder.encode(deviceId(c), "UTF-8");
            conn = (HttpURLConnection) new URL(API).openConnection();
            conn.setConnectTimeout(12000);
            conn.setReadTimeout(12000);
            conn.setRequestMethod("POST");
            conn.setDoOutput(true);
            conn.setRequestProperty("Content-Type", "application/x-www-form-urlencoded");
            OutputStream os = conn.getOutputStream();
            os.write(body.getBytes("UTF-8"));
            os.close();

            int status = conn.getResponseCode();
            BufferedReader br = new BufferedReader(new InputStreamReader(
                status >= 400 ? conn.getErrorStream() : conn.getInputStream(), "UTF-8"));
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = br.readLine()) != null) sb.append(line);
            br.close();

            JSONObject j = new JSONObject(sb.toString());
            r.valid = j.optBoolean("valid", false);
            r.reason = j.optString("reason", "");
            String exp = j.optString("expires", "");
            if (r.valid) {
                long expMs = 0L;
                if (exp != null && exp.length() >= 10) {
                    // "YYYY-MM-DD HH:MM:SS" (UTC)
                    try {
                        java.text.SimpleDateFormat f =
                            new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss", java.util.Locale.US);
                        f.setTimeZone(java.util.TimeZone.getTimeZone("UTC"));
                        expMs = f.parse(exp).getTime();
                    } catch (Exception ignore) {}
                }
                save(c, code, expMs);
                r.expires = expMs;
            }
        } catch (Exception e) {
            r.valid = false;
            r.reason = "reseau";
        } finally {
            if (conn != null) conn.disconnect();
        }
        return r;
    }

    public static String message(String reason) {
        if ("code_inconnu".equals(reason)) return "Code inconnu. Vérifie les 6 chiffres.";
        if ("code_bloque".equals(reason)) return "Ce code a été bloqué.";
        if ("code_expire".equals(reason)) return "Abonnement expiré. Contacte ton vendeur.";
        if ("autre_appareil".equals(reason)) return "Ce code est déjà utilisé sur un autre appareil.";
        if ("reseau".equals(reason)) return "Pas de connexion. Vérifie ton Internet.";
        return "Code invalide.";
    }
}
''' % {"pkg": JC_PACKAGE, "api": API_URL, "grace": OFFLINE_GRACE_DAYS}

    activity = r'''package %(pkg)s;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;

/** Écran d'activation TubePlus (point d'entrée). */
public class LicenseActivity extends Activity {

    private EditText mCode;
    private TextView mStatus;
    private Button mValidate;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Déjà activé (avec tolérance hors-ligne) -> on lance l'app directement
        if (LicenseManager.isActivatedLocally(this)) {
            revalidateInBackground();
            launchApp();
            return;
        }

        int id_root = getResources().getIdentifier("jc_license", "layout", getPackageName());
        setContentView(id_root);

        mCode = (EditText) findViewById(getResources().getIdentifier("jc_code", "id", getPackageName()));
        mStatus = (TextView) findViewById(getResources().getIdentifier("jc_status", "id", getPackageName()));
        mValidate = (Button) findViewById(getResources().getIdentifier("jc_validate", "id", getPackageName()));

        mValidate.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { submit(); }
        });
        mCode.requestFocus();
    }

    private void submit() {
        final String code = mCode.getText().toString().trim();
        if (code.length() < 4) {
            mStatus.setText("Entre ton code à 6 chiffres.");
            return;
        }
        mValidate.setEnabled(false);
        mStatus.setText("Vérification…");
        new Thread(new Runnable() {
            @Override public void run() {
                final LicenseManager.Result r = LicenseManager.check(LicenseActivity.this, code);
                runOnUiThread(new Runnable() {
                    @Override public void run() {
                        mValidate.setEnabled(true);
                        if (r.valid) {
                            launchApp();
                        } else {
                            mStatus.setText(LicenseManager.message(r.reason));
                        }
                    }
                });
            }
        }).start();
    }

    private void revalidateInBackground() {
        final String code = LicenseManager.savedCode(this);
        if (code == null || code.isEmpty()) return;
        new Thread(new Runnable() {
            @Override public void run() { LicenseManager.check(LicenseActivity.this, code); }
        }).start();
    }

    private void launchApp() {
        String exp = LicenseManager.expiresText(this);
        if (exp != null && !exp.isEmpty()) {
            android.widget.Toast.makeText(this,
                "Abonnement actif jusqu'au " + exp, android.widget.Toast.LENGTH_LONG).show();
        }
        try {
            Intent i = new Intent();
            i.setClassName(getPackageName(), "%(splash)s");
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);
            startActivity(i);
        } catch (Exception ignore) {}
        finish();
    }
}
''' % {"pkg": JC_PACKAGE, "splash": SPLASH_CLASS}

    write(os.path.join(pkg_path, "LicenseManager.java"), manager)
    write(os.path.join(pkg_path, "LicenseActivity.java"), activity)
    log("sources LicenseManager + LicenseActivity écrites (%s)" % JC_PACKAGE)

    # Layout de l'écran d'activation
    layout = r'''<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:orientation="vertical"
    android:gravity="center"
    android:background="#0A0F1D"
    android:padding="48dp">

    <ImageView
        android:layout_width="wrap_content"
        android:layout_height="120dp"
        android:adjustViewBounds="true"
        android:src="@drawable/jc_banner"
        android:layout_marginBottom="28dp"/>

    <TextView
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:text="Entre ton code d'activation"
        android:textColor="#FFFFFF"
        android:textSize="22sp"
        android:layout_marginBottom="18dp"/>

    <EditText
        android:id="@+id/jc_code"
        android:layout_width="360dp"
        android:layout_height="wrap_content"
        android:inputType="number"
        android:maxLength="6"
        android:gravity="center"
        android:textSize="30sp"
        android:letterSpacing="0.3"
        android:textColor="#FFFFFF"
        android:textColorHint="#5F719A"
        android:hint="000000"
        android:focusable="true"
        android:focusableInTouchMode="true"/>

    <Button
        android:id="@+id/jc_validate"
        android:layout_width="360dp"
        android:layout_height="wrap_content"
        android:layout_marginTop="18dp"
        android:text="Valider"
        android:textColor="#FFFFFF"
        android:textSize="18sp"
        android:background="#2B6AD6"
        android:focusable="true"/>

    <TextView
        android:id="@+id/jc_status"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:layout_marginTop="20dp"
        android:text=""
        android:textColor="#FFA6A6"
        android:textSize="15sp"/>

    <TextView
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:layout_marginTop="36dp"
        android:text="Basé sur SmartTube (MIT) · yuliskov"
        android:textColor="#3A4868"
        android:textSize="11sp"/>

</LinearLayout>
'''
    write(os.path.join(MAIN_SRC, "res", "layout", "jc_license.xml"), layout)
    log("layout jc_license.xml écrit")


# ============================================================================
# 4. Manifest : LicenseActivity devient le launcher à la place du Splash
# ============================================================================
def patch_manifest():
    m = read(MANIFEST)

    # a) retirer les catégories LAUNCHER du premier intent-filter du Splash
    #    (on neutralise le bloc MAIN/LAUNCHER/LEANBACK du Splash)
    launcher_block = re.compile(
        r'<intent-filter>\s*'
        r'<action android:name="android\.intent\.action\.MAIN"\s*/>\s*'
        r'<category android:name="android\.intent\.category\.DEFAULT"\s*/>\s*'
        r'<category android:name="android\.intent\.category\.LAUNCHER"\s*/>\s*'
        r'<category android:name="android\.intent\.category\.LEANBACK_LAUNCHER"\s*/>\s*'
        r'</intent-filter>', re.S)
    m2, n = launcher_block.subn('<!-- launcher déplacé vers LicenseActivity -->', m, count=1)
    if n:
        log("bloc launcher du Splash neutralisé")
        m = m2
    else:
        log("!! bloc launcher du Splash non trouvé (format différent) — à vérifier")

    # b) déclarer LicenseActivity comme nouveau launcher, juste après <application ...>
    license_activity = (
        '\n        <activity\n'
        '            android:name="%(pkg)s.LicenseActivity"\n'
        '            android:exported="true"\n'
        '            android:launchMode="singleTask"\n'
        '            android:screenOrientation="landscape"\n'
        '            android:theme="@android:style/Theme.Black.NoTitleBar.Fullscreen">\n'
        '            <intent-filter>\n'
        '                <action android:name="android.intent.action.MAIN" />\n'
        '                <category android:name="android.intent.category.DEFAULT" />\n'
        '                <category android:name="android.intent.category.LAUNCHER" />\n'
        '                <category android:name="android.intent.category.LEANBACK_LAUNCHER" />\n'
        '            </intent-filter>\n'
        '        </activity>\n'
    ) % {"pkg": JC_PACKAGE}

    m3, n2 = re.subn(r'(<application\b[^>]*>)', r'\1' + license_activity, m, count=1)
    if n2:
        log("LicenseActivity déclarée comme launcher")
        m = m3
    else:
        log("!! balise <application> non trouvée")

    # c) bannière TV de l'application
    if 'android:banner' not in m:
        m = re.sub(r'(<application\b)', r'\1 android:banner="@drawable/jc_banner"', m, count=1)
        log("bannière TV ajoutée à <application>")

    write(MANIFEST, m)


def main():
    log("=== Personnalisation TubePlus TV ===")
    rename_app()
    apply_logo()
    write_license_sources()
    patch_manifest()
    log("=== Terminé ===")


if __name__ == "__main__":
    sys.exit(main())
